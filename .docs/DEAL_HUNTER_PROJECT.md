# Deal Hunter: Canh giá sản phẩm Shopee và Lazada

> Tổng quan hiện trạng, viết lại theo mã nguồn ngày 03/11/2026 (commit sau `d674a15`).
> Nguồn sự thật cho quyết định: `docs/adr/` (ADR mới hơn thắng ADR cũ hơn). Nguồn sự thật cho thuật ngữ: `GLOSSARY.md`.
> Bản brief cũ ngày 12/10/2026 mô tả kiến trúc ban đầu và không còn đúng; nội dung lịch sử của nó nằm trong ADR 0001 đến 0004.

---

## 1. Tóm tắt

**Deal Hunter** là công cụ cá nhân cho một người làm affiliate. Người dùng dán link sản phẩm Shopee hoặc Lazada, đặt **giá mong muốn**, và hệ thống quét giá mỗi 2 phút, ghi **lịch sử giá**, rồi báo Telegram khi **giá thực trả** (sau voucher) chạm giá mong muốn và sản phẩm còn hàng.

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
6. **Chạy được không cần mạng** nhờ adapter dữ liệu giả, test toàn bộ luồng (198 test).

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
                  Telegram: admin (cảnh báo) · channel (deal, hiện tắt)
```

**Quét hai tầng (ADR 0060):** tầng 1 gọi API sản phẩm của Shopee bằng HTTP kèm cookie, 150 đến 300 ms, không mở trình duyệt. Lazada luôn đi tầng 2. Tầng 2 mở trình duyệt khi giá chạm giá mong muốn, giảm từ 20% so với lần trước, giảm từ 65% so với giá niêm yết, hoặc khi tầng 1 gặp phiên hết hạn/captcha.

**Trình duyệt (ADR 0064):** Chromium headless trong Docker với persistent context, NopeCHA extension đóng gói sẵn trong image (ADR 0004). Kết nối Chrome thật qua CDP (ADR 0063) đã rút lại, code còn giữ sau biến `CDP_URL`.

**Phiên (ADR 0006, 0017, 0049):** cookie từng sàn trong `data/cookies.json` và `data/cookies_lazada.json`, nạp qua dashboard hoặc lệnh `python run.py login <shopee|lazada>` trên máy có màn hình. Trong Docker không tự đăng nhập lại; cookie hết hạn thì admin được báo và phải cấp lại.

## 4. Trạng thái các phân hệ

| Phân hệ | Trạng thái | Ghi chú |
|---|---|---|
| Sản phẩm theo dõi, giá mong muốn | **Đang chạy** | Chu kỳ 2 phút (DB production đang đặt 15) |
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

**Giá mong muốn (ADR 0008, 0056):** giá thực trả nhỏ hơn hoặc bằng giá mong muốn và còn hàng, báo ngay ở mỗi chu kỳ, không cooldown.

**Deal thật (ADR 0003, hiện tắt cảnh báo):** cần 3 điểm lịch sử; giá thực trả thấp hơn trung vị 30 ngày từ 30% trở lên; còn hàng; giá trước giảm từ 500.000₫; với sản phẩm khám phá thêm rating từ 4.0. Giảm sâu theo giá niêm yết nhưng không giảm so với trung vị: gắn nhãn giá gốc ảo.

**Lỗi giá (ADR 0027, 0034, hiện tắt):** giảm từ 65% so với trung vị, hoặc so với lần quét trước khi chưa có trung vị; loại phụ kiện; quét lại sau 2 phút; admin duyệt trước khi đăng kênh.

**Biến thể (ADR 0053, 0054):** sản phẩm theo dõi luôn lấy biến thể rẻ nhất còn hàng, bỏ mã biến thể trong link, bấm qua mọi ô biến thể mỗi lần quét; giá niêm yết chỉ nhận khi có gạch giá thật, không dùng giá trần danh mục.

**Cảnh báo không lặp (`alerter`):** deal thật và giảm giá thường chỉ gửi lại khi giảm thêm từ 5% hoặc đã qua 24 giờ. Không áp cho giá mong muốn.

## 7. Giao diện

**Dashboard** (`templates/dashboard.html`, HTML/CSS/JS thuần, không CDN, chỉ giao diện tối): tab Sản phẩm theo dõi (mặc định) và Siêu Sale hiện; tab Nghi lỗi giá, Theo từ khóa, Lazada TMALL ẩn. Cài đặt: tần suất quét từng phân hệ, công tắc 4 phân hệ, khoảng giá TMALL, ngưỡng giá trị thật, chế độ chỉ-giá-mong-muốn. Có form nạp cookie và nút đăng nhập.

**API** (`web.py`, khoảng 35 route): `/api/summary`, `/api/products` (GET/POST, bulk-delete, purge-junk), `/api/products/<id>` (history, variants, compare, reactivate, target_price), `/api/scan`, `/api/scan-price-errors`, `/api/settings`, `/api/session`, `/api/login`, `/api/cookies`, `/api/search`, `/api/crawl-megasale`, `/api/crawl-tmall`, `/api/anomalies/...`, `/api/keywords/...`, `/api/keyword-products`.

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
python -m pytest -q            # 201 test
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
templates/dashboard.html · tests/ · docs/adr/ (64 ADR) · .docs/ (thiết kế chi tiết từng phân hệ) · GLOSSARY.md
```

