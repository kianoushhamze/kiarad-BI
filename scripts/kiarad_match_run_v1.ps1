$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"; $scripts = "$root\scripts"; $logs = "$root\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$pgU = "kiarad"; $pgD = "kiaradbi"
$pyExe = "python"
if (Test-Path "$root\.venv\Scripts\python.exe") { $pyExe = "$root\.venv\Scripts\python.exe" }
docker exec kiarad-postgres psql -U $pgU -d $pgD -q -c "COPY (SELECT code, name FROM products WHERE is_active = 1) TO STDOUT WITH CSV HEADER" 2>$null | Out-File "$scripts\products_export.csv" -Encoding utf8
docker exec kiarad-postgres psql -U $pgU -d $pgD -q -c "COPY (SELECT dkp_id, title FROM digikala_variants) TO STDOUT WITH CSV HEADER" 2>$null | Out-File "$scripts\digikala_export.csv" -Encoding utf8
& $pyExe "$scripts\kiarad_match_core.py" "$scripts\products_export.csv" "$scripts\digikala_export.csv" "$scripts\match_result.csv"
if (Test-Path "$scripts\variant_map.csv") { Copy-Item "$scripts\variant_map.csv" "$scripts\variant_map.csv.bak.$ts" }
$lines = @("# variant_map.csv (auto-generated $ts)","# format: supplier_code,holoo_code,note,active","# supplier_code = dkp_id (digikala internal id)","# leading # = commented = NOT applied","# === AUTO ===")
$res = Import-Csv "$scripts\match_result.csv"
$a = @($res | Where-Object { $_.level -eq "AUTO" })
$r = @($res | Where-Object { $_.level -eq "REVIEW" })
$n = @($res | Where-Object { $_.level -eq "NONE" })
foreach ($x in $a) { $lines += ("{0},{1},AUTO score={2},1" -f $x.dkp_id, $x.holoo_code, $x.score) }
$lines += "# === REVIEW (approve by removing leading #) ==="
foreach ($x in $r) {
  $dk = $x.digikala_title; if ($dk.Length -gt 40) { $dk = $dk.Substring(0,40) }
  $hn = $x.holoo_name;       if ($hn.Length -gt 30) { $hn = $hn.Substring(0,30) }
  $lines += ("#{0},{1},REVIEW score={2} dk=[{3}] h=[{4}],0" -f $x.dkp_id, $x.holoo_code, $x.score, $dk, $hn)
}
$lines += "# === NONE ==="
foreach ($x in $n) { $lines += ("#{0},,NONE,0" -f $x.dkp_id) }
$lines | Out-File "$scripts\variant_map.csv" -Encoding utf8
Write-Host "  matcher: AUTO=$($a.Count) REVIEW=$($r.Count) NONE=$($n.Count)"