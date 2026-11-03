# 13. Cào Deal Flash Sale Lazada và Siêu Sale đa sàn (Lazada Flash Sale Crawler & Multi-Platform Mega Sale)

Ngày: 2026-10-20

## Bối cảnh
Trước đây hệ thống đã có tính năng cào Flash Sale cho Shopee (`_crawl_flash_sale_sync`), tự động thu thập các mặt hàng giảm giá sâu trong các khung giờ vàng và đợt Mega Sale.
Khi mở rộng sang Lazada, người dùng cũng cần săn các deal chớp nhoáng (Lazada Flash Sale) từ trang `https://www.lazada.vn/flash-sale/` để:
1. **Thu thập tự động các deal Flash Sale của Lazada:** Bóc tách tên sản phẩm, giá flash sale, giá gốc niêm yết, tỷ lệ giảm giá, và thanh tiến độ bán hàng.
2. **Loại bỏ deal hết hàng:** Tự động lọc bỏ các sản phẩm đã bán hết 100% (sold out) trên trang Flash Sale, đảm bảo người dùng chỉ theo dõi các deal thực sự mua được.
3. **Cào Siêu Sale đa sàn linh hoạt:** Cho phép người dùng lựa chọn cào riêng Flash Sale Shopee, Flash Sale Lazada, hoặc cào đồng thời cả hai sàn từ Dashboard (`POST /api/crawl-megasale`).
4. **Quản lý rủi ro Captcha x5sec:** Bắt ngoại lệ an toàn khi gặp trang chống bot `/punish` hoặc slider captcha của Alibaba mà không làm crash luồng quét nền, thông báo rõ ràng cho quản trị viên.

## Quyết định kiến trúc

1. **Bộ cào Flash Sale Lazada (`PlaywrightAdapter.crawl_lazada_flash_sale`):**
   - Truy cập URL `https://www.lazada.vn/flash-sale/` với referer `https://www.lazada.vn/` và cookies nạp sẵn từ `data/cookies_lazada.json`.
   - Lắng nghe response network từ các API MTop hoặc trích xuất DOM từ các thẻ sản phẩm Flash Sale (`.item-card`, thẻ link `a[href*='/products/']`).
   - Lọc bỏ ngay các sản phẩm có nhãn hoặc tiến độ bán 100% ("Đã bán hết" / `sold_out`).
   - Chuẩn hóa dữ liệu trả về thành `Snapshot` với `platform = "lazada"` và `source = "flash_sale"`.

2. **Mở rộng `Scanner.discover_flash_sale` hỗ trợ đa sàn:**
   - Nhận tham số `platform: str = "all"` (`"shopee"`, `"lazada"` hoặc `"all"`).
   - Tự động gọi bộ cào tương ứng từ adapter.
   - Lưu trữ `Snapshot` vào cơ sở dữ liệu SQLite, tự động gán nhãn chiến dịch khuyến mãi đang hoạt động (ví dụ: "Flash Sale" hoặc "Mega Sale").
   - Kế thừa trọn vẹn bộ lọc giá và phát hiện Deal Thật của hệ thống.

3. **Cập nhật Web API và Giao diện Dashboard:**
   - Endpoint `POST /api/crawl-megasale` nhận payload `{"platform": "shopee" | "lazada" | "all", "limit": 25}`.
   - Tab **🔥 Siêu Sale & Giảm sâu** trên Dashboard:
     - Bổ sung nhóm nút điều khiển: `⚡ Cào Shopee`, `⚡ Cào Lazada`, và `🚀 Cào Tất Cả Sàn`.
     - Hiển thị badge nhận diện sàn (`🟠 Shopee` / `🔵 Lazada`) trên danh sách deal Siêu Sale.
     - Hiển thị thông báo trạng thái và thời gian hoàn tất rõ ràng.

## Trạng thái
Đã thống nhất qua quy trình `/grill-with-docs` và phê duyệt triển khai.