## 11. Vấn đề đã biết (rà soát 03/11/2026)

Đã sửa cùng ngày: xác thực tầng 2 khi chạm giá mong muốn không chạy; mặc định config không khớp ADR 0055/0062; bot gửi link gốc thay vì affiliate; script Chrome CDP mở cổng điều khiển ra LAN.

Còn lại, xếp theo mức ảnh hưởng:

1. **Khởi động lại hồi sinh sản phẩm đã ngưng**: migration bật lại mọi sản phẩm theo dõi đang `active=0`, kể cả sản phẩm sàn đã xóa, gây báo admin lặp.
2. **Cầu dao hạn ngạch không hoạt động**: cờ hết lượt không được scanner đọc và bị reset mỗi 10 giây; ngưỡng cảnh báo sớm khai báo nhưng không dùng.
3. **Đăng nhập Lazada tương tác ghi nhầm vào file cookie Shopee**, nên nút đăng nhập Lazada trên dashboard không có tác dụng.
4. **Cảnh báo giá mong muốn lặp mỗi 2 phút**, không cooldown; một sản phẩm nằm dưới giá mục tiêu sinh hàng trăm tin mỗi ngày.
5. **Quét đồng thời không khóa** (quét nhanh xác minh, quét tức thì từ web và bot) có thể gửi đôi cảnh báo và ghi hai dòng lịch sử cùng giây.
6. **Lịch sử giá sắp theo giây**: hai dòng cùng giây làm giá mới nhất không xác định và trung vị có thể lẫn giá vừa lưu.
7. **Vòng quét không có khoảng nghỉ** khi một chu kỳ dài hơn tần suất (Lazada luôn mở trình duyệt).
8. **Gộp sản phẩm trùng link làm mất giá mong muốn** và mồ côi bản ghi cảnh báo, biến thể.
9. **Chuyển hướng về trang chủ bị coi là ngừng bán**: một lần bị chặn bot có thể ngưng cả loạt sản phẩm.
10. **Lịch sử giá không hoàn toàn chỉ-thêm**: dòng mới nhất bị cập nhật khi đổi biến thể; một migration xóa cột giá niêm yết cũ.
11. Nạp cookie từ thread ngoài khi worker bận chỉ ghi log, không nạp.
12. Dashboard không có xác thực; mọi route sửa cấu hình và cookie đều mở.
13. Khoảng một nửa mã nguồn (scanner, playwright, bot, web, dashboard) phục vụ các phân hệ đang tắt.
14. Tài liệu `.docs/*.md` của các phân hệ là bản thiết kế trước khi code, có chi tiết không khớp (đã ghi chú đầu mỗi file).

## 12. Lịch sử quyết định

64 ADR trong `docs/adr/`. Các mốc: 0001 đến 0004 kiến trúc ban đầu; 0005 đến 0029 mở rộng khám phá, Lazada, voucher; 0033 đến 0054 độ chính xác giá và biến thể; 0048 đến 0050 captcha và cảnh báo; 0055, 0057, 0062 thu hẹp về sản phẩm theo dõi; 0060 quét hai tầng; 0063 rồi 0064 thử và rút Chrome CDP.
