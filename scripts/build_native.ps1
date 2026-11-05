$ErrorActionPreference = 'Stop'
$scheduleDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\schedule'))
$source = Join-Path $scheduleDir 'wheel_bridge.c'
$target = Join-Path $scheduleDir 'wheel_bridge.dll'
if (Get-Command gcc -ErrorAction SilentlyContinue) {
    & gcc -shared -O2 -s $source -o $target -lcomctl32 -luser32
    if ($LASTEXITCODE -ne 0) { throw 'Native scrolling bridge compilation failed.' }
    Write-Output 'Built native wheel bridge.'
} elseif (Get-Command cl -ErrorAction SilentlyContinue) {
    Push-Location $scheduleDir
    try {
        & cl /nologo /LD /O2 wheel_bridge.c /link user32.lib comctl32.lib /OUT:wheel_bridge.dll
        if ($LASTEXITCODE -ne 0) { throw 'Native scrolling bridge compilation failed.' }
    } finally { Pop-Location }
} else { Write-Warning 'No C compiler found. Scrolling will use the Python fallback. Re-run this script with GCC or MSVC to enable the native bridge.' }
