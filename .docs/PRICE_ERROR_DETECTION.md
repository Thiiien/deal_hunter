# Module phát hiện "lỗi giá" (Price Error Detection)

> **Hiện trạng 03/11/2026:** đã triển khai (ADR 0027, 0034). Phân hệ **đang tắt** theo ADR 0055 và 0062. Không triển khai: cột risk_score/risk_label/outcome, lệnh `/xacminh` và `/ketqua`, biến `ERROR_*` (ngưỡng 65% cố định, cổng là ngưỡng giá trị thật tối thiểu). Code và ADR là nguồn sự thật.

> Tài liệu thiết kế chi tiết cho một module mở rộng của dự án **Deal Hunter**.
> Cập nhật: 23/10/2026.
> **Trạng thái: mới ở mức thiết kế, chưa được viết code.** Phần "Hiện có sẵn" ở mục 3 là những gì dự án đã làm được, các phần còn lại là đề xuất.

---

## 1. Mục tiêu và định nghĩa

### 1.1 "Lỗi giá" là gì
Sản phẩm mà **người bán tự đặt nhầm giá** (thiếu một chữ số, nhầm đơn vị, nhập giá của biến thể rẻ cho cả listing, quên bỏ chương trình khuyến mãi...) khiến giá thấp bất thường so với giá trị thật.

Đặc điểm cần nhớ:
- Tồn tại rất ngắn, thường vài phút đến vài giờ trước khi shop hoặc sàn sửa.
- Thường là listing mới hoặc vừa được chỉnh sửa, nên **chưa có lịch sử giá** để so sánh.
- Phần lớn cảnh báo "lỗi giá" mà một công cụ tự động đưa ra thực ra là **lỗi đọc dữ liệu** hoặc **lừa đảo**, không phải lỗi giá thật.
- Đơn mua được vẫn có thể bị shop hoặc sàn hủy.

### 1.2 Mục tiêu của module
1. Phát hiện sớm các sản phẩm có giá lệch cực mạnh.
2. **Loại bỏ tối đa cảnh báo giả** trước khi báo cho người dùng, vì đây là chỗ dễ làm mất thời gian và uy tín nhất.
3. Đánh giá rủi ro người bán để người dùng biết cái nào đáng xem trước.
4. Báo riêng cho admin để tự quyết định, không tự đăng công khai.
5. Ghi lại kết quả thực tế (mua được, bị hủy, bị sửa giá) để chỉnh ngưỡng dần.

### 1.3 Ngoài phạm vi (cố ý không làm)
- **Khai thác lỗi của hệ thống sàn:** chồng voucher sai cách, lỗi thanh toán, lỗi hoàn tiền, lỗi tính phí. Đây là gian lận, có thể bị khóa tài khoản hoặc dính trách nhiệm pháp lý.
- **Tạo nhiều tài khoản hoặc tự động chốt đơn hàng loạt** khi gặp lỗi giá.
- **Vượt captcha, né chống bot** để quét nhanh hơn (xem mục 9).
- Chỉ hỗ trợ trường hợp **chính người bán đặt nhầm giá**.

---

## 2. Vấn đề thực tế cần giải quyết

| Thách thức | Giải thích |
|---|---|
| Không có lịch sử | Listing mới thì không so được với chính nó |
| Cảnh báo giả do đọc sai | Đọc nhầm giá biến thể, phụ kiện, combo, đặt cọc, cắt mất chữ số |
| Cơ hội rất ngắn | Cần quét thường hơn ở đúng chỗ, nhưng quét dày thì bị chặn |
| Lừa đảo giả dạng lỗi giá | Shop mới, giá rẻ phi lý, kèm liên hệ ngoài sàn |
| Đơn có thể bị hủy | Mất công, mất hoa hồng, mất uy tín nếu đã đăng công khai |
| Trang tìm kiếm khó đọc | Nơi tốt nhất để thấy listing mới lại là nơi chống bot chặt nhất |

---

## 3. Hiện có sẵn trong dự án

Những phần này đã được xây và kiểm thử với dữ liệu giả hoặc feed mẫu:

