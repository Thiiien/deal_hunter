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

**Trạng thái deal (DealStatus)**:
Nhãn phân loại kết quả phân tích của một sản phẩm tại một thời điểm quét: `REAL_DEAL` (deal thật), `FAKE_LIST_PRICE` (giá gốc cao ảo), `INSUFFICIENT_HISTORY` (chưa đủ lịch sử), hoặc `NORMAL` (giá bình thường).
_Avoid_: Deal flag, deal type, kết quả phân tích

**Giai đoạn thu thập lịch sử (Cold-start period)**:
Khoảng thời gian ngay sau khi một sản phẩm được thêm vào danh sách theo dõi, trong đó hệ thống chưa đủ tối thiểu 3 điểm lịch sử giá (tức chưa có 4 lần quét độc lập) để kết luận deal thật hay không.
_Avoid_: Warm-up, learning period, thiếu dữ liệu

**Khám phá và Theo dõi (Discover & Track)**:
Cơ chế cho phép người dùng chỉ định từ khóa sản phẩm, hệ thống tự động tìm kiếm trên sàn, chọn lọc Top 5 sản phẩm bán chạy/uy tín nhất và nạp vào danh sách theo dõi lịch sử giá.
_Avoid_: Tìm kiếm deal, cào theo từ khóa, crawl search page

**Chiến dịch Sale (Sale Campaign)**:
Đợt khuyến mãi định kỳ hoặc đặc biệt của sàn thương mại điện tử (Mega Sale ngày đôi, Lương về Payday, hoặc Flash Sale khung giờ), được dùng để gắn nhãn thời điểm ghi nhận giá của sản phẩm nhằm phân tích deal thật theo đợt.
_Avoid_: Đợt giảm giá, sự kiện khuyến mãi, sale event

**Danh mục sản phẩm (Category)**:
Cấp phân loại ngành hàng của sản phẩm được tự động bóc tách từ thanh điều hướng (breadcrumb) của sàn (ví dụ: Thiết Bị Điện Tử > Chuột & Bàn Phím) để phân nhóm sản phẩm và lọc deal theo lĩnh vực.
_Avoid_: Thể loại, tag ngành hàng, product type

**Cookie đăng nhập lưu trữ (Saved Cookies)**:
Tập hợp cookies phiên làm việc đã xác thực của tài khoản sàn được xuất ra file JSON từ trình duyệt người dùng, cho phép Playwright trong Docker tự động nạp vào phiên quét để vượt qua tường chặn tài khoản khách (guest wall).
_Avoid_: Dump tài khoản, auth token, mật khẩu lưu trữ

**Kiểm tra phiên trước quét (Pre-flight Session Check)**:
Bước kiểm tra tự động trước mỗi chu kỳ quét để xác nhận session/cookies của sàn còn hiệu lực, nếu thiếu hoặc hết hạn thì tự động kích hoạt luồng đăng nhập trước khi tiến hành cào giá.
_Avoid_: Healthcheck sàn, auth test, ping session

**Tự động nhận diện đăng nhập (Auto-detect Login)**:
Cơ chế tự động phát hiện người dùng đã hoàn tất đăng nhập (thông qua cookie xác thực và chuyển hướng trang) để tự động xuất cookies và đóng cửa sổ trình duyệt mà không yêu cầu người dùng phải bấm phím xác nhận.
_Avoid_: Tự động đăng nhập, bypass login, auto-fill

**Giá mong muốn (Target Price)**:
Mức giá mục tiêu tối đa do người dùng thiết lập cho từng sản phẩm. Khi giá bán ghi nhận được nhỏ hơn hoặc bằng ngưỡng này, hệ thống sẽ gửi thông báo Telegram khẩn cấp ngay lập tức kể cả khi sản phẩm chưa đủ lịch sử giá 30 ngày.
_Avoid_: Giá kỳ vọng, giá chốt, ngưỡng cảnh báo

**Hủy theo dõi sản phẩm (Untrack / Delete Product)**:
Thao tác gỡ bỏ một sản phẩm khỏi danh sách theo dõi chủ động, đồng thời làm sạch toàn bộ lịch sử giá và nhật ký cảnh báo liên quan của sản phẩm đó trong cơ sở dữ liệu.
_Avoid_: Tạm dừng sản phẩm, ẩn sản phẩm

**Tần suất quét (Scan Frequency / Interval)**:
Khoảng thời gian nghỉ (tính bằng phút) giữa các chu kỳ quét giá tự động của hệ thống, có thể tùy chỉnh trực tiếp từ bảng điều khiển web hoặc lệnh Telegram và có hiệu lực ngay lập tức trong chu kỳ tiếp theo mà không cần khởi động lại tiến trình.
_Avoid_: Chu kỳ cào, nhịp tim quét, cron interval

**Tab Siêu Sale (Mega Sale Tab)**:
Tab chuyên biệt trên bảng điều khiển web tổng hợp các sản phẩm giảm giá sâu (đạt deal thật ≥ 20% so với giá trung vị 30 ngày hoặc giảm ≥ 30% so với giá niêm yết trong đợt sale), cho phép người mua lọc nhanh những món hời nhất.
_Avoid_: Tab khuyến mãi, tab giảm giá, tab flash sale

**Nhóm theo danh mục (Category Grouping)**:
Cơ chế tự động gom nhóm các sản phẩm giảm giá theo từng ngành hàng phân loại (như Máy Tính & Laptop, Thiết Bị Điện Tử, Đồ Gia Dụng...) và sắp xếp theo mức giảm giá giảm dần để người dùng dễ dàng so sánh và theo dõi.
_Avoid_: Tag filter, phân loại thủ công, list phẳng

**Khóa chống quét trùng (Scan Concurrency Lock)**:
Cơ chế khóa phi chặn (`_scan_lock`) trong `Scanner` nhằm ngăn các tiến trình quét đồng thời (từ scheduler và kích hoạt thủ công qua Web/Telegram) làm nghẽn tiến trình thực thi Playwright hoặc kích hoạt anti-bot của sàn.
_Avoid_: Mutex quét, sync thread, block crawl

**Giá khuyến mãi tối thiểu (Promotional Minimum Price)**:
Mức giá thấp nhất trên toàn bộ listing sản phẩm (trường `price_min` từ API sàn) sau khi đã tính các chương trình flash sale hoặc giảm giá toàn shop, được dùng để ràng buộc và xác định mức giá thực sự tốt nhất giữa các phân loại hàng.
_Avoid_: Giá sàn, giá min, giá quảng cáo

**Mã giảm giá khả dụng (Shop Voucher)**:
Mã khuyến mãi do shop hoặc sàn phát hành cho từng sản phẩm, bao gồm mã giảm theo phần trăm hoặc số tiền cố định đi kèm điều kiện đơn hàng tối thiểu (`min_spend`) và hạn mức trần (`discount_cap`).
_Avoid_: Coupon rác, mã thưởng, quà tặng

**Giá sau áp mã (Final Price After Voucher)**:
Mức giá cuối cùng người mua thực sự phải thanh toán sau khi đã trừ đi mức chiết khấu của voucher tối ưu nhất mà sản phẩm đủ điều kiện áp dụng. Mức giá này được dùng để đánh giá đạt giá mong muốn và hiển thị trực tiếp cho người mua.
_Avoid_: Giá trừ mã, giá sau sale, giá net

**Sản phẩm sẵn sàng mua (Ready-to-buy Product)**:
Listing sản phẩm có ít nhất một phân loại hàng còn tồn kho thực tế (`stock > 0`), trạng thái hoạt động bình thường (không bị xóa, khóa, tạm dừng), và có thể tiến hành đặt mua ngay.
_Avoid_: Sản phẩm tồn tại, link sống

**Tự động hủy theo dõi deal hết hàng (Auto-deactivate Sold-out Deals)**:
Cơ chế tự động chuyển trạng thái của các sản phẩm Flash Sale / Siêu Sale sang ngừng theo dõi (`active = 0`) ngay khi chu kỳ quét phát hiện sản phẩm đã hết hàng hoặc kết thúc đợt khuyến mãi, tránh làm rác bảng điều khiển.
_Avoid_: Xóa sản phẩm, hủy deal, ẩn deal

**Chặn cảnh báo khi hết hàng (Stock Alert Suppression)**:
Cơ chế ngăn chặn hoàn toàn việc gửi thông báo Telegram (cả Deal Thật và Giá Mong Muốn) khi sản phẩm đang ở trạng thái hết hàng (`stock == 0` hoặc không còn phân loại nào mua được).
_Avoid_: Tắt bot, ngắt alert, hoãn thông báo

**So sánh giá đa shop (Multi-Shop Cross Comparison)**:
Quy trình đối sánh tự động cùng một sản phẩm giữa Top 5 shop bán chạy nhất trên sàn, đánh giá giá sau voucher (`final_price`) của từng phân loại còn hàng để chọn ra shop có mức giá thực trả thấp nhất.
_Avoid_: So sánh link, dò giá chéo, crawl đa shop

**Bộ lọc chống phụ kiện (Anti-Accessory Filter)**:
Quy tắc sàng lọc tự động dựa trên độ tương đồng từ khóa và ngưỡng giá nhằm loại bỏ các sản phẩm phụ kiện rẻ tiền (như ốp lưng, feet chuột, dây thay thế) bị sàn trả về trong kết quả tìm kiếm của sản phẩm chính.
_Avoid_: Lọc rác, bỏ link phụ, blacklist từ khóa

**Xác thực phiên đa sàn (Multi-Platform Session Authentication)**:
Cơ chế lưu trữ và nạp độc lập cookies/token phiên làm việc của từng sàn thương mại điện tử (`data/cookies.json` cho Shopee và `data/cookies_lazada.json` cho Lazada), ngăn chặn việc lỗi phiên của một sàn làm gián đoạn việc quét các sàn còn lại.
_Avoid_: Multi-cookie, gộp tài khoản

