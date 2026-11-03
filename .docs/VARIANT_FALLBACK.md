# Cấp 1: Tự động chuyển sang biến thể khác còn hàng, giá thấp nhất (cùng một listing)

> **Hiện trạng 03/11/2026:** đã triển khai một phần (ADR 0038 đến 0041, 0053, 0054): bảng biến thể, máy trạng thái tồn kho, quét nhanh xác minh, thay thế âm thầm. Không triển khai: lệnh `/thaythe`, thuộc tính khóa, biến `FALLBACK_*`, chế độ mặc định là `any` chứ không `selected`. Với sản phẩm theo dõi hệ thống luôn chọn biến thể rẻ nhất còn hàng. Code và ADR là nguồn sự thật.

> Tài liệu thiết kế chi tiết cho một tính năng của dự án **Deal Hunter**.
> Cập nhật: 28/10/2026.
> **Trạng thái: mới ở mức thiết kế, chưa có code.** Mục 3 ghi rõ dự án hiện có gì và còn thiếu gì.

---

## 1. Mục tiêu và phạm vi

### 1.1 Bài toán
Người dùng theo dõi một sản phẩm ở một **biến thể cụ thể** (ví dụ bàn phím cơ màu đen, switch đỏ). Khi biến thể đó hết hàng, người dùng muốn hệ thống **tự động xét các biến thể khác trong cùng listing**, chọn ra biến thể **còn hàng và có giá hiệu dụng thấp nhất** trong giới hạn cho phép, rồi báo để người dùng quyết định.

### 1.2 Trong phạm vi (Cấp 1)
- Các biến thể (màu, size, dung lượng, loại switch...) nằm **trên cùng một trang sản phẩm, cùng một shop, cùng một mô tả**.
- Theo dõi giá và tồn kho **từng biến thể**.
- Quy tắc chọn biến thể thay thế có giới hạn do người dùng đặt.
- Cảnh báo kèm link, và báo ngay khi biến thể chính có hàng trở lại.

### 1.3 Ngoài phạm vi
- Sản phẩm tương đương ở **shop khác** (đó là Cấp 2, có rủi ro ghép nhầm cao hơn nhiều).
- Tự động thêm vào giỏ hoặc thanh toán. Bot chỉ báo và đưa link, người dùng tự mua.
- Vượt captcha hoặc né chống bot. Gặp captcha hoặc đòi đăng nhập thì hệ thống dừng và báo.

### 1.4 Vì sao làm Cấp 1 trước
Cùng một trang, một shop, một mô tả nên rủi ro ghép nhầm sản phẩm gần như không có. Đây cũng là nền tảng dữ liệu (giá và tồn kho theo biến thể) mà Cấp 2 sẽ cần.

---

## 2. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| **Listing** | Một trang sản phẩm của một shop |
| **Biến thể** | Một lựa chọn cụ thể trong listing, gồm tổ hợp thuộc tính (Màu: Đen, Switch: Đỏ) |
| **Biến thể chính** | Biến thể người dùng đang theo dõi |
| **Biến thể thay thế** | Biến thể khác trong cùng listing được xét khi biến thể chính hết hàng |
| **Thuộc tính khóa** | Thuộc tính bắt buộc phải giống biến thể chính khi thay thế (ví dụ Switch) |
| **Giá hiệu dụng** | Giá + phí vận chuyển − voucher ước tính (khi có dữ liệu) |
| **Trạng thái hàng** | `còn`, `hết`, `chưa rõ` |

---

## 3. Hiện trạng dự án và những gì còn thiếu

| Hạng mục | Hiện tại | Cần cho tính năng này |
|---|---|---|
| Giá | Một giá cho cả sản phẩm, khoảng giá chỉ lấy số đầu | Giá và giá gốc **theo từng biến thể** |
| Tồn kho | Chỉ đánh dấu hết khi dữ liệu có cấu trúc ghi "OutOfStock"; để trống thì hàm đánh giá coi là còn hàng | Ba trạng thái **còn / hết / chưa rõ**, kèm số lượng, nguồn tín hiệu, thời điểm |
| Biến thể | Chưa có | Bảng biến thể, thuộc tính, lịch sử theo biến thể |
| Voucher, phí ship | Chưa đọc | Tính giá hiệu dụng (nếu chưa có thì hiển thị giá và ghi rõ chưa gồm ship, voucher) |
| Phân tầng quét | Một chu kỳ chung | Quét dày hơn cho sản phẩm đang hết hàng |
| Bot | `/dat` đặt theo sản phẩm | Đặt theo biến thể |

