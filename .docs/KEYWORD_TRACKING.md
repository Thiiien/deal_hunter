# Tính năng: Theo dõi sản phẩm theo từ khóa và bộ lọc

> Tài liệu riêng cho tab **"Theo từ khóa"** của dự án Deal Hunter.
> Cập nhật: 25/10/2026 (danh sách Dịch vụ & Khuyến mãi theo bộ lọc Lazada).
> Trạng thái: **đã code và kiểm thử với dữ liệu giả**; chưa kiểm chứng trên sàn thật (xem mục 11).

---

## 1. Mục đích

Người dùng nhập một từ khóa (ví dụ `bàn phím cơ aula`) và chọn bộ lọc. Hệ thống tự tìm sản phẩm theo từ khóa trên Shopee, Lazada, TikTok Shop, **chỉ giữ những sản phẩm khớp bộ lọc**, rồi theo dõi giá, lịch sử và deal thật như mọi sản phẩm khác trong dự án.

Mặc định tính năng phục vụ nhu cầu: **sản phẩm vận chuyển từ Việt Nam** (tương ứng "shipped from Vietnam"). Người dùng có thể đổi sang xuất xứ nước ngoài, lọc thêm loại shop và các dịch vụ, khuyến mãi.

3.

---

## 2. Bộ lọc

Mỗi từ khóa có bộ lọc riêng, nên cùng một chủ đề có thể theo dõi theo nhiều cách khác nhau.

| Bộ lọc | Giá trị | Mặc định | Ý nghĩa |
|---|---|---|---|
| **Xuất xứ** | `Việt Nam`, `Nước ngoài`, `Bất kỳ` | Việt Nam | Dựa vào mục "Xuất xứ" trên trang sản phẩm |
| **Vận chuyển từ** | `Việt Nam`, `Bất kỳ` | Việt Nam | Dựa vào "Gửi từ", "Vận chuyển từ", "Nơi gửi hàng" |
| **Loại shop** | `Mọi shop`, `Chỉ shop nước ngoài` | Mọi shop | Dựa vào nơi đặt shop hoặc nhãn hàng quốc tế |
| **Dịch vụ & Khuyến mãi** | Chọn nhiều | Không chọn | Sản phẩm phải có **tất cả** mục đã chọn |

### 2.1 Tùy chọn "Dịch vụ & Khuyến mãi" (theo bộ lọc của Lazada)

Danh sách dưới đây lấy đúng từ ảnh chụp bộ lọc **Dịch vụ & Khuyến mãi** mà bạn gửi (giao diện Lazada). Người dùng chọn một hoặc nhiều mục, sản phẩm phải có **tất cả** mục đã chọn.

| Mã | Nhãn trên Lazada | Dấu hiệu dò trong trang sản phẩm |
|---|---|---|
| `sale_cuoi_thang` | Sale Cuối Tháng | "sale cuối tháng" |
| `lazflash` | LazFlash Sale | "lazflash" |
| `bundle` | Bundle & Save | "bundle & save" |
| `fbl` | Xử lý đơn hàng bởi Lazada | "xử lý đơn hàng bởi lazada", "fulfilled by lazada" |
| `hoa_toc` | Giao hỏa tốc | "giao hỏa tốc" |
| `voucher_max` | Voucher Max | "voucher max" |
| `lazmall` | LazMall | "lazmall" |
| `tmall` | Tmall | "tmall" |
| `mua3` | Mua 3 Giảm 20% | "mua 3 giảm 20%" |
| `giao_trong_ngay` | Giao trong ngày | "giao trong ngày" |
| `giao_nhanh_24h` | Giao Nhanh 24H | "giao nhanh 24h" |
| `cod` | Thanh toán khi nhận hàng | "thanh toán khi nhận hàng" |
| `freeship` | Freeship | "freeship", "miễn phí vận chuyển" |
| `xu` | Xu | "hoàn xu", "nhận xu", "lazcoins" |

