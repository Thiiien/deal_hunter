# 65. Cảnh báo giá mong muốn khi bước vào tầm giá và khi giảm thêm

Date: 2026-11-03

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Thay thế ADR 0056.

## Bối cảnh

1. **ADR 0056 chọn gửi cảnh báo ở mỗi chu kỳ quét khi chu kỳ còn 8 phút:**
   - Với 8 phút một lần, một sản phẩm nằm dưới giá mong muốn sinh khoảng 180 tin mỗi ngày, được chấp nhận để người dùng chắc chắn hệ thống còn chạy.
2. **ADR 0060 rút chu kỳ xuống 2 phút:**
   - Cùng cách gửi đó, một sản phẩm nằm dưới giá mong muốn sinh khoảng 720 tin mỗi ngày, làm ngập Kênh phát sóng và che mất các deal khác.
3. **Mục tiêu giữ nguyên:** không bỏ lỡ deal và biết hệ thống còn sống, nhưng không làm ngập kênh.

## Quyết định kiến trúc

1. **Gửi khi giá bước vào tầm:** cảnh báo khi giá thực trả lần đầu nhỏ hơn hoặc bằng giá mong muốn và sản phẩm còn hàng.
2. **Gửi lại chỉ khi có thay đổi đáng kể:**
   - Giá giảm thêm từ 5% trở lên so với giá ở lần cảnh báo gần nhất.
   - Giá đã rời tầm (vượt lên trên giá mong muốn) rồi quay lại tầm.
3. **Nhắc mỗi 24 giờ:** chừng nào giá còn trong tầm, mỗi 24 giờ gửi một tin nhắc để người dùng biết hệ thống vẫn chạy.
4. **Nơi nhận:** gửi lên Kênh phát sóng (`TELEGRAM_CHANNEL_ID`); khi không cấu hình kênh thì gửi về chat admin thay vì bỏ qua.

## Hệ quả

- Một sản phẩm nằm yên dưới giá mong muốn sinh một tin lúc vào tầm và một tin nhắc mỗi ngày, thay vì khoảng 720 tin.
- Deal giảm sâu thêm hoặc quay lại tầm vẫn được báo ngay trong chu kỳ 2 phút.
- Cách gửi "mỗi chu kỳ quét" của ADR 0056 không còn áp dụng.
