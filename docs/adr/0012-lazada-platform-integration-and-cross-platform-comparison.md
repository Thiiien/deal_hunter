# 12. Tích hợp sàn Lazada và so sánh giá liên sàn (Lazada Integration & Cross-Platform Comparison)

Ngày: 2026-10-20

## Bối cảnh
Người dùng săn deal thường xuyên so sánh giá giữa hai sàn thương mại điện tử lớn nhất Việt Nam là **Shopee** và **Lazada**. Trước đây hệ thống chủ yếu tập trung vào Shopee.
Để hoàn thiện hệ thống theo dõi giá đa sàn thực thụ, cần:
1. **Giao diện Dashboard trực quan:** Phân biệt rõ ràng sản phẩm thuộc Shopee hay Lazada thông qua huy hiệu màu thương hiệu (Shopee cam, Lazada xanh tím), hỗ trợ lọc riêng theo từng sàn và thống kê số lượng sản phẩm mỗi sàn.
2. **Quản lý phiên độc lập:** Lazada áp dụng hệ thống bảo mật x5sec và captcha riêng của Alibaba. Cần quản lý cookie tách biệt (`data/cookies.json` cho Shopee và `data/cookies_lazada.json` cho Lazada) để sự cố phiên của một sàn không làm gián đoạn sàn còn lại.
3. **Bộ bóc tách trang sản phẩm Lazada (`_parse_lazada`):** Thu thập chính xác tên, giá bán, giá niêm yết, tồn kho, rating, lượt bán và voucher của shop từ các link `lazada.vn`.
4. **So sánh giá liên sàn:** Đối chiếu giá sản phẩm giữa cả Shopee và Lazada để tìm ra sàn có mức giá thực tế thấp nhất sau voucher.

## Quyết định kiến trúc

1. **Giao diện Dashboard & Bộ lọc đa sàn:**
   - Thêm bộ lọc sàn: `Tất cả` | `Shopee 🟠` | `Lazada 🔵` trên thanh công cụ.
   - Hiển thị huy hiệu sàn với màu thương hiệu đặc trưng:
     - Shopee: `#ee4d2d` (Cam)
     - Lazada: `#0f146d` (Xanh tím đặc trưng)
   - Thẻ thống kê (Stats): Bổ sung số lượng sản phẩm theo dõi phân bổ theo Shopee và Lazada.
   - Thêm nút "📋 Cookies Lazada" trên Header để nạp cookie độc lập.

2. **Quản lý phiên và nạp Cookie (`login.py` & `web.py`):**
   - Hỗ trợ lưu và đọc cookies riêng cho Lazada tại `data/cookies_lazada.json`.
   - Endpoint `GET /api/session` trả về trạng thái hiệu lực phiên của cả hai sàn: `{"shopee": {...}, "lazada": {...}}`.
   - Endpoint `POST /api/cookies` nhận tham số `platform: "shopee" | "lazada"`.
   - Khi khởi động `PlaywrightAdapter`, tự động nạp cookies tương ứng cho cả hai domain `.shopee.vn` và `.lazada.vn`.

3. **Bộ cào dữ liệu Lazada (`PlaywrightAdapter._parse_lazada`):**
   - Khi `fetch(url)` phát hiện domain `lazada.vn`:
     - Chuyển hướng xử lý sang `_parse_lazada(page, url)`.
     - Trích xuất dữ liệu từ các biến JSON nhúng của Lazada (`__moduleData__`, `appContext`) hoặc DOM selectors chuẩn (`.pdp-mod-product-badge-title`, `.pdp-price`, `.pdp-vouchers`, `.pdp-review-summary`).
     - Phát hiện trạng thái hết hàng: các nút mua bị vô hiệu hóa hoặc xuất hiện nhãn "Hết hàng".
     - Trích xuất mã voucher shop từ khối ưu đãi Lazada.

4. **So sánh giá liên sàn (`compare_shops`):**
   - Mở rộng chức năng so giá chéo để tìm kiếm cả trên Shopee và Lazada.
   - Trả về thông tin sàn rẻ nhất kèm link và mức tiết kiệm.

## Trạng thái
Đã thống nhất qua quy trình `/grill-with-docs` và phê duyệt triển khai.
