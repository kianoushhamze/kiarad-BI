$ErrorActionPreference = "Stop"
$destination = "D:\project\disk-space-recovery-20261102"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$cacheRoot = "C:\Users\kiano\.cache\codex-runtimes"
$tempRoot = "C:\Users\kiano\AppData\Local\Temp"
$sources = @(
  Get-ChildItem -LiteralPath $cacheRoot -Directory | Where-Object {
    $_.Name.StartsWith("codex-primary-runtime.previous-") -or $_.Name.StartsWith("codex-runtime-install-")
  } | ForEach-Object FullName
)
$sources += Join-Path $tempRoot "DiagOutputDir"
$processes = Get-CimInstance Win32_Process | ForEach-Object { $_.ExecutablePath; $_.CommandLine }
$manifest = @()
foreach ($source in $sources) {
  if (-not (Test-Path -LiteralPath $source)) { continue }
  $resolved = (Resolve-Path -LiteralPath $source).Path
  if (-not ($resolved.StartsWith($cacheRoot + "\", [StringComparison]::OrdinalIgnoreCase) -or $resolved -eq (Join-Path $tempRoot "DiagOutputDir"))) { throw "unexpected_source" }
  $active = @($processes | Where-Object { $_ -and $_.IndexOf($resolved,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
  if ($active.Count) { Write-Output "active_path_skipped"; continue }
  $target = Join-Path $destination (Split-Path -Leaf $resolved)
  if (Test-Path -LiteralPath $target) { throw "destination_exists" }
  $bytes = (Get-ChildItem -LiteralPath $resolved -File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  try {
    Move-Item -LiteralPath $resolved -Destination $target -ErrorAction Stop
    $manifest += [pscustomobject]@{ source=$resolved; destination=$target; bytes=$bytes }
  } catch { Write-Output ("move_skipped:" + (Split-Path -Leaf $resolved)) }
}
$manifest | Export-Csv -LiteralPath (Join-Path $destination "moves.csv") -NoTypeInformation -Encoding UTF8
[ordered]@{ moved=$manifest.Count; moved_bytes=($manifest | Measure-Object bytes -Sum).Sum; free_c=(Get-PSDrive C).Free; recovery=$destination } | ConvertTo-Json -Compress