- `core.evaluate()`: tính trung vị 30 ngày, `disc_hist`, `disc_list`, kiểm tra tồn kho và rating.
- Bảng `price_history` lưu mọi điểm giá, `products`, `alerts`, `orders`, `scan_log`.
- Cơ chế `Blocked`: gặp captcha hoặc đăng nhập thì dừng quét sàn đó và báo admin.
- Bot Telegram: cảnh báo admin, nút "Đặt mua", "Mở link".
- Chống gửi cảnh báo lặp (bảng `alerts`).

Điều này có nghĩa module mới có thể **tận dụng hạ tầng hiện có** thay vì xây lại.

---

## 4. Kiến trúc đề xuất

```
 Nguồn dữ liệu (feed / trình duyệt / từ khóa)
              │  Snapshot mới
              ▼
   ┌───────────────────────┐
   │ 1. Kiểm tra hợp lệ    │  loại giá = 0, quá nhỏ, lệch phi lý do đọc sai
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 2. Phát hiện lệch giá │  so với lịch sử, hoặc nhóm sản phẩm tương tự
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 3. Xác nhận bằng quét │  quét lại 1-2 lần, kiểm tra biến thể, tồn kho
   │    lại                │
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 4. Bộ lọc loại trừ    │  phụ kiện, combo, đặt cọc, biến thể rẻ nhất...
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 5. Điểm rủi ro        │  uy tín shop, đánh giá, dấu hiệu lừa đảo
   │    người bán          │
   └──────────┬────────────┘
              ▼
   Cảnh báo riêng cho admin (Telegram + dashboard), chờ admin quyết định
              ▼
   Ghi nhận kết quả thực tế → chỉnh ngưỡng
```

Mỗi bước có thể loại bỏ sản phẩm, và chỉ những cái qua hết các bước mới được báo.

---

## 5. Chi tiết từng bước

### 5.1 Bước 1: Kiểm tra hợp lệ dữ liệu (trước khi lưu)
Mục tiêu: không để lỗi đọc dữ liệu biến thành "lỗi giá".

Quy tắc đề xuất:
- Giá bằng 0 hoặc nhỏ hơn mức tối thiểu hợp lý (ví dụ dưới 1.000₫) thì loại.
- Giá lệch hơn 70% so với điểm quét liền trước **và** chưa được quét xác nhận thì không lưu thành điểm lịch sử chính thức. Đánh dấu "chờ xác nhận".
- Giá là một khoảng ("199.000 - 450.000") thì lưu **cả giá thấp nhất và cao nhất**, không chỉ số đầu tiên như bản hiện tại.
- Tên sản phẩm đổi đột ngột giữa hai lần quét (độ tương đồng thấp) thì nghi listing bị thay nội dung, đánh dấu để xem lại.

### 5.2 Bước 2: Phát hiện giá lệch cực mạnh

**Trường hợp A: có lịch sử (từ 3 điểm trở lên)**

Dùng công thức đã có `disc_hist`, nhưng với **ngưỡng riêng cho lỗi giá**:

| Mức | Điều kiện (mặc định, chỉnh được) | Nhãn |
|---|---|---|
| Deal thường | `disc_hist` từ 30% | "Deal thật" |
| Nghi lỗi giá | `disc_hist` từ 65% | "Nghi lỗi giá" |
| Cực nghi ngờ | `disc_hist` từ 85% | "Cực bất thường: ưu tiên kiểm tra thủ công" |

**Trường hợp B: chưa có lịch sử (listing mới)**

So với **trung vị của nhóm sản phẩm tương tự**:
- Nhóm được xác định theo từ khóa hoặc danh mục đã dùng để tìm ra sản phẩm.
- Chỉ so khi nhóm có đủ mẫu (ví dụ ít nhất 15 sản phẩm) và độ phân tán không quá lớn.
- Phải đối chiếu thêm các thuộc tính cơ bản (dung lượng, kích thước, số lượng) để tránh so táo với cam.

Trường hợp B phụ thuộc vào chức năng **tìm sản phẩm theo từ khóa**, hiện chưa làm. Nên triển khai trường hợp A trước.

