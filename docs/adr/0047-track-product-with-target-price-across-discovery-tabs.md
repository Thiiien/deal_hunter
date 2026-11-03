# 47. Track Product with Target Price Across Discovery Tabs

Date: 2026-10-29

## Status

Accepted. Các tab khám phá ẩn theo ADR 0055; chu kỳ quét sản phẩm theo dõi là 2 phút theo ADR 0060 (thay cho "8-15 phút" ở mục 2).

## Context

Hệ thống Deal Hunter hỗ trợ nhiều kênh khám phá deal tự động:
1. **Lazada TMALL** (`source = 'lazada_tmall'`): Cào sản phẩm chính hãng từ trang LazMall TMALL chính thức.
2. **Siêu Sale & Giảm sâu** (`source = 'flash_sale'`): Tổng hợp các deal giảm sâu từ flash sale Shopee & Lazada.
3. **Theo từ khóa** (`keyword_products`): Các sản phẩm khớp với bộ lọc từ khóa cấu hình của người dùng.

Trước đây:
- Tại Tab Lazada TMALL, người dùng chỉ có nút "Xem ↗" và "Xóa 🗑️", không có nút "➕ Theo dõi" để chuyển sản phẩm vào danh sách theo dõi cá nhân ("📦 Sản phẩm theo dõi").
- Tại Tab Siêu Sale, nút "➕ Theo dõi" chỉ thêm link vào database mà không cho phép đặt ngay **Giá mong muốn (Target Price)**. Người dùng phải chuyển sang tab Sản phẩm theo dõi rồi bấm nút ✏️ để cấu hình giá mục tiêu.
- Khi người dùng muốn đặt một mức giá cụ thể để nhận thông báo khẩn cấp qua Telegram khi sản phẩm giảm về mức đó, luồng thao tác bị ngắt quãng.

## Decisions

1. **Chuẩn hóa thao tác "➕ Theo dõi & Đặt giá mong muốn" trên toàn bộ các Tab khám phá**:
   - Bổ sung nút **➕ Theo dõi** đồng nhất trên Tab **Lazada TMALL**, **Siêu Sale & Giảm sâu**, và **Theo từ khóa**.
   - Khi người dùng nhấp **➕ Theo dõi**, hệ thống mở prompt nhập **Giá mong muốn (₫)**:
     - Gợi ý sẵn mức giá giảm 10% so với giá hiện tại làm mốc tham chiếu.
     - Cho phép người dùng nhập mức giá mục tiêu mong muốn, hoặc để trống / nhấn OK để thêm sản phẩm vào danh sách theo dõi mà không đặt giá.

2. **Hỗ trợ `target_price` trực tiếp tại Backend API (`POST /api/products`)**:
   - Endpoint `POST /api/products` chấp nhận payload `{ url: str, target_price: float | null }`.
   - Nếu `target_price` được cung cấp và hợp lệ (> 0), hệ thống tự động gọi `db.set_target_price(pid, target_price)` ngay trong cùng phiên tạo / kích hoạt sản phẩm.
   - Sản phẩm được nâng cấp `source = 'user'` theo cơ chế `ON CONFLICT DO UPDATE SET source='user'`, đưa sản phẩm vào chu kỳ quét ưu tiên của `get_active_tracked_products()` (8-15 phút/lần).
   - Khi scanner ghi nhận giá hiệu dụng `effective_price <= target_price`, bot Telegram lập tức bắn thông báo deal mục tiêu đến người dùng.

3. **Phản hồi trạng thái giao diện trực quan (UI State Reflection)**:
   - Khi một sản phẩm đã thuộc diện người dùng theo dõi (`p.source === 'user'`), nút thao tác tại dòng sản phẩm trong tab TMALL, Siêu Sale và Từ khóa tự động chuyển sang **✅ Đang theo dõi** (disabled) để tránh bấm trùng.
   - Tại Tab TMALL, nếu sản phẩm đã có giá mong muốn, nhãn `🎯 Mục tiêu: X₫` được hiển thị trực quan ngay dưới ô giá sản phẩm.
   - Sản phẩm TMALL sau khi được người dùng theo dõi vẫn tiếp tục hiển thị tại Tab TMALL (thông qua nhận diện `p.current_campaign === 'TMALL Trợ Giá'`) song song với việc xuất hiện tại Tab [📦 Sản phẩm theo dõi].

## Consequences

- Người dùng có thể săn deal và thiết lập ngưỡng giá cảnh báo Telegram chỉ trong một cú nhấp chuột từ bất kỳ tab khám phá nào.
- Trải nghiệm theo dõi sản phẩm trở nên liền mạch, nhất quán và minh bạch trên toàn bộ giao diện Dashboard.
