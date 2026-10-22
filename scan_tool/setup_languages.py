"""Download pinned official fast models; the OCR engine itself is installed separately."""
from urllib.request import urlopen

from scan_tool.core import STORE

REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
CONFIG_REVISION = "3decf1c8252ba6dbeef0bf908f4b0aab7f18d113"


def install_models():
    folder = STORE / "tessdata"
    folder.mkdir(parents=True, exist_ok=True)
    for filename in ("jpn.traineddata", "vie.traineddata", "eng.traineddata", "pdf.ttf"):
        target = folder / filename
        minimum = 128 if filename == "pdf.ttf" else 100_000
        if target.is_file() and target.stat().st_size > minimum:
            continue
        temporary = target.with_suffix(".part")
        try:
            url = (f"https://raw.githubusercontent.com/tesseract-ocr/tessconfigs/{CONFIG_REVISION}/pdf.ttf"
                   if filename == "pdf.ttf" else
                   f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}/{filename}")
            with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size < minimum:
                raise RuntimeError("Tệp mô hình nhận được không hợp lệ.")
            if filename == "pdf.ttf" and temporary.read_bytes()[:4] not in {b"\x00\x01\x00\x00", b"OTTO"}:
                raise RuntimeError("Tệp font PDF nhận được không hợp lệ.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    install_models()
    print("Da cai mo hinh jpn + vie + eng vao .ocr-local/tessdata")
