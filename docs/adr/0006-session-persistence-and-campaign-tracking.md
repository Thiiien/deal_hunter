# ADR 0006: Lưu Trữ Phiên Đăng Nhập (Cookies) và Theo Dõi Đợt Sale (Campaigns)

## Bối cảnh

1. Các sàn TMĐT (Shopee, Lazada) áp dụng cơ chế chống bot chặt chẽ với khách vãng lai (guest traffic), thường xuyên chuyển hướng sang trang captcha hoặc trang đăng nhập.
2. Giá sản phẩm có sự biến động lớn theo các chiến dịch khuyến mãi (Mega Sale ngày đôi, Payday lương về, Flash Sale khung giờ). Người dùng cần phân loại sản phẩm theo ngành hàng và phân tích biến động giá theo từng đợt sale.

## Quyết định

1. **Cơ chế lưu trữ phiên đăng nhập (Cookies Persistence)**:
   - Cung cấp script chạy trực tiếp trên máy host (`login.py` / `deal_hunter.login`), mở trình duyệt Chrome có giao diện thật (headful) để người dùng đăng nhập bằng QR code hoặc OTP.
   - Khi đăng nhập xong, script trích xuất toàn bộ cookies vào file `data/cookies.json` (nằm trong thư mục được mount trực tiếp vào Docker).
   - `PlaywrightAdapter` khi khởi động trong Docker sẽ tự động nạp cookies từ `data/cookies.json` vào browser context thông qua `add_cookies()`.

2. **Tự động nhận diện Đợt Sale (Sale Campaign)**:
   - Xây dựng module `deal_hunter.campaign` nhận diện lịch sale chuẩn của sàn TMĐT Việt Nam:
     - *Mega Sale ngày đôi* (1.1, 2.2, ..., 11.11, 12.12): từ 18:00 ngày D-1 đến 23:59 ngày D+1.
     - *Payday (Lương về)*: từ 18:00 ngày 14 đến 23:59 ngày 16 (Payday 15) và từ 18:00 ngày 24 đến 23:59 ngày 26 (Payday 25).
     - *Flash Sale*: các khung giờ vàng hàng ngày (0h-2h, 9h-11h, 12h-14h, 21h-23h).
   - Lưu trữ tên đợt sale `campaign` vào từng bản ghi `price_history` khi quét.

3. **Phân loại danh mục sản phẩm (Category)**:
   - Tự động bóc tách breadcrumb ngành hàng trên trang sản phẩm khi quét (ví dụ: `Thiết Bị Điện Tử > Chuột & Bàn Phím`).
   - Lưu vào cột `category` trong bảng `products` của SQLite.

4. **Giữ nguyên thuật toán Deal thật**:
   - Vẫn so sánh giá hiện tại với trung vị 30 ngày (Median 30d) của chính sản phẩm để ngăn chặn chiêu trò tăng giá ảo trước đợt sale.
   - Gắn nhãn đợt sale nổi bật vào thông báo Telegram và Web Dashboard (ví dụ: `🔥 [11.11 MEGA SALE] Chuột Logitech...`).

## Hệ quả

- `Snapshot` thêm trường `category: str = ""`.
- `products` thêm cột `category TEXT`.
- `price_history` thêm cột `campaign TEXT`.
- Bổ sung bảng `campaigns` để hỗ trợ thêm các đợt sale tùy chỉnh trong tương lai.
- Thêm file thực thi `login.py` cho phép người dùng đăng nhập tài khoản một lần trên máy tính.
- `PlaywrightAdapter` tự động load `cookies.json` khi khởi động, giảm thiểu tối đa tình trạng bị chặn.
