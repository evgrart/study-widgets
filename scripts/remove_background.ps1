$ErrorActionPreference = 'Stop'
foreach ($name in @('StudyWidgetsSHADSync','StudyWidgetsGoogleTasksSync')) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
foreach ($name in @('StudyWidgetsScheduleHotkey','StudyWidgetsTimerHotkey','StudyWidgetsSchedule')) {
    Remove-ItemProperty -Path $runKey -Name $name -ErrorAction SilentlyContinue
}
Write-Output 'Removed this repository installation from background sync and sign-in startup. User records are kept.'
