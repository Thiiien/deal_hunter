# 54. Đảm bảo lấy đúng phân loại giá thấp nhất và Triệt tiêu giá trần ảo

Date: 2026-11-01

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`)

## Bối cảnh

1. **Khóa cứng phân loại cũ qua `main_variant_id` trong chu kỳ quét**:
   - Khi quét sản phẩm theo dõi (`scan_product`), hệ thống đọc `main_variant_id` từ cơ sở dữ liệu và truyền vào làm `target_sku`.
   - Trong parser (`_parse_shopee` và `_parse_lazada`), `target_match` được ưu tiên chọn trước hàm `min()`, khiến các sản phẩm đã theo dõi bị "ghim chết" vào đúng phân loại ban đầu mà không bao giờ chuyển sang phân loại còn hàng có giá thấp nhất của listing.
2. **Lỗi logic Dò biến thể DOM trên Lazada (`operation-disabled` bug)**:
   - Trong script dò biến thể DOM của Lazada (`probe_res`), việc kiểm tra trạng thái hết hàng sử dụng `document.querySelector('.operation-disabled')` trên toàn phạm vi tài liệu (`document`).
   - Do Lazada gắn class `operation-disabled` vào bất kỳ ô swatch nào đang bị hết hàng, chỉ cần listing có ít nhất 1 biến thể hết hàng, toàn bộ các biến thể khác khi click vào đều bị đánh dấu nhầm là `inStock = false`. Kết quả là danh sách `probed_skus` bị trống và toàn bộ giá khuyến mãi dò được từ DOM bị hủy bỏ.
3. **Lạm phát giá niêm yết từ giá trần gian hàng (`tracking.pdt_price`)**:
   - Trường `tracking.pdt_price` trong payload Lazada thực chất là giá trần danh mục (thường từ 4.000.000₫ đến 5.600.000₫).
   - Việc dùng `pdt_price` làm giá gốc (`list_price`) khiến các sản phẩm giá vài trăm nghìn đồng (như tai nghe 400k, bàn phím 700k) bị hiển thị là giảm sâu 80-93%, gây spam cảnh báo "Deal thật" và "Lỗi giá" giả mạo trên Telegram và Dashboard.
4. **Sản phẩm bị xóa (404 Not Found) vẫn hiển thị còn hàng**:
   - Một số sản phẩm bị người bán xóa vĩnh viễn (như link ID 4161) trả về HTTP 404 hoặc tiêu đề "Xin lỗi! Sản phẩm này không còn tồn tại", nhưng hệ thống vẫn duy trì `stock = 1` và giá cũ.

## Quyết định kiến trúc

1. **Ưu tiên giá thấp nhất tuyệt đối của toàn bộ listing (Absolute Lowest In-Stock Variant Priority):**
   - Đối với sản phẩm người dùng theo dõi, parser luôn chọn `min()` của toàn bộ biến thể còn hàng (`in_stock_models` trên Shopee, `valid_skus` trên Lazada).
   - Không truyền `target_sku` khi quét sản phẩm theo dõi trong `scanner.py`, đảm bảo crawler luôn thích ứng động với biến thể rẻ nhất tại mỗi chu kỳ.
   - Giá niêm yết (`list_price`) trên Shopee được lấy tương ứng theo đúng phân loại rẻ nhất được chọn (`lowest_model["price_before_discount"]`), không lấy giá trần `max()` của các phân loại đắt tiền khác.

2. **Khắc phục triệt để logic dò biến thể DOM (DOM Swatch Probing Fix):**
   - Loại bỏ truy vấn `.operation-disabled` trên toàn trang. Chỉ kiểm tra tình trạng hết hàng tại khu vực cảnh báo tồn kho cục bộ (`.quantity-content-warning`), nút Mua hàng (`buyBtn`), và chính ô swatch đang được chọn (`.sku-variable-img-wrap-selected.disabled`).
   - Chuẩn hóa bóc tách giá DOM bằng Regex nhận diện tiền tệ, chống lỗi ghép số khi có nhãn phần trăm giảm giá (`-35%`).

3. **Triệt tiêu hoàn toàn `pdt_price` làm giá gốc (`list_price` Anti-Inflation):**
   - Xóa bỏ toàn bộ fallback gán `tracking.pdt_price` vào `list_price`.
   - `list_price` chỉ được ghi nhận khi biến thể hoặc DOM có giá gạch công khai hợp lệ (`originalPrice`, `listPrice`, `.pdp-price_type_deleted`). Nếu không có, gán `list_price = None` để triệt tiêu hoàn toàn deal ảo và cảnh báo lỗi giá giả.

4. **Tự động nhận diện và ngưng quét sản phẩm đã xóa (404 Delisted Product Detection):**
   - Nhận diện các dấu hiệu xóa sản phẩm: HTTP 404, tiêu đề hoặc nội dung trang chứa "Xin lỗi! Sản phẩm này không còn tồn tại", "không còn tồn tại".
   - Kích hoạt ngoại lệ `ProductDelisted`, tự động cập nhật `active = 0, fail_count = 0`, ghi nhận `stock = 0` vào lịch sử giá và ngưng gửi request quét.

5. **Chuẩn hóa dữ liệu cơ sở dữ liệu hiện hữu (Database Auto-Healing Migration):**
   - Tại `DB._migrate()`:
     - Tự động chuẩn hóa toàn bộ URL hiện có bằng `canonicalize_url` (cắt bỏ hoàn toàn `-s...` và `modelid=...`).
     - Đặt lại `main_variant_id = NULL` cho tất cả sản phẩm người dùng để xóa bỏ việc khóa phân loại cũ.
     - Vô hiệu hóa sản phẩm 4161 (delisted).
     - Dọn dẹp các bản ghi giá gốc ảo (`pdt_price >= 3.500.000₫`) trong bảng `price_history`.

## Hệ quả

- Toàn bộ 22 sản phẩm theo dõi trên Shopee và Lazada đều tự động nhận diện và bám sát mức giá option thấp nhất tuyệt đối còn hàng.
- Triệt tiêu 100% các cảnh báo deal ảo và lỗi giá giả mạo do lạm phát giá gốc từ `pdt_price`.
- Sản phẩm bị xóa (404) được tự động nhận diện và ngưng cào, giải phóng tài nguyên hệ thống.
- Toàn bộ 185 tests trong test suite đều pass 100%.
