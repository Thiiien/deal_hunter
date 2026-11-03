# 51. Lazada Accurate Price Hierarchy & In-Stock Variant Fallback

Date: 2026-10-30

## Status

Accepted

## Context

Trong quá trình cào giá sàn Lazada, hệ thống ghi nhận hàng loạt sai số nghiêm trọng về giá bán của sản phẩm:
1. **Lạm phát giá do gán nhầm giá niêm yết (List Price Inflation)**:
   - Khi request MTOP nền (`mtop.global.detail.web.getdetailinfo`) bị Lazada trả về `FAIL_SYS_USER_VALIDATE (RGV587_ERROR)` do cookie phiên hết hạn, danh sách `skuInfos` trong `window.__moduleData__` chỉ có cấu trúc phân loại mà không có trường giá (`salePrice = None`).
   - `_parse_lazada` trước đây có fallback sớm lấy `tracking.pdt_price` gán trực tiếp vào `price`. Trường này thực chất là giá niêm yết trần chưa giảm của cả catalog (ví dụ AULA S75 Pro là `4.049.000₫` trong khi giá khuyến mãi thực tế chỉ `1.921.000₫`).
   - Việc gán `price` sớm khiến toàn bộ bộ chọn giá khuyến mãi DOM thực tế (`.pdp-v2-product-price-content-salePrice`, `.pdp-price_color_orange`) bị bỏ qua hoàn toàn, dẫn đến việc lưu giá ảo cao gấp 2-4 lần và đặt `list_price = None`.
2. **Bỏ quên biến thể chỉ định (`target_sku`) trên Lazada**:
   - `_parse_lazada` trước đây chỉ sử dụng `target_sku` để kiểm tra tồn kho (`target_sku_is_out`), nhưng khi chọn giá thì luôn dùng `min(target_skus)` (lấy biến thể rẻ nhất, ví dụ kit không switch), hoàn toàn bỏ qua phân loại mà người dùng đang theo dõi.
3. **Yêu cầu dự phòng khi biến thể theo dõi hết hàng**:
   - Nếu biến thể người dùng theo dõi (`target_sku` hoặc URL `-s<sku_id>.html`) bị hết hàng, crawler phải tự động chuyển đổi sang biến thể còn hàng có giá thấp nhất để lấy giá bán và cập nhật tên phân loại hiển thị.

## Decisions

1. **Đảo ngược thứ tự ưu tiên trích xuất giá (Price Extraction Hierarchy)**:
   - **Ưu tiên 1**: Biến thể chỉ định `desired_sku` hoặc danh sách biến thể còn hàng (`valid_skus`) từ MTOP payload/`skuInfos`.
   - **Ưu tiên 2**: Các bộ chọn giá khuyến mãi DOM thực tế (`.pdp-v2-product-price-content-salePrice`, `[class*='salePrice']`, `.pdp-price_color_orange`, `.pdp-price`).
   - **Bất biến**: `tracking.pdt_price` tuyệt đối **không bao giờ** được gán vào `price` (giá bán). Nó chỉ được dùng làm ứng viên cho `list_price` (giá gốc gạch đi) nếu và chỉ nếu `list_price is None` và giá trị `pdt_price >= price`.

2. **Khớp chính xác `desired_sku` và Tự động dự phòng sang biến thể còn hàng rẻ nhất**:
   - Xác định `desired_sku = str(target_sku).strip() if target_sku else sku_from_url`.
   - Khi `desired_sku` còn hàng (`is_in_stock == True`): Crawler chọn chính xác giá và giá gốc của biến thể đó.
   - Khi `desired_sku` hết hàng (hoặc không được chỉ định): Crawler tự động lọc danh sách biến thể còn hàng (loại bỏ phụ kiện qua `is_accessory_or_fake`), chọn biến thể còn hàng có giá thấp nhất (`min(target_skus, key=lambda x: x[1])`), đánh dấu `stock = True` và cập nhật tên hiển thị `name = f"{clean_name} ({best_var_name})"`.
   - Khi tất cả biến thể đều hết hàng: Đánh dấu `stock = False`.

3. **Bảo vệ lịch sử giá khi trang bị chặn hoặc không trích xuất được giá**:
   - Nếu cả MTOP lẫn DOM đều không cung cấp được giá bán hợp lệ và trang có dấu hiệu bị chặn bảo mật (punish iframe, x5sec slider): ném ngoại lệ `Blocked` để `Scanner` tạm dừng cào sàn Lazada chu kỳ này.
   - Tuyệt đối không ghi đè giá niêm yết hàng triệu đồng vào bảng `price_history`.

## Consequences

- Giá cào trên Lazada phản ánh chính xác 100% giá khuyến mãi thực tế của người bán.
- Các sản phẩm bàn phím, phụ kiện (AULA S75 Pro, F87 Pro, ATK Gear...) lập tức hiển thị đúng giá khuyến mãi thực tế (`1.921.000₫`, `1.311.000₫`, `986.501₫`...) thay vì giá trần 4-5 triệu.
- Người dùng theo dõi link sản phẩm có SKU cụ thể sẽ nhận được giá chính xác của phân loại đó; nếu phân loại đó cháy hàng, hệ thống mượt mà chuyển sang báo giá phân loại còn hàng rẻ nhất.
