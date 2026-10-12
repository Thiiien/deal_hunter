# Deal Hunter: Hệ thống theo dõi giá và săn deal Shopee, Lazada, TikTok Shop

> Tài liệu đề án (project brief) tổng hợp từ các trao đổi ban đầu đến hiện tại.
> Cập nhật: 12/10/2026. Trạng thái: Đã chốt kiến trúc chi tiết (chuẩn bị triển khai code).

---

## 1. Tóm tắt

**Deal Hunter** là một công cụ tự động hóa giúp người làm MMO mảng "săn hàng giảm giá, mã giảm giá" tiếp thị liên kết (affiliate). Công cụ tự động theo dõi giá sản phẩm, lưu lịch sử giá và phân biệt **deal thật** với **giảm giá ảo** (shop nâng giá gốc rồi "sale sốc"). Hệ thống tích hợp giải Captcha tự động hoàn toàn (bằng NopeCHA extension nạp vào Playwright), giám sát hạn ngạch giải mã, tự động đăng bài deal hời vào kênh Telegram và quản lý qua dashboard web.

Ba thành phần chính:

| Thành phần | Vai trò |
|---|---|
| **Core (Python + SQLite)** | Lấy dữ liệu giá qua Playwright Stealth + NopeCHA Extension, phát hiện deal thật, quản lý phiên và hạn ngạch |
| **Web dashboard (Flask)** | Quan sát tổng quan: deal, biểu đồ giá, danh sách theo dõi, cảnh báo hạn ngạch captcha |
| **Telegram (Bot & Channel)** | Nhận lệnh nạp link từ admin (`/theodoi`), cảnh báo hạn ngạch/lỗi riêng cho admin, tự động bắn bài deal vào Channel công cộng |

Trọng tâm Giai đoạn 1: Ưu tiên **Shopee**, vận hành tự động 100% cho cá nhân làm tiếp thị liên kết.

---

## 2. Bối cảnh và mục tiêu

### 2.1 Người dùng
Người làm MMO cá nhân tập trung kiếm thu nhập hoa hồng tiếp thị liên kết (Affiliate) từ các đợt giảm giá sâu trên sàn TMĐT.

### 2.2 Mục tiêu của dự án
- Tự động hóa 100% từ khâu thu thập dữ liệu giá, vượt qua rào cản Captcha của sàn đến khâu đăng deal.
- Phát hiện nhanh các sản phẩm giảm giá mạnh **thật sự** (so với trung vị 30 ngày), loại bỏ hoàn toàn bẫy nâng giá gốc ảo.
- Tự động định dạng bài đăng tiếp thị kèm link affiliate bắn vào Telegram Channel.
- Cảnh báo chủ động cho người vận hành khi hạn ngạch giải captcha sắp hết.

### 2.3 Không nằm trong phạm vi (Giai đoạn 1)
- Không nhận đặt hàng hộ / checkout thay người dùng (cắt bỏ luồng khách vãng lai và quản lý đơn mua hộ để giữ hệ thống tinh gọn).
- Không cam kết thu nhập cố định.

---

## 3. Nguyên tắc thiết kế

1. **Ưu tiên nguồn dữ liệu chính thống** (feed, API affiliate) trước khi cào web.
2. **Mọi nguồn trả về cùng một dạng dữ liệu** (`Snapshot`), nên core không phân biệt sàn.
3. **Không bao giờ ghi đè giá.** Mỗi lần quét thêm một dòng vào bảng lịch sử, vì giá trị cốt lõi của công cụ nằm ở lịch sử.
4. **Gặp chặn thì dừng, không thử dồn dập.** Khi một sàn trả về captcha hoặc đòi đăng nhập, hệ thống dừng quét sàn đó và báo admin.
5. **Giữ nhịp quét thấp**, có giới hạn tốc độ và độ trễ ngẫu nhiên giữa các lần tải trang.
6. **Chạy được ngay không cần mạng** nhờ adapter dữ liệu giả, để kiểm thử toàn bộ luồng.

---

## 4. Kiến trúc tổng thể

