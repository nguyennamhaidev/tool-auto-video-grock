[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "Chrome Grok Tool (Port 9222)"

$C1 = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$C2 = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
$Chrome = $null
if (Test-Path $C1) { $Chrome = $C1 }
elseif (Test-Path $C2) { $Chrome = $C2 }

if (-not $Chrome) {
    Write-Host "KHONG TIM THAY chrome.exe"
    Read-Host "Nhấn Enter để thoát"
    exit 1
}

# Thu muc data rieng cho tool - KHONG dung cung Chrome chinh
$UData = Join-Path $PSScriptRoot ".browser_data\grok_chrome"

# Kiem tra port 9222 da mo chua
$port9222 = netstat -an | Select-String ":9222"
if ($port9222) {
    Write-Host "========================================"
    Write-Host " Chrome Grok da chay (port 9222)!"
    Write-Host " Bay gio chay Tool va bam BAT DAU."
    Write-Host "========================================"
    Start-Sleep -Seconds 4
    exit 0
}

Write-Host "========================================"
Write-Host " MO CHROME RIENG CHO GROK TOOL"
Write-Host " (Chrome chinh cua ban KHONG bi dong)"
Write-Host "========================================"
Write-Host ""

# Mo Chrome moi voi data dir rieng - chay song song voi Chrome chinh
Start-Process $Chrome -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$UData",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1200,900",
    "https://grok.com"
)

Write-Host " Dang mo Chrome Grok..."
Start-Sleep -Seconds 6

$port9222 = netstat -an | Select-String ":9222"
if ($port9222) {
    Write-Host "========================================"
    Write-Host " [OK] Chrome Grok san sang!"
    Write-Host ""
    Write-Host " Lan dau: dang nhap X/Grok trong cua so moi"
    Write-Host " Lan sau: tu dong dung lai session"
    Write-Host ""
    Write-Host " Cua so Chrome chinh cua ban van nguyen!"
    Write-Host "========================================"
} else {
    Write-Host " [!] Thu lai: chay file nay lan nua"
}
Start-Sleep -Seconds 8
