$ErrorActionPreference = "Stop"
$sourceRoot = "C:\Users\kiano\Downloads"
$destination = "D:\project\disk-space-recovery-20261102\installers"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$manifest = @()
$files = Get-ChildItem -LiteralPath $sourceRoot -File | Where-Object { $_.Length -gt 30MB -and $_.Extension -in @('.exe','.msi','.msix','.7z') }
foreach ($file in $files) {
  $resolved = (Resolve-Path -LiteralPath $file.FullName).Path
  if ((Split-Path -Parent $resolved) -ne $sourceRoot) { throw "unexpected_source" }
  $target = Join-Path $destination $file.Name
  if (Test-Path -LiteralPath $target) { throw "destination_exists" }
  Copy-Item -LiteralPath $resolved -Destination $target
  $sourceHash = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash
  if ($sourceHash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) { throw "copy_hash_mismatch" }
  Remove-Item -LiteralPath $resolved
  $manifest += [pscustomobject]@{source=$resolved;destination=$target;bytes=$file.Length;sha256=$sourceHash}
}
$manifest | Export-Csv -LiteralPath (Join-Path $destination 'moves.csv') -Encoding UTF8 -NoTypeInformation
[ordered]@{files=$manifest.Count;bytes=($manifest | Measure-Object bytes -Sum).Sum;free_c=(Get-PSDrive C).Free;recovery=$destination} | ConvertTo-Json -Compress
