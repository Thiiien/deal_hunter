# 32. Bổ sung lệnh /listtracked cho Bot Telegram quản lý tab Sản phẩm theo dõi

## Bối cảnh
Trước đây:
- Bot Telegram chỉ có lệnh `/theodoi <url>` để thêm mới một liên kết sản phẩm vào danh sách theo dõi.
- Người dùng không có lệnh nào để tra cứu danh sách các sản phẩm đang theo dõi trực tiếp từ Telegram, buộc phải mở Dashboard trên trình duyệt web.
- Ngoài ra, khi phân tách các phân hệ (Sản phẩm theo dõi, Theo từ khóa, Siêu Sale, Săn lỗi giá), người dùng có nhu cầu quản lý danh mục sản phẩm theo từng tab tương ứng thông qua Telegram bot.

## Quyết định kiến trúc

1. **Thêm phương thức truy vấn danh sách theo dõi kèm giá mới nhất ([db.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/db.py)):**
   - Bổ sung `get_tracked_products_with_latest_price(self) -> list[sqlite3.Row]`:
     - Lọc nghiêm ngặt: `WHERE p.active = 1 AND p.source = 'user'` (đúng chuẩn cô lập tab Sản phẩm theo dõi của ADR 0030/0031).
     - Kết nối `LEFT JOIN price_history` lấy snapshot giá gần nhất (`current_price`, `current_list_price`, `current_stock`, `current_voucher_code`, `current_voucher_discount`, `current_final_price`).
     - Sắp xếp sản phẩm mới thêm lên đầu: `ORDER BY p.id DESC`.

2. **Triển khai lệnh `/listtracked` ([bot.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/bot.py)):**
   - Đăng ký command handler `/listtracked` (có `@guard` bảo vệ chỉ admin được gọi).
   - Nếu chưa có sản phẩm nào: Phản hồi thông báo hướng dẫn sử dụng `/theodoi <link>`.
   - Nếu có sản phẩm:
     - Phân đoạn danh sách theo khối **5 sản phẩm/tin nhắn** (`chunk_size = 5`) để hiển thị gọn gàng, vừa vặn khung nhìn điện thoại và không vượt quá giới hạn 4096 ký tự của Telegram.
     - Tiêu đề tin nhắn đánh dấu tiến trình: `📋 SẢN PHẨM THEO DÕI (Phần X/Y) — Tổng: Z sản phẩm`.
     - Từng sản phẩm hiển thị: Tên sản phẩm, Giá sàn hiện tại (gạch ngang giá gốc nếu có), Thông tin Voucher & Giá sau áp mã (nếu có), Giá mong muốn (nếu có), Tình trạng kho hàng (Còn hàng/Hết hàng) và liên kết trực tiếp `Xem sản phẩm ↗` (tắt web page preview để tin nhắn không bị phình to).
     - Loại bỏ hiển thị ID kỹ thuật và tag sàn theo đúng yêu cầu tối giản thông tin.
   - Bổ sung gợi ý lệnh `/listtracked` vào phản hồi hướng dẫn của lệnh `/theodoi`.

## Hệ quả
- Người dùng dễ dàng nắm bắt toàn bộ các sản phẩm mình đang theo dõi, giá bán hiện tại và voucher trực tiếp từ Telegram mọi lúc mọi nơi.
- Dữ liệu hiển thị hoàn toàn sạch, không bị lẫn các sản phẩm cào từ khóa hay siêu sale.
- Tin nhắn gửi tuần tự mượt mà, không bị lỗi giới hạn độ dài của Telegram API.
