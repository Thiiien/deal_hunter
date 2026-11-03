# 23. Cào Deal Kênh TMALL Trợ Giá, Tối Ưu Bóc Tách Phân Loại Hàng và Cảnh Báo Deal Siêu Trợ Giá (TMALL Subsidy Crawling, SKU Price Refinement & Super Subsidy Alerts)

Ngày: 2026-10-23

## Bối cảnh
Người dùng phản ánh việc hệ thống quét liên tục nhưng không phát hiện được các deal giảm giá sâu đột biến (giảm từ 85% đến 96%) trên sàn Lazada, ví dụ:
- Bàn phím cơ Akko Gem 01 nhôm VIA: giá niêm yết 3.407.000₫ thanh toán chỉ còn 357.735₫ (~giảm 90%).
- RAM Laptop Lenovo DDR4 16GB: niêm yết 5.257.000₫ thanh toán chỉ còn 588.550₫ (~giảm 89%).
- Bộ ga đệm giữ lạnh: niêm yết 602.000₫ thanh toán chỉ còn 21.001₫ (~giảm 96.5%).

Qua rà soát chuyên sâu mã nguồn:
1. **Lỗ hổng bóc tách phân loại hàng (SKU) trên Lazada:**
   - Trong `PlaywrightAdapter._parse_lazada`, khi đọc `skuInfos` từ `window.__moduleData__`, vòng lặp ngắt (`break`) ngay tại SKU đầu tiên. Nếu SKU đầu tiên là phân loại giá cao gốc (3.4M), hệ thống ghi nhận mức giá đó mà bỏ qua phân loại được trợ giá (357k).
2. **Thiếu nguồn cào kênh TMALL Trợ Giá & Choice:**
   - Các deal khủng trên xuất phát từ kênh trợ giá quốc tế / thương hiệu chính hãng (`TMALL TRỢ GIÁ`, `Choice`). Hệ thống trước đây chỉ quét trang Flash Sale mặc định (`/flash-sale/`), hoàn toàn không truy cập danh mục hàng trợ giá của Lazada.
3. **Chưa có định dạng cảnh báo riêng cho Deal Giảm Giá Cực Đoan:**
   - Mức giảm 70% - 95% là các đợt trợ giá ngân sách lớn của sàn/thương hiệu, cần được gắn nhãn khẩn cấp `🚨 DEAL SIÊU TRỢ GIÁ` để thu hút sự chú ý của người mua.

## Quyết định kiến trúc

1. **Duyệt Toàn Bộ Phân Loại Hàng (SKU) Để Chọn Giá Thấp Nhất Còn Hàng:**
   - Cập nhật [PlaywrightAdapter._parse_lazada](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py):
     - Duyệt qua toàn bộ danh sách `skuInfos` trong `window.__moduleData__`.
     - Kiểm tra trường `promotionPrice`, `subsidyPrice`, `cartPrice`, `salePrice`, `price`.
     - Lọc các SKU còn tồn kho (`stock > 0`) và chọn SKU có mức giá rẻ nhất.
     - Lấy giá gốc (`originalPrice`/`listPrice`) làm `list_price` để đo lường chính xác tỷ lệ giảm giá thật.

2. **Tự Động Nhận Diện Nhãn "TMALL TRỢ GIÁ" & "MOMCLUB":**
   - Kiểm tra các phần tử huy hiệu DOM (`[class*="badge"]`, `[class*="tmall"]`, `[class*="subsidy"]`) và từ khóa trong tiêu đề.
   - Tự động gắn tiền tố `[TMALL TRỢ GIÁ]` vào tên sản phẩm khi phát hiện.
   - Mở rộng [_parse_lazada_voucher_text](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py) để nhận diện các voucher mang nhãn `trợ giá`, `subsidy`, `tmall` thành mã tầng sàn `TMALL_SUBSIDY`.

3. **Mở Rộng Cào Danh Mục TMALL Trợ Giá Khi Quét Flash Sale:**
   - Trong [PlaywrightAdapter._crawl_lazada_flash_sale_sync](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Tự động nạp thêm danh sách sản phẩm từ catalog `https://www.lazada.vn/catalog/?q=tmall+tr%E1%BB%A3+gi%C3%A1&sort=pricedesc` nếu số lượng deal flash sale chưa đạt giới hạn, giúp tự động bao quát các sản phẩm trợ giá mạnh.

4. **Cảnh Báo Phát Sóng Khẩn Cấp "🚨 DEAL SIÊU TRỢ GIÁ":**
   - Trong [Scanner._send_flash_deal_alert](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py):
     - Khi mức giảm giá `≥ 70%` hoặc sản phẩm có nhãn `[TMALL TRỢ GIÁ]`, thông báo được gắn tiêu đề khẩn cấp `🚨 DEAL SIÊU TRỢ GIÁ!` kèm giá niêm yết gạch ngang và giá thực trả sau trợ giá.

## Trạng thái
- 108/108 automated unit tests pass.

Bị thay thế một phần: URL cào TMALL theo ADR 0046; cảnh báo siêu trợ giá tắt theo ADR 0057; phân hệ TMALL tắt theo ADR 0055.
- Đã đồng bộ mã nguồn vào Docker container `deal_hunter-deal-hunter-1`.
