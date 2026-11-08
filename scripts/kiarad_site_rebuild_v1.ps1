$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"; $scripts = "$root\scripts"; $logs = "$root\logs"; $site = "$root\site"
New-Item -ItemType Directory -Force -Path $logs,$site | Out-Null
$pgU = "kiarad"; $pgD = "kiaradbi"
docker exec kiarad-postgres psql -U $pgU -d $pgD -q -c "COPY (SELECT code, name, category, price, stock FROM products WHERE is_active = 1 ORDER BY code) TO STDOUT WITH CSV HEADER" 2>$null | Out-File "$scripts\products_site_export.csv" -Encoding utf8
$rows = Import-Csv "$scripts\products_site_export.csv" -Encoding utf8
$dj = "$site\data.json"; $bk = "$site\data_demo_backup.json"
if ((Test-Path $dj) -and (-not (Test-Path $bk))) { Copy-Item $dj $bk }
$outProds = @()
$cats = @{}
$minP = [double]::MaxValue; $maxP = 0; $zero = 0
foreach ($r in $rows) {
    $code = $r.code.Trim()
    $title = $r.name.Trim()
    $cat = if ($r.category -and $r.category.Trim() -ne "") { $r.category.Trim() } else { "سایر" }
    $pr = 0; try { $pr = [double]$r.price } catch {}
    $st = 0; try { $st = [double]$r.stock } catch {}
    $pT = [long]([Math]::Round($pr / 10))
    if ($pT -lt 0) { $pT = 0 }
    if ($pT -eq 0) { $zero += 1 }
    if ($pT -gt 0 -and $pT -lt $minP) { $minP = $pT }
    if ($pT -gt $maxP) { $maxP = $pT }
    $cats[$cat] = 1
    $it = [ordered]@{ holoo_code = $code; title = $title; category = $cat; price_holoo = $pT; stock_holoo = [int]$st }
    $outProds += [pscustomobject]$it
}
$dataObj = [ordered]@{
    store = [ordered]@{ name = "فروشگاه کیاراد"; tagline = "کاتالوگ محصولات با قیمت به‌روز هلو" }
    categories = @($cats.Keys | Sort-Object)
    products = $outProds
    generated_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    source = "products (holoo); price in Toman (Rial/10)"
}
$dataObj | ConvertTo-Json -Depth 10 | Out-File $dj -Encoding utf8
Write-Host ("site: products=" + $outProds.Count + " cats=" + $cats.Count + " minP=" + $minP + " maxP=" + $maxP + " zero=" + $zero)
Write-Host ("data.json=" + (Get-Item $dj).Length + "b")
$loader = "$scripts\kiarad_loader_v1.ps1"
if (Test-Path $loader) {
    Write-Host "running loader (merge digikala)..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $loader 2>&1 | ForEach-Object { Write-Host "  | " + $_ }
}