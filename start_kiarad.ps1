# =====================================================================
#  Kiarad - راه‌اندازی کامل
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"

Write-Host "`n=== 1. Docker ===" -ForegroundColor Cyan
Set-Location $root
docker compose up -d postgres
Start-Sleep 8
docker ps --format "{{.Names}}: {{.Status}}"

Write-Host "`n=== 2. توقف uvicorn قدیمی ===" -ForegroundColor Cyan
$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }

Write-Host "`n=== 3. بک‌اند (پنجره جدید) ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Path "$root\logs" -Force | Out-Null
$py = "$root\.venv\Scripts\python.exe"
$bc = "Set-Location '$root'; & '$py' -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload --env-file .env"
Start-Process powershell -ArgumentList "-NoExit","-Command",$bc -WindowStyle Normal
Write-Host "منتظر بک‌اند..." -ForegroundColor Yellow
Start-Sleep 12

try {
  $h = Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 5
  Write-Host "OK Backend: $($h.status) / $($h.database)" -ForegroundColor Green
} catch {
  Write-Host "FAIL: Backend بالا نیامد" -ForegroundColor Red
}

Write-Host "`n=== 4. فرانت‌اند (پنجره جدید) ===" -ForegroundColor Cyan
$c3 = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($c3) { Stop-Process -Id $c3.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }
$fc = "Set-Location '$root\kiarad-dashboard'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit","-Command",$fc -WindowStyle Normal
Write-Host "منتظر فرانت..." -ForegroundColor Yellow
Start-Sleep 20

try {
  $f = Invoke-WebRequest http://127.0.0.1:3000/ -TimeoutSec 8 -UseBasicParsing
  Write-Host "OK Frontend: $($f.StatusCode)" -ForegroundColor Green
} catch {
  Write-Host "FAIL: Frontend بالا نیامد" -ForegroundColor Red
}

Write-Host "`n=========================================" -ForegroundColor Magenta
Write-Host "  پنل:     http://localhost:3000/login" -ForegroundColor White
Write-Host "  API:     http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  pgAdmin: ابزار اختیاری است و به‌صورت پیش‌فرض اجرا نمی‌شود" -ForegroundColor White
Write-Host "  ورود:    با حساب مدیر در صفحه ورود انجام شود" -ForegroundColor White
Write-Host "=========================================" -ForegroundColor Magenta
