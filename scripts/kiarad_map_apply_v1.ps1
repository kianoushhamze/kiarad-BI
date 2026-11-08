# =====================================================================
#  KIARAD - MAP APPLY v1 (2026-10-31, office session)
#  Digikala sends no seller code (supplier_code empty on all 50 items),
#  so the mapping dkp_id -> holoo_code is built by hand:
#    scripts\variant_map.csv  (two columns, no header):
#      84244150,H1001
#  Run 1 (empty CSV): prints all 50 variants (dkp_id | title) as a
#  pairing sheet -> build the CSV with the chat, then Run 2:
#  loads the map, applies it, runs the loader, shows the result.
#  Zero input. Report -> logs + clipboard + notepad.
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("kiarad_map_apply_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD MAP APPLY v1"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="

$pg = ""
$cl = docker ps --format "{{.Names}}|{{.Image}}" 2>$null
foreach ($l in $cl) {
  if ($l -like "*postgres*") { $pg = ($l -split "\|") | Select-Object -First 1 }
}
if ($pg -eq "") {
  & $say " postgres container not running - start Docker Desktop and rerun"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
$pguser = ""
$pgdb = ""
$cenv = docker inspect $pg --format "{{range .Config.Env}}{{println .}}{{end}}" 2>$null
foreach ($el in $cenv) {
  if ($el -like "POSTGRES_USER=*") { $pguser = ($el -split "=", 2) | Select-Object -Last 1 }
  elseif ($el -like "POSTGRESQL_USERNAME=*" -and $pguser -eq "") { $pguser = ($el -split "=", 2) | Select-Object -Last 1 }
  elseif ($el -like "POSTGRES_DB=*") { $pgdb = ($el -split "=", 2) | Select-Object -Last 1 }
  elseif ($el -like "POSTGRESQL_DATABASE=*" -and $pgdb -eq "") { $pgdb = ($el -split "=", 2) | Select-Object -Last 1 }
}
if ($pguser -eq "") { $pguser = "postgres" }
if ($pgdb -eq "") { $pgdb = $pguser }
& $say (" container=" + $pg + " user=" + $pguser + " db=" + $pgdb)

# --- variant map table (idempotent) ---
$schemaSql = "CREATE TABLE IF NOT EXISTS variant_map (supplier_code TEXT PRIMARY KEY, holoo_code TEXT NOT NULL, note TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());"
$schemaFile = Join-Path $scripts "variant_map_schema.sql"
$sw = New-Object System.IO.StreamWriter($schemaFile, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($schemaSql)
$sw.Close()
docker cp "$schemaFile" ($pg + ":/tmp/variant_map_schema.sql") | Out-Null
$null = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/variant_map_schema.sql" 2>&1

# --- read the csv (two columns, no header) ---
$csvPath = Join-Path $scripts "variant_map.csv"
$pairs = New-Object System.Collections.ArrayList
if (Test-Path $csvPath) {
  foreach ($ln in (Get-Content $csvPath -Encoding UTF8)) {
    $t = "$ln".Trim()
    if ($t -eq "" -or $t -like "#*") { continue }
    $p = $t -split ","
    if ($p.Count -ge 2) {
      $sup = "$($p | Select-Object -First 1)".Trim()
      $hol = "$($p | Select-Object -Index 1)".Trim()
      if ($sup -ne "" -and $hol -ne "") {
        $pair = New-Object System.Collections.Hashtable
        $pair.supplier = $sup
        $pair.holoo = $hol
        $null = $pairs.Add($pair)
      }
    }
  }
}
& $say (" csv: " + $csvPath + "  pairs: " + $pairs.Count)

if ($pairs.Count -eq 0) {
  & $say ""
  & $say "=== PAIRING SHEET (all variants) - build variant_map.csv from this ==="
  & $say " csv format: dkp_id,holoo_code   (one pair per line, no header)"
  $listSql = "COPY (SELECT dkp_id, left(title, 70) FROM digikala_variants ORDER BY dkp_id) TO STDOUT WITH (FORMAT csv)"
  $listFile = Join-Path $scripts "variant_list_query.sql"
  $sw = New-Object System.IO.StreamWriter($listFile, $false, (New-Object System.Text.UTF8Encoding $false))
  $sw.Write($listSql)
  $sw.Close()
  docker cp "$listFile" ($pg + ":/tmp/variant_list_query.sql") | Out-Null
  $rows = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/variant_list_query.sql" 2>&1
  foreach ($r in $rows) {
    if ("$r".Trim() -ne "") { & $say ("   " + "$r".Trim()) }
  }
  & $say ""
  & $say " also check the holoo catalog report (holoo_catalog_dump_*.txt) for real holoo codes."
  & $say " paste both lists in the chat - the csv content comes back ready to paste."
  & $say (" report: " + $reportPath)
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
  exit 0
}

# --- upsert the pairs ---
$sqlText = ""
foreach ($pr in $pairs) {
  $sup = "$($pr.supplier)" -replace "'", "''"
  $hol = "$($pr.holoo)" -replace "'", "''"
  $sqlText = $sqlText + "INSERT INTO variant_map (supplier_code, holoo_code, note) VALUES ('" + $sup + "', '" + $hol + "', 'office-20261031') ON CONFLICT (supplier_code) DO UPDATE SET holoo_code = EXCLUDED.holoo_code, updated_at = now();" + "`r`n"
}
$loadFile = Join-Path $scripts "variant_map_load.sql"
$sw = New-Object System.IO.StreamWriter($loadFile, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($sqlText)
$sw.Close()
docker cp "$loadFile" ($pg + ":/tmp/variant_map_load.sql") | Out-Null
$loadOut = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/variant_map_load.sql" 2>&1
$err = $false
foreach ($x in $loadOut) { $s = "$x"; if ($s -imatch "error" -or $s -imatch "FATAL") { & $say (" load error: " + $s); $err = $true } }
if ($err) {
  & $say " csv load failed - paste this report in the chat"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 2
}
& $say (" map rows loaded: " + $pairs.Count)

& $say ""
& $say "=== APPLY MAP + RUN LOADER ==="
$loaderPath = Join-Path $scripts "kiarad_loader_v1.ps1"
if (-not (Test-Path $loaderPath)) {
  & $say " loader not found in scripts - download kiarad_loader_v1.ps1 first"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
$null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $loaderPath 2>&1
& $say (" loader exit code: " + $LASTEXITCODE)
$stPath = Join-Path $logs "digikala_loader_status.json"
if (Test-Path $stPath) {
  $st = Get-Content $stPath -Raw -Encoding UTF8 | ConvertFrom-Json
  & $say (" loader: source=" + $st.source + " rows_total=" + $st.rows_total + " rows_digikala=" + $st.rows_digikala + " rows_holoo_mapped=" + $st.rows_holoo_mapped + " site_merged=" + $st.site_merged)
  & $say (" data file: " + $st.data_file)
}

& $say ""
& $say "=== SITE PRICES (up to 20 lines) ==="
$pp = Join-Path $root "site\digikala_prices.json"
if (Test-Path $pp) {
  $pc = Get-Content $pp -Raw -Encoding UTF8
  $i = 0
  foreach ($ln in ("$pc" -split "`n")) {
    if ("$ln".Trim() -ne "") {
      $i = $i + 1
      if ($i -le 20) { & $say ("   " + "$ln".Trim()) }
    }
  }
} else {
  & $say " site prices file not found"
}

& $say ""
& $say "=== VERDICT ==="
& $say " mapping applied and the loader ran with it."
& $say " if site_merged is above 0: double-click site\start_site.bat - real digikala prices are live."
& $say " add more pairs to scripts\variant_map.csv any time and rerun this script."
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
