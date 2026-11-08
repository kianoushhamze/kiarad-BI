$ErrorActionPreference='Stop'
$stackRoot=Split-Path -Parent $PSScriptRoot
$scriptPath=Join-Path $PSScriptRoot 'ensure_stack.ps1'
if(-not (Test-Path -LiteralPath $scriptPath)){throw 'راه‌انداز موجود نیست'}
$taskName='KiaradStackRecovery'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($existing){
    $backupDir=Join-Path $stackRoot 'backups\scheduled-tasks'
    New-Item -ItemType Directory -Path $backupDir -Force|Out-Null
    Export-ScheduledTask -TaskName $taskName|Set-Content -LiteralPath (Join-Path $backupDir ('stack-recovery-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.xml')) -Encoding UTF8
}
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "'+$scriptPath+'"') -WorkingDirectory $stackRoot
$login=New-ScheduledTaskTrigger -AtLogOn -User $identity
$periodic=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($login,$periodic) -Settings $settings -Principal $principal -Force|Out-Null
Write-Output 'بازیابی سرویس‌های محلی پس از ورود همین کاربر به ویندوز و بررسی پنج‌دقیقه‌ای ثبت شد؛ رمز یا دسترسی مدیریتی جدید ایجاد نشد.'