**Hai việc nền phải làm trước:** đọc giá theo biến thể và đọc tồn kho ba trạng thái. Phần còn lại của tài liệu giả định hai việc này đã có.

---

## 4. Yêu cầu dữ liệu (nền tảng)

### 4.1 Mỗi lần quét phải trả về
Danh sách biến thể, mỗi biến thể có: khóa nhận dạng, tên hiển thị, các thuộc tính (tên và giá trị), giá, giá gốc, trạng thái hàng, số lượng (nếu có), nguồn tín hiệu tồn kho.

### 4.2 Nguồn đọc (theo thứ tự ưu tiên)
1. **Dữ liệu có cấu trúc trong trang** (JSON-LD, danh sách `offers` nếu có một mục cho mỗi biến thể).
2. **Dữ liệu chính trang tải về** để dựng danh sách biến thể và tồn kho.
3. **Giao diện** (danh sách lựa chọn, nút mua bị vô hiệu hóa, chữ "hết hàng").

Đọc ít nhất hai nguồn nếu có và **đối chiếu**. Lệch nhau thì trạng thái là `chưa rõ`, không đoán.

**Tránh bấm lần lượt từng biến thể** nếu có thể đọc được trong một lần tải trang, vì nhiều thao tác làm tăng nguy cơ bị chặn. Nếu bắt buộc phải bấm, giới hạn số lần và giữ nhịp thấp.

### 4.3 Quy tắc trạng thái hàng
- `còn`: chỉ khi có **tín hiệu dương** (số lượng lớn hơn 0, hoặc nút mua đang bật cho đúng biến thể đó, hoặc dữ liệu ghi còn hàng).
- `hết`: có tín hiệu hết rõ ràng (chữ hết hàng, nút bị vô hiệu hóa, dữ liệu ghi hết).
- `chưa rõ`: không đọc được, hoặc các nguồn mâu thuẫn. **Không bao giờ ngầm hiểu là còn hàng.**
- Trạng thái chỉ đổi khi **hai lần đọc liên tiếp đồng ý**, tránh nhảy qua lại do trang chưa tải xong.

### 4.4 Lưu ý chưa kiểm chứng
Mình **chưa kiểm chứng** trang Lazada, Shopee, TikTok Shop có hiện giá và tồn kho từng biến thể công khai hay không, và hiện ở đâu. Nếu không hiện, nhiều biến thể sẽ ở trạng thái `chưa rõ` và tính năng chỉ chọn được trong số biến thể đọc được. Cần mẫu trang thật để viết bộ đọc (xem mục 15).

---

## 5. Mô hình dữ liệu đề xuất

**`variants`**: `id`, `product_id`, `variant_key`, `name`, `attrs` (JSON, ví dụ `{"Màu":"Đen","Switch":"Đỏ"}`), `active`, `first_seen`, `last_seen`. Cặp (`product_id`, `variant_key`) là duy nhất. Biến thể biến mất khỏi trang thì đặt `active = 0`, không xóa lịch sử.

**`variant_history`**: `id`, `variant_id`, `price`, `list_price`, `stock_state` (`in`/`out`/`unknown`), `stock_qty`, `stock_source`, `source` (feed hay trình duyệt), `ts`. Chỉ thêm, không ghi đè.

**`products`**: thêm `main_variant_id` (biến thể chính đang theo dõi).

**`fallback_rules`** (một dòng cho mỗi sản phẩm):
- `enabled`
- `mode`: `same_key_attrs`, `any`, hoặc `selected`
- `key_attrs`: danh sách thuộc tính phải giống biến thể chính (dùng khi `mode = same_key_attrs`)
- `selected_variants`: danh sách biến thể được phép (dùng khi `mode = selected`)
- `price_ceiling_pct`: giá thay thế tối đa so với giá tham chiếu của biến thể chính
- `max_price`: giá tuyệt đối tối đa (tùy chọn)

**`fallback_events`**: `id`, `product_id`, `main_variant_id`, `chosen_variant_id`, `state`, `effective_price`, `reason`, `created_at`, `notified_at`, `resolved_at`, `outcome`.

