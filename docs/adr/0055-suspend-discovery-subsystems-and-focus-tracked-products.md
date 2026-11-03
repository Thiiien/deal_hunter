# 55. Tạm ẩn các tab khám phá, dừng cào nền và tối ưu tài nguyên cho Sản phẩm theo dõi

Date: 2026-11-01

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`)
Mục 3 (bảo lưu cảnh báo giảm giá theo lịch sử) đã tắt theo ADR 0062.

## Bối cảnh

1. **Tiêu hao tài nguyên và Captcha từ các phân hệ khám phá tự động**:
   - Các phân hệ khám phá deal ngầm gồm: "⚠️ Nghi lỗi giá" (`price_error`), "🔍 Theo từ khóa" (`keyword`), "🔥 Siêu Sale" (`megasale`), và "🏷️ Lazada TMALL" (`tmall`).
   - Khi chạy định kỳ nền (`scan_due`), các phân hệ này gửi liên tục hàng loạt truy vấn tìm kiếm và cào danh mục diện rộng lên sàn Shopee và Lazada. Việc này tiêu hao nhanh chóng hạn mức giải Captcha (NopeCHA và Slider), làm tăng nguy cơ phiên đăng nhập bị sàn trừng phạt (punish/checkpoint), đồng thời gây chậm trễ chu kỳ cập nhật giá của các sản phẩm người dùng đang trực tiếp quan tâm.
2. **Spam thông báo Telegram không mong muốn**:
   - Khi các phân hệ khám phá phát hiện sản phẩm có biến động giá hoặc nghi lỗi giá ngoài danh mục người dùng quan tâm, hệ thống liên tục gửi thông báo lên Telegram Admin và Kênh, làm phân tán sự chú ý của người dùng.
3. **Nhu cầu tập trung tối đa cho danh mục Sản phẩm theo dõi**:
   - Người dùng yêu cầu tinh gọn giao diện Web Dashboard, tạm thời ẩn 3 tab: "⚠️ Nghi lỗi giá", "🔍 Theo từ khóa", "🏷️ Lazada TMALL", ngưng toàn bộ tác vụ quét nền của các phân hệ này, ngưng gửi thông báo Telegram tương ứng, và dành 100% tài nguyên mạng, trình duyệt cũng như quota Captcha phục vụ 22 sản phẩm trong tab "📦 Sản phẩm theo dõi".

## Quyết định kiến trúc

1. **Ẩn các tab khám phá trên Web Dashboard (`templates/dashboard.html`):**
   - Ẩn trực tiếp 3 nút chuyển tab: `#tab-anomalies-btn`, `#tab-keywords-btn`, `#tab-tmall-btn` bằng `style="display:none"`.
   - Bổ sung bộ lọc điều hướng trong hàm JavaScript `switchMainTab(tab)`: nếu người dùng truy cập trực tiếp hoặc thông qua trạng thái cũ vào các tab `anomalies`, `keywords`, hoặc `tmall`, hệ thống tự động chuyển hướng hiển thị an toàn về tab `tracked`.
   - Loại bỏ các lời gọi API định kỳ tải dữ liệu bất thường (`loadAnomalies`) và từ khóa (`loadKeywords`) khỏi chu kỳ cập nhật 120 giây của trang, giảm tải request HTTP lên server nội bộ.

2. **Đồng bộ trạng thái tắt quét nền từ CSDL vào vòng lặp Scanner (`src/deal_hunter/scanner.py`):**
   - Bổ sung hàm kiểm tra trạng thái kích hoạt phân hệ `_is_subsystem_enabled(key)`: ưu tiên đọc trực tiếp từ bảng `settings` trong CSDL SQLite (`deals.db`) trước khi tham chiếu cấu hình tĩnh `self._config`.
   - Trong bộ định thời `scan_due()`: áp dụng kiểm tra `_is_subsystem_enabled` cho cả 4 phân hệ:
     - `keyword_scan_enabled == 0`: Bỏ qua tìm kiếm từ khóa nền.
     - `megasale_scan_enabled == 0`: Bỏ qua cào deal Siêu Sale / Flash Sale.
     - `price_error_scan_enabled == 0`: Bỏ qua quét danh mục lỗi giá.
     - `tmall_scan_enabled == 0`: Bỏ qua cào trợ giá Lazada TMALL.
   - Khi các giá trị này được cấu hình là `"0"` trong DB, các phân hệ hoàn toàn ngủ đông, không tạo luồng cào và không tiêu tốn tài nguyên Captcha.

3. **Chặn cảnh báo Telegram lỗi giá từ các sản phẩm khám phá (`_handle_price_error`):**
   - Đặt chốt chặn ngay đầu hàm `_handle_price_error()`: nếu `price_error_scan_enabled` không kích hoạt, dừng xử lý ngay lập tức. Hệ thống không tạo bản ghi anomaly mới và không gửi tin nhắn cảnh báo lỗi giá tới Telegram admin.
   - Bảo lưu 100% cảnh báo deal chất lượng cao cho danh mục người dùng:
     - Cảnh báo chạm mức giá mong muốn (`_send_target_alert`).
     - Cảnh báo giảm giá thực tế theo lịch sử (`_send_price_drop_alert`).

4. **Bảo toàn dữ liệu lịch sử và cơ chế khôi phục tức thời:**
   - Dữ liệu sản phẩm, lịch sử quét và các thiết lập đã có trong CSDL `deals.db` được bảo toàn nguyên vẹn, không bị xóa.
   - Khi người dùng có nhu cầu tái kích hoạt lại bất kỳ phân hệ nào, chỉ cần chuyển cờ trong bảng `settings` hoặc trang cài đặt thành `"1"`, phân hệ đó sẽ hoạt động trở lại ngay lập tức mà không cần triển khai lại mã nguồn.

## Hệ quả

- Toàn bộ lưu lượng cào nền và chi phí giải Captcha được giảm thiểu tối đa, tập trung 100% công suất phục vụ việc theo dõi 22 sản phẩm mục tiêu.
- Giao diện Dashboard gọn gàng, trực quan, loại bỏ các cảnh báo và bảng dữ liệu ngoài lề.
- Không còn phát sinh tin nhắn spam báo lỗi giá hay deal từ các sản phẩm lạ trên Telegram.
- Đã bổ sung kiểm thử tự động `test_subsystem_suspension_db_settings_and_price_error_suppression`, 100% test suite (186/186 tests) chạy thành công.
