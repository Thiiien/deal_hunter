# 39. Máy trạng thái tồn kho, Quét nhanh xác minh và Cơ chế thay thế biến thể âm thầm

## Trạng thái

Accepted.

## Bối cảnh
Sau khi hoàn thiện nền tảng dữ liệu đa biến thể ở Phase 1 (ADR 0038), hệ thống cần một cơ chế tự động xử lý khi **Biến thể chính (Main Variant)** bị hết hàng. 
Theo tài liệu thiết kế [.docs/VARIANT_FALLBACK.md](file:///c:/Users/pvthien/source/deal_hunter/.docs/VARIANT_FALLBACK.md):
- Nếu chỉ dựa vào 1 lần quét để chuyển trạng thái sang hết hàng, nguy cơ kết luận sai (false positive) do mạng chập chờn hoặc trang chưa tải xong là rất cao.
- Nếu gửi tin nhắn Telegram liên tục mỗi khi nghi hết hàng, quét xác minh hoặc đổi sang biến thể phụ, người dùng sẽ bị làm phiền bởi các thông báo rác nội bộ.
- Cần có quy tắc mặc định an toàn (default rule) để tự động chọn biến thể thay thế mà không bắt buộc người dùng phải cấu hình từng sản phẩm.

## Quyết định kiến trúc

1. **Máy trạng thái tồn kho (Stock State Machine):**
   - Trạng thái 1: `CÒN HÀNG` (In Stock) — Biến thể chính đang còn hàng.
   - Trạng thái 2: `NGHI HẾT` (Unconfirmed Out of Stock / `suspect_out`) — Lần đầu tiên phát hiện biến thể chính hết hàng. Ghi nhận sự kiện vào `fallback_events` và tự động hẹn giờ quét nhanh xác minh (Fast Verification Scan).
   - Trạng thái 3: `HẾT HÀNG / TẠM THAY` (Confirmed Out of Stock / `active`) — Lần thứ 2 liên tiếp biến thể chính vẫn hết hàng. Chính thức kích hoạt thuật toán chọn **Biến thể thay thế (Fallback Variant)**.
   - Trạng thái 4: `HOÀN NGUYÊN` (Resolved) — Khi biến thể chính có hàng trở lại, sự kiện fallback được đóng (`resolved`) và hệ thống tự động hoàn nguyên giá/tồn kho về biến thể chính.

2. **Quét nhanh xác minh (Fast Verification Scan):**
   - Khi chuyển sang `NGHI HẾT`, hệ thống kích hoạt một Timer ngầm (`threading.Timer(180, ...)`) để quét lại sản phẩm đó sau 3 phút mà không làm nghẽn chu kỳ quét định kỳ chung.

3. **Chế độ thay thế âm thầm (Silent Fallback Mode):**
   - Toàn bộ quá trình chuyển trạng thái, fast scan và kích hoạt biến thể thay thế diễn ra hoàn toàn âm thầm trong cơ sở dữ liệu và hiển thị trên Dashboard / lệnh `/bienthe`.
   - Tuyệt đối không gửi tin nhắn push qua Telegram về việc đổi biến thể. Telegram chỉ gửi thông báo khi giá biến thể đang áp dụng thỏa mãn tiêu chí Deal thật hoặc Giá mong muốn.

4. **Thuật toán quy tắc thay thế mặc định (Default Fallback Rule):**
   - Áp dụng khi sản phẩm chưa có cấu hình riêng trong `fallback_rules`.
   - `mode = 'any'`, trần giá +20% so với giá tham chiếu của biến thể chính (`price_ceiling_pct = 20.0`).
   - Tự động loại trừ các biến thể phụ kiện/rác bằng `is_accessory_or_fake()`.
   - Chọn biến thể còn hàng có giá thấp nhất trong số các ứng viên hợp lệ.

5. **Đồng bộ hiển thị giá:**
   - Khi ở trạng thái `TẠM THAY`, mức giá của Biến thể thay thế được cập nhật vào snapshot giá mới nhất để Dashboard và hệ thống đánh giá deal phản ánh chính xác phân loại đang mua được trên sàn, trong khi `products.main_variant_id` vẫn được giữ nguyên.

## Hệ quả
- Loại bỏ hoàn toàn tình trạng chuyển biến thể ảo do gián đoạn mạng tạm thời.
- Kênh Telegram giữ được sự tinh gọn, không bị spam bởi các log trạng thái.
- Hệ thống tự động phục hồi về biến thể chính ngay khi shop nhập thêm hàng.
