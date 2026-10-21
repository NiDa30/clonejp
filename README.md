# Sao lưu JapanesePod101 trên Windows 11

Công cụ chạy trên máy bạn, mở Microsoft Edge để bạn đăng nhập trực tiếp. Chế độ `auto` tự lần theo liên kết học tập tìm được, cuộn trang, lưu chữ/bảng và tải tài liệu có liên kết tải xuống. Có thể tiếp tục hàng đợi khi chạy lại. Chỉ tải nội dung được tài khoản cho phép tải.

**Chưa thể bảo đảm sao lưu toàn bộ tài khoản.** Giao diện sau đăng nhập chưa được kiểm chứng. Công cụ không gọi API nội bộ, không lấy media từ luồng phát và không vượt DRM. Phân trang có liên kết HTML được lần theo; nút JavaScript, dữ liệu ẩn hoặc chức năng xuất riêng cần điều chỉnh sau khi kiểm tra cấu trúc trang. Nội dung chữ và bảng là bản chụp để đọc, không phải bản xuất có thể nhập lại tiến độ hoặc flashcard.

## Chạy trên Windows 11

1. Cài Python 3.11 trở lên từ https://www.python.org/downloads/windows/.
2. Tải repository thành ZIP và giải nén vào một thư mục riêng.
3. Đảm bảo Microsoft Edge đã được cài trên Windows, rồi nhấp đúp `start-windows.bat`. Lần đầu cần Internet để cài thư viện Playwright; không tải Chromium. Nếu Edge chưa có, cài từ https://www.microsoft.com/edge rồi chạy lại.
4. Đăng nhập JapanesePod101 trong cửa sổ Microsoft Edge vừa mở. Công cụ dùng hồ sơ Edge riêng trong `.jp101-local/edge-profile`, không dùng phiên đăng nhập Edge cá nhân sẵn có hoặc hồ sơ Chromium của bản cũ. Mật khẩu không nhập vào terminal.
5. Đợi đăng nhập xong. Có thể mở thêm tab từ vựng, flashcard, tiến độ trong cùng trình duyệt để làm điểm bắt đầu.
6. Quay lại terminal, nhập `auto`. Công cụ tự duyệt các đường dẫn học tập nhận diện được và tải file khi quét xong. Không cần mở từng bài.
7. Xem `coverage.json`: số trang đã lưu, số liên kết còn chờ, nguyên nhân dừng và giới hạn. Hết hàng đợi chỉ có nghĩa đã duyệt các liên kết nhận diện được, không chứng minh đã sao lưu cả tài khoản.
8. Chạy lại `auto` để tiếp tục nếu dừng. Nhập `quit` để đóng. `scan` vẫn dùng được để bổ sung trang thủ công, `download` để thử lại file lỗi.

Mỗi lượt tối đa 5.000 trang, mỗi trang tối đa 20 lượt kiểm tra/cuộn, chờ ít nhất 2 giây giữa các trang và giữa các lượt tải. Các trang chạm giới hạn cuộn được ghi trong `crawl.json`. Công cụ chỉ mở liên kết thuộc nhóm đường dẫn học tập đã nhận diện, không tự bấm nút xóa, mua hay đánh dấu hoàn thành. Bản thân website vẫn có thể ghi nhận việc truy cập bài học. Lỗi đăng nhập/403/429 sẽ dừng, không tự vượt hạn chế.

Mỗi lượt `auto` đọc lại dashboard, Lesson Library và các trang học đang mở để tìm liên kết mới sau khi đăng nhập; các bài khác đã xử lý vẫn được giữ trong trạng thái tiếp tục. Không cần xóa `crawl.json`. Báo cáo bổ sung số trang bài học, liên kết tải, file đã tải và lỗi tải. Nếu số trang bài học bằng 0, chưa có cơ sở nói đã sao lưu bài học: mở Lesson Library trong Edge do công cụ mở, đợi danh sách xuất hiện rồi chạy `auto` lại và gửi `coverage.json` mới nếu vẫn chưa tìm thấy bài.

## Nếu không đăng nhập được

Edge tự mở là hoạt động bình thường. Đây là hồ sơ riêng, không có sẵn tài khoản/cookie từ Edge thường; hãy đăng nhập trong cửa sổ do công cụ mở và chỉ nhập `auto` sau khi vào dashboard thành công. Trong lúc chờ lệnh, công cụ vẫn xử lý sự kiện trình duyệt để hỗ trợ cửa sổ và sự kiện đăng nhập.

Nếu thất bại, thử đăng nhập bằng Edge bình thường để so sánh. Ghi lại thông báo chính xác và cách đăng nhập (email/mật khẩu hay qua nhà cung cấp khác); không gửi mật khẩu/cookie. Nếu trang báo CAPTCHA hoặc từ chối trình duyệt tự động, xử lý qua luồng chính thức của website hoặc hỗ trợ JapanesePod101; công cụ không vượt cơ chế này. Việc sửa xử lý sự kiện chưa chứng minh sẽ giải quyết lỗi đăng nhập cụ thể của bạn.

Nếu bản cũ báo `Page.title: Execution context was destroyed`, đó là lỗi đọc tab trong lúc chuyển trang. Cập nhật bằng `git pull --ff-only` trong thư mục repository (hoặc tải ZIP code mới), rồi chạy lại `start-windows.bat`. Bản sửa hiển thị `Phien ban: Edge / navigation-retry-v1`; menu tab dùng đường dẫn thay vì đọc tiêu đề. Lệnh `structure`/`scan` chờ trang sẵn sàng, thử lại tối đa 3 lần nếu ngữ cảnh bị hủy và giữ cửa sổ mở khi chưa đọc được. Đợi đăng nhập/chuyển trang xong rồi thử lại lệnh nếu cần. Thông báo đề nghị cập nhật pip không phải lỗi này.

