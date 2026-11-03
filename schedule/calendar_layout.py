"""Uncapped task layout and Windows monitor work-area bounds."""
import ctypes
from ctypes import wintypes as w


def task_layout(groups, viewport_height, header, row_step, gap, extra_top, minimum_grid, bottom_gap):
    rows = max((len(items) for items in groups), default=0)
    task_bottom = header + (rows*row_step+gap if rows else 0)
    grid_top = task_bottom+extra_top
    content_height = max(viewport_height, grid_top+minimum_grid+bottom_gap)
    return rows,task_bottom,content_height


def work_area(hwnd):
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]
    user = ctypes.WinDLL('user32',use_last_error=True)
    user.MonitorFromWindow.argtypes = [w.HWND,w.DWORD]
    user.MonitorFromWindow.restype = w.HMONITOR
    user.GetMonitorInfoW.argtypes = [w.HMONITOR,ctypes.POINTER(MonitorInfo)]
    monitor = user.MonitorFromWindow(hwnd,2)
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    if not user.GetMonitorInfoW(monitor,ctypes.byref(info)):
        raise ctypes.WinError()
    rect = info.work
    return rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top