**`orders`**: thêm `variant_id`.

---

## 6. Máy trạng thái của biến thể chính

```
         đọc còn hàng
   ┌───────────────────────┐
   ▼                       │
 CÒN HÀNG ──(1 lần đọc hết)──► NGHI HẾT ──(lần 2 vẫn hết)──► HẾT HÀNG (đã xác nhận)
   ▲                           │ (lần 2 còn)                      │
   └───────────────────────────┘                                  │
   ▲                                                              │
   └──────────── 2 lần đọc liên tiếp còn hàng ◄───────────────────┘

 CHƯA RÕ: không đủ tín hiệu; không kích hoạt thay thế, báo trạng thái "chưa xác nhận"
```

- Chỉ khi **HẾT HÀNG (đã xác nhận)** mới chạy quy trình thay thế.
- Khi quay lại **CÒN HÀNG** (2 lần đọc liên tiếp), đóng sự kiện thay thế và báo ngay cho người dùng.

---

## 7. Thuật toán chọn biến thể thay thế

Chạy khi biến thể chính ở trạng thái HẾT HÀNG (đã xác nhận) và mỗi khi dữ liệu biến thể được làm mới.

1. **Tập ứng viên:** các biến thể `active` của cùng listing, trừ biến thể chính.
2. **Lọc tồn kho:** chỉ giữ biến thể có trạng thái `còn` với **tín hiệu dương**, và dữ liệu **còn mới** (không quá `FALLBACK_FRESHNESS_MIN` phút). Loại `chưa rõ` và `hết`.
3. **Lọc theo quy tắc người dùng:**
   - `same_key_attrs`: các thuộc tính khóa phải trùng biến thể chính (ví dụ Switch phải giống, Màu được khác).
   - `any`: chấp nhận mọi biến thể.
   - `selected`: chỉ các biến thể người dùng đã tích chọn.
4. **Lọc giá trần:** giá ≤ giá tham chiếu × (1 + `price_ceiling_pct`), và ≤ `max_price` nếu có.
   - Giá tham chiếu = giá gần nhất của biến thể chính trước khi hết hàng; nếu không có thì trung vị 30 ngày của biến thể chính; nếu vẫn không có thì giá trung vị của các biến thể còn hàng.
5. **Kiểm tra bất thường:** giá lệch cực mạnh so với các biến thể khác thì **không** xử lý như thay thế bình thường, chuyển sang quy trình nghi lỗi giá (xem `PRICE_ERROR_DETECTION.md`).
6. **Xếp hạng theo giá hiệu dụng tăng dần.** Hòa thì ưu tiên số lượng tồn lớn hơn, rồi lần xác nhận còn hàng gần nhất.
7. **Đọc lại ngay trước khi báo:** tải lại trang một lần, xác nhận biến thể được chọn vẫn còn hàng và giá không đổi. Đổi thì chạy lại từ bước 2.
8. **Ghi sự kiện** vào `fallback_events` kèm lý do (vì sao chọn, bị loại những biến thể nào và vì sao).

### 7.1 Giá hiệu dụng
`giá hiệu dụng = giá + phí vận chuyển − voucher ước tính`.
- Khi chưa có dữ liệu ship và voucher thì dùng giá hiển thị và **ghi rõ "chưa gồm ship, voucher"**.
- Voucher luôn là ước tính kèm điều kiện (đơn tối thiểu, giới hạn, hạn dùng), không cam kết áp dụng được.

### 7.2 Ví dụ

Bàn phím có các biến thể:

| Biến thể | Giá | Trạng thái |
|---|---|---|
| Đen, switch đỏ (chính) | 650.000₫ | hết |
| Trắng, switch đỏ | 690.000₫ | còn |
| Đen, switch xanh | 640.000₫ | còn |
| Trắng, switch xanh | 700.000₫ | chưa rõ |

Quy tắc `same_key_attrs` với thuộc tính khóa là Switch, trần +20%:
- Đen switch xanh bị loại vì khác Switch.
- Trắng switch xanh bị loại vì `chưa rõ`.
- Còn Trắng switch đỏ (690.000₫, trong trần 780.000₫) nên được chọn.

Nếu đổi quy tắc thành `any`, Đen switch xanh (640.000₫) sẽ thắng vì rẻ nhất.

---

## 8. Quy tắc cho người dùng đặt (chính sách thay thế)

