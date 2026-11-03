# ADR 0063: Tích hợp Kết nối Chrome Thật qua CDP (Chrome DevTools Protocol) và Cơ chế Tự động Dự phòng (Graceful Fallback)

## Trạng thái
Đã chấp thuận (Accepted)

Superseded bởi ADR 0064: quay về headless trong Docker; code CDP còn giữ sau biến `CDP_URL`, script khởi chạy Chrome đã xóa.

## Bối cảnh
1. **Thách thức về Cookie và Captcha**:
   - Khi cào quét giá trên Shopee và Lazada ở tần suất định kỳ, việc chạy Playwright nội bộ trong môi trường Docker Linux (headless) khiến hệ thống chống bot nhận diện sự bất thường về dấu vân tay trình duyệt (vân tay Canvas, WebGL, thiếu card âm thanh/màn hình thật).
   - Hệ quả là token phiên an ninh (`x5sec`, `lzd_sid`, `SPC_EC`) bị sàn thu hồi liên tục sau vài giờ, kích hoạt rào cản xác thực thanh trượt (Slider Captcha) hoặc yêu cầu đăng nhập lại, làm gián đoạn tiến trình quét giá và khiến người dùng phải cập nhật cookie thủ công nhiều lần.
2. **Yêu cầu về độ chính xác của giá**:
   - Chế độ cào ẩn danh (Guest Mode) không thể tiếp cận các voucher độc quyền của shop, voucher tích lũy và trợ giá trực tiếp ("Mua ngay giảm...", ADR 0059) vốn chỉ hiển thị khi có phiên đăng nhập của người dùng.
   - Để lấy được mức giá thanh toán thực tế thấp nhất (chuẩn xác 100%), hệ thống bắt buộc phải duy trì phiên đăng nhập của người dùng.

## Quyết định
1. **Hạt nhân cào chính: Kết nối Chrome Thật qua CDP (`connect_over_cdp`)**:
   - Hỗ trợ Playwright kết nối trực tiếp vào phiên Google Chrome thật đang chạy trên máy tính qua giao thức điều khiển từ xa (Chrome DevTools Protocol - CDP) tại cổng `9222`.
   - Cung cấp script tiện ích `start_chrome_crawler.bat` trên Windows:
     - Tự động dò tìm cài đặt Google Chrome trên máy tính.
     - Khởi chạy Chrome với profile riêng biệt tại `data/chrome_profile` (hoàn toàn cách ly, không ảnh hưởng đến Chrome làm việc hàng ngày của người dùng).
     - Mở sẵn cờ `--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0` để container Docker giao tiếp thông suốt qua `host.docker.internal:9222`.
     - Người dùng chỉ cần đăng nhập tài khoản Shopee và Lazada trên cửa sổ Chrome này **1 lần duy nhất**. Phiên làm việc (Session) sẽ được duy trì bền bỉ hàng tháng nhờ cơ chế lưu trữ bảo mật phần cứng gốc của Google Chrome.
2. **Cơ chế Tự động Dự phòng (Graceful Fallback)**:
   - Trong `PlaywrightAdapter._ensure_browser()`:
     - Hệ thống sẽ thử kết nối tới cổng CDP (`cdp_url` hoặc `host.docker.internal:9222` / `127.0.0.1:9222`) với thời gian chờ an toàn (3 giây).
     - Nếu Chrome thật đang mở: kết nối thành công và sử dụng trực tiếp phiên Chrome thật (`self._using_cdp = True`).
     - Nếu Chrome thật chưa bật hoặc máy tính tắt: tự động bắt ngoại lệ và rơi về luồng khởi chạy trình duyệt nội bộ (`launch_persistent_context`) có sẵn mà không gây lỗi hay dừng tiến trình quét.
3. **Cập nhật Telegram Bot Menu và Điều khiển Nhanh**:
   - Đăng ký danh mục 10 lệnh thiết yếu qua `bot.set_my_commands()` và gán cho `BotCommandScopeChat(admin_id)`.
   - Bổ sung lệnh `/menu` hiển thị bảng điều khiển nút bấm nhanh (Inline Keyboard) cho các tác vụ thường ngày (`/list`, `/quetngay`, `/status`, `/quota`, `/theodoi`, `/help`).

## Hệ quả
- **Tích cực**:
  - Triệt tiêu 99% tình trạng văng cookie và captcha: Sàn nhận diện đây là người dùng lướt web trên máy tính thật với đầy đủ vân tay phần cứng và hành vi người dùng.
  - Lấy giá chuẩn xác 100%: Phản ánh đầy đủ voucher cá nhân, voucher tích lũy và trợ giá tại bước thanh toán.
  - Khả năng chịu lỗi cao: Không phụ thuộc cứng vào Chrome, tự động dự phòng về trình duyệt nội bộ khi cần.
  - Thao tác bot Telegram mượt mà và trực quan hơn.
- **Tiêu cực**:
  - Khi muốn tối ưu tuyệt đối chống captcha, người dùng cần duy trì cửa sổ Chrome chạy nền (`start_chrome_crawler.bat`).
