# 15. Tìm kiếm từ khóa liên sàn và tối ưu bóc tách danh mục Lazada (Cross-Platform Keyword Search)

Ngày: 2026-10-20

## Bối cảnh
Trước đây, chức năng tìm kiếm sản phẩm theo từ khóa (`search()`) chỉ hoạt động cho Shopee:
1. Trong `PlaywrightAdapter._search_sync`, luồng tìm kiếm trực tiếp (bước 1) chỉ gửi request tới `https://shopee.vn/search?keyword=...`. Khi Shopee trả về đủ số lượng sản phẩm (`limit`), hàm lập tức return sớm mà không bao giờ tìm kiếm trên Lazada.
2. Bước 2 (fallback qua Search Engine Bing / DuckDuckGo) chứa các query `site:lazada.vn/products/` nhưng không bao giờ được kích hoạt do bước 1 luôn tìm thấy sản phẩm trên Shopee.
3. API endpoint `POST /api/search` và hàm `Scanner.discover_keyword` không tiếp nhận tham số nền tảng `platform`.
4. Trên giao diện Dashboard, ô tìm kiếm từ khóa không gửi bộ lọc sàn đang chọn (`currentPlatformFilter`), dẫn đến việc tìm kiếm trên tab Lazada không hiển thị kết quả từ Lazada.

## Quyết định kiến trúc

1. **Bóc tách trực tiếp danh mục tìm kiếm Lazada (Lazada Direct Catalog Search):**
   - Bổ sung bước cào trực tiếp qua URL catalog chuẩn của Lazada: `https://www.lazada.vn/catalog/?q={quote_plus(keyword)}`.
   - Sử dụng Playwright trích xuất các liên kết sản phẩm hợp lệ có định dạng `a[href*='/products/']` kết thúc bằng `-i...html`.
   - Nâng cấp `BaseAdapter.parse_item_key` để nhận diện cả mã sản phẩm Lazada không có mã shop `-i<itemid>.html` (ví dụ: `pdp-i260193102.html` -> item_key `260193102`), tránh tạo chuỗi hash ngẫu nhiên.

2. **Hỗ trợ tham số `platform` toàn diện:**
   - Cập nhật chữ ký `BaseAdapter.search(keyword, limit=5, platform="all")`, `MockAdapter.search`, `PlaywrightAdapter.search`, và `Scanner.discover_keyword(..., platform="all")`.
   - Khi `platform == "shopee"`: Chỉ tìm kiếm trên Shopee.
   - Khi `platform == "lazada"`: Chỉ tìm kiếm trên Lazada.
   - Khi `platform == "all"`: Tìm kiếm song song trên cả Shopee và Lazada, sau đó đan xen (interleave) các kết quả để đảm bảo độ phủ cân bằng.

3. **Cơ chế so sánh giá thấp nhất liên sàn (`lowest_only=True`):**
   - Khi người dùng ở chế độ "Tất cả sàn" và chọn "Săn giá thấp nhất":
     - Hệ thống thu thập các ứng viên hàng đầu từ cả Shopee và Lazada.
     - Tải thông tin chi tiết (snapshot), lọc sản phẩm còn hàng (`stock is not False`), loại trừ phụ kiện rác (anti-accessory filter).
     - Áp dụng các voucher giảm giá (nếu có) để tính giá thực trả (`final_price`).
     - Tự động chọn ra sản phẩm có giá thấp nhất trên toàn bộ các sàn và lưu vào danh sách theo dõi.

4. **Đồng bộ bộ lọc sàn trên giao diện Dashboard:**
   - Hàm `searchKeyword()` trên giao diện đọc trạng thái `currentPlatformFilter` (`all`, `shopee`, `lazada`) và gửi kèm trong payload `POST /api/search`.
   - Tự động thay đổi gợi ý (placeholder) của ô nhập từ khóa tương ứng với sàn đang chọn (ví dụ: hiển thị icon 🔵 Lazada khi đang lọc Lazada).
   - Hiển thị nhãn sàn (`[Lazada]`, `[Shopee]`) trên thông báo toast khi tìm thấy deal giá thấp nhất.

## Trạng thái
Đã hoàn thành kiểm thử đơn vị và triển khai trên toàn bộ hệ thống.
Từ ADR 0055 và 0057 (01/11/2026): cào Siêu Sale chỉ chạy khi người dùng bấm nút và không phát cảnh báo Telegram; quét nền theo từ khóa đang tắt.
