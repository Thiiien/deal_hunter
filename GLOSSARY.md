# Deal Hunter

Công cụ cá nhân theo dõi giá một danh sách sản phẩm chọn lọc trên Shopee và Lazada, ghi lịch sử giá và báo Telegram khi sản phẩm chạm giá mong muốn. Các phân hệ khám phá deal (từ khóa, siêu sale, lỗi giá, TMALL) vẫn có trong hệ thống nhưng hiện đang tắt (xem mục cuối).

Glossary chỉ chứa khái niệm nghiệp vụ. Chi tiết kỹ thuật (bảng, cờ, lệnh, bộ chọn DOM) nằm trong `docs/adr/`.

## Giá, lịch sử và deal

**Sản phẩm theo dõi (User-Tracked Product)**:
Sản phẩm do người dùng chủ động thêm vào danh sách (dán link trên dashboard, lệnh Telegram, hoặc nút "Theo dõi" ở tab khám phá). Chỉ sản phẩm theo dõi được quét định kỳ; các phân hệ khám phá không bao giờ tự chèn sản phẩm vào danh sách này.
_Avoid_: Sản phẩm quét ngầm, kết quả tìm kiếm tự thêm

**Snapshot**:
Bản ghi dữ liệu của một sản phẩm tại một lần quét: giá bán, giá niêm yết, giá sau áp mã, tồn kho, tên biến thể đang theo dõi, voucher, rating, lượt bán. Mọi nguồn dữ liệu (quét web, feed, dữ liệu giả) đều trả về cùng dạng này.
_Avoid_: Crawl result, product state

**Lịch sử giá (Price History)**:
Chuỗi Snapshot theo thời gian của một sản phẩm. Nguyên tắc thiết kế: chỉ ghi thêm, không bao giờ ghi đè hay xóa; giá trị cốt lõi của công cụ nằm ở chuỗi này.
_Avoid_: Biến động giá, log giá

**Giá trung vị 30 ngày (30-Day Median)**:
Giá trị nằm giữa của các mức giá thực trả ghi nhận trong 30 ngày gần nhất, không tính lần quét hiện tại. Dùng làm mốc so sánh chuẩn để chống nhiễu từ các đợt tăng/giảm giá đột biến.
_Avoid_: Giá trung bình, giá sàn

**Giai đoạn thu thập lịch sử (Cold-start Period)**:
Khoảng thời gian ngay sau khi thêm sản phẩm, khi chưa đủ 3 điểm lịch sử giá (tức chưa có 4 lần quét độc lập) để kết luận deal thật. Cảnh báo giá mong muốn và lỗi giá vẫn hoạt động trong giai đoạn này.
_Avoid_: Warm-up, learning period, thiếu dữ liệu

**Deal thật (Real Deal)**:
Sản phẩm có giá thực trả thấp hơn giá trung vị 30 ngày từ 30% trở lên (ngưỡng cấu hình được), còn hàng, và có giá trị thật tối thiểu đạt ngưỡng. Với sản phẩm khám phá tự động, thêm điều kiện rating sản phẩm từ 4.0 trở lên; với sản phẩm theo dõi, rating không được xét. Cảnh báo deal thật hiện đang tắt khi bật Chế độ chỉ thông báo đạt giá mong muốn.
_Avoid_: Giảm giá ảo, sale sốc, sale ảo

**Giá gốc ảo (Fake List Price)**:
Người bán nâng giá niêm yết lên cao bất thường để hiển thị mức giảm sâu, trong khi giá bán không hề rẻ hơn lịch sử giá thực tế. Một sản phẩm giảm sâu theo giá niêm yết nhưng không giảm so với trung vị 30 ngày được gắn nhãn này.
_Avoid_: Giá niêm yết, giá khuyến mãi, sale ảo

**Ngưỡng giá trị thật tối thiểu (Minimum Pre-Discount Baseline)**:
Mức giá trước giảm (mặc định 500.000₫, cấu hình được) mà sản phẩm phải đạt để được xét deal thật, flash deal hay lỗi giá. Giá trước giảm lấy theo trung vị 30 ngày, nếu chưa có thì theo lần quét trước, nếu vẫn chưa có thì theo giá niêm yết. Loại bỏ phụ kiện và đồ rác giá rẻ khỏi mọi cảnh báo.
_Avoid_: Giá sau giảm, ngưỡng cứng không cho cấu hình

