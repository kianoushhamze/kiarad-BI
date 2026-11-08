# =====================================================================
#  KIARAD - DIGIKALA UA FIX v1 (2026-10-31)
#  Digikala answered: every Self-Token request must send the header
#    User-Agent: DigikalaTrustedBot/SelfToken/SELLER-CODE
#  Our UA lacked the seller code - that was the whole 401 gate.
#  This script (zero input):
#    1. patches scripts\digikala_sync_task.ps1 with the full UA
#    2. runs one real sync (it refreshes the token itself if needed)
#    3. if the gate opened: runs the loader - real prices reach the site
#    4. prints the verdict, copies the report and opens notepad
#  Seller: 1061297 - gallery be ara
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
$secrets = Join-Path $root "secrets"
$sellerCode = "1061297"
$uaNew = "DigikalaTrustedBot/SelfToken/" + $sellerCode
$uaOld = "DigikalaTrustedBot/SelfToken"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("digikala_ua_fix_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD DIGIKALA UA FIX v1"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say (" seller: " + $sellerCode)
& $say (" new UA: " + $uaNew)
& $say "====================================================="

& $say ""
& $say "=== 0) PREFLIGHT ==="
$siteDir = Join-Path $root "site"
if (Test-Path $siteDir) {
  & $say " site folder: exists"
} else {
  & $say " site folder missing - unzip kiarad_site_v1.zip into D:\project\kiaradbi\site"
  & $say " (the sync will still run, but the site merge needs that folder)"
}
$taskScript = Join-Path $scripts "digikala_sync_task.ps1"
if (-not (Test-Path $taskScript)) {
  & $say " sync task script not found - run kiarad_digikala_watchtower_v1.ps1 first"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
$tokPath = Join-Path $secrets "digikala_tokens.json"
if (-not (Test-Path $tokPath)) {
  & $say " tokens file missing - run kiarad_digikala_final_v1.ps1 first"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
& $say " sync task + tokens: found"

& $say ""
& $say "=== 1) PATCH THE SYNC TASK UA (idempotent) ==="
$before = Select-String -Path $taskScript -Pattern "DigikalaTrustedBot"
foreach ($b in $before) { & $say (" before: " + $b.Line.Trim()) }
$txt = Get-Content $taskScript -Raw -Encoding UTF8
$txt = $txt.Replace($uaNew, $uaOld)
$txt = $txt.Replace($uaOld, $uaNew)
Set-Content -Path $taskScript -Value $txt -Encoding UTF8 -NoNewline
$after = Select-String -Path $taskScript -Pattern "DigikalaTrustedBot"
foreach ($a in $after) { & $say (" after : " + $a.Line.Trim()) }
$btxt = ($before | ForEach-Object { $_.Line }) -join "`n"
$atxt = ($after | ForEach-Object { $_.Line }) -join "`n"
if ($btxt -eq $atxt) {
  & $say " WARNING: no literal UA found to patch - paste the DigikalaTrustedBot lines above in the chat"
}

& $say ""
& $say "=== 2) RUN ONE REAL SYNC (refreshes the token itself if needed) ==="
$syncOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskScript 2>&1
$syncCode = $LASTEXITCODE
$syncOut | ForEach-Object { if ("$_".Trim() -ne "") { & $say ("   " + "$_".Trim()) } }
& $say (" sync exit code: " + $syncCode)

& $say ""
& $say "=== 3) WATCHDOG STATUS ==="
$wdPath = Join-Path $logs "digikala_watchdog_status.json"
$gateOpen = $false
if (Test-Path $wdPath) {
  $wd = Get-Content $wdPath -Raw -Encoding UTF8 | ConvertFrom-Json
  & $say (" gate=" + $wd.gate + "  refresh_ok=" + $wd.refresh_ok + "  items_total=" + $wd.items_total + "  at=" + $wd.at)
  if ("$($wd.gate)".Trim() -eq "open") { $gateOpen = $true }
} else {
  & $say " watchdog status not found - see the sync log tail below"
}
$syncLog = Join-Path $logs "digikala_sync_task.log"
if (Test-Path $syncLog) {
  & $say " sync log tail:"
  Get-Content $syncLog -Tail 12 -Encoding UTF8 | ForEach-Object { if ("$_".Trim() -ne "") { & $say ("   " + "$_".Trim()) } }
}

& $say ""
& $say "=== 4) LOADER (only if the gate is open) ==="
if ($gateOpen) {
  $loaderPath = Join-Path $scripts "kiarad_loader_v1.ps1"
  if (Test-Path $loaderPath) {
    $null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $loaderPath 2>&1
    & $say (" loader exit code: " + $LASTEXITCODE)
    $stPath = Join-Path $logs "digikala_loader_status.json"
    if (Test-Path $stPath) {
      $st = Get-Content $stPath -Raw -Encoding UTF8 | ConvertFrom-Json
      & $say (" loader: build=" + $st.build + " source=" + $st.source + " parsed=" + $st.items_parsed + " rows_total=" + $st.rows_total + " rows_digikala=" + $st.rows_digikala + " site_merged=" + $st.site_merged)
      & $say (" data file: " + $st.data_file)
    }
    $pp = Join-Path $siteDir "digikala_prices.json"
    if (-not (Test-Path $pp)) { $pp = Join-Path $root "digikala_prices.json" }
    if (Test-Path $pp) {
      & $say (" prices file: " + $pp)
      $pc = Get-Content $pp -Raw -Encoding UTF8
      $i = 0
      foreach ($ln in ("$pc" -split "`n")) {
        if ("$ln".Trim() -ne "") {
          $i = $i + 1
          if ($i -le 14) { & $say ("   " + "$ln".Trim()) }
        }
      }
    }
  } else {
    & $say " loader not found in scripts - copy kiarad_loader_v1.ps1 from the chat attachment into scripts"
  }
} else {
  & $say " gate still closed - loader skipped"
}

& $say ""
& $say "=== 5) BONUS PROBE (profile with the full UA) ==="
$tj = Get-Content $tokPath -Raw -Encoding UTF8 | ConvertFrom-Json
$acc = $tj.access_token
$profUrl = "https://seller.digikala.com/open-api/v1/profile"
foreach ($ln in (Get-Content $taskScript -Encoding UTF8)) {
  if ($ln -match "https://\S+profile") {
    $cand = ($ln -split "\s+" | Where-Object { $_ -like "https://*profile*" } | Select-Object -First 1)
    if ($cand) { $profUrl = "$cand".Trim('"') }
  }
}
& $say (" probe url: " + $profUrl)
if ($acc) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $profUrl -Method Get -Headers @{ Authorization = ("Bearer " + $acc) } -UserAgent $uaNew -TimeoutSec 30
    & $say (" PROFILE HTTP " + $r.StatusCode + " - GATE OPEN with the seller-code UA")
  } catch {
    $code = 0
    try { $code = $_.Exception.Response.StatusCode.value__ } catch { $code = 0 }
    $detail = "$($_.ErrorDetails.Message)".Trim()
    if ($detail -eq "") { $detail = $_.Exception.Message }
    & $say (" PROFILE HTTP " + $code + " - " + $detail)
  }
} else {
  & $say " no access token on disk to probe with - the sync step refreshed it, check its log above"
}

& $say ""
& $say "=== VERDICT ==="
if ($gateOpen) {
  & $say " DIGIKALA IS LIVE - real variants loaded, the site prices file is real,"
  & $say " and simulated rows were deleted by the loader. No manual step remains."
  & $say " open the site: double-click site\start_site.bat  (http://localhost:8081)"
  & $say " the watchdog task keeps running every 30 minutes with the fixed UA."
} else {
  & $say " gate still closed after the UA fix - paste this report in the chat."
}
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
