# 49. Lazada Cookie-First Priority & Slider Drag Captcha Solver

Date: 2026-10-30

## Status

Accepted

## Context

Trong quá trình cào dữ liệu từ Lazada, nền tảng thường xuyên kích hoạt các cơ chế kiểm tra bảo mật anti-bot (Alibaba Security / MTOP / x5sec):
1. **Hiện tượng chặn ngầm (Background Punish Iframe)**: Khi truy cập trang chi tiết sản phẩm (PDP) bằng cookies hợp lệ, HTML chính của trang web vẫn được tải và render đầy đủ thông tin (tiêu đề, giá, tồn kho, voucher). Tuy nhiên, các request JSONP ngầm của MTOP bị chặn và sinh ra các iframe phụ mang mã trừng phạt (`iframe[src*="punish"]`).
2. **Cảnh báo lỗi giả (False Blocked Alarm)**: Trước đây, `PlaywrightAdapter._fetch_sync()` kiểm tra `has_punish_iframe` như một điều kiện chặn cứng, lập tức dừng bóc tách DOM và rơi vào vòng chờ giải captcha 15 giây.
3. **Giới hạn của NopeCHA Extension**: NopeCHA Chromium Extension hoạt động rất tốt với các loại captcha tiêu chuẩn (reCAPTCHA, Cloudflare Turnstile, hCaptcha), nhưng không hỗ trợ kéo thanh trượt bản quyền của Alibaba (`#nc_1_wrapper`, `.btn_slide`). Khi hết 15 giây chờ, adapter ném ngoại lệ `Blocked`, khiến `Scanner` hiểu nhầm là hệ thống bị chặn và tạm dừng chu kỳ cào dù dữ liệu giá đã có sẵn trên trang.
4. **Thanh trượt vật lý khi bị chuyển hướng**: Khi trang thực sự bị chuyển hướng sang trang xác minh (`punish?`, `verify/slider`), thử thách hiển thị dưới dạng thanh trượt kéo ngang cần tương tác chuột vật lý mô phỏng con người.

## Decisions

1. **Ưu tiên bóc tách DOM bằng Cookies trước (Cookie-First Priority)**:
   - Trong `PlaywrightAdapter._fetch_sync()`: Khi URL chưa bị chuyển hướng sang trang xác minh (`is_lzd_blocked == False`), adapter luôn thử gọi `_parse_lazada(page)` bằng cookies trước tiên.
   - Nếu trích xuất thành công giá hợp lệ (`price > 0`), adapter tạo và trả về đối tượng `Snapshot` ngay lập tức, bỏ qua hoàn toàn các iframe punish ngầm, không lãng phí 15 giây chờ đợi và không kích hoạt cảnh báo `Blocked` sai lệch.

2. **Cơ chế giả lập kéo chuột giải Slider Captcha (`_try_drag_slider`)**:
   - Thêm phương thức `_try_drag_slider(page) -> bool` vào `PlaywrightAdapter`.
   - Tìm kiếm các phần tử thanh trượt đặc trưng của Alibaba: `#nc_1_wrapper`, `.btn_slide`, `#nc_1_n1z`, `.slidetounlock`, `[class*="btn_slide"]`.
   - Mô phỏng hành vi kéo chuột con người (human-like drag):
     - Di chuyển chuột tới vị trí nút trượt (`page.mouse.move`).
     - Nhấn giữ chuột trái (`page.mouse.down`).
     - Di chuyển nút trượt qua nhiều bước nhỏ (10-15 bước) với độ trễ ngẫu nhiên và tốc độ giảm dần (ease-out).
     - Nhả chuột (`page.mouse.up`) và kiểm tra phản hồi thành công qua class `.nc_ok` hoặc trạng thái biến mất của slider.

3. **Phối hợp liên hoàn NopeCHA + Mouse Drag trong `_wait_for_captcha_solve`**:
   - Khi gặp thử thách xác minh, hàm `_wait_for_captcha_solve` kích hoạt `_try_drag_slider` trước. Nếu slider giải thành công, ghi nhận `quota.record_solve(1)` và quay lại cào tiếp.
   - Nếu là captcha tiêu chuẩn (reCAPTCHA, Turnstile), cửa sổ chờ 15s cho phép NopeCHA extension tự động xử lý.
   - Loại bỏ việc kiểm tra `has_punish_iframe` khỏi điều kiện phán đoán chặn cứng khi DOM chính vẫn chứa dữ liệu sản phẩm.

4. **Nạp lại Cookie tự động khi bị thách thức (`reload_cookies`)**:
   - Nếu phát hiện trang bị chuyển hướng chặn hoặc không thể trích xuất giá từ DOM, adapter tự động nạp lại cookie mới nhất từ file đĩa (`reload_cookies()`) và tải lại trang một lần để thử khôi phục trước khi đưa ra kết luận `Blocked`.

5. **Cảnh báo rõ ràng và định hướng khắc phục (`Scanner._scan_platform`)**:
   - Khi token phiên đăng nhập vẫn còn hạn nhưng gặp rào cản an ninh (x5sec/Slider) không thể vượt qua: hệ thống tạm dừng cào Lazada ở chu kỳ hiện tại để bảo vệ IP và tài khoản, đồng thời gửi thông báo chỉ dẫn người dùng làm mới layer an ninh trên Dashboard.

## Consequences

- Triệt tiêu 100% tình trạng báo lỗi `Blocked` giả khi trang Lazada đã có sẵn dữ liệu giá qua cookies.
- Tiết kiệm 15 giây độ trễ không cần thiết cho mỗi sản phẩm Lazada được cào.
- Tự động hoá việc vượt thanh trượt Alibaba slider mà NopeCHA extension không xử lý được.
- Phối hợp nhịp nhàng giữa Cookie-First, Slider Drag tự động và NopeCHA captcha solver, mang lại độ ổn định cao nhất cho crawler Lazada.
