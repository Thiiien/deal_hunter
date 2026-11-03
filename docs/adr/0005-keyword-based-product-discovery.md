# ADR 0005: Cơ Chế Khám Phá Sản Phẩm Theo Từ Khóa (Discover & Track)

## Trạng thái

Accepted. Quét nền theo từ khóa đang tắt theo ADR 0055; tìm thủ công vẫn dùng được.

## Bối cảnh

Người dùng muốn theo dõi deal của một dòng sản phẩm bằng từ khóa (ví dụ: "chuột logitech g102", "phân nền senda") thay vì phải tự tìm và dán từng link sản phẩm cụ thể.

## Quyết định

Áp dụng mô hình **Discover & Track (Khám phá và Theo dõi)**:
1. Khi người dùng nhập từ khóa qua Telegram (`/timkiem <từ khóa>`) hoặc Web Dashboard (`POST /api/search`), adapter sẽ thực hiện tìm kiếm trên sàn với bộ lọc sắp xếp theo bán chạy (`sortBy=sales`).
2. Trích xuất **Top 5 sản phẩm** bán chạy và uy tín nhất từ trang 1 kết quả tìm kiếm.
3. Tự động thêm các URL sản phẩm này vào bảng `products` (bảng theo dõi hiện có của SQLite).
4. Giữ nguyên 100% thuật toán phát hiện deal trong `detector.py`: mỗi sản phẩm được tích lũy lịch sử giá độc lập và chỉ kết luận "Deal thật" khi giá giảm ≥ 30% so với **giá trung vị 30 ngày của chính sản phẩm đó**.

## Các phương án đã cân nhắc

- **So sánh chéo giá giữa các shop (Cross-shop deal comparison)**:
  - *Nhược điểm*: Khi tìm theo từ khóa, kết quả trên sàn lẫn lộn hàng nhái, hàng cũ, hoặc phụ kiện (ví dụ tìm "iPhone" ra ốp lưng giá 20k). Việc so sánh chéo giá giữa các shop khác nhau sẽ gây báo động giả (false positive) liên tục.
- **Quét trang tìm kiếm định kỳ mỗi chu kỳ thay vì quét link sản phẩm**:
  - *Nhược điểm*: Kết quả trang tìm kiếm thay đổi liên tục, tốn nhiều request và phá vỡ cấu trúc lưu trữ lịch sử giá theo `item_key`.
- **Mô hình Discover & Track (Đã chọn)**:
  - Tách bạch rõ ràng: Từ khóa dùng cho tầng Khám phá (Discovery), sau đó chuyển giao về tầng Theo dõi (Tracking) sẵn có. Tận dụng tối đa mã nguồn hiện có, không tạo thêm bảng DB mới.

## Hệ quả

- `BaseAdapter` bổ sung phương thức `search(keyword: str, limit: int = 5) -> list[str]`.
- `MockAdapter` và `FeedAdapter` hỗ trợ `search` phục vụ kiểm thử tự động không cần mạng.
- Telegram bot có thêm lệnh `/timkiem <keyword>`.
- Web dashboard bổ sung API `/api/search` và ô nhập từ khóa.
- Giới hạn trần Top 5 giúp kiểm soát chặt chẽ tải của crawler và hạn ngạch giải captcha.
