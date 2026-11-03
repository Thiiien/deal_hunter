# 40. Công tắc bật/tắt quét tự động từng phân hệ (Theo từ khóa, Siêu Sale, Săn lỗi giá)

## Trạng thái

Accepted. Từ ADR 0055 cả bốn phân hệ đều tắt theo mặc định.

## Bối cảnh
Hệ thống Deal Hunter vận hành 4 phân hệ quét ngầm độc lập trong vòng lặp `scan_due()`:
1. Sản phẩm theo dõi (`scan_tracked_products`)
2. Theo từ khóa (`run_keyword_search`)
3. Siêu Sale & Flash Sale (`discover_flash_sale`)
4. Săn lỗi giá (`scan_price_errors`)

Trước đây, người dùng chỉ có thể điều chỉnh tần suất quét (phút) nhưng không thể tắt hẳn việc quét tự động của từng phân hệ phụ (Từ khóa, Siêu Sale, Lỗi giá). Khi tài nguyên máy hạn chế hoặc người dùng muốn tiết kiệm lượt giải Captcha/bảo vệ cookies đăng nhập của sàn khỏi việc quét diện rộng liên tục, họ buộc phải nhập tần suất rất lớn (như 1440 phút). Ngoài ra, không có cách trực quan để tạm dừng riêng lẻ từng phân hệ mà vẫn giữ nguyên chu kỳ quét sản phẩm chính.

## Quyết định kiến trúc

1. **Lưu trữ trạng thái phân hệ trong SQLite:**
   - Bổ sung 3 khóa trạng thái trong bảng `settings`: `keyword_scan_enabled`, `megasale_scan_enabled`, `price_error_scan_enabled`.
   - Giá trị lưu trữ: `"1"` (Bật) hoặc `"0"` (Tắt). Mặc định là `"1"` để đảm bảo tương thích ngược.

2. **Cập nhật Config và Scheduler (`Config`, `run.py`, `scanner.py`):**
   - Đính kèm 3 cờ boolean vào `Config`: `keyword_scan_enabled`, `megasale_scan_enabled`, `price_error_scan_enabled`.
   - Trong `Scanner.scan_due()`, kiểm tra cờ tương ứng trước khi tính toán chu kỳ và thực thi tác vụ quét. Nếu bị tắt, hệ thống bỏ qua không chạy tác vụ nền đó.

3. **Bảo toàn tính năng quét thủ công:**
   - Việc tắt quét tự động chỉ áp dụng cho tiến trình hẹn giờ chạy ngầm.
   - Các nút bấm cào/quét thủ công trên từng tab (*"⚡ Cào Shopee"*, *"⚡ Cào Lazada"*, *"⚡ Quét Săn Lỗi Giá Ngay"*, *"🎯 Săn giá thấp nhất"*) vẫn kích hoạt bình thường theo yêu cầu chủ động của người dùng.

4. **Giao diện Modal Cài đặt trực quan ([dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Thêm checkbox/toggle bật-tắt riêng biệt cho từng phân hệ cạnh ô nhập tần suất.
   - Khi gạt sang TẮT, ô nhập phút tự động bị vô hiệu hóa (disabled / làm mờ) kèm nhãn trạng thái *"⏸️ Đã tạm dừng"*.

## Hệ quả
- Người dùng hoàn toàn chủ động điều phối tài nguyên hệ thống, tránh cào sàn không cần thiết.
- Trạng thái được duy trì xuyên suốt qua các lần khởi động lại container Docker.
