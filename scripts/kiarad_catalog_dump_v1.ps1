# =====================================================================
#  KIARAD - CATALOG DUMP v1 (2026-10-31, office session)
#  Plan B for the holoo<->digikala mapping: pull real holoo codes and
#  titles out of the local postgres catalog tables so we can match them
#  against the 50 real digikala variants.
#  Zero input. Report -> logs + clipboard + notepad. Paste it in chat.
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("holoo_catalog_dump_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD HOLOO CATALOG DUMP v1"
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
if ($pgdb -eq "") {
  $dbs = docker exec $pg psql -U $pguser -tAc "SELECT datname FROM pg_database WHERE datistemplate = false" 2>$null
  foreach ($d in $dbs) {
    $dn = "$d".Trim()
    if ($dn -like "*kiarad*") { $pgdb = $dn }
  }
}
if ($pgdb -eq "") { $pgdb = $pguser }
& $say (" container=" + $pg + " user=" + $pguser + " db=" + $pgdb)

# --- 1) list all public tables ---
$tablesSql = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
$tablesFile = Join-Path $root "scripts\holoo_tables_query.sql"
$sw = New-Object System.IO.StreamWriter($tablesFile, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($tablesSql)
$sw.Close()
docker cp "$tablesFile" ($pg + ":/tmp/holoo_tables_query.sql") | Out-Null
$tablesOut = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/holoo_tables_query.sql" 2>&1
$tables = New-Object System.Collections.ArrayList
foreach ($t in $tablesOut) {
  $tn = "$t".Trim()
  if ($tn -ne "" -and $tn -notmatch "psql:" -and $tn -notmatch "ERROR") { $null = $tables.Add($tn) }
}
& $say ""
& $say ("=== 1) PUBLIC TABLES (" + $tables.Count + ") ===")
foreach ($t in $tables) { & $say ("   " + $t) }

# --- 2) candidate catalog tables with a code-like and title-like column ---
$candTables = $tables | Where-Object { $_ -match "(?i)holoo|kala|product|catalog|item|goods" }
& $say ""
& $say "=== 2) CANDIDATE CATALOG TABLES (code + title columns) ==="
$best = ""
$bestCode = ""
$bestTitle = ""
foreach ($tn in $candTables) {
  $colSql = "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='" + $tn + "' ORDER BY ordinal_position"
  $colFile = Join-Path $root "scripts\holoo_cols_query.sql"
  $sw = New-Object System.IO.StreamWriter($colFile, $false, (New-Object System.Text.UTF8Encoding $false))
  $sw.Write($colSql)
  $sw.Close()
  docker cp "$colFile" ($pg + ":/tmp/holoo_cols_query.sql") | Out-Null
  $colsOut = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/holoo_cols_query.sql" 2>&1
  $cols = New-Object System.Collections.ArrayList
  foreach ($c in $colsOut) {
    $cn = "$c".Trim()
    if ($cn -ne "" -and $cn -notmatch "psql:" -and $cn -notmatch "ERROR") { $null = $cols.Add($cn) }
  }
  $codeCol = $cols | Where-Object { $_ -match "(?i)^(code|kala_code|product_code|item_code|sku|barcode)$|code$" } | Select-Object -First 1
  $titleCol = $cols | Where-Object { $_ -match "(?i)title|name|descr|sharh" } | Select-Object -First 1
  & $say ("   " + $tn + "  cols: " + (($cols | Select-Object -First 12) -join ", "))
  if ($codeCol -and $titleCol) {
    $cntRaw = docker exec $pg psql -U $pguser -d $pgdb -tAc ("SELECT count(*) FROM " + $tn) 2>$null
    & $say ("      -> code=" + $codeCol + "  title=" + $titleCol + "  rows=" + "$cntRaw".Trim())
    if ($best -eq "") { $best = $tn; $bestCode = $codeCol; $bestTitle = $titleCol }
  }
}

if ($best -eq "") {
  & $say ""
  & $say " no table with a code+title pair found - paste the table list above in the chat"
} else {
  & $say ""
  & $say ("=== 3) SAMPLE ROWS FROM " + $best + " (up to 30, code | title) ===")
  $dumpSql = "COPY (SELECT " + $bestCode + ", " + $bestTitle + " FROM " + $best + " LIMIT 30) TO STDOUT WITH (FORMAT csv)"
  $dumpFile = Join-Path $root "scripts\holoo_dump_query.sql"
  $sw = New-Object System.IO.StreamWriter($dumpFile, $false, (New-Object System.Text.UTF8Encoding $false))
  $sw.Write($dumpSql)
  $sw.Close()
  docker cp "$dumpFile" ($pg + ":/tmp/holoo_dump_query.sql") | Out-Null
  $rows = docker exec $pg psql -U $pguser -d $pgdb -f "/tmp/holoo_dump_query.sql" 2>&1
  foreach ($r in $rows) {
    if ("$r".Trim() -ne "") { & $say ("   " + "$r".Trim()) }
  }
  & $say ""
  & $say " next step: paste this report in the chat - the mapping table will be built from these codes"
}

& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
