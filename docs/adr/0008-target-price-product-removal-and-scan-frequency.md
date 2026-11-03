# ADR 0008: Giá Mong Muốn, Hủy Theo Dõi Sản Phẩm và Cài Đặt Tần Suất Quét

## Trạng thái

Accepted. Các lệnh bot trong ADR này được thay bởi ADR 0042 (`/setgia`, `/xoa`, `/tansuat`).

## Bối cảnh

Người dùng cần:
1. Thiết lập mức giá mong muốn (target price) cho từng sản phẩm cụ thể, để khi giá của sản phẩm giảm xuống nhỏ hơn hoặc bằng mức giá này thì Deal Hunter lập tức gửi cảnh báo về Telegram (kể cả khi sản phẩm mới theo dõi và chưa đủ dữ liệu tính toán trung vị 30 ngày).
2. Xóa các sản phẩm không còn nhu cầu theo dõi nữa để làm sạch danh sách và tiết kiệm tài nguyên quét.
3. Cài đặt và điều chỉnh tần suất quét giá tự động (số phút nghỉ giữa các chu kỳ) trực tiếp từ giao diện web hoặc Telegram bot mà không cần sửa file cấu hình `.env` hay khởi động lại container.

## Quyết định

1. **Giá mong muốn (Target Price)**:
   - Thêm cột `target_price REAL` vào bảng `products`.
   - Bổ sung API `PATCH /api/products/<int:pid>/target_price` cho phép đặt hoặc xóa giá mong muốn.
   - Khi cập nhật giá mong muốn, hệ thống tự động xóa bản ghi trong bảng `alerts` để đảm bảo chu kỳ quét kế tiếp sẽ phát cảnh báo ngay khi thỏa điều kiện `current_price <= target_price`.
   - Trong `Scanner._scan_platform()`: Nếu sản phẩm có `target_price` và `snapshot.price <= target_price`, kích hoạt cảnh báo chuyên biệt `🎯 ĐẠT GIÁ MONG MUỐN!` gửi qua Telegram kèm nút Affiliate "Mua ngay".

2. **Hủy theo dõi sản phẩm (Product Removal)**:
   - Bổ sung hàm `db.delete_product(product_id)` xóa triệt để sản phẩm khỏi bảng `products`, bảng `price_history` và bảng `alerts`.
   - Bổ sung API `DELETE /api/products/<int:pid>`.
   - Bổ sung nút 🗑️ Xóa trên bảng điều khiển giao diện web kèm hộp thoại xác nhận.

3. **Cài đặt tần suất quét (Dynamic Scan Interval)**:
   - Tạo bảng `settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)` trong SQLite để lưu trữ cấu hình động của hệ thống.
   - Bổ sung API `GET /api/settings` và `POST /api/settings` để đọc/ghi giá trị `scan_interval_min`.
   - Cập nhật vòng lặp lập lịch trong `run.py` chia nhỏ thời gian nghỉ thành các bước kiểm tra 2 giây, cho phép cập nhật nhịp quét ngay lập tức khi người dùng đổi tần suất mà không cần đợi hết chu kỳ ngủ cũ.
   - Thêm modal `⚙️ Cài đặt` trên thanh tiêu đề web dashboard và hiển thị tần suất quét hiện tại trên thẻ thống kê.
   - Bổ sung các lệnh Telegram tương ứng: `/giamongmuon`, `/xoasp`, `/tansuat`.

## Hệ quả

- Người dùng có thể kiểm soát hoàn toàn danh sách sản phẩm theo dõi và ngưỡng giá kích hoạt mua hàng.
- Tần suất quét có thể thay đổi linh hoạt theo nhu cầu (ví dụ: quét 15 phút/lần trong ngày Siêu Sale, hoặc 120 phút/lần trong ngày thường).
- Không phát sinh thư viện ngoài, tối giản code theo nguyên lý Ponytail, đảm bảo an toàn đa luồng thông qua SQLite `threading.RLock()`.
