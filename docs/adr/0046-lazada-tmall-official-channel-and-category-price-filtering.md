# 46. Lazada TMALL Official Channel Crawling and Category/Price Range Filtering

Date: 2026-10-29

## Status

Accepted. Tab TMALL ẩn, phân hệ tắt theo ADR 0055.

## Context

Trong phiên bản trước (ADR 0045), tính năng cào Lazada TMALL được triển khai dựa trên trang tìm kiếm catalog `https://www.lazada.vn/catalog/?q=tmall+tr%E1%BB%A3+gi%C3%A1`. Tuy nhiên, trang chuẩn chính thức của Lazada dành cho thương hiệu TMALL là chuyên trang LazMall:
`https://www.lazada.vn/wow/gcp/lazada/channel/vn/lazmall-channel/thuong-hieu-trung-chinh-hang`.

Trang landing page này có các đặc thù:
1. Được xây dựng dạng Single Page Application (React / Weex GCP), bao gồm các banner chiến dịch, carousel ưu đãi ("PHỤ KIỆN IPHONE18", "Xu Hướng Công Nghệ") và luồng sản phẩm cuộn vô tận ("Dành Riêng Cho Bạn").
2. Chứa nhiều ngành hàng hỗn hợp (mỹ phẩm, thời trang, đồ gia dụng, thực phẩm, công nghệ). Người dùng chỉ có nhu cầu săn deal thuộc 2 danh mục: **Thiết bị điện tử** và **Phụ kiện điện tử**.
3. Người dùng cần cấu hình linh hoạt khoảng giá mong muốn (`[tmall_min_price, tmall_max_price]`) để loại bỏ các phụ kiện lặt vặt quá rẻ hoặc các thiết bị vượt quá ngân sách săn deal.

## Decisions

1. **Cập nhật URL nguồn chính thức TMALL**:
   - Chuyển URL cào TMALL sang `https://www.lazada.vn/wow/gcp/lazada/channel/vn/lazmall-channel/thuong-hieu-trung-chinh-hang`.
   - Playwright mở trang với user agent desktop chuẩn, thực hiện auto-scroll từng đoạn (1500px x 4-5 lần) để kích hoạt tải dữ liệu feed và gom các liên kết sản phẩm (`a[href*="/products/"]`).
   - Chuẩn hóa URL protocol-relative (`//www.lazada.vn/products/...` -> `https://www.lazada.vn/products/...`) và loại bỏ query parameters để lấy canonical item URL.

2. **Cơ chế lọc danh mục 2 tầng (Electronics & Accessories)**:
   - **Tầng 1 (Lọc từ khóa tiêu đề thẻ)**: Nhận diện các từ khóa điện tử & phụ kiện điện tử (ví dụ: `sạc`, `cáp`, `tai nghe`, `chuột`, `bàn phím`, `pin dự phòng`, `loa`, `camera`, `máy tính`, `laptop`, `điện thoại`, `màn hình`, `củ sạc`, `hub`, `quạt tích điện`, `bluetooth`, `type-c`, `adapter`, `switch`, `headphone`, `smartwatch`, v.v.). Loại bỏ ngay các sản phẩm mang từ khóa mỹ phẩm (`son`, `phấn`, `kem`, `serum`, `dưỡng da`), thời trang (`váy`, `đầm`, `quần`, `áo`, `tất`, `ví da`), thực phẩm (`bánh`, `kẹo`, `trà`).
   - **Tầng 2 (Đối soát danh mục chi tiết)**: Gán danh mục chuẩn `Thiết Bị Điện Tử` hoặc `Phụ Kiện Điện Tử` dựa trên cấu trúc breadcrumb Lazada và taxonomy đã phân loại.

3. **Cấu hình khoảng giá cào & Bộ lọc thời gian thực đa tầng (Multi-tier Real-time Filtering)**:
   - Thêm `tmall_min_price: float = 100000.0` (mặc định 100.000₫) và `tmall_max_price: float | None = 20000000.0` (mặc định 20.000.000₫, hoặc None nếu không giới hạn) vào `Config`, database settings, backend API (`/api/settings`, `/api/summary`) và modal Cài đặt Dashboard.
   - **Tầng Scanner**: Khi cào sản phẩm TMALL, chỉ những sản phẩm có mức giá nằm trong khoảng `[tmall_min_price, tmall_max_price]` mới được lưu vào cơ sở dữ liệu.
   - **Tầng API (`/api/products`)**: Khi trả về danh sách sản phẩm cho frontend, hệ thống lọc thời gian thực đối với các sản phẩm mang `source == 'lazada_tmall'`. Các sản phẩm có giá nhỏ hơn `tmall_min_price`, lớn hơn `tmall_max_price`, hoặc không thuộc danh mục `("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử")` sẽ bị loại bỏ ngay lập tức.
   - **Tầng Frontend (`dashboard.html`)**: Hàm `renderTmallTable()` bổ sung điều kiện lọc giá `_tmallMinPrice` và `_tmallMaxPrice` để giao diện phản ánh chính xác ngay tức thì khi người dùng thay đổi hoặc tải lại dữ liệu.

4. **Dọn dẹp cơ sở dữ liệu tức thì & định kỳ (Immediate & Scheduled DB Purge)**:
   - **Kích hoạt tức thì**: Khi người dùng thay đổi `tmall_min_price` hoặc `tmall_max_price` qua API `POST /api/settings`, hệ thống lập tức thực thi `cleanup_invalid_tmall_products()` để xóa vĩnh viễn mọi sản phẩm TMALL trong DB vi phạm khoảng giá mới hoặc sai danh mục, không cần chờ đến phiên quét định kỳ.
   - **Quét định kỳ**: Phương thức `cleanup_invalid_tmall_products()` được tích hợp tự động vào đầu mỗi chu kỳ cào TMALL (`discover_tmall_subsidy`) trong Scanner.
   - **Thanh trừng dữ liệu cũ**: Đã thực thi dọn dẹp toàn bộ 130 sản phẩm TMALL legacy (từ truy vấn tìm kiếm cũ trước đây, gồm các mặt hàng > 30tr₫ và các mặt hàng mỹ phẩm/đời sống). Database `deals.db` chỉ giữ lại 47 sản phẩm TMALL chuẩn chỉ và hợp lệ.

## Consequences

- Tab Lazada TMALL hiển thị chính xác 100% sản phẩm thiết bị và phụ kiện điện tử nằm trong khoảng giá cấu hình của người dùng.
- Thay đổi cấu hình giá có hiệu lực ngay lập tức trên UI, API và dọn dẹp triệt để trong cơ sở dữ liệu.
- Loại bỏ hoàn toàn nguy cơ hiển thị sản phẩm ngoài tầm giá do cache hoặc sản phẩm legacy tồn dư từ phiên bản trước.
