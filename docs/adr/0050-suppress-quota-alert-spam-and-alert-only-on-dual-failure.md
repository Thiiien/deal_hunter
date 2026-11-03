# 50. Suppress Quota Alert Spam & Alert Only on Dual Failure

Date: 2026-10-30

## Status

Accepted

## Context

Trong quá trình vận hành, hệ thống gặp phải các vấn đề liên quan đến cơ chế thông báo hạn ngạch giải Captcha (NopeCHA):
1. **Spam cảnh báo khi cào thành công**: Khi số lượt giải captcha trong ngày đạt mốc 10 lượt, mỗi lần giải thành công một sản phẩm tiếp theo, hàm `QuotaMonitor.record_solve()` lại gọi `mark_exhausted()`, khiến Telegram bot gửi tin nhắn `🚨 NopeCHA đã hết 10 lượt miễn phí hôm nay!...` liên tục trên từng sản phẩm, ngay cả khi sản phẩm đó cào thành công rực rỡ (`23 ok, 0 fail`).
2. **Chặn quét nhầm (False Block on Scan Cycle)**: Khi `quota.is_exhausted == True`, các hàm `scan_all()` và `scan_tracked_products()` trong `Scanner` tự động dừng chu kỳ cào (`return {"msg": "quota_exhausted"}`). Điều này vô hiệu hóa toàn bộ crawler dù cookies phiên đăng nhập vẫn hoàn toàn hợp lệ và có thể cào bình thường.
3. **Yêu cầu cốt lõi từ người dùng**: Hệ thống chỉ được phép gửi cảnh báo khi và chỉ khi **cả Cookie phiên đăng nhập lẫn bộ giải Captcha đều thất bại** (không thể cào được dữ liệu), nhằm nhắc nhở người dùng cập nhật cookie mới hoặc bổ sung NopeCHA API Key.

## Decisions

1. **Triệt tiêu hoàn toàn cảnh báo tự động trong `QuotaMonitor`**:
   - `QuotaMonitor` đóng vai trò là một service thuần túy theo dõi số liệu: đếm số lượt giải trong ngày và lưu vào database để phục vụ lệnh tra cứu `/quota` trên Telegram bot.
   - Loại bỏ toàn bộ các lời gọi `self._notifier.alert_admin()` bên trong các hàm `record_solve()`, `check()`, và `mark_exhausted()`.

2. **Loại bỏ chặn chu kỳ quét khi hết hạn ngạch Captcha (`Scanner`)**:
   - Gỡ bỏ điều kiện `if self._quota.is_exhausted: return ...` ở đầu `scan_all()` và `scan_tracked_products()`.
   - Crawler luôn tiến hành cào dữ liệu bình thường bằng Cookie. Miễn là Cookie còn hiệu lực hoặc thử thách có thể vượt qua (bằng Cookie-first hoặc Slider Drag), chu kỳ quét vẫn hoàn thành đầy đủ.

3. **Cơ chế cảnh báo duy nhất khi cả Cookie và Captcha cùng bất lực (`Dual Failure Alert`)**:
   - Trong `Scanner._scan_platform`: Chỉ khi crawler ném ngoại lệ `Blocked` thực sự (đã thử đọc DOM bằng Cookie, đã thử giải bằng Slider Drag và NopeCHA 15s, đã tự động nạp lại Cookie mà vẫn bị sàn chặn cứng):
     - **Nếu Cookie đã hết hạn**: Gửi thông báo `🚨 Cào sàn {plat_name} thất bại! Cả Cookie phiên đăng nhập lẫn Captcha đều không thể sử dụng để vượt qua rào cản an ninh của sàn (Cookie đã hết hạn). 👉 Vui lòng cấp mới cookies... hoặc bổ sung NopeCHA API Key.`
     - **Nếu Cookie còn hạn nhưng bị kẹt thử thách bảo mật**: Gửi thông báo `🚨 Cào sàn {plat_name} thất bại! Cả Cookie phiên đăng nhập lẫn Captcha đều không vượt qua được rào cản bảo mật của sàn ({quota_desc}). 👉 Vui lòng làm mới phiên đăng nhập trên Dashboard hoặc bổ sung NopeCHA API Key...`
   - Nhờ cơ chế break sau khi ghi nhận chặn trên sàn, thông báo này chỉ được gửi **tối đa 1 lần duy nhất** trong mỗi chu kỳ quét cho sàn đó, tuyệt đối không lặp lại trên từng sản phẩm.

## Consequences

- Loại bỏ triệt để 100% tình trạng spam tin nhắn Telegram về hạn ngạch NopeCHA.
- Crawler chạy bền bỉ và liên tục bằng Cookie phiên, không bị đình trệ vô lý khi hết lượt giải captcha miễn phí.
- Người dùng chỉ nhận được thông báo khi hệ thống thực sự cần can thiệp (cập nhật Cookie mới hoặc nạp API Key).
