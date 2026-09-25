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
  Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
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
$st = docker inspect -f "{{.State.Running}}" kiarad-postgres 2>$null
if ($st -ne "true") { docker start kiarad-postgres | Out-Null; Write-Host "  container started" } else { Write-Host "  already running" }
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
  Start-Process -WindowStyle Minimized -FilePath "cmd.exe" -ArgumentList '/c cd /d D:\project\kiaradbi && .venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000 --env-file .env >> backend_service.log 2>&1'
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
  Start-Process -WindowStyle Minimized -FilePath "cmd.exe" -ArgumentList '/c cd /d D:\project\kiaradbi\kiarad-dashboard && npm run dev -- -H 0.0.0.0 > frontend.log 2>&1'
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
