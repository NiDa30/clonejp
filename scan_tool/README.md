# Scan → Văn bản: giáo trình Nhật–Việt

Giao diện web local có hai phần Input và Output, chạy trên Windows 11. Tesseract nhận dạng `jpn+vie+eng` trên CPU, không gửi tài liệu tới API AI, không tốn token. Internet cần cho cài đặt ban đầu và tải tài liệu đầu vào bằng link.

## Lấy và chạy code

Nếu đã clone dự án, đóng ứng dụng cũ rồi chạy trong Command Prompt:

```bat
cd /d "E:\repo e\clonejp"
git pull --ff-only
start-ocr-windows.bat
```

Nếu chưa có repository, tải ZIP từ GitHub và giải nén, hoặc dùng:

```bat
git clone https://github.com/NiDa30/clonejp.git
cd clonejp
start-ocr-windows.bat
```

Cần Python 3.11 trở lên. Script tạo `.venv-ocr`, cài đúng phiên bản thư viện và mở giao diện trong trình duyệt mặc định. Chỉ lắng nghe trên máy của bạn. Giữ cửa sổ lệnh mở khi xử lý.

## Cài OCR một lần

1. Cài Tesseract bằng PowerShell hoặc Command Prompt:

   ```powershell
   winget install --id UB-Mannheim.TesseractOCR --exact --source winget
   ```

   Đây là gói Windows do bên thứ ba đóng gói qua winget. Nếu máy không có winget, tham khảo hướng dẫn Windows tại https://tesseract-ocr.github.io/tessdoc/Installation.html. Ứng dụng tìm Tesseract trong PATH hoặc `C:\Program Files\Tesseract-OCR`. Có thể đặt biến `TESSERACT_CMD` trỏ tới `tesseract.exe` nếu cài ở nơi khác.

2. Chạy `start-ocr-windows.bat`.
3. Nếu giao diện báo thiếu ngôn ngữ, bấm **Tải bộ ngôn ngữ**. Bộ `jpn`, `vie`, `eng` dạng fast và font PDF được tải từ repository chính thức Tesseract, khóa theo commit; không tắt TLS. Không tải lại khi file đã có.

Có thể cài bộ ngôn ngữ bằng lệnh:

```bat
.venv-ocr\Scripts\python.exe -m scan_tool.setup_languages
```

## Dùng giao diện

- Dán link PDF/ảnh tải trực tiếp, bấm **＋**. Bấm **✕** để bỏ khỏi danh sách trước khi chạy.
- Hoặc chọn nhiều file PDF, PNG, JPG, TIFF, WebP. File được tự thêm vào danh sách, không cần bấm thêm lần nữa. Upload tối đa 512 MB/file; tải link tối đa 1 GB/file.
- Bấm **Bắt đầu xử lý**. Mỗi tài liệu có tiến độ riêng và nút **Dừng**. Các tài liệu vượt số slot sẽ chờ lượt.
- Tác vụ lỗi hoặc bị ngắt có nút **Tiếp tục**; các trang đã OCR xong được dùng lại nếu input không đổi.
- Trong Output, tải từng file hoặc xem trước Markdown. Văn bản có thể chọn, copy và chỉnh sửa bằng trình soạn thảo.
- Tùy chọn **Xuất thêm PDF có thể tìm kiếm** giữ ảnh từng trang và thêm lớp chữ; tốn thêm thời gian và dung lượng.

Link trang web, trang đăng nhập hoặc link xem Google Drive không tương đương link tải file. Với những nguồn này, tải PDF về máy rồi chọn file. Không nhập mật khẩu/cookie vào ứng dụng.

## Kết quả và tên file

Ví dụ input `Giáo trình N5.pdf` tạo:

```text
.ocr-local/
  <mã-tác-vụ>/
    output/
      Giáo trình N5.md
      Giáo trình N5.txt
      Giáo trình N5.json
      Giáo trình N5.pdf    (nếu chọn PDF có thể tìm kiếm)
```