**Affiliate Link**:
Đường dẫn sản phẩm đã gắn mã tiếp thị liên kết của người vận hành để nhận hoa hồng khi phát sinh đơn. Mọi link gửi ra khỏi hệ thống (bot, kênh, dashboard) đều phải là Affiliate Link.
_Avoid_: Direct link, link mua hàng

**Kênh phát sóng (Broadcast Channel)**:
Kênh hoặc nhóm Telegram công khai nơi bot đăng deal kèm Affiliate Link. Phân biệt với chat riêng của admin, nơi nhận cảnh báo kỹ thuật.
_Avoid_: Chat bot, kênh admin

**Chiến dịch Sale (Sale Campaign)**:
Đợt khuyến mãi của sàn (ngày đôi, Payday, Flash Sale khung giờ) được gắn nhãn vào mỗi lần ghi giá để phân tích deal theo đợt.
_Avoid_: Đợt giảm giá, sự kiện khuyến mãi

**Danh mục sản phẩm (Category)**:
Ngành hàng của sản phẩm, bóc từ thanh điều hướng của sàn, dùng để gom nhóm và lọc deal theo lĩnh vực.
_Avoid_: Thể loại, tag ngành hàng

**Nhóm theo danh mục (Category Grouping)**:
Cách dashboard gom sản phẩm theo ngành hàng và xếp theo mức giảm giảm dần để so sánh nhanh.
_Avoid_: Tag filter, list phẳng

## Theo dõi và cảnh báo

**Giá mong muốn (Target Price)**:
Mức giá tối đa người dùng đặt cho từng sản phẩm. Khi giá thực trả nhỏ hơn hoặc bằng mức này và sản phẩm còn hàng, hệ thống báo Telegram ngay, kể cả khi chưa đủ lịch sử giá.
_Avoid_: Giá kỳ vọng, giá chốt, ngưỡng cảnh báo

**Cảnh báo giá mong muốn tức thời (Instant Target Price Alert)**:
Cảnh báo giá mong muốn không chịu cooldown: được gửi ở mỗi chu kỳ quét chừng nào giá còn nằm trong tầm giá mong muốn. Với chu kỳ 2 phút, một sản phẩm nằm dưới giá mục tiêu lâu sẽ sinh rất nhiều tin (xem Vấn đề đã biết trong brief).
_Avoid_: Cooldown 24 giờ cho giá mong muốn

**Chế độ chỉ thông báo đạt giá mong muốn (Target-Price-Only Alert Mode)**:
Chế độ mặc định hiện nay: chỉ gửi cảnh báo giá mong muốn; tắt cảnh báo giảm giá thường, deal thật và nghi lỗi giá. Cảnh báo kỹ thuật cho admin (hết hạn phiên, captcha, sản phẩm bị xóa) không bị ảnh hưởng. Bật tắt trong Cài đặt dashboard.
_Avoid_: Tắt toàn bộ thông báo

**Cảnh báo giảm giá cho sản phẩm theo dõi (Tracked Price-Drop Alert)**:
Thông báo cho admin khi giá thực trả của sản phẩm theo dõi giảm so với lần quét trước (từ 5.000₫ hoặc 3% trở lên, cooldown 24 giờ), kể cả khi chưa đủ lịch sử. Hiện đang tắt theo Chế độ chỉ thông báo đạt giá mong muốn.
_Avoid_: Spam kênh deal chung

**Tần suất quét (Scan Interval)**:
Khoảng nghỉ (phút) giữa hai chu kỳ quét sản phẩm theo dõi, mặc định 2 phút, đổi được trên dashboard hoặc bằng lệnh Telegram và có hiệu lực ở chu kỳ kế tiếp. Giá trị lưu trong cài đặt hệ thống ghi đè giá trị trong file cấu hình.
_Avoid_: Chu kỳ cào, cron interval

