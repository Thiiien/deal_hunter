# Deal Hunter: Canh giá sản phẩm Shopee và Lazada

> Tổng quan hiện trạng, viết lại theo mã nguồn ngày 03/11/2026 (commit sau `d674a15`).
> Nguồn sự thật cho quyết định: `docs/adr/` (ADR mới hơn thắng ADR cũ hơn). Nguồn sự thật cho thuật ngữ: `GLOSSARY.md`.
> Bản brief cũ ngày 12/10/2026 mô tả kiến trúc ban đầu và không còn đúng; nội dung lịch sử của nó nằm trong ADR 0001 đến 0004.

---

## 1. Tóm tắt

**Deal Hunter** là công cụ cá nhân cho một người làm affiliate. Người dùng dán link sản phẩm Shopee hoặc Lazada, đặt **giá mong muốn**, và hệ thống quét giá theo nhịp thích ứng (mỗi chu kỳ với sản phẩm gần giá mong muốn, ba chu kỳ một lần với sản phẩm còn xa), ghi **lịch sử giá**, rồi báo Telegram khi **giá thực trả** (sau voucher) chạm giá mong muốn và sản phẩm còn hàng.

Hệ thống còn có các phân hệ **khám phá deal** (theo từ khóa, siêu sale, lỗi giá, TMALL trợ giá) và thuật toán **deal thật** theo trung vị 30 ngày. Từ ADR 0055 và 0062 (01/11/2026), các phân hệ này **đang tắt**: tab ẩn, không quét nền, không gửi Telegram. Chúng bật lại bằng công tắc trong Cài đặt, không cần triển khai lại.

Ba thành phần chạy trong một tiến trình (`run.py`), đóng gói trong một container Docker:

| Thành phần | Vai trò |
|---|---|
| **Scanner + Playwright** | Quét giá hai tầng (HTTP nhanh, trình duyệt xác thực), giải captcha bằng NopeCHA và kéo thanh trượt, quản lý phiên từng sàn |
| **Web dashboard (Flask)** | Tab Sản phẩm theo dõi, tab Siêu Sale (cào thủ công), Cài đặt, nạp cookie, đăng nhập |
| **Telegram bot** | Lệnh quản trị (thêm link, đặt giá, xem danh sách, quét ngay, quota), cảnh báo giá mong muốn, cảnh báo kỹ thuật cho admin |

Một người vận hành, một bot, một kênh, một bộ cookie mỗi sàn. Dashboard không có đăng nhập, chỉ bind 127.0.0.1.

## 2. Nguyên tắc thiết kế

1. **Mọi nguồn trả về cùng một Snapshot**, core không phân biệt sàn.
2. **Lịch sử giá chỉ thêm, không sửa.** Hai chỗ code vi phạm được ghi ở mục 11.
3. **Captcha: tự giải trước, dừng khi lỗi kép.** Cookie, rồi kéo thanh trượt, rồi NopeCHA; thất bại thì dừng sàn đó trong chu kỳ và báo admin (ADR 0048 đến 0050).
4. **Sản phẩm theo dõi là bất khả xâm phạm**: không bị phân hệ khám phá chèn vào, không bị tự ngưng vì lỗi tạm thời (ADR 0030, 0052).
5. **Giữ nhịp thấp**: trình duyệt đầy đủ chỉ mở khi cần xác thực (ADR 0060).
6. **Chạy được không cần mạng** nhờ adapter dữ liệu giả, test toàn bộ luồng (215 test).

## 3. Kiến trúc hiện tại

```
  Nguồn (adapter): PlaywrightAdapter [mặc định]   FeedAdapter (CSV/JSON)   MockAdapter (test)
          │  Tầng 1: HTTP + cookie (Shopee) ─┐
          │  Tầng 2: Chromium headless + NopeCHA + kéo slider (Lazada, xác thực, phục hồi phiên)
          ▼ Snapshot
  run.py vòng lặp 10 s ──► Scanner.scan_due() ──► SQLite (products, price_history, variants, settings, ...)
                                  │                        │
                                  ▼                        ▼
                      Cảnh báo giá mong muốn       Flask dashboard + API JSON
                                  │
                                  ▼
                  Telegram: channel (giá mong muốn, mặc định về admin nếu không có channel) · admin (kỹ thuật)
```

