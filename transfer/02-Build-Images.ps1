param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'payload'))
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Kit $PSScriptRoot
Assert-LinuxDocker
$release = Read-Release $PSScriptRoot
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$out = (Resolve-Path -LiteralPath $OutputDirectory).Path
if ((Test-Path -LiteralPath (Join-Path $out 'images.tar')) -or (Test-Path -LiteralPath (Join-Path $out 'images.json'))) { throw 'Image export already exists; use a new output folder.' }
$build = Join-Path $out ('build-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'source.zip') -DestinationPath $build
$backend = 'kiarad-transfer-backend:' + $release.image_tag
$frontend = 'kiarad-transfer-frontend:' + $release.image_tag
Push-Location $build
try {
    Invoke-Docker build --label ('org.opencontainers.image.revision=' + $release.source_commit) -f Dockerfile.backend -t $backend .
    Invoke-Docker build --label ('org.opencontainers.image.revision=' + $release.source_commit) --build-arg KIARAD_API_URL=http://backend:8000 --build-arg NEXT_PUBLIC_API_URL=http://backend:8000 -f kiarad-dashboard/Dockerfile -t $frontend .
    Invoke-Docker pull postgres:16
    Invoke-Docker pull node:22-slim
    Invoke-Docker pull --platform linux/amd64 traccar/traccar:6.17.0-alpine
    $images = @($backend,$frontend,'postgres:16','node:22-slim','traccar/traccar:6.17.0-alpine')
    $records = @()
    foreach ($name in $images) {
        $info = Invoke-Docker image inspect $name | ConvertFrom-Json
        if ($info[0].Os -ne 'linux' -or $info[0].Architecture -ne 'amd64') { throw ('Image platform mismatch: ' + $name) }
        $records += [ordered]@{name=$name;id=$info[0].Id}
    }
    $temporaryArchive = Join-Path $out 'images.tar.partial'
    Invoke-Docker save -o $temporaryArchive @images
    Move-Item -LiteralPath $temporaryArchive -Destination (Join-Path $out 'images.tar')
    Write-JsonFile ([ordered]@{source_commit=$release.source_commit;images=$records;archive_sha256=(Get-FileHash -LiteralPath (Join-Path $out 'images.tar') -Algorithm SHA256).Hash}) (Join-Path $out 'images.json')
} finally { Pop-Location }
Remove-Item -LiteralPath $build -Recurse -Force
Write-Host ('Images exported: ' + $out)
Write-Host 'Company database and credentials have not been copied. Capture them only after stopping writes and schedules.'