**So sánh giá liên sàn (Cross-Platform Price Comparison)**:
Quy trình tự động tìm kiếm và đối chiếu mức giá thực tế (sau voucher) của cùng một món hàng trên nhiều sàn thương mại điện tử khác nhau (Shopee, Lazada) để chỉ ra sàn nào đang bán món hàng đó với giá rẻ nhất.
_Avoid_: So sánh 2 web, check giá chéo, crawl đa sàn

**Cào deal Flash Sale Lazada (Lazada Flash Sale Crawler)**:
Cơ chế tự động truy cập trang Flash Sale của Lazada, bóc tách tên sản phẩm, mức giá khuyến mãi, giá gốc và thanh tiến độ bán hàng thông qua API gateway hoặc cấu trúc DOM, tự động loại bỏ các deal đã bán 100% (hết hàng).
_Avoid_: Crawl sale lazada, bóc deal lazada

**Cào Siêu Sale đa sàn (Multi-Platform Mega Sale Crawl)**:
Tính năng kích hoạt thu thập đồng thời hoặc riêng rẽ các deal Flash Sale / Siêu Sale từ cả Shopee và Lazada vào hệ thống, tự động phân loại theo nhãn sàn, lưu trữ lịch sử giá và gắn kèm chiến dịch khuyến mãi đang diễn ra.
_Avoid_: Quét sale tổng hợp, cào deal 2 sàn

**Chặn tài nguyên thứ cấp (Secondary Resource Blocking)**:
Kỹ thuật lọc và hủy bỏ (route abort) có chọn lọc các request tải hình ảnh, video media, font chữ và các script tracking phân tích nặng khi cào trang sản phẩm, giúp đẩy nhanh tốc độ bóc tách dữ liệu từ 3-5 lần và giảm thiểu tiêu thụ bộ nhớ RAM.
_Avoid_: Chặn web, tắt mạng, skip script

**Cào mở rộng danh mục Sale (Expanded Sale Crawling)**:
Chiến lược kết hợp song song nhiều nguồn trang khuyến mãi (widget Flash Sale trang chủ và trang danh mục chuyên đề `/tag/flash-sale/`), tự động cuộn trang để mở rộng độ phủ và số lượng deal giảm sâu giữa nhiều ngành hàng.
_Avoid_: Cào tràn lan, deep crawl rác

**Tìm kiếm từ khóa liên sàn (Cross-Platform Keyword Search)**:
Cơ chế tự động định tuyến truy vấn từ khóa sản phẩm tới catalog/API của từng sàn (Shopee `api/v4/search` hoặc Lazada `/catalog/?q=...`) dựa theo bộ lọc sàn đang chọn trên Dashboard hoặc quét đồng thời cả Shopee & Lazada, bóc tách giá sau voucher và chọn lọc deal rẻ nhất liên sàn đưa vào theo dõi.
_Avoid_: Tìm kiếm từ khóa Lazada, search bot, cào keyword đa sàn

**Chặn tài nguyên nặng toàn diện (Comprehensive Resource Blocking)**:
Phương thức chặn tải mạng dùng chung (`_enable_resource_blocking`) áp dụng cho toàn bộ các luồng cào Lazada (PDP, Catalog Search, Flash Sale), hủy bỏ triệt để ảnh, media, font và script analytics/telemetry giúp giảm thời gian tải trang từ ~10s xuống còn ~1.5 - 2s.
_Avoid_: Chặn mạng thủ công, skip asset riêng lẻ

**Bóc tách giá thẻ chống va chạm tiêu đề (Anti-Title Price Collision Parsing)**:
Kỹ thuật loại bỏ tiêu đề sản phẩm khỏi nội dung thẻ trước khi bóc tách giá (`non_title_text = text.replace(title, "")`) kết hợp với việc bắt buộc có ký hiệu tiền tệ chuẩn `₫` / `đ`, ngăn chặn hoàn toàn lỗi nhầm các con số chỉ quy cách/trọng lượng (ví dụ `1400g`, `48 hộp`) thành giá bán sản phẩm.
_Avoid_: Regex giá lỏng lẻo, bóc text toàn thẻ

**Tái tạo giá niêm yết từ % giảm (List Price Reconstruction)**:
Quy trình tự động suy ngược và tính toán giá niêm yết gốc (`list_price = price / (1 - discount%)`) từ nhãn phần trăm giảm giá trên thẻ Flash Sale khi sàn thương mại điện tử ẩn giá gốc, đảm bảo tính nhất quán của bộ lọc deal sâu.
_Avoid_: Bỏ trống giá gốc, đoán giá ngẫu nhiên

**Xác thực phiên độc lập từng sàn (Isolated Per-Platform Session Verification)**:
Quy trình tiền kiểm tra và cảnh báo trạng thái hiệu lực cookies/token của riêng từng sàn (Shopee `cookies.json`, Lazada `cookies_lazada.json`) trước khi quét nhóm sản phẩm thuộc sàn đó, cho phép sàn còn hiệu lực tiếp tục quét bình thường và gửi thông báo lỗi đúng tên file cookie khi có một sàn bị hết hạn hoặc gặp Captcha.
_Avoid_: Check cookie gộp, ngắt toàn bộ scanner, cảnh báo chung chung

**Cảnh báo Telegram gắn nhãn sàn (Platform-Badged Telegram Deal Alerts)**:
Định dạng thông báo Telegram tự động gắn kèm huy hiệu nhận diện sàn (`🔵 [LAZADA]` hoặc `🟠 [SHOPEE]`) trên tiêu đề và nút thao tác trực tiếp (`🛒 Xem deal Lazada ↗` / `🛒 Mua ngay trên Lazada ↗`), giúp người nhận dễ dàng phân biệt nguồn deal và truy cập đúng trang mua hàng.
_Avoid_: Alert không nhãn sàn, nút link mặc định

**Module giá thế hệ mới Lazada (Lazada V2 Price Module Parsing)**:
Cơ chế bóc tách giá thích ứng với kiến trúc DOM `#module_product_price_v2` của Lazada, tập trung vào các selector lớp chuyên dụng (`.pdp-v2-product-price-content-salePrice`, `[class*='salePrice']`, `[class*='originalPrice']`) thay cho các selector cũ và cấu trúc ld+json không chứa giá.
_Avoid_: Selector cũ, parse ld+json rỗng

**Bộ chặn ghi nhận giá rỗng (Zero-Price Rejection Guard)**:
Quy tắc kiểm soát chặt chẽ ngăn chặn hoàn toàn việc trả về hoặc lưu trữ giá trị `price = 0.0` vào cơ sở dữ liệu khi sản phẩm còn hàng (`stock is not False`), tự động kích hoạt lỗi ngoại lệ `FetchError` để bảo toàn tính toàn vẹn của lịch sử giá.
_Avoid_: Gán mặc định 0.0, nuốt lỗi giá rỗng

**Bắt bẫy điều hướng phiên hết hạn (Redirected Session Expiration Trap)**:
Kỹ thuật phát hiện sớm sự chuyển hướng URL sang các cổng đăng nhập (`member.lazada.vn/user/login`) hoặc trang kích hoạt Slider Captcha (`/punish`, `verify/slider`, `acs.lazada.vn`) trong quá trình cào trang chi tiết, lập tức ném ngoại lệ `Blocked` để kích hoạt thông báo Telegram nạp lại cookie.
_Avoid_: Bỏ sót redirect đăng nhập, báo nhầm lỗi mạng

**Bóc tách ưu đãi và mã giảm giá Lazada (Lazada Voucher & Promotion Tag Extraction)**:
Cơ chế bóc tách đa nguồn các chương trình khuyến mãi của shop/sàn Lazada từ cụm Promotion Tags DOM (`#module_promotion_tags`, `.promotion-tag-item-v2`, `.tag-name`), các thẻ voucher/coupon và nhãn ưu đãi trong tiêu đề sản phẩm, tự động trích xuất % giảm, số tiền giảm, điều kiện đơn tối thiểu (`min_spend`) và hạn mức trần (`discount_cap`).
_Avoid_: Bỏ sót thẻ ưu đãi, parse thiếu min_spend

**Quét tức thì theo liên kết (Instant Link Scan)**:
Cơ chế kích hoạt cào dữ liệu ngay lập tức trong luồng chạy ngầm khi người dùng dán liên kết sản phẩm (qua Web Dashboard hoặc Telegram Bot `/theodoi`), giúp cập nhật tức thời tên sản phẩm, giá sàn, mã giảm giá và tình trạng tồn kho thay vì phải chờ đến chu kỳ quét định kỳ kế tiếp.
_Avoid_: Chờ quét hàng loạt, lưu URL thụ động

**Chuẩn hóa liên kết và hợp nhất bản ghi (Canonical Link Normalization & Deduplication Merge)**:
Quy trình tự động theo dõi chuyển hướng trình duyệt từ các đường dẫn chia sẻ rút gọn (như `s.lazada.vn/...`) hoặc URL chứa tham số tracking rác (`?spm=...`), bóc tách định dạng URL chuẩn (`canonical_url`) và mã định danh duy nhất (`item_key`), đồng thời tự động hợp nhất lịch sử giá và dọn dẹp bản ghi tạm thời nếu sản phẩm đã từng tồn tại trong hệ thống.
_Avoid_: Lưu link rút gọn vĩnh viễn, nhân đôi sản phẩm (duplicate product)

**Ưu tiên quét sản phẩm người dùng (User-Tracked Scan Prioritization)**:
Quy tắc phân loại và xếp thứ tự quét định kỳ đặt các sản phẩm do người dùng chủ động theo dõi (`source='user'`) lên trước các sản phẩm tự động thu thập từ flash sale (`source='flash_sale'`), đảm bảo dữ liệu quan trọng nhất luôn được cập nhật sớm nhất trong mỗi chu kỳ quét 60 phút.
**Phát hiện sản phẩm ngừng bán/xóa sớm (Fast Delisted & 404 Detection)**:
Kỹ thuật phát hiện ngay lập tức trong vòng 1 giây khi trang sản phẩm trả về mã 404, thông báo "Sản phẩm không tồn tại / đã bị xóa / ngừng bán", hoặc bị chuyển hướng về trang chủ sàn, giúp lập tức ngắt quá trình tải trang thay vì phải chờ hết thời gian timeout 30 giây, đồng thời tự động tắt theo dõi (`active=0`) và cảnh báo cho người dùng.
_Avoid_: Chờ hết timeout 30s, cào lặp lại link chết

