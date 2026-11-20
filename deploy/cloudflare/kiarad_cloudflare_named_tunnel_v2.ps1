# ============================================================
# KIARAD Cloudflare Named Tunnel - hardened installer
# Windows PowerShell 5.1; run as Administrator.
# No automatic "latest" download, tunnel deletion or service deletion.
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { throw $m }

function Protect-Path([string]$Path, [switch]$Directory) {
    if (-not (Test-Path -LiteralPath $Path)) { Fail "Security path missing: $Path" }
    if ($Directory) {
        & icacls.exe $Path /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T /C | Out-Null
    } else {
        & icacls.exe $Path /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" /C | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { Fail "Could not restrict ACL: $Path" }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    Start-Process -FilePath powershell.exe -Verb RunAs -ArgumentList $arguments
    exit
}

$TunnelName = 'kiarad-stage'
$Home2 = Join-Path $env:USERPROFILE '.cloudflared'
$SvcDir = Join-Path $env:ProgramData 'cloudflared'
$LogDir = Join-Path $SvcDir 'logs'

Step '1. Domain and optional GPS'
$DOMAIN = (Read-Host 'Domain [default: kiaradhealer.ir]').Trim().ToLower() -replace '^https?://','' -replace '/$',''
if (-not $DOMAIN) { $DOMAIN = 'kiaradhealer.ir' }
if ($DOMAIN -notmatch '^[a-z0-9-]+(\.[a-z0-9-]+)+$') { Fail "Invalid domain: $DOMAIN" }
$wantGps = (Read-Host 'Publish gps.DOMAIN for Traccar too? (y/N)').Trim().ToLower() -eq 'y'

Step '2. Check local services without changing them'
foreach ($target in @(@('panel',3300),@('shop',8190))) {
    $up = Test-NetConnection 127.0.0.1 -Port $target[1] -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($up) { Ok "$($target[0]) listens on $($target[1])" } else { Warn "$($target[0]) is not listening on $($target[1])" }
}

Step '3. Verify cloudflared binary'
New-Item -ItemType Directory -Force -Path $SvcDir,$LogDir | Out-Null
Protect-Path $SvcDir -Directory
Protect-Path $LogDir -Directory
$exe = Join-Path $SvcDir 'cloudflared.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    $candidates = @('D:\Kiarad-New\cloudflared.exe',(Join-Path $env:ProgramFiles 'cloudflared\cloudflared.exe'))
    $source = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $source) { Fail "Place an official signed cloudflared.exe at $exe. Unverified automatic downloads are disabled." }
    Copy-Item -LiteralPath $source -Destination $exe
}
$signature = Get-AuthenticodeSignature -FilePath $exe
if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(?i)Cloudflare') {
    Fail 'cloudflared Authenticode signature is invalid or publisher is not Cloudflare.'
}
Protect-Path $exe
$version = (& $exe --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { Fail 'cloudflared execution failed.' }
Ok "Signed binary verified: $version"

Step '4. Cloudflare login'
New-Item -ItemType Directory -Force -Path $Home2 | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $Home2 'cert.pem'))) {
    & $exe tunnel login
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $Home2 'cert.pem'))) { Fail 'Cloudflare login did not complete.' }
}

Step '5. Reuse existing tunnel; do not delete or recreate it'
$list = (& $exe tunnel list --output json 2>$null | Out-String)
if ($LASTEXITCODE -ne 0) { Fail 'Could not list tunnels; no tunnel changed.' }
try { $tunnels = @($list | ConvertFrom-Json) } catch { Fail 'Invalid tunnel-list JSON.' }
$tunnel = $tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
if (-not $tunnel) {
    & $exe tunnel create $TunnelName
    if ($LASTEXITCODE -ne 0) { Fail 'Tunnel creation failed.' }
    $list = (& $exe tunnel list --output json 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0) { Fail 'Tunnel created but listing failed; do not create another.' }
    try { $tunnels = @($list | ConvertFrom-Json) } catch { Fail 'Invalid tunnel-list JSON after create.' }
    $tunnel = $tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
} else { Warn 'Reusing existing named tunnel.' }
if (-not $tunnel) { Fail 'Tunnel ID not found.' }
$tid = [string]$tunnel.id
$credSource = Join-Path $Home2 ($tid + '.json')
if (-not (Test-Path -LiteralPath $credSource -PathType Leaf)) {
    Fail "Credentials missing for existing tunnel $tid. Retrieve this tunnel's credential securely; do not delete/recreate it."
}
$credDestination = Join-Path $SvcDir ($tid + '.json')
Copy-Item -LiteralPath $credSource -Destination $credDestination -Force
Protect-Path $credDestination

