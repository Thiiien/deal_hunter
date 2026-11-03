# 33. Chuẩn hóa bóc tách Voucher và nhận diện tình trạng Còn hàng / Hết hàng trên Crawler

## Bối cảnh
Khi theo dõi sản phẩm (đặc biệt là bàn phím cơ và thiết bị ngoại vi trên sàn Lazada và Shopee):
1. **Lỗi bóc tách voucher ảo (`LAZADA_75PCT + LAZADA_75PCT`)**:
   - Biểu thức chính quy `_parse_lazada_voucher_text` đặt từ khóa giảm giá ở dạng tùy chọn (`?`), khiến các thông số kỹ thuật sản phẩm (ví dụ: *"Bàn phím cơ AULA S75 Pro 75%"*, *"Layout 75%"*) bị bắt nhầm thành voucher giảm 75%.
   - Crawler quét cả tên sản phẩm `name` (gán loại `shop`) và tiêu đề trang `page.title()` có chữ "Lazada.vn" (gán loại `platform`), khiến hàm `_find_best_voucher` cộng dồn thành chuỗi dị thường `LAZADA_75PCT + LAZADA_75PCT` với mức giảm 150% giá trị sản phẩm.
   - Khi lưu vào database, do biểu thức `0.0 or snapshot.price` trong [db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py), giá cuối `0.0` bị coi là falsy và rơi ngược lại giá gốc.
2. **Lỗi nhận diện tình trạng còn hàng / hết hàng (Stock)**:
   - **Lazada**: JSON-LD `offers.availability` thường trả về `InStock` cấp độ sản phẩm dù mọi phân loại SKU thực tế đã hết hàng. Khi duyệt `sku_infos`, biểu thức `sinfo.get("stock") or sinfo.get("quantity")` gặp giá trị `0` bị đánh giá falsy thành `None`, dẫn đến `(stk is None or stk > 0)` trả về `True`. Đồng thời, nếu `stock` đã là `True` từ JSON-LD, crawler bỏ qua hoàn toàn việc kiểm tra DOM.
   - **Shopee**: Trên DOM web fallback, Shopee dùng class `.btn--disabled` và `aria-disabled="true"` trên nút Mua Ngay thay vì thuộc tính `disabled`, khiến crawler bỏ sót và mặc định gán `stock = True`.

## Quyết định kiến trúc

1. **Khắc phục triệt để voucher ảo ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py), [db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - **Bộ lọc từ khóa bắt buộc**: Thêm `DISCOUNT_KEYWORDS` (`giảm`, `voucher`, `mã`, `coupon`, `hoàn`, `xu`, `trợ giá`, `ưu đãi`, `off`, `sale`, `discount`, `cashback`, v.v.) vào đầu hàm `_parse_lazada_voucher_text`. Bất kỳ chuỗi nào không chứa từ khóa ưu đãi (như "Layout 75%", "Cotton 100%") sẽ lập tức bị từ chối (`return None`).
   - **Không quét voucher từ tiêu đề trang trình duyệt**: Loại bỏ việc quét `page.title()` và chỉ bóc tách voucher tiêu đề khi tên sản phẩm có gắn thẻ ngoặc vuông ưu đãi rõ ràng (ví dụ: `[VOUCHER 25%]`).
   - **Khử trùng lặp mã giảm giá trước khi cộng dồn**: Trong `_find_best_voucher`, loại bỏ các mã giảm giá giống hệt nhau (`LAZADA_75PCT`) giữa các phân loại ưu đãi trước khi ghép chuỗi `+`.
   - **Bảo toàn giá cuối `0.0`**: Sửa logic lưu `final_price` trong `db.save_snapshot` thành `getattr(snapshot, "final_price", None) if ... is not None else snapshot.price`.

2. **Chuẩn hóa nhận diện Còn hàng / Hết hàng theo cấp độ Phân loại (Multi-variation SKU Stock Priority) ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - **Xác định còn hàng cho sản phẩm nhiều phân loại**:
     - Trên Lazada: Quét danh sách phân loại (`.sku-variable-item`, `[class*="sku-variable"]`). Nếu có **ít nhất 1 phân loại không bị vô hiệu hóa** (`!disabled`, `!sku-variable-item_disabled`), sản phẩm được xác định là **CÒN HÀNG (`stock = True`)**. Chỉ khi **tất cả phân loại đều bị disable** thì mới tính là hết hàng.
     - Trên Shopee: Quét các nút phân loại (`.product-variation`). Nếu có ít nhất 1 nút không bị disable thì tính là **CÒN HÀNG (`stock = True`)**.
     - **Không dùng trạng thái nút Mua hàng ban đầu để báo hết hàng**: Khi vừa tải trang sản phẩm nhiều phân loại, nút "Mua ngay / Thêm vào giỏ" luôn ở trạng thái disabled do người dùng chưa chọn phân loại; crawler chỉ kiểm tra nút Mua khi sản phẩm không có bất kỳ nút phân loại nào (single-SKU).
   - **Cấu trúc `sku_infos` và dự phòng giá trên Lazada**:
     - Nhận diện SKU còn hàng qua `operation.get("disable") is False` hoặc `quantity.get("limit", {}).get("max", 0) > 0` hoặc số lượng `> 0`. Không tự ý gán `stock = False` khi không tìm thấy trường `price` trực tiếp trong SKU.
     - Dự phòng giá từ metadata theo dõi: Bổ sung đọc `fields.tracking.pdt_price` trong `__moduleData__` khi JSON-LD không có giá, đảm bảo lấy đúng giá thực tế của sản phẩm thay vì bị rỗng hay rơi về 0.0.

3. **Dọn dẹp dữ liệu lịch sử và quét lại:**
   - Đã làm sạch các bản ghi bị gán sai mã voucher ảo và bản ghi `price = 0.0` trong bảng `price_history` của `data/deals.db`.
   - Đã kích hoạt quét lại toàn bộ 10 sản phẩm theo dõi (`Tracked scan complete: 10 ok, 0 fail`), khôi phục giá thật và trạng thái còn hàng chuẩn xác trên hệ thống.

## Hệ quả
- Dữ liệu voucher của các sản phẩm theo dõi hiển thị chuẩn xác, không còn tình trạng voucher ma hay cộng dồn vô lý.
- Tình trạng còn hàng/hết hàng phản ánh đúng thực tế của shop trên cả Lazada và Shopee, đặc biệt đối với các sản phẩm có nhiều phân loại (màu sắc, switch phím, kích cỡ...).
- Toàn bộ 144 bài kiểm thử trong test suite đều vượt qua.