Markdown có tiêu đề `Trang 1`, `Trang 2`…; TXT là văn bản thuần, JSON chứa thông tin nhận dạng theo trang và cảnh báo trang rỗng. Tên không hợp lệ trên Windows được thay ký tự, tên quá dài được rút gọn. Tài liệu trùng tên có thư mục tác vụ riêng, không ghi đè nhau. Mỗi trang có cache để tiếp tục; đầu ra chỉ được đánh dấu hoàn thành sau khi xử lý đủ tài liệu.

Toàn bộ dữ liệu và mô hình nằm trong `.ocr-local`, đã loại khỏi Git. Có thể mở thư mục này để lấy kết quả trực tiếp. Không xóa thư mục tác vụ khi đang chạy. Cache và PDF tìm kiếm được có thể tốn dung lượng đáng kể với scan 100+ trang.

## Song song và hiệu năng

Ứng dụng tự chọn số tài liệu chạy đồng thời theo CPU và RAM trống, tính lại trước batch mới nếu không còn tác vụ đang chạy:

- Dự trù 768 MB cho mỗi worker, giữ lại 1 GB RAM và một CPU logic nếu có thể.
- Tối thiểu 1, tối đa 8 tài liệu cùng lúc. Tesseract dùng 1 luồng/tài liệu để tránh nhân số luồng quá mức.
- Mỗi tài liệu là tiến trình riêng; chỉ render một trang tại một thời điểm, thường 300 DPI. Trang quá lớn được hạ DPI để không vượt 40 triệu pixel.
- Tài liệu có sẵn lớp chữ đủ dài dùng lại chữ; trang scan hoặc chỉ có ít chữ được OCR.
- Không giữ ảnh raster của cả tài liệu trong RAM. Upload và tải kết quả trên giao diện vẫn có thể dùng RAM theo kích thước file.

Đây là mức song song khởi đầu theo tài nguyên, không phải cam kết tối ưu tuyệt đối trên mọi máy. Tốc độ thực tế phụ thuộc CPU, độ phân giải, số chữ mỗi trang, ổ đĩa và chất lượng scan; không suy ra thời gian giáo trình thật từ fixture kiểm thử ngắn.

## Chất lượng và giới hạn

Chạy được chữ Nhật và tiếng Việt trên cùng trang nhưng không bảo đảm mọi ký tự đúng. Furigana, chữ dọc, nghiêng, mờ, bảng và nhiều cột cần kiểm tra/sửa. Chưa tự tách bảng thành Markdown table, chưa tái dựng nguyên bố cục và chưa xoay/nghiêng ảnh tự động. Không dùng AI để tự sửa đáp án hoặc nội dung giáo trình. PDF có mật khẩu cần bản được mở khóa hợp lệ trước khi nhập.

## Kiểm tra

```bat
.venv-ocr\Scripts\python.exe -m unittest scan_tool.test_scan -v
```

Các kiểm thử có sử dụng OCR yêu cầu Tesseract và ba bộ ngôn ngữ; runner báo skipped khi thiếu, không tính là đã kiểm chứng OCR. Có kiểm thử fixture 100 trang có lớp chữ, cache tiếp tục, tài liệu lỗi không làm hỏng tài liệu khác và giới hạn song song khi ít RAM. Việc chạy trực tiếp trên Windows vẫn cần xác nhận trên máy đích.

Kiểm thử thủ công trên Linux đã chạy hai PDF scan tổng hợp Nhật–Việt, mỗi file 100 trang trong cùng batch; xác nhận Markdown của cả hai đủ 100 tiêu đề trang và có chữ Nhật/Việt. Tùy chọn PDF tìm kiếm được đã được sửa lỗi font và kiểm tra lại đủ 100 trang với lớp chữ. Đã kiểm tra thêm/xóa link, nút tải kết quả, xem trước Markdown bằng Streamlit AppTest và phản hồi health của server. Đây là fixture chữ rõ, bố cục đơn giản; không đại diện độ chính xác hay tốc độ trên giáo trình thực tế.