Ba chế độ, vì biến thể không tương đương nhau:

| Chế độ | Khi nào dùng | Ví dụ |
|---|---|---|
| **Cùng thuộc tính khóa** | Biết chắc thuộc tính nào không được đổi | Giữ nguyên loại switch, màu thì sao cũng được |
| **Mọi biến thể** | Biến thể chỉ khác nhau về hình thức | Chỉ khác màu |
| **Chỉ biến thể đã chọn** | Muốn kiểm soát hoàn toàn | Chỉ chấp nhận đen hoặc trắng |

Kèm hai giới hạn tùy chọn: **giá trần theo phần trăm** so với biến thể chính (mặc định gợi ý +20%) và **giá tuyệt đối tối đa**.

Mặc định khi bật tính năng: chế độ "chỉ biến thể đã chọn" (an toàn nhất), người dùng phải chủ động chọn thì mới có thay thế.

---

## 9. Thông báo và quy trình người dùng

### 9.1 Khi nào báo
- Biến thể chính hết hàng (đã xác nhận) **và** có ít nhất một biến thể thay thế đạt điều kiện: báo "biến thể X hết, biến thể Y đang còn, giá Z".
- Biến thể chính hết hàng và **không có** thay thế: báo một lần "chưa có phương án thay thế", tiếp tục quét.
- Biến thể chính **có hàng trở lại**: báo ngay.
- Biến thể thay thế được chọn đổi sang cái khác, hoặc giá giảm hơn 5%, hoặc đã qua 24 giờ: báo lại (tránh gửi lặp).

### 9.2 Nội dung cảnh báo
Tên sản phẩm, biến thể chính (hết) và biến thể thay thế (còn), giá và giá hiệu dụng (ghi chú nếu chưa gồm ship, voucher), tín hiệu tồn kho và thời điểm đọc, lý do chọn, nhãn "chưa xác nhận tồn kho" nếu có.

### 9.3 Hành động của người dùng
Bot kèm các nút: **Mở link**, **Đặt mua biến thể này**, **Bỏ qua biến thể này** (loại khỏi lần chọn sau), **Chuyển sang theo dõi biến thể này** (đổi biến thể chính).

**Không tự đổi biến thể chính một cách âm thầm.** Mọi thay đổi do người dùng xác nhận.

---

## 10. Chiến lược quét

Biến thể được đọc trong **cùng một lần tải trang** với giá, nên tính năng này không tăng số lần tải nếu bộ đọc lấy được danh sách đầy đủ.

| Tình huống | Tần suất gợi ý |
|---|---|
| Biến thể chính còn hàng | Theo chu kỳ nền (30-60 phút) |
| Nghi hết hàng | Đọc lại sau vài phút để xác nhận |
| Hết hàng (đã xác nhận) | 10-15 phút một lần, có giới hạn thời gian (ví dụ tối đa 48 giờ rồi hạ về chu kỳ nền) |
| Trước khi gửi cảnh báo, trước khi trả link đặt mua | Đọc lại ngay |

Giới hạn cần đặt: tối đa khoảng 10 sản phẩm ở nhịp dày cùng lúc, hạn mức yêu cầu theo từng sàn, thử lại có chờ tăng dần khi lỗi. Dừng quét sàn đó khi gặp captcha hoặc đăng nhập và báo admin. Con số trên là điểm khởi đầu, cần chỉnh theo dữ liệu thực.

---

## 11. Giao diện và bot

### 11.1 Dashboard
- Trong chi tiết sản phẩm: **bảng biến thể** gồm tên, thuộc tính, giá, giá hiệu dụng, trạng thái hàng (còn, hết, chưa rõ), nguồn tín hiệu, thời điểm đọc. Đánh dấu biến thể chính và biến thể đang được đề xuất thay thế.
- Form **chính sách thay thế**: chế độ, thuộc tính khóa hoặc danh sách chọn, giá trần.
- Lịch sử sự kiện thay thế và biểu đồ giá theo từng biến thể.

### 11.2 Bot Telegram (đề xuất)

| Lệnh | Chức năng |
|---|---|
| `/bienthe <mã>` | Xem các biến thể, giá, tình trạng hàng |
| `/thaythe <mã> on/off` | Bật hoặc tắt thay thế |
| `/thaythe <mã> <chế độ> [giá trần %]` | Đặt chính sách |
| `/dat <mã> [số lượng] [biến thể]` | Tạo đơn, ghi kèm biến thể |