**Quét hai tầng (Dual-Speed Polling)**:
Tầng 1 lấy giá bằng yêu cầu HTTP gọn nhẹ kèm cookie (hiện chỉ Shopee; Lazada luôn dùng trình duyệt). Tầng 2 mở trình duyệt đầy đủ để xác thực lại khi giá chạm giá mong muốn, giảm từ 20% so với lần trước, hoặc giảm từ 65% so với giá niêm yết, và khi phiên hết hạn hay gặp captcha.
_Avoid_: Mở trình duyệt cho mọi sản phẩm ở mọi chu kỳ

**Quét tức thì theo liên kết (Instant Link Scan)**:
Khi người dùng dán link mới, hệ thống quét ngay trong nền để cập nhật tên, giá, voucher, tồn kho thay vì chờ chu kỳ kế tiếp.
_Avoid_: Lưu URL thụ động

**Chuẩn hóa liên kết và hợp nhất bản ghi (Canonical Link & Merge)**:
Link rút gọn hoặc có tham số theo dõi được đưa về dạng chuẩn và mã định danh sản phẩm của sàn; mã phân loại trong link bị bỏ để quét toàn bộ biến thể. Nếu sản phẩm đã tồn tại, lịch sử giá được gộp và bản ghi tạm bị dọn.
_Avoid_: Lưu link rút gọn vĩnh viễn, nhân đôi sản phẩm

**Hủy theo dõi sản phẩm (Untrack)**:
Gỡ sản phẩm khỏi danh sách theo dõi cùng lịch sử giá và nhật ký cảnh báo của nó.
_Avoid_: Tạm dừng sản phẩm, ẩn sản phẩm

**Khôi phục theo dõi (Reactivation)**:
Đưa sản phẩm đã ngưng trở lại chu kỳ quét, giữ nguyên lịch sử giá và giá mong muốn.
_Avoid_: Xóa đi thêm lại

**Bảo vệ sản phẩm theo dõi (User-Tracked Product Protection)**:
Sản phẩm theo dõi không bao giờ bị tự động ngưng vì lỗi mạng, lỗi bóc giá hay captcha tạm thời; sau 5 lần lỗi liên tiếp hệ thống chỉ báo admin. Quy tắc tự ngưng sau 5 lỗi chỉ áp cho sản phẩm khám phá tự động.
_Avoid_: Đánh đồng lỗi mạng với sản phẩm bị xóa

**Phát hiện sản phẩm ngừng bán (Delisted Detection)**:
Nhận ra trong vòng một giây khi trang trả 404, báo "sản phẩm không tồn tại", hoặc chuyển hướng về trang chủ; sản phẩm được chuyển sang ngưng theo dõi và admin được báo. Lưu ý: chuyển hướng về trang chủ do chặn bot cũng bị hiểu là ngừng bán (xem Vấn đề đã biết).
_Avoid_: Chờ hết timeout, cào lặp link chết

**Sản phẩm sẵn sàng mua (Ready-to-buy Product)**:
Sản phẩm còn ít nhất một biến thể còn hàng và không bị khóa, xóa hay tạm dừng.
_Avoid_: Link sống

**Trạng thái tồn kho nhị phân (Binary Stock State)**:
Tồn kho chỉ có hai giá trị, còn hàng hoặc hết hàng, xác định theo khả năng bấm mua; không bóc số lượng. Trạng thái hiển thị trên giao diện (nút mua bị vô hiệu, banner hết hàng) được tin hơn dữ liệu tĩnh của trang.
_Avoid_: Đếm số lượng tồn kho

**Chặn cảnh báo khi hết hàng (Stock Alert Suppression)**:
Không gửi bất kỳ cảnh báo giá nào khi sản phẩm hết hàng.
_Avoid_: Tắt bot

**Tự động hủy theo dõi deal hết hàng (Auto-deactivate Sold-out Deals)**:
Sản phẩm thu thập từ Flash Sale được tự động ngưng theo dõi khi hết hàng hoặc hết đợt, để không làm rác dashboard. Không áp cho sản phẩm theo dõi.
_Avoid_: Xóa sản phẩm

## Biến thể

**Biến thể (Variant / Phân loại)**:
Một lựa chọn cụ thể trong một link sản phẩm (màu, cấu hình, switch, dung lượng). Phân biệt với Danh mục sản phẩm (ngành hàng).
_Avoid_: Option, SKU khi nói với người dùng

