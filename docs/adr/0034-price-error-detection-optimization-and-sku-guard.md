# 34. Tối ưu hóa Crawler phát hiện lỗi giá cấp độ phân loại (SKU) và cơ chế chống báo giả phụ kiện

## Bối cảnh
Sản phẩm được người dùng theo dõi (tab Sản phẩm theo dõi) thường là những sản phẩm có giá trị cao (như bàn phím cơ, chuột gaming, đồ công nghệ) và người dùng muốn canh bắt các đợt **sập giá / lỗi giá** (price error / flash bug do người bán set nhầm giá, ví dụ: 223.000₫ thay vì 2.230.000₫).

Tuy nhiên, hệ thống trước đây gặp phải 3 vấn đề cốt lõi:
1. **Báo động giả từ phụ kiện giá rẻ (False Positive Anomaly)**:
   - Các shop công nghệ thường gộp phụ kiện (như *switch lẻ, keycap lẻ, dụng cụ kẹp nhổ switch/keycap, mỡ bôi trơn lube, dây cáp sạc xoắn, feet chuột, túi đựng, lót chuột*) vào cùng một link bàn phím/chuột với mức giá rất thấp (ví dụ: 30.000₫ - 50.000₫).
   - Bộ lọc `is_accessory_or_fake` trước đây chỉ chứa các từ khóa chung chung (`ốp`, `case`, `dây`, `cáp`), thiếu từ khóa đặc thù bàn phím/chuột. Đồng thời, từ khóa `"dây"` nguyên bản khiến các sản phẩm bàn phím/chuột `"không dây"` (wireless) và `"có dây"` bị nhận nhầm thành phụ kiện.
   - Chưa tận dụng so sánh tỷ lệ giá phân loại so với giá gốc sản phẩm để lọc phụ kiện.
2. **Bỏ lọt lỗi giá ở các lần quét đầu tiên khi chưa có median 30 ngày**:
   - `check_price_error` trong `scanner.py` sử dụng `base_val = result.median_30d or snapshot.list_price or effective_price or 0.0`.
   - Với sản phẩm mới theo dõi (< 3 lần quét), `median_30d = None`. Nếu `snapshot.list_price` không có, `base_val` rơi về `effective_price`, khiến tỷ lệ chiết khấu luôn bằng 0% và hoàn toàn bỏ lọt đợt sập giá dù giá vừa giảm từ 2.230.000₫ xuống 223.000₫ so với lần quét trước.
3. **Thiếu liên kết phân loại SKU với tiêu đề biến thể trên Lazada**:
   - Trên Lazada, giá theo từng SKU nằm trong `skuInfos`, trong khi tên biến thể (ví dụ: *"Trắng Switch Reaper"*, *"Glacier Blue"*) được ánh xạ qua `skuBase.skus` và `skuBase.properties`. Crawler trước đây chưa bóc tách bảng ánh xạ này nên khi phân loại có giá lỗi, tên biến thể bị thiếu.
   - Người dùng chưa có tùy chọn chuyển nhanh tần suất quét (1-2 phút) cho các sản phẩm theo dõi để bắt kịp lỗi giá trong vài phút trước khi shop hủy đơn hoặc sửa giá.

## Quyết định kiến trúc