**Quét hai tầng (ADR 0060):** tầng 1 gọi API sản phẩm của Shopee bằng HTTP kèm cookie, 150 đến 300 ms, không mở trình duyệt. Lazada luôn đi tầng 2. Tầng 2 mở trình duyệt khi giá chạm giá mong muốn, giảm từ 20% so với lần trước, giảm từ 65% so với giá niêm yết, hoặc khi tầng 1 gặp phiên hết hạn/captcha.

**Trình duyệt (ADR 0064):** Chromium headless trong Docker với persistent context, NopeCHA extension đóng gói sẵn trong image (ADR 0004). Kết nối Chrome thật qua CDP (ADR 0063) đã rút lại, code còn giữ sau biến `CDP_URL`.

**Phiên (ADR 0006, 0017, 0049):** cookie từng sàn trong `data/cookies.json` và `data/cookies_lazada.json`, nạp qua dashboard hoặc lệnh `python run.py login <shopee|lazada>` trên máy có màn hình. Trong Docker không tự đăng nhập lại; cookie hết hạn thì admin được báo và phải cấp lại.

## 4. Trạng thái các phân hệ

| Phân hệ | Trạng thái | Ghi chú |
|---|---|---|
| Sản phẩm theo dõi, giá mong muốn | **Đang chạy** | Nhịp thích ứng, chu kỳ 5 phút (ADR 0066) |
| Cảnh báo giảm giá thường, deal thật | Tắt | Bởi chế độ chỉ-giá-mong-muốn (ADR 0062) |
| Theo từ khóa | Tắt quét nền, tìm thủ công vẫn được | ADR 0055 |
| Siêu Sale / Flash Sale Lazada | Chỉ cào khi bấm nút, không báo Telegram | ADR 0057 |
| Lỗi giá | Tắt | ADR 0055 + 0062 |
| Lazada TMALL | Tắt | ADR 0055 |
| Biến thể, máy trạng thái tồn kho | Đang chạy, không có công tắc | ADR 0038 đến 0041, 0053, 0054 |

Trạng thái tắt được lưu trong bảng `settings` và, từ commit sửa lỗi ngày 03/11, cũng là mặc định trong `config.py`. Mặc định trong file cấu hình bị DB ghi đè lúc khởi động.

## 5. Dữ liệu

SQLite một kết nối chia sẻ, không WAL. Bảng: `products` (có `source`: user, keyword, flash_sale, price_error, lazada_tmall; `target_price`; `main_variant_id`; `fail_count`), `price_history` (có `final_price`, `campaign`), `variants`, `variant_history`, `fallback_rules`, `fallback_events`, `campaigns`, `alerts`, `scan_log`, `settings`, `keywords`, `keyword_products`, `rejected_items`, `price_anomalies`. Không có bảng `orders`.

## 6. Thuật toán

**Giá mong muốn (ADR 0008, 0065):** giá thực trả nhỏ hơn hoặc bằng giá mong muốn và còn hàng: báo khi bước vào tầm giá, báo lại khi giảm thêm từ 5% hoặc rời tầm rồi quay lại, nhắc mỗi 24 giờ khi vẫn trong tầm.

**Deal thật (ADR 0003, hiện tắt cảnh báo):** cần 3 điểm lịch sử; giá thực trả thấp hơn trung vị 30 ngày từ 30% trở lên; còn hàng; giá trước giảm từ 500.000₫; với sản phẩm khám phá thêm rating từ 4.0. Giảm sâu theo giá niêm yết nhưng không giảm so với trung vị: gắn nhãn giá gốc ảo.

**Lỗi giá (ADR 0027, 0034, hiện tắt):** giảm từ 65% so với trung vị, hoặc so với lần quét trước khi chưa có trung vị; loại phụ kiện; quét lại sau 2 phút; admin duyệt trước khi đăng kênh.

**Biến thể (ADR 0053, 0054):** sản phẩm theo dõi luôn lấy biến thể rẻ nhất còn hàng, bỏ mã biến thể trong link, bấm qua mọi ô biến thể khi quét Lazada hoặc xác thực tầng 2 (Shopee tầng 1 lấy biến thể từ dữ liệu API); giá niêm yết chỉ nhận khi có gạch giá thật, không dùng giá trần danh mục.

