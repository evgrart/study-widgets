param([string]$Python = 'python', [switch]$NoShortcuts, [switch]$BackgroundSync,
      [string]$AutoHotkey = '', [switch]$SkipDependencies)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & $Python -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python with venv and Tk is required.' }
}
if (-not $SkipDependencies) {
    & $pythonExe -m pip install --disable-pip-version-check -r (Join-Path $repoRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $pythonExe -c 'import tkinter, icalendar, recurring_ical_events, playwright.sync_api, tzdata'
if ($LASTEXITCODE -ne 0) { throw 'Required dependencies are missing.' }
& (Join-Path $repoRoot 'scripts\build_native.ps1')
if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($destination in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))) {
        foreach ($app in @('schedule','study')) {
            $label = if ($app -eq 'schedule') {'Study Widgets - Schedule'} else {'Study Widgets - Timer'}
            $shortcut = $shell.CreateShortcut((Join-Path $destination ($label+'.lnk')))
            $shortcut.TargetPath = Join-Path $repoRoot '.venv\Scripts\pythonw.exe'
            $shortcut.Arguments = '"' + (Join-Path $repoRoot ($app+'\widget.py')) + '"'
            $shortcut.WorkingDirectory = Join-Path $repoRoot $app
            $icon = if ($app -eq 'schedule') {'widget.ico'} else {'study.ico'}
            $shortcut.IconLocation = (Join-Path $repoRoot ($app+'\'+$icon))+',0'
            $shortcut.Save()
        }
    }
}
if ($BackgroundSync) {
    & (Join-Path $repoRoot 'schedule\install_shad_sync.ps1')
    & (Join-Path $repoRoot 'schedule\install_tasks_sync.ps1')
}
if ($AutoHotkey) { & (Join-Path $repoRoot 'scripts\install_hotkeys.ps1') -AutoHotkey $AutoHotkey }
Write-Output 'Ready. Run .venv\Scripts\python.exe configure.py to connect your own calendar/account.'
