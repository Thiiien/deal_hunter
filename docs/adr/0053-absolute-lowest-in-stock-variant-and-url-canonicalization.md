# 53. Tự động lấy giá phân loại thấp nhất và Chuẩn hóa URL sản phẩm

Date: 2026-11-01

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`)

## Bối cảnh

1. **Khóa cứng biến thể sai lệch theo URL (URL SKU Locking)**:
   - Khi người dùng sao chép liên kết từ trình duyệt hoặc ứng dụng, liên kết thường chứa mã phân loại cụ thể (`-s<sku_id>.html` trên Lazada hoặc `?modelid=<id>` trên Shopee).
   - Trước đây, parser gán `desired_sku = sku_from_url`, khiến hệ thống bị "khóa cứng" vào biến thể ngẫu nhiên có trong URL đó (thường là biến thể đắt tiền hơn hoặc đã hết hàng) thay vì tìm phân loại có giá thấp nhất của sản phẩm.
2. **Bộ lọc phụ kiện làm mất giá thấp nhất của listing**:
   - Thuật toán `is_accessory_or_fake` trước đây tự động loại bỏ các phân loại có giá < 25% giá trung vị/baseline (ví dụ switch lẻ, keycap lẻ, hoặc kit bàn phím giá rẻ) vì coi chúng là "bẫy biến thể".
   - Tuy nhiên, nhu cầu thực tế của người dùng là: bất kể link sản phẩm có bao nhiêu option, hệ thống **bắt buộc phải lấy option có giá thấp nhất tuyệt đối còn hàng** (không lọc bỏ phụ kiện hay sản phẩm chính).
3. **Giá khuyến mãi ẩn trong các ô biến thể (DOM Swatches) trên Lazada**:
   - Trên Lazada, dữ liệu MTOP nền hoặc SSR đôi khi không chứa giá khuyến mãi giảm sâu của tất cả các biến thể nếu chưa click vào ô phân loại trên giao diện (DOM).
   - Cơ chế dò swatch trước đây chỉ kích hoạt khi biến thể ban đầu bị hết hàng (`needs_swatch_probing`), bỏ sót việc phát hiện các biến thể còn hàng khác đang có giá khuyến mãi rẻ hơn.
4. **Hiển thị thiếu tên phân loại đã chọn**:
   - Người dùng không biết hệ thống đang theo dõi và báo giá cho phân loại cụ thể nào trong số các option của link.

## Quyết định kiến trúc

1. **Chuẩn hóa URL (URL Canonicalization) loại bỏ SKU khi thêm và quét:**
   - Xây dựng hàm `canonicalize_url(url)` dùng chung cho toàn bộ hệ thống:
     - **Lazada**: Cắt bỏ hậu tố `-s\d+` trước đuôi `.html` hoặc dấu `?` (chỉ giữ lại mã sản phẩm gốc `...-i<itemid>.html`).
     - **Shopee**: Loại bỏ toàn bộ tham số `modelid=\d+` khỏi query string.
   - Áp dụng chuẩn hóa ngay khi tiếp nhận link tại Web API (`/api/products`), Telegram Bot (`/theodoi`, chat input), và các luồng nạp sản phẩm.
   - Trong parser `_parse_shopee` và `_parse_lazada`, biến thể mục tiêu `desired_sku` không còn tự động khóa vào `sku_from_url` mà chỉ kích hoạt khi có chỉ định tường minh.

2. **Ưu tiên giá thấp nhất tuyệt đối trong số các biến thể còn hàng (Absolute Lowest In-Stock Variant):**
   - Loại bỏ hoàn toàn bộ lọc `is_accessory_or_fake` khi bóc tách giá biến thể.
   - Crawler duyệt qua toàn bộ danh sách phân loại còn hàng (`stock > 0`, `operation.disable == False`):
     - **Shopee**: `lowest_model = min(in_stock_models, key=lambda m: float(m["price"]))`.
     - **Lazada**: `best_sku = min(valid_skus, key=lambda x: x[1])`.
   - Lấy mức giá thấp nhất tuyệt đối tìm được làm giá đại diện cho lần quét.

3. **Chủ động dò biến thể DOM (Proactive Swatch Probing) trên Lazada:**
   - Đối với các sản phẩm đang theo dõi (`is_tracked=True`), nếu listing có từ 2 biến thể trở lên (`len(swatch_info) > 1`), crawler chủ động click qua các ô biến thể trên DOM để đọc giá bán và tình trạng tồn kho thực tế, bảo đảm không bỏ sót giá khuyến mãi ẩn.

4. **Tự động gắn tên biến thể vào tên sản phẩm (Variant Name Suffixing):**
   - Tên biến thể được trích xuất tự động (từ `models[i]["name"]` trên Shopee hoặc `skuBase.properties` trên Lazada) và gắn vào sau tên sản phẩm theo định dạng: `f"{clean_name} ({variant_name})"`.
   - Trước khi gắn, tên gốc được làm sạch bằng Regex `re.sub(r"\s*\([^)]*\)$", "", clean_name)` để ngăn chặn tình trạng cộng dồn nhiều ngoặc đơn qua các chu kỳ quét liên tiếp.

5. **Tự động thích ứng biến thể giữa các chu kỳ quét (Dynamic Variant Fallback):**
   - Không khóa cứng phân loại qua các chu kỳ quét: nếu phân loại rẻ nhất của chu kỳ này bị hết hàng ở chu kỳ sau, crawler tự động chuyển sang phân loại còn hàng rẻ nhất tiếp theo và cập nhật tên hiển thị tương ứng.

## Hệ quả

- Toàn bộ link sản phẩm có nhiều phân loại (Shopee & Lazada) đều tự động nhận diện và theo dõi chính xác mức giá thấp nhất tuyệt đối còn hàng.
- Tên sản phẩm hiển thị trên Dashboard và thông báo Telegram luôn thể hiện rõ tên phân loại tương ứng (ví dụ: `Bàn phím Aula F75 Pro (Pack 10 Switch lẻ)`).
- Người dùng dán link chứa SKU nào thì hệ thống cũng tự động chuẩn hóa về link gốc và săn đúng biến thể rẻ nhất.
