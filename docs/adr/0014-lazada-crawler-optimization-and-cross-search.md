# 14. Tối ưu hóa Crawler Lazada và Mở rộng tìm kiếm liên sàn (Lazada Crawler Optimization & Cross Search)

Ngày: 2026-10-20

## Bối cảnh
Sau khi tính năng bóc tách sản phẩm và cào Flash Sale của Lazada hoạt động ổn định, hệ thống cần được tối ưu hóa ở 4 khía cạnh chính:
1. **Tốc độ cào link chi tiết sản phẩm (PDP):** Trang Lazada tải rất nhiều ảnh chất lượng cao, video ngắn, font chữ và các script tracking phân tích (Alilog, aplus, itrace), khiến việc fetch mỗi trang mất từ 4–6 giây.
2. **Độ phủ các đợt Sale:** Nguồn Flash Sale trang chủ chỉ chứa ~15–40 deal. Cần kết hợp thêm trang chuyên đề `/tag/flash-sale/` để cào được số lượng deal lớn (≥ 30 deal) đa dạng mọi ngành hàng.
3. **Mở rộng công cụ tìm kiếm (`search`):** Trước đây hàm `search()` chỉ tìm kiếm trên Shopee (`site:shopee.vn`). Khi người dùng muốn tìm kiếm từ khóa hoặc so giá một món hàng Lazada giữa các shop khác nhau, hệ thống cần tìm kiếm được trên cả Lazada (`lazada.vn/products/`).
4. **Nhận diện voucher Lazada đa dạng:** Cần tối ưu nhận diện nhiều biến thể coupon của Lazada (giảm theo %, giảm số tiền cố định, nhãn trợ giá) để tính chính xác giá sau voucher (`final_price`).

## Quyết định kiến trúc

1. **Chặn tài nguyên nặng khi tải trang Lazada (Resource Blocking):**
   - Thiết lập `page.route` khi duyệt trang Lazada để hủy (abort) các request thuộc loại: `image`, `media`, `font` và các domain/tracking script phân tích nặng (`alilog`, `aplus`, `itrace`).
   - Giúp thời gian tải trang giảm từ ~5s xuống còn ~1.2–1.5s, giảm đáng kể nguy cơ quá tải bộ nhớ trình duyệt Chromium trong container Docker.

2. **Cào mở rộng danh mục Flash Sale Lazada:**
   - Trong `_crawl_lazada_flash_sale_sync`, nếu số lượng deal trích xuất từ widget Flash Sale chưa đạt chỉ tiêu `limit`, crawler sẽ tiếp tục cuộn trang và tải bổ sung danh sách sản phẩm từ `https://www.lazada.vn/tag/flash-sale/?q=flash+sale`.
   - Giữ nguyên bộ lọc tồn kho và bóc tách `clickTrackInfo` để đảm bảo dữ liệu chuẩn xác và loại bỏ hàng hết hàng.

3. **Mở rộng tìm kiếm đa sàn trong `_search_sync`:**
   - Hàm `_add(url)` tiếp nhận cả URL sản phẩm Shopee (`shopee.vn/product/` hoặc `-i.`) và Lazada (`lazada.vn/products/`).
   - Bổ sung truy vấn `site:lazada.vn/products/ {norm}` vào các công cụ tìm kiếm (Bing, DuckDuckGo) để đối sánh chéo đa shop và đa sàn khi người dùng yêu cầu so giá hoặc tìm sản phẩm theo từ khóa.

4. **Nâng cấp độ nhạy bóc tách Voucher Lazada:**
   - Mở rộng regex quét các nhãn khuyến mãi trên Lazada: `Giảm \d+k`, `Voucher \d+k`, `-\d+%` từ các selector `.pdp-mod-voucher`, `.voucher-tag`, `.pdp-vouchers`.
   - Tự động trừ chiết khấu voucher để tính `final_price`.

## Trạng thái
Đã thống nhất qua quy trình `/grill-with-docs` và phê duyệt triển khai.