**Cảnh báo giảm giá cho sản phẩm theo dõi (Tracked Product Price-Drop Alert)**:
Cơ chế thông báo trực tiếp tới quản trị viên Telegram khi một sản phẩm do người dùng chủ động theo dõi (`source='user'`) có giá thực trả giảm (do giảm giá trực tiếp hoặc do xuất hiện voucher mới) so với lần quét gần nhất, ngay cả khi sản phẩm chưa tích lũy đủ 30 ngày lịch sử giá.
_Avoid_: Bỏ sót thông báo giảm giá khi thiếu lịch sử, spam kênh deal chung

**Bóc tách ưu đãi đa nguồn mở rộng (Multi-Source Deep Voucher Extraction)**:
Cơ chế khai thác song song cả dữ liệu cấu trúc nội bộ (`window.__moduleData__` trên Lazada, `pdp/get_pc` trên Shopee) kết hợp với các thẻ ưu đãi DOM (`.voucher-ticket`, `[class*="voucher"]`, nhãn Xu / Coins, Hoàn tiền MAX), giúp trích xuất toàn diện mọi tầng giảm giá áp dụng được cho sản phẩm.
_Avoid_: Chỉ phụ thuộc vào 1 API duy nhất, bỏ sót voucher hiển thị trên giao diện

**Cộng dồn voucher đa tầng (Voucher Stacking)**:
Cơ chế gom và áp dụng đồng thời các tầng ưu đãi không xung đột gồm Voucher Shop, Voucher Sàn (hoặc Voucher Tích Lũy) và Ưu đãi Xu/Hoàn tiền (Shopee/Lazada Coins) cho một sản phẩm để tính toán mức giá thực trả tối ưu nhất (`final_price`).
_Avoid_: Chỉ chọn 1 voucher đơn lẻ, bỏ sót mã sàn khi đã có mã shop

**Cảnh báo Flash Deal tức thời (Instant Flash Deal Alert)**:
Cơ chế tự động phát sóng thông báo lên kênh Telegram cho các sản phẩm Flash Sale / Siêu Sale mới phát hiện có mức giảm giá sâu (≥ 30% so với giá niêm yết) kèm nhiều tầng voucher và shop uy tín, giúp người mua săn deal ngay trong đợt khuyến mãi mà không phải chờ tích lũy đủ 30 ngày lịch sử giá.
_Avoid_: Bỏ qua deal mới vì thiếu lịch sử (cold start), hoãn cảnh báo sale gấp

**Kênh TMALL Trợ Giá & Choice (TMALL Subsidy & Choice Channel)**:
Chuyên trang khuyến mãi trợ giá sâu của Lazada dành cho các thương hiệu chính hãng (LazMall/Tmall) và mặt hàng Choice với mức trợ giá ngân sách lớn lên tới 70% - 95%, đi kèm huy hiệu nhận diện màu đỏ `TMALL TRỢ GIÁ` hoặc `MOMCLUB`.
_Avoid_: Flash sale thường, tag quảng cáo

**Bóc tách giá phân loại tối ưu (Lowest In-Stock SKU Price Parsing)**:
Cơ chế duyệt qua toàn bộ danh sách các biến thể/phân loại hàng (`skuInfos` trên Lazada, `models` trên Shopee) của một listing sản phẩm, bóc tách giá sau khuyến mãi/trợ giá của từng phân loại còn tồn kho thực tế (`stock > 0`) để chọn ra mức giá thấp nhất tuyệt đối (theo ADR 0053), đồng thời tự động gắn hậu tố tên phân loại vào tên sản phẩm.
_Avoid_: Lấy SKU đầu tiên, khóa cứng SKU theo URL, break sớm vòng lặp SKU

**Cảnh báo Deal Siêu Trợ Giá (Super Subsidy Deal Alert)**:
Định dạng thông báo đặc biệt khẩn cấp gắn biểu tượng `🚨 DEAL SIÊU TRỢ GIÁ!` dành riêng cho các sản phẩm có mức giảm giá thực tế `≥ 70%` hoặc gắn nhãn `[TMALL TRỢ GIÁ]`, thông báo ngay số tiền tiết kiệm và giá thực trả sau trợ giá lên kênh Telegram.
_Avoid_: Thông báo deal thường, bỏ lỡ trợ giá khủng

**Bóc tách dữ liệu gốc cổng MTOP (Lazada MTOP Gateway Interception)**:
Cơ chế lắng nghe trực tiếp phản hồi mạng từ cổng API nội bộ của Alibaba/Lazada (`mtop.lazada.item.detail.getdetail`, `mtop.lazada.promotion`, `tradeInfo`) trong quá trình tải trang bằng Playwright, cho phép bóc tách cấu trúc giá SKU và danh mục voucher khuyến mãi từ dữ liệu JSON gốc có độ tin cậy tuyệt đối, không bị phụ thuộc vào việc xáo trộn DOM.
_Avoid_: Chỉ dựa vào DOM, cào tĩnh HTML

**Chuẩn hóa giá phân loại đa định dạng (Robust SKU Price Normalization)**:
Thuật toán làm sạch và nhận diện giá số (`_clean_price_val`) có khả năng xử lý linh hoạt mọi định dạng dữ liệu trả về từ Lazada (đối tượng dict `{value, text}`, chuỗi chứa ký hiệu tiền tệ `₫`/`đ`, dấu chấm/phẩy phân cách hàng nghìn, hoặc số nguyên), giải quyết triệt để lỗi chuyển đổi `float()` làm rớt giá khuyến mãi của các biến thể hàng.
_Avoid_: Ép kiểu float trực tiếp, nuốt lỗi ngoại lệ để lộ giá gốc

**Voucher Trợ giá Độc quyền Hội viên (Exclusive Member Subsidy Voucher - MOMCLUB / TMALL)**:
Các gói trợ giá tài trợ trực tiếp từ nền tảng Lazada dành cho nhóm khách hàng thành viên đặc quyền (`MOMCLUB`, `TMALL TRỢ GIÁ`, `SIÊU TRỢ GIÁ`), với giá trị trợ giá trừ tiền mặt lên tới hàng triệu đồng hoặc mức giảm % từ 70% đến 96.5%, được hệ thống phân loại vào tầng trợ giá nền tảng (`platform`) để cộng dồn song song cùng Voucher Shop và Ưu đãi Xu.
_Avoid_: Gộp chung vào voucher shop thường, không cho cộng dồn

**Nâng trần giảm giá siêu trợ giá (Super Subsidy Percentage Threshold - 99%)**:
Quy tắc mở rộng ngưỡng chiết khấu % hợp lệ trong parser voucher từ `90%` lên `99%`, cho phép ghi nhận chuẩn xác các deal xả kho và siêu trợ giá cực hạn (giảm 95% - 96.5%) mà không bị bộ lọc an toàn loại bỏ nhầm thành lỗi nhập liệu.
_Avoid_: Giới hạn cứng 90%, từ chối deal giảm trên 90%

**Lọc bỏ sản phẩm rác giá trị thấp (Low-Value Junk Product Filter)**:
Cơ chế tự động loại bỏ các sản phẩm giá rẻ, linh tinh hoặc phụ kiện (như ốp lưng 10k, kẹp tóc 15k, tất chân 20k) ra khỏi luồng thu thập Flash Sale tự động và các kênh thông báo deal thật, đảm bảo hệ thống chỉ tập trung theo dõi và săn lùng các sản phẩm có giá trị sử dụng thực sự cao.
_Avoid_: Thu thập ồ ạt mọi mặt hàng, spam deal phụ kiện giá rẻ

**Ngưỡng giá trị thật tối thiểu (Minimum Pre-Discount Baseline Threshold)**:
Mức giá sàn trước khi giảm giá (mặc định `500.000₫`, cấu hình qua biến `DEAL_MIN_ORIGINAL_PRICE` và Web Dashboard) mà một sản phẩm bắt buộc phải đạt tới để được xem xét gửi thông báo Deal Thật hoặc Flash Deal Hot. Giá trị trước giảm được đo bằng giá trung vị 30 ngày (`median_30d`) đối với sản phẩm đã có lịch sử hoặc giá niêm yết ban đầu (`list_price`) đối với sản phẩm mới.
_Avoid_: Giá sau giảm, ngưỡng cứng không cho cấu hình

**Dọn dẹp rác Flash Sale (Purge Junk Flash Sale)**:
Hành động xóa vĩnh viễn khỏi cơ sở dữ liệu các bản ghi sản phẩm Flash Sale thu thập tự động (kèm toàn bộ lịch sử giá và cảnh báo liên quan) có giá gốc và giá bán nhỏ hơn ngưỡng giá tối thiểu cài đặt (`deal_min_original_price`), giúp giải phóng dung lượng DB và bảo toàn tuyệt đối 100% các sản phẩm do người dùng tự thêm để theo dõi (`source = 'user'`).
_Avoid_: Xóa nhầm link người dùng tự thêm, chỉ xóa lịch sử mà để lại sản phẩm mồ côi

**Lọc sạch tab Siêu Sale (MegaSale View Strict Threshold Filter)**:
Quy tắc hiển thị nghiêm ngặt trên giao diện tab Siêu Sale & Giảm sâu: chỉ hiển thị các sản phẩm có giá gốc hoặc giá niêm yết lớn hơn hoặc bằng ngưỡng cài đặt, ngăn chặn hoàn toàn các phụ kiện, ốp lưng, móc khóa hoặc đồ rác giá rẻ xuất hiện trong bảng tổng hợp deal.
_Avoid_: Hiển thị đồ 10k-50k trong tab siêu sale, gộp chung rác vào bảng deal

