# 52. Bảo vệ sản phẩm theo dõi của người dùng và chống lỗi ẩn dữ liệu

Date: 2026-10-31

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`)

## Bối cảnh

1. **Dữ liệu sản phẩm theo dõi biến mất bí ẩn khỏi giao diện**:
   - Người dùng phản ánh tab "📦 Sản phẩm theo dõi" bị trống trơn và số lượng thống kê trên giao diện mặc định bằng 0 dù trước đó đã thêm 23 sản phẩm.
   - Kiểm tra cơ sở dữ liệu `data/deals.db` cho thấy toàn bộ 23 sản phẩm vẫn tồn tại 100% nhưng đều bị gán `active = 0` và `fail_count = 5`.
2. **Nguyên nhân phân loại sai ngoại lệ trên sàn Lazada**:
   - Khi Lazada chặn bảo mật hoặc cookie phiên hết hạn, hàm phân tích `_parse_lazada` không bóc tách được giá bán.
   - Adapter ném ngoại lệ `FetchError` thay vì `Blocked`.
   - Cơ chế dọn dẹp cũ (theo ADR 0031) ghi nhận đây là lỗi của từng sản phẩm riêng lẻ và tự động chuyển `active = 0` sau 5 lần lỗi liên tiếp (`fail_count >= 5`).
3. **Lỗi `add_cookies` trên `NoneType` khi nạp Cookies**:
   - Khi người dùng cập nhật cookies từ giao diện Web Modal (`/api/cookies`) hoặc khi khởi động tiến trình, việc gọi `reload_cookies()` khi trình duyệt Chromium chưa khởi động (`self._ctx` là `None`) gây ngoại lệ `AttributeError: 'NoneType' object has no attribute 'add_cookies'`.
4. **Lỗi giao diện (Bug UI Badge & Bộ lọc "Tất cả")**:
   - Trong `dashboard.html`, hàm `loadProducts()` trích xuất phần tử DOM `tracked-tab-count` nhưng gán bằng `activeUserProducts.length` thay vì `userProducts.length`, khiến huy hiệu số lượng trên tab hiển thị `0` khi sản phẩm bị chuyển trạng thái.
   - Bộ lọc mặc định "Tất cả" trả về `p.active !== 0`, vô tình ẩn toàn bộ sản phẩm người dùng nếu sản phẩm bị vô hiệu hóa hoặc gặp lỗi.
5. **Thiếu cơ chế phục hồi và quyền kiểm soát cho người dùng**:
   - Khi sản phẩm rơi vào trạng thái `active = 0`, hệ thống thiếu cơ chế Auto-healing tự động sửa sai cho database đã tồn tại.

## Quyết định kiến trúc

1. **Quy tắc bất biến bảo vệ sản phẩm người dùng (`source = 'user'`):**
   - **Tuyệt đối không bao giờ tự động chuyển `active = 0`** cho sản phẩm do người dùng chủ động theo dõi (đặc biệt là 23 sản phẩm trên sàn Lazada) bất kể gặp lỗi `FetchError` bao nhiêu lần (kể cả khi `fail_count >= 5`).
   - `fail_count` vẫn tiếp tục được cộng dồn nhằm mục đích đo lường độ ổn định và gửi cảnh báo quản trị Telegram duy nhất một lần khi chạm mốc 5 lần lỗi liên tiếp (`new_fails == 5`), giữ nguyên `active = 1` để người dùng tiếp tục theo dõi trên Dashboard.
   - Chỉ được phép tự động chuyển `active = 0` đối với sản phẩm từ kênh tự động cào khám phá (Flash Sale, Siêu Sale, Từ khóa) khi `fail_count >= 5`.
   - Đối với sản phẩm người dùng, việc ngưng theo dõi chỉ diễn ra khi người dùng chủ động bấm nút "Xóa" trên giao diện hoặc sàn trả về HTTP 404 / `ProductDelisted` xác nhận link đã bị xóa vĩnh viễn.

2. **Cơ chế Auto-healing tự động khôi phục dữ liệu tại `DB._migrate()`:**
   - Bổ sung câu lệnh cập nhật khôi phục tự động vào quá trình migration khi khởi tạo DB:
     ```sql
     UPDATE products SET active = 1, fail_count = 0 WHERE source = 'user' AND active = 0
     ```
   - Đảm bảo toàn bộ 23 sản phẩm người dùng từng bị lỗi cũ de-activate sẽ được tự động kích hoạt lại `active = 1` ngay khi ứng dụng khởi chạy mà không cần thao tác thủ công.

3. **Nạp Cookies an toàn khi trình duyệt chưa khởi động:**
   - Trong `PlaywrightAdapter._load_saved_cookies()` và `reload_cookies()`, kiểm tra điều kiện bảo vệ `if not self._ctx: return`.
   - Nếu Chromium context chưa khởi tạo, bỏ qua thao tác `add_cookies` (cookies đã được ghi an toàn vào `data/cookies.json` và `data/cookies_lazada.json`). Khi Playwright context khởi động qua `_ensure_started()`, cookies sẽ được nạp đầy đủ.

4. **Phân loại chuẩn xác ngoại lệ `Blocked` trên Lazada:**
   - Khi không trích xuất được giá bán trên Lazada và trang có dấu hiệu chặn bảo mật (URL chứa `/punish`, `login.lazada.vn`, `verify/slider`, phần tử DOM slider `#nc_1_wrapper`, hoặc mã MTOP `RGV587_ERROR`, `FAIL_SYS_USER_VALIDATE`), adapter ném ngoại lệ `Blocked`.
   - Scanner xử lý `Blocked` như một sự cố cấp độ toàn sàn: dừng quét sàn đó cho chu kỳ hiện tại, cảnh báo admin làm mới phiên mà không phạt `fail_count` lên bất kỳ sản phẩm nào.

