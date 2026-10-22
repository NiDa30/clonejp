"""A small local web UI: link/file inputs on the left, OCR results on the right."""
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

# Streamlit executes this file directly, including on Windows.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from scan_tool.core import STORE, JobManager, engine_status, safe_filename
from scan_tool.setup_languages import install_models

st.set_page_config(page_title="Scan → Văn bản", page_icon="📄", layout="wide")


@st.cache_resource
def manager():
    return JobManager()


def main():
    jobs = manager()
    st.title("Scan → Văn bản")
    st.caption("Giáo trình Nhật–Việt · Xử lý trên máy · Không dùng API AI")
    selected_mode = st.selectbox("Chế độ OCR", ["Cân bằng Nhật–Việt · v2", "Nhanh · Tesseract 200 DPI"],
                                  help="Cân bằng tách vùng chữ và nhận dạng tiếng Việt riêng. Nhanh ưu tiên tốc độ, có thể sai nhiều hơn.")
    mode = "balanced" if selected_mode.startswith("Cân bằng") else "fast"
    status = engine_status(mode)
    if not status["ready"]:
        st.warning(status["message"])
        with st.expander("Cài OCR một lần", expanded=True):
            st.markdown("Cài Tesseract trên Windows bằng PowerShell, rồi mở lại ứng dụng:")
            st.code("winget install --id UB-Mannheim.TesseractOCR --exact --source winget", language="powershell")
            st.markdown("Sau khi có Tesseract, tải bộ ngôn ngữ Nhật–Việt–Anh chính thức bằng nút bên dưới.")
            if st.button("Tải bộ ngôn ngữ", icon=":material/download:"):
                try:
                    with st.spinner("Đang tải mô hình OCR…"):
                        install_models()
                    st.rerun()
                except Exception:
                    st.error("Chưa tải được mô hình. Kiểm tra Internet rồi thử lại.")
    else:
        st.caption(status["message"])
    if "inputs" not in st.session_state:
        st.session_state.inputs = []
    if "upload_batch" not in st.session_state:
        st.session_state.upload_batch = 0
        st.session_state.uploaded_ids = set()
    left, right = st.columns([1, 1.35], gap="large")
    with left:
        st.subheader("Input")
        with st.form("add_link", clear_on_submit=True):
            address, add = st.columns([7, 1], vertical_alignment="bottom")
            url = address.text_input("Link PDF hoặc ảnh", placeholder="https://…/giao-trinh.pdf")
            submitted = add.form_submit_button("＋", help="Thêm đường link")
        if submitted:
            parsed = urlsplit(url.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                st.error("Nhập link HTTP/HTTPS tải trực tiếp, không chứa tài khoản hoặc mật khẩu.")
            elif any(item.get("url") == url.strip() for item in st.session_state.inputs):
                st.info("Link này đã có trong danh sách.")
            else:
                name = safe_filename(Path(parsed.path).name or "tai-lieu.pdf")
                st.session_state.inputs.append({"id": uuid.uuid4().hex, "name": name, "url": url.strip()})
        uploads = st.file_uploader("Hoặc chọn PDF / ảnh từ máy", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"],
                                   accept_multiple_files=True, key=f"files-{st.session_state.upload_batch}")
        for upload in uploads or []:
            if upload.file_id in st.session_state.uploaded_ids:
                continue
            inbox = STORE / "inputs"
            inbox.mkdir(exist_ok=True)
            # Selecting a file is sufficient; no second "add file" click required.
            entry_id = uuid.uuid4().hex
            name = safe_filename(upload.name)
            folder = inbox / entry_id
            folder.mkdir()
            path = folder / name
            try:
                with path.open("wb") as output:
                    output.write(upload.getbuffer())
                st.session_state.inputs.append({"id": entry_id, "name": name, "path": str(path.resolve())})
                st.session_state.uploaded_ids.add(upload.file_id)
            except OSError:
                path.unlink(missing_ok=True)
                st.error(f"Không lưu được {name}. Kiểm tra dung lượng và quyền ghi thư mục dự án.")
        if not st.session_state.inputs:
            st.info("Thêm link bằng biểu tượng ＋ hoặc chọn nhiều file để bắt đầu.")
        for item in list(st.session_state.inputs):
            label, remove = st.columns([7, 1], vertical_alignment="center")
            label.write(item["name"])
            label.caption("Link tải trực tiếp" if item.get("url") else "File trên máy")
            if remove.button("✕", key="remove-" + item["id"], help="Xóa khỏi danh sách đầu vào"):
                st.session_state.inputs.remove(item)
                st.rerun()
        searchable = st.checkbox("Xuất thêm PDF có thể tìm kiếm", help="Giữ ảnh gốc và thêm lớp chữ; tốn thêm dung lượng và thời gian.")
        st.caption("Luôn xuất Markdown (.md), văn bản (.txt) và dữ liệu trang (.json). Tên file giữ theo đầu vào.")
        if not status["ready"]:
            st.info("Chưa thể bắt đầu: " + status["message"] + " Bấm Tải bộ ngôn ngữ ở phía trên nếu thiếu jpn/vie.")
        elif not st.session_state.inputs:
            st.caption("Chọn ít nhất một file hoặc thêm link bằng nút ＋ để bật nút xử lý.")
        else:
            st.caption(f"Đã sẵn sàng: {len(st.session_state.inputs)} tài liệu.")
        if st.button("Bắt đầu xử lý", type="primary", icon=":material/play_arrow:",
                     disabled=not status["ready"] or not st.session_state.inputs, use_container_width=True):
            jobs.refresh_plan()
            for item in st.session_state.inputs:
                jobs.create(item["name"], "url" if item.get("url") else "file",
                            path=item.get("path"), url=item.get("url"), searchable=searchable, mode=mode)
            st.session_state.inputs = []
            st.session_state.upload_batch += 1
            st.session_state.uploaded_ids = set()
            st.rerun()
        st.caption(f"Tự động: tối đa {jobs.plan['workers']} tài liệu đồng thời · 1 luồng OCR/tài liệu · {220 if mode == 'balanced' else 200} DPI")
        st.caption("Số luồng được tính khi mở ứng dụng theo CPU/RAM trống; không tải cả tài liệu 100+ trang vào bộ nhớ ảnh.")
    with right:
        render_output(jobs)
    with st.expander("Nơi lưu dữ liệu và giới hạn"):
        st.code(str(STORE))
        st.write("Mỗi tài liệu có thư mục riêng nên các file trùng tên không ghi đè nhau. Sau khi đóng ứng dụng, mở lại và bấm Tiếp tục nếu tác vụ bị ngắt.")
        st.write("Link phải trả về PDF/ảnh trực tiếp. Với Google Drive, trang yêu cầu đăng nhập hoặc link trang web, hãy tải file về rồi chọn file từ máy.")
        st.write("Furigana, chữ nhỏ, bảng và nhiều cột có thể cần sửa. Markdown là văn bản chỉnh sửa được, không bảo đảm giữ nguyên bố cục scan.")


@st.fragment(run_every=2)
def render_output(jobs):
    st.subheader("Output")
    records = jobs.jobs()
    if not records:
        st.info("Kết quả và tiến độ từng tài liệu sẽ xuất hiện ở đây.")
        return
    for job in records:
        with st.container(border=True):
            st.markdown("**" + job.get("name", "Tài liệu") + "**")
            state = job.get("state", "queued")
            total = job.get("total", 0)
            current = job.get("page", 0)
            if total:
                st.progress(min(1.0, current / total), text=f"{current}/{total} trang")
            message = job.get("message", "Đang chờ")
            if state == "failed":
                st.error(message)
            elif state == "completed":
                st.success("Hoàn thành")
                if job.get("empty_pages"):
                    st.warning(f"{job['empty_pages']} trang không có chữ nhận dạng được; kiểm tra bản gốc.")
                if job.get("review_pages"):
                    st.warning(f"{job['review_pages']} trang có vùng chữ cần đối chiếu. Điểm OCR không phải tỷ lệ chính xác.")
                for name in job.get("files", []):
                    target = Path(job["folder"]) / "output" / name
                    if target.is_file():
                        # Read on demand, not every 2-second UI refresh.
                        st.download_button("Tải " + name, data=lambda p=target: p.read_bytes(),
                                           file_name=name, key=job["id"] + name, on_click="ignore")
                if st.button("Xem Markdown", key="view-" + job["id"]):
                    st.session_state["show-md-" + job["id"]] = not st.session_state.get("show-md-" + job["id"], False)
                if st.session_state.get("show-md-" + job["id"]):
                    text_path = next((Path(job["folder"]) / "output").glob("*.md"), None)
                    if text_path:
                        with text_path.open(encoding="utf-8") as text:
                            preview = text.read(30000)
                        st.code(preview, language="markdown")
                        st.caption("Xem trước tối đa 30.000 ký tự; tải file để chỉnh sửa toàn bộ.")
                with st.expander("Đối chiếu ảnh gốc và sửa chữ từng trang"):
                    number = st.number_input("Trang", min_value=1, max_value=max(1, total), value=1,
                                             key="page-" + job["id"])
                    if st.button("Mở trang", key="open-page-" + job["id"]):
                        st.session_state["inspect-" + job["id"]] = int(number)
                    selected = st.session_state.get("inspect-" + job["id"])
                    if selected and job.get("input_path"):
                        source = Path(job["input_path"])
                        if source.is_file():
                            image_column, text_column = st.columns(2)
                            image_column.image(page_preview(str(source), selected, source.stat().st_mtime_ns))
                            text_file = next((Path(job["folder"]) / "output").glob("*.txt"), None)
                            if text_file:
                                pages = text_file.read_text(encoding="utf-8").split("\f")
                                original = pages[selected - 1].strip() if selected <= len(pages) else ""
                                edited = text_column.text_area(f"Chữ trang {selected}", original, height=480,
                                                               key=f"edit-{job['id']}-{selected}")
                                text_column.download_button("Tải trang đã sửa", edited,
                                                            file_name=f"{text_file.stem}-trang-{selected}.md",
                                                            key=f"save-page-{job['id']}-{selected}", on_click="ignore")
                                text_column.caption("Bản sửa tải riêng; không ghi đè kết quả OCR gốc.")
            else:
                st.caption(message)
            if state in {"running", "queued", "downloading"}:
                if st.button("Dừng", key="cancel-" + job["id"]):
                    jobs.cancel(job["id"])
                    st.info("Đã yêu cầu dừng. Đang giữ lại các trang đã xong.")
            elif state in {"failed", "cancelled", "interrupted"}:
                if st.button("Tiếp tục", key="resume-" + job["id"]):
                    jobs.start(job["id"])
                    st.rerun(scope="fragment")


@st.cache_data(max_entries=4, ttl=600)
def page_preview(path, number, modified):
    import fitz
    with fitz.open(path) as document:
        return document[number - 1].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False).tobytes("png")


if __name__ == "__main__":
    main()
