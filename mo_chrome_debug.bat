@echo off
chcp 65001 >nul
title Chrome Grok Tool (Port 9222)

set "C1=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "C2=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set "CHROME="
if exist "%C1%" set "CHROME=%C1%"
if "%CHROME%"=="" if exist "%C2%" set "CHROME=%C2%"
if "%CHROME%"=="" (echo KHONG TIM THAY chrome.exe & pause & exit /b 1)

:: Thu muc data rieng cho tool – KHONG dung cung Chrome chinh
set "UDATA=%~dp0.browser_data\grok_chrome"

:: Kiem tra port 9222 da mo chua
netstat -an | findstr ":9222" >nul 2>&1
if %errorlevel%==0 (
    echo ========================================
    echo  Chrome Grok da chay (port 9222)!
    echo  Bay gio chay Tool va bam BAT DAU.
    echo ========================================
    timeout /t 4
    exit /b 0
)

echo ========================================
echo  MO CHROME RIENG CHO GROK TOOL
echo  (Chrome chinh cua ban KHONG bi dong)
echo ========================================
echo.

:: Mo Chrome moi voi data dir rieng – chay song song voi Chrome chinh
start "" "%CHROME%" ^
    --remote-debugging-port=9222 ^
    "--user-data-dir=%UDATA%" ^
    --no-first-run ^
    --no-default-browser-check ^
    --window-size=1200,900 ^
    https://grok.com

echo  Dang mo Chrome Grok...
timeout /t 6 >nul

netstat -an | findstr ":9222" >nul 2>&1
if %errorlevel%==0 (
    echo ========================================
    echo  [OK] Chrome Grok san sang!
    echo.
    echo  Lan dau: dang nhap X/Grok trong cua so moi
    echo  Lan sau: tu dong dung lai session
    echo.
    echo  Cua so Chrome chinh cua ban van nguyen!
    echo ========================================
) else (
    echo  [!] Thu lai: chay file nay lan nua
)
timeout /t 8
