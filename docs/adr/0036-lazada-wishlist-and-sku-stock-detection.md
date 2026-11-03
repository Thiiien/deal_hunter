# 36. Nhận diện hết hàng qua trạng thái Yêu thích (Wishlist) và số lượng SKU trên Lazada

## Bối cảnh
Khi một sản phẩm trên sàn Lazada hết hàng toàn bộ hoặc hết hàng theo từng phân loại (SKU), hệ thống trước đây vẫn nhận diện là Còn hàng (`stock = True`) và ghi nhận mức giá của phân loại hết hàng.

Qua điều tra thực tế trực tiếp trên trang chi tiết sản phẩm (`https://www.lazada.vn/products/...-i13467967356-s117392597274.html`), phát hiện 2 nguyên nhân gốc rễ:
1. **Lazada không gán `disable: true` cho SKU hết hàng**:
   - Khi SKU hết hàng, Lazada chuyển đổi hành vi của nút sang thao tác Wishlist:
     `operation = {'disable': False, 'type': 'wishlist', 'text': 'Thêm vào danh sách Yêu thích'}`
     `quantity = {'limit': {'max': 0, 'min': 0}, 'text': 'Hết hàng', 'type': 'warning'}`
   - Do nút Wishlist vẫn bấm được nên `operation.disable` mang giá trị `False`. Code cũ kiểm tra `elif op_disable is False: is_in_stock = True` trước `quantity`, khiến crawler nhận định sai là phân loại còn hàng.
2. **Nút Mua chuyển thành Yêu thích trong DOM**:
   - Ở tầng DOM, nút Mua/Thêm vào giỏ chuyển thành class `.add-to-cart-buy-now-btn` với văn bản `"Thêm vào danh sách Yêu thích"`. Bộ kiểm tra DOM `is_dom_out_of_stock` trước đây chỉ bắt các từ khóa `"hết hàng"`, `"out of stock"` mà bỏ qua `"yêu thích"` / `"wishlist"`.
   - Đồng thời selector `[class*="sku-variable"]` bị khớp nhầm vào các thẻ con không có thuộc tính disabled (như `.sku-variable-img-wrap`), dẫn đến đánh giá sai là còn phân loại khả dụng.

## Quyết định kiến trúc

1. **Đảo thứ tự ưu tiên kiểm tra tồn kho SKU ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Đặt các điều kiện hết hàng tuyệt đối lên hàng đầu:
     - `op_disable is True`
     - `op_type == "wishlist"` hoặc text chứa `"yêu thích"`, `"wishlist"`, `"hết hàng"`
     - `quantity` dạng dict có `quantity.limit.max <= 0` hoặc `quantity.text` chứa `"hết hàng"`
     - `stk_val <= 0` hoặc `qty_val <= 0`
   - Chỉ khi phân loại vượt qua tất cả các điều kiện trên và có số lượng hợp lệ mới được coi là còn hàng (`is_in_stock = True`).

2. **Bổ sung nhận diện nút Yêu thích trên DOM:**
   - Trong `is_dom_out_of_stock`:
     - Kiểm tra nút hành động mua hàng (`.add-to-cart-buy-now-btn`, `.next-btn-buy...`): Nếu chứa `"yêu thích"` hoặc `"wishlist"`, xác định ngay là hết hàng (`return true`).
     - Chuẩn hóa selector phân loại chỉ nhắm vào các swatch thực tế (`.sku-variable-item, .sku-prop-content-item, [class*="sku-variable-item-"]`).

3. **Chặn cảnh báo khi sản phẩm Hết hàng ([scanner.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
   - Giữ nguyên mức giá của phân loại gần nhất trong `price_history` để người dùng theo dõi biểu đồ giá.
   - Thêm điều kiện `snapshot.stock is not False` vào các luồng gửi cảnh báo mục tiêu, cảnh báo lỗi giá (price error), cảnh báo giảm giá (price drop) và cảnh báo flash deal, ngăn chặn tuyệt đối việc thông báo các deal không thể mua được.

## Hệ quả
- Khắc phục triệt để tình trạng link hết hàng cả 4 phân loại trên Lazada nhưng vẫn báo còn hàng.
- Không gửi cảnh báo giả sập giá/lỗi giá khi shop hết hàng.
- Toàn bộ 151 unit test trong test suite vượt qua.
