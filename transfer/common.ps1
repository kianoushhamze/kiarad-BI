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