Lưu ý quan trọng:
- **Danh sách này chỉ áp dụng cho Lazada.** Shopee và TikTok Shop có bộ lọc riêng mà mình chưa có. Khi chọn sàn Shopee hoặc TikTok Shop, giao diện tắt các ô này. Khi chọn "Mọi sàn" kèm điều kiện dịch vụ, kết quả Shopee và TikTok Shop sẽ là "chưa rõ" và bị loại (trừ khi bật `KEYWORD_INCLUDE_UNKNOWN=1`).
- **Cách nhận dạng là dò chữ trên trang sản phẩm** và chưa được thử trên Lazada thật. Dễ nhận nhầm: tên như LazMall, Tmall, Freeship thường xuất hiện cả ở menu và banner của trang. Cần chỉnh để chỉ đọc khu vực huy hiệu của sản phẩm hoặc của shop.
- Các mục này trên Lazada là **bộ lọc có sẵn của trang tìm kiếm**. Nếu tìm ra tham số lọc tương ứng trên URL thì dùng thẳng sẽ chính xác và tiết kiệm hơn nhiều so với dò chữ (xem mục 13). Mình chưa kiểm chứng tham số nào.
- Mã cũ của phiên bản trước (`sale`, `instock`, `voucher`) không còn dùng và bị bỏ qua nếu còn sót trong dữ liệu.

---

## 3. Cách hệ thống đánh giá một sản phẩm

Mỗi điều kiện trả về một trong ba kết quả:

- **Khớp** (đã xác nhận),
- **Sai** (rõ ràng không khớp),
- **Chưa rõ** (trang không có thông tin hoặc không nhận dạng được).

Quy tắc kết luận:
1. Có bất kỳ điều kiện **Sai** thì loại.
2. Mọi điều kiện đều **Khớp** thì giữ, gắn nhãn **"Khớp mọi bộ lọc"**.
3. Còn lại (có điều kiện **Chưa rõ**): loại, trừ khi bật `KEYWORD_INCLUDE_UNKNOWN=1`. Khi bật, sản phẩm được giữ nhưng gắn nhãn **"Chưa rõ một số điều kiện, cần tự kiểm tra"**.

Chi tiết nhận dạng:
- **Xuất xứ:** `Việt Nam` khớp nếu ghi Việt Nam, VN. `Nước ngoài` khớp khi xuất xứ có ghi và không phải Việt Nam. Không ghi xuất xứ thì là "chưa rõ".
- **Vận chuyển từ:** nhận cả tên nước ("Việt Nam") lẫn tên tỉnh, thành phố (Hà Nội, TP. Hồ Chí Minh, Đà Nẵng...) là Việt Nam. Tên nước ngoài (Trung Quốc, Hồng Kông, Nhật Bản...) là sai. Danh sách tỉnh thành **chưa đầy đủ**, địa danh lạ sẽ là "chưa rõ" chứ không bị đoán.
- **Loại shop nước ngoài:** nhận qua tên nước hoặc nhãn "Quốc tế", "Nước ngoài", "Cross-border", "Overseas". Địa danh trong nước là shop trong nước.
- **Dịch vụ & Khuyến mãi:** thấy dấu hiệu của mục đã chọn thì **Khớp**; không thấy thì **Chưa rõ**, không kết luận "không có". Sản phẩm ở Shopee hoặc TikTok Shop luôn là **Chưa rõ** với điều kiện này vì danh sách chỉ của Lazada.

Ngoài ra sản phẩm phải **liên quan từ khóa**: mọi từ trong từ khóa xuất hiện trong tên sản phẩm (khi có tên).

Lưu ý quan trọng: **xuất xứ, nơi gửi hàng và dịch vụ do shop hoặc trang hiển thị, sàn không bảo đảm.** Nhiều khi nhãn xuất xứ không đúng thực tế (ví dụ thương hiệu vốn sản xuất ở nước khác nhưng shop khai xuất xứ khác). Bộ lọc giúp thu hẹp danh sách chứ không thay cho việc tự kiểm tra trước khi mua.

---

## 4. Luồng hoạt động