```
        ┌─────────────────────────── Nguồn dữ liệu (adapter) ───────────────────────────┐
        │  FeedAdapter (CSV/JSON affiliate)   SeleniumAdapter   [PlaywrightAdapter]   MockAdapter │
        └───────────────────────────────────────┬───────────────────────────────────────┘
                                                │ Snapshot (giá, giá gốc, tồn kho, rating, đã bán)
                                                ▼
   Scheduler ──► core.scan_all() ──► SQLite (products, price_history, orders, alerts, scan_log)
                      │                         │
                      ▼                         ▼
             Bộ phát hiện deal           Flask web (dashboard + API JSON)
                      │
                      ▼
               Bot Telegram ◄──► Người dùng (cảnh báo, /deals, /gia, /dat, /donhang)
```

### 4.1 Năm khối chức năng
1. **Scheduler:** quét định kỳ (mặc định 30 phút). Hiện chạy trong job nền của bot hoặc bằng `scan.py --loop`.
2. **Fetcher/Parser (adapter):** lấy và chuẩn hóa dữ liệu từ từng nguồn.
3. **Database:** SQLite, mỗi lần quét ghi một dòng vào `price_history`.
4. **Bộ phát hiện deal:** so giá hiện tại với giá trung vị 30 ngày, kiểm tra tồn kho và rating.
5. **Notifier:** gửi cảnh báo qua Telegram kèm nút đặt mua và link affiliate.

---

## 5. Nguồn dữ liệu và độ ưu tiên

| Ưu tiên | Nguồn | Ưu điểm | Nhược điểm |
|---|---|---|---|
| 1 | **Feed/API của mạng affiliate** (Accesstrade, Ecomobi, Masoffer, chương trình affiliate của sàn) | Ổn định, có sẵn giá, giá gốc, hoa hồng, link affiliate; không đụng chống bot | Phụ thuộc dữ liệu họ cung cấp, có thể không đủ mọi sản phẩm |
| 2 | **Công cụ no-code** (Octoparse, ParseHub, Web Scraper, Browse AI) hoặc **Apify** | Thử ý tưởng nhanh | Khó theo dõi liên tục, vẫn gặp chặn bot, tốn phí |
| 3 | **Trình duyệt tự động** (Selenium hoặc Playwright) | Linh hoạt, lấy được trang không có feed | Dễ bị chặn, phải chỉnh selector thường xuyên, rủi ro điều khoản |
| 4 | **API nội bộ của trang** (JSON trong tab Network) | Nhanh, nhẹ | Hay bị ký/mã hóa và đổi liên tục, rủi ro điều khoản cao |
| 5 | **Dịch vụ cào trả phí** (ScraperAPI, ZenRows, Bright Data...) | Họ lo proxy | Tốn tiền theo lượt, vẫn là thu thập tự động |
| 6 | **Scrapy** (+ scrapy-playwright) | Mạnh cho hàng chục nghìn sản phẩm | Quá thừa ở quy mô khởi đầu |

**Khuyến nghị:** bắt đầu bằng feed affiliate, thử nhóm hàng mục tiêu bằng no-code hoặc Apify, rồi mới tự viết bằng trình duyệt tự động nếu feed thiếu dữ liệu.

---

## 6. Core: mô hình dữ liệu và logic

### 6.1 Snapshot (dạng dữ liệu chung)
Mỗi adapter trả về đối tượng gồm: `platform`, `item_key`, `url`, `name`, `shop`, `price`, `list_price`, `stock`, `rating`, `sold`.

`item_key` được trích từ link bằng biểu thức chính quy cho từng sàn (ví dụ Shopee `-i.<shopid>.<itemid>`, Lazada `-i<id>-s<id>.html`, TikTok `/product/<id>`). Link rút gọn hoặc không nhận dạng được thì dùng mã băm của host và path.

### 6.2 Cơ sở dữ liệu SQLite

| Bảng | Mục đích | Cột chính |
|---|---|---|
| `products` | Sản phẩm đang theo dõi | `id`, `platform`, `item_key` (duy nhất cùng `platform`), `url`, `name`, `shop`, `rating`, `sold`, `active`, `created_at` |
| `price_history` | Lịch sử giá, chỉ thêm không ghi đè | `product_id`, `price`, `list_price`, `stock`, `ts` (chỉ mục theo `product_id, ts`) |
| `orders` | Đơn tạo từ Telegram | `product_id`, `chat_id`, `qty`, `price_at_order`, `status` (`pending`/`bought`/`cancelled`), `note`, `created_at` |
| `alerts` | Chống gửi cảnh báo lặp | `product_id`, `last_price`, `sent_at` |
| `scan_log` | Nhật ký mỗi lần quét | `ts`, `ok`, `fail`, `msg` |

SQLite chạy chế độ WAL để web và bot đọc ghi đồng thời ổn hơn.

