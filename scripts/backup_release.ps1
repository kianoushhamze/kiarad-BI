param(
  [string]$ProjectRoot = "D:\project\kiaradbi",
  [string]$ContainerName = "kiarad-postgres"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destination = Join-Path $root ("private_exports\release-backups\" + $stamp)
New-Item -ItemType Directory -Path $destination -Force | Out-Null

$envFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envFile)) { throw "env_file_missing" }

$values = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
  $trimmed = $line.Trim()
  if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
  $parts = $trimmed.Split("=", 2)
  $values[$parts[0]] = $parts[1].Trim().Trim('"').Trim("'")
}
$dbUser = if ($values.DB_USER) { $values.DB_USER } else { "kiarad" }
$dbName = if ($values.DB_NAME) { $values.DB_NAME } else { "kiaradbi" }

$running = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") { throw "postgres_container_not_running" }

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
if ($mediaSources.Count -gt 0) {
  $mediaArchive = Join-Path $destination "media.zip"
  Compress-Archive -LiteralPath $mediaSources -DestinationPath $mediaArchive -CompressionLevel Optimal
}

$manifest = [ordered]@{
  created_at = (Get-Date).ToString("o")
  database_file = "database.dump"
  database_bytes = (Get-Item -LiteralPath $dump).Length
  database_sha256 = (Get-FileHash -LiteralPath $dump -Algorithm SHA256).Hash.ToLowerInvariant()
  media_file = if ($mediaArchive) { "media.zip" } else { $null }
  media_bytes = if ($mediaArchive) { (Get-Item -LiteralPath $mediaArchive).Length } else { 0 }
  media_sha256 = if ($mediaArchive) { (Get-FileHash -LiteralPath $mediaArchive -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
  contains_env = $false
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination "manifest.json") -Encoding utf8
$manifest | ConvertTo-Json -Compress
