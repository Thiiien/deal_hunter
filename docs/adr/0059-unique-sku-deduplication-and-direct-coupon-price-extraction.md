# ADR 0059: Chuẩn hóa định danh SKU duy nhất (Unique SKU Deduplication) và Bóc tách giá Voucher trực tiếp (Direct Coupon Price Extraction)

## Trạng thái
Đã chấp thuận (Accepted)

## Bối cảnh
Trước đây:
1. Khi cào sản phẩm Lazada đơn lẻ (Single-SKU) như AMD Ryzen 5 7500F, cấu trúc MTOP `skuInfos` trả về 2 phần tử gồm key `'0'` (chỉ mục mặc định) và key `'117120756839'` (mã SKU thực tế). Cả 2 phần tử này đều mang cùng một `skuId` duy nhất.
2. Việc đếm số lượng key trong từ điển (`len(sku_infos) == 2 > 1`) khiến hệ thống nhận định sai sản phẩm 1 option thành "sản phẩm có nhiều phân loại", làm bỏ qua luồng xử lý sản phẩm đơn lẻ.
3. Đồng thời, trong đối tượng `price` của SKU, mức giá `6.527.000₫` là `salePrice` trước voucher, trong khi sàn hiển thị mức giá thực tế màu đỏ **`5.156.330₫`** sau khi áp dụng voucher trực tiếp "Mua ngay giảm 1.370.670₫" (nằm tại trường `coupon.priceNumber` và class DOM `.pdp-v2-product-price-content-salePrice-amount`). Hàm `_clean_price_val` trước đây chỉ quét các trường `salePrice`/`value` nên đã bỏ lỡ `coupon`.

## Quyết định kỹ thuật
1. **Chuẩn hóa nhận diện biến thể bằng Unique SKU ID**:
   - Sử dụng `unique_sku_ids = set(str(sinfo.get("skuId") or sid))` để đếm số lượng biến thể thực sự.
   - Chỉ khi `len(unique_sku_ids) > 1` hệ thống mới chuyển vào nhánh xử lý sản phẩm đa phân loại (chọn biến thể rẻ nhất in-stock).
   - Nếu `len(unique_sku_ids) <= 1`, sản phẩm được xác định chính xác là sản phẩm đơn lẻ, kích hoạt cơ chế bóc tách giá sale/voucher trực tiếp.
   - Sử dụng `seen_sids` để khử trùng lặp các SKU mang cùng `skuId`, loại bỏ tình trạng nhân đôi biến thể trong `variants`.
2. **Ưu tiên bóc tách giá Voucher trực tiếp (`coupon.priceNumber`)**:
   - Nâng cấp `_clean_price_val(raw_val)`: nếu `raw_val` là dictionary chứa `coupon`, ưu tiên trích xuất `coupon.priceNumber` hoặc `coupon.priceText` trước các trường `salePrice` danh nghĩa.
   - Nâng cấp `_extract_lazada_dom_price`: bổ sung `.pdp-v2-product-price-content-salePrice-amount` lên đầu danh sách selector.
   - Đối với giá gốc (`list_price`), trích xuất từ `price.originalPrice` để bảo lưu chính xác giá niêm yết (ví dụ `8.484.000₫ -39%`).
3. **Bảo toàn 100% cách ly sản phẩm đa phân loại**:
   - Sản phẩm có nhiều biến thể (`len(unique_sku_ids) > 1`) hoàn toàn không bị ảnh hưởng, giữ nguyên logic chọn SKU còn hàng rẻ nhất.

## Hệ quả & Rủi ro
- Giá bóc tách cho các sản phẩm đơn lẻ như AMD Ryzen 5 7500F phản ánh chính xác 100% số tiền thực trả hiển thị trên giao diện người mua (`5.156.330₫`).
- Danh sách biến thể không còn bị trùng lặp.
- Các sản phẩm đa phân loại tiếp tục hoạt động độc lập và ổn định.
