# 21. Bóc Tách Voucher Đa Nguồn, Phát Hiện 404 Nhanh và Cảnh Báo Giảm Giá Sản Phẩm Theo Dõi (Deep Voucher Extraction, Fast 404 & Tracked Price-Drop Alerts)

Ngày: 2026-10-22

## Bối cảnh
Nhằm tiếp tục nâng cao hiệu năng cào dữ liệu, độ chính xác của voucher và trải nghiệm theo dõi liên kết sản phẩm của người dùng:
1. **Thiếu sót trong thuật toán phát hiện deal thật khi áp dụng voucher:**
   - Trước đây, `detect()` trong `Scanner` chỉ nhận giá niêm yết thô (`snapshot.price`). Khi một sản phẩm có mã giảm giá lớn (ví dụ giảm 30%-50% qua voucher shop), `final_price` giảm sâu nhưng `detect()` lại so sánh giá thô với lịch sử giá, dẫn đến việc bỏ sót các deal giảm giá sâu thông qua voucher.
2. **Hạn chế trong cảnh báo sản phẩm theo dõi (`source='user'`):**
   - Người dùng chủ động thêm liên kết cần được thông báo ngay khi giá giảm hoặc khi shop phát hành voucher mới.
   - Trước đây, nếu sản phẩm mới thêm chưa đủ 3 điểm lịch sử 30 ngày (`INSUFFICIENT_HISTORY`) và chưa đặt `target_price`, hệ thống sẽ im lặng ngay cả khi sản phẩm giảm giá mạnh.
3. **Lãng phí thời gian cào đối với sản phẩm đã bị xóa hoặc ngừng bán (404 / Delisted):**
   - Khi một liên kết sản phẩm bị shop gỡ hoặc sàn khóa, trang web hiển thị thông báo lỗi 404 hoặc chuyển hướng trang chủ. Trình duyệt Playwright trước đây phải đợi hết 30 giây timeout cho mỗi link chết, gây nghẽn toàn bộ hàng đợi quét định kỳ.
4. **Voucher hiển thị đa dạng chưa được bóc tách hết:**
   - Trên Shopee, nếu API `pdp/get_pc` không trả về voucher thì bộ bóc tách bỏ cuộc và không tìm kiếm trong DOM.
   - Trên Lazada, các ưu đãi bằng Xu (`Lazada Coins`) hoặc `Hoàn tiền MAX` chưa được trích xuất vào giá thực trả.

## Quyết định kiến trúc

1. **Đưa Giá Thực Trả Sau Voucher (`final_price`) vào Phát Hiện Deal Thật:**
   - Cập nhật [Scanner.scan_product](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py): Truyền `effective_price = snapshot.final_price or snapshot.price` vào hàm `detect()`.
   - Cập nhật [DB.get_price_history_30d](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py): Truy vấn `SELECT COALESCE(final_price, price) FROM price_history` để lịch sử giá phản ánh đúng số tiền thực tế người mua chi trả.

2. **Cảnh Báo Giảm Giá & Voucher Mới Tức Thời Cho Sản Phẩm Người Dùng Theo Dõi:**
   - Khi quét sản phẩm có `source='user'`, nếu `effective_price < prev_price` (giảm ≥ 5.000₫ hoặc ≥ 3%):
     - Gửi cảnh báo riêng tới quản trị viên Telegram qua [Notifier.alert_admin](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/notifier.py) với tiêu đề `📉 GIẢM GIÁ SẢN PHẨM THEO DÕI!`.
     - Hiển thị rõ giá cũ, giá mới, số tiền tiết kiệm và mã voucher mới xuất hiện.

3. **Phát Hiện Nhanh Sản Phẩm Bị Xóa / Ngừng Bán (Fast Delisted & 404 Detection):**
   - Bổ sung ngoại lệ [ProductDelisted](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/base.py) kế thừa từ `FetchError`.
   - Trong [PlaywrightAdapter._fetch_sync](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Ngay sau `page.goto`, kiểm tra nhanh các mẫu tín hiệu 404 ("sản phẩm không tồn tại", "đã bị xóa", "ngừng bán", hoặc redirect về trang chủ sàn). Nếu phát hiện, lập tức ném `ProductDelisted` trong vòng 1 giây thay vì chờ 30 giây timeout.
   - Trong `Scanner.scan_product`: Tự động cập nhật `active = 0` để loại bỏ link chết khỏi các chu kỳ quét sau và gửi thông báo cảnh báo cho admin.

4. **Bóc Tách Voucher Đa Nguồn Mở Rộng:**
   - Trên Shopee: Bổ sung fallback trích xuất voucher trực tiếp từ DOM (`.voucher-ticket`, `[class*="voucher"]`, etc.) khi API `pdp/get_pc` bị ẩn.
   - Trên Lazada: Đọc thêm voucher từ dữ liệu cấu trúc `window.__moduleData__` và mở rộng regex bóc tách nhãn Xu (`COIN_xPCT`), Hoàn tiền MAX (`CASHBACK_xPCT`), và Tích lũy.

## Trạng thái
- 104/104 automated unit tests pass.
- Đã đồng bộ mã nguồn vào Docker container `deal_hunter-deal-hunter-1` và kiểm tra hoạt động trực tiếp.
- Mục 2 (cảnh báo giảm giá sản phẩm theo dõi) đang tắt theo ADR 0062.
