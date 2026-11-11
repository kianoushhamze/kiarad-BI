param([Parameter(Mandatory=$true)][string]$Destination, [switch]$CheckHoloo)
. (Join-Path $PSScriptRoot 'common.ps1')
$dest = (Resolve-Path -LiteralPath $Destination).Path
$installed = Get-Content -LiteralPath (Join-Path $dest 'install-receipt.json') -Raw | ConvertFrom-Json
$checks = @()
foreach ($url in @('http://127.0.0.1:8800/health','http://127.0.0.1:3300/login','http://127.0.0.1:3300/api/health','http://127.0.0.1:8190/buy/','http://127.0.0.1:8190/api/public/catalog')) {
    try { $ok = (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 20).StatusCode -eq 200 } catch { $ok = $false }
    $checks += [ordered]@{url=$url;passed=$ok}
}
$holooOk = $null
if ($CheckHoloo) {
    $compose = @('compose','--env-file',(Join-Path $dest '.env'),'-p',$installed.project,'-f',(Join-Path $dest 'compose.transfer.yml'))
    try {
        $lines = @(Invoke-Docker @compose exec -T backend python scripts/check_holoo_login.py)
        $records = @($lines | ForEach-Object { try { $_ | ConvertFrom-Json } catch {} })
        $holooOk = @($records | Where-Object { $_.login_ok -eq $true }).Count -gt 0
    } catch { $holooOk = $false }
}
$report = [ordered]@{checked_at=(Get-Date).ToString('o');source_commit=$installed.source_commit;checks=$checks;holoo_login_ok=$holooOk;company_data_reconciled=$false;roles_accepted=$false;mobile_https_accepted=$false;production_ready=$false}
Write-JsonFile $report (Join-Path $dest 'stage-checks.json')
$report | ConvertTo-Json -Depth 5
if (@($checks | Where-Object { -not $_.passed }).Count -gt 0 -or ($CheckHoloo -and -not $holooOk)) { throw 'Stage checks failed. Keep the old installation and inspect logs.' }
Write-Host 'Technical checks passed. Complete the manual company acceptance checklist before cutover.'
