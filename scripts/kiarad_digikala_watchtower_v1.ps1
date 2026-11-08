# =====================================================================
#  KIARAD - DIGIKALA WATCHTOWER v1  (2026-10-30)
#  Purpose: keep the Digikala connection alive while the UA gate is
#  closed server-side, and start pulling data the moment it opens.
#  - writes scripts\digikala_sync_task.ps1 (UA = DigikalaTrustedBot/SelfToken,
#    the one the ecosystem confirms as required; it already passes on refresh)
#  - registers scheduled task KiaradDigikalaSync every 30 minutes
#  - every run: refresh token (keeps it alive) -> test /profile ->
#    if 200: pull variants and save; if 401: log gate closed. No human action.
#  Usage: paste this WHOLE block into PowerShell and press Enter.
# =====================================================================
$ErrorActionPreference = "Continue"
$root    = "D:\project\kiaradbi"
$logs    = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
$secrets = Join-Path $root "secrets"
foreach ($d in @($logs, $scripts, $secrets)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
$stamp      = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("digikala_watchtower_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD DIGIKALA WATCHTOWER v1"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="

$UA = "DigikalaTrustedBot/SelfToken"
$taskTemplate = @'
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$secrets = Join-Path $root "secrets"
$UA = "__UA__"
$base = "https://seller.digikala.com/open-api/v1"
$tokPath = Join-Path $secrets "digikala_tokens.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
function Log-Line { param($t) $line = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  " + $t; $line | Out-File -FilePath (Join-Path $logs "digikala_sync_task.log") -Append -Encoding utf8 }
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }
if (-not (Test-Path $tokPath)) { Log-Line "tokens file missing"; exit 1 }
$tok = Get-Content $tokPath -Raw | ConvertFrom-Json
$acc = $tok.access_token
if (-not $acc) { $acc = $tok.data.access_token }
$ref = $tok.refresh_token
if (-not $ref) { $ref = $tok.data.refresh_token }
$sid = $tok.seller_id
if (-not $sid) { $sid = $tok.data.seller_id }
$cc = $tok.client_code
if (-not $cc) { $cc = $tok.data.client_code }
if (-not $acc -or -not $ref) { Log-Line "tokens incomplete"; exit 1 }

# --- 1) refresh first: keeps access alive and proves auth path works ---
$refOk = $false
$bodyJson = New-Object System.Collections.Hashtable
$bodyJson.access_token = $acc
$bodyJson.refresh_token = $ref
$bj = $bodyJson | ConvertTo-Json
try {
  $rr = Invoke-RestMethod -Method Post -Uri ($base + "/auth/refresh-token") -ContentType "application/json" -Body $bj -Headers @{Accept="application/json"} -UserAgent $UA -TimeoutSec 40
  $na = $rr.data.access_token
  if ($na) {
    $nr = $rr.data.refresh_token
    if (-not $nr) { $nr = $ref }
    Copy-Item $tokPath (Join-Path $secrets "digikala_tokens_autobackup.json") -Force
    $fresh = New-Object System.Collections.Hashtable
    $fresh.access_token = $na
    $fresh.refresh_token = $nr
    $fresh.seller_id = $sid
    $fresh.client_code = $cc
    $fresh | ConvertTo-Json | Out-File -FilePath $tokPath -Encoding utf8
    $acc = $na
    $refOk = $true
    Log-Line "refresh ok"
  }
} catch {
  Log-Line ("refresh failed: " + $_.Exception.Message)
}
if (-not $refOk) { Log-Line "using existing access token" }

# --- 2) gate test on data endpoint ---
$gate = "closed"
try {
  $r = Invoke-WebRequest -UseBasicParsing -Method Get -Uri ($base + "/profile") -Headers @{Authorization=("Bearer " + $acc); Accept="application/json"} -UserAgent $UA -TimeoutSec 40
  $gate = "open"
} catch {
  $code = ""
  if ($null -ne $_.Exception.Response) { $code = $_.Exception.Response.StatusCode.value__ }
  $b = ""
  try { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); $b = $sr.ReadToEnd() } catch { }
  Log-Line ("gate test failed code=" + $code + " body=" + $b)
}

# --- 3) if open: pull variants page 1..5 ---
$total = 0
if ($gate -eq "open") {
  $lastCnt = 100
  $pg = 1
  while ($pg -le 5 -and $lastCnt -ge 100) {
    try {
      $rv = Invoke-WebRequest -UseBasicParsing -Method Get -Uri ($base + "/variants?page=" + $pg + "&size=100") -Headers @{Authorization=("Bearer " + $acc); Accept="application/json"} -UserAgent $UA -TimeoutSec 60
      $rv.Content | Out-File -FilePath (Join-Path $logs ("digikala_variants_p" + $pg + ".json")) -Encoding utf8
      $cnt = 0
      try {
        $jv = $rv.Content | ConvertFrom-Json
        $items = $jv.data.items
        if ($null -eq $items) { $items = $jv.items }
        if ($items) { $cnt = $items.Count }
      } catch { }
      $total = $total + $cnt
      $lastCnt = $cnt
      Log-Line ("variants page " + $pg + " items=" + $cnt)
      $pg = $pg + 1
      Start-Sleep -Seconds 2
    } catch {
      Log-Line ("variants page " + $pg + " failed")
      $lastCnt = 0
    }
  }
}

$status = New-Object System.Collections.Hashtable
$status.gate = $gate
$status.refresh_ok = $refOk
$status.items_total = $total
$status.at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
$status.ua = $UA
$status | ConvertTo-Json | Out-File -FilePath (Join-Path $logs "digikala_watchdog_status.json") -Encoding utf8
Log-Line ("gate=" + $gate + " refresh_ok=" + $refOk + " total=" + $total)
exit 0
'@
$taskScript = $taskTemplate.Replace("__UA__", $UA)
$taskPath = Join-Path $scripts "digikala_sync_task.ps1"
Set-Content -Path $taskPath -Value $taskScript -Encoding UTF8
& $say (" task script written: " + $taskPath)

& $say ""
& $say "=== REGISTERING SCHEDULED TASK (every 30 min) ==="
schtasks /Create /F /SC MINUTE /MO 30 /TN "KiaradDigikalaSync" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\project\kiaradbi\scripts\digikala_sync_task.ps1" | Out-Null
if ($LASTEXITCODE -eq 0) { & $say " scheduled task KiaradDigikalaSync registered" } else { & $say " schtasks failed - rerun this block" }

& $say ""
& $say "=== FIRST RUN NOW ==="
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskPath
$statusFile = Join-Path $logs "digikala_watchdog_status.json"
if (Test-Path $statusFile) {
  $st = Get-Content $statusFile -Raw | ConvertFrom-Json
  & $say (" watchdog status: gate=" + $st.gate + " refresh_ok=" + $st.refresh_ok + " items_total=" + $st.items_total)
} else {
  & $say " no status file - check logs\digikala_sync_task.log"
}
& $say ""
& $say "=== VERDICT ==="
& $say " Watchtower is ON. Every 30 min: refresh (keeps token alive) + gate test."
& $say " While Digikala keeps the UA gate closed, the log shows 401 Invalid User-Agent - EXPECTED."
& $say " The moment Digikala whitelists our client, variants data starts flowing automatically"
& $say " into logs\digikala_variants_p1.json with zero human action."
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
& $say " report copied to clipboard too."
