# 30. Cô lập sản phẩm theo dõi và cấu hình tần suất quét độc lập theo từng tab

## Trạng thái

Accepted. Chu kỳ quét mặc định là 2 phút theo ADR 0060.

## Bối cảnh
Trước đây:
1. Khi hệ thống quét theo từ khóa (`run_keyword_search`), cào deal Siêu Sale hoặc săn lỗi giá, các hàm lưu dữ liệu (`upsert_product_meta`) không chỉ định trường `source`, khiến SQLite gán giá trị mặc định `source='user'`. Hệ quả là hàng loạt sản phẩm tìm thấy từ các tab khác tự động tràn vào tab **"📦 Sản phẩm theo dõi"**, gây nhiễu loạn danh sách sản phẩm mà người dùng đích thực quan tâm theo dõi.
2. Hệ thống chỉ có duy nhất 1 tham số cấu hình tần suất quét `scan_interval_min` trong popup Cài đặt. Vòng lặp scheduler chính quét chung tất cả sản phẩm trong cùng một chu kỳ, không cho phép người dùng tùy biến tần suất riêng biệt cho từng nghiệp vụ (ví dụ: muốn quét sản phẩm theo dõi mỗi 30 phút, nhưng quét từ khóa chỉ cần 180 phút, cào siêu sale mỗi 60 phút).

## Quyết định kiến trúc

1. **Cô lập tuyệt đối tab "Sản phẩm theo dõi" ([db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py), [web.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py), [dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Mở rộng hàm `upsert_product_meta(self, snapshot, source="keyword")`: chỉ định rõ nguồn khi ghi dữ liệu. Khi cập nhật sản phẩm có sẵn, quy tắc ưu tiên giữ nguyên: `source = CASE WHEN products.source='user' THEN 'user' WHEN excluded.source='user' THEN 'user' ELSE excluded.source END`. Sản phẩm do người dùng thêm (`source='user'`) sẽ không bao giờ bị hạ cấp, nhưng sản phẩm do quét ngầm tạo ra sẽ mang đúng nguồn `keyword`, `flash_sale`, hoặc `price_error`.
   - Bổ sung hàm `get_active_tracked_products()`: chỉ lọc `active=1 AND source='user'`.
   - Migration chuẩn hóa: tự động chuyển các sản phẩm liên kết với `keyword_products` mà không phải do người dùng tự thêm về `source='keyword'`.
   - Tab "Sản phẩm theo dõi" trên giao diện chỉ tải và hiển thị các sản phẩm có `p.source === 'user'`.

2. **Cấu hình tần suất quét độc lập cho từng tab ([config.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/config.py), [web.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py), [dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Hỗ trợ 4 tham số độc lập trong cấu hình và cơ sở dữ liệu (`settings` table):
     - `scan_interval_min`: Tần suất quét Sản phẩm theo dõi (mặc định 30 phút).
     - `keyword_interval_min`: Tần suất quét Theo từ khóa (mặc định 180 phút).
     - `megasale_interval_min`: Tần suất quét Siêu Sale & Flash Sale (mặc định 60 phút).
     - `price_error_interval_min`: Tần suất quét Săn lỗi giá (mặc định 60 phút).
   - Modal Cài đặt trên Web Dashboard hiển thị rõ ràng 4 trường nhập số phút tương ứng cho từng tab.
   - API `/api/settings` trả về và cập nhật đầy đủ cả 4 trường tần suất.

3. **Điều phối lịch quét chạy ngầm phân hệ ([scanner.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py), [run.py](file:///c:/Users/pvthien/source/deal_hunter/run.py)):**
   - Bổ sung phương thức `scan_due()` trong `Scanner`: theo dõi timestamp lần chạy cuối của từng phân hệ (`_last_tracked_scan_time`, `_last_keyword_scan_time`, `_last_megasale_scan_time`, `_last_price_error_scan_time`).
   - Phân hệ nào đến hạn thời gian thì chỉ thực hiện quét riêng cho phân hệ đó:
     - Sản phẩm theo dõi: gọi `scan_tracked_products()` chỉ quét các link `source='user'`.
     - Từ khóa: gọi `run_keyword_search()`.
     - Siêu Sale: gọi `crawl_flash_sale_deals()`.
     - Săn lỗi giá: gọi `scan_price_errors()`.
   - Vòng lặp chính tại `run.py` kiểm tra `scan_due()` định kỳ mỗi 10 giây thay vì sleep khối lớn, giúp các thay đổi về tần suất từ giao diện người dùng có hiệu lực tức thì.

## Hệ quả
- Tab "Sản phẩm theo dõi" hoàn toàn tinh gọn, đúng nghĩa là danh sách cá nhân hóa của người dùng.
- Giảm tải đáng kể cho trình duyệt và đường truyền khi hệ thống không còn quét lại toàn bộ sản phẩm từ khóa trong mỗi chu kỳ quét giá cá nhân.
- Người dùng có toàn quyền kiểm soát tốc độ quét và độ sâu dữ liệu cho từng tab.