### 6.3 Thuật toán phát hiện deal thật
Với mỗi sản phẩm:
1. Lấy giá mới nhất và các giá trong **30 ngày trước đó** (không tính điểm mới nhất).
2. Cần **ít nhất 3 điểm lịch sử** (tức tối thiểu 4 lần quét) mới kết luận. Chưa đủ thì ghi chú "đang thu thập lịch sử".
3. Tính **giá trung vị 30 ngày** và `disc_hist = 1 - giá_hiện_tại / trung_vị`.
4. Tính thêm `disc_list = 1 - giá_hiện_tại / giá_gốc_shop_công_bố`.
5. Là **deal thật** khi cùng lúc thỏa:
   - `disc_hist` từ ngưỡng `DEAL_MIN_DISCOUNT` trở lên (mặc định 30%)
   - còn hàng (hoặc chưa rõ tồn kho)
   - rating từ `DEAL_MIN_RATING` trở lên (mặc định 4.0) hoặc chưa có rating
6. Các trường hợp khác được gắn nhãn:
   - Giảm sâu theo `disc_list` nhưng không giảm so với lịch sử: **"giá gốc cao ảo"**
   - Giảm sâu nhưng hết hàng hoặc rating thấp: không báo deal
   - Còn lại: "giá bình thường"

Đây là phần tạo khác biệt chính so với các nơi chỉ đăng "giảm X%" theo giá gốc.

### 6.4 Quét và xử lý chặn
- Adapter feed tự đề xuất sản phẩm mới (`discover`). Adapter trình duyệt quét lần lượt các sản phẩm đang theo dõi.
- Gặp `Blocked` (captcha, đăng nhập, xác minh): đánh dấu sàn đó là bị chặn, **bỏ qua phần còn lại của sàn trong lượt quét**, ghi vào `scan_log` và báo admin qua Telegram.
- Lỗi đọc giá lẻ (`FetchError`) chỉ bỏ qua sản phẩm đó.

### 6.5 Cảnh báo không lặp
Chỉ gửi lại cảnh báo cho một sản phẩm khi chưa từng gửi, hoặc giá giảm thêm hơn 5% so với lần báo trước, hoặc đã qua 24 giờ.

### 6.6 Link affiliate
Cấu hình mẫu theo từng sàn trong `.env` (`AFF_SHOPEE`, `AFF_LAZADA`, `AFF_TIKTOK`) với hai biến thay thế: `{url}` (link đã mã hóa) và `{raw}` (link gốc). Mọi link gửi ra (bot, dashboard) đều đi qua hàm này, tránh quên gắn affiliate.

---

## 7. Web dashboard

Backend Flask (`web.py`), giao diện một trang (`templates/dashboard.html`) bằng HTML/CSS/JS thuần, không phụ thuộc CDN.

**Hiển thị:**
- Thanh số liệu: số deal thật, số sản phẩm theo từng sàn, số đơn chờ, lần quét gần nhất (kèm cảnh báo nếu bị chặn).
- Bảng sản phẩm có bộ lọc "Deal thật" hoặc "Tất cả" và lọc theo sàn: giá hiện tại, trung vị 30 ngày, giảm thật, giảm theo giá gốc, biểu đồ nhỏ 30 ngày, rating và số đã bán.
- Bấm vào một dòng để xem biểu đồ giá chi tiết kèm đường trung vị.
- Form dán link để thêm theo dõi, nút "Quét giá ngay".
- Bảng đơn từ Telegram, có nút "Đánh dấu đã mua" và "Huỷ".

**API JSON:** `GET /api/summary`, `GET/POST /api/products`, `GET /api/products/<id>/history`, `POST /api/scan`, `GET /api/orders`, `POST /api/orders/<id>`.

**Chất lượng giao diện:** hỗ trợ chế độ sáng và tối, hiển thị tốt trên điện thoại (bảng cuộn ngang), có viền focus cho điều hướng bàn phím, và thoát ký tự HTML khi hiển thị dữ liệu từ sàn.

**Lưu ý bảo mật:** mặc định web chỉ lắng nghe `127.0.0.1` và **chưa có đăng nhập**. Nếu mở ra internet phải thêm xác thực (xem lộ trình).

---

## 8. Kiến trúc Playwright, NopeCHA Extension và Giải Captcha tự động

