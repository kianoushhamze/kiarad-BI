$ErrorActionPreference = 'Stop'
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw ('docker_failed:' + ($args -join ' ')) }
}
function Assert-LinuxDocker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is not installed.' }
    $platform = Invoke-Docker version --format '{{.Server.Os}}/{{.Server.Arch}}'
    if ($platform.Trim() -ne 'linux/amd64') { throw ('Linux amd64 Docker engine required; found: ' + $platform) }
}
function Read-Release {
    param([string]$KitRoot)
    $release = Get-Content -LiteralPath (Join-Path $KitRoot 'release.json') -Raw | ConvertFrom-Json
    if ($release.source_commit -notmatch '^[0-9a-f]{40}$') { throw 'Invalid source commit.' }
    return $release
}
function Assert-Kit {
    param([string]$KitRoot)
    $root = (Resolve-Path -LiteralPath $KitRoot).Path
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $items = Get-Content -LiteralPath (Join-Path $root 'checksums.json') -Raw | ConvertFrom-Json
    if (@($items).Count -lt 5) { throw 'Kit manifest is incomplete.' }
    foreach ($item in $items) {
        if (-not $item.path -or [IO.Path]::IsPathRooted($item.path)) { throw 'Invalid kit path.' }
        $path = [IO.Path]::GetFullPath((Join-Path $root $item.path))
        if (-not $path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($path)) { throw 'Unsafe or duplicate kit path.' }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Missing kit file: ' + $item.path) }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) { throw ('Kit checksum failed: ' + $item.path) }
    }
    foreach ($required in @('source.zip','release.json','compose.transfer.yml','common.ps1')) {
        if (-not $seen.Contains([IO.Path]::GetFullPath((Join-Path $root $required)))) { throw ('Missing manifest entry: ' + $required) }
    }
}
function Assert-FreePorts {
    param([int[]]$Ports)
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    foreach ($port in $Ports) {
        if (@($listeners | Where-Object { $_.Port -eq $port }).Count -gt 0) { throw ('Port is busy: ' + $port) }
    }
}
function Write-JsonFile {
    param($Value, [string]$Path)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}

function Get-ArchiveConfigDigest {
    param([string]$Archive, [string]$ImageName, [string]$Directory)
    # Read only files from docker image save. Hash the unmodified config bytes.
    & tar -xf $Archive -C $Directory manifest.json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read saved image manifest.' }
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Directory 'manifest.json') | ConvertFrom-Json
    $rows = @($manifest | Where-Object { $_.RepoTags -ccontains $ImageName })
    if ($rows.Count -ne 1 -or $rows[0].Config -cnotmatch '^(?:blobs/sha256/[0-9a-f]{64}|[0-9a-f]{64}\.json)$') {
        throw ('Missing or ambiguous saved image config: ' + $ImageName)
    }
    $config = $rows[0].Config
    & tar -xf $Archive -C $Directory $config
    if ($LASTEXITCODE -ne 0) { throw ('Cannot read saved image config: ' + $ImageName) }
    return 'sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Directory $config)).Hash.ToLowerInvariant()
}

function Assert-LoadedImage {
    param([string]$ImageName, [string]$ExpectedId)
    $info = @(Invoke-Docker image inspect $ImageName | ConvertFrom-Json)
    if ($ExpectedId -cnotmatch '^sha256:[0-9a-f]{64}$' -or $info.Count -ne 1 -or
        $info[0].Os -ne 'linux' -or $info[0].Architecture -ne 'amd64') { throw ('Loaded image mismatch: ' + $ImageName) }
    if ($info[0].Id -ceq $ExpectedId) { return }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ('kiarad-image-check-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temp | Out-Null
    try {
        $archive = Join-Path $temp 'loaded.tar'
        Invoke-Docker image save -o $archive $ImageName | Out-Null
        if ((Get-ArchiveConfigDigest $archive $ImageName $temp) -cne $ExpectedId) { throw ('Loaded image mismatch: ' + $ImageName) }
    } finally { Remove-Item -LiteralPath $temp -Recurse -Force }
}
