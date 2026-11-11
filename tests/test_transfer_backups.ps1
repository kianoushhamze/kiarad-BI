param([Parameter(Mandatory=$true)][string]$PostgresContainer, [switch]$DisposableDatabase)
$ErrorActionPreference = 'Stop'
if (-not $DisposableDatabase) { throw 'This test requires an explicitly disposable database.' }
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'scripts/postgres_container.ps1')
function Run-Docker { & docker @args; if ($LASTEXITCODE -ne 0) { throw 'test_docker_command_failed' } }
$settings = Get-PostgresContainerSettings $PostgresContainer
$root = Join-Path ([IO.Path]::GetTempPath()) ('kiarad-backup-test-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $root 'source'
$target = Join-Path $root 'target'
$restoreContainer = 'kiarad-backup-test-' + [guid]::NewGuid().ToString('N')
$table = 'backup_probe_' + [guid]::NewGuid().ToString('N')
$createdContainer = $false
try {
    New-Item -ItemType Directory -Path (Join-Path $source 'private_uploads') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $source 'kiarad-dashboard/public/uploads') -Force | Out-Null
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    # Deliberately wrong .env values prove that the actual container is authoritative.
    'DB_USER=wrong-user # inline comment' | Set-Content -LiteralPath (Join-Path $source '.env')
    'DB_NAME=wrong-database' | Set-Content -LiteralPath (Join-Path $target '.env')
    'hidden fixture' | Set-Content -LiteralPath (Join-Path $source 'private_uploads/.hidden-test')
    if ($env:OS -eq 'Windows_NT') { (Get-Item -LiteralPath (Join-Path $source 'private_uploads/.hidden-test') -Force).Attributes = [IO.FileAttributes]::Hidden }
    'synthetic media' | Set-Content -LiteralPath (Join-Path $source 'kiarad-dashboard/public/uploads/audit.txt')
    Run-Docker exec $PostgresContainer psql -U $settings.user -d $settings.database -v ON_ERROR_STOP=1 -c "CREATE TABLE public.$table(n INTEGER); INSERT INTO public.$table VALUES (7);" | Out-Null
    & (Join-Path $repo 'scripts/backup_release.ps1') -ProjectRoot $source -ContainerName $PostgresContainer
    $backup = (Get-ChildItem -LiteralPath (Join-Path $source 'private_exports/release-backups') -Directory | Select-Object -First 1).FullName
    Run-Docker run -d --name $restoreContainer -e POSTGRES_PASSWORD=test-only -e POSTGRES_USER=restoreuser -e POSTGRES_DB=restoretest postgres:16 | Out-Null
    $createdContainer = $true
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        & docker exec $restoreContainer pg_isready -U restoreuser -d restoretest 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'restore_test_database_timeout' }
    & (Join-Path $repo 'scripts/restore_release_backup.ps1') -ProjectRoot $target -BackupDirectory $backup -ContainerName $restoreContainer
    & (Join-Path $repo 'scripts/restore_release_media.ps1') -ProjectRoot $target -BackupDirectory $backup
    $number = Run-Docker exec $restoreContainer psql -U restoreuser -d restoretest -tAc "SELECT n FROM public.$table"
    if ($number.Trim() -ne '7') { throw 'restored_database_content_wrong' }
    if ((Get-Content -LiteralPath (Join-Path $target 'private_uploads/.hidden-test') -Raw).Trim() -ne 'hidden fixture') { throw 'hidden_media_not_restored' }
    $databaseBlocked = $false; $mediaBlocked = $false
    try { & (Join-Path $repo 'scripts/restore_release_backup.ps1') -ProjectRoot $target -BackupDirectory $backup -ContainerName $restoreContainer } catch { $databaseBlocked = $_.Exception.Message -eq 'target_database_not_empty' }
    try { & (Join-Path $repo 'scripts/restore_release_media.ps1') -ProjectRoot $target -BackupDirectory $backup } catch { $mediaBlocked = $_.Exception.Message -eq 'media_target_exists_restore_to_empty_folder' }
    if (-not $databaseBlocked -or -not $mediaBlocked) { throw 'overwrite_guard_failed' }
    $dump = Join-Path $backup 'database.dump'
    [IO.File]::AppendAllText($dump, 'tampered')
    $tamperBlocked = $false
    try { & (Join-Path $repo 'scripts/restore_release_backup.ps1') -ProjectRoot $target -BackupDirectory $backup -ContainerName $restoreContainer } catch { $tamperBlocked = $_.Exception.Message -eq 'backup_checksum_mismatch' }
    if (-not $tamperBlocked) { throw 'tampered_backup_was_accepted' }
    @{passed=$true;checks=@('container_settings','database_restore','hidden_media','database_overwrite_guard','media_overwrite_guard','tamper_guard');company_data_used=$false} | ConvertTo-Json
} finally {
    & docker exec $PostgresContainer psql -U $settings.user -d $settings.database -c "DROP TABLE IF EXISTS public.$table" | Out-Null
    if ($createdContainer) { & docker rm -f -v $restoreContainer | Out-Null }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