## Lấy cấu trúc trang để hoàn thiện chế độ tự động

1. Dùng bản công cụ mới này và đăng nhập trong Microsoft Edge do công cụ mở.
2. Mở dashboard. Trong terminal nhập `structure`, rồi chọn số tab tương ứng.
3. Làm tương tự với danh sách bài học, một bài học có phần Download đang mở, trang flashcard/từ vựng và trang tiến độ. Nếu có phân trang hoặc Load More, để nút đó xuất hiện.
4. Các tệp nằm trong `.jp101-local/structures/structure-....json`.
5. Mở và kiểm tra các tệp JSON rồi gửi **chỉ các tệp structure** vào cuộc trò chuyện để điều chỉnh công cụ.

Lệnh `structure` không xuất nội dung chữ của tài khoản, mật khẩu, cookie, giá trị ô nhập, URL đầy đủ hay giá trị tham số. Nó giữ số lượng phần tử, bộ chọn DOM, nhóm nhãn nút thông dụng và mẫu đường dẫn đã che các đoạn không nhận diện. Không gửi `manifest.json`, `pages/`, `crawl.json`, `browser-profile/` hay cả thư mục `.jp101-local`.

Nếu website có nút Export/Download tạo file bằng JavaScript, hãy dùng nút chính thức và chọn lưu file trên máy. Công cụ chỉ tự nhận liên kết HTML dẫn đến file media/tài liệu hoặc mang nhãn Download; nó không tự bấm mọi nút hay xuất toàn bộ tài khoản.

## Dữ liệu

Tất cả nằm trong `.jp101-local` cạnh script:

- `pages/`: nội dung chữ, bảng và liên kết của từng trang đã quét.
- `lessons/<khóa>/<tên-bài--mã>/`: nội dung từng bài (`content.txt`, `page.json`) và tài liệu trong `files/`. Khóa được lấy từ liên kết breadcrumb tới `/lesson-library/...`; nếu trang không cung cấp thông tin này, bài nằm trong `Chua-xac-dinh-khoa`. Chưa tự phân cấp trình độ hoặc suy đoán thứ tự bài.
- `downloads/`: các file đã tải thành công.
- `manifest.json`: danh sách trang, trạng thái tải và đường dẫn file. Chạy lại sẽ bỏ qua file đã tải còn tồn tại.
- `crawl.json`: hàng đợi và trạng thái duyệt để tiếp tục.
- `coverage.json`: báo cáo phạm vi đã quét, không phải chứng nhận sao lưu đầy đủ.
- `structures/`: cấu trúc đã lược bỏ dữ liệu tài khoản, dành cho chẩn đoán.
- `edge-profile/`: phiên đăng nhập Edge riêng của công cụ. `browser-profile/` nếu có là phiên Chromium của bản cũ.

Không chia sẻ `.jp101-local`: thư mục chứa phiên đăng nhập, dữ liệu cá nhân và có thể có liên kết tạm thời cấp quyền tải. Thư mục này đã được loại khỏi Git. Sau khi dùng xong, đóng công cụ rồi xóa `edge-profile` (và `browser-profile` nếu còn từ bản cũ) nếu không muốn giữ phiên đăng nhập.

Các bài đã lưu bằng bản cũ được lập thư mục mới khi khởi động, không xóa bản gốc. Chạy `download` hoặc `auto` để đặt thêm file đã tải vào từng thư mục bài; file dùng chung có mặt ở mỗi bài liên quan (ưu tiên hard link trên cùng ổ đĩa, nếu không hỗ trợ thì sao chép). Các bản chụp cũ không có breadcrumb sẽ được xếp vào khóa chưa xác định; dùng `scan` trên bài đang mở để lấy lại thông tin mới.

Tệp lớn được tải lần lượt vào bộ nhớ trước khi ghi xuống đĩa. Lỗi 401, 403 hoặc 429 sẽ dừng lượt tải để bạn kiểm tra đăng nhập/quyền tải hoặc chờ; không tự vượt giới hạn. Liên kết hết hạn cần quét lại trang. Không bảo đảm mọi file audio/video đều có liên kết tải trực tiếp.

## Kiểm tra đã thực hiện

Đã kiểm tra logic chọn URL, loại đường dẫn thao tác, tên file Windows, bỏ qua file đã tải, tự phát hiện trang và tiếp tục hàng đợi bằng kiểm thử độc lập. Chưa kiểm thử trực tiếp trên Windows hoặc tài khoản JapanesePod101: kết nối từ môi trường phát triển tới website bị proxy từ chối HTTP 403. Vì vậy chưa thể xác nhận việc sao lưu đầy đủ, khả năng đăng nhập hoặc cấu trúc trang hiện tại.

Đã đối chiếu các tệp cấu trúc do người dùng cung cấp: một trang có liên kết thư viện bài học và một trang có 4 thẻ liên kết được phân loại Download. Tệp đã che URL nên chưa xác nhận đích tải, loại file, phản hồi máy chủ hoặc sự hiện diện của breadcrumb. Kiểm thử bổ sung xác minh phân thư mục, tài liệu dùng chung và lập lại chỉ mục các bản lưu cũ.
