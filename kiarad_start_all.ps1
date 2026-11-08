# KIARAD one-click stack start (docker -> postgres -> backend -> frontend)
$ErrorActionPreference = "Continue"
Set-Location "D:\project\kiaradbi"
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  KIARAD - one-click stack start" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "`n[1/4] Docker engine..." -ForegroundColor Cyan
docker ps 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "  engine down - launching Docker Desktop..."
  $desktopCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"),
    "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  )
  $desktopPath = $desktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($desktopPath) {
    Start-Process -FilePath $desktopPath -WindowStyle Hidden
  } else {
    Write-Host "  داکر دسکتاپ پیدا نشد؛ نصبش کن یا دستی بازش کن" -ForegroundColor Red
    Read-Host "Enter to close"
    exit 1
  }
  $ready = $false
  foreach ($i in 1..24) {
    Start-Sleep -Seconds 5
    docker ps 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Write-Host "  waiting for engine... (attempt $i/24)"
  }
  if (-not $ready) { Write-Host "  ENGINE DID NOT COME UP - open Docker Desktop manually" -ForegroundColor Red; Read-Host "Enter to close"; exit 1 }
} else { Write-Host "  already up" }
Write-Host "  DOCKER_OK" -ForegroundColor Green

Write-Host "`n[2/4] Postgres container..." -ForegroundColor Cyan
docker compose up -d postgres | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  پُستگرس اجرا نشد؛ تنظیمات پروژه را بررسی کن" -ForegroundColor Red; Read-Host "Enter to close"; exit 1 }
$pg = $null; $t = 0
while (-not $pg -and $t -lt 12) {
  Start-Sleep -Seconds 5
  $pg = Get-NetTCPConnection -State Listen -LocalPort 5432 -ErrorAction SilentlyContinue
  $t++
  if (-not $pg) { Write-Host "  waiting for port 5432... (attempt $t/12)" }
}
if ($pg) { Write-Host "  POSTGRES_OK" -ForegroundColor Green } else { Write-Host "  POSTGRES FAILED - run: docker logs kiarad-postgres" -ForegroundColor Red; Read-Host "Enter to close"; exit 1 }

Write-Host "`n[3/4] Backend (port 8000)..." -ForegroundColor Cyan
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
  Write-Host "  already listening"
} else {
  Write-Host "  starting backend..."
  Start-Process -WindowStyle Hidden -FilePath "D:\project\kiaradbi\.venv\Scripts\python.exe" -WorkingDirectory "D:\project\kiaradbi" -ArgumentList @('-m','uvicorn','api:app','--host','127.0.0.1','--port','8000','--env-file','.env') -RedirectStandardOutput "D:\project\kiaradbi\backend_service.log" -RedirectStandardError "D:\project\kiaradbi\backend_service_error.log"
  $t = 0
  while (-not (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) -and $t -lt 12) {
    Start-Sleep -Seconds 5; $t++
    Write-Host "  waiting for port 8000... (attempt $t/12)"
  }
}
$beOk = $false
try { $h = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop; $beOk = ($h.StatusCode -eq 200) } catch {}
if ($beOk) { Write-Host "  BACKEND_OK" -ForegroundColor Green } else { Write-Host "  BACKEND health FAILED - check backend_service.log" -ForegroundColor Yellow }

Write-Host "`n[4/4] Frontend (port 3000)..." -ForegroundColor Cyan
if (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) {
  Write-Host "  already listening"
} else {
  Write-Host "  starting frontend..."
  Push-Location "D:\project\kiaradbi\kiarad-dashboard"
  try {
    & node scripts/prepare-standalone.mjs
    if ($LASTEXITCODE -ne 0) { throw "آماده‌سازی نسخهٔ مستقل انجام نشد؛ ابتدا داشبورد را بسازید." }
    $panelPreviousHostname = $env:HOSTNAME
    $panelPreviousPort = $env:PORT
    try {
      $env:HOSTNAME = "0.0.0.0"
      $env:PORT = "3000"
      Start-Process -WindowStyle Hidden -FilePath (Get-Command node).Source -WorkingDirectory "D:\project\kiaradbi\kiarad-dashboard" -ArgumentList @('.next/standalone/server.js') -RedirectStandardOutput "D:\project\kiaradbi\frontend.log" -RedirectStandardError "D:\project\kiaradbi\frontend_error.log"
    } finally { $env:HOSTNAME=$panelPreviousHostname; $env:PORT=$panelPreviousPort }
  } finally { Pop-Location }
  $t = 0
  while (-not (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) -and $t -lt 18) {
    Start-Sleep -Seconds 5; $t++
    Write-Host "  waiting for port 3000... (attempt $t/18)"
  }
}
$feOk = $false
try { $r = Invoke-WebRequest -Uri "http://localhost:3000/login" -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop; $feOk = ($r.StatusCode -eq 200) } catch {}
if ($feOk) { Write-Host "  FRONTEND_OK" -ForegroundColor Green } else { Write-Host "  FRONTEND not answering yet - give the browser 30 more seconds" -ForegroundColor Yellow }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
if ($beOk -and $feOk) { Write-Host "  ALL GREEN - kiarad is up" -ForegroundColor Green } else { Write-Host "  partially up - see messages above" -ForegroundColor Yellow }
Write-Host "  Dashboard : http://localhost:3000/management"
Write-Host "  Login     : http://localhost:3000/login"
Write-Host "=========================================="
Write-Host "`nclosing in 15s..."
Start-Sleep -Seconds 15