**Biến thể giá thấp nhất còn hàng (Lowest In-Stock Variant)**:
Quy tắc cho sản phẩm theo dõi: hệ thống luôn lấy biến thể rẻ nhất trong số các biến thể còn hàng của link làm đại diện, kể cả khi link người dùng dán có chứa mã một biến thể cụ thể (mã đó bị bỏ qua). Tên biến thể được gắn vào tên sản phẩm hiển thị.
_Avoid_: Lấy giá biến thể đã hết hàng, khóa cứng biến thể theo link

**Chuyển tiếp biến thể tự động (Automatic Variant Transition)**:
Khi biến thể rẻ nhất hết hàng, mốc theo dõi chuyển sang biến thể còn hàng rẻ tiếp theo. Sản phẩm chỉ bị coi là hết hàng khi mọi biến thể đều hết.
_Avoid_: Báo hết hàng toàn bộ khi còn biến thể khác

**Biến thể thay thế (Fallback Variant)**:
Biến thể được chọn thay khi biến thể đang theo dõi hết hàng đã được xác nhận. Điều kiện: còn hàng, không phải phụ kiện, và không đắt hơn biến thể cũ quá 20%. Hệ thống không có khái niệm thuộc tính bắt buộc giữ nguyên.
_Avoid_: Thay sang phụ kiện rác

**Bẫy biến thể phụ kiện (Accessory Variant Trap)**:
Người bán gài biến thể phụ kiện giá rẻ (ốp lưng, cáp, switch lẻ) vào link sản phẩm giá trị cao để hiển thị giá rẻ bất thường. Với phân hệ khám phá, bộ lọc chống phụ kiện loại các biến thể này; với sản phẩm theo dõi, hệ thống tôn trọng biến thể rẻ nhất còn hàng.
_Avoid_: Bỏ lỡ biến thể rẻ khi người dùng chủ động săn

**Bộ lọc chống phụ kiện (Anti-Accessory Filter)**:
Quy tắc loại sản phẩm hay biến thể phụ kiện dựa trên từ khóa (ốp, cáp, keycap lẻ, feet chuột...) kết hợp chênh lệch giá (dưới 20% giá sản phẩm chính), tránh báo deal hay lỗi giá giả.
_Avoid_: Blacklist từ khóa thuần

**Máy trạng thái tồn kho (Stock State Machine)**:
Ba mức: còn hàng, nghi hết (sau lần đọc đầu thấy hết), hết hàng (sau quét nhanh xác minh). Chỉ ở mức hết hàng mới chuyển biến thể.
_Avoid_: Đổi biến thể sau một lần đọc

**Quét nhanh xác minh (Fast Verification Scan)**:
Lần quét bổ sung sau khoảng 3 phút khi biến thể chuyển sang nghi hết, để xác nhận trước khi đổi biến thể.
_Avoid_: Chờ chu kỳ định kỳ

**Chế độ thay thế âm thầm (Silent Fallback)**:
Việc đổi trạng thái tồn kho và biến thể diễn ra trong dữ liệu và dashboard, không gửi Telegram.
_Avoid_: Thông báo mỗi lần đổi biến thể

**Dò biến thể (Variant Probing)**:
Với sản phẩm theo dõi có nhiều biến thể, trình duyệt bấm qua từng ô biến thể ở mỗi lần quét để đọc giá và tồn kho thực. Tốn thời gian hơn nhưng bảo đảm chọn đúng biến thể rẻ nhất còn hàng.
_Avoid_: Tin dữ liệu tĩnh của trang về giá từng biến thể

## Voucher và giá thực trả

**Mã giảm giá khả dụng (Shop Voucher)**:
Mã do shop hoặc sàn phát cho sản phẩm, giảm theo phần trăm hoặc số tiền, có điều kiện đơn tối thiểu và mức giảm tối đa.
_Avoid_: Coupon rác, quà tặng

**Giá thực trả (Final Price After Voucher)**:
Giá sau khi trừ tổ hợp voucher tốt nhất mà sản phẩm đủ điều kiện. Đây là giá dùng để so với giá mong muốn, tính trung vị 30 ngày và hiển thị cho người mua.
_Avoid_: Giá net, giá sau sale

