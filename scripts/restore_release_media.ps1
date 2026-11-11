param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot), [Parameter(Mandatory=$true)][string]$BackupDirectory)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$backup=(Resolve-Path -LiteralPath $BackupDirectory).Path
$manifest=Get-Content -LiteralPath (Join-Path $backup 'manifest.json') -Raw | ConvertFrom-Json
if (-not $manifest.media_file) { Write-Output 'no_media_in_backup'; exit 0 }
$archive=Join-Path $backup 'media.zip'
if (-not $manifest.media_sha256 -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.media_sha256.ToLowerInvariant()) { throw 'media_checksum_missing_or_mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[System.IO.Compression.ZipFile]::OpenRead($archive)
$plan=@()
$targets=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
try {
  foreach ($entry in $zip.Entries) {
    $name=$entry.FullName.Replace('\','/')
    if ($name.EndsWith('/')) { continue }
    if ($name -match '(^/|:|(^|/)\.\.(/|$))') { throw 'unsafe_archive_path' }
    if ($name.StartsWith('uploads/')) { $target=Join-Path $root ('kiarad-dashboard/public/'+$name) }
    elseif ($name.StartsWith('private_uploads/')) { $target=Join-Path $root $name }
    else { throw 'unknown_media_root' }
    $target=[IO.Path]::GetFullPath($target)
    if (-not $targets.Add($target)) { throw 'duplicate_media_target' }
    if (-not $target.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'unsafe_target' }
    if (Test-Path -LiteralPath $target) { throw 'media_target_exists_restore_to_empty_folder' }
    $parent=Split-Path -Parent $target
    while ($parent.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
      if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'media_target_is_link' }
      $parent=Split-Path -Parent $parent
      if (-not $parent) { break }
    }
    $plan+=@{entry=$entry;target=$target}
  }
  foreach ($item in $plan) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $item.target) -Force | Out-Null
    [IO.Compression.ZipFileExtensions]::ExtractToFile($item.entry,$item.target,$false)
  }
} finally { $zip.Dispose() }
[ordered]@{status='restored';files=$plan.Count;existing_files_overwritten=$false} | ConvertTo-Json -Compress
