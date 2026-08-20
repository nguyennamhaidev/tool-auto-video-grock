@echo off
chcp 65001 >nul
title Video Factory AI
python main.py
if errorlevel 1 (
    echo.
    echo [!] Lỗi khởi động. Chạy setup.bat trước.
    pause
)
