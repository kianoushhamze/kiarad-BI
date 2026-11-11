param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [switch]$CompanyAcceptancePassed,
    [switch]$OldSchedulersStopped,
    [switch]$EnableAssistantAutomations
)
. (Join-Path $PSScriptRoot 'common.ps1')
if (-not $CompanyAcceptancePassed -or -not $OldSchedulersStopped) { throw 'Complete company acceptance and stop ALL old schedulers first.' }
$dest = (Resolve-Path -LiteralPath $Destination).Path
$installed = Get-Content -LiteralPath (Join-Path $dest 'install-receipt.json') -Raw | ConvertFrom-Json
$checks = Get-Content -LiteralPath (Join-Path $dest 'stage-checks.json') -Raw | ConvertFrom-Json
if ($checks.source_commit -ne $installed.source_commit -or $checks.holoo_login_ok -ne $true -or @($checks.checks | Where-Object { -not $_.passed }).Count -gt 0) { throw 'Run 05-Check-Stage.ps1 -CheckHoloo successfully before enabling sync.' }
$envFile = Join-Path $dest '.env'
$envText = [IO.File]::ReadAllText($envFile)
$envText = [regex]::Replace($envText, '(?m)^\s*(?:HOLO_AUTO_REFRESH_ENABLED|KIARAD_AUTOMATIONS_DISABLED)\s*=.*\r?$', '')
$disabled = if ($EnableAssistantAutomations) { '0' } else { '1' }
$envText += "`r`nHOLO_AUTO_REFRESH_ENABLED=1`r`nKIARAD_AUTOMATIONS_DISABLED=$disabled`r`n"
[IO.File]::WriteAllText($envFile, $envText, [Text.UTF8Encoding]::new($false))
Invoke-Docker compose --env-file $envFile -p $installed.project -f (Join-Path $dest 'compose.transfer.yml') up -d --no-build --pull never --wait backend
Write-Host 'Holoo automatic refresh enabled on the new installation. Verify completion and financial totals; a login test alone does not confirm freshness.'
