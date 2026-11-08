$ErrorActionPreference = 'Stop'
$taskName = 'KiaradDailyProformaExport'
$task = Get-ScheduledTask -TaskName $taskName
if ($task.Actions.Execute -notcontains 'D:\project\kiaradbi\.venv\Scripts\python.exe') {
    throw 'Unexpected task action; refusing automatic replacement'
}
$backupDir = 'D:\project\kiaradbi\backups\scheduled-tasks'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backupFile = Join-Path $backupDir ('daily-export-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml')
[IO.File]::WriteAllText($backupFile, (Export-ScheduledTask -TaskName $taskName), [Text.Encoding]::UTF8)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -WindowStyle Hidden -File "D:\project\kiaradbi\scripts\run_daily_export.ps1"' -WorkingDirectory 'D:\project\kiaradbi'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -Hidden
Set-ScheduledTask -TaskName $taskName -Action $action -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output 'Existing export task repaired and triggered; check completion separately.'
