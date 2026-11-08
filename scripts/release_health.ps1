param(
  [string]$FrontendUrl = "http://127.0.0.1:3000/login",
  [string]$BackendUrl = "http://127.0.0.1:8000/health",
  [string]$BackendContainer = "kiarad-backend",
  [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$backendOk = $false
$frontendOk = $false
do {
  try { $backendOk = (Invoke-WebRequest -UseBasicParsing -Uri $BackendUrl -TimeoutSec 5).StatusCode -eq 200 } catch { $backendOk = $false }
  if (-not $backendOk) {
    try { $backendOk = (docker inspect -f "{{.State.Health.Status}}" $BackendContainer 2>$null) -eq "healthy" } catch { $backendOk = $false }
  }
  try { $frontendOk = (Invoke-WebRequest -UseBasicParsing -Uri $FrontendUrl -TimeoutSec 5).StatusCode -eq 200 } catch { $frontendOk = $false }
  if ($backendOk -and $frontendOk) { break }
  Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

$result = [ordered]@{
  checked_at = (Get-Date).ToString("o")
  backend_ok = $backendOk
  frontend_ok = $frontendOk
}
$result | ConvertTo-Json -Compress
if (-not ($backendOk -and $frontendOk)) { exit 1 }