**Cảnh báo không lặp (`alerter`):** deal thật và giảm giá thường chỉ gửi lại khi giảm thêm từ 5% hoặc đã qua 24 giờ. Giá mong muốn theo quy tắc riêng ở trên.

## 7. Giao diện

**Dashboard** (`templates/dashboard.html`, HTML/CSS/JS thuần, không CDN, chỉ giao diện tối): tab Sản phẩm theo dõi (mặc định) và Siêu Sale hiện; tab Nghi lỗi giá, Theo từ khóa, Lazada TMALL ẩn. Cài đặt: tần suất quét từng phân hệ, công tắc 4 phân hệ, khoảng giá TMALL, ngưỡng giá trị thật, chế độ chỉ-giá-mong-muốn. Có form nạp cookie và nút đăng nhập.

**API** (`web.py`, 33 route): `/api/summary`, `/api/products` (GET/POST, bulk-delete, purge-junk), `/api/products/<id>` (history, variants, compare, reactivate, target_price), `/api/scan`, `/api/scan-price-errors`, `/api/settings`, `/api/session`, `/api/login`, `/api/cookies`, `/api/search`, `/api/crawl-megasale`, `/api/crawl-tmall`, `/api/anomalies/...`, `/api/keywords/...`, `/api/keyword-products`.

**Bot Telegram** (admin only): `/theodoi` (`/track`, `/add`) nhận link Shopee hoặc Lazada kèm giá mong muốn tùy chọn; `/list` (`/ds`) thẻ sản phẩm 5 thẻ/trang với nút Đặt giá, Xóa; `/setgia` (`/gia`, `/target`); `/xoa` (`/untrack`); `/status`; `/quota`; `/quetngay`; `/tansuat`; `/bienthe`; `/menu`, `/help`. Lệnh của phân hệ đang tắt vẫn tồn tại: `/timkiem`, `/loigia`, `/tukhoa`, `/dstukhoa`.

## 8. Cấu hình

Xem `.env.example` (31 biến, đã khớp `config.py`). Các giá trị lưu trong bảng `settings` (tần suất, công tắc, ngưỡng, chế độ thông báo) ghi đè `.env` lúc khởi động.

## 9. Cài đặt và chạy

```bash
# Docker (khuyên dùng)
cp .env.example .env   # điền TELEGRAM_TOKEN, ADMIN_CHAT_ID, TELEGRAM_CHANNEL_ID; NOPECHA_API_KEY tùy chọn
docker compose up -d --build
docker compose logs -f
# Nạp cookie: dán vào Dashboard > Cookie, hoặc copy data/cookies*.json từ máy có màn hình

# Chạy trực tiếp (máy có màn hình, cho đăng nhập tương tác)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt && pip install -e .
playwright install chromium
python run.py login shopee     # hoặc lazada; mở Chrome để đăng nhập, tự lưu cookie
python run.py                  # web + bot + scheduler; hoặc run_windows.bat (dừng container trước)
python -m pytest -q            # 215 test
```

Docker: image `mcr.microsoft.com/playwright/python:v1.48.0-noble`, `shm_size: 2gb`, chỉ mount `./data`, `.env` qua `env_file`, extension đóng gói sẵn (ADR 0004).

## 10. Cấu trúc thư mục

```
src/deal_hunter/
  adapters/ base.py (Snapshot helpers, Blocked, FetchError, ProductDelisted) · playwright.py · feed.py · mock.py
  scanner.py  vòng quét, quét hai tầng, cảnh báo, phân hệ khám phá
  detector.py deal thật, giá gốc ảo, lỗi giá (pure functions)
  db.py       schema và migration SQLite
  bot.py · notifier.py · alerter.py · quota.py · login.py · campaign.py · classifier.py · affiliate.py · config.py · models.py · web.py
run.py (web + bot + scheduler) · scan.py (CLI) · login.py · dump_prices.py · run_windows.bat
templates/dashboard.html · tests/ · docs/adr/ (66 ADR) · .docs/ (thiết kế chi tiết từng phân hệ) · GLOSSARY.md
```

