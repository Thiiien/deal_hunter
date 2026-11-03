# 45. Tab Chuyên Biệt Lazada TMALL Trợ Giá và Bộ Cào Tinh Gọn Độc Lập (Dedicated Lazada TMALL Tab & Isolated Streamlined Crawler)

Ngày: 2026-10-29

## Bối cảnh
Người dùng muốn theo dõi và gom nhóm các sản phẩm từ chuyên trang **Lazada TMALL Trợ Giá / Choice** vào một tab riêng biệt trên Web Dashboard, với:
1. Logic cào dữ liệu và hiển thị tinh gọn tương tự tab **Sản phẩm theo dõi**:
   - Kiểm tra trạng thái tồn kho nhị phân (`🟢 Còn hàng` / `🔴 Hết hàng`).
   - Bỏ qua hoàn toàn việc trích xuất và chờ đợi `Rating` (để tối ưu hóa tốc độ cào).
   - Tự động bóc tách các mã voucher trợ giá nền tảng (`TMALL_SUBSIDY`, `MOMCLUB`) và chọn phân loại hàng (SKU) rẻ nhất còn hàng.
2. Giao diện bảng hiển thị tinh gọn 6 cột (bỏ cột Rating và cột Giá mong muốn).
3. Độc lập tài nguyên và lịch quét trong Scheduler (có toggle bật/tắt và chu kỳ riêng `tmall_interval_min`, mặc định 120 phút).

## Quyết định kiến trúc

1. **Phân loại nguồn dữ liệu trong Database (`source='lazada_tmall'`):**
   - Các sản phẩm được phát hiện từ chuyên trang TMALL sẽ được lưu trữ với `source='lazada_tmall'` trong bảng `products`.
   - Cơ chế này giúp phân tách hoàn toàn với `source='user'` (tab Sản phẩm theo dõi) và `source='flash_sale'` (tab Siêu Sale & Giảm sâu).

2. **Bộ cào dữ liệu chuyên biệt (`crawl_tmall_subsidy`):**
   - Bổ sung phương thức `crawl_tmall_subsidy(limit)` vào [BaseAdapter](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/base.py) và các adapter tương ứng.
   - [PlaywrightAdapter](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py): Cào danh mục catalog TMALL Trợ Giá (`https://www.lazada.vn/catalog/?q=tmall+tr%E1%BB%A3+gi%C3%A1&sort=pricedesc`), trích xuất các thẻ sản phẩm kèm gắn nhãn `[TMALL TRỢ GIÁ]`, đặt `rating=None` và `stock=True` (nhị phân).
   - Khi quét cập nhật từng sản phẩm (`scan_product`), hệ thống coi `source='lazada_tmall'` là đối tượng theo dõi tinh gọn (`is_tracked=True`), không bóc tách rating.

3. **Lịch quét Scheduler & Toggle độc lập:**
   - Cấu hình bổ sung: `tmall_interval_min` (mặc định 120 phút) và `tmall_scan_enabled` (mặc định True).
   - Cho phép điều chỉnh trong file `.env`, lưu cài đặt động qua SQLite `settings` và bảng điều khiển Cài Đặt trên Dashboard.
   - Cung cấp API thủ công `POST /api/crawl-tmall` để người dùng có thể kích hoạt cào TMALL bất kỳ lúc nào.

4. **Giao diện Tab "Lazada TMALL" trên Web Dashboard:**
   - Nút Tab mới: `🏷️ Lazada TMALL` kèm bộ đếm số lượng deal TMALL đang có.
   - Bảng hiển thị 6 cột:
     1. `Checkbox` (chọn nhiều để xóa hàng loạt)
     2. `Sản phẩm` (Tên kèm badge TMALL, danh mục)
     3. `Giá hiện tại` (kèm giá sau voucher trợ giá)
     4. `Giảm thật` (% giảm so với giá niêm yết)
     5. `Trạng thái` (huy hiệu trực quan `🟢 Còn hàng` hoặc `🔴 Hết hàng`)
     6. `Thao tác` (Xem link ↗, Xóa 🗑️)

## Trạng thái
- Đã được thống nhất qua quy trình `/grill-with-docs`.
- Triển khai code vào hệ thống.
