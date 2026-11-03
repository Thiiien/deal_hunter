# 42. Chuẩn hóa lệnh Telegram Bot và tương tác nút bấm Inline cho Sản phẩm theo dõi

## Bối cảnh
Trước đây:
- Tab Sản phẩm theo dõi được quản trị trên Telegram qua các lệnh rời rạc: `/theodoi <url>`, `/giamongmuon <id> <giá>`, `/xoasp <id>`, và `/listtracked`.
- Lệnh `/listtracked` ẩn mã `#ID`, khiến người dùng không biết ID nào để nhập vào lệnh `/giamongmuon` hay `/xoasp`.
- Người dùng trên điện thoại phải gõ cú pháp dài, không có nút bấm tương tác (Inline Keyboard) dẫn đường và không có ngữ cảnh nhớ sản phẩm vừa thêm.

## Quyết định kiến trúc

1. **Chuẩn hóa danh mục 4 lệnh cốt lõi + 1 lệnh trợ giúp:**
   - `/theodoi` (hỗ trợ alias `/track`, `/add`): Thêm link theo dõi giá sản phẩm.
   - `/setgia` (hỗ trợ alias `/gia`, `/target`): Đặt giá mong muốn cho sản phẩm.
   - `/xoa` (hỗ trợ alias `/xoasp`, `/untrack`): Xóa sản phẩm khỏi danh sách theo dõi.
   - `/list` (hỗ trợ alias `/ds`): Liệt kê danh sách sản phẩm theo dõi (loại bỏ hoàn toàn `/listtracked`).
   - `/help` (hỗ trợ alias `/start`): Bảng hướng dẫn tra cứu cú pháp và các nút bấm.
   - Đăng ký tự động qua `bot.set_my_commands()` để menu popup khi gõ `/` chỉ xuất hiện đúng các lệnh này.

2. **Cơ chế lưu vết ngữ cảnh tương tác (Contextual Bot State):**
   - Lưu trữ `last_product_id` theo từng `chat_id` trong bộ nhớ ứng dụng.
   - Khi người dùng gõ `/theodoi` (không tham số):
     - Bot hiển thị 2 nút bấm Inline: `[🔗 Nhập Link Sản Phẩm]` và `[🎯 Đặt Giá Mong Muốn]`.
     - Bấm `[🔗 Nhập Link Sản Phẩm]`: Bot chờ nhận link và tự động kích hoạt cào giá ngay.
     - Bấm `[🎯 Đặt Giá Mong Muốn]`: Bot tự động hiểu là đặt giá cho sản phẩm vừa thao tác gần nhất, người dùng chỉ việc nhập số tiền (hỗ trợ cả định dạng `850k`, `850.000`, `850000`).

3. **Tương tác trực tiếp bằng nút bấm trong danh sách `/list`:**
   - Từng sản phẩm trong `/list` hiển thị rõ tiền tố `#ID` ở đầu tiêu đề.
   - Đính kèm nút bấm Inline Keyboard:
     - `[🎯 Đặt giá]` (`callback_data="setgia_<pid>"`): Bấm vào bot hỏi giá và tự gán cho `<pid>`.
     - `[🗑️ Xóa]` (`callback_data="del_<pid>"`): Bấm vào bot xác nhận và xóa ngay khỏi database.

4. **Hỗ trợ song song cả ID lẫn Link URL cho `/setgia` và `/xoa`:**
   - Người dùng có thể gõ nhanh:
     - `/setgia 3261 1200000` hoặc `/setgia https://... 1200000`
     - `/xoa 3261` hoặc `/xoa https://...`
   - Hệ thống tự động phân tích nếu là link thì trích xuất `item_key` để truy vấn `product_id`.

## Hệ quả
- Trải nghiệm Telegram Bot mượt mà, thân thiện tối đa trên di động nhờ các nút bấm Inline trực quan.
- Tốc độ thao tác cực nhanh: có thể thêm link, set giá và xóa chỉ với vài lần chạm màn hình mà không cần nhớ ID hay gõ lệnh phức tạp.
- Loại bỏ hoàn toàn lệnh cũ `/listtracked`, menu bot sạch sẽ và đồng bộ.
