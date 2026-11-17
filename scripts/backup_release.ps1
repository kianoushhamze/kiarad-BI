param(
  [string]$ProjectRoot = "D:\project\kiaradbi",
  [string]$ContainerName = "kiarad-postgres"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
$destination = Join-Path $root ("private_exports\release-backups\" + $stamp)
New-Item -ItemType Directory -Path $destination -Force | Out-Null

$envFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envFile)) { throw "env_file_missing" }

. (Join-Path $PSScriptRoot 'postgres_container.ps1')
$settings = Get-PostgresContainerSettings -ContainerName $ContainerName
$dbUser = $settings.user
$dbName = $settings.database

$running = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") { throw "postgres_container_not_running" }

$versionNumber = docker exec $ContainerName psql -U $dbUser -d $dbName -tAc 'SHOW server_version_num'
if ($LASTEXITCODE -ne 0) { throw 'postgres_version_check_failed' }
$postgresMajor = [int]([math]::Floor([int]$versionNumber.Trim() / 10000))

$inside = "/tmp/kiarad-release-" + $stamp + ".dump"
$dump = Join-Path $destination "database.dump"
docker exec $ContainerName pg_dump -U $dbUser -d $dbName -Fc -f $inside
if ($LASTEXITCODE -ne 0) { throw "database_dump_failed" }
try {
  docker cp ($ContainerName + ":" + $inside) $dump
  if ($LASTEXITCODE -ne 0) { throw "database_copy_failed" }
} finally {
  docker exec $ContainerName rm -f $inside | Out-Null
}

$mediaSources = @(
  (Join-Path $root "private_uploads"),
  (Join-Path $root "kiarad-dashboard\public\uploads")
) | Where-Object { Test-Path -LiteralPath $_ }
$mediaArchive = $null
$mediaFiles = @()
foreach ($folder in $mediaSources) {
  $entries = @(Get-ChildItem -LiteralPath $folder -Recurse -Force)
  if ((Get-Item -LiteralPath $folder -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'media_source_is_link' }
  foreach ($entry in $entries) {
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'media_source_contains_link' }
    if (-not $entry.PSIsContainer) {
      $relative = $entry.FullName.Substring($folder.Length + 1).Replace('\','/')
      $mediaFiles += @{source=$entry.FullName;entry=(Split-Path -Leaf $folder) + '/' + $relative}
    }
  }
}
if ($mediaFiles.Count -gt 0) {
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $mediaArchive = Join-Path $destination "media.zip"
  $zip = [IO.Compression.ZipFile]::Open($mediaArchive, [IO.Compression.ZipArchiveMode]::Create)
  try {
    foreach ($file in $mediaFiles) {
      [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.source, $file.entry, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
  } finally { $zip.Dispose() }
}

$manifest = [ordered]@{
  created_at = (Get-Date).ToString("o")
  database_file = "database.dump"
  database_name = $dbName
  postgres_major = $postgresMajor
  database_user = $dbUser
  media_files = $mediaFiles.Count
  database_bytes = (Get-Item -LiteralPath $dump).Length
  database_sha256 = (Get-FileHash -LiteralPath $dump -Algorithm SHA256).Hash.ToLowerInvariant()
  media_file = if ($mediaArchive) { "media.zip" } else { $null }
  media_bytes = if ($mediaArchive) { (Get-Item -LiteralPath $mediaArchive).Length } else { 0 }
  media_sha256 = if ($mediaArchive) { (Get-FileHash -LiteralPath $mediaArchive -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
  contains_env = $false
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination "manifest.json") -Encoding utf8
$manifest | ConvertTo-Json -Compress
