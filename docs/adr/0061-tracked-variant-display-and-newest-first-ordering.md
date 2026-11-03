# ADR 0061: Hiển thị Phân loại Đang Theo Dõi và Ưu Tiên Sản Phẩm Mới Thêm (Tracked Variant Display and Newest-First Ordering)

## Trạng thái
Đã chấp thuận (Accepted)

## Bối cảnh
1. Ở tab *Sản phẩm theo dõi*, cột *Sản phẩm* trước đây hiển thị đường dẫn danh mục (ví dụ `📂 Linh kiện & phụ kiện điện tử > Phụ kiện Máy tính > Bàn phím & chuột > Bàn phím cơ bản`). Thông tin này chiếm diện tích nhưng không mang lại giá trị cho người săn sale, trong khi người dùng cần biết chính xác mức giá hiển thị là của phân loại/option nào (màu sắc, switch, cấu hình).
2. Với các sản phẩm đơn lẻ (Single-SKU) chỉ có 1 option duy nhất (như CPU Ryzen 7500F hay Ống kính Canon RF 24-105mm), việc hiển thị dòng phân loại là thừa thãi và gây rối mắt.
3. Thứ tự hiển thị mặc định của bảng trước đây theo `p.platform, p.id ASC` (tăng dần), khiến mỗi khi người dùng dán link theo dõi sản phẩm mới thì sản phẩm đó luôn bị đẩy xuống đáy bảng, gây khó khăn cho việc theo dõi tiến độ cào dữ liệu ban đầu.

## Quyết định
1. **Thay thế dòng danh mục bằng Tên Phân loại đang lấy giá**:
   - Truy vấn SQL trong `get_products_with_latest_price` được mở rộng để lấy `active_variant_name` (từ `main_variant_id` hoặc SKU rẻ nhất còn hàng gần nhất) và `variants_count`.
   - API `/api/products` chuẩn hóa `variant_name`, `variants_count` và `clean_name` (đã lược bỏ hậu tố ngoặc đơn của option để tránh trùng lặp giữa tiêu đề và dòng phân loại).
   - Giao diện: Nếu `variants_count > 1 && variant_name`, hiển thị nhãn `🏷️ Phân loại: [Tên option]`. Nếu `variants_count <= 1` (sản phẩm 1 option), ẩn hoàn toàn dòng phụ này.
2. **Sắp xếp mặc định: Sản phẩm mới nhất lên trên cùng (Newest-First)**:
   - Thay đổi câu lệnh truy vấn `get_products_with_latest_price` từ `ORDER BY p.platform, p.id` thành `ORDER BY p.id DESC`.
   - Trong `dashboard.html` (`renderTable()`), khi chế độ sắp xếp là mặc định (`currentSortTracked === 'default'`), luôn ưu tiên sắp xếp theo `(b.id || 0) - (a.id || 0)`.
   - Người dùng vừa thêm link mới sẽ thấy sản phẩm xuất hiện ngay tại dòng đầu tiên của bảng.

## Hệ quả
- **Tích cực**:
  - Giao diện trực quan, minh bạch: người dùng biết chính xác giá theo dõi thuộc option nào.
  - Tối ưu trải nghiệm: sản phẩm mới thêm xuất hiện ngay đầu trang, dễ theo dõi kết quả quét tức thời.
  - Tinh gọn cho sản phẩm đơn option.
- **Tiêu cực**: Không còn hiển thị đường dẫn danh mục breadcrumb trong bảng theo dõi (được đánh giá là không cần thiết trong nghiệp vụ săn deal).
