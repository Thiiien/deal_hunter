# 18. Tương thích Cụm DOM Giá V2 Lazada & Bộ Chặn Giá Rỗng (Lazada V2 Price DOM & Zero-Price Rejection Guard)

Ngày: 2026-10-21

## Bối cảnh
Khi theo dõi các sản phẩm của sàn Lazada trên Deal Hunter, phát hiện vấn đề giá sản phẩm trên Bảng điều khiển (Dashboard) và lịch sử giá (`price_history`) đều hiển thị `0.0₫` hoặc không hiển thị giá:
1. **Lazada cập nhật cấu trúc DOM trang chi tiết sản phẩm (V2 Price Module):**
   - Lazada đã chuyển toàn bộ khối giá sang cụm DOM `#module_product_price_v2` với các lớp css mới: `.pdp-v2-product-price-content-salePrice`, `[class*='salePrice']`, `.pdp-v2-product-price-content-originalPrice-amount`, `[class*='originalPrice']`.
   - Các selector cũ (`.pdp-price_color_orange`, `.pdp-price`) không còn tồn tại trên các trang sản phẩm này.
   - Dữ liệu có cấu trúc `application/ld+json` của Lazada trên các trang này chỉ cung cấp link và tính trạng còn hàng (`availability`), không còn chứa trường `price` trong `offers`.
2. **Cơ chế fallback mặc định gán giá `0.0₫`:**
   - Trong `PlaywrightAdapter._parse_lazada`, khi không tìm thấy giá qua selector, hàm tự động gán `price = price or 0.0`.
   - Hậu quả: Hệ thống ghi nhận các bản ghi `price = 0.0` vào bảng `price_history`, làm ô nhiễm dữ liệu lịch sử giá, sai lệch thuật toán phát hiện deal thật và khiến dashboard hiển thị `0₫`.
3. **Thiếu nhận diện điều hướng đăng nhập của Lazada:**
   - Khi cookie hết hạn, Lazada điều hướng sang `member.lazada.vn/user/login` hoặc xuất hiện Slider Captcha. Trước đây bộ lọc chỉ kiểm tra `login.lazada.vn`, khiến việc hết hạn phiên không kích hoạt được ngoại lệ `Blocked`.

## Quyết định kiến trúc

1. **Chuẩn hóa bộ bóc tách giá Lazada V2 Price Module:**
   - Bổ sung nhóm selector ưu tiên cho khối giá V2:
     - Giá bán (`salePrice`): `.pdp-v2-product-price-content-salePrice`, `[class*='salePrice']`, `.pdp-mod-product-price-v2`, `.pdp-v2-product-price-content`.
     - Giá gốc niêm yết (`originalPrice`): `.pdp-v2-product-price-content-originalPrice-amount`, `.pdp-v2-product-price-content-originalPrice`, `[class*='originalPrice']`.
   - Bổ sung tầng fallback quét regex tiền tệ toàn trang (`body`) có kiểm tra ký hiệu tiền tệ chuẩn `₫` / `đ`.
   - Tích hợp kiểm tra Captcha (`x5sec`, `bảo vệ tài khoản`, `trượt để xác minh`) ngay trong tầng fallback body.

2. **Thiết lập Bộ chặn ghi nhận giá rỗng (Zero-Price Rejection Guard):**
   - Triệt tiêu hoàn toàn logic gán `price or 0.0` cho sản phẩm còn hàng (`stock is not False`).
   - Nếu không bóc tách được giá và sản phẩm không phải trạng thái hết hàng, lập tức ném ngoại lệ `FetchError(f"Cannot parse price for Lazada item at {url}")`.
   - Chỉ cho phép `price = 0.0` khi và chỉ khi sản phẩm được xác định rõ là hết hàng (`stock is False`).

3. **Bắt bẫy điều hướng phiên hết hạn Lazada (Redirected Session Expiration Trap):**
   - Mở rộng kiểm tra URL điều hướng trong `_fetch_sync`: bổ sung `member.lazada.vn`, `/punish`, `verify/slider`, `acs.lazada.vn`.
   - Khi bị chuyển hướng, lập tức ném `Blocked`, kích hoạt `Scanner` gửi cảnh báo Telegram báo đích danh file `data/cookies_lazada.json` cần nạp lại.

4. **Dọn dẹp dữ liệu lịch sử giá:**
   - Đã xóa sạch 539 bản ghi giá `0.0₫` bị lưu sai trong database `data/deals.db`.
   - Kích hoạt chu kỳ quét tự động nạp lại giá thật cho 29 sản phẩm Lazada đang theo dõi.

## Trạng thái
- Đã kiểm tra thực tế: Tất cả sản phẩm Lazada đã bóc tách chính xác giá thật (ví dụ: Vinamilk 451.170₫, Selsun 86.000₫, Acnes 61.440₫, Belkin 153.000₫...).
- 97/97 automated unit tests pass.
- Đã đồng bộ mã nguồn và vận hành ổn định trên Docker container `deal_hunter-deal-hunter-1`.
