# Kiến trúc gói mô-đun hóa theo trách nhiệm đơn

## Trạng thái

Accepted.

Thay vì gom toàn bộ logic vào `core.py` nguyên khối, chúng tôi tổ chức mã nguồn thành package `src/deal_hunter/` với các mô-đun tách biệt theo từng trách nhiệm: `db.py` (schema SQLite), `models.py` (dataclass Snapshot/Deal), `detector.py` (thuật toán phát hiện deal - pure functions không có side effect), `scanner.py` (vòng lặp quét, truy vấn DB), `alerter.py` (logic chống lặp cảnh báo), `quota.py` (giám sát NopeCHA), `notifier.py` (gửi Telegram), `affiliate.py` (tạo link), và `adapters/` riêng. Quyết định này cho phép test từng mô-đun độc lập (đặc biệt `detector.py` là pure function testable không cần mock DB), giảm rủi ro khi debug và chỉnh sửa thuật toán phát hiện deal mà không đụng đến luồng crawler hay Telegram.

## Considered Options

- **`core.py` nguyên khối** (mô tả ban đầu trong đặc tả): nhanh để bắt đầu nhưng mọi thay đổi nhỏ buộc đọc và hiểu toàn bộ file; không thể test thuật toán trung vị 30 ngày mà không khởi động DB.
- **Mô-đun hóa theo trách nhiệm đơn** *(đã chọn)*: thêm một chút cấu trúc ban đầu nhưng mỗi file nhỏ, có mục đích rõ ràng, dễ debug và dễ thêm adapter mới mà không rủi ro làm hỏng logic hiện có.

## Consequences

`detector.py` nhận `(prices: list[float], current_price: float, min_discount: float, rating: float | None, min_rating: float, in_stock: bool | None)` và trả về `DealStatus` enum - hoàn toàn không phụ thuộc DB hay config global. `scanner.py` là lớp duy nhất kết nối DB với detector. Không dùng ORM (sqlite3 stdlib) và không dùng Pydantic (`@dataclass` stdlib) để giữ dependency tối thiểu.
