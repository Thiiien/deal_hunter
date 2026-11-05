# 68. Quét toàn danh mục CellphoneS qua API công khai để bắt giảm sâu và nghi lỗi giá trước 11.11

Date: 2026-11-04

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Nguồn không phải sàn đầu tiên của hệ thống. Không thay đổi ADR 0055 và 0062 cho Shopee/Lazada; mở rộng nghĩa của Chế độ chỉ thông báo đạt giá mong muốn (ADR 0062) thành "chỉ áp cho sản phẩm theo dõi".

## Bối cảnh

1. **Mục tiêu:** người dùng muốn canh các link sắp giảm sâu hoặc lỗi giá quanh đợt 11.11 để mua hoặc đăng kênh. Hội nhóm săn sale làm việc này bằng bot quét diện rộng; trên sàn, hệ thống đã tắt quét diện rộng vì captcha và tường chặn (ADR 0055, 0067).
2. **CellphoneS là nguồn rẻ để quét diện rộng** (đo ngày 04/11/2026):
   - API GraphQL công khai `api.cellphones.com.vn/v2/graphql/query`, không cookie, không captcha, 200 sản phẩm mỗi request trong 0,9 giây.
   - Quét không lọc ngành bị trần 10.000 sản phẩm; quét theo 1.771 ngành con cho 20.434 sản phẩm trong 2.001 request, trong đó 2.671 là hàng cũ.
   - 20/20 sản phẩm mẫu ở 5 ngành: giá JSON-LD trong HTML và ô giá sau khi render bằng Chromium đều bằng `special_price` của API (hoặc `price` khi `special_price` = 0). `special_price` là giá của màu rẻ nhất; mỗi dung lượng là một sản phẩm riêng. Giá Smember chỉ hiện sau đăng nhập và không có trong API.
   - `price` (giá niêm yết) ít đổi và thường cao ảo: so với nó, hàng trăm sản phẩm luôn "giảm 20-30%".
   - Trang sản phẩm trả 404 với tiêu đề "Trang không tồn tại" khi ngừng bán.
3. **Thế Giới Di Động** chỉ có HTML, `robots.txt` yêu cầu nghỉ 5 giây mỗi request, một lượt toàn bộ mất khoảng 18 giờ. Được hoãn; làm CellphoneS trước.
4. **Ràng buộc có sẵn:** tên sàn `shopee`/`lazada` ghi cứng ở khoảng 88 chỗ trong 9 file; mọi link gửi ra phải là Affiliate Link; bảng `products` được dashboard tải toàn bộ ở mỗi lần làm mới, nên không thể chứa 18.000 dòng.

## Quyết định kiến trúc

1. **Nguồn dữ liệu và phạm vi** (`src/deal_hunter/adapters/cellphones.py`):
   - `CellphonesAdapter.iter_catalog()` gọi GraphQL theo danh sách ngành hàng cấp cao cố định, phân trang 200, khử trùng theo `product_id`, bỏ sản phẩm thuộc ngành "Hàng cũ" (id 29) hoặc ngành có tên kết thúc bằng " cũ".
   - Giá bán = `special_price` nếu > 0, ngược lại `price`; giá niêm yết = `price`; tồn kho coi là còn (API chỉ trả hàng đang bán), xác nhận lại bằng trang sản phẩm khi có nghi lỗi giá.
   - `CellphonesAdapter.fetch(url)` đọc JSON-LD của trang sản phẩm (giá, tên, tình trạng), 404 là ngừng bán. Dùng cho quét lại sau 2 phút và cho sản phẩm CellphoneS được người dùng bấm "Theo dõi".
   - Không dùng trình duyệt cho nguồn này.
2. **Lưu trữ riêng** (`db.py`): bảng `retail_items` (một dòng mỗi sản phẩm, giá hiện tại, lần thấy đầu và cuối) và `retail_price_history`. Lịch sử chỉ ghi thêm khi giá đổi so với dòng gần nhất, cộng một dòng mỗi 24 giờ. Không chạm `products` và `price_history`, nên dashboard, bot và quét sản phẩm theo dõi không chậm đi.
3. **Mốc giá trị thật:** Giá đỉnh gần đây = giá bán cao nhất trong 7 ngày lịch sử trước lần quét hiện tại; khi chưa có lịch sử thì dùng `price`. Giảm sâu là giảm từ 30% so với mốc; nghi lỗi giá là giảm từ 65% so với mốc và mốc từ Ngưỡng giá trị thật tối thiểu (500.000₫) trở lên, qua bộ lọc chống phụ kiện sẵn có.
4. **Luồng nghi lỗi giá tái dùng:** khi một sản phẩm quét toàn danh mục đạt ngưỡng, hệ thống tạo một dòng `products` với `source='retail'` rồi đi tiếp luồng ADR 0027 (bảng anomaly, quét lại sau 2 phút bằng trang sản phẩm, admin duyệt đăng kênh). Chốt chặn trong `_handle_price_error` (`price_error_scan_enabled` và `only_target_price_alerts`) chỉ còn áp cho sàn, không áp cho nguồn bán lẻ. Bật tắt nguồn này bằng cờ riêng `cellphones_scan_enabled`.
5. **Lịch chạy:** `scan_due` khởi động lượt quét trong một luồng riêng, không chặn chu kỳ sản phẩm theo dõi, không chạy chồng. Nhịp mặc định 15 phút, đổi được trong Cài đặt cùng công tắc bật tắt (khóa `cellphones_interval_min`, `cellphones_scan_enabled`). Lượt quét thấy dưới một nửa số sản phẩm của lượt trước thì báo admin một lần, vì khả năng cao API đã đổi.
6. **Giao diện:** tab "CellphoneS giảm sâu" liệt kê 200 dòng xếp theo mức giảm so với Giá đỉnh gần đây, kèm mức giảm so với niêm yết, lọc theo ngành và giá tối thiểu, nút Mở và nút Theo dõi (đi qua đường dán link sẵn có, nay nhận thêm link CellphoneS). Link gửi ra là link thường vì không có mã tiếp thị cho nguồn này.
7. **Định tuyến adapter:** `Scanner._adapter_for(platform)` trả adapter CellphoneS cho `cellphones`, còn lại giữ adapter hiện tại; bước kiểm tra phiên trước quét bỏ qua nguồn bán lẻ.

## Hệ quả

- Một lượt quét toàn danh mục khoảng 100 request, không tốn hạn ngạch captcha, không ảnh hưởng tường chặn của Shopee/Lazada.
- Hai ngày đầu tab gần như không có deal so với Giá đỉnh gần đây; đó là hành vi đúng, vì mốc cần lịch sử. Nghi lỗi giá vẫn bắt được ngay từ lượt đầu nhờ mốc niêm yết.
- Lỗi giá ở nhà bán lẻ thường bị hủy đơn; hệ thống chỉ phát hiện và đưa admin duyệt, không hứa mua được.
- Rủi ro: CellphoneS đổi schema hoặc chặn IP trong tuần sale thì nguồn này dừng; không có đường vòng bằng cookie. Cảnh báo "số sản phẩm giảm quá nửa" là tín hiệu duy nhất.
- Hoãn lại, chưa làm: Thế Giới Di Động; Flash Sale sắp diễn ra trên Shopee/Lazada; nhận link từ hội nhóm qua bot.
