# 11. Lọc sản phẩm sẵn sàng mua (In-Stock) và so sánh giá đa shop (Multi-Shop Cross Comparison)

Ngày: 2026-10-20

## Bối cảnh
Trong quá trình theo dõi deal và tìm kiếm sản phẩm:
1. Nhiều link sản phẩm trên Shopee đã hết hàng (`stock == 0` hoặc các phân loại đều hết), hoặc đợt Flash Sale đã bán hết sản phẩm. Việc tiếp tục cào hoặc chọn các link hết hàng làm "giá rẻ nhất" gây lãng phí tài nguyên và làm giảm độ tin cậy của thông báo gửi tới người dùng.
2. Nhiều người bán cố tình đặt một phân loại phụ kiện hoặc phân loại ảo giá cực rẻ nhưng đã hết hàng để kéo thứ hạng tìm kiếm.
3. Cùng một mặt hàng thường được bán bởi nhiều shop khác nhau trên sàn với mức giá chênh lệch, chương trình voucher và tồn kho khác nhau. Người mua có nhu cầu tìm shop bán món đó với giá thực trả thấp nhất và hàng còn sẵn sàng để mua.

## Quyết định kiến trúc

1. **Chuẩn hóa trạng thái "Sẵn sàng mua" (In-Stock Detection):**
   - Trong `PlaywrightAdapter._parse_shopee`:
     - Nếu sản phẩm có phân loại hàng (`models`): kiểm tra danh sách `in_stock_models = [m for m in models if (m.get("stock") or 0) > 0 and m.get("price") is not None]`.
     - Nếu `len(in_stock_models) == 0` khi có `models`, hoặc nếu `item.stock == 0`, `item.status in (2, 3)`, `item.item_status in ("out_of_stock", "deleted", "banned")`, hoặc nút mua trên giao diện ghi "Hết hàng" / bị vô hiệu hóa: xác định `stock = False`.
     - Giá của sản phẩm được tính dựa trên phân loại **còn hàng rẻ nhất** (loại bỏ hoàn toàn các phân loại hết hàng).
   - Trong `_crawl_flash_sale_sync`:
     - Bỏ qua các sản phẩm có `stock == 0`, `is_sold_out == True`, hoặc `stock_status == 2`.

2. **Xử lý tồn kho trong quy trình quét (`Scanner`):**
   - **Với sản phẩm Flash Sale (`source = 'flash_sale'`):**
     - Khi một chu kỳ quét phát hiện sản phẩm đã hết hàng (`snapshot.stock is False`), tự động tắt kích hoạt (`active = 0`) trong cơ sở dữ liệu để giải phóng khỏi Tab Siêu Sale và không tiếp tục quét lại.
   - **Với sản phẩm người dùng theo dõi (`source = 'user'`):**
     - Giữ nguyên theo dõi nhưng chặn tuyệt đối việc gửi thông báo Telegram (cả Deal Thật và Giá Mong Muốn) chừng nào sản phẩm chưa có hàng trở lại.

3. **Thuật toán so sánh giá đa shop (Multi-Shop Cross Comparison):**
   - Khi tìm kiếm theo từ khóa hoặc khi kích hoạt so giá chéo:
     - Quét chi tiết Top 5 shop bán chạy nhất từ kết quả tìm kiếm sàn.
     - **Bộ lọc chống dính phụ kiện (Anti-Accessory Filter):**
       - Yêu cầu tiêu đề sản phẩm của shop ứng viên phải chứa các từ khóa cốt lõi của món đồ.
       - Loại bỏ các sản phẩm chứa từ khóa phụ kiện (`ốp`, `dán`, `skin`, `feet`, `dây thay thế`, `hộp đựng`, `switch lẻ`) trừ khi từ khóa tìm kiếm yêu cầu.
       - Loại bỏ ứng viên có giá < 35% so với giá trung vị của các shop trong top (dấu hiệu phụ kiện/hàng khác loại).
     - **Tiêu chí xếp hạng:**
       - Chỉ xét các shop có hàng sẵn sàng mua (`stock is True` hoặc `stock is None`).
       - So sánh theo giá sau voucher (`effective_price = final_price or price`).
       - Chọn shop có mức giá sau voucher thấp nhất để theo dõi.

4. **Tích hợp giao diện Dashboard & Web API:**
   - Cung cấp API `POST /api/products/<id>/compare` để kiểm tra so sánh giá các shop khác cho sản phẩm đang theo dõi.
   - Hiển thị nhãn trạng thái "Hết hàng" (màu đỏ) rõ ràng trên bảng điều khiển.

## Trạng thái
Đã thống nhất qua quy trình `/grill-with-docs` và phê duyệt triển khai.
