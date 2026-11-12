param(
 [Parameter(Mandatory=$true)][string]$Destination,
 [Parameter(Mandatory=$true)][string]$ClientUrl
)
. (Join-Path $PSScriptRoot 'common.ps1')
$dest=(Resolve-Path -LiteralPath $Destination).Path
$receipt=Get-Content -LiteralPath (Join-Path $dest 'install-receipt.json') -Raw | ConvertFrom-Json
$release=Read-Release $PSScriptRoot
if($receipt.source_commit -ne $release.source_commit){throw 'Installed source does not match this transfer kit.'}
Assert-FreePorts @(5055)
$envFile=Join-Path $dest '.env'
$compose=@('compose','--env-file',$envFile,'-p',$receipt.project,'-f',(Join-Path $dest 'compose.transfer.yml'),'--profile','traccar')
$runArgs=@('run','--rm','--pull','never')
if([Environment]::OSVersion.Platform -eq [PlatformID]::Unix){
 $taskUid=(& id -u).Trim();$taskGid=(& id -g).Trim()
 $runArgs+=@('--user',($taskUid+':'+$taskGid))
}
Invoke-Docker @runArgs --mount ("type=bind,source="+$dest+",target=/setup") ("kiarad-transfer-backend:"+$release.image_tag) python /app/scripts/configure_traccar.py --root /setup --client-url $ClientUrl
Invoke-Docker @compose config --quiet
Invoke-Docker @compose up -d --no-build --pull never --wait backend
Invoke-Docker @compose up -d --no-build --pull never --force-recreate traccar
Write-Host 'GPS gateway started on loopback port5055. Configure HTTPS reverse proxy before phones connect; staff must start their own consented shift.'
