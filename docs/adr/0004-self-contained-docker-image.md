# Docker Image Tự Chủ Hoàn Toàn: Bake Extension, Không Mount Source Code

## Trạng thái

Accepted.

Để container không phụ thuộc vào môi trường máy host, toàn bộ bootstrap được thực hiện trong Dockerfile: cài `requirements.txt`, `pip install -e .` (pyproject.toml tối giản để `src/deal_hunter/` được nhận dạng đúng), và tải NopeCHA extension v0.6.1 (`chromium.zip` từ GitHub releases) vào `/app/extensions/nopecha` khi build image. Chỉ có `./data` (SQLite + browser profile) và `.env` (secrets) được mount từ host; source code và extension được bake vào image. Cập nhật code = `docker compose up -d --build`, không cần hot-reload.

## Considered Options

- **Mount source code vào container** (dev-friendly): dễ sửa code không cần rebuild, nhưng thư mục `extensions/` trên host còn trống sẽ ghi đè extension đã bake, phá vỡ crawler ngay lần chạy đầu.
- **Tải NopeCHA lúc container start (entrypoint)**: extension luôn mới nhất nhưng container start chậm và lỗi mạng = không khởi động được.
- **Bake mọi thứ vào image, chỉ mount data và secrets** *(đã chọn)*: môi trường ổn định, reproducible, không phụ thuộc mạng khi chạy.

## Consequences

Pin cứng `NOPECHA_VERSION=0.6.1` trong Dockerfile; nâng version = sửa 1 dòng `ARG` rồi rebuild. Ba process (Flask web, Telegram bot, scheduler) chạy trong cùng 1 Python process qua `threading` trong `run.py`, không dùng supervisord. Base image: `mcr.microsoft.com/playwright/python:v1.48.0-noble`, Python 3.12, `shm_size: 2gb`.
