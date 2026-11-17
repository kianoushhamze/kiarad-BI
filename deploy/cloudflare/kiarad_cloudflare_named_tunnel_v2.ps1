# ============================================================
#  KIARAD x Cloudflare Named Tunnel - v2 (stage 20261114)
#  panel.DOMAIN -> 127.0.0.1:3300   shop.DOMAIN -> 127.0.0.1:8190
#  gps.DOMAIN   -> 127.0.0.1:5055   (optional, Traccar)
#  The current Quick Tunnel is NOT touched; stop it yourself
#  only after the permanent addresses are verified.
#  Run (Windows PowerShell 5.1):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\kiarad_cloudflare_named_tunnel_v2.ps1
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; Read-Host 'Enter to close'; exit 1 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Warn 'Admin (UAC) is required - a new window will open.'
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$TunnelName = 'kiarad-stage'
$Home2 = "$env:USERPROFILE\.cloudflared"
$SvcDir = "$env:ProgramData\cloudflared"
$LogDir = "$SvcDir\logs"

Step '1. Domain'
Write-Host 'Prerequisite: domain added to Cloudflare and status = Active (nameservers changed at the registrar).'
$DOMAIN = (Read-Host 'Domain [default: kiaradhealer.ir]').Trim().ToLower() -replace '^https?://','' -replace '/$',''
if (-not $DOMAIN) { $DOMAIN = 'kiaradhealer.ir' }
if ($DOMAIN -notmatch '^[a-z0-9-]+(\.[a-z0-9-]+)+$') { Fail "Invalid domain: '$DOMAIN'" }
$wantGps = (Read-Host 'Publish gps.DOMAIN for Traccar too? (y/N)').Trim().ToLower() -eq 'y'
Ok "Domain: $DOMAIN"

Step '2. Local services must answer (nothing is changed)'
foreach ($t in @(@('panel',3300),@('shop',8190))) {
    $up = Test-NetConnection -ComputerName 127.0.0.1 -Port $t[1] -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($up) { Ok "$($t[0]) listens on $($t[1])" } else { Warn "$($t[0]) does NOT listen on $($t[1]) - check: docker compose ps" }
}

Step '3. cloudflared binary'
New-Item -ItemType Directory -Force -Path $SvcDir, $LogDir | Out-Null
$exe = "$SvcDir\cloudflared.exe"
if (-not (Test-Path $exe)) {
    $src = 'D:\Kiarad-New\cloudflared.exe'
    if (Test-Path $src) { Copy-Item $src $exe -Force; Ok "Copied from $src" }
    else {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $exe
        Ok 'Downloaded cloudflared'
    }
}
& $exe --version
if ($LASTEXITCODE -ne 0) { Fail 'cloudflared does not run.' }

Step '4. Cloudflare login (browser opens; choose the domain)'
if (-not (Test-Path "$Home2\cert.pem")) {
    & $exe tunnel login
    if (-not (Test-Path "$Home2\cert.pem")) { Fail 'Login incomplete (cert.pem missing).' }
}
Ok 'Logged in.'

Step "5. Tunnel $TunnelName"
$list = (& $exe tunnel list --output json 2>$null | Out-String | ConvertFrom-Json)
$t = $list | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
if (-not $t) {
    & $exe tunnel create $TunnelName
    $list = (& $exe tunnel list --output json | Out-String | ConvertFrom-Json)
    $t = $list | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
} else { Warn 'Tunnel already exists - reusing.' }
if (-not $t) { Fail 'Tunnel id not found.' }
$tid = $t.id
$credSrc = "$Home2\$tid.json"
if (-not (Test-Path $credSrc)) { Fail "Credentials file missing: $credSrc (if the tunnel pre-existed, delete it in Cloudflare and rerun)" }
Copy-Item $credSrc "$SvcDir\$tid.json" -Force
Ok "Tunnel ID: $tid"

Step '6. config.yml'
$gpsBlock = ''
if ($wantGps) { $gpsBlock = "  - hostname: gps.$DOMAIN`r`n    service: http://127.0.0.1:5055`r`n" }
$cfg = "tunnel: $tid`r`ncredentials-file: $SvcDir\$tid.json`r`nprotocol: http2`r`ningress:`r`n" +
       "  - hostname: panel.$DOMAIN`r`n    service: http://127.0.0.1:3300`r`n" +
       "  - hostname: shop.$DOMAIN`r`n    service: http://127.0.0.1:8190`r`n" +
       $gpsBlock + "  - service: http_status:404`r`n"
$cfgPath = "$SvcDir\config.yml"
[System.IO.File]::WriteAllText($cfgPath, $cfg, (New-Object System.Text.UTF8Encoding($false)))
& $exe tunnel --config $cfgPath ingress validate
if ($LASTEXITCODE -ne 0) { Fail 'config.yml is invalid.' }
Ok "Config written: $cfgPath"

Step '7. DNS records'
$hosts = @("panel.$DOMAIN","shop.$DOMAIN"); if ($wantGps) { $hosts += "gps.$DOMAIN" }
foreach ($h in $hosts) {
    $o = (& $exe tunnel route dns $TunnelName $h 2>&1 | Out-String).Trim()
    if ($o -match 'already') { Warn "$h exists (verify in Cloudflare DNS that it points to this tunnel)" } else { Ok $o }
}

Step '8. Windows service (auto start after reboot)'
$svc = Get-Service -Name 'KiaradCloudflared' -ErrorAction SilentlyContinue
if ($svc) { Stop-Service KiaradCloudflared -Force -ErrorAction SilentlyContinue; & sc.exe delete KiaradCloudflared | Out-Null; Start-Sleep 2 }
$bin = "`"$exe`" tunnel --config `"$cfgPath`" --logfile `"$LogDir\cloudflared.log`" run $tid"
New-Service -Name 'KiaradCloudflared' -BinaryPathName $bin -DisplayName 'Kiarad Cloudflare Tunnel' -StartupType Automatic | Out-Null
& sc.exe failure KiaradCloudflared reset= 86400 actions= restart/5000/restart/5000/restart/30000 | Out-Null
Start-Service KiaradCloudflared
Start-Sleep 6
if ((Get-Service KiaradCloudflared).Status -ne 'Running') { Fail "Service not running. See $LogDir\cloudflared.log" }
Ok 'Service KiaradCloudflared is running.'

Step '9. Verification from this machine'
Start-Sleep 5
foreach ($h in @("https://panel.$DOMAIN/login","https://shop.$DOMAIN/buy/")) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $h -TimeoutSec 25; Ok "$h -> HTTP $($r.StatusCode)" }
    catch { Warn "$h -> $($_.Exception.Message)  (DNS may need a few minutes; also test from mobile data)" }
}

Write-Host @"

Done. Next:
 1) Test https://panel.$DOMAIN from mobile data (not office wifi); VPN may interfere.
 2) Keep the old Quick Tunnel until step 1 passes.
 3) Reboot test: restart the server, then check Get-Service KiaradCloudflared
 4) Optional: Cloudflare Zero Trust > Access to put email login in front of the panel.
 Log: $LogDir\cloudflared.log
"@ -ForegroundColor White
Read-Host 'Enter to close'
