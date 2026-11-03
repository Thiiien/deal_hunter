@echo off
chcp 65001 >nul
title Deal Hunter - Săn Deal Tự Động
echo ========================================================
echo   DEAL HUNTER - KHỞI ĐỘNG HỆ THỐNG
echo ========================================================
echo.
echo [1/3] Đang dừng Docker nếu đang chiếm cổng 5000...
docker stop deal_hunter-deal-hunter-1 >nul 2>&1
echo [2/3] Đang mở Dashboard trên trình duyệt...
start http://127.0.0.1:5000
echo [3/3] Đang chạy Deal Hunter trên Windows...
echo.
python run.py
pause
