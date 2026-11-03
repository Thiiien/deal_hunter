# 56. Phát cảnh báo giá mong muốn tức thời ở mỗi chu kỳ quét

Date: 2026-11-01

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`)

## Bối cảnh

1. **Giới hạn tần suất của Alerter ảnh hưởng đến việc săn deal tức thời:**
   - Trước đây, khi sản phẩm đạt mức giá mong muốn (`effective_price <= target_price`), hệ thống kiểm tra qua `self._alerter.should_alert(product_id, effective_price)`.
   - Cơ chế của `Alerter` áp dụng quy tắc chống spam thông thường: chỉ gửi lại sau 24 giờ kể từ thông báo gần nhất, hoặc khi giá tiếp tục giảm sâu thêm ít nhất 5%.
   - Hệ quả là khi một sản phẩm theo dõi (ví dụ: bàn phím cơ AULA F108PRO - ID 4174) giảm xuống `823.500₫` (thấp hơn giá mong muốn `900.000₫`), cảnh báo chỉ được gửi 1 lần duy nhất lúc 17:01. Các chu kỳ quét tiếp theo (mỗi 8 phút) dù sản phẩm vẫn duy trì mức giá mục tiêu nhưng đều bị `Alerter` chặn lại, khiến người dùng lầm tưởng hệ thống không còn hoạt động hoặc không gửi thông báo.
2. **Kỳ vọng của người dùng:**
   - Với các sản phẩm do người dùng chủ động đặt giá mong muốn ("📦 Sản phẩm theo dõi"), mục tiêu cao nhất là săn deal kịp thời. Người dùng yêu cầu mỗi lần chu kỳ quét phát hiện giá đang nằm trong ngưỡng mong muốn thì phải gửi cảnh báo Telegram ngay lập tức.
   - Nơi nhận thông báo tiếp tục duy trì phát vào Group Telegram "Deal Hunter" (`TELEGRAM_CHANNEL_ID`).

## Quyết định kiến trúc

1. **Bỏ qua cơ chế cooldown của `Alerter` đối với Cảnh báo Giá mong muốn (`_send_target_alert`):**
   - Trong `src/deal_hunter/scanner.py` tại phương thức `scan_product()`: loại bỏ điều kiện kiểm tra `if self._alerter.should_alert(product_id, effective_price):` đối với nhánh `target_price`.
   - Bất cứ khi nào `effective_price <= target_price` và sản phẩm còn hàng (`snapshot.stock is not False`), hệ thống lập tức gọi `self._send_target_alert()` để gửi tin nhắn đến Telegram Group.
   - Vẫn gọi `self._alerter.record(product_id, effective_price)` và gán `alerted = True` để ngăn chặn các cảnh báo deal ảo hoặc cảnh báo giảm giá thông thường trùng lặp cho cùng sản phẩm trong chu kỳ đó.

2. **Duy trì kênh phát sóng Group Telegram:**
   - Thông báo tiếp tục được gửi tập trung vào Group Telegram "Deal Hunter" (`TELEGRAM_CHANNEL_ID`) thông qua `self._notifier.broadcast_deal()`.

3. **Cập nhật Docker container:**
   - Tiến hành build lại Docker image và tái khởi động container `deal_hunter-deal-hunter-1` để nạp toàn bộ mã nguồn mới nhất.

## Hệ quả

- Người dùng luôn nhận được thông báo ở mỗi chu kỳ quét khi sản phẩm đang có giá hời dưới mức mong muốn.
- Tần suất quét mặc định của danh mục sản phẩm theo dõi là 8 phút, với tối đa 26 sản phẩm cách nhau 8 giây (tối đa ~7.5 tin nhắn/phút), hoàn toàn an toàn và nằm dưới hạn mức rate limit 20 tin nhắn/phút của Telegram.
- Toàn bộ 186/186 kiểm thử tự động đều vượt qua.
