# 27. Kiến Trúc Phát Hiện Lỗi Giá và Phê Duyệt Quản Trị (Price Error Detection & Admin Approval Workflow)

Ngày: 2026-10-23

## Bối cảnh
Người bán trên các sàn TMĐT (Shopee, Lazada) thỉnh thoảng gặp sự cố đặt nhầm giá (thiếu chữ số, nhầm đơn vị tiền tệ, đặt giá của phụ kiện cho cả listing chính, hoặc quên tắt khuyến mãi chồng chéo). Những deal này có mức giảm sâu bất thường (từ 65% đến 95%), tồn tại trong thời gian rất ngắn (vài phút đến vài giờ) và có tỷ lệ bị sàn/shop hủy đơn cao.

Dựa trên tài liệu thiết kế chi tiết tại [PRICE_ERROR_DETECTION.md](file:///c:/Users/pvthien/source/deal_hunter/.docs/PRICE_ERROR_DETECTION.md) và kết quả trao đổi với người dùng:
1. **Nguồn quét:** Tận dụng luồng quét sản phẩm theo dõi, luồng cào Flash Sale/Siêu Sale liên sàn và mở rộng quét nhóm từ khóa hàng giá trị cao.
2. **Kênh cảnh báo:** Gửi riêng cho Admin trước qua Telegram (kèm inline keyboard duyệt đăng) và tab riêng trên Dashboard, tuyệt đối không tự động phát sóng công khai lên kênh Telegram.
3. **Quy trình xác nhận:** Báo ngay cho Admin khi phát hiện (kèm nhãn "Đang xác minh") và tự động hẹn giờ quét lại sau 2 phút để kiểm tra độ ổn định của giá và tình trạng tồn kho.

## Quyết định kiến trúc

1. **Bộ lọc sơ cấp và chống cảnh báo giả (Anti-Fake & Accessory Filter):**
   - Lọc bỏ giá `<= 0` hoặc `< 1.000₫`.
   - Lọc từ khóa phụ kiện và đặt cọc trong tên sản phẩm (`ốp`, `case`, `dây`, `cáp`, `bao da`, `miếng dán`, `cường lực`, `móc khóa`, `đặt cọc`, `cọc`, `pre-order`, `combo`, `set`).
   - Đảm bảo giá trị trước giảm (`baseline`) thỏa mãn ngưỡng giá sàn `deal_min_original_price` (mặc định ≥ 500.000₫).

2. **Tiêu chuẩn nhận diện lỗi giá:**
   - Trường hợp có lịch sử giá: Mức giảm so với giá trung vị 30 ngày `disc_hist >= 65%`.
   - Trường hợp sản phẩm mới: Mức giảm so với giá niêm yết `disc_list >= 65%` và shop uy tín (`rating >= 4.0`).
   - Phân cấp bất thường:
     - `65% <= discount < 85%`: Nhãn `[⚠️ NGHI LỖI GIÁ]`.
     - `discount >= 85%`: Nhãn `[🚨 CỰC KỲ BẤT THƯỜNG / SẬP GIÁ]`.

3. **Bảng lưu trữ `price_anomalies` trong Database ([DB](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - Quản lý vòng đời phát hiện:
     - `stage`: `confirming` (đang xác minh 2 phút) ➔ `confirmed` (giá ổn định, còn hàng) | `rejected` (shop đã sửa giá hoặc hết hàng) | `published` (admin đã duyệt đăng).
     - `reject_reason`: `price_fixed`, `out_of_stock`, `accessory_fake`.
     - `admin_message_id`: lưu ID tin nhắn Telegram gửi cho admin để cập nhật trạng thái theo thời gian thực.

4. **Xác nhận tự động sau 2 phút ([Scanner._schedule_anomaly_confirmation](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
   - Sau khi gửi tin ban đầu cho Admin, một background timer (120s) được kích hoạt để nạp lại snapshot sản phẩm.
   - Nếu giá vẫn sập và còn hàng: cập nhật `confirmed`, sửa tin Telegram báo Admin "✅ Đã xác nhận deal vẫn còn sống".
   - Nếu giá tăng lại hoặc hết hàng: cập nhật `rejected`, sửa tin Telegram báo Admin "ℹ️ Shop đã sửa lại giá / Đã hết hàng".

5. **Tương tác phê duyệt Admin trên Telegram ([bot.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/bot.py)):**
   - Tin nhắn Admin đính kèm inline buttons:
     - `[🛒 Mua ngay ↗]`: Mở link tiếp thị liên kết đến trang sản phẩm.
     - `[📢 Đăng lên Kênh]`: Callback `publish_anomaly:<id>` phát sóng thông báo lên kênh Telegram chung.
     - `[❌ Bỏ qua]`: Callback `dismiss_anomaly:<id>` đóng cảnh báo.

6. **Tab Quản lý trên Web Dashboard ([templates/dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Bổ sung thẻ tab `⚠️ Nghi lỗi giá` hiển thị danh sách các deal lỗi giá đang theo dõi kèm trạng thái xác minh, điểm lệch giá và nút thao tác nhanh.

## Trạng thái
- Bản thiết kế kiến trúc đã thống nhất qua phỏng vấn phản biện với người dùng.
- Tiến hành hiện thực hóa mã nguồn Phase 1 theo quy chuẩn Ponytail.
