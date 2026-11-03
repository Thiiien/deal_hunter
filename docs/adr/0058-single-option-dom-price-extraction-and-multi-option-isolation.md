# ADR 0058: Bóc tách giá sản phẩm đơn lẻ (Single-SKU DOM Price Extraction) và bảo vệ cách ly sản phẩm đa phân loại (Multi-Option Isolation)

## Trạng thái
Đã chấp thuận (Accepted)

## Bối cảnh
Trước đây:
1. Đối với sản phẩm có nhiều phân loại (multi-option/variants), Deal Hunter đã hoạt động chuẩn xác theo ADR 0053 và 0054: duyệt toàn bộ `sku_infos` để tìm SKU còn hàng (in-stock) có giá thấp nhất tuyệt đối.
2. Tuy nhiên, đối với sản phẩm đơn lẻ không có phân loại (single-SKU / no variants):
   - Khi Lazada hoặc Shopee chỉ hiển thị 1 SKU hoặc MTOP không trả về danh sách SKU chi tiết (chỉ render SSR / JSON-LD catalog), crawler lấy giá từ JSON-LD (`price = float(p_val)`).
   - Giá trong JSON-LD thường là giá niêm yết hoặc giá gốc chưa áp dụng các mã trợ giá, Flash Sale hoặc chương trình khuyến mãi hiển thị trực quan trên giao diện DOM (`.pdp-v2-product-price-content-salePrice`, `.pdp-price_color_orange`, `.priceSectionPrice`, `.pqTWkA`).
   - Do `price is not None` từ bước JSON-LD, crawler bỏ qua việc bóc tách giá sale trên DOM.
   - Khi sửa đổi, bắt buộc phải tuân thủ nghiêm ngặt nguyên tắc **Zero-Regression**: không được làm ảnh hưởng đến logic chọn SKU thấp nhất của các sản phẩm đa phân loại đã hoạt động chuẩn xác.

## Quyết định kỹ thuật
1. **Hạ cấp JSON-LD thành Fallback cuối cùng**:
   - Trong `_parse_lazada`, giá trích xuất từ `script[type="application/ld+json"]` được lưu vào biến `jsonld_price` thay vì gán trực tiếp vào `price`.
2. **Cách ly hoàn toàn giữa Sản phẩm Đa phân loại và Đơn lẻ**:
   - Nếu `len(sku_infos) > 1` (sản phẩm có nhiều phân loại): Giữ nguyên 100% logic hiện tại, chọn `best_sku = min(valid_skus, key=lambda x: x[1])`. Không để DOM selector ghi đè làm sai lệch giá của phân loại rẻ nhất.
   - Nếu `len(sku_infos) <= 1` (sản phẩm đơn lẻ không có phân loại hoặc chỉ 1 SKU):
     - Kiểm tra giá sale hiển thị trên DOM qua hàm trợ năng `_extract_lazada_dom_price(page)`.
     - Nếu DOM có giá sale hợp lệ và thấp hơn giá SKU/catalog, ưu tiên lấy giá DOM để phản ánh đúng mức giá trợ giá/khuyến mãi thực tế.
     - Nếu không có DOM price hoặc MTOP trống, fallback về `jsonld_price`.
3. **Shopee Single-Option DOM Check**:
   - Trong `_parse_shopee`, bổ sung kiểm tra `_extract_shopee_dom_price(page)` và flash sale price chỉ khi `not in_stock_models or len(in_stock_models) <= 1`. Sản phẩm có nhiều model giữ nguyên logic lặp `models` hiện tại.

## Hệ quả & Rủi ro
- Các sản phẩm đơn lẻ (như máy ảnh Sony ZV-E10, CPU AMD Ryzen 7500F, Sony A6000) lấy đúng mức giá khuyến mãi thực tế hiển thị trên trang sản phẩm.
- Các sản phẩm đa phân loại hoàn toàn không bị ảnh hưởng do luồng xử lý `len(sku_infos) > 1` được cách ly tuyệt đối.
