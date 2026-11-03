# 31. Tối ưu luồng cào dữ liệu Sản phẩm theo dõi và quản lý lỗi quét liên tiếp

## Trạng thái

Accepted. Tự ngưng sau 5 lỗi chỉ còn áp cho sản phẩm khám phá; sản phẩm theo dõi được giữ và báo admin (ADR 0052).

## Bối cảnh
Sau khi phân tách tab "Sản phẩm theo dõi" và áp dụng lịch quét độc lập ở ADR 0030:
1. **Phạm vi nút Quét thủ công chưa nhất quán**: Nút `⚡ Quét ngay` trong tab Sản phẩm theo dõi trên Dashboard gọi endpoint `/api/scan`. Endpoint này trước đây gọi `scanner.scan_all()`, quét toàn bộ sản phẩm active thuộc mọi nguồn (`user`, `keyword`, `flash_sale`, `price_error`), phá vỡ tính cô lập khi quét thủ công.
2. **Xung đột logic hẹn giờ quét từ khóa**: Trong `scanner.scan_all()` vẫn tồn tại đoạn mã cũ kiểm tra và kích hoạt `run_keyword_search()` theo `_last_keyword_scan_time`, gây reset sai lệch chu kỳ của bộ điều phối `scan_due()`.
3. **Thiếu cơ chế phát hiện và xử lý sản phẩm lỗi kéo dài**: Một số sản phẩm người dùng theo dõi có thể bị xóa, đổi cấu trúc URL, shop bị khóa hoặc lỗi mạng liên tục. Trước đây, hệ thống chỉ ghi nhận `fail` tạm thời trong chu kỳ quét mà không theo dõi số lần thất bại liên tiếp, dẫn đến việc trình duyệt vẫn liên tục truy cập các link hỏng trong mọi chu kỳ sau, gây lãng phí tài nguyên CPU/RAM và tăng nguy cơ bị sàn chặn.

## Quyết định kiến trúc

1. **Chuẩn hóa API Quét thủ công ([web.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py), [dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Chuyển đổi endpoint `/api/scan` từ `scanner.scan_all()` sang `scanner.scan_tracked_products()`.
   - Nút `⚡ Quét ngay` trên tab Sản phẩm theo dõi giờ đây chỉ quét đúng các sản phẩm `source='user'`, phản hồi thông báo `"Đã bắt đầu quét sản phẩm theo dõi"`.

2. **Dọn dẹp bộ điều phối quét ([scanner.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
   - Loại bỏ đoạn mã kích hoạt quét từ khóa con bên trong `scan_all()`. Toàn bộ việc kích hoạt quét định kỳ theo phân hệ được giao trọn vẹn cho `scan_due()`.
   - Bỏ kiểm tra phiên đăng nhập chung (`ensure_authenticated()`) ở đầu `scan_tracked_products()`, ủy thác hoàn toàn việc kiểm tra phiên sàn cụ thể cho từng nhóm nền tảng bên trong `_scan_platform(platform, group)`. Tránh tình trạng cảnh báo sai khi người dùng chỉ theo dõi link của một sàn hoạt động bình thường nhưng sàn kia chưa đăng nhập.
   - Giữ nguyên cơ chế khóa quét chia sẻ `_scan_lock` nhằm đảm bảo bối cảnh Chromium đơn luồng của Playwright không bị quá tải bởi các yêu cầu quét đồng thời.

3. **Theo dõi lỗi quét liên tiếp và tự động ngưng theo dõi ([db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py), [scanner.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
   - Thêm cột `fail_count INTEGER NOT NULL DEFAULT 0` vào bảng `products` kèm tự động migration.
   - Khi quét thất bại do `FetchError` (lỗi tải trang, timeout, lỗi phân tích cú pháp):
     - Tăng `fail_count` của sản phẩm lên 1 đơn vị (`increment_product_fail_count`).
     - Khi `fail_count >= 5`: tự động chuyển `active = 0` (ngưng quét), ghi log cảnh báo và gửi tin nhắn cảnh báo đến quản trị viên qua Telegram để thông báo link cần kiểm tra hoặc thay thế.
   - Khi quét thành công một snapshot hoặc người dùng thêm lại/cập nhật link (`update_product_from_snapshot`, `add_product_url`): tự động đặt lại `fail_count = 0` và kích hoạt lại `active = 1`.
   - Lỗi chặn do Captcha sàn (`Blocked`) không làm tăng `fail_count` của từng sản phẩm vì đây là lỗi phiên sàn diện rộng, không phải lỗi của bản thân sản phẩm.

## Hệ quả
- Thao tác quét thủ công từ tab Sản phẩm theo dõi diễn ra nhanh chóng, đúng trọng tâm và cô lập hoàn toàn.
- Hệ thống tự động thanh lọc các link sản phẩm hỏng/chết sau 5 lần thử, tiết kiệm tài nguyên trình duyệt và hạn ngạch quota.
- Quản trị viên nhận thông báo rõ ràng khi có link sản phẩm bị gián đoạn kéo dài để chủ động cập nhật.
