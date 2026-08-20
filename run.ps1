[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "Video Factory AI"

python main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] Lỗi khởi động. Chạy setup.ps1 trước."
    Read-Host "Nhấn Enter để thoát"
}
