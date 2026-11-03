# ADR 0060: Kiến trúc Polling 2 Tầng (Dual-Speed Polling Architecture) và Tự động phục hồi phiên (Self-Healing Session Fallback)

## Trạng thái
Đã chấp thuận (Accepted)

## Bối cảnh
Người dùng cần săn các deal giảm giá sâu và sản phẩm bị lỗi giá (price error) trong thời gian ngắn nhất có thể (< 2 phút). Tuy nhiên:
1. Việc mở toàn bộ trình duyệt Playwright (Headless Chromium) cho mọi sản phẩm trong chu kỳ ngắn làm tiêu tốn CPU/RAM rất lớn (300MB - 500MB RAM/lượt) và dễ kích hoạt cơ chế giới hạn tần suất (rate limiting / punish challenge) của các sàn thương mại điện tử.
2. Kiểm tra thực nghiệm trên toàn bộ 25 sản phẩm theo dõi cho thấy giá lấy trực tiếp từ API (Shopee PDP API & Lazada MTOP JSON) và giá hiển thị trên DOM của Playwright trùng khớp 100%.
3. Dù vậy, API đơn thuần không thể tự giải Captcha khi phiên làm việc (cookie) hết hạn, và các voucher hiển thị dạng pop-up/banner đôi khi cần render DOM để xác thực.

## Quyết định
Áp dụng mô hình **Kiến trúc Polling 2 Tầng (Dual-Speed Polling Architecture)**:

1. **Tầng 1 - Quét nhanh (Tier-1 Fast Poller)**:
   - Với Shopee: Gọi trực tiếp Endpoint JSON (`/api/v4/pdp/get_pc`) qua HTTP client gọn nhẹ (`httpx`) kèm cookie phiên làm việc, hoàn thành trong ~150ms - 300ms mà không cần khởi tạo trình duyệt.
   - Với Lazada: Tận dụng cơ chế chặn tài nguyên nặng (`image`, `media`, `font`, `tracking`) và bóc tách trực tiếp payload `skuInfos` (đã hỗ trợ bóc tách voucher `coupon.priceNumber` theo ADR 0059).
   - Chu kỳ quét được người dùng cấu hình linh hoạt trong mục Cài đặt (`scan_interval_min`, mặc định giảm xuống còn 2 phút).

2. **Tầng 2 - Xác thực chuyên sâu (Tier-2 Playwright Verifier & Escalation)**:
   - Khi phát hiện biến động giá bất thường:
     - Giá giảm ≥ 20% so với giá gần nhất.
     - Giá chạm hoặc thấp hơn giá mục tiêu (`target_price`).
     - Nghi vấn lỗi giá (giảm ≥ 65% so với giá gốc/lịch sử).
   - Hệ thống lập tức kích hoạt Playwright Verifier để tải trang đầy đủ, chụp ảnh màn hình (screenshot) làm bằng chứng và xác thực lại trên DOM trước khi bắn thông báo Telegram.

3. **Cơ chế tự phục hồi phiên (Self-Healing Session Fallback)**:
   - Nếu Tầng 1 gặp lỗi phiên hết hạn, cookie rỗng hoặc sàn trả về yêu cầu xác minh an ninh (slider/punish iframe):
   - Hệ thống tự động chuyển giao cho Playwright cùng tiện ích NopeCHA giải quyết thách thức, nạp lại cookie mới vào `data/cookies.json` / `data/cookies_lazada.json` và tiếp tục quét bình thường.

## Hệ quả
- **Tích cực**:
  - Giảm độ trễ phát hiện deal và lỗi giá từ 30-60 phút xuống còn 1 - 2 phút.
  - Tiết kiệm 80-90% tài nguyên CPU/RAM trong trạng thái hoạt động bình thường.
  - Đảm bảo tính xác thực cao: không lo spam cảnh báo giả nhờ tầng Playwright Verifier xác minh kép.
  - Tuyệt đối không làm ảnh hưởng đến logic lấy giá đa phân loại (multi-option) đã kiểm chứng.
- **Tiêu cực**:
  - Khi sàn đổi thuật toán token MTOP, hệ thống sẽ tự động fallback về Playwright đầy đủ, chu kỳ quét có thể kéo dài thêm một vài giây trong lúc giải Captcha.
