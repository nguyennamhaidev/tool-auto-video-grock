[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "Video Factory AI - Setup"

Write-Host ""
Write-Host "==================================================="
Write-Host "  VIDEO FACTORY AI - CAI DAT"
Write-Host "==================================================="
Write-Host ""

python --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[LOI] Python chua duoc cai. Tai tai https://python.org"
    Read-Host "Nhấn Enter để thoát"
    exit 1
}

Write-Host "[1/4] Cai thu vien Python..."
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[LOI] Khong cai duoc thu vien."
    Read-Host "Nhấn Enter để thoát"
    exit 1
}

Write-Host ""
Write-Host "[2/4] Cai Playwright browser (Chromium)..."
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Host "[LOI] Khong cai duoc Playwright."
    Read-Host "Nhấn Enter để thoát"
    exit 1
}

Write-Host ""
Write-Host "[3/4] Tao thu muc..."
@("assets\music", "assets\characters", "output", "temp") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}

Write-Host ""
Write-Host "[4/4] Xong!"
Write-Host ""
Write-Host "==================================================="
Write-Host "  CAI DAT HOAN TAT"
Write-Host ""
Write-Host "  Buoc tiep theo:"
Write-Host "  1. Bo nhac nen vao:    assets\music\"
Write-Host "  2. Bo anh nhan vat:    assets\characters\"
Write-Host "  3. Chay tool:          run.ps1"
Write-Host "  4. Dang nhap ChatGPT va Grok khi trinh duyet mo"
Write-Host "     (chi can dang nhap 1 lan, tool tu nho)"
Write-Host "==================================================="
Write-Host ""
Read-Host "Nhấn Enter để thoát"