5. **Đặt lại `fail_count = 0` khi quét thành công:**
   - Trong `_scan_platform()`, ngay khi một snapshot được đọc thành công (`snap is not None`), hệ thống lập tức gọi `self._db.reset_product_fail_count(prod["id"])`.

6. **Hoàn thiện hiển thị, bộ đếm và phục hồi trên Dashboard:**
   - Endpoint `/api/summary` sử dụng `db.get_products_with_latest_price(include_inactive=True)` để tổng số sản phẩm và số lượng từng sàn (Shopee/Lazada) hiển thị chính xác.
   - Huy hiệu `tracked-tab-count` trên tab Sản phẩm theo dõi luôn phản ánh tổng số sản phẩm người dùng (`userProducts.length`).
   - Bộ lọc mặc định "Tất cả" trả về `true` cho tất cả sản phẩm của người dùng, hiển thị kèm huy hiệu trạng thái rõ ràng (`🟢 Còn hàng`, `🔴 Hết hàng`, `⏸️ Đã ngưng`, `⚠️ Lỗi quét (x lần)`) cùng nút `♻️ Khôi phục` khi sản phẩm ở trạng thái ngưng.

## Hệ quả

- 23 sản phẩm người dùng theo dõi trên sàn Lazada được khôi phục trạng thái `active = 1` và bảo vệ vĩnh viễn: dù gặp lỗi `FetchError` quá 5 lần, scanner không bao giờ hạ `active = 0`.
- Triệt tiêu hoàn toàn lỗi warning `add_cookies` trên `NoneType`.
- Con số thống kê trên thẻ "Đang theo dõi" (`23 (🟠 0 / 🔵 23)`) và huy hiệu tab Sản phẩm theo dõi (`23`) luôn hiển thị đầy đủ, chính xác.
- Danh sách 23 sản phẩm luôn hiển thị nguyên vẹn trên bảng điều khiển tab Sản phẩm theo dõi.