```
Người dùng thêm từ khóa + bộ lọc (dashboard hoặc bot)
        │
        ▼
run_keyword_search()  ← bấm "Tìm" hoặc bot tự chạy định kỳ
  với mỗi từ khóa đang bật, mỗi sàn:
    1. adapter.search()  → danh sách link (tối đa KEYWORD_RESULT_LIMIT)
    2. bỏ qua link đã bị loại trong 7 ngày gần đây (bộ nhớ đệm theo từ khóa)
    3. adapter.fetch()   → lấy giá, xuất xứ, gửi từ, shop, dịch vụ
    4. classify()        → khớp bộ lọc?
         khớp   → lưu sản phẩm + lịch sử giá, gắn keyword_id và nhãn xác nhận
         không  → ghi vào bộ nhớ đệm loại
    5. gặp captcha/đăng nhập → dừng sàn đó, báo admin
        │
        ▼
Sản phẩm đã khớp nằm trong danh sách theo dõi chung:
quét giá định kỳ, phát hiện deal thật, cảnh báo Telegram như bình thường
```

Điểm cần biết:
- **Đổi bộ lọc không tự xét lại sản phẩm đã theo dõi.** Bộ lọc mới áp dụng cho lần tìm kế tiếp. Khi đổi bộ lọc, bộ nhớ đệm loại của từ khóa đó được xóa để các sản phẩm từng bị loại được xét lại.
- Thêm lại cùng từ khóa và cùng sàn sẽ **cập nhật bộ lọc**, không tạo bản trùng.
- Xóa từ khóa sẽ ngừng theo dõi các sản phẩm của nó.

---

## 5. Giao diện (dashboard)

Tab **"Theo từ khóa"** gồm:
- Ô nhập từ khóa, chọn sàn (hoặc mọi sàn), 3 danh sách chọn bộ lọc, các ô chọn **Dịch vụ & Khuyến mãi**, nút **Theo dõi** và **Tìm ngay tất cả**.
- Bảng từ khóa: tóm tắt bộ lọc, số sản phẩm đang theo dõi, kết quả lần tìm gần nhất (đã xem bao nhiêu, khớp bao nhiêu, có bị chặn không), nút Tìm, Tạm dừng/Bật lại, Xóa.
- Bảng sản phẩm khớp: sàn, tên (bấm vào mở link affiliate), shop và nơi đặt shop, xuất xứ và nơi gửi hàng, giá, giảm thật, biểu đồ 30 ngày, trạng thái xác nhận. Có thể lọc theo từ khóa.

---

## 6. Telegram

| Lệnh | Quyền | Chức năng |
|---|---|---|
| `/tukhoa <từ khóa>` | Admin | Thêm từ khóa với bộ lọc mặc định (xuất xứ Việt Nam, vận chuyển từ Việt Nam) |
| `/dstukhoa` | Mọi người | Xem danh sách từ khóa và số sản phẩm đang theo dõi |

Bot tự tìm lại theo từ khóa mỗi `KEYWORD_INTERVAL_MIN` phút (mặc định 180) và báo admin nếu bị chặn. Bộ lọc khác (xuất xứ nước ngoài, dịch vụ và khuyến mãi...) hiện chỉ chỉnh được trên dashboard. Sản phẩm khớp tham gia cảnh báo deal thật như mọi sản phẩm khác.

---

## 7. Mô hình dữ liệu

**Bảng `keywords`:** `id`, `keyword`, `platform` (rỗng = mọi sàn), `active`, `created_at`, `last_run`, `last_scanned`, `last_matched`, `last_msg`, và bộ lọc: `origin_filter` (`vn`/`foreign`/`any`), `ship_filter` (`vn`/`any`), `shop_filter` (`any`/`foreign`), `services_filter` (danh sách mã, cách nhau dấu phẩy). Cặp (`keyword`, `platform`) là duy nhất.

**Bảng `products`:** thêm `origin`, `shop_country`, `ships_from`, `services`, `keyword_id`, `verified`.

**Bảng `rejected_items`:** (`platform`, `item_key|<id từ khóa>`, `reason`, `ts`), dùng để không tải lại sản phẩm đã bị loại trong 7 ngày.