**Sản phẩm lỗi giá (Price Error Product)**:
Sản phẩm mà người bán tự đặt nhầm giá (thiếu số 0, nhầm đơn vị, nhập nhầm giá phụ kiện/biến thể rẻ cho listing chính) khiến giá giảm cực sâu bất thường (từ 65% đến 95%) so với giá trị thực hoặc giá trung vị lịch sử.
_Avoid_: Deal giảm giá thông thường, voucher chồng chéo gian lận

**Bất thường về giá (Price Anomaly)**:
Bản ghi dữ liệu đánh dấu sự xuất hiện của một điểm giá giảm đột biến vượt ngưỡng 65% - 85%, được đưa vào quy trình thẩm định đa tầng (lọc phụ kiện, quét xác nhận lại 2 phút) trước khi cho phép quản trị viên phê duyệt.
_Avoid_: Cảnh báo lỗi giá chưa qua kiểm chứng, spam deal ảo

**Xác minh lỗi giá bằng quét lại (Price Error Re-scan Confirmation)**:
Cơ chế tự động lên lịch quét lại sản phẩm sau 2 phút (120 giây) kể từ thời điểm phát hiện bất thường, nhằm kiểm tra giá có thực sự ổn định hay shop đã sửa lại giá/hết hàng trước khi chốt trạng thái `confirmed`.
_Avoid_: Chờ chu kỳ quét hàng giờ, chỉ tin tưởng 1 lần đọc duy nhất

**Duyệt đăng kênh quản trị (Admin Telegram Approval)**:
Luồng tương tác đặc quyền cho phép Admin xem xét deal nghi lỗi giá qua tin nhắn Telegram riêng có gắn inline keyboard (`[🛒 Mua ngay]`, `[📢 Đăng lên Kênh]`, `[❌ Bỏ qua]`), ngăn chặn rủi ro làm mất uy tín hoặc bùng nổ đơn bị hủy trên kênh cộng đồng.
_Avoid_: Tự động đăng lỗi giá lên kênh công khai, không cho admin duyệt

**Bẫy biến thể phụ kiện (Variant Trap / Accessory SKU)**:
Chiêu trò của người bán khi thêm các phân loại phụ kiện giá rẻ (như ốp lưng 20k, cáp sạc 10k, switch lẻ) vào trong một listing sản phẩm có giá trị cao nhằm hiển thị giá rẻ bất thường. Với các kênh cào khám phá tự động, hệ thống có bộ lọc loại trừ; riêng đối với sản phẩm do người dùng theo dõi (ADR 0053), hệ thống tôn trọng tuyệt đối giá thấp nhất còn hàng của listing và bổ sung tên biến thể vào tiêu đề.
_Avoid_: Bỏ lỡ option thấp nhất khi người dùng chủ động săn phân loại rẻ

**Cộng dồn voucher đa tầng (Multi-tier Voucher Stacking)**:
Khả năng kết hợp tối đa 1 mã giảm giá trên từng cấp độ ưu đãi hợp lệ (Voucher Shop + Voucher Sàn / Trợ giá nền tảng + Ưu đãi Xu / Hoàn tiền) để tính toán chính xác mức giá thanh toán cuối cùng của đơn hàng theo đúng chính sách của các sàn TMĐT.
_Avoid_: Chỉ lấy 1 voucher duy nhất, cộng dồn không kiểm soát

**Chống chiết khấu kép (Double Discount Prevention)**:
Quy tắc bảo đảm một khoản trợ giá hoặc ưu đãi chỉ được trừ một lần duy nhất vào giá thanh toán. Nếu giá bán của SKU đã được niêm yết theo mức giá trợ giá (`subsidyPrice`), hệ thống sẽ không trừ thêm lần thứ hai từ huy hiệu trợ giá đó như một voucher riêng biệt.
_Avoid_: Trừ lặp lại, giá ảo hai tầng

**Theo dõi theo từ khóa (Keyword-based Tracking)**:
Cơ chế tự động định kỳ tìm kiếm sản phẩm theo từ khóa chỉ định của người dùng trên các sàn TMĐT, áp dụng bộ lọc tiêu chuẩn (xuất xứ, nơi gửi, dịch vụ) và tự động ghi nhận các sản phẩm thỏa mãn vào danh sách theo dõi lịch sử giá.
_Avoid_: Tìm kiếm thủ công, cào từ khóa ồ ạt

**Bộ lọc nguồn gốc & vận chuyển (Origin & Shipping Filter)**:
Tập hợp các tiêu chí ràng buộc về địa lý bao gồm Xuất xứ hàng hóa (Việt Nam / Nước ngoài), Nơi gửi hàng (Việt Nam / Bất kỳ), và Loại shop (Mọi shop / Chỉ shop nước ngoài) nhằm đảm bảo hệ thống chỉ săn tìm các sản phẩm theo đúng nhu cầu kho bãi và tốc độ giao nhận của người mua.
_Avoid_: Lọc thô, chỉ lọc theo tên

**Bộ lọc Dịch vụ & Khuyến mãi Lazada (Lazada Service & Promotion Filter)**:
Danh sách 14 tiêu chí dịch vụ và khuyến mãi đặc thù của sàn Lazada (`lazmall`, `tmall`, `lazflash`, `fbl`, `hoa_toc`, `freeship`, `voucher_max`, v.v.) được nhận diện qua huy hiệu và metadata để phân loại chính xác các ưu đãi đặc quyền đi kèm sản phẩm.
_Avoid_: Tag chung chung, bộ lọc chung mọi sàn

**Bộ nhớ đệm loại trừ sản phẩm (Rejection Cache / `rejected_items`)**:
Bảng lưu trữ tạm thời các sản phẩm đã bị đánh giá không đạt bộ lọc của từ khóa kèm lý do từ chối, giúp hệ thống không phải tải lại các trang chi tiết không phù hợp trong vòng 7 ngày, tối ưu hóa băng thông và giảm thiểu nguy cơ bị sàn chặn.
_Avoid_: Cào lặp lại, blacklist vĩnh viễn

**Bảng liên kết từ khóa - sản phẩm (`keyword_products`)**:
Cấu trúc quan hệ N-N giữa danh sách từ khóa theo dõi và bảng sản phẩm, cho phép một sản phẩm có thể cùng lúc thỏa mãn nhiều từ khóa khác nhau mà không làm xung đột hay ghi đè dữ liệu nguồn gốc (`source`) của sản phẩm.
_Avoid_: 1 cột keyword_id duy nhất, ghi đè từ khóa

**Sản phẩm theo dõi (User-Tracked Product)**:
Sản phẩm được người dùng chủ động chỉ định theo dõi biến động giá (thông qua dán link trực tiếp, lệnh Telegram `/theodoi`, hoặc bấm nút *"➕ Theo dõi"*), có `source='user'`. Tab này được cô lập nghiêm ngặt, tuyệt đối không bị tự động chèn các sản phẩm tìm thấy từ luồng cào từ khóa, siêu sale hoặc săn lỗi giá.
_Avoid_: Sản phẩm quét ngầm, kết quả tìm kiếm tự thêm

**Nguồn sản phẩm (Product Source / `products.source`)**:
Định danh phân loại nguồn gốc sản phẩm trong hệ thống (`user`: người dùng tự thêm theo dõi, `keyword`: quét theo từ khóa, `flash_sale`: cào siêu sale, `price_error`: săn lỗi giá), giúp hệ thống tách bạch hiển thị và áp dụng chu kỳ quét phù hợp.
_Avoid_: Gán mặc định 'user' cho mọi sản phẩm cào được

**Tần suất quét theo phân hệ (Subsystem Scan Interval)**:
Cấu hình tần suất chạy ngầm độc lập cho từng tab chức năng (Sản phẩm theo dõi, Theo từ khóa, Siêu Sale, Săn lỗi giá), cho phép người dùng tùy biến chu kỳ quét nhanh/chậm riêng biệt cho từng phân hệ mà không làm quá tải hệ thống hay dồn chung vào một chu kỳ quét duy nhất.
_Avoid_: 1 tần suất quét chung cho mọi chức năng

**Đếm lỗi quét liên tiếp (Consecutive Fail Count / `fail_count`)**:
Số lần quét thất bại liên tiếp do lỗi cào dữ liệu (`FetchError`, mạng ngắt quãng, trang lỗi) của một sản phẩm. Khi sản phẩm quét thành công, chỉ số này được tự động đặt lại về 0.
_Avoid_: Tổng số lần lỗi tích lũy, cờ báo lỗi vĩnh viễn

**Tự động ngưng theo dõi khi lỗi kéo dài (Consecutive Failure Auto-Deactivation)**:
Cơ chế tự động chuyển trạng thái sản phẩm sang ngưng kích hoạt (`active=0`) khi ghi nhận 5 lần quét thất bại liên tiếp, đồng thời gửi cảnh báo đến quản trị viên qua Telegram để tránh lãng phí hạn ngạch và tài nguyên trình duyệt.
_Avoid_: Quét sản phẩm chết vô tận, xóa sản phẩm khỏi cơ sở dữ liệu

**Khóa quét chia sẻ đơn luồng (Shared Browser Scan Lock)**:
Cơ chế đồng bộ hóa luồng quét (`_scan_lock`) dùng chung cho toàn bộ các phân hệ nhằm ngăn chặn việc gửi yêu cầu đồng thời đến phiên trình duyệt Playwright đơn luồng, giảm tải tài nguyên CPU/RAM và tránh xung đột bối cảnh trình duyệt.
_Avoid_: Chạy song song nhiều crawler trên 1 browser context

**Lệnh xem danh sách theo dõi (`/listtracked`)**:
Lệnh bot Telegram dành riêng cho việc tra cứu toàn bộ danh sách sản phẩm người dùng đang chủ động theo dõi (`source='user'`, `active=1`), phân đoạn 5 sản phẩm/tin nhắn, hiển thị chi tiết tên, giá hiện tại, voucher, giá mong muốn, tình trạng kho và liên kết trực tiếp tới sản phẩm.
_Avoid_: Lệnh xem chung toàn bộ cơ sở dữ liệu, in tràn tin nhắn

