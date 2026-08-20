@echo off
title Video Factory AI - Setup

echo.
echo ===================================================
echo   VIDEO FACTORY AI - CAI DAT
echo ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai. Tai tai https://python.org
    pause
    exit /b 1
)

echo [1/4] Cai thu vien Python...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] Khong cai duoc thu vien.
    pause
    exit /b 1
)

echo.
echo [2/4] Cai Playwright browser (Chromium)...
python -m playwright install chromium
if errorlevel 1 (
    echo [LOI] Khong cai duoc Playwright.
    pause
    exit /b 1
)

echo.
echo [3/4] Tao thu muc...
if not exist "assets\music"      mkdir "assets\music"
if not exist "assets\characters" mkdir "assets\characters"
if not exist "output"            mkdir "output"
if not exist "temp"              mkdir "temp"

echo.
echo [4/4] Xong!
echo.
echo ===================================================
echo   CAI DAT HOAN TAT
echo.
echo   Buoc tiep theo:
echo   1. Bo nhac nen vao:    assets\music\
echo   2. Bo anh nhan vat:    assets\characters\
echo   3. Chay tool:          run.bat
echo   4. Dang nhap ChatGPT va Grok khi trinh duyet mo
echo      (chi can dang nhap 1 lan, tool tu nho)
echo ===================================================
echo.
pause
