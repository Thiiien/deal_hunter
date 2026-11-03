# 17. Quản lý Phiên Đăng nhập Độc lập Từng Sàn & Chuẩn hóa Cảnh báo Telegram Lazada (Isolated Session Management & Platform-Badged Telegram Alerts)

Ngày: 2026-10-21

## Bối cảnh
Sau khi hệ thống hỗ trợ quét sản phẩm song song trên cả Shopee và Lazada, việc vận hành thực tế đối mặt với 2 vấn đề trọng yếu:
1. **Quản lý phiên đăng nhập và xử lý hết hạn cookie bị phụ thuộc đơn sàn:**
   - Ban đầu, hàm kiểm tra phiên trước khi quét (`ensure_authenticated()`) mặc định kiểm tra `data/cookies.json` của Shopee. Nếu Shopee hết hạn hoặc chưa có cookie, toàn bộ chu kỳ quét bị hủy bỏ ngay cả khi người dùng chỉ đang theo dõi sản phẩm Lazada hoặc cookie Lazada vẫn còn hiệu lực.
   - Khi Lazada gặp Captcha trượt (Slider Captcha) hoặc hết hạn cookie, thông báo gửi cho Admin báo nhầm sang file `data/cookies.json` của Shopee thay vì `data/cookies_lazada.json`.
2. **Cảnh báo Telegram thiếu nhận diện sàn và nút thao tác trực tiếp:**
   - Các cảnh báo "Deal Thật" và "Đạt Giá Mong Muốn" gửi qua Telegram chưa hiển thị rõ nhãn phân biệt sàn (`[LAZADA]` hay `[SHOPEE]`), khiến người xem khó nhận biết ngay nguồn deal.
   - Nút inline URL chỉ để nhãn chung chung hoặc tên chưa chuẩn hóa với từng sàn thương mại điện tử.

## Quyết định kiến trúc

1. **Kiểm tra phiên độc lập từng sàn (Isolated Per-Platform Session Verification):**
   - Nâng cấp `ensure_authenticated(self, platform: str = "all")` trong `BaseAdapter` và `PlaywrightAdapter`:
     - Khi `platform="all"`: Kiểm tra xem có ít nhất một trong hai sàn (Shopee hoặc Lazada) còn phiên hợp lệ hay không.
     - Khi `platform="lazada"`: Kiểm tra riêng `check_session_valid(data_dir, "lazada")` trên file `data/cookies_lazada.json` với các token xác thực đặc trưng (`lzd_sid`, `t`, `x5sec`, `user_credentials`, `cna`).
     - Khi `platform="shopee"`: Kiểm tra riêng `data/cookies.json` với token `SPC_EC` / `SPC_ST`.
   - Trong `Scanner._scan_platform(platform, products)`: Trước khi tiến hành quét nhóm sản phẩm của sàn nào, thực hiện tiền kiểm tra phiên của sàn đó (`ensure_authenticated(platform=platform)`). Nếu cookie sàn đó hết hạn:
     - Gửi cảnh báo Telegram riêng biệt đến Admin ghi rõ tên sàn và đường dẫn file cookie cần cấp lại (`data/cookies_lazada.json` hoặc `data/cookies.json`).
     - Đánh dấu thất bại cho các sản phẩm của sàn đó trong chu kỳ quét, **nhưng tuyệt đối không làm gián đoạn việc quét các sàn còn lại**.
   - Phân biệt rõ loại Captcha khi bị chặn: Lazada Slider Captcha vs Shopee Captcha trong thông báo gửi Admin.

2. **Chuẩn hóa thông báo Telegram có nhãn sàn và nút mua hàng theo sàn:**
   - Thêm huy hiệu nhận diện sàn vào tiêu đề cảnh báo: `🔵 [LAZADA]` cho Lazada và `🟠 [SHOPEE]` cho Shopee trong cả hai loại cảnh báo:
     - Thông báo Deal Thật (`_send_deal_alert`).
     - Thông báo Đạt Giá Mong Muốn (`_send_target_alert`).
     - Kết quả lệnh `/timkiem` trong Telegram Bot (`cmd_timkiem`).
   - Cập nhật nút Inline Keyboard điều hướng trực tiếp theo định dạng: `🛒 Xem deal Lazada ↗` / `🛒 Mua ngay trên Lazada ↗` hoặc Shopee tương ứng.
   - Tích hợp chuẩn hóa `AffiliateLinker` cho link Lazada (`aff_lazada`).

## Trạng thái
- Đã kiểm tra trực tiếp qua Telegram Bot API với tài khoản Admin (`7356350637`) và Kênh phát deal (`-5533273576`), tin nhắn đến thành công.
- 95/95 automated unit tests pass.
- Đã đồng bộ và vận hành trơn tru trong container Docker `deal_hunter-deal-hunter-1`.