### 5.3 Bước 3: Xác nhận bằng quét lại

Một phát hiện chỉ chuyển sang "đã xác nhận" khi:
1. Quét lại tối thiểu **2 lần**, cách nhau vài phút (tôn trọng hạn mức yêu cầu).
2. Giá ở các lần quét **ổn định** (lệch không quá khoảng 5%).
3. Giá thuộc **đúng biến thể chính** của sản phẩm (không phải biến thể rẻ nhất hay phụ kiện).
4. **Còn hàng** (tồn kho lớn hơn 0, hoặc chưa rõ nhưng không báo hết hàng).
5. Link vẫn mở được và trang không chuyển sang trang khác.

Nếu giá về mức bình thường giữa các lần quét thì chuyển trạng thái `rejected` kèm lý do "giá đã được sửa". Đây cũng là dữ liệu hữu ích để đo thời gian trung bình lỗi giá tồn tại.

### 5.4 Bước 4: Bộ lọc loại trừ (lỗi giá "giả")

Các nguồn cảnh báo giả phổ biến và cách xử lý:

| Nguyên nhân | Cách phát hiện |
|---|---|
| Giá phụ kiện gắn vào tên sản phẩm chính (ốp lưng, dây sạc, giá đỡ) | Từ khóa trong tên ("ốp", "case", "dây", "bao da", "miếng dán"...); giá nhỏ hơn nhiều so với nhóm sản phẩm chính |
| Giá của biến thể rẻ nhất (size, màu, dung lượng) | Lấy đầy đủ danh sách biến thể; so giá từng biến thể |
| Giá một chiếc trong combo hoặc bộ | Từ khóa "combo", "set", "x2", "bộ"; kiểm tra giá trên đơn vị |
| Giá đặt cọc hoặc giữ chỗ | Từ khóa "cọc", "đặt trước", "pre-order" |
| Cắt mất chữ số do parse sai | Thử so với phiên bản giá nhân 10 hoặc 100: nếu khớp với nhóm sản phẩm thì nghi lỗi đọc |
| Đơn vị tiền khác, giá theo kg hoặc theo lít | Kiểm tra thêm thuộc tính đơn vị |
| Listing tạm thời lỗi hiển thị | Quét lại ở bước 3 |

Mọi lý do loại trừ được ghi vào bảng để thống kê và cải thiện sau này.

### 5.5 Bước 5: Điểm rủi ro người bán

Mục đích: một món rẻ phi lý ở shop mới, ít đánh giá thường là lừa đảo chứ không phải lỗi giá.

Các tín hiệu có thể dùng (tùy nguồn dữ liệu có cung cấp hay không, thiếu thì để trung tính, không phỏng đoán):

| Tín hiệu | Ý nghĩa |
|---|---|
| Shop chính hãng (Mall, LazMall, shop được xác minh) | Giảm rủi ro |
| Tuổi shop, số lượng sản phẩm, số người theo dõi | Shop mới và ít hoạt động thì tăng rủi ro |
| Tỷ lệ đánh giá tích cực, số đánh giá | Ít đánh giá, tỷ lệ thấp thì tăng rủi ro |
| Số đã bán và tốc độ tăng đột biến | Tăng đột biến bất thường cần để ý |
| Mô tả có từ khóa liên hệ ngoài sàn (Zalo, chuyển khoản, số điện thoại, link lạ) | Dấu hiệu lừa đảo rõ |
| Hình ảnh và mô tả sao chép từ shop khác | Dấu hiệu listing giả |

Đầu ra: điểm rủi ro 0-100 và 3 nhãn: **"Ưu tiên xem"**, **"Thận trọng"**, **"Nhiều khả năng lừa đảo hoặc lỗi đọc"**.

Lưu ý: điểm này chỉ hỗ trợ ra quyết định, không thay thế việc admin tự kiểm tra shop và điều khoản đổi trả trên sàn.

---

## 6. Mô hình dữ liệu đề xuất

### 6.1 Bảng mới `price_anomalies`

