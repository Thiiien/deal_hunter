# 26. Xóa và Lọc Bỏ Sản Phẩm Rác Khỏi Tab Siêu Sale (Purging Junk Flash Sale Products & MegaSale Clean View)

Ngày: 2026-10-23

## Bối cảnh
Trước đây, các đợt cào tự động Flash Sale và Siêu Sale đã thu thập hàng chục sản phẩm linh tinh, giá rẻ (dưới 500k như ốp lưng, móc khóa, đồ gia dụng nhỏ 10k–50k). Dù người dùng đã cài đặt ngưỡng giá gốc tối thiểu `deal_min_original_price` (mặc định 500.000₫), các sản phẩm rác cũ này vẫn tồn tại trong cơ sở dữ liệu SQLite (`products` và `price_history`) và tiếp tục xuất hiện trong tab **"🔥 Tổng Hợp Deal Giảm Sâu & Siêu Sale"** trên Web Dashboard.

Người dùng yêu cầu:
1. Lọc sạch tab Siêu Sale, chỉ giữ lại các sản phẩm có giá gốc và giá niêm yết lớn hơn hoặc bằng con số cài đặt.
2. Cung cấp cơ chế xóa sạch (purge) các sản phẩm rác này khỏi cơ sở dữ liệu khi người dùng kích hoạt mà vẫn bảo toàn an toàn 100% các sản phẩm người dùng tự thêm theo dõi (`source = 'user'`).

## Quyết định kiến trúc

1. **Phương thức dọn rác chuyên biệt trong Database ([DB.purge_junk_flash_sales](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - Truy vấn tìm toàn bộ sản phẩm có `source = 'flash_sale'` mà giá trị cao nhất giữa `list_price` và `price` ở bản ghi gần nhất nhỏ hơn ngưỡng `min_price`:
     ```sql
     SELECT p.id FROM products p
     LEFT JOIN price_history ph ON ph.id = (
         SELECT id FROM price_history WHERE product_id = p.id ORDER BY ts DESC LIMIT 1
     )
     WHERE p.source = 'flash_sale'
       AND MAX(COALESCE(ph.list_price, 0), COALESCE(ph.price, 0)) < ?
     ```
   - Xóa theo chuỗi an toàn: xóa toàn bộ lịch sử giá (`price_history`), cảnh báo (`alerts`) và bản ghi sản phẩm (`products`).
   - Tuyệt đối không xóa bất kỳ sản phẩm nào có `source = 'user'` (link do người dùng tự dán theo dõi).

2. **API Endpoint Dọn rác ([web.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py)):**
   - Tuyến đường `POST /api/products/purge-junk` nhận `min_price` (hoặc mặc định lấy `config.deal_min_original_price`), thực hiện dọn dẹp và phản hồi số lượng bản ghi đã xóa.
   - Tại API `GET /api/products`, tự động bỏ qua các sản phẩm `source = 'flash_sale'` có giá trị trước giảm `< deal_min_original_price` để giao diện luôn sạch sẽ ngay cả trước khi chạy lệnh xóa DB.

3. **Giao diện Web Dashboard ([templates/dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Thêm nút **`🧹 Dọn dẹp SP rác (< 500k)`** trên thanh công cụ của tab Siêu Sale.
   - Hàm `isMegaSaleDeal(p)` kiểm tra nghiêm ngặt `baseVal >= window.dealMinOriginalPrice` trước khi đưa sản phẩm vào danh sách hiển thị Siêu Sale.
   - Bổ sung nút xóa nhanh `🗑️` cho từng dòng sản phẩm trong bảng Siêu Sale.
   - Tự động cập nhật nhãn ngưỡng giá trên nút dọn rác khi người dùng thay đổi cấu hình trong Settings Modal.

## Trạng thái
- 115/115 automated unit tests pass.
- Bổ sung test case kiểm thử `test_purge_junk_flash_sales` trong `test_db.py` và `test_services.py`.
- Đã chạy dọn dẹp thành công 97 sản phẩm rác cũ trên container đang chạy, đưa số sản phẩm flash sale hiển thị về đúng 21 sản phẩm đạt chuẩn giá gốc ≥ 500.000₫.
