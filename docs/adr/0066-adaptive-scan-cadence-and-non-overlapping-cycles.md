# 66. Nhịp quét thích ứng và chu kỳ không chạy nối đuôi

Date: 2026-11-03

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Bổ sung ADR 0060; không đổi cách chọn giá của ADR 0054.

## Bối cảnh

Số đo từ DB sản xuất ngày 03/11/2026, 39 sản phẩm theo dõi, tất cả Lazada:

1. **Một chu kỳ đủ 39 sản phẩm mất trung vị 30 phút** (khoảng 20 giây mỗi sản phẩm) trong khi tần suất cài 15 phút, nên các chu kỳ chạy nối đuôi không nghỉ; mỗi sản phẩm được quét lại sau 12 đến 24 phút.
2. **Hơn 95% lượt quét không thấy gì mới**: mỗi sản phẩm chỉ đổi giá khoảng 2 lần mỗi ngày; chỉ 3 sản phẩm đang cách giá mong muốn dưới 10%.
3. **Cứ 4 lượt tải trang có 1 lượt bị thử thách captcha** (380 đến 416 lượt giải mỗi ngày), nên số lượt tải quyết định cả tốc độ lẫn rủi ro bị chặn.
4. **Nửa thời gian mỗi sản phẩm là chờ cố định 500 ms sau mỗi lần bấm ô biến thể** (tới 15 ô), dù giá hiển thị đổi sau 150 đến 250 ms.
5. Người dùng xác nhận cách lấy giá hiện tại (bấm tối đa 15 ô, chọn biến thể rẻ nhất còn hàng) đúng yêu cầu và không được thay đổi. Mọi tối ưu chỉ được chạm vào lịch quét và thời gian chờ.

## Quyết định kiến trúc

1. **Nhịp quét thích ứng:** trong mỗi chu kỳ chỉ quét sản phẩm (a) chưa có giá, (b) cách giá mong muốn không quá 10%, (c) có giá thay đổi trong 24 giờ qua, hoặc (d) đã bị bỏ qua hai chu kỳ liên tiếp. Sản phẩm còn lại được quét ba chu kỳ một lần.
2. **Chu kỳ không chạy nối đuôi:** chu kỳ kế tiếp bắt đầu tại thời điểm muộn hơn giữa "bắt đầu chu kỳ trước + tần suất" và "kết thúc chu kỳ trước + 60 giây". Tần suất sản xuất hạ từ 15 phút xuống 5 phút.
3. **Nghỉ 4 đến 6 giây ngẫu nhiên giữa hai sản phẩm** (trước đây 1,6 đến 2,4 giây) để giảm tỷ lệ bị thử thách.
4. **Chờ sau khi bấm ô biến thể theo sự kiện:** chờ đến khi chữ giá trên trang đổi, tối đa 500 ms; số ô bấm và cách đọc giá giữ nguyên.
5. **Thử nghiệm chặn ảnh trang Lazada** trong một ngày (`BLOCK_IMAGES`, mặc định bật): giữ nếu tỷ lệ captcha không tăng so với ngày trước, tắt nếu tăng.

Những phương án bị loại vì đổi nguồn giá: bỏ bấm ô khi payload có giá SKU, gọi MTOP trực tiếp không qua trình duyệt, chọn giá payload làm giá chuẩn. Số liệu cho thấy payload chặn được chỉ cho giá của 1 SKU ở hơn 90% lượt quét và lệch với giá hiển thị cho cùng SKU ở 42% lượt so sánh, nên giá đúng hiện đến từ việc bấm ô.

## Hệ quả

- Sản phẩm gần giá mong muốn được quét lại mỗi 5 phút; sản phẩm xa giá mong muốn mỗi 15 phút; giá thu được ở mỗi lần quét giống hệt trước.
- Số lượt tải trang và captcha giảm khoảng 60%; thời gian mỗi sản phẩm nhiều biến thể giảm 3 đến 4 giây.
- Đánh đổi: sản phẩm xa giá mong muốn có thể trễ tới ba chu kỳ khi giá bất ngờ rơi mạnh; chấp nhận vì khi đó giá đã đổi và chu kỳ sau nó được quét mỗi chu kỳ.
- Giới hạn 15 ô biến thể và không tổ hợp màu × trục giữ nguyên theo yêu cầu người dùng, ghi ở "Vấn đề đã biết".
