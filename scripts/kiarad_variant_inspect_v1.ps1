# =====================================================================
#  KIARAD - VARIANT INSPECT v1 (2026-10-31)
#  Real digikala data is on disk (50 rows, source=digikala) but the
#  loader found no sku/seller_code/code field, so the site map is empty.
#  This script (zero input) shows exactly what one variant item looks
#  like and which fields could carry the holoo code.
#  Report goes to logs + clipboard + notepad. Paste it in the chat.
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("digikala_variant_inspect_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD DIGIKALA VARIANT INSPECT v1"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="

$files = Get-ChildItem -Path $logs -Filter "digikala_variants_p*.json" -ErrorAction SilentlyContinue | Sort-Object Name
if (-not $files -or $files.Count -eq 0) {
  & $say " no digikala_variants_p*.json in logs - run the sync task first"
  $lines | Out-File -FilePath $reportPath -Encoding utf8
  Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
  exit 1
}
& $say (" files: " + $files.Count)
$total = 0
$first = $null
foreach ($f in $files) {
  $j = $null
  try { $j = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
  if ($null -eq $j) { & $say (" bad json: " + $f.Name); continue }
  $items = $j.data.items
  if ($null -eq $items) { $items = $j.items }
  if ($null -eq $items) { & $say (" no items: " + $f.Name); continue }
  & $say (" " + $f.Name + " -> items: " + $items.Count)
  $total = $total + $items.Count
  if ($null -eq $first -and $items.Count -gt 0) { $first = $items | Select-Object -First 1 }
}
& $say (" total items: " + $total)

& $say ""
& $say "=== KEYS OF THE FIRST ITEM (top level) ==="
if ($null -ne $first) {
  foreach ($k in $first.PSObject.Properties.Name) { & $say ("   " + $k) }

  & $say ""
  & $say "=== FIRST ITEM, PRETTY JSON (trimmed) ==="
  $pj = ""
  try { $pj = $first | ConvertTo-Json -Depth 8 } catch { $pj = "convert failed" }
  if ($pj.Length -gt 1600) { $pj = $pj.Substring(0, 1600) + "`n... (trimmed)" }
  foreach ($ln in ($pj -split "`n")) { & $say ("   " + $ln) }

  & $say ""
  & $say "=== CANDIDATE FIELDS ACROSS ALL FILES (sku/code/seller/ean/barcode) ==="
  $found = New-Object System.Collections.Hashtable
  $seen = New-Object System.Collections.Hashtable
  foreach ($f in $files) {
    $j = $null
    try { $j = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
    $items = $j.data.items
    if ($null -eq $items) { $items = $j.items }
    if ($null -eq $items) { continue }
    foreach ($it in $items) {
      foreach ($p in $it.PSObject.Properties) {
        $nm = $p.Name
        if ($nm -match "(?i)sku|code|seller|ean|barcode|attribute") {
          if (-not $found.ContainsKey($nm)) { $found.set_Item($nm, (New-Object System.Collections.ArrayList)) }
          $lst = $found.get_Item($nm)
          $val = ""
          if ($null -ne $p.Value) { $val = "$($p.Value)" }
          if ($val -ne "" -and $val.Length -gt 60) { $val = $val.Substring(0, 60) + "..." }
          if ($val -ne "" -and -not $seen.ContainsKey($nm + "|" + $val)) {
            $seen.set_Item($nm + "|" + $val, 1)
            if ($lst.Count -lt 8) { $null = $lst.Add($val) }
          }
        }
      }
    }
  }
  if ($found.Count -eq 0) {
    & $say "   NO field matching sku/code/seller/ean/barcode/attribute exists in items"
  } else {
    foreach ($key in $found.Keys) {
      $lst = $found.get_Item($key)
      & $say ("   " + $key + "  (samples up to 8):")
      foreach ($v in $lst) { & $say ("      " + $v) }
    }
  }

  & $say ""
  & $say "=== FIRST 5 TITLES ==="
  $i = 0
  foreach ($f in $files) {
    $j = $null
    try { $j = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
    $items = $j.data.items
    if ($null -eq $items) { $items = $j.items }
    if ($null -eq $items) { continue }
    foreach ($it in $items) {
      if ($i -ge 5) { break }
      $t = $it.title
      if ($null -eq $t) { $t = $it.fa_title }
      if ($null -eq $t) { $t = $it.name }
      & $say ("   " + $t)
      $i = $i + 1
    }
    if ($i -ge 5) { break }
  }
} else {
  & $say " nothing readable found"
}

& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
