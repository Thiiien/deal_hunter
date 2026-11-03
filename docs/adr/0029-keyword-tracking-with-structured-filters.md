# 29. Kiến trúc theo dõi sản phẩm theo từ khóa và bộ lọc nâng cao

## Trạng thái

Accepted. Quét nền theo từ khóa đang tắt theo ADR 0055.

## Bối cảnh
Trước đây, Deal Hunter hỗ trợ tìm kiếm sản phẩm theo từ khóa (`discover_keyword`) nhưng chỉ chọn sản phẩm có giá thấp nhất hoặc thêm hàng loạt sản phẩm mà không có tiêu chí phân loại nguồn gốc, kho vận và dịch vụ. Người dùng có nhu cầu lọc sâu:
1. Chỉ muốn mua hàng xuất xứ Việt Nam hoặc vận chuyển từ kho Việt Nam để nhận hàng nhanh.
2. Cần lọc các shop chính hãng hoặc dịch vụ uy tín (LazMall, Tmall, Freeship, Giao hỏa tốc, Xử lý bởi Lazada).
3. Cần cơ chế lưu trữ từ khóa theo dõi định kỳ, ghi nhớ bộ lọc và tránh quét lặp các sản phẩm không phù hợp.

## Quyết định kiến trúc

1. **Tận dụng nền tảng Playwright hiện có ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Không cài thêm Selenium. Tích hợp trực tiếp vào PlaywrightAdapter với tính năng stealth, quản lý session cookie và tự động giải captcha.
   - **Shopee**: Gắn `locations=-1` (Việt Nam) hoặc `locations=-2` (Nước ngoài) vào URL tìm kiếm kết hợp bóc tách `shop_location` từ payload API `search_items`.
   - **Lazada**: Lazada không hỗ trợ query param `location=Vietnam` trên URL catalog (gắn vào sẽ khiến giao diện catalog trả về 0 kết quả). Thay vào đó, PlaywrightAdapter bóc tách thẻ sản phẩm trên trang tìm kiếm (mỗi card đều hiển thị rõ tỉnh/thành hoặc quốc gia như "Thành phố Hồ Chí Minh", "Hà Nội", "China", "Hong Kong"), tiền lọc ngay trên search card và lưu vào bộ nhớ cache vị trí `_item_locations[url]`.
   - **Bóc tách sâu PDP**:
     - Kế thừa vị trí đã nhận diện từ thẻ tìm kiếm (`_item_locations`).
     - Tự động nhận diện bổ sung từ thông tin shop (`Cửa hàng nước ngoài`, `Quốc tế` -> `Nước ngoài`) và tùy chọn vận chuyển (`Đối với hàng nội địa`, `tracking.core.country == 'VN'` -> `Việt Nam`).

2. **Cơ chế phân loại và bộ lọc độc lập ([classifier.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/classifier.py)):**
   - Hỗ trợ 3 nhóm tùy chọn chuẩn hóa cho Xuất xứ & Vận chuyển từ:
     - `Việt Nam` (Trong nước: đối soát đầy đủ 18 tỉnh thành và các tên viết tắt/không dấu).
     - `Nước ngoài` (Quốc tế: China, Hong Kong, South Korea, US, Japan...).
     - `Mặc định` (Tất cả / Bất kỳ nếu người dùng không chọn tiêu chí lọc vị trí).
   - Cơ chế dự phòng khi `ships_from` chưa đủ rõ ràng: tự động đối soát chéo qua `shop_country`, `origin` và nhãn loại shop để tránh loại nhầm sản phẩm nội địa.
   - Loại shop: `Mọi shop` / `Chính hãng (Mall)` / `Shop quốc tế`.
   - Bộ lọc Dịch vụ & Khuyến mãi (14 mã theo Lazada): `sale_cuoi_thang`, `lazflash`, `bundle`, `fbl`, `hoa_toc`, `voucher_max`, `lazmall`, `tmall`, `mua3`, `giao_trong_ngay`, `giao_nhanh_24h`, `cod`, `freeship`, `xu`.
   - Quy tắc thẩm định:
     - Nếu bất kỳ điều kiện nào **Sai** -> Loại.
     - Mọi điều kiện **Khớp** -> Giữ, gán `verified=1`.
     - Điều kiện **Chưa rõ** (thiếu thông tin) -> Mặc định loại; nếu bật `KEYWORD_INCLUDE_UNKNOWN=1` thì giữ và gán `verified=0` (kèm nhãn cảnh báo).
   - Khi người dùng bấm quét thủ công một từ khóa cụ thể: tự động làm mới bộ nhớ đệm `rejected_items` của từ khóa đó.

3. **Mô hình dữ liệu cơ sở dữ liệu ([db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - Bảng `keywords`: lưu từ khóa, sàn, trạng thái, các trường bộ lọc và thống kê lần quét gần nhất.
   - Bảng `keyword_products`: bảng liên kết N-N giữa từ khóa và sản phẩm (`keyword_id`, `product_id`, `verified`, `matched_at`), ngăn ngừa xung đột khi một sản phẩm khớp nhiều từ khóa.
   - Bảng `rejected_items`: lưu cache sản phẩm bị loại trong 7 ngày (`platform`, `item_key`, `keyword_id`, `reason`, `ts`). Tự động xóa cache của từ khóa khi người dùng cập nhật bộ lọc.
   - Mở rộng bảng `products`: thêm `origin`, `shop_country`, `ships_from`, `services`, `verified`.

4. **Tương tác người dùng & Kênh thông báo ([web.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/web.py), [bot.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/bot.py)):**
   - Tab "Theo từ khóa" trên Web Dashboard: quản lý thêm/xóa/bật/tắt từ khóa, tìm kiếm tức thì, lọc bảng sản phẩm khớp và xem trạng thái xác minh.
   - Lệnh Telegram Bot:
     - `/tukhoa <từ khóa>`: thêm nhanh với bộ lọc mặc định Việt Nam, gửi kèm nút Inline mở Dashboard tùy chỉnh.
     - `/dstukhoa`: xem danh sách từ khóa đang theo dõi và số lượng deal bắt được.
   - Tự động quét lại định kỳ mỗi `KEYWORD_INTERVAL_MIN` phút (mặc định 180 phút).

## Hệ quả
- Người dùng có thể theo dõi tự động bất kỳ thị trường ngách nào theo từ khóa kèm tiêu chuẩn lọc chất lượng khắt khe.
- Hệ thống tiết kiệm băng thông và hạn chế bị sàn chặn nhờ bộ nhớ đệm từ chối (`rejected_items`) và lọc URL thông minh.