| Cột | Ý nghĩa |
|---|---|
| `id` | Khóa chính |
| `product_id` | Sản phẩm liên quan |
| `detected_at` | Thời điểm phát hiện lần đầu |
| `price` | Giá bất thường |
| `baseline` | Giá cơ sở dùng để so (trung vị lịch sử hoặc của nhóm) |
| `baseline_type` | `history` hoặc `peer_group` |
| `discount` | % lệch so với cơ sở |
| `stage` | `detected`, `confirming`, `confirmed`, `rejected`, `expired` |
| `reject_reason` | Lý do bị loại (phụ kiện, biến thể, giá đã sửa...) |
| `risk_score` | Điểm rủi ro người bán |
| `risk_label` | Nhãn rủi ro |
| `confirmed_at`, `resolved_at` | Thời điểm xác nhận, kết thúc |
| `outcome` | Kết quả thực tế do admin nhập: `bought_ok`, `order_cancelled`, `price_fixed`, `scam`, `ignored` |

### 6.2 Cột bổ sung cho bảng hiện có
- `price_history`: thêm `source` (feed hay trình duyệt), `price_max` (khi giá là khoảng), `validated` (đã qua kiểm tra hợp lệ chưa).
- `products`: thêm `shop_id`, `shop_age_days`, `shop_rating`, `review_count`, `is_official` (khi nguồn có dữ liệu).
- Nếu triển khai theo dõi biến thể: bảng `variants(product_id, variant_key, name)` và `price_history.variant_id`.

---

## 7. Cấu hình đề xuất (`.env`)

| Biến | Ý nghĩa | Mặc định gợi ý |
|---|---|---|
| `ERROR_MIN_DISCOUNT` | % lệch tối thiểu để nghi lỗi giá | 65 |
| `ERROR_EXTREME_DISCOUNT` | % lệch để gắn nhãn cực bất thường | 85 |
| `ERROR_CONFIRM_SCANS` | Số lần quét xác nhận | 2 |
| `ERROR_CONFIRM_GAP_SEC` | Khoảng cách giữa các lần xác nhận | 180 |
| `ERROR_STABLE_TOLERANCE` | Độ lệch giá cho phép giữa các lần xác nhận (%) | 5 |
| `ERROR_MIN_PRICE` | Giá tối thiểu hợp lệ | 1000 |
| `ERROR_PEER_MIN_SAMPLES` | Số mẫu tối thiểu của nhóm so sánh | 15 |
| `ERROR_MAX_ALERTS_PER_HOUR` | Giới hạn số cảnh báo/giờ để tránh ngập tin | 5 |
| `ERROR_RATE_LIMIT_PER_HOUR` | Hạn mức yêu cầu quét/giờ cho từng sàn | tùy sàn, đặt thấp |

Các giá trị này là điểm khởi đầu, nên chỉnh theo từng nhóm hàng sau khi có dữ liệu thực.

---

## 8. Chiến lược quét

Mục tiêu: phát hiện sớm **mà không quét dày**.

1. **Hàng đợi ưu tiên:** listing mới, sản phẩm giá biến động nhiều, nhóm hàng giá trị cao được quét thường hơn; sản phẩm giá đứng yên thì quét thưa.
2. **Hạn mức theo sàn:** đặt trần số yêu cầu mỗi giờ cho từng sàn, giữ độ trễ ngẫu nhiên giữa các lần tải.
3. **Thử lại có chờ tăng dần** khi lỗi mạng.
4. **Dừng khi gặp chặn:** có captcha hoặc đòi đăng nhập thì dừng quét sàn đó, báo admin (đã có sẵn cơ chế `Blocked`).
5. **Nguồn dữ liệu:** feed affiliate là nguồn ổn định nhất nhưng thường **chậm hơn giá thực vài giờ**, nên có thể bỏ lỡ lỗi giá đã được sửa. Quét trình duyệt nhanh hơn nhưng dễ bị chặn, và trang tìm kiếm sắp xếp theo mới nhất là nơi chống bot chặt nhất. Mình chưa kiểm chứng được hành vi này trên sàn thật.
6. **Không dùng proxy xoay vòng hay giả dạng trình duyệt** để quét nhanh hơn.

---

