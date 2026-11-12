"""Capture only this app's native window for local visual verification."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import struct


def capture(hwnd, output, screen=False):
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
    user.GetWindowDC.argtypes = [w.HWND]
    user.GetWindowDC.restype = w.HDC
    user.GetDC.argtypes = [w.HWND]
    user.GetDC.restype = w.HDC
    user.ReleaseDC.argtypes = [w.HWND, w.HDC]
    gdi.CreateCompatibleDC.argtypes = [w.HDC]
    gdi.CreateCompatibleDC.restype = w.HDC
    gdi.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = w.HBITMAP
    gdi.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
    gdi.SelectObject.restype = w.HGDIOBJ
    gdi.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]
    gdi.DeleteDC.argtypes = [w.HDC]
    gdi.BitBlt.argtypes = [w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HDC,ctypes.c_int,ctypes.c_int,w.DWORD]
    rect = w.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    width, height = rect.right-rect.left, rect.bottom-rect.top
    hdc = user.GetDC(None) if screen else user.GetWindowDC(hwnd)
    mem = gdi.CreateCompatibleDC(hdc)
    bitmap = gdi.CreateCompatibleBitmap(hdc, width, height)
    old = gdi.SelectObject(mem, bitmap)
    try:
        if screen:
            if not gdi.BitBlt(mem,0,0,width,height,hdc,rect.left,rect.top,0x40CC0020):
                raise ctypes.WinError()
        elif not user.PrintWindow(hwnd, mem, 2):
            raise ctypes.WinError()
        gdi.SelectObject(mem, old)
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0)
        info = ctypes.create_string_buffer(header)
        pixels = ctypes.create_string_buffer(width*height*4)
        if not gdi.GetDIBits(mem, bitmap, 0, height, pixels, info, 0):
            raise ctypes.WinError()
        Path(output).write_bytes(struct.pack("<2sIHHI", b"BM", 54+len(pixels), 0, 0, 54)+header+pixels.raw)
    finally:
        gdi.SelectObject(mem, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(mem)
        user.ReleaseDC(None if screen else hwnd, hdc)


