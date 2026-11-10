# Launch/refresh the KiaradHealer static site server (port 8090)
# Site lives in the repo: <repo>\site-healer  |  server: <repo>\scripts\serve_kiaradhealer.mjs
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-kiaradhealer-site.ps1
param(
    [string]$SiteDir   = "D:\project\kiaradbi\site-healer",
    [string]$ScriptDir = "D:\project\kiaradbi\scripts",
    [int]$Port         = 8090
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path "$SiteDir\index.html")) { Fail "index.html پیدا نشد در: $SiteDir (git pull را چک کن)" }
if (-not (Test-Path "$ScriptDir\serve_kiaradhealer.mjs")) { Fail "serve_kiaradhealer.mjs پیدا نشد در: $ScriptDir" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail 'Node.js نصب نیست.' }

$old = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
       Where-Object { $_.CommandLine -like '*serve_kiaradhealer.mjs*' }
foreach ($p in $old) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Warn ("پروسهٔ قبلی بسته شد (PID {0})" -f $p.ProcessId) }

$env:KIARAD_SITE_DIR  = $SiteDir
$env:KIARAD_SITE_PORT = $Port
Start-Process node -ArgumentList "`"$ScriptDir\serve_kiaradhealer.mjs`"" -WindowStyle Hidden
Start-Sleep 2
try { $code = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 8).StatusCode } catch { $code = 0 }
if ($code -eq 200) { Ok "سایت KiaradHealer روی http://127.0.0.1:$Port بالا آمد (از $SiteDir)" }
else { Fail "سرور جواب نداد (کد: $code) — دستی امتحان کن: node `"$ScriptDir\serve_kiaradhealer.mjs`"" }
