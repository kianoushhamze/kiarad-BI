$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$secrets = Join-Path $root "secrets"
$UA = "DigikalaTrustedBot/SelfToken/1061297"
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

# --- 4) persist the pull into the database for the dashboard/site ---
if ($gate -eq "open" -and $total -gt 0) {
  try {
    $pyOut = & (Join-Path $root ".venv\Scripts\python.exe") -I (Join-Path $root "scripts\digikala_db_upsert.py") 2>&1
    Log-Line ("db_upsert: " + ($pyOut -join " | "))
  } catch {
    Log-Line ("db_upsert failed: " + $_.Exception.Message)
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
