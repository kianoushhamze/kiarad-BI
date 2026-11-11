param([string]$ReportPath = (Join-Path $PSScriptRoot 'server-inspection.json'))
. (Join-Path $PSScriptRoot 'common.ps1')
$report = [ordered]@{
    inspected_at = (Get-Date).ToString('o')
    powershell = $PSVersionTable.PSVersion.ToString()
    docker_available = $false
    docker_platform = $null
    containers = @()
    postgres_mounts = @()
    listeners = @()
    free_drives = @()
    cloudflare_services = @()
    scheduled_tasks = @()
    changes_made = $false
}
try {
    $report.docker_platform = Invoke-Docker version --format '{{.Server.Os}}/{{.Server.Arch}}'
    $report.docker_available = $true
    $lines = @(Invoke-Docker ps -a --format '{{json .}}')
    $report.containers = @($lines | ForEach-Object {
        $entry = $_ | ConvertFrom-Json
        [ordered]@{name=$entry.Names;image=$entry.Image;status=$entry.Status;ports=$entry.Ports}
    })
    foreach ($container in $report.containers) {
        if ($container.image -like '*postgres*') {
            $mounts = Invoke-Docker inspect --format '{{json .Mounts}}' $container.name | ConvertFrom-Json
            $report.postgres_mounts += [ordered]@{container=$container.name;mounts=@($mounts | Select-Object Type,Name,Source,Destination)}
        }
    }
} catch { $report.docker_error = 'Docker engine unavailable; start Docker Desktop and select Linux containers.' }
$ports = @(3000,3100,3300,8000,8090,8190,8800,5432)
$report.listeners = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -in $ports } | ForEach-Object { [ordered]@{address=$_.Address.ToString();port=$_.Port} })
$report.free_drives = @(Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used)
if (Get-Command Get-Service -ErrorAction SilentlyContinue) {
    $report.cloudflare_services = @(Get-Service -ErrorAction SilentlyContinue | Where-Object Name -like '*cloudflar*' | Select-Object Name,Status)
}
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    $report.scheduled_tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'kiarad|holoo|digikala' } | Select-Object TaskName,TaskPath,State)
}
Write-JsonFile $report $ReportPath
Write-Host ('Inspection saved: ' + $ReportPath)
Write-Host ('Docker: ' + $report.docker_platform)
Write-Host 'No services, scheduled tasks, tunnel settings or data were changed.'
