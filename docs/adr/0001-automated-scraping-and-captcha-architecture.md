# Kiến trúc thu thập dữ liệu tự động với Playwright, NopeCHA Extension và Giám sát hạn ngạch

## Trạng thái

Accepted, bị thay thế một phần: hạn ngạch NopeCHA miễn phí là 10 lượt/ngày (ADR 0048); cảnh báo hạn ngạch chỉ gửi khi lỗi kép (ADR 0050); phiên lưu bằng cookie từng sàn (ADR 0006, 0017); quét hai tầng (ADR 0060); headless trong Docker được tái khẳng định ở ADR 0064.

Để vận hành hệ thống Deal Hunter tự động hoàn toàn mà không cần can thiệp thủ công, chúng tôi chọn Playwright chạy chế độ Persistent Context (`--headless=new`) kết hợp nạp trực tiếp NopeCHA Extension vào nhân trình duyệt, cơ chế lưu phiên (session persistence), bộ ngắt mạch (circuit breaker) và hệ thống theo dõi hạn ngạch (quota monitor). Quyết định này giúp loại bỏ hoàn toàn mã nguồn xử lý ảnh và giả lập chuột phức tạp, tận dụng 100 lượt giải captcha miễn phí mỗi ngày từ NopeCHA, đồng thời chủ động gửi cảnh báo khẩn cấp đến Telegram của người quản trị khi số dư lượt giải sắp hết để kịp thời nạp thêm hoặc nâng cấp.
