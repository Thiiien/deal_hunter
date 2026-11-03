# 37. Chuẩn hóa URL Item và trích xuất giá biến thể qua MTOP API trên Lazada

## Bối cảnh
Người dùng phản ánh hệ thống hiển thị và theo dõi giá không đúng nguyên tắc: Với sản phẩm có nhiều phân loại (SKU), hệ thống cần ưu tiên lấy giá của phân loại CÒN HÀNG và phải lấy loại có GIÁ THẤP NHẤT.
Tuy nhiên, trên thực tế sản phẩm 2790 và 2788 lại hiển thị mức giá cao chót vót (4.105.000₫ và 4.044.000₫) thay vì mức giá biến thể thấp nhất còn hàng (khoảng 1.153.000₫).

Qua điều tra thực nghiệm chi tiết trên mạng và DOM của trang chi tiết Lazada (`pdp_revamp`), phát hiện 3 nguyên nhân cốt lõi:
1. **Liên kết bị khóa cứng vào mã SKU cụ thể (`-s<skuid>.html`)**:
   - Khi người dùng dán link dạng `...-i13409556827-s117098513613.html`, Lazada gắn mã `defaultSkuId: 117098513613` và chỉ xuất trường `tracking.pdt_price: 4.105.000₫` cho đúng SKU đó trong SSR HTML.
2. **SSR HTML không nhúng giá biến thể**:
   - Trong dữ liệu SSR `window.__moduleData__`, toàn bộ 19 SKU đều có `price: None`, `salePrice: None`. Giá và tồn kho thực tế chỉ được nạp qua API client-side `mtop.global.detail.web.getdetailinfo`.
3. **Bỏ lọt endpoint MTOP và không phát hiện iframe punish**:
   - Bộ lắng nghe gói tin mạng trước đây chỉ bắt `mtop.lazada.item.detail`, bỏ qua `mtop.global.detail.web.getdetailinfo`.
   - Khi phiên duyệt web bị Lazada kiểm tra bot hoặc hết hạn `x5sec`, API MTOP trả về iframe `punish?x5secdata=...`. Scraper không nhận diện iframe này nên rơi vào fallback đọc `tracking.pdt_price`, vô tình lưu giá ảo (4.105.000₫) vào cơ sở dữ liệu.

## Quyết định kiến trúc

1. **Chuẩn hóa URL Lazada về cấp Item gốc ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Tự động tách bỏ hậu tố `-s\d+` khỏi đường dẫn khi truy vấn hoặc phân tích, giữ lại dạng chuẩn `...-i<itemId>.html`.
   - Giúp trình duyệt tải trang ở trạng thái Item tổng quan, cho phép đánh giá đầy đủ toàn bộ dải phân loại.

2. **Chặn bắt MTOP `mtop.global.detail` và nạp giá biến thể:**
   - Mở rộng bộ lọc `_on_response` để chặn bắt `mtop.global.detail` và `getdetailinfo`.
   - Cập nhật payload chi tiết SKU (`salePrice`, `originalPrice`, `quantity`, `operation`) vào `sku_infos` để tìm ra biến thể còn hàng có giá rẻ nhất.

3. **Phát hiện iframe Punish và chặn ghi nhận giá ảo:**
   - Kiểm tra sự xuất hiện của `iframe[src*="punish"]` hoặc frame chứa `acs-m.lazada.vn/.../punish`.
   - Nếu phát hiện bị chặn captcha mà không có dữ liệu giá SKU hợp lệ, kích hoạt `Blocked` thay vì âm thầm đọc `tracking.pdt_price`.

## Hệ quả
- Hệ thống luôn chọn chính xác biến thể còn hàng có giá thấp nhất trên toàn bộ dải phân loại của link sản phẩm Lazada.
- Ngăn chặn hoàn toàn việc ghi nhận giá ảo 4 triệu đồng khi bị chặn captcha.
