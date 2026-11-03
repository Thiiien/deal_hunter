# 44. Tinh giản Crawler và chuẩn hóa trạng thái hiển thị cho Sản phẩm theo dõi

## Trạng thái

Accepted.

## Bối cảnh
- Trước đây, crawler luôn cố gắng bóc tách điểm đánh giá (`Rating`) cho tất cả sản phẩm, bao gồm cả sản phẩm thuộc tab "Sản phẩm theo dõi".
- Bảng hiển thị tab Theo dõi trên Web Dashboard có cột `Rating` và cột `Trạng thái` hiển thị các nhãn phân loại thuật toán (`🔥 Deal thật`, `⏳ Đang thu thập`, `⚠️ Giá ảo`, `Bình thường`).
- Đối với sản phẩm người dùng tự dán link theo dõi, người dùng đã mặc định tin tưởng shop, do đó thông tin Rating là thừa thãi và làm chậm quá trình cào dữ liệu; đồng thời người dùng chỉ quan tâm sản phẩm hiện tại `Còn hàng` hay `Hết hàng` và có đạt giá mong muốn hay không.

## Quyết định kiến trúc

1. **Bỏ bóc tách Rating và rút gọn kiểm tra Tồn kho khi cào Sản phẩm theo dõi:**
   - Trong `Scanner.scan_product()` và crawler, đối với sản phẩm theo dõi (`source = 'user'`), bỏ qua yêu cầu kiểm tra rating tối thiểu (`min_rating`).
   - Tối ưu kiểm tra tồn kho thành dạng nhị phân nhanh (`True` / `False`) dựa trên các dấu hiệu vô hiệu hóa nút mua hoặc thông báo hết hàng của sàn.

2. **Cập nhật giao diện bảng Sản phẩm theo dõi trên Web Dashboard:**
   - Bỏ cột `Rating` khỏi thead và tbody của bảng Sản phẩm theo dõi, mở rộng không gian hiển thị cho tên sản phẩm và cột giá.
   - Cột `Trạng thái` chuyển thành hiển thị trực quan tình trạng hàng: `🟢 Còn hàng` hoặc `🔴 Hết hàng`, kèm huy hiệu `🎯 Đạt giá!` nếu giá hiện tại nhỏ hơn hoặc bằng giá mong muốn.
   - Giữ nguyên cột Rating và các nhãn thuật toán ở các tab tự động quét deal diện rộng (Siêu Sale / Flash Sale, Từ khóa).

3. **Điều kiện kích hoạt Cảnh báo Telegram:**
   - Sản phẩm thuộc tab theo dõi khi giảm sâu hoặc chạm giá mong muốn chỉ cần điều kiện `Còn hàng` là phát thông báo ngay, bỏ qua kiểm tra rating của shop.

## Hệ quả
- Tốc độ quét và phản hồi cho các sản phẩm theo dõi được cải thiện.
- Giao diện tab Sản phẩm theo dõi trên Dashboard trở nên tinh gọn, đúng trọng tâm nhu cầu theo dõi giá và tồn kho của người dùng.
- Duy trì sự an toàn và lọc shop uy tín ở các tab săn deal tự động từ sàn.
