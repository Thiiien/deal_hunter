# 70. Mở lại tab TMALL trên trang LazTmall Affiliate

Date: 2026-11-05

## Trạng thái

Accepted (Đã thống nhất qua quy trình `/grill-with-docs`). Thay URL nguồn của ADR 0046 (quyết định 1); mở lại một trong bốn phân hệ mà ADR 0055 đã tắt; giữ bộ lọc ngành hàng và khoảng giá của ADR 0046.

## Bối cảnh

1. Người dùng có trang `https://www.lazada.vn/wow/gcp/lazada/channel/vn/affiliate/hFa6ZXcrph` (tiêu đề "LazTmall Affiliate Độc Quyền") và muốn một tab quét trang này.
2. Dò trang ngày 05/11/2026 bằng trình duyệt tạm trong container: cùng khuôn với trang kênh LazMall mà ADR 0046 đang cào (ứng dụng một trang, cuộn vô tận, thẻ có giá, giá gạch, phần trăm giảm). Phần sản phẩm là luồng gợi ý cá nhân hóa (`lzdpagerecommendservice`, 121 mã mỗi lần tải thêm, 90 thẻ sau 4 lần cuộn), ngành hàng lẫn lộn (mỹ phẩm, đồ chơi, pin). Có khối "Thu thập Voucher" riêng cho cộng tác viên.
3. Tab "Lazada TMALL" đã có đủ bảng, nút cào, lọc, sắp xếp, xóa hàng loạt, công tắc và tần suất trong Cài đặt; chỉ đang ẩn và tắt theo ADR 0055. Một lượt cào trang này tốn một lần tải trang, so với 40 lần tải mỗi vòng quét sản phẩm theo dõi.

## Quyết định kiến trúc

1. **Dùng lại tab TMALL, không tạo tab mới.** URL nguồn của bộ cào kênh chuyển sang trang LazTmall Affiliate; trang kênh LazMall cũ bỏ. Nhãn tab, tiêu đề, nút và nhãn Cài đặt đổi thành "LazTmall Affiliate"; mã nguồn `lazada_tmall`, nhãn chiến dịch "TMALL Trợ Giá" và tiền tố tên sản phẩm giữ nguyên để không phải di trú dữ liệu.
2. **Cào thủ công và theo lịch.** Nút "Cào LazTmall Ngay" dùng được ngay. Quét nền bật bằng công tắc sẵn có trong Cài đặt, tần suất 60 phút (giá trị 10 phút đang lưu trong DB được đặt lại). Không gửi Telegram từ tab này; ba phân hệ còn lại của ADR 0055 vẫn tắt.
3. **Giữ bộ lọc.** Chỉ lưu sản phẩm thuộc Thiết bị điện tử hoặc Phụ kiện điện tử trong khoảng giá cấu hình (hiện 100.000₫ đến 30.000.000₫); phần còn lại của feed bỏ qua.
4. **Sản phẩm trong tab không tự thành sản phẩm theo dõi.** Người dùng bấm theo dõi từng món như hiện nay.

5. **Giá thẻ không phải giá sản phẩm (bổ sung 05/11/2026 sau khi người dùng báo giá sai).** Thẻ trong luồng gợi ý mang `skuId` và giá của đúng phân loại đó; cùng một listing bị cào ra 798.000₫ rồi 1.561.000₫ cách nhau 20 phút chỉ vì feed đổi phân loại. Vì vậy giá thẻ chỉ dùng để lọc khoảng giá sơ bộ, không lưu vào lịch sử giá. Sau khi lọc, mỗi món được quét trang sản phẩm bằng luồng quét sẵn có (phân loại rẻ nhất còn hàng theo ADR 0054, có giá gốc thật và tồn kho); mỗi lượt cào quét tối đa 10 món chưa có ảnh giá trong 24 giờ, phần còn lại chờ lượt sau. Món chưa kịp quét không hiện trong tab thay vì hiện giá sai. 189 dòng TMALL cũ (toàn giá thẻ, không có bản ghi biến thể) đã xóa hẳn theo yêu cầu người dùng, không sao lưu.

## Hệ quả

- Người dùng xem được deal điện tử từ trang affiliate ngay trên dashboard; chi phí thêm là một lần tải trang mỗi lượt cào.
- Feed là gợi ý cá nhân hóa: bot thấy theo tài khoản Lazada của nó, có thể khác những gì người dùng thấy trên máy mình; số món điện tử sau lọc mỗi lượt có thể chỉ vài chục.
- Giá trong tab là giá trên thẻ, chưa trừ voucher trong khối "Thu thập Voucher"; voucher affiliate không được lấy.
- Cấu hình: biến `TMALL_*` và công tắc `tmall_scan_enabled` giữ tên cũ.
- Mỗi lượt cào chen tối đa 10 lần quét trang sản phẩm (khoảng 2 phút) vào vòng quét sản phẩm theo dõi, vì hai luồng dùng chung trình duyệt và khóa tuần tự. Cảnh báo deal và thông báo ngừng kinh doanh không gửi cho sản phẩm nguồn LazTmall.
