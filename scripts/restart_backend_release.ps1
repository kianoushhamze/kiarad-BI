param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$listener=Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $process=Get-CimInstance Win32_Process -Filter ("ProcessId="+$listener.OwningProcess)
  if ($process.Name -ne 'python.exe' -or $process.CommandLine -notmatch 'uvicorn\s+api:app' -or $process.CommandLine -notmatch '--port\s+8000') { throw 'unexpected_backend_listener' }
  Stop-Process -Id $process.ProcessId
}
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
Start-Process -WindowStyle Hidden -FilePath (Join-Path $root '.venv\Scripts\python.exe') -WorkingDirectory $root -ArgumentList @('-m','uvicorn','api:app','--host','127.0.0.1','--port','8000','--env-file','.env') -RedirectStandardOutput (Join-Path $root 'logs\backend-release.log') -RedirectStandardError (Join-Path $root 'logs\backend-release-error.log')