## 9. Ranh giới pháp lý và đạo đức

- Dự án chỉ xử lý trường hợp **chính người bán đặt nhầm giá**, hỗ trợ khai thác hệ thống sàn voucher, hoàn tiền của hệ thống.
- Không tự động mua hàng loạt, không dùng nhiều tài khoản, chỉ báo link về
- Điều khoản về thu thập dữ liệu tự động của các sàn thường hạn chế; rủi ro này do người dùng tự chịu khi chọn cách cào trình duyệt.

---

## 10. Quy trình vận hành cho admin

1. Bot gửi cảnh báo **riêng cho admin**, gồm: tên, sàn, giá hiện tại, giá cơ sở, % lệch, trạng thái xác nhận, điểm rủi ro, lý do còn nghi ngờ.
2. Admin mở trang sản phẩm, tự kiểm tra: biến thể, tồn kho, shop, điều khoản đổi trả.
3. Admin chọn hành động: **Mở link**, **Bỏ qua**, **Đánh dấu đã xác minh**.
4. Sau khi mua, admin cập nhật kết quả trên dashboard: giao hàng thành công, bị hủy, giá bị sửa.
5. **Không đăng công khai ngay.** Chỉ chia sẻ cho khách hoặc kênh khi đơn đã được xác nhận vận chuyển, vì đăng sớm khiến lỗi bị sửa nhanh hơn và sinh ra nhiều đơn bị hủy trên kênh của bạn.

### Ảnh hưởng đến affiliate
- Đơn bị hủy thì không có hoa hồng.
- Nhiều chương trình xem xét lại đơn bất thường. Hãy đọc kỹ điều khoản chương trình bạn tham gia trước khi dựa vào nguồn thu này.

---

## 11. Lệnh Telegram và dashboard đề xuất

**Bot:**

| Lệnh | Chức năng |
|---|---|
| `/loigia` | Danh sách cảnh báo nghi lỗi giá đang mở (chỉ admin) |
| `/loigia <mã>` | Chi tiết một cảnh báo: dữ liệu, bước đã qua, điểm rủi ro |
| `/xacminh <mã>` | Đánh dấu admin đã tự kiểm tra |
| `/ketqua <mã> <bought_ok\|cancelled\|fixed\|scam>` | Ghi nhận kết quả thực tế |

**Dashboard:** thêm thẻ "Nghi lỗi giá", bảng các cảnh báo kèm trạng thái, và thống kê độ chính xác (bao nhiêu cảnh báo được xác nhận, bao nhiêu mua được, bao nhiêu bị hủy).

---

## 12. Đo lường và cải thiện

| Chỉ số | Cách tính | Dùng để |
|---|---|---|
| Độ chính xác cảnh báo | Số `confirmed` chia tổng cảnh báo | Chỉnh ngưỡng, tăng bộ lọc |
| Tỷ lệ cảnh báo giả theo lý do | Thống kê `reject_reason` | Biết bộ lọc nào cần cải thiện |
| Thời gian tồn tại của lỗi giá | Từ phát hiện đến khi giá được sửa | Đặt tần suất quét hợp lý |
| Tỷ lệ mua thành công và bị hủy | Từ `outcome` | Đánh giá giá trị thực của module |
| Tỷ lệ lừa đảo theo điểm rủi ro | `scam` theo khoảng điểm | Hiệu chỉnh điểm rủi ro |

Sau vài tuần dữ liệu, chỉnh ngưỡng riêng cho từng nhóm hàng, vì đồ điện tử và mỹ phẩm không có biên giảm giá giống nhau.

---

## 13. Kiểm thử

1. **Dữ liệu tổng hợp:** tạo lịch sử giá giả rồi chèn một điểm giá sập, kiểm tra từng nhãn (deal thường, nghi lỗi giá, cực bất thường).
2. **Các ca "lỗi giá giả":** phụ kiện, biến thể rẻ nhất, combo, đặt cọc, giá thiếu chữ số, giá dạng khoảng, kiểm tra bộ lọc loại đúng.
3. **Ca giá được sửa giữa lần xác nhận:** phải chuyển `rejected`.
4. **Trang HTML mẫu đã lưu** của mỗi sàn để kiểm tra bộ đọc. Khi sàn đổi giao diện, test hỏng sẽ cảnh báo.
5. **Giới hạn cảnh báo:** kiểm tra không vượt `ERROR_MAX_ALERTS_PER_HOUR`.
6. Thử trên sàn thật chỉ sau khi các bước trên qua, bắt đầu với số lượng sản phẩm nhỏ.

