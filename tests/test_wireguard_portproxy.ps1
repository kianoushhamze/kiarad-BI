#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$repairScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/repair_wireguard_portproxy.ps1'
$global:PortproxyFixture = @{
    Address = '10.10.0.2'
    HasAddress = $true
    TunnelRunning = $true
    HasOtherListener = $false
    FailNextAdd = $false
    AddressDelay = 0
    WaitTicks = 0
    Actions = [Collections.Generic.List[string]]::new()
    Bound = @{ '3300' = $true; '8190' = $true }
    Destinations = @{ '3300' = '127.0.0.1'; '8190' = '127.0.0.1' }
    LocalStatus = @{ '3300' = '200'; '8190' = '200' }
}

function Get-Service($Name) {
    $state = if ($Name -eq 'iphlpsvc' -or $global:PortproxyFixture.TunnelRunning) { 'Running' } else { 'Stopped' }
    [pscustomobject]@{ Status = $state }
}
function Get-NetIPAddress {
    [CmdletBinding()] param($InterfaceAlias, $IPAddress, $AddressFamily, $AddressState)
    if ($InterfaceAlias -eq 'fixture' -and $IPAddress -eq $global:PortproxyFixture.Address -and $AddressState -eq 'Preferred') {
        if ($global:PortproxyFixture.HasAddress) { $true }
    }
}
function Get-NetTCPConnection {
    [CmdletBinding()] param($LocalAddress, $LocalPort, $State)
    if ($global:PortproxyFixture.HasOtherListener) { $true }
}
function Set-FixtureTunnelReady($Action) {
    $global:PortproxyFixture.Actions.Add($Action)
    $global:PortproxyFixture.HasAddress = $global:PortproxyFixture.AddressDelay -eq 0
}
function Start-Service($Name) { Set-FixtureTunnelReady 'start' }
function Restart-Service($Name) { Set-FixtureTunnelReady 'restart' }
function Start-Sleep($Seconds) {
    if ($global:PortproxyFixture.AddressDelay -gt 0) {
        $global:PortproxyFixture.WaitTicks++
        if ($global:PortproxyFixture.WaitTicks -ge $global:PortproxyFixture.AddressDelay) {
            $global:PortproxyFixture.HasAddress = $true
        }
    }
}
function curl.exe {
    $uri = [Uri]$args[-1]
    $port = [string]$uri.Port
    $global:LASTEXITCODE = 0
    if ($uri.Host -eq '127.0.0.1') { return $global:PortproxyFixture.LocalStatus[$port] }
    if ($global:PortproxyFixture.Bound[$port]) { return '200' }
    $global:LASTEXITCODE = 7
    '000'
}
function netsh.exe {
    $global:LASTEXITCODE = 0
    if ($args[2] -eq 'show') {
        foreach ($port in '3300','8190') { "  $($global:PortproxyFixture.Address)   $port   $($global:PortproxyFixture.Destinations[$port])   $port" }
        return
    }
    $port = $args[5].Split('=')[1]
    $global:PortproxyFixture.Actions.Add("$($args[2]) $port")
    if ($args[2] -eq 'add') {
        if ($global:PortproxyFixture.FailNextAdd) {
            $global:PortproxyFixture.FailNextAdd = $false
            $global:LASTEXITCODE = 1
        } else { $global:PortproxyFixture.Bound[$port] = $true }
    }
}
function Invoke-Fixture([switch]$Repair) {
    & $repairScript -TunnelName fixture -TunnelAddress $global:PortproxyFixture.Address -Repair:$Repair
}
function Assert-Equal($Actual, $Expected) {
    if ($Actual -ne $Expected) { throw "Expected '$Expected'; got '$Actual'." }
}

try {
    $fixture = $global:PortproxyFixture
    Assert-Equal (@(Invoke-Fixture).Status -join ',') 'Healthy,Healthy'
    $fixture.Bound['3300'] = $false
    Assert-Equal (@(Invoke-Fixture)[0].Status) 'PortproxyUnreachable'
    Assert-Equal $fixture.Actions.Count 0
    Assert-Equal (@(Invoke-Fixture -Repair).Status -join ',') 'Repaired,Healthy'
    Assert-Equal ($fixture.Actions -join ',') 'delete 3300,add 3300'
    Assert-Equal (@(Invoke-Fixture -Repair).Status -join ',') 'Healthy,Healthy'
    Assert-Equal $fixture.Actions.Count 2

    $fixture.Destinations['3300'] = '127.0.0.2'
    $fixture.Bound['3300'] = $false
    $fixture.LocalStatus['8190'] = '503'
    Assert-Equal (@(Invoke-Fixture -Repair).Status -join ',') 'ExpectedRuleNotFound,LoopbackUnavailable'
    $fixture.Destinations['3300'] = '127.0.0.1'
    $fixture.HasOtherListener = $true
    Assert-Equal (@(Invoke-Fixture -Repair)[0].Status) 'ExistingListenerUnhealthy'
    Assert-Equal $fixture.Actions.Count 2

    $fixture.HasOtherListener = $false
    $fixture.HasAddress = $false
    $fixture.TunnelRunning = $false
    $fixture.FailNextAdd = $true
    $fixture.Actions.Clear()
    Assert-Equal (@(Invoke-Fixture).Status -join ',') 'TunnelAddressUnavailable,LoopbackUnavailable'
    Assert-Equal (@(Invoke-Fixture -Repair)[0].Status) 'Repaired'
    Assert-Equal ($fixture.Actions -join ',') 'start,delete 3300,add 3300,add 3300'

    $fixture.HasAddress = $false
    $fixture.TunnelRunning = $true
    $fixture.AddressDelay = 16
    Assert-Equal (@(Invoke-Fixture -Repair)[0].Status) 'Healthy'
    Assert-Equal $fixture.Actions[-1] 'restart'
    Assert-Equal $fixture.WaitTicks 16
    'WireGuard portproxy checks passed.'
} finally {
    Remove-Variable -Name PortproxyFixture -Scope Global
}