Cơ sở dữ liệu cũ được nâng cấp tự động khi khởi động (thêm cột nếu chưa có).

**Snapshot** (dạng dữ liệu chung của adapter) có thêm: `origin`, `shop_country`, `ships_from`, `services`.

---

## 8. API

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| GET | `/api/keywords` | Danh sách từ khóa kèm bộ lọc và thống kê |
| POST | `/api/keywords` | Thêm hoặc cập nhật: `keyword`, `platform`, `origin_filter`, `ship_filter`, `shop_filter`, `services` (mảng mã) |
| POST | `/api/keywords/<id>` | Bật hoặc tạm dừng: `{"active": true/false}` |
| DELETE | `/api/keywords/<id>` | Xóa từ khóa |
| POST | `/api/keywords/search` | Tìm ngay: `{"keyword_id": id}` hoặc rỗng cho tất cả |
| GET | `/api/keyword-products` | Sản phẩm khớp, lọc theo `keyword_id` |

Tìm kiếm và quét giá dùng chung một khóa, nên không chạy chồng nhau (trả lỗi 409 nếu đang bận).

---

## 9. Cấu hình (`.env`)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `KEYWORD_INCLUDE_UNKNOWN` | `1` = giữ cả sản phẩm chưa rõ một số điều kiện (gắn nhãn cảnh báo) | 0 |
| `KEYWORD_RESULT_LIMIT` | Số sản phẩm tối đa lấy từ mỗi từ khóa trên mỗi sàn | 30 |
| `KEYWORD_INTERVAL_MIN` | Chu kỳ bot tự tìm lại (phút) | 180 |
| `REQUEST_DELAY_SEC` | Nghỉ giữa hai lần tải trang (dùng chung với Selenium) | 6 |

---

## 10. Nguồn dữ liệu và adapter

| Adapter | Hỗ trợ tìm theo từ khóa | Ghi chú |
|---|---|---|
| **Mock** | Có | Sinh dữ liệu giả để thử toàn bộ luồng, không cần mạng |
| **Feed** | Có (lọc theo tên trong feed) | Feed cần thêm cột `origin`, `shop_country`, `ships_from`, `services`. Ổn định nhất, nhưng phụ thuộc feed có các trường này không |
| **Selenium** | Shopee và Lazada | TikTok Shop chưa hỗ trợ tìm bằng trình duyệt. Selector chưa kiểm chứng |

Selenium mở trang tìm kiếm, cuộn vài lần để tải thêm, gom link sản phẩm, rồi mở từng trang để đọc xuất xứ ("Xuất xứ"), nơi gửi ("Gửi từ", "Vận chuyển từ", "Nơi gửi hàng"), nơi đặt shop ("Địa chỉ shop", "Nơi bán") và dấu hiệu dịch vụ.

**Chi phí quét:** bộ lọc được áp dụng **sau khi** mở từng trang sản phẩm, nên mỗi từ khóa cần nhiều lần tải trang. Giữ `KEYWORD_RESULT_LIMIT` thấp và dùng bộ nhớ đệm loại để giảm tải. Nếu sàn có tham số lọc ngay trên URL tìm kiếm thì dùng được sẽ tiết kiệm hơn nhiều, nhưng mình chưa kiểm chứng tham số nào hoạt động.

---

## 11. Giới hạn đã biết

