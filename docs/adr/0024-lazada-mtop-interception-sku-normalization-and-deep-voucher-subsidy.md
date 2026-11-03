# 24. Lắng Nghe Phản Hồi Cổng MTOP, Chuẩn Hóa Giá Phân Loại Đa Định Dạng và Bóc Tách Trợ Giá Độc Quyền MOMCLUB / TMALL (Lazada MTOP Gateway Interception, Robust SKU Price Normalization & Deep Member Subsidy Stacking)

Ngày: 2026-10-23

## Bối cảnh
Tiếp tục tối ưu hóa crawler để lấy giá chuẩn xác nhất kèm đầy đủ voucher/trợ giá trên sàn Lazada:
1. **Lỗi chuyển đổi kiểu dữ liệu phân loại hàng (SKU Price Type Error):**
   - Trên Lazada, giá trị `promotionPrice` hoặc `subsidyPrice` trong `skuInfos` có thể trả về dưới dạng chuỗi có ký hiệu tiền tệ (`"357.735 ₫"`), đối tượng từ điển (`{"value": 588550, "text": "588.550 ₫"}`) hoặc số nguyên. Lệnh `float()` trước đây bị vấp lỗi `ValueError` khi gặp ký tự `₫`/`đ`, dẫn đến việc nuốt ngoại lệ và bỏ lỡ mức giá trợ giá của phân loại hàng rẻ nhất.
2. **Cấu trúc dữ liệu SKU và Voucher lồng nhiều nhánh:**
   - Trong phản hồi từ sàn Lazada, `skuInfos` có thể nằm ở `fields.skuInfos`, `fields.skuGalleries.skuInfos`, hoặc `tradeInfo.skuInfos`. Đồng thời danh mục `voucherList` và `promotionList` bị bọc trong nhiều lớp object khiến việc duyệt thông thường bị sót.
3. **Giới hạn cứng 90% chiết khấu voucher làm mất deal giảm 95% - 96.5%:**
   - Hàm `_parse_lazada_voucher_text` trước đây chỉ chấp nhận `1 <= pct <= 90`. Các deal trợ giá xả kho thực tế của người dùng (như Ga đệm 602k giảm còn 21k, chiết khấu tới 96.5%) bị loại bỏ hoàn toàn.
4. **Phụ thuộc vào DOM thay vì dữ liệu mạng gốc:**
   - Lazada tải dữ liệu chi tiết sản phẩm qua cổng API nội bộ Alibaba MTOP Gateway (`mtop.lazada.item.detail.getdetail`, `mtop.lazada.promotion`). Nếu không chặn bắt (intercept) response mạng, crawler phụ thuộc hoàn toàn vào DOM và có thể bị trễ hoặc thiếu dữ liệu khi trang bị obfuscate.

## Quyết định kiến trúc

1. **Lắng nghe phản hồi mạng cổng MTOP trong Playwright:**
   - Cập nhật [PlaywrightAdapter._fetch_sync](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py):
     - Lắng nghe sự kiện `page.on("response")` đối với các URL chứa `mtop.lazada.item.detail`, `mtop.lazada.promotion`, `tradeinfo`.
     - Tự động bóc tách JSON và giải mã JSONP (`mtopjsonp...`) để thu được payload dữ liệu gốc `lazada_payload`.
     - Truyền `lazada_payload` vào `_parse_lazada(page, url, lazada_payload=lazada_payload)` để làm nguồn dữ liệu ưu tiên cao nhất trước khi đọc DOM.

2. **Hàm chuẩn hóa giá đa định dạng `_clean_price_val` và tìm kiếm đệ quy `_find_sku_infos`:**
   - Bổ sung [_clean_price_val](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Tự động trích xuất số thực sạch từ mọi kiểu dữ liệu (dict `value/amount/price/salePrice`, float, int, chuỗi chứa `₫`, `đ`, dấu chấm phân cách hàng nghìn).
   - Bổ sung [_find_sku_infos](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Quét đệ quy toàn bộ cây dữ liệu (`root`, `fields`, `skuGalleries`, `tradeInfo`, `skuBase`) để tìm thấy `skuInfos` bất kể vị trí lồng ghép.

3. **Mở rộng nhận diện voucher Trợ giá Hội viên (`MOMCLUB`, `TMALL_SUBSIDY`) và nâng trần 99%:**
   - Cập nhật [_parse_lazada_voucher_text](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py):
     - Mở rộng trần chiết khấu % từ `90%` lên `99%` để bắt trọn vẹn các deal giảm 91% - 96.5%.
     - Nhận diện `MOMCLUB` và gán tiền tố `MOMCLUB`, phân loại vào tầng trợ giá `platform`.
     - Hỗ trợ số tiền trợ giá lớn hàng triệu đồng (ví dụ: `MOMCLUB Giảm 629.850₫`, `Trợ giá 3.049.265₫`).

4. **Duyệt đệ quy toàn diện voucher từ `window.__moduleData__` và `lazada_payload`:**
   - Hàm duyệt đệ quy Javascript và Python bóc tách mọi phần tử trong `voucherList`, `promotionList`, `bonusVoucher`, `tradeInfo` để nạp vào danh sách `candidate_vouchers`.
   - Trong [_find_best_voucher](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py), cho phép cộng dồn đồng thời `MOMCLUB` / `TMALL_SUBSIDY` (tầng platform) cùng Voucher Shop và Ưu đãi Xu/Coins.

## Trạng thái
- 112/112 automated unit tests pass.
- Đã bổ sung 4 test case chuyên sâu cho MTOP payload, _clean_price_val, _find_sku_infos và trợ giá MOMCLUB 629k + 96% discount.
