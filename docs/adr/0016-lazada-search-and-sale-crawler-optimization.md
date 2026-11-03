# 16. Tối ưu hóa Crawler Tìm kiếm và Săn Sale Lazada (Lazada Search & Flash Sale Optimization)

Ngày: 2026-10-21

## Bối cảnh
Sau khi tính năng tìm kiếm từ khóa liên sàn và cào Flash Sale của Lazada được tích hợp, quá trình kiểm thử thực tế và rà soát bóc tách DOM phát hiện một số hạn chế:
1. **Thời gian tải trang danh mục & sale còn chậm (~9 - 10 giây):**
   Mặc dù trang chi tiết sản phẩm (PDP) đã được trang bị cơ chế hủy tải tài nguyên nặng, các luồng tìm kiếm danh mục (`https://www.lazada.vn/catalog/?q=...`) và trang Flash Sale (`https://www.lazada.vn/flash-sale/`) vẫn tải toàn bộ hình ảnh độ phân giải cao, font chữ, video ngắn và các script telemetry/tracking (`alilog`, `aplus`, `itrace`, `woodpecker`, `arms-retcode`).
2. **Lỗi phân tích giá sai do nhầm số lượng/trọng lượng trong tên sản phẩm:**
   Regex bóc tách giá trên các thẻ DOM trước đây coi ký hiệu tiền tệ `₫` / `đ` là tùy chọn (`(?:₫|đ)?`), dẫn đến việc các con số chỉ quy cách đóng gói hoặc trọng lượng trong tiêu đề (ví dụ: `1400g` trong hộp sữa 1400g, `48 hộp`, `180ml`) bị nhận dạng nhầm thành giá bán của sản phẩm (`1.400₫` thay vì giá thật `503.442₫`).
3. **Thiếu thông tin giá niêm yết, % giảm giá và độ uy tín:**
   Nhiều deal Flash Sale chỉ hiển thị giá bán và nhãn phần trăm giảm (ví dụ: `-51%`, `-17%`) hoặc số lượt đánh giá/lượt mua dạng `(1665)`, `(2160)`, nhưng crawler chưa tính toán ngược lại giá niêm yết gốc (`list_price`) và chưa ghi nhận số lượt mua/đánh giá (`sold`, `rating`).

## Quyết định kiến trúc

1. **Chuẩn hóa cơ chế chặn tài nguyên nặng dùng chung (`_enable_resource_blocking`):**
   - Đóng gói logic can thiệp mạng `page.route` thành phương thức tĩnh `_enable_resource_blocking(page)` trong `PlaywrightAdapter`.
   - Áp dụng đồng bộ cho cả 3 luồng cào Lazada:
     1. Tải trang chi tiết sản phẩm (`fetch`).
     2. Tìm kiếm danh mục trực tiếp theo từ khóa (`_search_sync`).
     3. Cào deal Siêu Sale / Flash Sale (`_crawl_lazada_flash_sale_sync`).
   - Thời gian tải trang giảm từ ~9.6s xuống còn ~1.5 - 2s, tiết kiệm đáng kể RAM của container Docker.

2. **Thuật toán bóc tách giá tiền thẻ DOM chống nhầm lẫn (Anti-Title Price Collision):**
   - Tách biệt hoàn toàn tiêu đề sản phẩm (`title`) khỏi nội dung thẻ trước khi phân tích số tiền (`non_title_text = text.replace(title, "")`).
   - Bắt buộc số tiền phải đi liền với ký hiệu tiền tệ chuẩn: `(?:₫|đ)\s*([0-9.,]+)|([0-9.,]+)\s*(?:\|\s*)?(?:₫|đ)`. Các số liệu gram, ml, số lượng trong tên sản phẩm hoàn toàn không bị bắt nhầm.
   - Bổ sung bộ lọc sàn giá tối thiểu: Bỏ qua các bản ghi có giá `< 1.000₫` để loại trừ quà tặng kèm hoặc mã lỗi.

3. **Bóc tách % giảm giá, tái tạo giá niêm yết và số lượt mua/đánh giá:**
   - Trích xuất nhãn giảm giá dạng `[-–—]?\s*([1-9][0-9]?)\s*%` (ví dụ: `-51%`, `25% Off`). Nếu sàn ẩn giá gốc, tự động suy ra giá niêm yết: `list_price = round(price / (1.0 - (pct / 100.0)), -3)`.
   - Trích xuất số lượt đánh giá / lượt mua từ các thẻ có mẫu `\(([0-9]+)\)` hoặc `(?:đã bán|sold)\s*([0-9.,kK]+)` để điền vào trường `sold` và thiết lập điểm uy tín `rating = 4.8` cho các deal có lượng mua lớn.

## Trạng thái
Đã hoàn thành kiểm thử đơn vị (93/93 tests pass) và kiểm thử thực tế thành công trên môi trường Docker.
Từ ADR 0055 và 0057 (01/11/2026): cào Siêu Sale chỉ chạy khi người dùng bấm nút và không phát cảnh báo Telegram; quét nền theo từ khóa đang tắt.
