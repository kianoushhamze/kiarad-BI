param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$PayloadDirectory = (Join-Path $PSScriptRoot 'payload'),
    [string]$ProjectName = 'kiaradstage20261113',
    [string]$HolooUrl = 'http://192.168.1.2:8080/TncHoloo/api'
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Kit $PSScriptRoot
Assert-LinuxDocker
$release = Read-Release $PSScriptRoot
if ($ProjectName -notmatch '^[a-z0-9][a-z0-9_-]*$') { throw 'Invalid Compose project name.' }
if (Test-Path -LiteralPath $Destination) { throw 'Destination exists. Inspect the previous attempt; do not overwrite it.' }
$payload = (Resolve-Path -LiteralPath $PayloadDirectory).Path
$receipt = Get-Content -LiteralPath (Join-Path $payload 'payload.json') -Raw | ConvertFrom-Json
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $receipt.files) {
    if (-not $entry.path -or [IO.Path]::IsPathRooted($entry.path)) { throw 'Invalid payload path.' }
    $file = [IO.Path]::GetFullPath((Join-Path $payload $entry.path))
    if (-not $file.StartsWith($payload + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($file)) { throw 'Unsafe or duplicate payload path.' }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { throw ('Payload checksum failed: ' + $entry.path) }
}
foreach ($required in @('runtime.env','images.tar','images.json','backup\manifest.json','backup\database.dump')) {
    if (-not $seen.Contains([IO.Path]::GetFullPath((Join-Path $payload $required)))) { throw ('Payload incomplete: ' + $required) }
}
foreach ($file in @(Get-ChildItem -LiteralPath $payload -File -Recurse)) {
    if ($file.FullName -ne (Join-Path $payload 'payload.json') -and -not $seen.Contains($file.FullName)) { throw 'Unexpected file in payload; capture it again.' }
}
$images = Get-Content -LiteralPath (Join-Path $payload 'images.json') -Raw | ConvertFrom-Json
if ($images.source_commit -ne $release.source_commit -or (Get-FileHash -LiteralPath (Join-Path $payload 'images.tar') -Algorithm SHA256).Hash -ne $images.archive_sha256) { throw 'Wrong release images or damaged archive.' }
Assert-FreePorts @(3300,8800,8190)
if (@(Invoke-Docker ps -aq --filter ('label=com.docker.compose.project=' + $ProjectName)).Count -gt 0) { throw 'Stage project containers already exist.' }
if (@(Invoke-Docker volume ls -q --filter ('label=com.docker.compose.project=' + $ProjectName)).Count -gt 0) { throw 'Stage project volumes already exist.' }
if (@(Invoke-Docker volume ls --format '{{.Name}}') -contains ($ProjectName + '_postgres_data')) { throw 'Stage database volume name already exists.' }
Invoke-Docker load -i (Join-Path $payload 'images.tar')
$expected = @("kiarad-transfer-backend:$($release.image_tag)","kiarad-transfer-frontend:$($release.image_tag)",'postgres:16','node:22-slim')
foreach ($name in $expected) {
    $record = @($images.images | Where-Object name -eq $name)
    if ($record.Count -ne 1) { throw ('Image missing in export manifest: ' + $name) }
    $info = Invoke-Docker image inspect $name | ConvertFrom-Json
    if ($info[0].Id -ne $record[0].id -or $info[0].Os -ne 'linux' -or $info[0].Architecture -ne 'amd64') { throw ('Loaded image mismatch: ' + $name) }
}
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'source.zip') -DestinationPath $Destination
$dest = (Resolve-Path -LiteralPath $Destination).Path
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compose.transfer.yml') -Destination (Join-Path $dest 'compose.transfer.yml')
$envText = [IO.File]::ReadAllText((Join-Path $payload 'runtime.env'))
$envText = [regex]::Replace($envText, '(?m)^\s*(?:HOLO_URL|HOLO_API_URL|HOLO_AUTO_REFRESH_ENABLED|KIARAD_AUTOMATIONS_DISABLED|KIARAD_AGENT_DISABLED|KIARAD_ROUTINES_DISABLED|KIARAD_OUTBOUND_ENABLED|KIARAD_RELEASE_TAG)\s*=.*\r?$', '')
if ($HolooUrl -notmatch '^https?://[^\r\n]+$') { throw 'Invalid Holoo URL.' }
$envText += "`r`nHOLO_URL=$HolooUrl`r`nHOLO_API_URL=$HolooUrl`r`nHOLO_AUTO_REFRESH_ENABLED=0`r`nKIARAD_AUTOMATIONS_DISABLED=1`r`nKIARAD_AGENT_DISABLED=1`r`nKIARAD_ROUTINES_DISABLED=1`r`nKIARAD_OUTBOUND_ENABLED=0`r`nKIARAD_RELEASE_TAG=$($release.image_tag)`r`n"
[IO.File]::WriteAllText((Join-Path $dest '.env'), $envText, [Text.UTF8Encoding]::new($false))
if (Test-Path -LiteralPath (Join-Path $payload 'secrets')) { Copy-Item -LiteralPath (Join-Path $payload 'secrets') -Destination $dest -Recurse }
if (Test-Path -LiteralPath (Join-Path $payload 'speech-models')) {
    New-Item -ItemType Directory -Path (Join-Path $dest 'data') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $payload 'speech-models') -Destination (Join-Path $dest 'data\speech-models') -Recurse
}
$compose = @('compose','--env-file',(Join-Path $dest '.env'),'-p',$ProjectName,'-f',(Join-Path $dest 'compose.transfer.yml'))
Invoke-Docker @compose config --quiet
Invoke-Docker @compose up -d --no-build --pull never --wait postgres
$pg = Invoke-Docker @compose ps -q postgres
& (Join-Path $dest 'scripts\restore_release_backup.ps1') -ProjectRoot $dest -BackupDirectory (Join-Path $payload 'backup') -ContainerName $pg.Trim()
& (Join-Path $dest 'scripts\restore_release_media.ps1') -ProjectRoot $dest -BackupDirectory (Join-Path $payload 'backup')
Invoke-Docker @compose run --rm --no-deps --pull never backend python scripts/check_release_database.py
Invoke-Docker @compose run --rm --no-deps --pull never backend python scripts/run_migrations.py
Invoke-Docker @compose up -d --no-build --pull never --wait --wait-timeout 240 backend frontend storefront
Write-JsonFile ([ordered]@{source_commit=$release.source_commit;project=$ProjectName;destination=$dest;installed_at=(Get-Date).ToString('o');dashboard='http://127.0.0.1:3300/login';storefront='http://127.0.0.1:8190/buy/';sync_enabled=$false;automations_enabled=$false;production_cutover=$false}) (Join-Path $dest 'install-receipt.json')
Write-Host 'STAGE READY: panel http://127.0.0.1:3300/login and shop http://127.0.0.1:8190/buy/'
Write-Host 'Existing installation and tunnel were not changed. Complete company acceptance before cutover.'
