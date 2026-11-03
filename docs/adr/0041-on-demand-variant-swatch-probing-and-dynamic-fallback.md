# 41. Dò biến thể theo nhu cầu khi hết hàng và tái đánh giá biến thể thay thế động

## Bối cảnh
1. **Lệch giá giữa MTOP payload và giao diện DOM của Lazada:**
   - Trên một số chiến dịch khuyến mãi/Flash Sale (như "Tiệc Sale Chớp Nhoáng"), giá chuẩn trong payload tĩnh hoặc MTOP JSON của Lazada chỉ phản ánh mức giá gốc không áp dụng trợ giá tức thời (ví dụ variant Trắng là 1.005.000₫). Mức giá thực tế (540.700₫) chỉ được máy chủ nạp và hiển thị trên DOM khi người dùng nhấp chọn ô biến thể (swatch) tương ứng.
2. **Khóa cố định biến thể thay thế cũ:**
   - Khi biến thể chính (ví dụ N9 Pro Đen) hết hàng, hệ thống chọn một biến thể thay thế khác (ví dụ Xingyu Cam 880.000₫) và lưu vào `fallback_events`. Nếu biến thể thay thế tốt hơn (N9 Pro Trắng 540.700₫) sau đó giảm giá hoặc được cập nhật, hệ thống trước đây chưa tái đánh giá lại danh sách ứng viên mà vẫn tiếp tục giữ nguyên biến thể cũ.
3. **Yêu cầu khắt khe về hiệu năng từ người dùng:**
   - **Chỉ khi hết hàng mới cần click để chuyển qua các biến thể khác.** Khi biến thể đang chọn còn hàng (in stock), crawler tuyệt đối không thực hiện click dò biến thể nhằm đảm bảo tốc độ cào tối đa (zero-click overhead).

## Quyết định kiến trúc

1. **Dò biến thể theo nhu cầu chỉ khi hết hàng (`PlaywrightAdapter._parse_lazada`):**
   - Đánh giá trạng thái tồn kho của biến thể hiện tại trên DOM (nút mua bị vô hiệu hóa, thông báo hết hàng, hoặc gắn nhãn "Thêm vào danh sách yêu thích" / wishlist).
   - Nếu còn hàng (`is_dom_out_of_stock is False`): Bỏ qua hoàn toàn việc nhấp vào các ô biến thể (swatches). Duy trì zero-click.
   - Nếu hết hàng (`is_dom_out_of_stock is True` hoặc toàn bộ SKU ban đầu hết hàng):
     - Duyệt qua danh sách swatches trên DOM (`.sku-variable-img-wrap, .sku-variable-item, .sku-prop-content-item`).
     - Bỏ qua các swatch bị disable cứng.
     - Nhấp chọn từng swatch còn lại, đợi DOM cập nhật (`.pdp-price_type_normal`, `.pdp-price`, trạng thái nút mua).
     - Cập nhật giá thực và trạng thái kho trực tiếp vào `extracted_variants` và `valid_skus`.
     - Lựa chọn mức giá thấp nhất trong số các biến thể còn hàng và không phải phụ kiện rác.

2. **Tái đánh giá biến thể thay thế động (`db.evaluate_variant_state`):**
   - Khi biến thể chính vẫn đang hết hàng, trong mỗi chu kỳ quét khi có bảng giá biến thể mới từ `save_snapshot()`, hệ thống tự động tái đánh giá danh sách ứng viên biến thể thay thế.
   - Nếu có biến thể còn hàng mới với giá tốt hơn (như Pro Trắng 540.700₫ so với Xingyu Cam 880.000₫), hệ thống lập tức cập nhật `chosen_variant_id`, `effective_price` trong `fallback_events` và đồng bộ vào `price_history`.
   - Chuẩn hóa cờ `stock = 1` trong `price_history` khi biến thể thay thế được áp dụng thành công.

## Hệ quả
- Dữ liệu hiển thị trên tab Sản phẩm theo dõi luôn phản ánh chính xác giá thấp nhất của biến thể còn hàng thực tế trên sàn.
- Thời gian quét trang đối với các sản phẩm còn hàng không bị suy giảm (zero latency overhead).
- Dữ liệu lịch sử vi sai (`variant_history`) và `price_history` được đồng bộ chuẩn xác.
