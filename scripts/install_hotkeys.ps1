param([Parameter(Mandatory=$true)][string]$AutoHotkey)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$hotkeyExe = (Get-Item -LiteralPath $AutoHotkey).FullName
if ([IO.Path]::GetFileName($hotkeyExe) -notmatch '^AutoHotkey.*\.exe$') { throw 'Pass the path to AutoHotkey v2.' }
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
foreach ($app in @('schedule','study')) {
    $file = if ($app -eq 'schedule') {'widget-hotkey.ahk'} else {'study-hotkey.ahk'}
    $script = Join-Path $repoRoot ($app+'\hotkey\'+$file)
    $name = if ($app -eq 'schedule') {'StudyWidgetsScheduleHotkey'} else {'StudyWidgetsTimerHotkey'}
    $command = '"'+$hotkeyExe+'" "'+$script+'"'
    New-ItemProperty -Path $runKey -Name $name -Value $command -PropertyType String -Force | Out-Null
    Start-Process -FilePath $hotkeyExe -ArgumentList ('"'+$script+'"') -WindowStyle Hidden
}
Write-Output 'Win+1: Schedule; Win+2: Timer. Helpers start at sign-in; widget windows stay closed until requested.'
