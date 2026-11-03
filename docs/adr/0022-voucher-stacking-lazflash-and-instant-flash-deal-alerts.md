# 22. Cộng Dồn Voucher Đa Tầng, Tối Ưu Cào Flash Sale và Cảnh Báo Deal Sâu Tức Thời (Voucher Stacking, Flash Sale Crawl & Instant Flash Deal Alerts)

Ngày: 2026-10-23

## Bối cảnh
Nhằm nâng cao hiệu quả săn deal và đáp ứng yêu cầu tìm kiếm các sản phẩm giảm giá mạnh kèm nhiều voucher:
1. **Hạn chế chỉ lấy 1 voucher duy nhất:**
   - Trên các sàn thương mại điện tử (Shopee, Lazada), người mua thường được hưởng cùng lúc nhiều tầng ưu đãi: Voucher Shop + Voucher Sàn/Tích lũy + Ưu đãi Xu/Hoàn tiền.
   - Thuật toán cũ chỉ giữ lại 1 voucher có số tiền chiết khấu lớn nhất, dẫn đến việc bỏ qua các tầng ưu đãi cộng dồn, làm cho giá thực trả (`final_price`) bị tính cao hơn so với thực tế.
2. **Nguy cơ nhận diện sai voucher cố định:**
   - Biểu thức chính quy trích xuất voucher số tiền cố định trước đây có tiền tố từ khóa tùy chọn, dễ bắt nhầm các thông số kỹ thuật (ví dụ trọng lượng `400g` hoặc cấu hình `128k`) thành mã giảm giá.
3. **Bỏ sót cảnh báo cho deal giảm sâu mới phát hiện (Cold-Start Gap):**
   - Các sản phẩm mới được cào về từ Flash Sale hoặc công cụ tìm kiếm chưa tích lũy đủ 3 điểm lịch sử giá 30 ngày (`INSUFFICIENT_HISTORY`).
   - Dù sản phẩm có mức giảm giá trực tiếp rất sâu (≥ 30% - 50%) kèm nhiều voucher hấp dẫn, hệ thống trước đây không gửi cảnh báo nào đến người dùng vì bị chặn bởi điều kiện lịch sử 30 ngày.

## Quyết định kiến trúc

1. **Cộng Dồn Voucher Đa Tầng (Voucher Stacking):**
   - Phân loại toàn bộ voucher thu thập được thành 3 nhóm không xung đột:
     - `shop`: Voucher do Người Bán / Shop phát hành.
     - `platform`: Voucher do Sàn phát hành (Voucher sàn, Voucher Tích Lũy / Bonus).
     - `coins`: Ưu đãi khấu trừ bằng Xu (Shopee/Lazada Coins) hoặc Hoàn tiền (Cashback).
   - Trong [PlaywrightAdapter._find_best_voucher](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Chọn lọc mã tốt nhất trong từng nhóm và cộng dồn mức chiết khấu (`total_disc = sum(discounts)`), đảm bảo tổng chiết khấu không vượt quá giá bán.
   - Định dạng mã tổng hợp: Nối các mã khả dụng bằng dấu ` + ` (ví dụ `SHOP_50K + BONUS_20K + COIN_10PCT`).

2. **Siết Chặt Quy Tắc Trích Xuất Voucher Cố Định:**
   - Yêu cầu bắt buộc phải có từ khóa khuyến mãi (`giảm`, `voucher`, `hoàn`, `tích lũy`, `ưu đãi`, `coupon`) hoặc ký hiệu tiền tệ rõ ràng (`₫`, `đ`), loại bỏ triệt để việc bắt nhầm thông số kỹ thuật/trọng lượng.

3. **Cảnh Báo Tức Thời Cho Deal Flash Sale Giảm Sâu (Instant Flash Deal Alerts):**
   - Trong [Scanner.discover_flash_sale](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py) và [Scanner.scan_product](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py):
     - Khi một sản phẩm Flash Sale (`source='flash_sale'`) có mức giảm giá sau voucher `(list_price - effective_price) / list_price >= 30%`, rating uy tín (≥ 4.2 hoặc chưa có đánh giá nhưng bán chạy) và còn hàng:
     - Ngay lập tức gửi cảnh báo phát sóng Telegram với tiêu đề `⚡ FLASH DEAL HOT!` kèm thông tin giá gốc gạch ngang, giá sale, chi tiết các tầng voucher đã áp dụng và link mua hàng.
     - Kiểm tra qua [Alerter.should_alert](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/alerter.py) để chống lặp lại thông báo trong chu kỳ cooldown 24 giờ.

## Trạng thái
- Đạt 106/106 automated tests trong toàn bộ test suite.
- Sẵn sàng đồng bộ môi trường container production.
- Mục 3 (Instant Flash Deal Alerts) bị thay thế bởi ADR 0057; hàm cảnh báo flash deal không còn được gọi.
