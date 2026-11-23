#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]{1,32}$')]
    [string]$TunnelName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')]
    [string]$TunnelAddress,

    [switch]$Repair
)

$ErrorActionPreference = 'Stop'
$address = [Net.IPAddress]::Parse($TunnelAddress)
$octets = $address.GetAddressBytes()
if ($address.ToString() -cne $TunnelAddress -or -not (
    $octets[0] -eq 10 -or
    ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
    ($octets[0] -eq 192 -and $octets[1] -eq 168)
)) { throw 'TunnelAddress must be a canonical private IPv4 address.' }

$routes = [ordered]@{ '3300' = '/api/health'; '8190' = '/buy/' }
$serviceName = 'WireGuardTunnel$' + $TunnelName
$tunnel = Get-Service -Name $serviceName
$ipHelper = Get-Service -Name 'iphlpsvc'

function Test-PortHttp($HostAddress, $Port, $Path) {
    $status = & curl.exe --silent --fail --noproxy '*' --max-time 5 --output NUL --write-out '%{http_code}' ("http://{0}:{1}{2}" -f $HostAddress, $Port, $Path)
    return $LASTEXITCODE -eq 0 -and $status -eq '200'
}

function Test-TunnelAddress {
    return [bool](Get-NetIPAddress -InterfaceAlias $TunnelName -IPAddress $TunnelAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue)
}

$loopback = @{}
foreach ($port in $routes.Keys) { $loopback[$port] = Test-PortHttp '127.0.0.1' $port $routes[$port] }
$tunnelReady = Test-TunnelAddress

if ($Repair -and -not $tunnelReady -and ($loopback.Values -contains $true)) {
    if ($tunnel.Status -eq 'Stopped') {
        Start-Service -Name $serviceName
    } elseif ($tunnel.Status -eq 'Running') {
        Restart-Service -Name $serviceName
    }
    # WireGuardNT can wait 15 seconds for the adapter before the address is assigned.
    $tunnelReady = Test-TunnelAddress
    for ($attempt = 0; $attempt -lt 25 -and -not $tunnelReady; $attempt++) {
        Start-Sleep -Seconds 1
        $tunnelReady = Test-TunnelAddress
    }
}

$rules = @(& netsh.exe interface portproxy show v4tov4)
if ($LASTEXITCODE -ne 0) { throw 'Could not read Windows portproxy rules.' }

foreach ($port in $routes.Keys) {
    $match = @($rules | Select-String -Pattern ('^\s*' + [regex]::Escape($TunnelAddress) + '\s+' + $port + '\s+(\S+)\s+(\d+)\s*$'))
    $expectedRule = $match.Count -eq 1 -and $match[0].Matches[0].Groups[1].Value -eq '127.0.0.1' -and
        $match[0].Matches[0].Groups[2].Value -eq [string]$port
    $reachable = $tunnelReady -and (Test-PortHttp $TunnelAddress $port $routes[$port])
    $state = if (-not $loopback[$port]) { 'LoopbackUnavailable' }
        elseif (-not $tunnelReady) { 'TunnelAddressUnavailable' }
        elseif ($ipHelper.Status -ne 'Running') { 'IpHelperUnavailable' }
        elseif (-not $expectedRule) { 'ExpectedRuleNotFound' }
        elseif ($reachable) { 'Healthy' }
        else { 'PortproxyUnreachable' }

    if ($Repair -and $state -eq 'PortproxyUnreachable') {
        if (Get-NetTCPConnection -LocalAddress $TunnelAddress -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
            $state = 'ExistingListenerUnhealthy'
        } else {
            & netsh.exe interface portproxy delete v4tov4 "listenaddress=$TunnelAddress" "listenport=$port" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not remove the stale portproxy rule for port $port." }
            $addRule = @('interface', 'portproxy', 'add', 'v4tov4', "listenaddress=$TunnelAddress", "listenport=$port", 'connectaddress=127.0.0.1', "connectport=$port")
            & netsh.exe @addRule | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Start-Sleep -Seconds 1
                & netsh.exe @addRule | Out-Null
            }
            if ($LASTEXITCODE -ne 0) { throw "Could not restore the portproxy rule for port $port." }
            $reachable = Test-PortHttp $TunnelAddress $port $routes[$port]
            $state = if ($reachable) { 'Repaired' } else { 'ReboundButUnreachable' }
        }
    }

    [pscustomobject]@{
        Port = [int]$port
        LoopbackHealthy = $loopback[$port]
        TunnelAddressReady = $tunnelReady
        ExpectedRulePresent = $expectedRule
        TunnelHttpHealthy = $reachable
        Status = $state
    }
}
