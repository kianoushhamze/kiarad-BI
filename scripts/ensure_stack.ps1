# Recover missing local project services; never terminates a running process.
$ErrorActionPreference='Stop'
$stackRoot=Split-Path -Parent $PSScriptRoot
$stackRoot=[IO.Path]::GetFullPath($stackRoot)
$maintenance=Join-Path $stackRoot 'logs\stack-maintenance.flag'
if((Test-Path -LiteralPath $maintenance) -and (Get-Item -LiteralPath $maintenance).LastWriteTimeUtc -gt [DateTime]::UtcNow.AddMinutes(-15)){
    Write-Output '{"maintenance":true,"services_changed":false}'
    exit 0
}
$stackLock=New-Object Threading.Mutex($false,'Local\KiaradStackRecovery')
if(-not $stackLock.WaitOne(0)){exit 0}
$stackState=[ordered]@{checked_at=(Get-Date).ToUniversalTime().ToString('o');backend=$false;dashboard=$false;passed=$false}
function Test-StackPort([int]$Port){return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)}
function Test-StackHealth([string]$Url){try{return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 12 -ErrorAction Stop).StatusCode -eq 200}catch{return $false}}
function Test-EngineReady{
    $oldPreference=$ErrorActionPreference
    try{$ErrorActionPreference='Continue';docker info --format '{{.ServerVersion}}' 2>$null|Out-Null;return $LASTEXITCODE -eq 0}
    finally{$ErrorActionPreference=$oldPreference}
}
try{
    Set-Location -LiteralPath $stackRoot
    if(-not (Test-EngineReady)){
        $desktopPaths=@((Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),'C:\Program Files\Docker\Docker\Docker Desktop.exe')
        $desktop=$desktopPaths|Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
        if(-not $desktop){throw 'docker_missing'}
        Start-Process -FilePath $desktop -WindowStyle Hidden
        $deadline=(Get-Date).AddSeconds(120)
        do{Start-Sleep -Seconds 5;$engineReady=Test-EngineReady}while(-not $engineReady -and (Get-Date) -lt $deadline)
        if(-not $engineReady){throw 'docker_not_ready'}
    }
    $oldPreference=$ErrorActionPreference
    try{$ErrorActionPreference='Continue';docker compose --project-directory $stackRoot -f (Join-Path $stackRoot 'docker-compose.yml') up -d postgres 2>$null|Out-Null;$composeExit=$LASTEXITCODE}
    finally{$ErrorActionPreference=$oldPreference}
    if($composeExit -ne 0){throw 'postgres_start_failed'}
    $deadline=(Get-Date).AddSeconds(45)
    while(-not (Test-StackPort 5432) -and (Get-Date) -lt $deadline){Start-Sleep -Seconds 3}
    if(-not (Test-StackPort 5432)){throw 'postgres_not_ready'}
    $logs=Join-Path $stackRoot 'logs'
    New-Item -ItemType Directory -Path $logs -Force|Out-Null
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    # Docker-forwarded ports do not always appear in Get-NetTCPConnection on this
    # host; probe the service itself so a healthy stack is never double-started.
    if(-not (Test-StackHealth 'http://127.0.0.1:8000/health')){
        Start-Process -WindowStyle Hidden -FilePath (Join-Path $stackRoot '.venv\Scripts\python.exe') -WorkingDirectory $stackRoot -ArgumentList @('-m','uvicorn','api:app','--host','127.0.0.1','--port','8000','--env-file','.env') -RedirectStandardOutput (Join-Path $logs "recovery-backend-$stamp.log") -RedirectStandardError (Join-Path $logs "recovery-backend-$stamp-error.log")
    }
    if(-not (Test-StackHealth 'http://127.0.0.1:3000/login')){
        $panel=Join-Path $stackRoot 'kiarad-dashboard'
        $server=Join-Path $panel '.next\standalone\server.js'
        if(-not (Test-Path -LiteralPath $server)){throw 'dashboard_build_missing'}
        # Refresh standalone static assets; a stale/empty copy 404s every chunk.
        Push-Location $panel
        try{& node scripts/prepare-standalone.mjs 2>$null|Out-Null}finally{Pop-Location}
        $oldHostname=$env:HOSTNAME;$oldPort=$env:PORT
        try{
            $env:HOSTNAME='0.0.0.0';$env:PORT='3000'
            Start-Process -WindowStyle Hidden -FilePath (Get-Command node -ErrorAction Stop).Source -WorkingDirectory $panel -ArgumentList @('.next/standalone/server.js') -RedirectStandardOutput (Join-Path $logs "recovery-panel-$stamp.log") -RedirectStandardError (Join-Path $logs "recovery-panel-$stamp-error.log")
        }finally{$env:HOSTNAME=$oldHostname;$env:PORT=$oldPort}
    }
    if(-not (Test-StackHealth 'http://127.0.0.1:8081/')){
        $site=Join-Path $stackRoot 'site'
        if(Test-Path -LiteralPath (Join-Path $site 'server.mjs')){
            Start-Process -WindowStyle Hidden -FilePath (Get-Command node -ErrorAction SilentlyContinue).Source -WorkingDirectory $site -ArgumentList 'server.mjs'
        }
    }
    $deadline=(Get-Date).AddSeconds(35)
    do{
        $stackState.backend=Test-StackHealth 'http://127.0.0.1:8000/health'
        $stackState.dashboard=Test-StackHealth 'http://127.0.0.1:3000/login'
        if($stackState.backend -and $stackState.dashboard){break}
        Start-Sleep -Seconds 3
    }while((Get-Date) -lt $deadline)
    $stackState.passed=$stackState.backend -and $stackState.dashboard
}catch{
    # Exception text can contain paths or connection details; report only its type.
    $stackState.error_type=$_.Exception.GetType().Name
}finally{
    $stateDir=Join-Path $stackRoot 'logs'
    New-Item -ItemType Directory -Path $stateDir -Force|Out-Null
    $stackState|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $stateDir 'stack-recovery.json') -Encoding UTF8
    $stackLock.ReleaseMutex();$stackLock.Dispose()
}
$stackState|ConvertTo-Json -Compress
if(-not $stackState.passed){exit 1}