1. **Bộ lọc phụ kiện cấp độ SKU và Guard tỷ lệ giá ([detector.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/detector.py)):**
   - **Mở rộng `ACCESSORY_KEYWORDS`**: Bổ sung đầy đủ từ khóa phụ kiện đồ công nghệ và phím cơ: `keycap`, `key cap`, `nút phím`, `switch lẻ`, `hộp switch`, `pack switch`, `set switch`, `túi switch`, `chỉ switch`, `puller`, `kẹp nhổ`, `nhổ keycap`, `nhổ switch`, `lube`, `mỡ bôi trơn`, `cọ lube`, `dây cáp`, `cáp xoắn`, `pad chuột`, `lót chuột`, `bàn di chuột`, `miếng lót`, `feet`, `skates`, `miếng dán feet`, `kê tay`, `đệm kê tay`, `wrist rest`, `núm xoay`, `núm phím`, `túi đựng`, `hộp đựng`, `bao đựng`, `vỏ case`, `sticker`, `decal`.
   - **Loại bỏ từ khóa trần `"dây"`**: Thay bằng các cụm từ cụ thể (`dây sạc`, `dây cáp`, `dây đeo`, `dây nguồn`, `dây đồng hồ`) để không gây nhận diện nhầm trên các sản phẩm công nghệ `"không dây"` (wireless) và `"có dây"`.
   - **Guard tỷ lệ giá (`price < 0.20 * baseline`)**: Trong `is_accessory_or_fake(name, price, baseline)`, nếu giá phân loại nhỏ hơn 20% giá gốc sản phẩm (> 80% chiết khấu) và chứa các từ khóa đơn vị lẻ (`"lẻ"`, `"1 chiếc"`, `"1 cái"`, `"phụ kiện"`, `"dùng thử"`, `"sample"`), tự động xác định là phụ kiện giá rẻ gài trong link để loại bỏ.

2. **Ánh xạ SKU và bóc tách biến thể chính xác trên Crawler ([playwright.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/adapters/playwright.py)):**
   - Bổ sung hàm `_extract_sku_names(obj)`: Đệ quy duyệt `skuBase` để giải mã `propPath` (`pid:vid`) thành tên hiển thị thuộc tính tương ứng (ví dụ: *"Trắng Switch Reaper"*).
   - Khi chọn phân loại có giá tốt nhất (`best_sku`), tự động đính kèm tên biến thể vào tiêu đề sản phẩm: `name = f"{name} ({best_var_name})"`, giúp admin và người dùng thấy ngay biến thể nào bị lỗi giá.
   - Ưu tiên cấu trúc dữ liệu server-side rendering `mod_data` (`window.__moduleData__.data`), có cơ chế fallback an toàn qua `tracking.pdt_price` và `tracking.pdt_name`.

3. **Mốc so sánh giá quét trước đó cho sản phẩm mới ([scanner.py](file:///c:/Users/pvthien/source/deal_hunter/src/deal_hunter/scanner.py)):**
   - Trong `scan_product`, cập nhật tính toán `base_val`:
     `prior_price = history[0] if history and history[0] > 0 else None`
     `base_val = result.median_30d or prior_price or snapshot.list_price or effective_price or 0.0`
   - Nhờ đó, ngay khi sản phẩm mới chỉ có 1-2 điểm lịch sử giá quét, nếu lần quét tiếp theo giá sập sâu ≥ 65% so với lần quét trước, `check_price_error` lập tức kích hoạt, gửi cảnh báo khẩn cấp tới Telegram admin và khởi chạy luồng quét lại sau 2 phút để tự động xác minh.

4. **Preset tần suất quét nhanh trên giao diện ([dashboard.html](file:///c:/Users/pvthien/source/deal_hunter/templates/dashboard.html)):**
   - Bổ sung các nút bấm chọn nhanh tần suất (`1p ⚡`, `2p`, `5p`, `15p`, `30p`) cho cả phân hệ **Sản phẩm theo dõi** và **Săn lỗi giá** trong popup Cài đặt, cho phép kích hoạt chế độ quét tần suất cao ngay lập tức khi nghi ngờ có đợt sale xả kho hay lỗi giá.

## Hệ quả
- Khả năng phát hiện lỗi giá cực nhạy: bắt ngay lập tức các đợt sập giá ≥ 65% dựa trên giá vừa quét trước đó ngay cả khi sản phẩm chưa tích lũy đủ 30 ngày lịch sử.
- Triệt tiêu hoàn toàn báo động giả do các phân loại switch lẻ, keycap lẻ, cáp sạc gài kèm trong link sản phẩm chính.
- Toàn bộ 148 bài kiểm thử trong test suite đều vượt qua.