**Bóc tách voucher có điều kiện (Guarded Voucher Extraction)**:
Quy tắc bóc tách mã giảm giá trên sàn thương mại điện tử, bắt buộc chuỗi văn bản phải chứa từ khóa khuyến mãi rõ ràng (`giảm`, `voucher`, `mã giảm`, `coupon`, `hoàn`, `trợ giá`) đi liền với số `%` hoặc số tiền, đồng thời chỉ trích xuất từ dữ liệu khuyến mãi có cấu trúc (`payload`, `ticket`, `badge`) hoặc thẻ khuyến mãi ngoặc vuông rõ ràng trong tiêu đề; tuyệt đối không bắt nhầm các thông số kỹ thuật sản phẩm (như *"Layout 75%"*, *"Cotton 100%"*) thành voucher giảm giá.
_Avoid_: Bóc tách số % tùy tiện từ tên sản phẩm, voucher ảo

**Ưu tiên tình trạng kho từ DOM (DOM Stock Priority)**:
Cơ chế kiểm tra tình trạng còn hàng/hết hàng đa tầng, trong đó trạng thái nút thao tác và thông báo thực tế hiển thị trên giao diện trình duyệt (nút Mua Ngay bị vô hiệu hóa `disabled`, `aria-disabled="true"`, `.btn--disabled`, `.next-btn-disabled` hoặc banner *"Hết hàng"*, *"Sản phẩm tạm thời hết hàng"*) luôn có quyền ưu tiên cao hơn và ghi đè lên dữ liệu cấu trúc tĩnh JSON-LD, ngăn ngừa việc sàn báo `InStock` ảo khi sản phẩm hoặc toàn bộ phân loại SKU thực tế đã hết hàng.
_Avoid_: Tin tưởng hoàn toàn JSON-LD InStock, bỏ qua trạng thái nút mua

**Khử trùng lặp mã giảm giá (Voucher De-duplication)**:
Cơ chế chuẩn hóa và loại bỏ các mã giảm giá tương đồng trước khi áp dụng logic cộng dồn đa tầng (`allow_stacking`), ngăn chặn tình trạng cùng một ưu đãi bị trích xuất lặp lại ở nhiều tầng khác nhau dẫn đến chuỗi voucher dị thường như `LAZADA_75PCT + LAZADA_75PCT` và chiết khấu vượt quá 100% giá trị sản phẩm.
_Avoid_: Cộng dồn nhiều mã giống hệt nhau, giảm giá vượt quá giá bán

**Kiểm tra tồn kho theo phân loại (Multi-variation SKU Stock Priority)**:
Quy tắc xác định tình trạng còn hàng cho các sản phẩm có nhiều phân loại (màu sắc, kích cỡ, phân loại hàng...). Sản phẩm được tính là Còn hàng (`stock = True`) nếu có ít nhất một phân loại không bị vô hiệu hóa. Chỉ khi toàn bộ các phân loại đều hết hàng/vô hiệu hóa thì sản phẩm mới bị coi là Hết hàng (`stock = False`). Trạng thái vô hiệu hóa mặc định của nút Mua hàng ban đầu khi chưa chọn phân loại không được dùng để kết luận sản phẩm hết hàng.
_Avoid_: Báo hết hàng vì nút Mua ban đầu bị disabled, kiểm tra stock cấp link bỏ qua phân loại

**Dự phòng giá theo dõi sản phẩm (Tracking Price Fallback)**:
Cơ chế trích xuất giá dự phòng từ trường dữ liệu theo dõi hoặc phân tích của sàn (như `fields.tracking.pdt_price` trên Lazada) khi các trường dữ liệu tĩnh (JSON-LD) hoặc phân loại riêng lẻ không chứa giá trực tiếp, ngăn chặn tình trạng giá sản phẩm bị rơi về `None` hoặc ép về `0.0`.
**Bảo vệ phân loại chống báo giả phụ kiện (SKU-level Anti-Accessory Guard)**:
Quy tắc loại trừ các phân loại rác hoặc phụ kiện giá rẻ (như switch lẻ, keycap lẻ, dụng cụ nhổ puller, mỡ bôi trơn lube, dây cáp sạc, feet chuột, túi đựng, miếng lót chuột) được người bán gài chung vào cùng link sản phẩm chính (như bàn phím cơ, chuột gaming, laptop). Hệ thống kết hợp từ khóa danh mục phụ kiện mở rộng với tỷ lệ chênh lệch giá (nếu giá phân loại < 20% so với giá sản phẩm chính kèm từ khóa chỉ đơn vị lẻ `1 chiếc`, `lẻ`, `phụ kiện`) để loại trừ khỏi việc tính giá deal, ngăn chặn việc báo lỗi giá giả 90% khi thực chất chỉ là mua phụ kiện lẻ.
_Avoid_: Báo nhầm deal sập giá khi người bán bán switch lẻ hoặc keycap lẻ trong link bàn phím

**Mốc so sánh lỗi giá trước lịch sử đầy đủ (Prior Scan Baseline for Early Price Errors)**:
Cơ chế xác định giá tham chiếu cho sản phẩm mới theo dõi khi chưa đủ 3 điểm dữ liệu để tính giá trung vị 30 ngày (`median_30d = None`). Hệ thống sử dụng giá quét ngay trước đó (`history[0]`) làm mốc tham chiếu so sánh. Khi giá sản phẩm ở lần quét tiếp theo giảm đột ngột ≥ 65% so với lần quét trước, hệ thống lập tức kích hoạt quy trình cảnh báo lỗi giá khẩn cấp kèm cơ chế tự động quét lại sau 2 phút để xác minh.
_Avoid_: Bỏ lọt sập giá/lỗi giá ở các lần quét đầu tiên khi chưa có median 30 ngày

**Biến thể giá thấp nhất còn hàng (Lowest In-Stock Variation)**:
Quy tắc ưu tiên theo dõi biến thể (model/SKU) có giá bán thấp nhất trong số các biến thể đang CÒN HÀNG (`stock > 0` và không bị vô hiệu hóa) của một link sản phẩm (kể cả phụ kiện hay sản phẩm chính theo ADR 0053). Giá và tên của biến thể này được dùng làm đại diện cho sản phẩm theo dõi, kèm hậu tố tên biến thể `(Tên biến thể)` trên giao diện.
_Avoid_: Lấy giá của biến thể đã hết hàng, lấy giá `price_min` từ model đã bán hết

**Chuyển tiếp biến thể tự động (Automatic Variation Transition)**:
Cơ chế tự động chuyển mốc theo dõi sang biến thể còn hàng có giá thấp tiếp theo khi biến thể rẻ nhất trước đó bị bán hết hàng (`stock = 0` hoặc `disable = True`). Sản phẩm chỉ bị đánh dấu là hết hàng khi tất cả biến thể hợp lệ đều hết hàng. Tên sản phẩm được làm sạch và cập nhật hậu tố biến thể mới tương ứng mà không bị cộng dồn nhiều ngoặc đơn.
_Avoid_: Báo toàn bộ sản phẩm hết hàng khi vẫn còn biến thể khác còn hàng, cộng dồn tên biến thể qua các lần quét

**Chuẩn hóa liên kết sản phẩm đa phân loại (Canonical Product URL Normalization)**:
Quy tắc loại bỏ hậu tố mã phân loại cụ thể (`-s<skuid>.html` trên Lazada hoặc `?modelid=<id>` trên Shopee) khỏi URL khi người dùng thêm sản phẩm theo dõi (ADR 0053), chuẩn hóa đường dẫn về định dạng Item gốc. Việc chuẩn hóa này đảm bảo quá trình cào dữ liệu không bị cố định vào một phân loại đơn lẻ trong URL mà luôn quét toàn bộ dải biến thể để chọn ra biến thể còn hàng có giá rẻ nhất.
_Avoid_: Giữ nguyên mã SKU `-s...` hoặc `modelid=...` trong URL khiến hệ thống chỉ theo dõi một phân loại đơn lẻ

**Nhận diện chặn Captcha Punish Lazada (Lazada Punish Frame Detection)**:
Cơ chế phát hiện trạng thái bị sàn Lazada chặn hoặc thách thức xác minh bằng iframe reCAPTCHA (`acs-m.lazada.vn/.../punish?x5secdata=...`). Khi phát hiện iframe này xuất hiện trên trang, hệ thống kích hoạt ngoại lệ `Blocked` để cảnh báo cần làm mới phiên đăng nhập (refresh cookies) thay vì âm thầm đọc dữ liệu tracking dự phòng (`fields.tracking.pdt_price`) dẫn đến việc ghi nhận giá ảo hoặc sai lệch vào cơ sở dữ liệu.
_Avoid_: Bỏ qua iframe punish và lấy nhầm giá tĩnh/giá tracking dự phòng khi trang đang bị chặn captcha

**Trích xuất giá MTOP chi tiết phân loại Lazada (Lazada MTOP Detail SKU Price Extraction)**:
Cơ chế chặn bắt gói tin mạng của API MTOP `mtop.global.detail.web.getdetailinfo` trên trình duyệt Playwright để nạp đầy đủ dữ liệu giá bán (`salePrice`, `originalPrice`, `subsidyPrice`) và số lượng tồn kho thực tế cho từng phân loại (SKU), khắc phục triệt để hạn chế của cơ chế kết xuất tĩnh SSR của Lazada khi `skuInfos` không nhúng sẵn giá của từng biến thể.
_Avoid_: Chỉ dựa vào dữ liệu SSR `window.__moduleData__` vốn để trống giá của các biến thể

**Biến thể chính (Main Variant)**:
Biến thể cụ thể trong một listing mà người dùng muốn sở hữu và theo dõi giá hàng đầu (ví dụ bàn phím màu đen, switch đỏ). Nếu link người dùng dán có chứa mã SKU/model cụ thể, biến thể đó được gán làm Biến thể chính; nếu dán link chung thì biến thể còn hàng có giá rẻ nhất ban đầu được chọn làm Biến thể chính. Mọi cảnh báo về giá deal hoặc hết hàng đều xoay quanh Biến thể chính này trước tiên.
_Avoid_: Bỏ qua lựa chọn SKU ban đầu của người dùng khi họ dán link biến thể cụ thể

