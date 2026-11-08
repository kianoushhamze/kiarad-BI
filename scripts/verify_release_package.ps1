param([string]$PackageRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $PackageRoot).Path
$manifest=Get-Content -LiteralPath (Join-Path $root 'checksums.json') -Raw | ConvertFrom-Json
if (-not $manifest -or @($manifest).Count -lt 1) { throw 'empty_release_manifest' }
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($item in $manifest) {
  if (-not $item.path -or [IO.Path]::IsPathRooted($item.path)) { throw 'invalid_release_path' }
  $target=[IO.Path]::GetFullPath((Join-Path $root $item.path))
  if (-not $target.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($target)) { throw 'invalid_or_duplicate_release_path' }
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw ('release_file_missing:'+$item.path) }
  if ((Get-Item -LiteralPath $target).Length -ne $item.bytes -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $item.sha256) { throw ('release_file_changed:'+$item.path) }
}
foreach ($required in @('kiarad-images.tar','postgres-image.tar','docker-compose.yml','deploy.ps1','backup\database.dump','backup\manifest.json')) {
  if (-not $seen.Contains([IO.Path]::GetFullPath((Join-Path $root $required)))) { throw ('release_manifest_incomplete:'+$required) }
}
[ordered]@{status='verified';files=@($manifest).Count} | ConvertTo-Json -Compress
