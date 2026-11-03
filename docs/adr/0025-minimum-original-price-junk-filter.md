# 25. Lọc Bỏ Sản Phẩm Rác Giá Trị Thấp và Thiết Lập Ngưỡng Giá Gốc Tối Thiểu (Minimum Pre-Discount Baseline Threshold & Low-Value Junk Filter)

Ngày: 2026-10-23

## Bối cảnh
Khi quét tự động các chương trình Flash Sale, Siêu Sale và Deal Trợ Giá trên các sàn (Shopee, Lazada), hệ thống thu thập rất nhiều sản phẩm giá rẻ/linh tinh (như ốp lưng 15k, tất chân 20k, phụ kiện 50k). Mặc dù các sản phẩm này hiển thị mức giảm giá sâu (ví dụ giảm 50% - 80%), chúng không mang lại giá trị thiết thực và gây rác cơ sở dữ liệu cũng như spam thông báo trên kênh Telegram.

Người dùng yêu cầu loại bỏ các sản phẩm có "giá trị thật trước khi giảm giá nhỏ hơn 500k" để chỉ tập trung vào các mặt hàng có giá trị cao (như thiết bị công nghệ, đồ gia dụng, linh kiện máy tính, hàng thương hiệu).

## Quyết định kiến trúc

1. **Định nghĩa Giá trị thật trước giảm giá (Pre-Discount Baseline Value):**
   - Đối với sản phẩm đã có lịch sử theo dõi: Giá trị thật là giá trung vị 30 ngày (`median_30d`).
   - Đối với sản phẩm mới phát hiện (Flash Sale, Siêu sale, Cold-start): Giá trị thật là giá niêm yết ban đầu (`list_price` hoặc `price`).
   - Nếu giá trị này `< 500.000₫` (hoặc nhỏ hơn ngưỡng cấu hình), sản phẩm được phân loại là sản phẩm rác giá trị thấp.

2. **Lọc đa tầng từ thu thập đến cảnh báo:**
   - **Tầng thu thập Flash Sale ([Scanner.discover_flash_sale](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
     - Bỏ qua ngay lập tức các mặt hàng có `list_price < deal_min_original_price`, không nạp vào bảng `products` hay `price_history` của cơ sở dữ liệu, giúp DB luôn tinh gọn.
   - **Tầng thông báo kênh Telegram ([Scanner._process_snapshot](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
     - Chặn phát sóng thông báo `_send_deal_alert` (Deal thật) và `_send_flash_deal_alert` (Flash Deal tức thời) nếu giá trị trước giảm `< deal_min_original_price`.
   - **Bảo toàn sản phẩm người dùng tự theo dõi (`source == 'user'`):**
     - Nếu người dùng chủ động dán link qua Dashboard hoặc Telegram bot, hệ thống vẫn lưu trữ và cảnh báo giảm giá cá nhân (`_send_price_drop_alert` / `_send_target_alert`) bất kể mức giá.

3. **Cấu hình linh hoạt và giao diện Web Dashboard:**
   - Thêm trường `deal_min_original_price: float = 500000.0` trong [Config](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/config.py) (nhận qua biến môi trường `DEAL_MIN_ORIGINAL_PRICE`).
   - Cập nhật API [/api/settings](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py) và giao diện cài đặt [templates/dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html) cho phép người dùng tùy chỉnh ngưỡng giá sàn này trực tiếp trên trình duyệt.

## Trạng thái
- 114/114 automated unit tests pass.
- Bổ sung 3 test case kiểm thử bộ lọc rác < 500k và API cài đặt ngưỡng giá gốc.