**Biến thể thay thế (Fallback Variant)**:
Biến thể khác trong cùng một listing được hệ thống tự động tìm kiếm, đánh giá và đề xuất cho người dùng khi Biến thể chính rơi vào trạng thái HẾT HÀNG (đã xác nhận). Biến thể thay thế phải còn hàng, thỏa mãn thuộc tính khóa hoặc danh sách cho phép, và không vượt trần giá quy định (mặc định +20%).
_Avoid_: Tự động thay thế sang phụ kiện rác hoặc loại biến thể không tương đương

**Thuộc tính khóa (Key Attribute)**:
Thuộc tính kỹ thuật hoặc cốt lõi của biến thể bắt buộc phải giữ nguyên như Biến thể chính khi thực hiện tìm kiếm Biến thể thay thế (ví dụ: cùng loại Switch hay dung lượng RAM, trong khi Màu sắc có thể linh hoạt chấp nhận đổi).
_Avoid_: Chọn biến thể thay thế có giá rẻ nhưng sai thông số kỹ thuật cốt lõi

**Lịch sử biến thể theo sai biệt (Delta Variant History)**:
Cơ chế lưu trữ lịch sử giá và tồn kho của từng biến thể (`variant_history`) theo nguyên tắc vi sai: chỉ chèn bản ghi mới khi giá bán, giá niêm yết hoặc trạng thái kho của biến thể thực sự thay đổi so với lần ghi trước đó. Điều này giúp hệ thống theo dõi chi tiết hàng chục biến thể trên mỗi listing mà không gây phình to cơ sở dữ liệu SQLite.
_Avoid_: Ghi trùng lặp lịch sử biến thể sau mỗi chu kỳ quét khi dữ liệu không có biến động

**Máy trạng thái tồn kho (Stock State Machine)**:
Mô hình chuyển dịch trạng thái tồn kho của Biến thể chính gồm 3 mức: `CÒN HÀNG` (In Stock) -> `NGHI HẾT` (Unconfirmed Out of Stock) sau lần đọc đầu tiên phát hiện hết hàng -> `HẾT HÀNG` (Confirmed Out of Stock) sau khi lượt quét nhanh xác minh (fast scan) lần 2 xác nhận vẫn hết hàng. Việc kích hoạt Biến thể thay thế chỉ xảy ra khi đã ở trạng thái `HẾT HÀNG` được xác nhận.
_Avoid_: Chuyển sang biến thể thay thế ngay lập tức chỉ sau 1 lần quét lỗi hoặc chưa tải xong trang

**Quét nhanh xác minh (Fast Verification Scan)**:
Chu kỳ quét lặp lại ưu tiên với độ trễ ngắn (mặc định 2-3 phút) được tự động kích hoạt ngay khi Biến thể chính chuyển sang trạng thái `NGHI HẾT`, nhằm xác minh nhanh tín hiệu hết hàng trước khi chính thức chuyển sang `HẾT HÀNG` và kích hoạt thuật toán tìm biến thể thay thế.
_Avoid_: Chờ đủ chu kỳ quét định kỳ 8-15 phút mới kiểm tra lại biến thể nghi hết hàng

**Chế độ thay thế âm thầm (Silent Fallback Mode)**:
Cơ chế tự động chuyển đổi trạng thái tồn kho, xác minh fast scan và gán Biến thể thay thế hoàn toàn ngầm trong cơ sở dữ liệu và bảng điều khiển (Dashboard) mà không bắn tin nhắn thông báo đẩy (push notifications) qua Telegram, tránh làm phiền người dùng bằng các thông tin thay đổi nội bộ.
_Avoid_: Gửi tin nhắn thông báo Telegram liên tục mỗi khi biến thể chuyển trạng thái nghi hết hoặc đổi biến thể tạm thời

**Tạm dừng quét phân hệ tự động (Subsystem Scan Suspension)**:
Cơ chế cho phép người dùng bật hoặc tắt chu kỳ quét tự động định kỳ của từng phân hệ phụ trợ (Theo từ khóa, Siêu Sale & Flash Sale, Săn lỗi giá) trực tiếp từ bảng Cài đặt web mà không làm gián đoạn việc quét sản phẩm theo dõi chính hay các tính năng quét thủ công khi bấm nút.
_Avoid_: Phải sửa code hoặc tắt toàn bộ tiến trình hệ thống để ngừng cào một phân hệ

**Dò biến thể theo nhu cầu khi hết hàng (On-Demand Swatch Probing on Out-of-Stock)**:
Cơ chế tối ưu hóa hiệu năng cào dữ liệu: crawler chỉ thực hiện thao tác nhấp chuột (click) vào các ô biến thể (swatches) trên giao diện DOM để đọc giá khuyến mãi và trạng thái kho thực tế khi và chỉ khi biến thể hiện tại (hoặc biến thể chính đang theo dõi) rơi vào trạng thái HẾT HÀNG. Khi sản phẩm đang còn hàng, crawler duy trì đường dẫn không nhấp chuột (zero-click) nhằm bảo đảm tốc độ quét tối đa và không gây trễ cho toàn hệ thống.
_Avoid_: Nhấp chuột chuyển qua chuyển lại tất cả các biến thể trong mọi chu kỳ quét ngay cả khi sản phẩm đang còn hàng

**Ngữ cảnh tương tác Bot (Interactive Bot Context)**:
Trạng thái lưu vết tạm thời trong bộ nhớ của Telegram Bot gắn với từng đoạn hội thoại (chat), ghi nhớ sản phẩm vừa được thao tác gần nhất (`last_product_id`) và hành động kế tiếp đang chờ. Cơ chế này cho phép người dùng chỉ cần nhập trực tiếp nội dung (đường dẫn sản phẩm hoặc số tiền giá mong muốn) theo hướng dẫn của nút bấm Inline mà không cần gõ lặp lại mã định danh `#ID` hay link sản phẩm.
_Avoid_: Bắt người dùng phải nhớ và gõ lại ID sản phẩm ở mỗi bước tương tác trên điện thoại

