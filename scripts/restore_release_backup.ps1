param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [Parameter(Mandatory=$true)][string]$BackupDirectory,
  [string]$ContainerName = "kiarad-postgres"
)
$ErrorActionPreference = "Stop"
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$backup=(Resolve-Path -LiteralPath $BackupDirectory).Path
$manifest=Get-Content -LiteralPath (Join-Path $backup 'manifest.json') -Raw | ConvertFrom-Json
$dump=Join-Path $backup 'database.dump'
if ((Get-FileHash -LiteralPath $dump -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.database_sha256.ToLowerInvariant()) { throw 'backup_checksum_mismatch' }
. (Join-Path $PSScriptRoot 'postgres_container.ps1')
$settings=Get-PostgresContainerSettings -ContainerName $ContainerName
$dbUser=$settings.user
$dbName=$settings.database
$count=docker exec $ContainerName psql -U $dbUser -d $dbName -tAc "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"
if ($LASTEXITCODE -ne 0) { throw 'target_database_unavailable' }
if ([int]$count.Trim() -ne 0) { throw 'target_database_not_empty' }
$inside='/tmp/kiarad-restore-'+[guid]::NewGuid().ToString('N')+'.dump'
docker cp $dump ("${ContainerName}:"+$inside)
if ($LASTEXITCODE -ne 0) { throw 'backup_copy_failed' }
try {
  docker exec $ContainerName pg_restore -U $dbUser -d $dbName --single-transaction --exit-on-error --no-owner --no-privileges $inside
  if ($LASTEXITCODE -ne 0) { throw 'backup_restore_failed' }
} finally { docker exec $ContainerName rm -f $inside | Out-Null }
[ordered]@{status='restored';container=$ContainerName;existing_data_overwritten=$false;media_restored=$false} | ConvertTo-Json -Compress
