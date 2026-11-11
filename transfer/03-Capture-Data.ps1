param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$PostgresContainer = 'kiarad-postgres',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'payload'),
    [switch]$WritesStopped,
    [switch]$SchedulesStopped
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Kit $PSScriptRoot
Assert-LinuxDocker
if (-not $WritesStopped -or -not $SchedulesStopped) { throw 'Stop source writes and all old synchronization schedules first; then pass -WritesStopped -SchedulesStopped.' }
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $source '.env') -PathType Leaf)) { throw 'Source .env is missing.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$out = (Resolve-Path -LiteralPath $OutputDirectory).Path
foreach ($required in @('images.tar','images.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $out $required) -PathType Leaf)) { throw ('Build images before stopping writes: ' + $required) }
}
if ($out.StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Payload must be outside the source project folder.' }
$release = Read-Release $PSScriptRoot
$imageManifest = Get-Content -LiteralPath (Join-Path $out 'images.json') -Raw | ConvertFrom-Json
if ($imageManifest.source_commit -ne $release.source_commit) { throw 'Build the images for this exact kit before capture.' }
foreach ($name in @('backup','runtime.env','secrets','speech-models','data.json','payload.json')) {
    if (Test-Path -LiteralPath (Join-Path $out $name)) { throw ('Capture destination exists: ' + $name) }
}
$temp = Join-Path $out ('capture-tools-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'source.zip') -DestinationPath $temp
$started = Get-Date
& (Join-Path $temp 'scripts\backup_release.ps1') -ProjectRoot $source -ContainerName $PostgresContainer
$backups = @(Get-ChildItem -LiteralPath (Join-Path $source 'private_exports\release-backups') -Directory |
    Where-Object { $_.CreationTime -ge $started -and (Test-Path -LiteralPath (Join-Path $_.FullName 'manifest.json')) } | Sort-Object Name -Descending)
if ($backups.Count -ne 1) { throw 'Expected exactly one fresh backup; inspect the source backup folder.' }
$backupManifest = Get-Content -LiteralPath (Join-Path $backups[0].FullName 'manifest.json') -Raw | ConvertFrom-Json
if ($backupManifest.postgres_major -gt 16) { throw 'Source PostgreSQL is newer than 16; do not restore it into this kit.' }
Copy-Item -LiteralPath $backups[0].FullName -Destination (Join-Path $out 'backup') -Recurse
Copy-Item -LiteralPath (Join-Path $source '.env') -Destination (Join-Path $out 'runtime.env')
if (Test-Path -LiteralPath (Join-Path $source 'secrets')) { Copy-Item -LiteralPath (Join-Path $source 'secrets') -Destination (Join-Path $out 'secrets') -Recurse }
if (Test-Path -LiteralPath (Join-Path $source 'data\speech-models')) { Copy-Item -LiteralPath (Join-Path $source 'data\speech-models') -Destination (Join-Path $out 'speech-models') -Recurse }
$hashes = @(Get-ChildItem -LiteralPath $out -File -Recurse | Where-Object { -not $_.FullName.StartsWith($temp + [IO.Path]::DirectorySeparatorChar) -and $_.FullName -ne (Join-Path $out 'payload.json') } | ForEach-Object {
    [ordered]@{path=$_.FullName.Substring($out.Length+1);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
})
Write-JsonFile ([ordered]@{captured_at=(Get-Date).ToString('o');source_commit=$release.source_commit;source_container=$PostgresContainer;files=$hashes}) (Join-Path $out 'payload.json')
Remove-Item -LiteralPath $temp -Recurse -Force
Write-Host ('Capture ready: ' + $out)
Write-Host 'Keep source writes and schedules stopped through cutover. This payload contains credentials; transfer it privately.'
