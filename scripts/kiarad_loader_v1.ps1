# =====================================================================
#  KIARAD - DIGIKALA LOADER v1 (2026-10-30, build C: auto user/db)
#  Reads logs\digikala_variants_p*.json (or the simulated sample while
#  the UA gate is closed) and upserts rows into the digikala_variants
#  table, then writes site\digikala_prices.json and, if a site data.json
#  with a products list exists, adds price_digikala / price_source fields
#  to matching products (non-destructive: holoo price stays untouched).
#  Build C: postgres user and database are auto-detected from the
#  container env (POSTGRES_USER / POSTGRES_DB, bitnami names too) and a
#  hard SELECT 1 probe gates every later step. Root cause found:
#  the container has no role "postgres" - psql calls were failing
#  silently. SQL still travels via docker cp + psql -f (no stdin).
#  Standalone: can run via scheduled task. No input needed.
# =====================================================================
$ErrorActionPreference = "Continue"
$root    = "D:\project\kiaradbi"
$logs    = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
foreach ($d in @($logs, $scripts)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$logPath = Join-Path $logs "digikala_loader.log"
function Log-Line { param($t) $line = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  " + $t; $line | Out-File -FilePath $logPath -Append -Encoding utf8 }
Log-Line "loader start (build C)"

# --- find postgres container ---
$pg = ""
$cl = docker ps --format "{{.Names}}|{{.Image}}" 2>$null
foreach ($l in $cl) {
  if ($l -like "*postgres*") { $pg = ($l -split "\|") | Select-Object -First 1 }
}
if ($pg -eq "") { Log-Line "no postgres container found"; exit 1 }

# --- detect user and db from container env ---
$pguser = ""
$pgdb = ""
$envLines = docker inspect $pg --format "{{range .Config.Env}}{{println .}}{{end}}" 2>$null
foreach ($e in $envLines) {
  $el = "$e"
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
Log-Line ("container=" + $pg + " user=" + $pguser + " db=" + $pgdb)

# --- hard probe: nothing proceeds unless SELECT 1 works ---
$probeRaw = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT 1" 2>&1
$probeStr = ("$probeRaw" -join " ").Trim()
if ($probeStr -ne "1") {
  Log-Line ("DB_PROBE_FAILED user=" + $pguser + " db=" + $pgdb + " raw=" + $probeStr)
  $status = New-Object System.Collections.Hashtable
  $status.set_Item("at", (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  $status.set_Item("build", "C")
  $status.set_Item("container", $pg)
  $status.set_Item("pguser", $pguser)
  $status.set_Item("pgdb", $pgdb)
  $status.set_Item("probe_ok", $false)
  $status.set_Item("probe_raw", $probeStr)
  $status | ConvertTo-Json | Out-File -FilePath (Join-Path $logs "digikala_loader_status.json") -Encoding utf8
  exit 3
}
Log-Line "db probe ok"

# --- ensure schema (idempotent; docker cp + psql -f, zero stdin) ---
$schemaSql = @"
CREATE TABLE IF NOT EXISTS digikala_variants (
  dkp_id BIGINT PRIMARY KEY,
  holoo_code TEXT,
  title TEXT,
  status TEXT,
  price_rrp BIGINT,
  price_selling BIGINT,
  stock INTEGER,
  source TEXT NOT NULL DEFAULT 'digikala',
  raw JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_digikala_variants_holoo ON digikala_variants (holoo_code);
CREATE TABLE IF NOT EXISTS variant_map (
  supplier_code TEXT PRIMARY KEY,
  holoo_code TEXT NOT NULL,
  note TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"@
$schemaPath = Join-Path $scripts "digikala_schema.sql"
$sw = New-Object System.IO.StreamWriter($schemaPath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($schemaSql)
$sw.Close()
$schemaTarget = "/tmp/kiarad_schema.sql"
docker cp "$schemaPath" ($pg + ":" + $schemaTarget) | Out-Null
$schemaOk = $true
$schemaOut = docker exec $pg psql -U $pguser -d $pgdb -f $schemaTarget 2>&1
foreach ($x in $schemaOut) {
  $s = "$x"
  if ($s -imatch "error" -or $s -imatch "FATAL") { Log-Line ("schema error: " + $s); $schemaOk = $false }
}
if ($schemaOk) { Log-Line "schema applied" }

# --- collect input files ---
$files = Get-ChildItem -Path $logs -Filter "digikala_variants_p*.json" -ErrorAction SilentlyContinue | Sort-Object Name
$src = "digikala"
$sim = $false
if (-not $files -or $files.Count -eq 0) {
  $files = Get-ChildItem -Path $scripts -Filter "digikala_sample_response.json" -ErrorAction SilentlyContinue
  $src = "simulated"
  $sim = $true
}
if (-not $files -or $files.Count -eq 0) { Log-Line "no input files"; exit 0 }
Log-Line ("input: " + $files.Count + " file(s), source=" + $src)

$sqlText = ""
if (-not $sim) { $sqlText = "DELETE FROM digikala_variants WHERE source = 'simulated';" + "`r`n" }

$n = 0
foreach ($f in $files) {
  $j = $null
  try { $j = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Log-Line ("bad json: " + $f.Name) }
  if ($null -eq $j) { continue }
  $items = $j.data.items
  if ($null -eq $items) { $items = $j.items }
  if ($null -eq $items) { Log-Line ("no items in " + $f.Name); continue }
  foreach ($it in $items) {
    $id = $it.id
    if ($null -eq $id) { $id = $it.variant_id }
    if ($null -eq $id) { $id = $it.dkp }
    if ($null -eq $id) { $id = $it.product_id }
    if ($null -eq $id) { continue }
    $title = $it.title
    if ($null -eq $title) { $title = $it.fa_title }
    if ($null -eq $title) { $title = $it.name }
    if ($null -eq $title) { $title = "" }
    $sku = $it.sku
    if ($null -eq $sku) { $sku = $it.seller_code }
    if ($null -eq $sku) { $sku = $it.code }
    if ($null -eq $sku) { $sku = $it.supplier_code }
    if ("$sku".Trim() -eq "") { $sku = $null }
    $price = $it.price.selling_price
    if ($null -eq $price) { $price = $it.price.rrp_price }
    if ($null -eq $price) { $price = $it.price }
    if ($null -eq $price) { $price = $it.selling_price }
    if ($null -eq $price) { $price = 0 }
    $rrp = $it.price.rrp_price
    if ($null -eq $rrp) { $rrp = $it.rrp_price }
    if ($null -eq $rrp) { $rrp = 0 }
    $stock = $it.stock
    if ($null -eq $stock) { $stock = $it.quantity }
    if ($null -eq $stock) { $stock = 0 }
    $stt = $it.status
    if ($null -eq $stt) { $stt = "unknown" }
    $raw = $it | ConvertTo-Json -Depth 8 -Compress
    $rawE = $raw -replace "'", "''"
    $titleE = $title -replace "'", "''"
    $sttE = $stt -replace "'", "''"
    $skuS = "NULL"
    if ($null -ne $sku) { $skuS = "'" + (($sku -replace "'", "''")) + "'" }
    $sql = "INSERT INTO digikala_variants (dkp_id, holoo_code, title, status, price_rrp, price_selling, stock, source, raw) VALUES (" + $id + ", " + $skuS + ", '" + $titleE + "', '" + $sttE + "', " + $rrp + ", " + $price + ", " + $stock + ", '" + $src + "', '" + $rawE + "'::jsonb) ON CONFLICT (dkp_id) DO UPDATE SET holoo_code = EXCLUDED.holoo_code, title = EXCLUDED.title, status = EXCLUDED.status, price_rrp = EXCLUDED.price_rrp, price_selling = EXCLUDED.price_selling, stock = EXCLUDED.stock, source = EXCLUDED.source, raw = EXCLUDED.raw, updated_at = now();"
    $sqlText = $sqlText + $sql + "`r`n"
    $n = $n + 1
  }
}
Log-Line ("parsed items=" + $n)

# --- apply batch (docker cp + psql -f, zero stdin) ---
$batchPath = Join-Path $scripts "digikala_load_batch.sql"
$sw = New-Object System.IO.StreamWriter($batchPath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($sqlText)
$sw.Close()
$batchTarget = "/tmp/kiarad_load_batch.sql"
docker cp "$batchPath" ($pg + ":" + $batchTarget) | Out-Null
$batchOut = docker exec $pg psql -U $pguser -d $pgdb -f $batchTarget 2>&1
foreach ($x in $batchOut) {
  $s = "$x"
  if ($s -imatch "error" -or $s -imatch "FATAL") { Log-Line ("psql error: " + $s) }
}

# --- verify table (hard check with error capture) ---
$cntRaw = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT count(*) FROM digikala_variants" 2>&1
$cntStr = ("$cntRaw" -join " ").Trim()
$tableOk = $true
if ($cntStr -eq "" -or $cntStr -imatch "error" -or $cntStr -imatch "FATAL") {
  $tableOk = $false
  Log-Line "TABLE_VERIFY_FAILED: count query gave no number"
}
$totalRows = $cntStr
$cntReal = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT count(*) FROM digikala_variants WHERE source = 'digikala'" 2>$null
$cntHoloo = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT count(*) FROM digikala_variants WHERE holoo_code IS NOT NULL" 2>$null
$realRows = ("$cntReal" -join " ").Trim()
$holooRows = ("$cntHoloo" -join " ").Trim()
Log-Line ("rows total=" + $totalRows + " digikala=" + $realRows + " holoo_mapped=" + $holooRows)

# --- apply supplier mapping from variant_map (supplier_code -> holoo_code) ---
$mapApplySql = "UPDATE digikala_variants v SET holoo_code = m.holoo_code FROM variant_map m WHERE v.holoo_code IS NULL AND v.dkp_id::text = m.supplier_code;"
$mapApplyPath = Join-Path $scripts "digikala_map_apply.sql"
$sw = New-Object System.IO.StreamWriter($mapApplyPath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($mapApplySql)
$sw.Close()
$mapApplyTarget = "/tmp/kiarad_map_apply.sql"
docker cp "$mapApplyPath" ($pg + ":" + $mapApplyTarget) | Out-Null
$mapApplyOut = docker exec $pg psql -U $pguser -d $pgdb -f $mapApplyTarget 2>&1
foreach ($x in $mapApplyOut) { $s = "$x"; if ($s -imatch "error" -or $s -imatch "FATAL") { Log-Line ("map apply error: " + $s) } }
$mappedCnt = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT count(*) FROM digikala_variants WHERE holoo_code IS NOT NULL" 2>$null
Log-Line ("mapped variants after variant_map: " + "$mappedCnt".Trim())

# --- build holoo_code map (COPY TO STDOUT via file, zero stdin) ---
$mapSql = "COPY (SELECT coalesce(holoo_code,''), price_selling, stock, to_char(updated_at, 'YYYY-MM-DD HH24:MI') FROM digikala_variants WHERE holoo_code IS NOT NULL AND price_selling IS NOT NULL) TO STDOUT WITH (FORMAT csv)"
$mapQueryPath = Join-Path $scripts "digikala_map_query.sql"
$sw = New-Object System.IO.StreamWriter($mapQueryPath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($mapSql)
$sw.Close()
$mapTarget = "/tmp/kiarad_map_query.sql"
docker cp "$mapQueryPath" ($pg + ":" + $mapTarget) | Out-Null
$mapOut = docker exec $pg psql -U $pguser -d $pgdb -f $mapTarget 2>&1
$mapRowsPath = Join-Path $scripts "digikala_map_rows.csv"
$sw = New-Object System.IO.StreamWriter($mapRowsPath, $false, (New-Object System.Text.UTF8Encoding $false))
foreach ($x in $mapOut) { $sw.WriteLine("$x") }
$sw.Close()
$map = New-Object System.Collections.Hashtable
$mapLines = Get-Content $mapRowsPath -Encoding UTF8
foreach ($r in $mapLines) {
  $rr = "$r".Trim()
  if ($rr -ne "" -and $rr -notmatch "COPY" -and $rr -notmatch "FATAL" -and $rr -notmatch "psql:" -and $rr -notmatch "error") {
    $parts = $rr -split ","
    $code = $parts | Select-Object -First 1
    $pr = $parts | Select-Object -Index 1
    # digikala api returns RIAL - convert to toman for the site
    $prNum = [int64]0
    if ([int64]::TryParse("$pr", [ref]$prNum)) { $pr = [string]([int64][math]::Round($prNum / 10)) }
    $stq = $parts | Select-Object -Index 2
    $up = $parts | Select-Object -Index 3
    if ($code -ne "") {
      $entry = New-Object System.Collections.Hashtable
      $entry.set_Item("price", $pr)
      $entry.set_Item("stock", $stq)
      $entry.set_Item("updated", $up)
      $entry.set_Item("source", $src)
      $map.set_Item($code, $entry)
    }
  }
}

# --- site prices file ---
$siteDir = Join-Path $root "site"
$pricesPath = Join-Path $root "digikala_prices.json"
if (Test-Path $siteDir) { $pricesPath = Join-Path $siteDir "digikala_prices.json" }
$pricesJson = "{}"
if ($map.Count -gt 0) { $pricesJson = $map | ConvertTo-Json -Depth 6 }
$sw = New-Object System.IO.StreamWriter($pricesPath, $false, (New-Object System.Text.UTF8Encoding $false))
$sw.Write($pricesJson)
$sw.Close()

# --- merge into site data.json (non-destructive) ---
$merged = 0
$dataFile = $null
$cand = Join-Path $siteDir "data.json"
if (Test-Path $cand) { $dataFile = $cand }
else {
  $found = Get-ChildItem -Path $root -Recurse -Filter "data.json" -ErrorAction SilentlyContinue | Where-Object { ($_.FullName -notlike "*node_modules*") -and ($_.FullName -notlike "*.next*") } | Select-Object -First 1
  if ($found) { $dataFile = $found.FullName }
}
if ($dataFile -and $map.Count -gt 0) {
  $dj = $null
  try { $dj = Get-Content $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $dj = $null }
  if ($null -ne $dj) {
    $prods = $dj.products
    if ($null -eq $prods) { $prods = $dj.items }
    if ($null -eq $prods) { $prods = $dj.products_list }
    if ($null -ne $prods -and $prods.Count -gt 0) {
      foreach ($p in $prods) {
        $code = $p.holoo_code
        if ($null -eq $code) { $code = $p.sku }
        if ($null -eq $code) { $code = $p.code }
        if ($null -eq $code) { $code = $p.product_code }
        if ($null -ne $code) {
          if ($map.ContainsKey($code)) {
            $v = $map.get_Item($code)
            $p | Add-Member -NotePropertyName price_digikala -NotePropertyValue $v.price -Force
            $p | Add-Member -NotePropertyName price_source -NotePropertyValue "digikala" -Force
            $merged = $merged + 1
          }
        }
      }
      if ($merged -gt 0) {
        Copy-Item $dataFile ($dataFile + ".bak_loader") -Force
        $out = $dj | ConvertTo-Json -Depth 12
        $sw = New-Object System.IO.StreamWriter($dataFile, $false, (New-Object System.Text.UTF8Encoding $false))
        $sw.Write($out)
        $sw.Close()
      }
    }
  }
}

$status = New-Object System.Collections.Hashtable
$status.set_Item("at", (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
$status.set_Item("build", "C")
$status.set_Item("container", $pg)
$status.set_Item("pguser", $pguser)
$status.set_Item("pgdb", $pgdb)
$status.set_Item("probe_ok", $true)
$status.set_Item("source", $src)
$status.set_Item("items_parsed", $n)
$status.set_Item("schema_ok", $schemaOk)
$status.set_Item("table_ok", $tableOk)
$status.set_Item("rows_total", $totalRows)
$status.set_Item("rows_digikala", $realRows)
$status.set_Item("rows_holoo_mapped", $holooRows)
$mapTblRaw = docker exec $pg psql -U $pguser -d $pgdb -tAc "SELECT count(*) FROM variant_map" 2>$null
$status.set_Item("map_table_rows", "$mapTblRaw".Trim())
$status.set_Item("site_merged", $merged)
$status.set_Item("data_file", $dataFile)
$status | ConvertTo-Json | Out-File -FilePath (Join-Path $logs "digikala_loader_status.json") -Encoding utf8
Log-Line ("done parsed=" + $n + " total=" + $totalRows + " merged=" + $merged + " table_ok=" + $tableOk)
exit 0