| Giới hạn | Tác động |
|---|---|
| **Chưa thử trên sàn thật** (môi trường phát triển không có mạng và Chrome) | Selector tìm kiếm, "Xuất xứ", "Gửi từ", dịch vụ chỉ là điểm khởi đầu, bạn phải chỉnh bằng F12 |
| Trang tìm kiếm bị chống bot chặt, có thể đòi captcha hoặc đăng nhập | Hệ thống dừng sàn đó và báo bạn, không né captcha |
| Dữ liệu xuất xứ, nơi gửi, dịch vụ do shop khai | Có thể sai hoặc thiếu; sản phẩm thiếu thông tin bị loại (hoặc gắn nhãn "chưa rõ" nếu bật tùy chọn) |
| Nhận dạng dịch vụ bằng cách dò chữ trên trang, chưa thử trên Lazada thật | Dễ nhận nhầm vì menu và banner cũng có chữ LazMall, Tmall, Freeship; cần siết theo trang thật |
| Danh sách tỉnh thành chưa đầy đủ | Địa danh lạ thành "chưa rõ" |
| Danh sách "Dịch vụ & Khuyến mãi" chỉ có của Lazada (từ ảnh bạn gửi) | Shopee và TikTok Shop chưa có danh sách; Lazada có thể đổi danh sách theo thời gian |
| Lệnh bot chỉ dùng bộ lọc mặc định | Muốn bộ lọc khác phải dùng dashboard |
| Đổi bộ lọc không xét lại sản phẩm đã theo dõi | Cần xóa hoặc để sản phẩm cũ tự hết hạn theo dõi |

Về điều khoản: các sàn thường hạn chế thu thập dữ liệu tự động. Ưu tiên dùng feed affiliate khi có thể. Gặp captcha hoặc đăng nhập thì hệ thống dừng, không cố vượt.

---

## 12. Kiểm thử đã thực hiện

Với adapter dữ liệu giả:
- Thêm từ khóa, chạy tìm, lọc và lưu sản phẩm khớp: đạt.
- Các từ khóa với bộ lọc khác nhau (xuất xứ Việt Nam + gửi từ Việt Nam; xuất xứ nước ngoài + Freeship; Lazada + LazMall + Thanh toán khi nhận hàng) cho kết quả khác nhau đúng như bộ lọc; điều kiện dịch vụ chỉ khớp với sản phẩm Lazada: đạt.
- Nhận dạng "Hà Nội", "TP. Hồ Chí Minh" là Việt Nam, "Trung Quốc" là nước ngoài, địa danh không có trong danh sách là "chưa rõ": đạt.
- Khởi tạo cơ sở dữ liệu hai lần (nâng cấp cột) không lỗi: đạt.
- Các điểm cuối API từ khóa trả đúng; quét giá tiếp tục theo dõi các sản phẩm đã khớp: đạt.
- Giao diện HTML mới và bot Telegram: **chưa chạy thử trên trình duyệt hay với token thật** (bot mới kiểm tra cú pháp).

---

## 13. Hướng phát triển

1. Chạy thử Selenium trên Shopee và Lazada, chỉnh selector, siết nhận dạng dịch vụ theo trang thật.
2. Tìm tham số lọc trên URL tìm kiếm của Lazada tương ứng với từng mục trong "Dịch vụ & Khuyến mãi" để lọc ngay từ trang kết quả thay vì dò chữ; bổ sung danh sách tương tự cho Shopee và TikTok Shop.
3. Hỗ trợ tìm theo từ khóa cho TikTok Shop.
4. Cho phép đặt bộ lọc ngay trong lệnh bot (ví dụ `/tukhoa bàn phím cơ aula --xuatxu nuocngoai --freeship`).
5. Nút "Xét lại bộ lọc" cho các sản phẩm đã theo dõi.
6. Bổ sung đầy đủ danh sách tỉnh thành và các nhãn "quốc tế" thường gặp.
7. Kết hợp với module lỗi giá: so giá sản phẩm mới với trung vị của nhóm cùng từ khóa khi chưa có lịch sử.

---

## 14. Câu hỏi còn mở

1. Bạn muốn **mặc định** là "xuất xứ Việt Nam + vận chuyển từ Việt Nam + mọi shop" như hiện tại, hay vẫn muốn mặc định chỉ shop nước ngoài?
2. Bạn có ảnh chụp bộ lọc "Dịch vụ & Khuyến mãi" (hoặc bộ lọc tương đương) của Shopee và TikTok Shop không? Gửi để mình bổ sung danh sách cho từng sàn.
3. Bạn dùng nguồn dữ liệu nào để chạy thật (feed hay Selenium)? Nếu là feed, feed có các trường xuất xứ, nơi gửi, dịch vụ không?
4. Với sản phẩm "chưa rõ", bạn muốn loại bỏ hay giữ lại kèm cảnh báo?
