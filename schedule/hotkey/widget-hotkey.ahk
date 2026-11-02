#Requires AutoHotkey v2.0
#SingleInstance Force
#NoTrayIcon
#UseHook

DetectHiddenWindows(True)
SplitPath(A_ScriptDir,, &WidgetRoot)
RuntimeRoot := EnvGet("LOCALAPPDATA") "\StudyWidgets\Schedule"
DirCreate(RuntimeRoot)
PythonW := WidgetRoot "\..\.venv\Scripts\pythonw.exe"
ActivationCount := 0
HotkeyPid := DllCall("GetCurrentProcessId", "UInt")
VerifiedHwnd := 0
VerifiedPid := 0
VerifiedProcess := 0
LaunchPid := 0

if A_Args.Length && A_Args[1] = "--check" {
    FileAppend("Hotkey script syntax OK`n", "*")
    ExitApp(0)
}
if A_Args.Length && A_Args[1] = "--show-once" {
    ShowSchedule()
    ExitApp(0)
}
WriteStatus("ready")

#1::{
    ToggleSchedule()
    KeyWait("1")
}

ToggleSchedule() {
    hwnd := FindWidgetWindow()
    if hwnd && DllCall("IsWindowVisible", "Ptr", hwnd, "Int") && !DllCall("IsIconic", "Ptr", hwnd, "Int") {
        target := "ahk_id " hwnd
        try {
            PostMessage(0x10, 0, 0, , target)
            WriteStatus("hidden")
        } catch {
            WriteStatus("error")
        }
        return
    }
    ShowSchedule()
}

FindWidgetWindow() {
    global WidgetRoot, RuntimeRoot, VerifiedHwnd, VerifiedPid, VerifiedProcess, LaunchPid
    try {
        text := FileRead(RuntimeRoot "\status.json", "UTF-8")
        if !RegExMatch(text, '"window_handle"\s*:\s*(\d+)', &match)
            return 0
        hwnd := Integer(match[1])
        target := "ahk_id " hwnd
        if !WinExist(target)
            return 0
        pid := WinGetPID(target)
        if hwnd = VerifiedHwnd && pid = VerifiedPid && VerifiedProcess && DllCall("WaitForSingleObject", "Ptr", VerifiedProcess, "UInt", 0, "UInt") = 258
            return hwnd
        if pid = LaunchPid {
            RememberWidget(hwnd, pid)
            return hwnd
        }
        processes := ComObjGet("winmgmts:").ExecQuery("SELECT CommandLine FROM Win32_Process WHERE ProcessId=" pid)
        for process in processes {
            if InStr(process.CommandLine, WidgetRoot "\widget.py") {
                RememberWidget(hwnd, pid)
                return hwnd
            }
        }
    }
    return 0
}

RememberWidget(hwnd, pid) {
    global VerifiedHwnd, VerifiedPid, VerifiedProcess
    if VerifiedProcess
        DllCall("CloseHandle", "Ptr", VerifiedProcess)
    VerifiedHwnd := hwnd
    VerifiedPid := pid
    VerifiedProcess := DllCall("OpenProcess", "UInt", 0x100000, "Int", false, "UInt", pid, "Ptr")
}

ShowSchedule() {
    global WidgetRoot, RuntimeRoot, PythonW, ActivationCount, LaunchPid
    try {
        hwnd := FindWidgetWindow()
        if hwnd {
            FileAppend("", RuntimeRoot "\show.request", "UTF-8-RAW")
        } else {
            Run('"' PythonW '" "' WidgetRoot '\widget.py"', WidgetRoot, "Hide", &LaunchPid)
        }
        Loop 200 {
            hwnd := FindWidgetWindow()
            if hwnd {
                target := "ahk_id " hwnd
                WinShow(target)
                WinRestore(target)
                WinActivate(target)
                ActivationCount += 1
                WriteStatus("activated")
                return
            }
            Sleep(30)
        }
        WriteStatus("window_not_ready")
    } catch {
        WriteStatus("error")
    }
}

WriteStatus(state) {
    global WidgetRoot, RuntimeRoot, ActivationCount, HotkeyPid
    target := RuntimeRoot "\hotkey-status.json"
    temporary := target ".tmp"
    text := '{"state":"' state '","hotkey":"Win+1","pid":' HotkeyPid ',"activations":' ActivationCount '}'
    try {
        if FileExist(temporary)
            FileDelete(temporary)
        FileAppend(text, temporary, "UTF-8-RAW")
        FileMove(temporary, target, 1)
    }
}
