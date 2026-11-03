# ADR 0007: Tự Động Nhận Diện Đăng Nhập và Kiểm Tra Phiên Trước Khi Quét

## Trạng thái

Accepted. Trong Docker không có màn hình nên đăng nhập tương tác không chạy; hệ thống báo admin cấp cookie (ADR 0048, 0050).

## Bối cảnh

Trước đây, khi cookies chưa được khởi tạo hoặc bị hết hạn, người dùng phải tự nhận thấy lỗi và chạy thủ công lệnh `python login.py`, sau đó phải nhấn phím Enter trên dòng lệnh để lưu session. Người dùng mong muốn quy trình này diễn ra hoàn toàn tự động: khi thiếu hoặc hết hạn cookie, hệ thống tự động mở trình duyệt lên cho người dùng quét mã QR, tự nhận diện khi đăng nhập xong, tự đóng trình duyệt và tự lưu cookies để tiếp tục quét.

## Quyết định

1. **Tự động nhận diện đăng nhập (Auto-detect Login Completion)**:
   - Trong `interactive_login()`, thay vì dùng `input()` chặn luồng chờ người dùng nhấn Enter, Playwright sẽ thăm dò (poll) cookie xác thực (`SPC_EC`, `SPC_U`, `shopee_token`, `SPC_ST`) và chuyển hướng URL (rời khỏi trang `/buyer/login`).
   - Ngay khi phát hiện đăng nhập thành công, hệ thống tự động lưu `data/cookies.json`, `data/storage_state.json` và đóng trình duyệt. Người dùng chỉ cần quét mã QR trên điện thoại là xong.

2. **Kiểm tra phiên trước quét (Pre-flight Session Check)**:
   - Trước mỗi chu kỳ quét (`Scanner.scan_all()`), hệ thống gọi `adapter.ensure_authenticated()`.
   - Kiểm tra `check_session_valid()`: nếu thiếu cookie hoặc session rỗng:
     - Nếu môi trường có giao diện đồ họa (máy host Windows, `has_display() == True`): Tự động bật Chrome lên màn hình cho người dùng đăng nhập (thời gian chờ tối đa 3 phút).
     - Nếu môi trường không có giao diện (headless Docker, `has_display() == False`): Gửi cảnh báo qua Telegram cho quản trị viên kèm hướng dẫn chạy `python login.py`.

3. **Cơ chế giới hạn thời gian (Unattended Timeout)**:
   - Đặt giới hạn 180 giây (3 phút) cho phiên đăng nhập tự động. Nếu quá 3 phút người dùng không quét QR hoặc đóng cửa sổ, Playwright tự đóng sạch tài nguyên, giải phóng lock và hoãn chu kỳ quét để tránh treo hệ thống.

## Hệ quả

- `deal_hunter.login` bổ sung `has_display()`, `check_session_valid()` và cơ chế tự động đóng trình duyệt khi quét QR xong.
- `BaseAdapter`, `PlaywrightAdapter`, `MockAdapter`, `FeedAdapter` hỗ trợ `ensure_authenticated()`.
- `Scanner.scan_all()` thực hiện pre-flight check trước mỗi chu kỳ quét.
- Khi người dùng chạy ứng dụng trực tiếp trên Windows (`python run.py`), trải nghiệm hoàn toàn mượt mà: Chrome tự động bật lên khi cần, người dùng quét QR, Chrome tự đóng và chu kỳ quét bắt đầu.
