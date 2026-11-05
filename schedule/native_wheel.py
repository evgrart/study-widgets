"""Small native, queued Windows input bridge. No pointer speed settings change."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path

_library=None


class NativeWheel:
    def __init__(self,panel):
        global _library
        if _library is None:
            lib=ctypes.WinDLL(str(Path(__file__).with_name('wheel_bridge.dll')))
            lib.WheelRegister.argtypes=[w.HWND];lib.WheelRegister.restype=ctypes.c_int
            lib.WheelPoll.argtypes=[ctypes.c_int,ctypes.POINTER(ctypes.c_int)];lib.WheelPoll.restype=ctypes.c_int
            lib.WheelUnregister.argtypes=[ctypes.c_int]
            lib.WheelSubclassProc.restype=ctypes.c_void_p
            lib.WheelThreadId.restype=w.DWORD
            _library=lib
        self.lib=_library
        self.token=self.lib.WheelRegister(panel)
        if not self.token:raise OSError('Native wheel hook could not start')
        self.subclass_address=self.lib.WheelSubclassProc()
        self.thread_id=self.lib.WheelThreadId()

    def poll(self):
        value=ctypes.c_int()
        for _ in range(256):
            if not self.lib.WheelPoll(self.token,ctypes.byref(value)):break
            yield value.value

    def close(self):
        if self.token:self.lib.WheelUnregister(self.token);self.token=0
