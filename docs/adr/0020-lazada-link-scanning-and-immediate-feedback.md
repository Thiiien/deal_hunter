# 20. Tối ưu Quét Sản Phẩm Theo Link Lazada và Phản Hồi Tức Thì (Lazada Link Scanning & Instant Feedback)

Ngày: 2026-10-22

## Bối cảnh
Người dùng cần tối ưu hóa trải nghiệm theo dõi sản phẩm bằng link trên sàn Lazada và làm rõ việc áp dụng chu kỳ quét:
1. **Xác nhận chu kỳ quét 60 phút/lần:**
   - Kiểm tra mã nguồn cho thấy hệ thống đang áp dụng chung chu kỳ 60 phút (`scan_interval_min = 60`) cho toàn bộ sản phẩm kích hoạt (`get_active_products()`), phân nhóm tuần tự qua `_scan_platform` cho cả Shopee và Lazada.
2. **Điểm nghẽn phản hồi khi thêm link sản phẩm:**
   - Khi người dùng thêm URL qua Web Dashboard (`POST /api/products`) hoặc Telegram Bot (`/theodoi <url>`), hệ thống chỉ lưu URL thô vào cơ sở dữ liệu mà không quét ngay, buộc người dùng phải chờ đến chu kỳ kế tiếp (tối đa 60 phút) mới thấy tên, giá và voucher.
3. **Phân mảnh định danh và URL phức tạp (Link rút gọn app `s.lazada.vn`, tracking query):**
   - Link chia sẻ từ ứng dụng điện thoại thường có dạng rút gọn (`https://s.lazada.vn/s....`), khiến bộ trích xuất ban đầu chỉ băm MD5 tạm thời.
   - Khi trình duyệt Playwright cào trang, URL được chuyển hướng sang canonical URL gốc (`https://www.lazada.vn/products/...-i<item_id>-s<sku_id>.html?spm=...`).
   - Nếu không cập nhật lại URL chuẩn và `item_key`, cơ sở dữ liệu có thể sinh ra bản ghi trùng lặp hoặc giữ URL rút gọn khó quản lý.
4. **Thứ tự ưu tiên quét trong chu kỳ 60 phút:**
   - Các sản phẩm do người dùng chủ động dán link (`source='user'`) cần được ưu tiên cập nhật sớm hơn nhóm sản phẩm tự động thu thập từ các đợt flash sale (`source='flash_sale'`).

## Quyết định kiến trúc

1. **Kích hoạt Quét tức thì (Instant Link Scan):**
   - Trên Telegram Bot (`/theodoi <url>`): Phản hồi tin nhắn chờ `⏳ Đang quét thông tin sản phẩm...`, kích hoạt quét ngầm bằng thread và tự động cập nhật tin nhắn sang dạng thẻ sản phẩm đầy đủ (Tên, Huy hiệu sàn `🔵 [Lazada]`, Giá sàn, Giá niêm yết, Mã giảm giá, Giá thực trả, Tình trạng kho và link trực tiếp).
   - Trên Web Dashboard (`POST /api/products`): Khởi chạy luồng quét tức thì (`threading.Thread`) ngay khi tạo ID sản phẩm, giúp sản phẩm hiển thị đầy đủ thông tin sau vài giây mà không làm chậm phản hồi HTTP.

2. **Chuẩn hóa Canonical URL và Tự động Hợp nhất Bản ghi (`update_product_from_snapshot`):**
   - Lược bỏ tham số tracking rác (`?spm=...`) khỏi `canonical_url` của trang chi tiết Lazada và Shopee trong `PlaywrightAdapter`.
   - Bổ sung phương thức `update_product_from_snapshot(product_id, snapshot)` trong `DB`:
     - Cập nhật URL chuẩn và `item_key` chuẩn vào bản ghi sản phẩm.
     - Tự động phát hiện trường hợp hợp nhất (merge): Nếu `(platform, item_key)` chuẩn đã tồn tại trên một bản ghi khác, toàn bộ lịch sử giá (`price_history`) sẽ được chuyển sang bản ghi đích và bản ghi tạm thời được xóa an toàn, triệt tiêu nguy cơ nhân đôi dữ liệu.

3. **Ưu tiên Quét Nhóm Sản phẩm Người dùng (`User-Tracked Scan Prioritization`):**
   - Sắp xếp thứ tự quét trong `get_active_products`:
     `ORDER BY platform, CASE WHEN source='user' THEN 0 ELSE 1 END, id`.
   - Đảm bảo trong chu kỳ 60 phút, toàn bộ sản phẩm người dùng theo dõi sẽ luôn được quét và đối soát giá trước khi quét nhóm flash sale.

## Trạng thái
- 101/101 automated unit tests pass.
- Đã triển khai và hoạt động ổn định trên cả Web API, Telegram Bot và Scanner core.