---

## 14. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Cảnh báo giả nhiều, mất thời gian | Cao | Bước xác nhận và bộ lọc loại trừ; theo dõi độ chính xác |
| Đơn bị hủy, mất hoa hồng và uy tín | Cao | Không đăng công khai sớm; không cam kết với khách |
| Bị chặn khi quét dày | Cao | Hạn mức thấp, ưu tiên hàng đợi, dừng khi gặp captcha |
| Lừa đảo giả dạng lỗi giá | Trung bình đến cao | Điểm rủi ro người bán; admin tự kiểm tra |
| Dữ liệu feed trễ nên bỏ lỡ cơ hội | Trung bình | Kết hợp quét trình duyệt cho nhóm hàng chọn lọc |
| Vi phạm điều khoản sàn khi cào | Trung bình đến cao | Chỉ dữ liệu công khai, tần suất thấp, ưu tiên nguồn chính thống |
| Hiểu nhầm là khai thác lỗi hệ thống | Cao nếu làm sai | Giữ đúng phạm vi: chỉ lỗi do người bán đặt giá |

---

## 15. Kế hoạch triển khai

**Giai đoạn 1: Nền tảng (ưu tiên cao nhất)**
- Kiểm tra hợp lệ dữ liệu giá, lưu cả giá thấp nhất và cao nhất khi là khoảng.
- Thêm mức "nghi lỗi giá" vào `core.evaluate()` với cấu hình ngưỡng.
- Bước xác nhận bằng quét lại.
- Bảng `price_anomalies`, lệnh `/loigia`, thẻ trên dashboard.

**Giai đoạn 2: Giảm cảnh báo giả**
- Theo dõi giá theo biến thể.
- Bộ lọc loại trừ (phụ kiện, combo, đặt cọc...).
- Giám sát tỷ lệ đọc thành công của từng sàn, báo khi tụt bất thường.
- Lưu HTML hoặc ảnh chụp khi đọc lỗi để sửa selector nhanh.

**Giai đoạn 3: Chất lượng quyết định**
- Điểm rủi ro người bán.
- Ghi nhận kết quả thực tế (`/ketqua`) và thống kê độ chính xác.
- Hàng đợi quét ưu tiên theo mức biến động.

**Giai đoạn 4: Mở rộng**
- Tìm theo từ khóa, so với nhóm sản phẩm tương tự cho listing mới.
- Chỉnh ngưỡng theo từng nhóm hàng dựa trên dữ liệu thực.

---

## 16. Câu hỏi còn mở

1. Bạn dùng nguồn dữ liệu nào là chính (feed affiliate hay trình duyệt)? Điều này quyết định tốc độ phát hiện thực tế.
2. Nhóm hàng và sàn nào bạn muốn ưu tiên? Ngưỡng và bộ lọc phụ thuộc vào nhóm hàng.
3. Bạn mua để dùng, bán lại, hay chia sẻ cho cộng đồng? Điều này ảnh hưởng đến cách báo và rủi ro uy tín.
4. Bạn chấp nhận mức cảnh báo giả bao nhiêu để đổi lấy phát hiện sớm hơn? Ngưỡng 65% có thể cần nâng hoặc hạ.
5. Chương trình affiliate bạn tham gia có điều khoản gì về đơn bị hủy hoặc đơn bất thường?

---

## 17. Tóm tắt một dòng

Phát hiện giá lệch cực mạnh, **xác nhận bằng quét lại**, **lọc kỹ lỗi đọc dữ liệu và lừa đảo**, báo riêng cho admin, đừng đăng công khai sớm, và chỉ làm trong phạm vi người bán tự đặt nhầm giá.
