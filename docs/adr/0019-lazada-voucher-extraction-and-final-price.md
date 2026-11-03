# 19. Tối ưu Bóc tách Mã giảm giá và Tính giá Thực trả Lazada (Lazada Voucher Extraction & Net Effective Price)

Ngày: 2026-10-21

## Bối cảnh
Sau khi khắc phục thành công việc bóc tách giá bán từ cụm DOM V2 (`#module_product_price_v2`), phát hiện các chương trình ưu đãi, mã giảm giá của shop/sàn Lazada chưa được bóc tách triệt để:
1. **Lazada hiển thị mã giảm giá dưới dạng Promotion Tags (`#module_promotion_tags`):**
   - Thay vì các class voucher truyền thống, Lazada sử dụng cụm ưu đãi `.pdp-mod-promotion-tags-v2`, `.promotion-tag-item-v2`, `.tag-name` hiển thị các nhãn như `25% Giảm`, `Giảm 50k đơn từ 300k`, `Ưu đãi: | 10% Giảm`.
   - Nhiều shop đưa thẳng thông tin voucher vào tiêu đề sản phẩm dạng `[VOUCHER 25%]`, `[GIẢM 50K]`.
   - Bộ bóc tách cũ chỉ tìm kiếm class `.voucher-tag, .pdp-mod-voucher` nên bỏ sót toàn bộ các nhãn ưu đãi này.
2. **Nguy cơ lỗi định dạng số tiền VND trong hàm tính voucher dùng chung (`_find_best_voucher`):**
   - Hàm `_find_best_voucher` kế thừa từ Shopee có cơ chế tự động chia `100.000` cho các số liệu `> 100.000` (do Shopee API lưu giá theo đơn vị cents nhân 100.000).
   - Khi áp dụng cho số tiền VND thực tế của Lazada (ví dụ: đơn tối thiểu `300.000₫`), phép chia này khiến `300.000₫` bị hiểu nhầm thành `3.0₫`, dẫn đến tính sai điều kiện đơn tối thiểu.
3. **Lỗi JavaScript tiềm ẩn khi duyệt DOM:**
   - Việc gọi `e.innerText.trim()` trực tiếp trên các node không có thuộc tính `innerText` (như SVG/text node) gây ngoại lệ `TypeError`, làm gián đoạn toàn bộ quá trình bóc tách voucher.

## Quyết định kiến trúc

1. **Mở rộng nguồn bóc tách mã giảm giá và ưu đãi Lazada:**
   - Bổ sung nhóm selector toàn diện: `#module_promotion_tags`, `[class*="promotion-tag"]`, `.tag-name`, `[class*="voucher-ticket"]`, `[class*="voucher-item"]`, `[class*="voucher"]`, `[class*="coupon"]`, `[class*="discount-tag"]`, `.pdp-mod-voucher`.
   - Bóc tách đồng thời từ cả nhãn voucher trong tiêu đề sản phẩm (`name`) và tiêu đề trang (`page.title()`).
   - Xử lý an toàn chuỗi văn bản với `(e.innerText || e.textContent || '').trim()`.

2. **Chuẩn hóa bộ phân tích ưu đãi chuyên dụng (`_parse_lazada_voucher_text`):**
   - Tự động bóc tách:
     - Giảm theo phần trăm: `(\d{1,2})%` (ví dụ: `25% Giảm` -> 25%).
     - Giảm theo số tiền cố định: `Giảm 50k`, `30.000₫`.
     - Đơn hàng tối thiểu (`min_spend`): `đơn từ 300k`, `mua từ 199.000₫`, `đơn tối thiểu 200k`.
     - Hạn mức trần chiết khấu (`discount_cap`): `tối đa 30k`.
   - Tự động bỏ qua các chương trình quà tặng kèm ("Quà tặng khi mua...") không phải voucher giảm giá tiền mặt.

3. **Bảo vệ tính toàn vẹn số tiền VND trong `_find_best_voucher`:**
   - Nhận diện các voucher VND từ Lazada (`is_vnd=True` hoặc mã có tiền tố `LAZADA_`, `TITLE_`).
   - Giữ nguyên số tiền thực tế (VND) mà không chia 100.000.
   - So sánh tất cả voucher thỏa mãn điều kiện `price >= min_spend` và tự động chọn ra voucher mang lại mức chiết khấu cao nhất (`best_discount`).
   - Tính toán giá sau áp mã chuẩn xác: `final_price = max(0.0, round(price - voucher_discount, 2))`.

## Trạng thái
- Đã kiểm tra thực tế: Sản phẩm *[VOUCHER 25%] Thùng 30 Gói Bún Riêu Cua VIFON* đã bóc tách chính xác:
  - Giá bán: **52.897₫**
  - Voucher: `LAZADA_25PCT` (-13.224,25₫)
  - Giá thực trả sau ưu đãi: **39.672,75₫**
- 99/99 automated unit tests pass.
- Đã triển khai và đồng bộ vào container Docker `deal_hunter-deal-hunter-1`.
