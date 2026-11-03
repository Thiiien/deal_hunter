@echo off
chcp 65001 >nul
title Deal Hunter - Chrome Crawler Runner

echo ========================================================
echo  DEAL HUNTER - KHOI CHAY CHROME THAT (CDP REMOTE DEBUG)
echo ========================================================
echo.

set "CHROME_PATH="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
if "%CHROME_PATH%"=="" if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if "%CHROME_PATH%"=="" if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if "%CHROME_PATH%"=="" (
    echo [LOI] Khong tim thay Google Chrome tren may tinh!
    echo Vui long cai dat Google Chrome.
    pause
    exit /b 1
)

set "PROFILE_DIR=%~dp0data\chrome_profile"
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

echo [OK] Tim thay Chrome: "%CHROME_PATH%"
echo [OK] Thu muc Profile: "%PROFILE_DIR%"
echo [OK] Cong CDP debug: 9222
echo.
echo ========================================================
echo HUONG DAN:
echo 1. Chrome se mo ra voi Profile doc lap.
echo 2. Dang nhap Shopee / Lazada (1 lan duy nhat de luu cookie).
echo 3. Giu cua so Chrome mo de Deal Hunter tu dong crawl.
echo ========================================================
echo.

start "" "%CHROME_PATH%" --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --remote-allow-origins=* --load-extension="%~dp0extensions\nopecha" --user-data-dir="%PROFILE_DIR%" --no-first-run --no-default-browser-check https://shopee.vn https://www.lazada.vn

echo [THANH CONG] Da khoi chay Chrome!
ping 127.0.0.1 -n 4 >nul
