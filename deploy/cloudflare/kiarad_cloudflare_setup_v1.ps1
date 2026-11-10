# ============================================================
#  KIARAD x Cloudflare Tunnel  -  setup v1
#  Goal: publish panel.kiarad-domain + shop.kiarad-domain
#        from the office PC (behind Irancell CGNAT) with zero
#        open ports and zero monthly cost.
#  Run:  PowerShell as normal user -> script self-elevates.
#        Browser opens once for Cloudflare login.
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; Read-Host 'Enter to close'; exit 1 }

# ---- self-elevate (service install needs admin) ----
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Warn 'اجازهٔ مدیر (UAC) لازم است — پنجرهٔ جدید باز می‌شود.'
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

# ---- step 1: domain ----
Step '۱. دامنه'
Write-Host 'پیش‌نیاز: دامنه خریداری شده، در اکانت رایگان Cloudflare اضافه شده و'
Write-Host 'Nameserverهای رجیسترار به کلادفلر تغییر کرده (وضعیت Active).'
$DOMAIN = (Read-Host 'دامنه را وارد کنید (مثلاً kiaradshafa.ir)').Trim() -replace '^https?://','' -replace '/$',''
if (-not $DOMAIN -or $DOMAIN -notmatch '^[a-z0-9.-]+\.[a-z]{2,}$') { Fail "دامنهٔ نامعتبر: '$DOMAIN'" }
Ok "دامنه: $DOMAIN"

# ---- step 2: cloudflared binary ----
Step '۲. نصب cloudflared'
$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    try {
        winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements | Out-Null
    } catch { Warn 'winget کار نکرد — دانلود مستقیم.' }
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        $dir = "$env:ProgramData\cloudflared"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile "$dir\cloudflared.exe"
        [Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + $dir, 'Machine')
        $env:Path += ";$dir"
    }
}
& cloudflared --version | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'cloudflared نصب نشد.' }
Ok ('cloudflared آماده است.')

# ---- step 3: login (browser) ----
Step '۳. لاگین کلادفلر (مرورگر باز می‌شود)'
Write-Host 'در صفحهٔ بازشده، دامنه‌ی'  -NoNewline; Write-Host " $DOMAIN " -NoNewline -ForegroundColor Yellow; Write-Host 'را انتخاب و تأیید کن.'
& cloudflared tunnel login
if (-not (Test-Path "$env:USERPROFILE\.cloudflared\cert.pem")) { Fail 'لاگین کامل نشد (cert.pem ساخته نشد).' }
Ok 'لاگین انجام شد.'

# ---- step 4: create tunnel ----
Step '۴. ساخت تانل kiarad'
$createOut = (& cloudflared tunnel create kiarad 2>&1 | Out-String)
if ($createOut -match 'already exists') { Warn 'تانل kiarad از قبل وجود دارد — ادامه.' } else { Ok $createOut.Trim() }
$tid = (& cloudflared tunnel list --output json | ConvertFrom-Json |
        Where-Object { $_.name -eq 'kiarad' } | Select-Object -First 1).id
if (-not $tid) { Fail 'شناسهٔ تانل پیدا نشد.' }
Ok "Tunnel ID: $tid"

# ---- step 5: local ports + config.yml ----
Step '۵. تنظیم مسیرهای محلی'
$panelPort = 3100
try {
    if (Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -InformationLevel Quiet -WarningAction SilentlyContinue) { $panelPort = 3000 }
} catch {}
Ok "پورت پنل: $panelPort   (سایت: 8090)"
$cfg = @"
tunnel: kiarad
credentials-file: C:\Users\$env:USERNAME\.cloudflared\$tid.json
ingress:
  - hostname: panel.$DOMAIN
    service: http://localhost:$panelPort
  - hostname: shop.$DOMAIN
    service: http://localhost:8090
  - service: http_status:404
"@
$cfgPath = "$env:USERPROFILE\.cloudflared\config.yml"
[System.IO.File]::WriteAllText($cfgPath, $cfg, (New-Object System.Text.UTF8Encoding($false)))
Ok "config.yml نوشته شد: $cfgPath"

# ---- step 6: DNS routes ----
Step '۶. ساخت رکوردهای DNS'
$r1 = (& cloudflared tunnel route dns kiarad "panel.$DOMAIN" 2>&1 | Out-String)
if ($r1 -match 'already exist') { Warn 'رکورد panel از قبل موجود است.' } else { Ok $r1.Trim() }
$r2 = (& cloudflared tunnel route dns kiarad "shop.$DOMAIN" 2>&1 | Out-String)
if ($r2 -match 'already exist') { Warn 'رکورد shop از قبل موجود است.' } else { Ok $r2.Trim() }

# ---- step 7: windows service ----
Step '۷. نصب سرویس ویندوز (اجرای خودکار همیشگی)'
$sysProf = "$env:WINDIR\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Force -Path $sysProf | Out-Null
Copy-Item "$env:USERPROFILE\.cloudflared\*" $sysProf -Force
$svc = Get-Service cloudflared -ErrorAction SilentlyContinue
if ($svc) { & cloudflared service uninstall 2>$null | Out-Null; Start-Sleep 2 }
& cloudflared service install | Out-Null
Start-Service cloudflared
Start-Sleep 3
$st = (Get-Service cloudflared).Status
if ($st -ne 'Running') { Fail "سرویس بالا نیامد (وضعیت: $st) — لاگ: Event Viewer > cloudflared" }
Ok 'سرویس cloudflared در حال اجراست.'

# ---- step 8: summary ----
Step '۸. جمع‌بندی'
Write-Host @"
حالا دو سرویس محلی باید روشن باشند که تانل چیزی برای ارسال داشته باشد:

  پنل داشبورد:   powershell -NoProfile -ExecutionPolicy Bypass -File D:\project\kiaradbi\start-kiarad-frontend.ps1
  سایت همکاران:  powershell -NoProfile -ExecutionPolicy Bypass -File .\start-kiaradhealer-site.ps1

سپس از هر جای ایران (اینترنت موبایل هم کافی است):
  https://panel.$DOMAIN
  https://shop.$DOMAIN

اگر صفحهٔ ورود Cloudflare (Access) برای پنل خواستی، بگو تا راهنمایی کنم.
"@ -ForegroundColor White
Read-Host 'پایان — Enter بزن'
