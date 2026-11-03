# 35. Ưu tiên theo dõi biến thể giá thấp nhất còn hàng và chuyển tiếp biến thể tự động

## Bối cảnh
Trong tab **Sản phẩm theo dõi**, một đường dẫn sản phẩm thường có nhiều biến thể/phân loại (trên Shopee là `models`, trên Lazada là `skuInfos`). Trước đây, việc bóc tách biến thể gặp phải các tồn tại:
1. **Theo dõi nhầm biến thể đã hết hàng**:
   - Trên Shopee, API trả về trường `price_min` đại diện cho mức giá thấp nhất trên toàn bộ item trong quá khứ hoặc hiện tại. Tuy nhiên, `price_min` này thường thuộc về một biến thể đã cháy hàng (`stock = 0`) từ trước hoặc biến thể phụ kiện. Việc fallback ghi đè `raw_price = p_min` khiến hệ thống hiển thị mức giá rẻ của một phân loại người dùng không thể mua được.
   - Trên Lazada, dữ liệu JSON-LD tĩnh thường trỏ về SKU mặc định hoặc SKU hết hàng, khiến giá hiển thị không phản ánh phân loại còn hàng.
2. **Thiếu cơ chế chuyển tiếp biến thể khi cháy hàng (Stock Transition)**:
   - Khi biến thể có giá thấp nhất trước đó bị bán hết, hệ thống không tự động nhảy sang biến thể có giá thấp tiếp theo mà vẫn đang còn hàng.
3. **Cộng dồn ngoặc đơn tên biến thể qua các lần quét**:
   - Khi cập nhật tên biến thể `name = f"{name} ({var_name})"`, nếu không làm sạch chuỗi trước đó, qua nhiều lần quét hoặc chuyển tiếp biến thể, tiêu đề bị lặp ngoặc đơn (ví dụ: `AULA F75 (Bản Tiêu Chuẩn) (Bản Cao Cấp)`).

## Quyết định kiến trúc

1. **Ưu tiên biến thể giá thấp nhất còn hàng ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - **Shopee**: Lọc danh sách `in_stock_models = [m for m in models if (m.get("stock") or 0) > 0 and m.get("price") is not None]`. Loại bỏ các phân loại phụ kiện bằng `is_accessory_or_fake`. Chọn biến thể `min(target_models, key=lambda m: float(m["price"]))`.
   - **Loại bỏ fallback `price_min`**: Không ghi đè giá của biến thể còn hàng bằng `item.get("price_min")`. `price_min` chỉ được sử dụng làm fallback khi sản phẩm không có danh sách biến thể (sản phẩm đơn).
   - **Lazada**: Lọc `valid_skus = [(float(price), name, sku_id) for sku_id, info in sku_infos.items() if info.get("operation", {}).get("disable") is not True and info.get("quantity", 1) > 0]`. Khi có `valid_skus`, giá sản phẩm được gán trực tiếp bằng `best_sku[0]` (giá thấp nhất còn hàng), bỏ qua giá tĩnh từ JSON-LD.
   - **Đồng bộ giá niêm yết (List Price)**: Trích xuất `price_before_discount` của chính biến thể được chọn để phản ánh tỷ lệ chiết khấu chính xác.

2. **Chuyển tiếp biến thể tự động (Automatic Transition):**
   - Ở mỗi chu kỳ quét, crawler đánh giá lại toàn bộ biến thể. Nếu biến thể rẻ nhất trước đó hết hàng, hệ thống tự động chọn biến thể rẻ tiếp theo đang còn hàng.
   - Chỉ khi toàn bộ biến thể hợp lệ đều hết hàng (`stock = 0` hoặc `disable = True`), sản phẩm mới bị đánh dấu là hết hàng (`stock = False`).

3. **Làm sạch tiêu đề biến thể chống lặp ngoặc đơn:**
   - Dùng biểu thức chính quy `clean_name = re.sub(r"\s*\([^)]*\)$", "", name).strip()` để gỡ bỏ hậu tố biến thể cũ trước khi gắn hậu tố biến thể mới: `name = f"{clean_name} ({var_name})"`.

## Hệ quả
- Dữ liệu sản phẩm theo dõi luôn phản ánh đúng phân loại có thể mua được với mức giá tối ưu nhất.
- Không còn tình trạng báo deal ảo hay lỗi giá ảo từ các phân loại đã hết hàng.
- Toàn bộ 150 test unit trong bộ kiểm thử đều vượt qua.
