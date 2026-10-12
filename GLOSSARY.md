# Deal Hunter

Hệ thống theo dõi lịch sử giá và phát hiện deal giảm giá thật trên các sàn thương mại điện tử (Shopee, Lazada, TikTok Shop).

## Thuật ngữ cốt lõi

**Deal thật**:
Sản phẩm có giá bán hiện tại giảm sâu (mặc định ≥ 30%) so với giá trung vị 30 ngày trong lịch sử giá, còn hàng và shop có độ uy tín đạt chuẩn (rating ≥ 4.0).
_Avoid_: Giảm giá ảo, sale sốc, sale ảo

**Giá gốc ảo**:
Tình trạng người bán tự nâng giá niêm yết (list price) lên cao bất thường để hiển thị mức giảm giá sâu, nhưng thực chất giá bán không hề rẻ hơn so với lịch sử giá thực tế.
_Avoid_: Giá niêm yết, giá khuyến mãi, sale ảo

**Snapshot**:
Bản ghi dữ liệu tại một thời điểm quét nhất định của sản phẩm (bao gồm giá, giá gốc, tồn kho, rating, lượt bán).
_Avoid_: Crawl result, product state

**Lịch sử giá**:
Tập hợp các bản ghi giá theo thời gian của một sản phẩm, chỉ ghi thêm (append-only), không bao giờ bị ghi đè.
_Avoid_: Biến động giá, log giá

**Giá trung vị 30 ngày**:
Giá trị nằm ở giữa của tập hợp các mức giá ghi nhận trong 30 ngày gần nhất (không tính điểm quét hiện tại), dùng làm mốc so sánh chuẩn để chống nhiễu từ các đợt tăng/giảm giá đột biến.
_Avoid_: Giá trung bình, giá sàn

**Affiliate Link**:
Đường dẫn sản phẩm có gắn mã tiếp thị liên kết của người vận hành để nhận hoa hồng khi có phát sinh đơn hàng.
_Avoid_: Direct link, link mua hàng

**Phiên xác thực (Session State)**:
Bộ lưu trữ cookies, token và thông tin phiên trình duyệt sau khi giải captcha hoặc xác thực thành công, dùng để tái sử dụng cho các lần quét tiếp theo mà không kích hoạt lại captcha.
_Avoid_: Cookie dump, auth cache

**Trình duyệt có hồ sơ lưu trữ (Persistent Context)**:
Phiên làm việc của Playwright gắn liền với một thư mục dữ liệu người dùng (User Data Dir), cho phép nạp extension và giữ nguyên cookies, cache giữa các lần khởi động trình duyệt.
_Avoid_: Temporary browser, headless context

**Chặn Captcha (Captcha Intercept)**:
Tình huống sàn phát hiện bot và chặn hiển thị dữ liệu bằng câu đố xác thực (như kéo thanh trượt puzzle), kích hoạt hệ thống tự động giải mã hoặc xử lý ngoại lệ.
_Avoid_: Bot block, rate limit

**Extension giải Captcha (In-Browser Captcha Extension)**:
Tiện ích mở rộng chạy trực tiếp trong nhân trình duyệt Chromium, tự động phát hiện và hoàn thành thử thách xác thực (slider, puzzle, token) mà không cần mã nguồn crawler can thiệp vào DOM hay điều khiển chuột.
_Avoid_: Plugin bẻ khoá, hack extension

**Hạn ngạch giải mã (Solver Quota)**:
Số lượt giải captcha tối đa mà nhà cung cấp (NopeCHA) cấp phát miễn phí trong ngày (100 lượt) hoặc theo số dư gói trả phí.
_Avoid_: Số lần cào, giới hạn request

**Cảnh báo cạn hạn ngạch (Quota Exhaustion Alert)**:
Thông báo khẩn cấp gửi riêng cho người quản trị khi số lượt giải captcha còn dưới ngưỡng an toàn hoặc chạm mốc 0, nhắc nhở nạp thêm lượt hoặc nâng cấp gói.
_Avoid_: Lỗi captcha, out of money

**Trình duyệt ẩn danh chống nhận diện (Stealth Browser)**:
Cấu hình Playwright được ngụy trang các thuộc tính vân tay trình duyệt (fingerprint, navigator.webdriver, webgl, canvas) nhằm giảm thiểu tối đa việc sàn nhận diện là công cụ tự động.
_Avoid_: Headless browser thuần, bot cào

**Vùng nhớ chia sẻ trình duyệt (Shared Memory / shm_size)**:
Phân vùng bộ nhớ `/dev/shm` cấp phát cho container để nhân Chromium trong Docker render trang web nặng mà không bị sập vì tràn bộ nhớ.
_Avoid_: RAM container, bộ nhớ đệm

**Kênh phát sóng (Broadcast Channel)**:
Kênh hoặc nhóm Telegram nơi bot tự động xuất bản các bài đăng về deal thật kèm link affiliate để kéo người mua.
_Avoid_: Chat bot, kênh admin