### 8.1 Playwright Persistent Context
- Sử dụng **Playwright Chromium** với `launch_persistent_context` lưu dữ liệu hồ sơ trình duyệt tại `data/browser_profile`.
- Chạy cờ `--headless=new` để trình duyệt chạy ngầm 100% dưới background, không hiển thị cửa sổ làm phiền người dùng nhưng vẫn hỗ trợ nạp extension đầy đủ.
- Tự động lưu và tái sử dụng session (`storage_state.json`), giảm thiểu tối đa số lần kích hoạt captcha của sàn.

### 8.2 Tự động giải Captcha bằng NopeCHA Extension
- Nạp trực tiếp thư mục unpacked của **NopeCHA Extension** vào Chromium qua cờ `--load-extension`.
- Tận dụng gói **100 lượt giải miễn phí/ngày** của NopeCHA (hoàn toàn 0 đồng cho cá nhân).
- Mã crawler hoàn toàn không cần can thiệp xử lý ảnh hay giả lập tọa độ chuột phức tạp; Extension tự phát hiện và giải captcha ngay trên DOM.

### 8.3 Giám sát hạn ngạch (Quota Monitor) & Bộ ngắt mạch (Circuit Breaker)
- **Giám sát 2 tầng:**
  1. *Kiểm tra định kỳ:* Đầu mỗi chu kỳ quét, gọi `GET https://api.nopecha.com/status?key=<KEY>` để kiểm tra số dư. Nếu `credit ≤ 10`, gửi cảnh báo sớm về Admin Telegram.
  2. *Bắt lỗi tức thời:* Nếu gặp lỗi hết hạn ngạch trong quá trình cào, kích hoạt cảnh báo khẩn cấp kèm link nạp tiền.
- **Bộ ngắt mạch an toàn:** Khi cạn hạn ngạch hoặc gặp lỗi captcha liên tiếp 3 lần, crawler tự động chuyển sang chế độ "ngủ đông" (tạm ngắt cào để bảo vệ địa chỉ IP không bị Shopee khóa vĩnh viễn), tự động phục hồi khi sang ngày mới hoặc sau khi admin nạp thêm hạn ngạch.

---

## 9. Telegram: Quản trị và Kênh phát sóng tự động (Broadcast Channel)

### 9.1 Lệnh Bot quản trị (Chỉ Admin)

| Lệnh | Chức năng |
|---|---|
| `/theodoi <link>` | Thêm link sản phẩm Shopee vào danh sách theo dõi |
| `/status` | Xem trạng thái hệ thống: số sản phẩm, lần quét gần nhất, số deal hôm nay |
| `/quota` | Kiểm tra số lượt giải captcha còn lại của NopeCHA |
| `/quetngay` | Kích hoạt chu kỳ quét ngay lập tức |

### 9.2 Kênh phát sóng tự động (Broadcast Channel)
- Bot tự động định dạng bài đăng tiếp thị cho mỗi "Deal thật" phát hiện được và bắn vào Telegram Channel công cộng:
  - Ảnh đại diện sản phẩm
  - Tiêu đề sản phẩm
  - Giá hiện tại vs Giá trung vị 30 ngày (kèm nhãn % giảm thật)
  - Đánh giá sao (rating) và số lượt bán
  - Nút bấm trực tiếp gắn **Affiliate Link** để điều hướng khách vào mua hàng trên sàn.
- Cảnh báo chống lặp: Không đăng lại cùng 1 deal trong vòng 24h trừ khi giá giảm sâu thêm > 5%.

---

## 10. Cấu trúc thư mục

```
dealhunter/
├── adapters/
│   ├── __init__.py          # get_adapter(): chọn nguồn theo FETCH_MODE
│   ├── base.py              # Snapshot, Blocked, FetchError, nhận diện sàn, item_key, parse_price
│   ├── playwright_adapter.py# Playwright Chromium + NopeCHA extension + Persistent Context
│   ├── feed_adapter.py      # Đọc CSV/JSON từ affiliate
│   └── mock_adapter.py      # Dữ liệu giả để demo
├── extensions/
│   └── nopecha/             # Unpacked Chrome Extension NopeCHA
├── core.py                  # Lưu dữ liệu, phát hiện deal, quét, cảnh báo, hạn ngạch
├── db.py                    # Schema SQLite
├── config.py                # Đọc cấu hình từ .env
├── quota.py                 # Giám sát hạn ngạch NopeCHA và cảnh báo
├── run.py                   # Tiến trình nền tự động hóa toàn trình (Web + Bot + Scheduler)
├── scan.py                  # CLI: quét một lần, --loop, --add <link>
├── web.py                   # Flask dashboard và API
├── bot.py                   # Bot Telegram (lệnh quản trị & bắn deal vào Channel)
├── templates/dashboard.html # Giao diện Dashboard
├── Dockerfile               # Docker image dựa trên Playwright Python
├── docker-compose.yml       # Quản lý container, volume persistence, shm_size 2GB
├── .env.example
├── requirements.txt
└── README.md
```

