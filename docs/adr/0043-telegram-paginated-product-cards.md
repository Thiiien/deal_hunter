# 43. Thẻ sản phẩm tương tác và phân trang danh sách theo dõi trên Telegram

## Bối cảnh
- Trước đây, lệnh `/list` gộp 5 sản phẩm vào một tin nhắn dài và xếp toàn bộ 10 nút bấm (`[🎯 Đặt giá #id]` và `[🗑️ Xóa #id]`) dồn xuống dưới đáy tin nhắn.
- Do giới hạn kiến trúc của Telegram Bot API, các nút bấm Inline Keyboard không thể chèn xen kẽ vào giữa văn bản nội dung.
- Điều này khiến người dùng di động khó đối chiếu nút bấm nào thuộc về sản phẩm nào ở phía trên, đặc biệt khi nội dung từng sản phẩm dài (có voucher, giá gạch, tình trạng kho).

## Quyết định kiến trúc

1. **Mô hình Thẻ sản phẩm tương tác (Interactive Product Card):**
   - Mỗi sản phẩm được phát hành thành một tin nhắn độc lập.
   - Cụm nút thao tác `[🎯 Đặt giá]` và `[🗑️ Xóa]` được gắn trực tiếp vào chân của chính tin nhắn sản phẩm đó (`reply_markup`).
   - Rút gọn nhãn nút bấm thành `[🎯 Đặt giá]` và `[🗑️ Xóa]` vì thông tin và mã `#ID` đã hiển thị trực quan ngay trên thẻ.

2. **Cơ chế xác nhận xóa tại chỗ (In-Place Confirmation):**
   - Khi bấm `[🗑️ Xóa]`, bàn phím inline của chính thẻ sản phẩm được chuyển đổi thành `[⚠️ Xác nhận xóa]` và `[❌ Hủy]` mà không bắn thêm tin nhắn rác vào cuộc hội thoại.
   - Khi xác nhận xóa, tin nhắn thẻ sản phẩm được cập nhật nội dung thành thông báo xóa thành công và gỡ bỏ bàn phím tương tác.
   - Nếu bấm hủy, bàn phím quay trở lại trạng thái ban đầu `[🎯 Đặt giá]` và `[🗑️ Xóa]`.

3. **Phân trang danh sách (Pagination):**
   - Giới hạn mỗi trang hiển thị tối đa 5 thẻ sản phẩm để ngăn ngừa quá tải màn hình và tránh chạm giới hạn tần suất gửi tin của Telegram (Rate limit / Flood control).
   - Một tin nhắn điều khiển phân trang được đính kèm ở cuối danh sách nếu tổng số trang > 1, cung cấp các nút `[◀️ Trang trước]`, `[📄 x/y]`, và `[Trang sau ▶️]`.
   - Lệnh `/list` cho phép chỉ định số trang: `/list [số_trang]` (mặc định trang 1).

## Hệ quả
- Giao diện danh sách sản phẩm theo dõi trên Telegram trực quan, hiện đại, dễ thao tác với một chạm.
- Khắc phục hoàn toàn sự nhầm lẫn giữa các nút bấm và sản phẩm.
- Luồng xác nhận xóa gọn gàng, giữ cho lịch sử chat luôn sạch sẽ.