---

## 12. Cấu hình đề xuất (`.env`)

| Biến | Ý nghĩa | Gợi ý |
|---|---|---|
| `FALLBACK_CONFIRM_READS` | Số lần đọc liên tiếp để xác nhận đổi trạng thái hàng | 2 |
| `FALLBACK_CONFIRM_GAP_SEC` | Khoảng cách giữa các lần đọc xác nhận | 180 |
| `FALLBACK_FRESHNESS_MIN` | Dữ liệu biến thể thay thế phải mới hơn mức này | 30 |
| `FALLBACK_PRICE_CEILING_PCT` | Giá trần mặc định so với biến thể chính | 20 |
| `FALLBACK_HOT_INTERVAL_MIN` | Chu kỳ đọc khi biến thể chính đang hết hàng | 10 |
| `FALLBACK_HOT_MAX_HOURS` | Thời gian tối đa giữ nhịp dày | 48 |
| `FALLBACK_MAX_HOT_PRODUCTS` | Số sản phẩm tối đa ở nhịp dày cùng lúc | 10 |
| `FALLBACK_MAX_VARIANTS` | Số biến thể tối đa theo dõi mỗi listing | 30 |

---

## 13. Trường hợp biên và cách xử lý

| Trường hợp | Cách xử lý |
|---|---|
| Biến thể biến mất khỏi listing | Đặt `active = 0`, giữ lịch sử; nếu là biến thể chính thì báo người dùng |
| Biến thể đổi tên hoặc thứ tự | Nhận dạng bằng `variant_key` ổn định (tổ hợp thuộc tính chuẩn hóa), không dựa vào vị trí |
| Mọi biến thể đều hết hoặc `chưa rõ` | Báo "chưa có phương án thay thế", tiếp tục quét |
| Giá biến thể thay thế rẻ bất thường | Chuyển sang quy trình nghi lỗi giá, không xử lý như thay thế thường |
| Hàng đặt trước (pre-order) | Nhận diện riêng, không tính là `còn` như hàng có sẵn |
| Tồn kho khác nhau theo địa chỉ giao hoặc kho gửi | Ghi rõ trong cảnh báo rằng số liệu chưa theo địa chỉ của bạn |
| Giới hạn số lượng mua mỗi người, hàng flash sale bị giữ | Trang có thể hiện còn nhưng không mua được; ghi chú rủi ro này |
| Trang tải chưa xong, đọc ra giá rỗng | Không lưu thành điểm dữ liệu hợp lệ, đọc lại |
| Nguồn là feed affiliate | Feed thường trễ vài giờ; trạng thái hàng từ feed không dùng làm xác nhận cho cảnh báo gấp |
| Listing bị xóa hoặc đổi sang sản phẩm khác | Phát hiện bằng tên hoặc thuộc tính đổi đột ngột, báo người dùng, không tự thay thế |
| Biến thể chính có hàng trở lại nhưng thay thế rẻ hơn | Báo cả hai để người dùng chọn |

---

## 14. Rủi ro và giới hạn

| Rủi ro, giới hạn | Mức | Giảm thiểu |
|---|---|---|
| Hàng hết ngay sau khi nhận cảnh báo | Cao | Đọc lại trước khi báo; ghi thời điểm đọc; người dùng tự kiểm tra trước khi thanh toán |
| Không đọc được tồn kho từng biến thể | Cao | Ba trạng thái; `chưa rõ` không được tính là còn |
| Thay thế không tương đương (khác loại) | Trung bình đến cao | Mặc định "chỉ biến thể đã chọn"; thuộc tính khóa; giá trần |
| Chọn nhầm do đọc sai biến thể | Trung bình | Đối chiếu hai nguồn; bộ kiểm thử bằng trang HTML đã lưu |
| Giá hiệu dụng sai vì thiếu ship, voucher | Trung bình | Gắn nhãn "chưa gồm ship, voucher"; voucher luôn ước tính |
| Bị chặn khi quét dày | Trung bình | Giới hạn số sản phẩm nhịp dày, hạn mức theo sàn, dừng khi gặp captcha |
| Vi phạm điều khoản thu thập tự động | Trung bình đến cao | Ưu tiên feed khi có; tần suất thấp; chỉ dữ liệu công khai |
| Đơn bị hủy dù thấy còn hàng | Trung bình | Không cam kết với khách; ghi nhận kết quả thực tế |