## 11. Vấn đề đã biết (rà soát 03/11/2026, lượt 2)

Đã sửa cùng ngày: xác thực tầng 2 khi chạm giá mong muốn không chạy; mặc định config không khớp ADR 0055/0062; bot gửi link gốc thay vì affiliate; script Chrome CDP mở cổng điều khiển ra LAN. Lượt 2: cảnh báo giá mong muốn theo ADR 0065; hoàn xu không còn tính vào giá thực trả và số tiền trợ giá không còn bị đọc thành giá bán (voucher phần trăm không ghi trần vẫn được tính, theo ADR 0021/0059); báo giá về admin khi không có channel; tầng 2 lỗi thì bỏ qua lượt; lượt quét hết hàng (giá 0) không còn tính vào giá mới nhất và trung vị; bốn migration chạy mỗi khởi động bị xóa; hạn ngạch captcha chỉ reset theo ngày thay vì mỗi 10 giây (ADR 0050 giữ nguyên: hết hạn ngạch không chặn quét); file cookie Lazada; khóa quét đồng thời; xóa sản phẩm xóa cả bảng con; escape HTML tin Telegram; từ chối link ngoài Shopee/Lazada; nạp ngưỡng giá từ DB khi khởi động. Tối ưu crawl (ADR 0066): nhịp quét thích ứng; chu kỳ không chạy nối đuôi; nghỉ 4–6 giây giữa hai sản phẩm; chờ sau khi bấm ô biến thể theo sự kiện đổi giá thay vì 500 ms cố định; thử nghiệm chặn ảnh trang Lazada (`BLOCK_IMAGES`, đặt 0 nếu captcha tăng).

Còn lại, xếp theo mức ảnh hưởng:

1. **Lịch sử giá sắp theo giây**: hai dòng cùng giây làm giá mới nhất không xác định.
2. **Chỉ bấm tối đa 15 ô biến thể mỗi lần quét, không tổ hợp màu × trục**: 13 sản phẩm có trên 15 biến thể (ví dụ #4166 có 58) có thể có biến thể rẻ hơn chưa từng được nhìn thấy. Người dùng xác nhận giữ nguyên (03/11/2026).
3. **Gộp sản phẩm trùng link làm mất giá mong muốn** và mồ côi bản ghi cảnh báo, biến thể.
4. **Chuyển hướng về trang chủ và chuỗi "không còn tồn tại" ở bất kỳ đâu trong trang bị coi là ngừng bán**: một lần chặn bot hoặc một bình luận có thể ngưng sản phẩm.
5. **Dòng lịch sử giá mới nhất bị cập nhật khi đổi biến thể** (lịch sử chưa hoàn toàn chỉ-thêm).
6. Nạp cookie từ thread ngoài khi worker bận chỉ ghi log, không nạp.
7. Dashboard không có xác thực, kể cả nút xóa tất cả; chấp nhận vì chỉ chạy trong LAN.
8. Dashboard chèn tên danh mục, shop, sản phẩm cào từ sàn vào HTML không escape.
9. Lệnh `/quetngay` quét cả sản phẩm khám phá; lệnh `/loigia` dựng nội dung nhưng không gửi.
10. Khoảng một nửa mã nguồn phục vụ các phân hệ đang tắt; khoảng một phần ba test chạy các phân hệ đó.
11. Tài liệu `.docs/*.md` của các phân hệ là bản thiết kế trước khi code (đã ghi chú đầu mỗi file).

## 12. Lịch sử quyết định

66 ADR trong `docs/adr/`. Các mốc: 0001 đến 0004 kiến trúc ban đầu; 0005 đến 0029 mở rộng khám phá, Lazada, voucher; 0033 đến 0054 độ chính xác giá và biến thể; 0048 đến 0050 captcha và cảnh báo; 0055, 0057, 0062 thu hẹp về sản phẩm theo dõi; 0060 quét hai tầng; 0063 rồi 0064 thử và rút Chrome CDP; 0065 cảnh báo giá mong muốn khi vào tầm giá, thay 0056; 0066 nhịp quét thích ứng và chu kỳ không nối đuôi.
