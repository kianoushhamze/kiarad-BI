param([Parameter(Mandatory=$true)][string]$KitRoot, [switch]$DockerGuards)
$ErrorActionPreference = 'Stop'
. (Join-Path $KitRoot 'common.ps1')
Assert-Kit $KitRoot
$temp = Join-Path ([IO.Path]::GetTempPath()) ('kiarad-kit-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$checks = @('valid_kit')
try {

    # Exercise the config fallback with the two docker-save config path formats.
    $fixture = Join-Path $temp 'image-fixture'
    New-Item -ItemType Directory -Path (Join-Path $fixture 'blobs/sha256') -Force | Out-Null
    $sample = Join-Path $fixture 'sample'
    [IO.File]::WriteAllBytes($sample, [Text.Encoding]::UTF8.GetBytes('{"architecture":"amd64","os":"linux"}'))
    $hash = (Get-FileHash -LiteralPath $sample -Algorithm SHA256).Hash.ToLowerInvariant()
    foreach ($key in @(($hash + '.json'), ('blobs/sha256/' + $hash))) {
        $readDir = Join-Path $temp ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $readDir | Out-Null
        Copy-Item -LiteralPath $sample -Destination (Join-Path $fixture $key)
        $json = '[{"RepoTags":["test:stage"],"Config":"' + $key + '"}]'
        [IO.File]::WriteAllText((Join-Path $fixture 'manifest.json'), $json)
        $archive = Join-Path $temp 'fixture.tar'
        & tar -cf $archive -C $fixture manifest.json $key
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create image fixture.' }
        if ((Get-ArchiveConfigDigest $archive 'test:stage' $readDir) -cne ('sha256:' + $hash)) { throw 'Config digest mismatch.' }
        $blocked = $false
        try { Get-ArchiveConfigDigest $archive 'test:other' $readDir } catch { $blocked = $_.Exception.Message -like '*saved image config*' }
        if (-not $blocked) { throw 'Wrong image tag accepted.' }
    }
    $checks += 'saved_image_config_digest'
    $copy = Join-Path $temp 'copy'
    Copy-Item -LiteralPath $KitRoot -Destination $copy -Recurse
    Add-Content -LiteralPath (Join-Path $copy 'README-fa.md') -Value 'tampered'
    $blocked = $false
    try { Assert-Kit $copy } catch { $blocked = $_.Exception.Message -like '*checksum failed*' }
    if (-not $blocked) { throw 'Kit corruption guard failed.' }
    $checks += 'kit_corruption_guard'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead((Join-Path $KitRoot 'source.zip'))
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName -match '(^\.env$|^secrets/|^private_uploads/|^private_exports/|/node_modules/|^\.git/)') { throw 'Runtime secrets or build material in source archive.' }
        }
    } finally { $zip.Dispose() }
    $checks += 'source_excludes_runtime'
    $blocked = $false
    try { & (Join-Path $KitRoot '06-Enable-Sync.ps1') -Destination (Join-Path $temp 'absent') } catch { $blocked = $_.Exception.Message -like '*Complete company acceptance*' }
    if (-not $blocked) { throw 'Sync acceptance guard failed.' }
    $checks += 'sync_acceptance_guard'
    if ($DockerGuards) {
        $exists = Join-Path $temp 'existing-install'
        New-Item -ItemType Directory -Path $exists | Out-Null
        'preserve' | Set-Content -LiteralPath (Join-Path $exists 'data.txt')
        $blocked = $false
        try { & (Join-Path $KitRoot '04-Install-Stage.ps1') -Destination $exists } catch { $blocked = $_.Exception.Message -like '*Destination exists*' }
        if (-not $blocked -or (Get-Content -LiteralPath (Join-Path $exists 'data.txt')).Trim() -ne 'preserve') { throw 'Existing installation guard failed.' }
        $checks += 'existing_installation_guard'
        $blocked = $false
        try { & (Join-Path $KitRoot '03-Capture-Data.ps1') -SourceRoot $exists } catch { $blocked = $_.Exception.Message -like '*Stop source writes*' }
        if (-not $blocked) { throw 'Capture write-freeze guard failed.' }
        $checks += 'capture_freeze_guard'
        $payload = Join-Path $temp 'unsafe-payload'
        New-Item -ItemType Directory -Path $payload | Out-Null
        Write-JsonFile @{files=@(@{path='../escape';sha256='invalid'})} (Join-Path $payload 'payload.json')
        $blocked = $false
        try { & (Join-Path $KitRoot '04-Install-Stage.ps1') -Destination (Join-Path $temp 'new-install') -PayloadDirectory $payload } catch { $blocked = $_.Exception.Message -like '*Unsafe or duplicate payload path*' }
        if (-not $blocked -or (Test-Path -LiteralPath (Join-Path $temp 'new-install'))) { throw 'Payload traversal guard failed.' }
        $checks += 'payload_path_guard'
    }
    @{passed=$true;checks=$checks;company_data_used=$false} | ConvertTo-Json -Depth 3
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