**Thẻ sản phẩm tương tác (Interactive Product Card)**:
Đơn vị hiển thị độc lập của mỗi sản phẩm trong danh sách theo dõi trên Telegram, bao gồm một tin nhắn chứa thông tin chi tiết (mã #ID, tên, giá, voucher, tồn kho, link) và một bàn phím Inline Keyboard gắn trực tiếp dưới chân tin nhắn (`[🎯 Đặt giá]`, `[🗑️ Xóa]`). Mô hình này đảm bảo các nút thao tác luôn nằm sát dưới sản phẩm tương ứng, hỗ trợ đổi trạng thái xác nhận xóa tại chỗ.
_Avoid_: Gom nhiều sản phẩm vào một tin nhắn dài rồi dồn toàn bộ nút bấm xuống cuối cùng

**Trạng thái tồn kho nhị phân (Binary Stock State)**:
Tình trạng hàng hóa của sản phẩm được rút gọn thành hai trạng thái duy nhất: Còn hàng (`stock=True`) hoặc Hết hàng (`stock=False`), không cần bóc tách số lượng cụ thể, tập trung kiểm tra khả năng bấm nút mua hàng của người dùng.
_Avoid_: Bắt buộc phải cào chính xác số lượng tồn kho hay phân cấp trạng thái tồn kho phức tạp cho sản phẩm người dùng tự theo dõi

**Tab Lazada TMALL (Lazada TMALL Tab)**:
Phân hệ chuyên biệt trên Web Dashboard dành riêng cho việc hiển thị và gom nhóm các sản phẩm được trợ giá sâu từ chuyên trang Lazada TMALL Trợ Giá / Choice, áp dụng cấu trúc bảng tinh gọn 6 cột và logic cào nhị phân không rating tương tự tab Sản phẩm theo dõi.
_Avoid_: Dồn chung sản phẩm TMALL vào tab Sản phẩm theo dõi của người dùng hay tab Siêu Sale diện rộng

**Nguồn dữ liệu Lazada TMALL (`source='lazada_tmall'`)**:
Nhãn phân loại nguồn gốc sản phẩm trong cơ sở dữ liệu xác định sản phẩm xuất phát từ luồng cào danh mục TMALL Trợ Giá của sàn Lazada, cho phép phân tách độc lập trong truy vấn, bảo tồn danh sách sản phẩm người dùng tự theo dõi và điều chỉnh lịch quét riêng biệt.
_Avoid_: Ghi đè thành source='user' hoặc source='flash_sale'

**Kênh TMALL Thương Hiệu Trung Chính Hãng (Lazada TMALL Official Channel)**:
Chuyên trang chính thức của Lazada (`https://www.lazada.vn/wow/gcp/lazada/channel/vn/lazmall-channel/thuong-hieu-trung-chinh-hang`) tập hợp các sản phẩm chính hãng LazMall từ các thương hiệu nội địa và quốc tế, được xây dựng dưới dạng ứng dụng đơn trang (SPA) với các section khuyến mãi và luồng sản phẩm cuộn vô tận.
_Avoid_: Dùng URL tìm kiếm từ khóa catalog thông thường để cào TMALL

**Bộ lọc danh mục TMALL (TMALL Category Filtering)**:
Cơ chế lọc 2 tầng (tầng 1: đối soát từ khóa công nghệ trên tiêu đề thẻ; tầng 2: kiểm tra breadcrumb danh mục Lazada) nhằm chỉ giữ lại các sản phẩm thuộc nhóm "Thiết bị điện tử" và "Phụ kiện điện tử", loại bỏ hoàn toàn các mặt hàng thời trang, mỹ phẩm, đồ gia dụng phi điện tử.
_Avoid_: Cào tràn lan toàn bộ các ngành hàng không liên quan từ trang landing page

**Khoảng giá cào TMALL (TMALL Price Range Filter)**:
Cấu hình khoảng giá gồm ngưỡng tối thiểu (`tmall_min_price`) và tối đa (`tmall_max_price`) trong cài đặt hệ thống, chỉ cho phép lưu và theo dõi các sản phẩm TMALL có mức giá hiện tại nằm trong phạm vi này.
_Avoid_: Cào tất cả sản phẩm bất kể giá hoặc cố định giá cứng trong mã nguồn

**Ưu tiên bóc tách Cookie (Cookie-First DOM Parsing)**:
Chiến lược trong `PlaywrightAdapter` ưu tiên đọc dữ liệu trực tiếp từ DOM đã render bởi cookie phiên đăng nhập trước khi kiểm tra các tín hiệu cảnh báo anti-bot. Nếu trang đã nạp đủ giá (`price > 0`), hệ thống trả về kết quả ngay lập tức thay vì dừng lại chờ giải các iframe trừng phạt ngầm (`punish`).
_Avoid_: Kiểm tra punish iframe trước rồi ném lỗi Blocked làm gián đoạn cào khi trang đã hiển thị đủ dữ liệu

**Kéo thanh trượt giả lập người thật (Simulated Human Slider Drag)**:
Kỹ thuật điều khiển chuột tự động (`_try_drag_slider`) tương tác với các thanh trượt xác thực của Alibaba (`.btn_slide`, `#nc_1_wrapper`) bằng cách di chuột, nhấn chuột trái, kéo theo từng bước ngẫu nhiên giảm tốc (ease-out) và nhả chuột, giúp vượt qua thử thách trượt mà các extension tự động thông thường không giải được.
_Avoid_: Dùng JavaScript gán thuộc tính DOM để vượt thanh trượt bảo mật hoặc bỏ qua thanh trượt khi bị chặn

**Cảnh báo lỗi kép (Dual Failure Alert)**:
Thông báo khẩn gửi tới quản trị viên Telegram chỉ khi cả hai tầng giải pháp đều thất bại (Cookie phiên đăng nhập hết hạn hoặc bị rào cản an ninh chặn và bộ giải Captcha không thể tự vượt qua), nhắc nhở người dùng cập nhật cookie mới hoặc cấu hình NopeCHA API Key.
_Avoid_: Gửi thông báo hết lượt giải captcha khi phiên cào vẫn thành công qua cookie

**Thứ bậc trích xuất giá (Price Extraction Hierarchy)**:
Quy tắc ưu tiên dữ liệu giá khi phân tích trang sản phẩm: ưu tiên biến thể chỉ định còn hàng từ API/payload MTOP, sau đó đến các phần tử giá khuyến mãi thực tế trên giao diện DOM (`.pdp-v2-product-price-content-salePrice`, `.pdp-price_color_orange`), và chỉ dùng giá danh mục (`pdt_price`) làm ứng viên cho giá gốc (`list_price`), tuyệt đối không gán vào giá bán.
_Avoid_: Gán giá niêm yết catalog làm giá bán, bỏ qua bộ chọn DOM

**Tự động chuyển đổi biến thể còn hàng rẻ nhất (In-Stock Variant Fallback)**:
Cơ chế tự động chuyển đổi sang biến thể còn hàng có giá thấp nhất (đã loại trừ phụ kiện qua bộ lọc) khi phân loại người dùng chỉ định (`target_sku` hoặc mã SKU trong URL) bị hết hàng, đảm bảo crawler vẫn thu thập được dữ liệu chào bán thực tế và cập nhật đúng tên biến thể thay thế.
_Avoid_: Báo hết hàng toàn bộ khi vẫn còn biến thể khác, lấy biến thể rẻ nhất bất chấp phân loại chỉ định còn hàng

**Bảo vệ sản phẩm người dùng tự theo dõi (User Tracked Product Protection)**:
Quy tắc bất biến trong hệ thống crawler: các sản phẩm do chính người dùng thêm vào danh sách theo dõi (`source = 'user'`) tuyệt đối không bao giờ bị tự động chuyển sang trạng thái ngưng hoạt động (`active = 0`) chỉ vì gặp các lỗi mạng, lỗi bóc tách giá hay rào cản captcha tạm thời (`FetchError`). Thay vào đó, sản phẩm vẫn được duy trì trong danh sách, chỉ gắn cờ cảnh báo lỗi và gửi thông báo cho quản trị viên sau 5 lần thử thất bại liên tiếp.
_Avoid_: Đánh đồng lỗi mạng tạm thời của sàn thành việc sản phẩm bị xóa và tự động tắt theo dõi của người dùng

**Khôi phục theo dõi (Product Reactivation)**:
Hành động kích hoạt lại sản phẩm đã bị ngưng hoạt động (`active = 1`, `fail_count = 0`), đưa sản phẩm trở lại chu kỳ quét định kỳ của crawler mà vẫn giữ nguyên toàn bộ lịch sử giá và cấu hình mong muốn trước đó.
_Avoid_: Bắt người dùng phải xóa đi và thêm lại đường dẫn từ đầu khi muốn theo dõi lại

**Lỗi sàn diện rộng (Platform-Wide Blocked Exception)**:
Ngoại lệ kỹ thuật (`Blocked`) chỉ định sự cố bảo mật, hết hạn phiên xác thực hoặc rào cản Captcha/Slider cấp độ toàn sàn thương mại điện tử (ví dụ lỗi MTOP `RGV587_ERROR` hay `FAIL_SYS_USER_VALIDATE` của Alibaba), buộc crawler dừng ngay chu kỳ quét của toàn bộ sàn đó để tránh gửi request vô nghĩa, hoàn toàn phân biệt với lỗi của một đường link sản phẩm cá biệt (`FetchError`).
_Avoid_: Ném ngoại lệ FetchError khi sàn bị chặn bảo mật, làm tích lũy số lần quét lỗi sai lệch cho từng sản phẩm
**Triệt tiêu giá trần gian hàng (Category Ceiling Price Elimination / Anti-Inflation)**:
Quy tắc loại bỏ hoàn toàn trường giá danh mục `tracking.pdt_price` khỏi việc gán vào giá gốc (`list_price`) trên sàn Lazada (ADR 0054). Giá gốc chỉ được công nhận khi có gạch giá công khai thực tế trên chính phân loại đó hoặc trên DOM (`originalPrice`, `.pdp-price_type_deleted`). Điều này loại trừ triệt để tình trạng báo deal giảm sâu 80-93% ảo và các cảnh báo lỗi giá giả.
_Avoid_: Dùng giá trần catalog làm giá gốc, lạm phát % giảm giá ảo

**Tự động ngưng theo dõi sản phẩm bị xóa (Delisted / 404 Product Auto-Deactivation)**:
Cơ chế tự động phát hiện các liên kết sản phẩm đã bị người bán xóa vĩnh viễn hoặc sàn gỡ bỏ (HTTP 404 hoặc thông báo "Xin lỗi! Sản phẩm này không còn tồn tại"). Hệ thống tự động chuyển `active = 0, fail_count = 0`, ghi nhận tồn kho bằng 0 và ngưng quét link này, giúp bảng điều khiển luôn phản ánh đúng thực tế và giải phóng tài nguyên cào giá.
_Avoid_: Tiếp tục quét và duy trì giá cũ cho link 404 đã bị xóa


**Tạm dừng quét phân hệ tự động (Subsystem Scan Suspension)**:
Cơ chế tạm thời vô hiệu hóa tiến trình cào tự động nền của các phân hệ khám phá (Tìm kiếm từ khóa `keyword`, Bắt lỗi giá `price_error`, Siêu Sale `megasale`, và Lazada TMALL `tmall`), đồng thời ẩn các tab tương ứng khỏi giao diện Web Dashboard (ADR 0055). Toàn bộ tài nguyên mạng, trình duyệt và hạn mức giải Captcha được tập trung tối đa cho danh mục sản phẩm theo dõi của người dùng. Hệ thống triệt tiêu mọi thông báo Telegram từ các phân hệ bị ẩn trong khi bảo lưu trọn vẹn cảnh báo khi sản phẩm theo dõi chạm giá mong muốn (`target_price`).
_Avoid_: Chạy quét cào nền tiêu tốn captcha cho các phân hệ khám phá khi người dùng chỉ tập trung săn deal danh sách sản phẩm theo dõi chỉ định.


**Cảnh báo giá mong muốn tức thời (Instant Target Price Alert)**:
Quy tắc xử lý cảnh báo khi sản phẩm người dùng theo dõi đạt hoặc thấp hơn mức giá mong muốn (`effective_price <= target_price`) (ADR 0056). Cảnh báo giá mong muốn được ưu tiên tối đa và bỏ qua hoàn toàn cơ chế giới hạn tần suất (cooldown 24 giờ hoặc yêu cầu giảm tiếp ≥ 5% của `Alerter`). Hệ thống phát thông báo ngay lập tức vào Group Telegram ở mỗi chu kỳ quét chừng nào giá sản phẩm vẫn nằm trong tầm giá mong muốn của người dùng, đảm bảo người dùng không bỏ lỡ đợt giảm giá chớp nhoáng.
_Avoid_: Giữ cơ chế cooldown 24h đối với thông báo giá mong muốn khiến người dùng bị lỡ cơ hội săn deal khi giá đạt mục tiêu trong các chu kỳ quét liên tiếp.


**Nạp Cookie Không Khóa Trình Duyệt (Non-Blocking & Deadlock-Free Cookie Reloading)**:
Kỹ thuật nạp cookies vào phiên trình duyệt Playwright an toàn: khi hàm được gọi từ chính luồng công nhân của crawler (`pw-worker`), hệ thống sẽ nạp trực tiếp vào ngữ cảnh thay vì đẩy thêm task vào hàng đợi của chính executor đơn luồng gây deadlock tự khóa vĩnh viễn (ADR 0057). Khi gọi từ luồng ngoài (Flask Web API), hàm áp dụng thời gian chờ (timeout) an toàn kết hợp phản hồi tức thì trên giao diện để người dùng không gặp tình trạng treo giao diện hoặc mất phản hồi khi ấn "Lưu & Kích hoạt".
_Avoid_: Đẩy task vào chính luồng worker đơn đang thực thi khiến executor deadlock, gọi đồng bộ không có timeout từ Flask request.

**Câm Lặng Phân Hệ Siêu Sale & Cào Thủ Công (Megasale Silence & Manual-Only Scanning)**:
Chính sách ngừng phát sóng toàn bộ cảnh báo Telegram (kể cả Flash Deal và Nghi lỗi giá) sinh ra từ phân hệ "🔥 Siêu sale & Giảm giá sâu" (`source = 'flash_sale'`), đồng thời chuyển chu kỳ quét sang chế độ thủ công theo yêu cầu (chỉ cào khi người dùng chủ động bấm các nút cào trên Dashboard) (ADR 0057). Nếu một deal trong Siêu Sale được người dùng gắn giá mong muốn (`target_price`), cảnh báo giá mong muốn vẫn được phát bình thường khi đạt điều kiện.
_Avoid_: Gửi tin nhắn Flash Sale tự động làm phiền Telegram, tự động quét nền tiêu tốn tài nguyên và hạn ngạch giải captcha khi chưa có lệnh thủ công từ người dùng.


**Kéo Trượt Dự Phòng Đa Tầng (Multi-Tier Fallback Slider Dragging)**:
Thứ tự ưu tiên xử lý rào cản an ninh thanh trượt (Alibaba/Lazada Slider): (1) Dùng cookie phiên có sẵn (`x5sec`, `lzd_sid`) -> (2) Chờ tiện ích NopeCHA tự động xử lý -> (3) Kích hoạt thuật toán kéo trượt mô phỏng hành vi người thật (Bezier Curve Dragging qua Chrome DevTools Protocol) làm tuyến phòng thủ cuối cùng khi cả 2 phương án trước không hiệu quả. Tối đa 2 lần thử trước khi áp dụng thời gian chờ (cool-down).
_Avoid_: Kéo trượt ngay từ đầu khi chưa cho NopeCHA cơ hội giải, bỏ qua cookie hợp lệ có sẵn.

**Thu Hoạch Token An Ninh Tự Động (Automated Security Token Harvesting)**:
Cơ chế tự động bóc tách và thu thập các cookie phiên an ninh mới nhất (đặc biệt là `x5sec`, `_tb_token_`, `lzd_sid`) từ ngữ cảnh trình duyệt Playwright ngay khi giải phóng thanh trượt thành công, sau đó lập tức ghi đè cập nhật vào `data/cookies_lazada.json` để miễn trừ captcha cho toàn bộ các lượt cào sản phẩm kế tiếp.
_Avoid_: Bỏ qua việc lưu cookie sau khi giải thành công, khiến từng sản phẩm riêng lẻ đều phải kéo lại thanh trượt.


**Bóc tách giá sản phẩm đơn lẻ (Single-SKU DOM Price Extraction)**:
Cơ chế bóc tách giá chuyên biệt cho các sản phẩm đơn lẻ không có phân loại (single-SKU / no variants) trên Lazada và Shopee (ADR 0058). Hạ cấp dữ liệu JSON-LD thành phương án dự phòng (fallback) cuối cùng và ưu tiên bóc tách trực tiếp giá khuyến mãi/trợ giá đang hiển thị trên giao diện DOM (`.pdp-v2-product-price-content-salePrice`, `.pdp-price_color_orange`, `.priceSectionPrice`, `.pqTWkA`). Cơ chế này được cách ly hoàn toàn với các sản phẩm có nhiều phân loại (`len(sku_infos) > 1`), đảm bảo tuyệt đối không làm sai lệch hay ảnh hưởng tới thuật toán chọn SKU còn hàng rẻ nhất của các sản phẩm đa biến thể.
_Avoid_: Gán cứng giá JSON-LD tĩnh cho sản phẩm đơn lẻ khiến bỏ lỡ giá khuyến mãi DOM, hoặc sửa logic làm ảnh hưởng tới việc chọn SKU của sản phẩm đa phân loại.


**Chuẩn hóa định danh SKU duy nhất (Unique SKU Deduplication)**:
Kỹ thuật lọc và đếm số lượng phân loại sản phẩm dựa trên tập các mã định danh SKU duy nhất (`unique_sku_ids = set(actual_sid)`) thay vì đếm số lượng key trong từ điển `skuInfos` (ADR 0059). Khắc phục tình trạng các sàn (như Lazada) trả về cả key chỉ mục `'0'` và key ID `'117120756839'` cho cùng 1 SKU duy nhất, ngăn chặn hoàn toàn việc nhận nhầm sản phẩm đơn lẻ thành sản phẩm đa phân loại.
_Avoid_: Đếm số lượng key từ điển `len(sku_infos)` khiến sản phẩm 1 SKU bị nhận diện nhầm thành multi-option.


**Bóc tách giá voucher trực tiếp (Direct Coupon Price Extraction)**:
Cơ chế ưu tiên trích xuất mức giá thanh toán thực tế sau khi đã trừ voucher/khuyến mãi áp dụng trực tiếp tại chỗ (chẳng hạn ưu đãi "Mua ngay giảm..." của Lazada) nằm trong trường `price.coupon.priceNumber` của payload và class DOM `.pdp-v2-product-price-content-salePrice-amount` (ADR 0059). Giúp phản ánh chính xác con số giá bán hiển thị trực quan cho người mua thay vì lấy giá `salePrice` danh nghĩa trước voucher.
_Avoid_: Bỏ qua trường coupon trong payload khiến lấy nhầm giá bán cao hơn giá thực tế hiển thị trên màn hình.


**Kiến trúc Polling 2 Tầng (Dual-Speed Polling Architecture)**:
Mô hình theo dõi giá kết hợp giữa Quét nhanh tầng 1 (Tier-1 Fast Poller qua HTTP/API gọn nhẹ với tần suất cao 1-2 phút) và Xác thực chuyên sâu tầng 2 (Tier-2 Playwright Verifier mở trình duyệt đầy đủ khi phát hiện biến động giá sốc hoặc cần phục hồi phiên làm việc cookie/captcha) (ADR 0060).
_Avoid_: Chạy Playwright liên tục cho mọi sản phẩm ở tần suất cao gây nghẽn RAM và dính anti-bot.


**Tự phục hồi phiên (Self-Healing Session Fallback)**:
Cơ chế tự động chuyển đổi luồng cào sang Playwright và NopeCHA khi phát hiện cookie hoặc token phiên làm việc trên sàn bị hết hạn hoặc bị dính thử thách xác minh, nhằm cập nhật lại cookie mới mà không cần can thiệp thủ công từ quản trị viên (ADR 0060).
_Avoid_: Báo lỗi dừng cào ngay khi cookie hết hạn mà không thử kích hoạt trình duyệt để tự làm mới phiên.


**Phân loại theo dõi (Tracked Variant)**:
Biến thể hoặc phân loại cụ thể (màu sắc, cấu hình, switch) của một sản phẩm đa lựa chọn mà hệ thống đang trực tiếp lấy giá và giám sát biến động (ưu tiên biến thể còn hàng có giá thấp nhất) (ADR 0061).
_Avoid_: Nhầm lẫn giữa phân loại sản phẩm theo ngành hàng (category) với phân loại lựa chọn SKU của người bán (option/variant).


**Chế độ chỉ thông báo đạt giá mong muốn (Target-Price-Only Alert Mode)**:
Chế độ lọc thông báo giá trong đó hệ thống chỉ phát cảnh báo Telegram khi sản phẩm trong danh sách theo dõi đạt hoặc thấp hơn mức giá kỳ vọng (`effective_price <= target_price`) do người dùng thiết lập, đồng thời tạm tắt các cảnh báo giảm giá thường, deal thật thuật toán và nghi lỗi giá (ADR 0062).
_Avoid_: Gửi thông báo biến động giảm giá vụn vặt gây nhiễu kênh nhận tin của người dùng khi đang săn deal mục tiêu.


**Kết nối Trình duyệt Điều khiển từ xa (Chrome DevTools Protocol / CDP)**:
Phương thức điều khiển và bóc tách dữ liệu trực tiếp từ phiên Google Chrome thật đang chạy trên máy tính người dùng thông qua cổng điều khiển từ xa (mặc định 9222), giúp crawler tận dụng 100% vân tay phần cứng thật và phiên đăng nhập lưu trữ tự nhiên của Chrome để triệt tiêu hoàn toàn captcha và hiện tượng thu hồi cookie (ADR 0063).
_Avoid_: Chạy Chromium ẩn danh cô lập trong container khiến sàn nhận diện dấu hiệu bot giả lập.


**Cơ chế Tự động Dự phòng Trình duyệt (Graceful Browser Fallback)**:
Khả năng tự động kiểm tra và chuyển đổi thông minh giữa hạt nhân cào Chrome thật (qua giao thức CDP) và nhân trình duyệt Playwright nội bộ có sẵn trong ứng dụng khi phát hiện tiến trình Chrome bên ngoài chưa được khởi chạy, đảm bảo chu kỳ quét giá không bao giờ bị dừng hoặc treo (ADR 0063).
_Avoid_: Dừng toàn bộ tiến trình quét hoặc ném lỗi văng ứng dụng khi không tìm thấy cổng CDP.


**Trình duyệt Headless Ngầm trong Docker (Docker Headless Internal Crawler)**:
Mô hình khởi chạy trình duyệt Chromium nội bộ hoàn toàn không giao diện (headless) bên trong container Docker độc lập với máy chủ, tích hợp sẵn tiện ích giải captcha NopeCHA và bộ kịch bản giả lập hành vi người dùng, đảm bảo tiến trình cào quét vận hành tự động và tĩnh lặng 100% mà không gây nhấp nháy hay can thiệp vào màn hình làm việc của người dùng (ADR 0064).
_Avoid_: Bật mở cửa sổ trình duyệt trực quan trên màn hình máy tính chủ làm phiền người dùng.