**Cộng dồn voucher đa tầng (Voucher Stacking)**:
Áp đồng thời tối đa một mã ở mỗi tầng không xung đột: voucher shop, voucher sàn hoặc trợ giá nền tảng, ưu đãi xu hoặc hoàn tiền. Mã trùng được khử trước khi cộng.
_Avoid_: Chọn một voucher duy nhất, cộng dồn không kiểm soát

**Chống chiết khấu kép (Double Discount Prevention)**:
Một khoản trợ giá chỉ được trừ một lần: nếu giá biến thể đã là giá trợ giá thì không trừ thêm từ huy hiệu trợ giá đó.
_Avoid_: Giá ảo hai tầng

**Voucher trợ giá hội viên (Member Subsidy Voucher)**:
Trợ giá do Lazada tài trợ cho nhóm thành viên (MOMCLUB, TMALL trợ giá), có thể tới hàng triệu đồng hoặc trên 90%, xếp vào tầng trợ giá nền tảng để cộng dồn cùng voucher shop.
_Avoid_: Gộp vào voucher shop

## Phiên đăng nhập và captcha

**Cookie đăng nhập lưu trữ (Saved Cookies)**:
Cookie phiên của tài khoản sàn, xuất từ trình duyệt người dùng hoặc từ lần đăng nhập tương tác, được trình duyệt trong Docker nạp để vượt tường chặn khách. Mỗi sàn một bộ cookie riêng.
_Avoid_: Mật khẩu lưu trữ, auth token

**Xác thực phiên đa sàn (Per-Platform Session)**:
Cookie của Shopee và Lazada được lưu, kiểm tra và báo lỗi độc lập; một sàn hết phiên không làm gián đoạn sàn kia.
_Avoid_: Gộp cookie, ngắt toàn bộ scanner

**Kiểm tra phiên trước quét (Pre-flight Session Check)**:
Trước mỗi chu kỳ, hệ thống kiểm tra cookie từng sàn còn hiệu lực. Khi chạy có màn hình, nó mở đăng nhập tương tác; trong Docker không có màn hình, nó báo admin cấp cookie mới.
_Avoid_: Healthcheck sàn

**Tự động nhận diện đăng nhập (Auto-detect Login)**:
Trong đăng nhập tương tác, hệ thống nhận ra người dùng đã đăng nhập xong (qua cookie xác thực và chuyển hướng) để tự xuất cookie và đóng cửa sổ.
_Avoid_: Tự động điền mật khẩu

**Chặn Captcha (Captcha Intercept)**:
Sàn chặn dữ liệu bằng thử thách xác minh (thanh trượt, puzzle, reCAPTCHA). Thứ tự xử lý: dùng cookie sẵn có; nếu trang vẫn bị chặn, tự kéo thanh trượt mô phỏng người thật; rồi chờ tiện ích NopeCHA trong trình duyệt tối đa 15 giây. Thất bại thì coi là Lỗi sàn diện rộng.
_Avoid_: Bot block, rate limit

**Hạn ngạch giải mã (Solver Quota)**:
Số lượt NopeCHA giải captcha còn lại: 10 lượt mỗi ngày với tiện ích miễn phí không cần khóa API, hoặc số dư tài khoản khi có khóa API. Lệnh Telegram cho xem số còn lại.
_Avoid_: Số lần cào, giới hạn request

**Lỗi sàn diện rộng (Platform-Wide Block)**:
Sự cố cấp toàn sàn (phiên hết hạn, captcha không giải được, lỗi xác thực của cổng API) khiến hệ thống dừng quét phần còn lại của sàn đó trong chu kỳ. Phân biệt với lỗi của một link cá biệt, chỉ bỏ qua link đó.
_Avoid_: Tính lỗi sàn vào số lỗi của từng sản phẩm

**Cảnh báo lỗi kép (Dual Failure Alert)**:
Cảnh báo khẩn gửi admin chỉ khi cả cookie lẫn bộ giải captcha cùng thất bại, nói rõ phiên hết hạn hay hết lượt giải. Không gửi khi quét vẫn thành công nhờ cookie.
_Avoid_: Báo hết lượt khi vẫn cào được

