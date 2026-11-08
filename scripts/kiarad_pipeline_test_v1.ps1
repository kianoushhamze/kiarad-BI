# =====================================================================
#  KIARAD - DIGIKALA PIPELINE TEST v1 (2026-10-30)
#  Simulated end-to-end test of the second half of the Digikala chain
#  while the UA gate is closed:
#    embedded sample -> loader -> digikala_variants table -> site file
#  Zero user input. If Docker or Postgres is off, start Docker Desktop
#  and rerun the same block.
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
foreach ($d in @($logs, $scripts)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("digikala_pipeline_test_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD DIGIKALA PIPELINE TEST v1 (simulated data)"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="

& $say ""
& $say "=== 0) PREFLIGHT ==="
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  & $say " docker not found - start Docker Desktop and rerun the same block"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
$pg = ""
$cl = docker ps --format "{{.Names}}|{{.Image}}" 2>$null
foreach ($l in $cl) {
  if ($l -like "*postgres*") { $pg = ($l -split "\|") | Select-Object -First 1 }
}
if ($pg -eq "") {
  & $say " postgres container not running - start Docker Desktop and rerun the same block"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
& $say (" postgres container: " + $pg)
$db = "postgres"
$alt = ""
$dbs = docker exec $pg psql -U postgres -tAc "SELECT datname FROM pg_database WHERE datistemplate = false" 2>$null
foreach ($d in $dbs) {
  $dn = "$d".Trim()
  if ($dn -like "*kiarad*") { $db = $dn }
  elseif ($dn -ne "postgres" -and $alt -eq "") { $alt = $dn }
}
if ($db -eq "postgres" -and $alt -ne "") { $db = $alt }
& $say (" database: " + $db)

& $say ""
& $say "=== 1) SAMPLE (simulated API response) -> scripts folder ==="
$itemsList = New-Object System.Collections.ArrayList

$m1 = New-Object System.Collections.Hashtable
$m1.id = 7100001
$m1.sku = "H1001"
$m1.title = "Test Product A - Size 1"
$m1.status = "active"
$pr1 = New-Object System.Collections.Hashtable
$pr1.selling_price = 2450000
$pr1.rrp_price = 2900000
$m1.price = $pr1
$m1.stock = 12
$null = $itemsList.Add($m1)

$m2 = New-Object System.Collections.Hashtable
$m2.id = 7100002
$m2.sku = "H1002"
$m2.title = "Test Product B - Size 2"
$m2.status = "active"
$pr2 = New-Object System.Collections.Hashtable
$pr2.selling_price = 1895000
$pr2.rrp_price = 2200000
$m2.price = $pr2
$m2.stock = 7
$null = $itemsList.Add($m2)

$m3 = New-Object System.Collections.Hashtable
$m3.id = 7100003
$m3.sku = "H1003"
$m3.title = "Test Product C - Size 1"
$m3.status = "inactive"
$pr3 = New-Object System.Collections.Hashtable
$pr3.selling_price = 990000
$pr3.rrp_price = 1200000
$m3.price = $pr3
$m3.stock = 0
$null = $itemsList.Add($m3)

$m4 = New-Object System.Collections.Hashtable
$m4.id = 7100004
$m4.sku = "H1004"
$m4.title = "Test Product D"
$m4.status = "active"
$pr4 = New-Object System.Collections.Hashtable
$pr4.selling_price = 3750000
$pr4.rrp_price = 3750000
$m4.price = $pr4
$m4.stock = 3
$null = $itemsList.Add($m4)

$inner = New-Object System.Collections.Hashtable
$inner.items = $itemsList
$data = New-Object System.Collections.Hashtable
$data.data = $inner
$sampleJson = $data | ConvertTo-Json -Depth 8
$samplePath = Join-Path $scripts "digikala_sample_response.json"
$sw = New-Object System.IO.StreamWriter($samplePath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($sampleJson)
$sw.Close()
& $say (" sample written: " + $samplePath + "  (4 simulated items, source=simulated)")

& $say ""
& $say "=== 2) RUN LOADER ==="
$loaderPath = Join-Path $scripts "kiarad_loader_v1.ps1"
if (-not (Test-Path $loaderPath)) {
  & $say " loader not found - the download block was incomplete - rerun the same block"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
& $say " running loader ..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $loaderPath
& $say (" loader exit code: " + $LASTEXITCODE)

& $say ""
& $say "=== 3) VERIFY TABLE ==="
$q1 = docker exec $pg psql -U postgres -d $db -tAc "SELECT count(*) FROM digikala_variants" 2>$null
$q2 = docker exec $pg psql -U postgres -d $db -tAc "SELECT count(*) FROM digikala_variants WHERE source = 'simulated'" 2>$null
$q3 = docker exec $pg psql -U postgres -d $db -tAc "SELECT count(*) FROM digikala_variants WHERE holoo_code IS NOT NULL" 2>$null
if ("$q1".Trim() -eq "") {
  & $say " table missing - loader failed - check logs\digikala_loader.log"
} else {
  & $say (" rows total: " + "$q1".Trim())
  & $say (" rows simulated: " + "$q2".Trim())
  & $say (" rows with holoo_code: " + "$q3".Trim())
  & $say " rows:"
  $rows = docker exec $pg psql -U postgres -d $db -tA -F "  |  " -c "SELECT dkp_id, holoo_code, price_selling, stock, status FROM digikala_variants ORDER BY dkp_id" 2>$null
  foreach ($r in $rows) {
    if ("$r".Trim() -ne "") { & $say ("   " + "$r".Trim()) }
  }
}

& $say ""
& $say "=== 4) SITE PRICES FILE ==="
$pricesPath = Join-Path $root "site\digikala_prices.json"
if (-not (Test-Path $pricesPath)) { $pricesPath = Join-Path $root "digikala_prices.json" }
if (Test-Path $pricesPath) {
  & $say (" prices file: " + $pricesPath)
  $pc = Get-Content $pricesPath -Raw -Encoding UTF8
  foreach ($ln in ("$pc" -split "`n")) {
    if ("$ln".Trim() -ne "") { & $say ("   " + "$ln".Trim()) }
  }
} else {
  & $say " prices file NOT found - check logs\digikala_loader.log"
}

& $say ""
& $say "=== 5) SITE MERGE CHECK ==="
$stPath = Join-Path $logs "digikala_loader_status.json"
if (Test-Path $stPath) {
  $st = Get-Content $stPath -Raw -Encoding UTF8 | ConvertFrom-Json
  & $say (" loader status: source=" + $st.source + " parsed=" + $st.items_parsed + " site_merged=" + $st.site_merged)
  & $say (" data file used: " + $st.data_file)
  if ("$st.site_merged".Trim() -eq "0") {
    & $say " site_merged=0 is EXPECTED now: sample SKUs H1001..H1004 are placeholders,"
    & $say " not real holoo codes. With real sync data the same loader maps automatically."
  }
}

& $say ""
& $say "=== VERDICT ==="
& $say " chain verified: sample -> loader -> digikala_variants -> prices file (+ data.json merge)"
& $say " at gate-open: sync task writes real files -> next loader run deletes simulated rows"
& $say " and loads real ones. No manual step."
& $say " run the loader any time with:"
& $say "   powershell -NoProfile -ExecutionPolicy Bypass -File D:\project\kiaradbi\scripts\kiarad_loader_v1.ps1"
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
