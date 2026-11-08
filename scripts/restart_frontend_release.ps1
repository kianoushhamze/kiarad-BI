param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$dashboard=Join-Path $root 'kiarad-dashboard'
Push-Location $dashboard
try {
  & node scripts/prepare-standalone.mjs
  if ($LASTEXITCODE -ne 0) { throw 'standalone_prepare_failed' }
  $listener=Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) {
    $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listener.OwningProcess)
    if ($process.Name -ne 'node.exe' -or $process.CommandLine -notmatch '(standalone[/\\]server\.js|next-server)') { throw 'unexpected_frontend_listener' }
    Stop-Process -Id $process.ProcessId
  }
  $previousHost=$env:HOSTNAME;$previousPort=$env:PORT
  try {
    # A stale KIARAD_JWT_SECRET inherited from the user environment once broke
    # token verification for every host-side caller; the panel must not need it.
    $env:KIARAD_JWT_SECRET=$null
    $env:HOSTNAME='0.0.0.0';$env:PORT='3000'
    Start-Process -WindowStyle Hidden -FilePath (Get-Command node).Source -WorkingDirectory $dashboard -ArgumentList @('.next/standalone/server.js') -RedirectStandardOutput (Join-Path $root 'logs\frontend-release.log') -RedirectStandardError (Join-Path $root 'logs\frontend-release-error.log')
  } finally { $env:HOSTNAME=$previousHost;$env:PORT=$previousPort }
} finally { Pop-Location }
