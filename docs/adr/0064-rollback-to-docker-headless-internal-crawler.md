# 64. Quay về Trình duyệt Headless Ngầm trong Docker (Rollback to Docker Headless Internal Crawler)

## Trạng thái
Đã chấp thuận (Accepted)

## Bối cảnh
Sau khi thử nghiệm giải pháp kết nối Google Chrome thật qua CDP trên máy tính chủ (ADR 0063), người dùng ghi nhận các bất cập thực tế:
1. **Giao diện nhảy và gây phiền**: Việc Playwright mở tab duyệt sản phẩm trên Chrome thật của hệ điều hành gây nhảy tab, chiếm chuột và phân tâm khi người dùng đang sử dụng máy tính làm việc.
2. **Thách thức Captcha trên màn hình chính**: Khi gặp các liên kết sản phẩm đã ngừng bán (404/delisted) hoặc sàn kích hoạt reCAPTCHA, hộp thoại kiểm tra robot bật lên ngay trước mắt người dùng thay vì được xử lý âm thầm trong nền.
3. **Yêu cầu của người dùng**: Thu hồi cơ chế Chrome CDP, quay lại chế độ chạy hoàn toàn ngầm trong container Docker (Docker Headless) như kiến trúc ban đầu.

## Quyết định kiến trúc
1. **Hoàn nguyên chế độ cào mặc định về Docker Headless**:
   - Loại bỏ cấu hình `CDP_URL` và `extra_hosts` khỏi [docker-compose.yml](file:///C:/Users/pvthien/source/deal_hunter/docker-compose.yml).
   - Container Docker `deal_hunter-deal-hunter-1` tự động khởi chạy Chromium nội bộ ở chế độ ngầm (`launch_persistent_context` với cờ `--headless=new`).
2. **Khai thác tiện ích tự động giải Captcha ngầm trong Docker**:
   - Tận dụng tiện ích NopeCHA đã được cài đặt sẵn tại `/app/extensions/nopecha` trong Docker image kết hợp với thuật toán kéo thanh trượt Slider Drag để giải captcha hoàn toàn ngầm trong nền container mà không ảnh hưởng tới màn hình làm việc của người dùng.
3. **Giải phóng tài nguyên máy chủ**:
   - Đóng tiến trình Chrome Crawler chạy trên cổng `9222` của máy chủ Windows.
4. **Bảo toàn khả năng mở rộng (Extensibility)**:
   - Giữ nguyên mã nguồn hỗ trợ CDP trong [playwright.py](file:///C:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py) để có thể tái kích hoạt bằng cờ cấu hình `CDP_URL` trong tương lai nếu cần, nhưng chế độ mặc định luôn là Docker Headless ngầm.

## Hệ quả
- **Tích cực**:
  - Màn hình máy tính của người dùng hoàn toàn yên tĩnh, không bị mở tab hay che khuất giao diện.
  - Toàn bộ crawler được đóng gói gọn gàng, tự trị bên trong container Docker.
- **Tiêu cực / Rủi ro**:
  - Khi chạy Headless trong Docker, thời hạn sống của cookie tài khoản sẽ ngắn hơn so với Chrome thật. Người dùng cần cập nhật lại cookie vào `data/cookies.json` và `data/cookies_lazada.json` khi phiên hết hạn.
