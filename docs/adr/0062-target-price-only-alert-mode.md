# ADR 0062: Chế độ chỉ nhận thông báo đạt giá mong muốn (Target-Price-Only Alert Mode)

## Trạng thái
Đã chấp thuận (Accepted)
Từ 03/11/2026 mặc định trong mã là bật (True).

## Bối cảnh
1. Người dùng đang theo dõi nhiều sản phẩm trên các sàn thương mại điện tử (Shopee, Lazada). Hiện tại hệ thống phát nhiều loại thông báo qua kênh Telegram:
   - Thông báo đạt giá mong muốn (`target_price`)
   - Thông báo giảm giá định kỳ / có voucher mới (`price_drop`)
   - Thông báo deal thật giảm sâu theo thuật toán median 30 ngày (`REAL_DEAL`)
   - Thông báo bất thường nghi lỗi giá (`price_error`)
2. Khi số lượng sản phẩm theo dõi tăng lên hoặc trong các đợt biến động giá nhỏ (vài nghìn đồng), số lượng thông báo giảm giá thường và deal thật xuất hiện nhiều, gây nhiễu kênh Telegram và làm người dùng khó tập trung vào những deal mục tiêu quan trọng nhất.
3. Người dùng yêu cầu tạm thời chỉ nhận thông báo đối với những sản phẩm đạt hoặc thấp hơn mức giá mong muốn (`target_price`) đã đặt trong tab *Sản phẩm theo dõi*, đồng thời có thể chủ động bật/tắt chế độ này trên giao diện Cài đặt (Settings).

## Quyết định
1. **Thiết lập chế độ lọc thông báo giá (`only_target_price_alerts`)**:
   - Thêm cờ cấu hình `only_target_price_alerts: bool = False` (mặc định môi trường production/docker là `True` qua `ONLY_TARGET_PRICE_ALERTS=1` và bảng `settings` trong SQLite).
   - Trong `Scanner.scan_product()`:
     - Khi `only_target_price_alerts == True`: chỉ thực hiện gửi thông báo khi sản phẩm đạt giá mong muốn (`effective_price <= target_price` và còn hàng `stock is not False`).
     - Tạm tắt (bỏ qua) việc gửi các thông báo: `_handle_price_error`, `_send_deal_alert`, và `_send_price_drop_alert`.
     - Các cảnh báo kỹ thuật quan trọng của hệ thống (hết hạn cookie, gặp captcha challenge, sản phẩm bị xóa/ngừng kinh doanh) **không bị ảnh hưởng** và vẫn gửi tới admin như bình thường.
2. **Tích hợp cài đặt trên giao diện Web Dashboard**:
   - Mở rộng API `GET /api/settings` và `POST /api/settings` để đọc và ghi trường `only_target_price_alerts`.
   - Bổ sung tùy chọn bật/tắt (checkbox toggle) trong modal Cài đặt của `dashboard.html` tại mục "🔔 Thông báo Telegram", cho phép người dùng kích hoạt hoặc vô hiệu hóa bất kỳ lúc nào mà không cần khởi động lại container.

## Hệ quả
- **Tích cực**:
  - Kênh Telegram trở nên tinh gọn, chỉ đổ chuông khi sản phẩm đúng tầm giá mong muốn của người dùng.
  - Loại bỏ hoàn toàn nhiễu từ các cảnh báo giảm giá nhẹ hoặc deal thật không mong muốn.
  - Linh hoạt: có thể tắt/bật lại chỉ với 1 click trong Cài đặt.
- **Tiêu cực**:
  - Người dùng sẽ không nhận được cảnh báo lỗi giá bất thường (nếu sản phẩm đó chưa được đặt giá mục tiêu thấp tương ứng) khi đang bật chế độ này.