**Giới hạn cốt lõi:** trạng thái "còn hàng" từ bên ngoài không bao giờ chắc 100%. Tính năng giúp phát hiện nhanh và lọc sạch phương án, không thay cho việc người dùng kiểm tra trước khi thanh toán.

---

## 15. Kiểm thử và dữ liệu cần có

### 15.1 Kiểm thử bằng dữ liệu tổng hợp
1. Listing giả có nhiều biến thể, chuyển biến thể chính từ còn sang hết rồi quay lại, kiểm tra từng trạng thái trong máy trạng thái.
2. Ba chế độ chính sách cho ra tập ứng viên khác nhau đúng như kỳ vọng (dùng ví dụ ở mục 7.2).
3. Giá trần loại đúng biến thể quá đắt.
4. Biến thể `chưa rõ` không bao giờ được chọn.
5. Hai lần đọc trái ngược nhau không làm đổi trạng thái.
6. Cảnh báo không lặp; có cảnh báo khi biến thể chính hàng trở lại.
7. Giá bất thường của biến thể thay thế chuyển sang quy trình nghi lỗi giá.

### 15.2 Dữ liệu thật cần để viết bộ đọc
Để bộ đọc khớp với trang thật thay vì đoán, mình cần:
- File HTML (Ctrl+S) của **một listing còn đủ hàng** và **một listing có biến thể hết hàng** trên Lazada.
- Nếu có, ảnh chụp phần chọn biến thể ở cả hai trạng thái.

Với hai mẫu đối chiếu, có thể xác định tín hiệu nào thật sự khác nhau giữa còn và hết.

---

## 16. Kế hoạch triển khai

**Giai đoạn 1: Nền tảng dữ liệu**
- Đọc giá và tồn kho theo biến thể; trạng thái hàng ba mức; lưu `variants` và `variant_history`.
- Sửa quy tắc đánh giá deal: `chưa rõ` tồn kho thì gắn cảnh báo, không tính là còn hàng.

**Giai đoạn 2: Phát hiện hết hàng đáng tin**
- Máy trạng thái xác nhận 2 lần đọc; nhịp quét dày khi hết hàng; đọc lại trước khi báo.

**Giai đoạn 3: Thay thế**
- Bảng quy tắc và sự kiện; thuật toán mục 7; giá hiệu dụng (ban đầu chỉ giá, thêm ship và voucher khi có dữ liệu).
- Cảnh báo bot kèm nút; lệnh `/bienthe`, `/thaythe`; `/dat` ghi kèm biến thể.

**Giai đoạn 4: Giao diện và hoàn thiện**
- Bảng biến thể và form chính sách trên dashboard; thống kê sự kiện và kết quả thực tế.
- Bộ kiểm thử bằng trang HTML đã lưu; giám sát tỷ lệ đọc biến thể thành công.

**Sau đó:** Cấp 2 (sản phẩm tương đương ở shop khác) dựa trên dữ liệu biến thể này.

---

## 17. Câu hỏi còn mở

1. Bạn muốn **mặc định** là "chỉ biến thể đã chọn" (an toàn nhất) hay "cùng thuộc tính khóa"?
2. Giá trần mặc định +20% so với biến thể chính có hợp lý với nhóm hàng của bạn không?
3. Khi hết hàng, bạn muốn nhận cảnh báo ngay cả khi **chưa có** phương án thay thế, hay chỉ khi có?
4. Bạn có thể gửi hai file HTML mẫu (listing còn hàng và listing có biến thể hết) của Lazada không?
5. Bạn có cần biến thể thay thế theo **địa chỉ giao hàng** cụ thể không? Nếu có, tính năng cần thêm bước nhập địa chỉ và sẽ phức tạp hơn.

---

## 18. Tóm tắt một dòng

Theo dõi giá và tồn kho **từng biến thể** trong cùng listing, chỉ kết luận hết hoặc còn khi có **tín hiệu rõ ràng và xác nhận hai lần**, khi biến thể chính hết thì chọn biến thể **còn hàng, đúng chính sách, giá hiệu dụng thấp nhất**, đọc lại ngay trước khi báo, và để **người dùng quyết định**.