Step '6. Write and validate config'
$newLine = [Environment]::NewLine
$gps = ''
if ($wantGps) { $gps = "  - hostname: gps.$DOMAIN" + $newLine + "    service: http://127.0.0.1:5055" + $newLine }
$config = "tunnel: $tid" + $newLine + "credentials-file: $credDestination" + $newLine +
          "protocol: http2" + $newLine + "ingress:" + $newLine +
          "  - hostname: panel.$DOMAIN" + $newLine + "    service: http://127.0.0.1:3300" + $newLine +
          "  - hostname: shop.$DOMAIN" + $newLine + "    service: http://127.0.0.1:8190" + $newLine +
          $gps + "  - service: http_status:404" + $newLine
$configPath = Join-Path $SvcDir 'config.yml'
[IO.File]::WriteAllText($configPath,$config,(New-Object System.Text.UTF8Encoding($false)))
Protect-Path $configPath
& $exe tunnel --config $configPath ingress validate
if ($LASTEXITCODE -ne 0) { Fail 'Ingress validation failed; service not changed.' }

Step '7. DNS routes'
$hosts = @("panel.$DOMAIN","shop.$DOMAIN")
if ($wantGps) { $hosts += "gps.$DOMAIN" }
foreach ($hostName in $hosts) {
    $output = (& $exe tunnel route dns $TunnelName $hostName 2>&1 | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and $output -notmatch '(?i)already exists|already routed') { Fail "DNS route failed for $hostName : $output" }
    if ($output -match '(?i)already exists|already routed') { Warn "Existing DNS route for $hostName; verify it targets $tid." } else { Ok $output }
}

Step '8. Preserve and reconfigure Windows service'
$log = Join-Path $LogDir 'cloudflared.log'
$binaryPath = '"' + $exe + '" tunnel --config "' + $configPath + '" --logfile "' + $log + '" run ' + $tid
$service = Get-CimInstance Win32_Service -Filter "Name='KiaradCloudflared'" -ErrorAction SilentlyContinue
if ($service) {
    if ($service.State -eq 'Running') { Stop-Service KiaradCloudflared -Force }
    & sc.exe config KiaradCloudflared binPath= $binaryPath start= auto | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'Could not reconfigure existing Windows service.' }
    Set-Service KiaradCloudflared -StartupType Automatic
    Warn 'Existing service preserved and reconfigured; it was not deleted.'
} else {
    New-Service KiaradCloudflared -BinaryPathName $binaryPath -DisplayName 'Kiarad Cloudflare Tunnel' -StartupType Automatic | Out-Null
}
& sc.exe failure KiaradCloudflared reset= 86400 actions= restart/5000/restart/5000/restart/30000 | Out-Null
Start-Service KiaradCloudflared
$running = $false
for ($i=0; $i -lt 12; $i++) {
    if ((Get-Service KiaradCloudflared).Status -eq 'Running') { $running = $true; break }
    Start-Sleep 1
}
if (-not $running) { Fail "Service not running. Inspect $log" }

Step '9. Verify public endpoints'
foreach ($url in @("https://panel.$DOMAIN/login","https://shop.$DOMAIN/buy/")) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 25; Ok "$url -> HTTP $($r.StatusCode)" }
    catch { Warn "$url -> $($_.Exception.Message); test again from mobile data after DNS propagation." }
}
Write-Host "Quick Tunnel was not stopped. Log: $log" -ForegroundColor White
Read-Host 'Enter to close'
