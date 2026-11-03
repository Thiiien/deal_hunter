# Đóng gói hệ thống trên Docker với Playwright và Volume Persistence

## Trạng thái

Accepted, bị thay thế bởi ADR 0004: image ghim `v1.48.0-noble`, extension đóng gói sẵn trong image, chỉ mount `./data`, `.env` qua `env_file`.

Để đơn giản hóa việc triển khai và đảm bảo môi trường thực thi đồng nhất giữa các máy chủ, chúng tôi chọn đóng gói toàn bộ hệ thống Deal Hunter vào một Docker container duy nhất quản lý bởi docker-compose. Container sử dụng image chính thức `mcr.microsoft.com/playwright/python`, thiết lập `shm_size: 2gb` để tránh lỗi tràn bộ nhớ của Chromium, và ánh xạ các volume `./data` cùng `./extensions` ra máy chủ host nhằm đảm bảo cơ sở dữ liệu SQLite, phiên duyệt web và cấu hình extension được lưu trữ bền vững vĩnh viễn qua các lần cập nhật container.
