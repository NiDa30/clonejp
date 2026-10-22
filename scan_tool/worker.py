"""One-document worker; invoked as a module to isolate PDF rendering on Windows."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import fitz

from scan_tool.core import atomic_json, engine_environment, engine_status, fetch_document, load_json, safe_filename


class Cancelled(Exception):
    pass


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_tesseract(command, folder):
    with (folder / "ocr-engine.log").open("ab") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log,
                                   env=engine_environment(),
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 300
        try:
            while process.poll() is None:
                if (folder / "cancel").exists():
                    raise Cancelled()
                if time.monotonic() > deadline:
                    raise RuntimeError("Một trang OCR vượt 5 phút. Kiểm tra trang hoặc thử tiếp tục.")
                time.sleep(0.2)
            if process.returncode:
                raise RuntimeError("Tesseract không đọc được trang. Xem ocr-engine.log trong thư mục tác vụ.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def process_document(folder):
    job = load_json(folder / "job.json")
    status = {"state": "running", "page": 0, "total": 0, "message": "Chuẩn bị tài liệu",
              "worker_pid": os.getpid()}

    def progress(**values):
        status.update(values)
        atomic_json(folder / "status.json", status)

    try:
        engine = engine_status()
        if not engine["ready"]:
            raise RuntimeError(engine["message"])
        source = Path(job["input_path"]) if job.get("input_path") else folder / "missing"
        if not source.is_file():
            if not job.get("url"):
                raise RuntimeError("Không tìm thấy file đầu vào.")
            progress(state="downloading", message="Đang tải tài liệu từ link")
            source = fetch_document(job["url"], folder)
            job["input_path"] = str(source.resolve())
            job["name"] = source.name
            atomic_json(folder / "job.json", job)
        if (folder / "cancel").exists():
            raise Cancelled()
        signature = file_digest(source) + "-jpn-vie-eng-300-v1"
        work = folder / "pages" / signature
        work.mkdir(parents=True, exist_ok=True)
        output = folder / "output"
        output.mkdir(exist_ok=True)
        stem = Path(safe_filename(source.name)).stem
        markdown = output / (stem + ".md")
        plain = output / (stem + ".txt")
        metadata = output / (stem + ".json")
        progress(state="running", message="Đang mở tài liệu")
        with fitz.open(source) as document:
            if document.needs_pass:
                raise RuntimeError("PDF có mật khẩu. Hãy chọn bản PDF đã được bạn mở khóa hợp lệ.")
            total = len(document)
            if not total:
                raise RuntimeError("Tài liệu không có trang.")
            progress(total=total)
            page_info = []
            # Write partial exports; only publish complete exports after all pages succeed.
            with markdown.with_suffix(".md.part").open("w", encoding="utf-8") as md, \
                    plain.with_suffix(".txt.part").open("w", encoding="utf-8") as txt:
                md.write(f"# {stem}\n\n")
                for index, page in enumerate(document):
                    if (folder / "cancel").exists():
                        raise Cancelled()
                    base = work / f"page-{index + 1:05d}"
                    text_path = base.with_suffix(".txt")
                    page_pdf = base.with_suffix(".pdf")
                    marker = base.with_suffix(".json")
                    cached = load_json(marker)
                    need_pdf = bool(job.get("searchable"))
                    if not text_path.is_file() or not cached or (need_pdf and not page_pdf.is_file()):
                        progress(page=index, message=f"Đang nhận dạng trang {index + 1}/{total}")
                        # Preserve native text when available; scanned pages use OCR.
                        native = page.get_text("text").strip()
                        # A page number over a scanned image is not usable native text.
                        if len(native) < 60:
                            native = ""
                        method = "native_text" if native else "tesseract"
                        if native:
                            text_path.write_text(native, encoding="utf-8")
                            if need_pdf:
                                with fitz.open() as single:
                                    if document.is_pdf:
                                        single.insert_pdf(document, from_page=index, to_page=index)
                                    else:
                                        with fitz.open("pdf", document.convert_to_pdf()) as converted:
                                            single.insert_pdf(converted, from_page=index, to_page=index)
                                    single.save(page_pdf)
                        else:
                            scale = min(300 / 72, (40_000_000 / max(1, page.rect.width * page.rect.height)) ** 0.5)
                            dpi = round(scale * 72)
                            image = base.with_suffix(".png")
                            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
                            pix.save(image)
                            del pix
                            command = [engine["executable"], str(image), str(base), "-l", "jpn+vie+eng",
                                       "--dpi", str(dpi), "--psm", "3", "-c", "tessedit_create_txt=1"]
                            if need_pdf:
                                command.extend(["-c", "tessedit_create_pdf=1"])
                            try:
                                run_tesseract(command, folder)
                                if not text_path.is_file() or (need_pdf and not page_pdf.is_file()):
                                    raise RuntimeError("Tesseract không tạo đủ file đầu ra. Cài lại bộ ngôn ngữ và thử tiếp tục.")
                            finally:
                                image.unlink(missing_ok=True)
                        cached = {"page": index + 1, "method": method}
                        atomic_json(marker, cached)
                    text = text_path.read_text(encoding="utf-8").strip()
                    md.write(f"## Trang {index + 1}\n\n{text}\n\n")
                    txt.write(("\n\f\n" if index else "") + text + "\n")
                    page_info.append({**cached, "characters": len(text), "empty": not bool(text)})
                    progress(page=index + 1, message=f"Đã nhận dạng {index + 1}/{total} trang")
            if job.get("searchable"):
                progress(message="Đang ghép PDF có thể tìm kiếm")
                merged = work / "merged.pdf"
                merged.unlink(missing_ok=True)
                for index in range(total):
                    if (folder / "cancel").exists():
                        raise Cancelled()
                    with fitz.open(work / f"page-{index + 1:05d}.pdf") as one:
                        if not merged.exists():
                            one.save(merged)
                        else:
                            with fitz.open(merged) as combined:
                                combined.insert_pdf(one)
                                combined.saveIncr()
                final_pdf = output / (stem + ".pdf")
                shutil_copy = final_pdf.with_suffix(".pdf.part")
                # No second full raster pass or all-pages image list in RAM.
                import shutil
                shutil.copyfile(merged, shutil_copy)
                shutil_copy.replace(final_pdf)
            markdown.with_suffix(".md.part").replace(markdown)
            plain.with_suffix(".txt.part").replace(plain)
            atomic_json(metadata, {"input_name": source.name, "pages": page_info,
                                   "languages": ["jpn", "vie", "eng"], "ai_api_calls": 0})
            files = [markdown.name, plain.name, metadata.name]
            if job.get("searchable"):
                files.append(stem + ".pdf")
            progress(state="completed", page=total, total=total, message="Hoàn thành",
                     files=files, empty_pages=sum(item["empty"] for item in page_info))
    except Cancelled:
        progress(state="cancelled", message="Đã dừng; các trang OCR xong được giữ để tiếp tục.")
    except Exception as exc:
        # Do not expose full signed URLs from network exceptions in the interface.
        message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else f"{type(exc).__name__}: không xử lý được tài liệu. Kiểm tra file/link và thử lại."
        progress(state="failed", message=message)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(process_document(Path(sys.argv[1]).resolve()))
