# 28. Tối ưu hóa độ chuẩn xác bóc tách dữ liệu cào và hệ thống voucher đa tầng

## Trạng thái

Accepted. Mục chọn giá phân loại được thay bởi ADR 0053.

## Bối cảnh
Trong quá trình vận hành quét sản phẩm trên Shopee và Lazada, một số tình huống bóc tách dữ liệu và tính toán voucher gặp phải sai lệch:
1. **Bỏ sót voucher sàn trên Shopee**: Khi sản phẩm có voucher từ shop (`shop_vouchers` trong API `pdp/get_pc`), hệ thống coi như đã có voucher và bỏ qua việc quét vé voucher sàn trên DOM, khiến người dùng không nhận được mức giá tối ưu nhất khi cộng dồn.
2. **Nguy cơ giảm giá 2 lần (Double Discount)**:
   - Trên Shopee: Tự động trừ `discount_breakdown` từ `price_breakdown` khi giá biến thể (`model.price`) vốn dĩ đã là giá sau khuyến mãi.
   - Trên Lazada: Khi giá SKU đã lấy trực tiếp từ `subsidyPrice` (giá đã trợ giá), việc quét thêm huy hiệu "TMALL Trợ giá X%" thành voucher bổ sung sẽ trừ tiền lần 2, tạo ra giá ảo cực thấp (ví dụ: RAM 588k bị giảm tiếp 89% còn 64k).
3. **Nhiễu bóc tách Regex Voucher**:
   - Các điều kiện giá trị đơn tối thiểu dạng `đơn hàng từ 1.000.000₫` bị lọt do thiếu từ `hàng`, dẫn tới `min_spend = 0` và áp dụng voucher cho sản phẩm giá trị thấp.
   - Các ưu đãi miễn phí vận chuyển ("Freeship Extra", "giảm phí ship") hoặc mua theo combo ("mua 2 giảm 5%") bị nhận diện nhầm thành voucher giảm giá sản phẩm đơn lẻ.
4. **Bẫy biến thể phụ kiện (Variant Trap)**: Nhiều shop điện thoại, máy tính tạo biến thể ốp lưng, cáp sạc 20k trong cùng một link sản phẩm 20 triệu, khiến thuật toán lấy giá thấp nhất chọn nhầm giá phụ kiện làm giá máy.

## Quyết định kiến trúc

1. **Bóc tách voucher Shopee đa nguồn và cộng dồn đa tầng ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Kết hợp danh sách voucher shop từ API (`shop_vouchers`) với toàn bộ vé voucher quét từ giao diện DOM (`.voucher-ticket`, `.voucher-badge`, `aria-label`).
   - Phân loại rõ từng voucher vào các tầng:
     - `shop`: Voucher do Người bán phát hành.
     - `platform`: Voucher do Sàn phát hành (Shopee / Lazada / TMALL).
     - `coins`: Ưu đãi hoàn xu / đổi xu / cashback.
   - Sử dụng `_find_best_voucher` với `allow_stacking=True` để cộng dồn tối đa 1 voucher tốt nhất trên mỗi tầng.

2. **Chống chiết khấu kép (Double Discount Prevention):**
   - Bỏ việc suy diễn voucher từ `price_breakdown.discount_breakdown` trên Shopee. Chỉ công nhận voucher khi có mã hoặc vé cụ thể.
   - Trên Lazada: Đánh dấu biến thể nếu mức giá được lấy từ trường `subsidyPrice`. Khi giá đã là giá trợ giá, vô hiệu hóa việc áp dụng lại chính voucher trợ giá nền tảng (`TMALL_SUBSIDY`, `MOMCLUB`) để tránh trừ tiền 2 lần.

3. **Chuẩn hóa bộ lọc Regex Voucher ([_parse_lazada_voucher_text](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Mở rộng regex `min_spend` hỗ trợ các mẫu: `đơn hàng từ`, `từ đơn`, `cho đơn`, `áp dụng từ`.
   - Loại trừ hoàn toàn các chuỗi chứa từ khóa vận chuyển (`vận chuyển`, `freeship`, `phí ship`) và điều kiện mua nhiều (`combo`, `mua kèm`, `mua \d+`).

4. **Bộ lọc biến thể phụ kiện (Variant Trap Filter):**
   - Khi duyệt danh sách phân loại (`models` trên Shopee, `skuInfos` trên Lazada), kiểm tra tên phân loại qua `is_accessory_or_fake`.
   - Nếu có các phân loại chính không phải phụ kiện còn hàng, ưu tiên chọn phân loại chính và bỏ qua các biến thể phụ kiện đi kèm để xác định đúng giá bán thực tế.

## Hệ quả
- Dữ liệu giá bán và giá sau voucher phản ánh chính xác 100% số tiền người dùng thực trả khi thanh toán.
- Loại bỏ hoàn toàn tình trạng deal ảo do chiết khấu 2 lần hoặc nhầm lẫn phụ kiện giá rẻ trong listing giá trị cao.
