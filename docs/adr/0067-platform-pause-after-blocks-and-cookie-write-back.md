# 67. Tạm nghỉ sàn sau khi bị chặn và đồng bộ cookie từ trình duyệt

Date: 2026-11-03

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Bổ sung ADR 0048 đến 0050; giữ nguyên quy tắc hết hạn ngạch không chặn quét của ADR 0050. Bổ sung 04/11/2026: dán cookie mới trên Dashboard kết thúc đợt nghỉ sớm, chu kỳ kế tiếp thử lại ngay thay vì chờ hết 30 phút.

## Bối cảnh

Nhật ký quét 7 ngày (27/10 đến 03/11/2026), toàn bộ sản phẩm theo dõi đều là Lazada:

1. **Mỗi đêm có một khoảng 6 đến 7 giờ không lượt quét nào thành công**, bắt đầu 23:00 đến 02:00 và tự hồi phục khoảng 08:00 giờ Việt Nam, trùng giờ hạn ngạch miễn phí của NopeCHA được cấp lại. File cookie không được ghi trong các sáng đó, nên nguyên nhân là tường thử thách chỉ NopeCHA giải được, không phải cookie hết hạn. `.env` không có khóa NopeCHA.
2. **Trong khoảng đó, mỗi chu kỳ 5 phút hệ thống thử 3 link, bị chặn, gửi một tin admin rồi bỏ chu kỳ**: khoảng 85 tin cảnh báo giống nhau mỗi đêm và 36 lượt tải thất bại mỗi giờ.
3. **Cookie lưu trữ chỉ được ghi lúc đăng nhập và không bao giờ cập nhật từ trình duyệt đang chạy.** Mỗi lần bị chặn hệ thống nạp đè file cũ lên profile trình duyệt, có thể ghi đè token mới hơn mà Lazada vừa xoay. Hàm kiểm tra phiên chỉ xem tên cookie, nên không phân biệt được phiên sống hay chết.
4. Người dùng hỏi về tự giải captcha khi hết NopeCHA; quyết định không viết bộ giải reCAPTCHA hay x5sec tự động vì đó là phá lớp bảo vệ của sàn và dẫn tới khóa tài khoản hoặc IP nặng hơn.

## Quyết định kiến trúc

1. **Tạm nghỉ sàn 30 phút sau 3 link liên tiếp bị chặn.** Hết 30 phút, chu kỳ kế tiếp thử lại với một sản phẩm: còn bị chặn thì nghỉ tiếp 30 phút, quét được thì chạy lại bình thường. Admin nhận đúng hai tin cho một đợt nghỉ: một khi bắt đầu, một khi chạy lại. Không dựa vào bộ đếm hạn ngạch, không cần người can thiệp.
2. **Đồng bộ cookie từ trình duyệt.** Sau mỗi lượt quét Lazada thành công, cookie thuộc miền Lazada trong trình duyệt được ghi lại vào `cookies_lazada.json`. File chỉ được nạp vào trình duyệt khi nó thay đổi từ bên ngoài (người dùng đăng nhập lại); một file như vậy không bao giờ bị ghi đè trước khi được nạp.
3. **Không tự giải captcha.** Đường thoát khi phiên chết thật vẫn là người dùng đăng nhập lại trên máy có màn hình; khóa NopeCHA trả phí là lựa chọn của người dùng, chưa áp dụng.

## Hệ quả

- Ban đêm: tối đa 2 lượt thử mỗi giờ thay vì 36, hai tin admin cho mỗi đợt thay vì một tin mỗi 5 phút; hệ thống tự chạy lại khi tường chặn hết.
- Token Lazada xoay trong ngày sống sót qua khởi động lại; đăng nhập lại từ máy người dùng vẫn được ưu tiên tuyệt đối.
- Đánh đổi: nếu tường chặn hết sớm hơn, hệ thống chậm tối đa 30 phút mới biết.
- Chưa đo: độ dài tường chặn ban đêm sau thay đổi này; cần một đêm số liệu trước khi cân nhắc NopeCHA trả phí.