---

## 11. Cấu hình (`.env`)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `DB_PATH` | Đường dẫn file SQLite | `data/deals.db` |
| `FETCH_MODE` | `mock`, `feed` hoặc `playwright` | `playwright` |
| `DEAL_MIN_DISCOUNT` | % giảm tối thiểu so với trung vị 30 ngày | 30 |
| `DEAL_MIN_RATING` | Rating shop tối thiểu | 4.0 |
| `SCAN_INTERVAL_MIN` | Chu kỳ quét giá (phút) | 30 |
| `REQUEST_DELAY_SEC` | Nghỉ ngẫu nhiên giữa 2 sản phẩm (giây) | 8 |
| `NOPECHA_API_KEY` | API Key của NopeCHA (gói Free 100/ngày) | (trống) |
| `AFF_SHOPEE` | Mẫu gắn link Shopee Affiliate | `{raw}` |
| `TELEGRAM_TOKEN` | Token Bot từ BotFather | (trống) |
| `ADMIN_CHAT_ID` | Telegram Chat ID riêng của Admin (nhận cảnh báo quota, lỗi) | (trống) |
| `TELEGRAM_CHANNEL_ID` | Telegram Channel công cộng (nơi bot tự động đăng deal) | (trống) |
| `WEB_HOST`, `WEB_PORT` | Địa chỉ Web Dashboard | `0.0.0.0`, 5000 |

---

## 12. Cài đặt và Triển khai

### Cách 1: Triển khai nhanh bằng Docker (Khuyên dùng)

```bash
cp .env.example .env
# Điền TELEGRAM_TOKEN, ADMIN_CHAT_ID, TELEGRAM_CHANNEL_ID, NOPECHA_API_KEY vào .env

# Khởi chạy toàn bộ hệ thống ngầm trong 1 container:
docker compose up -d --build

# Xem log hoạt động:
docker compose logs -f
```

### Cách 2: Chạy trực tiếp trên máy (Python local)

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env

