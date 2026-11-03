# 48. NopeCHA Extension Free Quota & Session Token Fallback

Date: 2026-10-30

## Status

Accepted

## Context

Trong quá trình cào dữ liệu từ Shopee và Lazada, các trang bảo vệ thường xuyên đưa ra thử thách Captcha (reCAPTCHA, GeeTest, Cloudflare Turnstile, slider captcha, MTOP punish iframe `/verify/slider`, `/punish`, `/verify/traffic`).

Trước đây:
1. Hệ thống hỗ trợ tích hợp NopeCHA qua API key trả phí (`NOPECHA_API_KEY`). Nếu người dùng không cấu hình API key, crawler không thể tự giải captcha.
2. Tiện ích mở rộng NopeCHA Chromium Extension cung cấp chính sách miễn phí **10 lượt giải Captcha/ngày** (free-tier credit) cho mỗi cài đặt extension mà không bắt buộc có API key.
3. Khi hết 10 lượt giải miễn phí hoặc khi captcha không thể giải được (crawler nhận ngoại lệ `Blocked`), hệ thống trước đây không phân biệt được nguyên nhân là do token phiên đăng nhập (cookies) bị hết hạn hay do cơ chế anti-bot của sàn kích hoạt, dẫn đến việc thiếu cảnh báo chính xác cho quản trị viên.

## Decisions

1. **Tự động triển khai NopeCHA Chromium Extension (Free Tier)**:
   - Trong Dockerfile: Tải và giải nén NopeCHA Chromium extension v0.6.1 (`chromium.zip` từ `NopeCHALLC/nopecha-extension`) vào `/app/extensions/nopecha` khi build container image.
   - Trên môi trường máy chủ cục bộ (Host): Thêm hàm `_ensure_nopecha_extension(ext_dir)` tự động tải và giải nén NopeCHA v0.6.1 nếu thư mục chưa tồn tại hoặc thiếu `manifest.json`.
   - Chromium trong Playwright tự động nạp extension qua các cờ `--load-extension` và `--disable-extensions-except`.

2. **Quản lý hạn ngạch 10 lượt giải miễn phí/ngày (`QuotaMonitor`)**:
   - Khi không cấu hình `NOPECHA_API_KEY`, `QuotaMonitor` tự động theo dõi số lượt giải trong ngày thông qua bảng `settings` trong SQLite (`captcha_solves_YYYY-MM-DD`).
   - Cung cấp các phương thức `record_solve(count=1)`, `get_daily_solves()`, `get_remaining_credits()`.
   - Khi đạt đủ 10 lượt giải trong ngày, `QuotaMonitor` chuyển cờ `is_exhausted = True` và thông báo tới Admin qua Telegram để thông báo hết hạn ngạch giải miễn phí trong ngày.
   - Lệnh `/quota` trên Telegram bot hiển thị chính xác trạng thái: hạn ngạch giải miễn phí `X/10 lượt hôm nay` hoặc số credit từ NopeCHA API.

3. **Cửa sổ chờ 15s cho NopeCHA Extension giải Captcha trong Playwright**:
   - Khi Playwright phát hiện tín hiệu bị chặn hoặc iframe thách thức captcha (`/punish`, `verify/slider`, `iframe[src*="punish"]`, `/verify/traffic`, v.v.), `PlaywrightAdapter` kích hoạt hàm `_wait_for_captcha_solve(page, timeout_sec=15)`.
   - Nếu NopeCHA giải thành công trong vòng 15 giây (URL chuyển hướng trở lại hoặc slider/punish iframe biến mất): ghi nhận `quota.record_solve(1)` và tiếp tục cào sản phẩm bình thường.
   - Nếu quá 15 giây mà không giải được: adapter ném ngoại lệ `Blocked`.

4. **Cơ chế Fallback kiểm tra Token phiên đăng nhập khi bị chặn (`Blocked`)**:
   - Khi gặp ngoại lệ `Blocked` (sau 3 lần liên tiếp hoặc với sản phẩm đơn lẻ), `Scanner` gọi `check_session_valid(data_dir, platform)` để phân định:
     - **Nếu Token/Cookie hết hạn**: Bắn cảnh báo khẩn cấp `🚨 Phiên đăng nhập sàn {plat_name} đã hết hạn! Vui lòng cấp mới cookies...` để quản trị viên cập nhật lại cookies phiên.
     - **Nếu Token vẫn còn hạn**: Bắn cảnh báo `⚠️ Sàn {plat_name} chặn Captcha (hết 10 lượt giải miễn phí)... Token phiên đăng nhập vẫn còn hạn.` và tạm dừng cào sàn đó trong chu kỳ quét hiện tại để bảo vệ tài khoản và địa chỉ IP.

## Consequences

- Hệ thống tận dụng tối đa 10 lượt giải captcha miễn phí mỗi ngày từ NopeCHA extension mà không tốn chi phí API key.
- Phân biệt minh bạch giữa lỗi hết hạn phiên đăng nhập và lỗi hết quota captcha, giúp người dùng nắm rõ khi nào cần cấp lại cookies và khi nào chỉ cần chờ chu kỳ quét kế tiếp.
- Giữ an toàn tối đa cho tài khoản người dùng và địa chỉ IP máy chủ trước các rủi ro khoá tài khoản do spam vượt captcha thất bại.
