# Kiểm tra phiên bản 2 trên mẫu scan Nhật–Việt

Chạy trên cùng môi trường Linux/CPU, Tesseract 5.5.0, một worker OCR dùng một luồng, không dùng GPU/API AI. Mẫu là PDF 5 trang do người dùng cung cấp, ảnh scan khoảng 150 DPI. Không đưa tài liệu hoặc nội dung người dùng vào repository.

| Chế độ | Thời gian cả lượt | Đầu ra được bật |
|---|---:|---|
| Cũ: Tesseract 300 DPI | 32,10 giây | Markdown, TXT, JSON |
| Nhanh: Tesseract 200 DPI | 22,19 giây | Markdown, TXT, JSON |
| Cân bằng v2: theo vùng, 220 DPI | khoảng 57,34 giây | Markdown, TXT, JSON và PDF tìm kiếm được |

Chế độ Nhanh giảm khoảng 31% thời gian trên mẫu này, nhưng một số câu Nhật sai nhiều hơn. Chế độ Cân bằng tốn thêm thời gian; đầu ra PDF được bật ở lượt này nên không dùng tỷ số thời gian để kết luận chi phí riêng của OCR.

Trên một nhóm 10 câu Nhật đối chiếu thủ công ở trang đầu, kiểm tra khớp nguyên câu sau khi bỏ khoảng trắng cho kết quả: bản cũ 7/10, bản Nhanh 6/10, bản Cân bằng 10/10. Đây là nhóm câu nhỏ, không phải CER/WER hay mức chính xác đại diện của toàn tài liệu. Các đoạn tiếng Việt vẫn có lỗi dấu/từ; furigana và thứ tự giữa nhiều cột vẫn cần xem lại.

Đã kiểm tra cả 5 trang của lớp chữ PDF bằng cách trích ngược và tìm từng vùng OCR trong văn bản, sau khi bỏ khoảng trắng. Điều này kiểm chứng việc ghi/đọc lớp chữ PDF, không chứng minh nội dung OCR đúng với ảnh gốc.

Đã kiểm tra giao diện chọn chế độ, thêm/xóa input, xem Markdown không biến mất sau cập nhật, đối chiếu ảnh–chữ và chỉnh sửa văn bản một trang. Chưa kiểm thử trực tiếp trên Windows, chưa chạy toàn bộ 234 trang bằng cấu hình mới, chưa có bản chép tay đầy đủ để tính độ chính xác toàn tài liệu. Không dùng kết quả fixture để hứa thời gian trên máy người dùng.