# Chạy toàn bộ hệ thống (Web + Bot + Tự động quét):
python run.py
```

---

## 13. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Core, SQLite, phát hiện deal | Đã làm và **đã kiểm thử** với dữ liệu giả và feed mẫu |
| FeedAdapter | Đã làm và đã kiểm thử với file mẫu |
| Web dashboard và API | Đã làm, đã kiểm thử các endpoint bằng test client |
| Giao diện trình duyệt (HTML/JS) | Đã viết, **chưa mở thử trên trình duyệt thật** |
| Bot Telegram | Đã viết, mới kiểm tra cú pháp, **chưa chạy với token thật** |
| SeleniumAdapter | Đã viết, mới kiểm tra cú pháp, **chưa thử trên sàn thật**, selector cần chỉnh |
| Theo dõi theo từ khóa/danh mục | Chưa làm |
| PlaywrightAdapter | Chưa làm |
| Đăng nhập cho web dashboard | Chưa làm |

---

## 14. Rủi ro và cách giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Sàn chặn IP/tài khoản khi cào | Cao | Ưu tiên feed; quét thưa; dừng khi gặp captcha; không dùng tài khoản chính |
| Vi phạm điều khoản sàn | Cao | Chỉ dùng dữ liệu công khai, tần suất thấp; ưu tiên nguồn chính thống |
| Selector hỏng do giao diện đổi | Cao | Đọc JSON-LD trước; theo dõi `scan_log`; chỉnh định kỳ |
| Đăng deal đã hết hàng/hết mã | Trung bình | Kiểm tra tồn kho; quét lại trước khi gửi; gắn thời điểm cập nhật |
| Giá dữ liệu sai làm mất uy tín kênh | Trung bình | Cần đủ lịch sử; ngưỡng rating; không cam kết "rẻ nhất" |
| Mất hoa hồng do link affiliate sai | Trung bình | Mọi link đi qua `affiliate_link()`; kiểm tra thủ công mẫu link |
| Lộ dashboard khi mở ra internet | Trung bình | Chỉ chạy `127.0.0.1`; thêm xác thực trước khi public |
| Khóa học, nhóm hứa "thu nhập thụ động" | Trung bình | Kỳ vọng thực tế: cần vài tháng để thấy kết quả ổn định |

---

## 15. Lộ trình đề xuất

**Giai đoạn 1: Chạy được với dữ liệu thật (1-2 tuần)**
- Đăng ký chương trình affiliate, lấy feed đầu tiên, chỉnh `FeedAdapter` theo đúng định dạng.
- Tạo bot Telegram, điền token và chat ID, chạy `bot.py` và `web.py`.
- Mở dashboard trên trình duyệt thật, sửa lỗi giao diện nếu có.

**Giai đoạn 2: Mở rộng nguồn dữ liệu (2-4 tuần)**
- Chọn 1-2 nhóm hàng (ví dụ đồ gia dụng, mẹ và bé).
- Viết `PlaywrightAdapter` với chế độ chờ giải captcha thủ công và lưu phiên.
- Thêm bảng `keywords`, quản lý từ khóa trên dashboard, lệnh `/tukhoa` trên bot, tìm sản phẩm theo từ khóa với giới hạn số lượng.

**Giai đoạn 3: Vận hành và tăng chất lượng (1-2 tháng)**
- Thêm đăng nhập cho dashboard; sao lưu SQLite.
- Mã giảm giá/voucher: theo dõi và gắn vào deal.
- Báo cáo hoa hồng, thống kê deal nào ra đơn.
- Đăng tự động lên kênh (Telegram channel, Zalo, fanpage) theo khung giờ sale (12h, 20h, ngày đôi 10.10, 11.11, 12.12).

**Giai đoạn 4: Nếu quy mô lớn**
- Chuyển SQLite sang PostgreSQL, thêm hàng đợi (Redis/Celery) hoặc Scrapy.

---

## 16. Các quyết định đã chốt chính thức (Qua quy trình Grill-with-docs 12/10/2026)

1. **Phạm vi & Đối tượng:** Công cụ cá nhân tự động hóa 100% làm MMO Affiliate Shopee. Cắt bỏ luồng đặt hàng hộ của khách vãng lai và quản lý đơn (`orders`) để tối giản hệ thống.
2. **Sàn & Nguồn dữ liệu:** Tập trung duy nhất vào Shopee với danh sách link sản phẩm chọn lọc (Curated URLs nạp qua Bot hoặc Dashboard).
3. **Engine trình duyệt & Captcha:** Playwright Persistent Context (`--headless=new`) nạp NopeCHA Extension (Free 100 lượt/ngày) để giải captcha tự động hoàn toàn không cần code xử lý ảnh/chuột.
4. **Giám sát hạn ngạch:** Kiểm tra định kỳ API NopeCHA, cảnh báo sớm (`credit ≤ 10`) và báo động khẩn cấp về Admin Telegram + Dashboard; kích hoạt Circuit Breaker tạm ngưng cào khi hết hạn ngạch để bảo vệ an toàn cho địa chỉ IP.
5. **Kênh xuất bản:** Bot tự động format bài đăng tiếp thị kèm link affiliate và bắn trực tiếp vào Telegram Broadcast Channel.
6. **Chiến lược Cold-start:** Giữ nguyên quy tắc tối thiểu 3 điểm lịch sử giá (4 lần quét độc lập) mới kết luận deal thật để bảo vệ uy tín kênh.
7. **Triển khai Docker:** Đóng gói Single-container qua `docker-compose.yml`, dùng base image `mcr.microsoft.com/playwright/python:v1.48.0-noble`, cấu hình `shm_size: 2gb` và mount volume bền vững ra host (`./data`, `./extensions`, `.env`).

---

## 17. Phụ lục: nhắc nhở thực hành cho người mới

- Chỉ dùng chương trình affiliate chính thống; tránh tool lách luật, spam mã hoặc tạo tài khoản ảo.
- Đừng cam kết quá mức với người mua ("chắc chắn rẻ nhất"), vì giá và mã đổi liên tục.
- Kiểm tra lại tồn kho và mã trước khi đăng deal.
- Cảnh giác khóa học đòi phí cao, hứa thu nhập chắc chắn.
- Bắt đầu nhỏ: một sàn, một ngách, vài trăm sản phẩm, rồi mới mở rộng.