**Phục hồi phiên (Session Recovery)**:
Khi tầng quét nhanh gặp phiên hết hạn hoặc captcha, hệ thống chuyển sang trình duyệt đầy đủ để giải thử thách và quét tiếp. Hệ thống không tự đăng nhập lại và không tự lưu cookie mới: cookie hết hạn thật sự thì admin phải cấp lại.
_Avoid_: Tự làm mới cookie

## Phân hệ khám phá (hiện đang tắt)

**Tạm dừng quét phân hệ tự động (Subsystem Scan Suspension)**:
Trạng thái hiện tại: quét nền theo từ khóa, siêu sale, lỗi giá và TMALL đều tắt qua Cài đặt, tab tương ứng ẩn khỏi dashboard, không gửi Telegram từ các phân hệ này. Toàn bộ tài nguyên và hạn ngạch captcha dành cho sản phẩm theo dõi. Bật lại bằng một công tắc trong Cài đặt, không cần triển khai lại.
_Avoid_: Sửa code để dừng một phân hệ

**Khám phá và Theo dõi (Discover & Track)**:
Người dùng nhập từ khóa, hệ thống tìm trên sàn, lấy tối đa 4 ứng viên và đưa đúng một sản phẩm rẻ nhất (theo giá thực trả) vào danh sách theo dõi.
_Avoid_: Top 5, cào theo từ khóa

**Theo dõi theo từ khóa (Keyword Tracking)**:
Định kỳ tìm sản phẩm theo từ khóa với bộ lọc xuất xứ, nơi gửi, loại shop, dịch vụ (riêng Lazada có 14 nhãn dịch vụ và khuyến mãi); sản phẩm không đạt được ghi nhớ 7 ngày để không tải lại. Quét nền hiện đang tắt; tìm thủ công vẫn dùng được.
_Avoid_: Cào từ khóa ồ ạt

**So sánh giá đa shop (Cross-Shop Comparison)**:
Đối chiếu cùng một sản phẩm giữa các shop bán chạy trên một sàn theo giá thực trả của biến thể còn hàng để chọn shop rẻ nhất.
_Avoid_: Crawl đa shop

**So sánh giá liên sàn (Cross-Platform Comparison)**:
Tìm cùng một món trên cả Shopee và Lazada, so giá thực trả, chỉ ra sàn rẻ hơn.
_Avoid_: Check giá chéo

**Siêu Sale và Flash Sale (Mega Sale)**:
Phân hệ thu thập deal từ trang Flash Sale của Lazada và các đợt siêu sale, gắn chiến dịch, lọc rác giá rẻ, hiển thị ở tab riêng. Hiện chỉ cào khi người dùng bấm nút và không phát cảnh báo Telegram.
_Avoid_: Tab khuyến mãi

**Dọn dẹp rác Flash Sale (Purge Junk Flash Sale)**:
Xóa vĩnh viễn sản phẩm Flash Sale thu thập tự động có giá dưới Ngưỡng giá trị thật tối thiểu, không bao giờ chạm sản phẩm theo dõi.
_Avoid_: Xóa nhầm link người dùng

**Kênh TMALL Trợ Giá (TMALL Subsidy Channel)**:
Chuyên trang trợ giá sâu của Lazada cho hàng chính hãng, được cào vào tab riêng với bộ lọc ngành hàng điện tử và khoảng giá. Hiện đang tắt.
_Avoid_: Flash sale thường

**Sản phẩm lỗi giá (Price Error Product)**:
Sản phẩm người bán đặt nhầm giá (thiếu số 0, nhầm đơn vị, nhầm giá phụ kiện) khiến giá giảm từ 65% trở lên so với giá trị thật. Nghi vấn được quét lại sau 2 phút để xác nhận, rồi gửi admin duyệt trước khi đăng kênh. Phân hệ hiện đang tắt.
_Avoid_: Deal giảm giá thông thường

**Duyệt đăng kênh quản trị (Admin Approval)**:
Admin xem deal nghi lỗi giá trong chat riêng với nút Mua ngay, Đăng lên kênh, Bỏ qua; không gì được tự động đăng lên kênh công khai.
_Avoid_: Tự động đăng lỗi giá
