# 38. Kiến trúc nền tảng dữ liệu đa biến thể và cơ chế theo dõi vi sai (Delta Tracking)

## Trạng thái

Accepted.

## Bối cảnh
Người dùng cần theo dõi một sản phẩm ở **biến thể cụ thể (Biến thể chính)** trên sàn thương mại điện tử (Shopee, Lazada). Khi biến thể đó hết hàng, hệ thống cần tự động đánh giá các **biến thể thay thế** trong cùng một listing để đề xuất biến thể còn hàng có giá hiệu dụng rẻ nhất theo chính sách (xem tài liệu [VARIANT_FALLBACK.md](file:///c:/Users/pvthien/source/deal_hunter/.docs/VARIANT_FALLBACK.md)).

Trước đây, hệ thống Deal Hunter chỉ lưu trữ duy nhất 1 mức giá đại diện cho mỗi sản phẩm trong bảng `price_history`. Dù crawler đã có thể bóc tách toàn bộ danh sách SKU từ mạng và DOM, toàn bộ danh mục biến thể, giá gốc, tồn kho từng phân loại đều bị tiêu biến sau khi chọn ra 1 biến thể duy nhất. Nếu lưu toàn bộ lịch sử 20-30 biến thể sau mỗi chu kỳ quét định kỳ (8-15 phút), cơ sở dữ liệu SQLite sẽ bị phình to hàng trăm nghìn dòng chỉ sau vài ngày.

## Quyết định kiến trúc

1. **Mô hình thực thể biến thể (Schema & Migrations trong [db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - Thêm bảng `variants`: lưu trữ danh mục biến thể hiện có của từng sản phẩm (`id`, `product_id`, `variant_key`, `name`, `attrs`, `active`, `first_seen`, `last_seen`).
   - Thêm cột `main_variant_id` trong bảng `products` để xác định biến thể người dùng chủ đích theo dõi.
   - Thêm bảng `variant_history`: lưu vết biến động giá và kho theo từng biến thể (`variant_id`, `price`, `list_price`, `stock_state`, `stock_qty`, `stock_source`, `ts`).
   - Thêm bảng `fallback_rules`: cấu hình chính sách thay thế cho từng sản phẩm (`product_id`, `enabled`, `mode`, `key_attrs`, `selected_variants`, `price_ceiling_pct`, `max_price`).
   - Thêm bảng `fallback_events`: ghi nhận các sự kiện chuyển đổi biến thể thay thế phục vụ báo cáo và kiểm tra.

2. **Cơ chế theo dõi vi sai (Delta Tracking):**
   - Không chèn dòng mới vào `variant_history` nếu giá bán (`price`), giá niêm yết (`list_price`) và trạng thái kho (`stock_state`) của biến thể đó không có sự thay đổi so với bản ghi gần nhất.
   - Tiết kiệm hơn 90% dung lượng ghi đĩa và đảm bảo hiệu năng truy vấn nhanh của SQLite.

3. **Gán Biến thể chính thông minh khi nạp URL:**
   - Nếu URL người dùng nhập có chứa mã phân loại (ví dụ: Lazada có `-s<skuid>.html`, Shopee có `modelid`), hệ thống trích xuất mã này và tự động gán làm `main_variant_id`.
   - Nếu URL là link chung, biến thể còn hàng có giá rẻ nhất ban đầu được chọn làm `main_variant_id`.

4. **Nâng cấp Adapters trích xuất danh sách biến thể đầy đủ ([models.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/models.py), [playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Bổ sung cấu trúc `VariantInfo` trong `Snapshot` chứa danh sách tất cả các phân loại bóc tách được (Shopee `models`, Lazada `skuInfos`).

5. **Lệnh Telegram hỗ trợ người dùng (`/bienthe <id>` trong [bot.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/bot.py)):**
   - Cho phép người dùng xem nhanh toàn bộ danh sách biến thể, tình trạng còn/hết hàng và giá của từng phân loại kèm đánh dấu biến thể chính đang theo dõi.

## Hệ quả
- Hệ thống có nền tảng dữ liệu vững chắc về từng biến thể, cho phép chuẩn bị triển khai logic máy trạng thái xác nhận hết hàng và cảnh báo thay thế tự động ở giai đoạn tiếp theo.
- Tối ưu hóa lưu trữ, không làm nặng database.
