# 69. Mỗi vòng quét toàn bộ sản phẩm theo dõi

Date: 2026-11-04

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Thay quyết định 1 của ADR 0066 (nhịp quét thích ứng); giữ nguyên quyết định 2 đến 5 của ADR 0066 và cách chọn giá của ADR 0054.

## Bối cảnh

Số đo từ DB sản xuất ngày 04/11/2026, 39 sản phẩm theo dõi, tất cả Lazada:

1. **Người dùng không nhận được cảnh báo kịp lúc để mua.** Với nhịp thích ứng, sản phẩm xa giá mong muốn chỉ được quét ba chu kỳ một lần: khoảng cách giữa hai lần quét cùng một sản phẩm có trung vị 6,7 phút nhưng một phần mười số lần vượt 26 phút. Người dùng muốn mọi sản phẩm được quét lại ở mỗi vòng, chấp nhận trả phí giải captcha.
2. **Thời gian một vòng đo được:** 25 đến 27 sản phẩm mất khoảng 5 phút, đủ 39 sản phẩm mất khoảng 7 phút (khoảng 11 giây mỗi sản phẩm, trong đó 5 giây là nghỉ theo ADR 0066). Vòng đủ dài hơn tần suất 5 phút, nên quy tắc "vòng kế tiếp bắt đầu sau khi vòng trước kết thúc ít nhất 60 giây" của ADR 0066 quyết định nhịp thực: khoảng 8 phút cho mọi sản phẩm.
3. **Chi phí captcha:** cứ 4 đến 7 lượt tải trang có một lượt giải. Quét hết mỗi vòng nâng số lượt tải từ khoảng 5.500 lên khoảng 7.000 mỗi ngày, tức 1.000 đến 1.750 lượt giải mỗi ngày. Gói NopeCHA miễn phí (100 lượt mỗi 23 giờ) cạn sau chưa đầy một giờ; quyết định này chỉ có nghĩa khi đi cùng gói trả phí và việc nạp khóa vào extension (chưa làm, ghi ở phần chưa làm).
4. **Độ trễ cảnh báo không nằm ở khâu gửi:** 26 cảnh báo trong 7 ngày đều được gửi trong cùng phút với lượt quét thấy giá đạt mốc. Độ trễ đến từ khoảng cách giữa hai lần quét và từ các khoảng chết khi bị chặn (18 trong 49 giờ gần nhất), xử lý ở quyết định riêng.

## Quyết định kiến trúc

1. **Mỗi vòng quét toàn bộ sản phẩm theo dõi đang hoạt động.** Bỏ điều kiện "sát giá mong muốn, có biến động 24 giờ, chưa có giá, hoặc đã bị bỏ qua hai vòng" của ADR 0066; không còn bộ đếm vòng bị bỏ qua, không còn truy vấn biến động 24 giờ.
2. **Thứ tự trong vòng: sản phẩm sát giá mong muốn trước.** Sản phẩm có giá mới nhất cách giá mong muốn không quá 10% được quét ở đầu vòng, phần còn lại theo thứ tự thêm vào. Không thêm lượt tải trang.
3. **Tần suất quét giữ nghĩa "khoảng nghỉ tối thiểu giữa hai vòng".** Khi vòng dài hơn tần suất, nhịp thực bằng độ dài vòng cộng 60 giây (ADR 0066, quyết định 2). Không hạ thời gian nghỉ giữa hai sản phẩm, không mở nhiều tab song song: hai cách đó tăng tỷ lệ bị thử thách mà ADR 0066 vừa giảm; xem lại sau một tuần có số liệu captcha của gói trả phí.

Phương án bị loại: công tắc "quét hết mỗi vòng" chỉ bật trong tuần sale, vì là cấu hình không ai nhớ tắt; muốn thưa lại thì tăng tần suất trong Cài đặt là đủ.

## Hệ quả

- Mọi sản phẩm được quét lại khoảng 8 phút một lần với 39 sản phẩm; thêm sản phẩm thì vòng dài thêm khoảng 11 giây mỗi sản phẩm. Sản phẩm sát mốc được quét trong phút đầu của vòng.
- Sản phẩm xa mốc nhanh gấp đôi so với trước; sản phẩm sát mốc chậm hơn khoảng 3 phút so với trước (5 phút thành 8 phút).
- Lượt tải và lượt giải captcha tăng khoảng 25%; khoảng chết khi hết quota giải dài thêm nếu không nạp khóa NopeCHA trả phí.
- Chưa làm, cần làm ngay sau ADR này: Dockerfile dùng bản `chromium_automation.zip` của NopeCHA và nạp `NOPECHA_API_KEY` vào `manifest.json`; hiện khóa trong `.env` chỉ dùng để hỏi số dư, extension chạy quota miễn phí theo IP. Tin báo khi bị chặn ghi số lượt giải còn lại và giờ cấp lại.
