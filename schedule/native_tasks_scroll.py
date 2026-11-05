"""Windows wheel/pan input for the Tasks pane, before Tk can discard it.

All other windows and all input outside this pane are passed through untouched.
Callbacks only queue scroll distances; the Tk thread applies them during its idle loop.
"""
import ctypes
from ctypes import wintypes as w
from collections import deque
import os
import time
import tkinter as tk

u=ctypes.WinDLL('user32',use_last_error=True)
c=ctypes.WinDLL('comctl32',use_last_error=True)
k=ctypes.WinDLL('kernel32',use_last_error=True)
LRESULT=ctypes.c_ssize_t
MOUSEPROC=ctypes.WINFUNCTYPE(LRESULT,ctypes.c_int,w.WPARAM,w.LPARAM)
SUBCLASSPROC=ctypes.WINFUNCTYPE(LRESULT,w.HWND,w.UINT,w.WPARAM,w.LPARAM,ctypes.c_size_t,ctypes.c_size_t)


class MouseInfo(ctypes.Structure):
    _fields_=[('pt',w.POINT),('data',w.DWORD),('flags',w.DWORD),
              ('time',w.DWORD),('extra',ctypes.c_size_t)]


class PointShort(ctypes.Structure):
    _fields_=[('x',ctypes.c_short),('y',ctypes.c_short)]


class GestureInfo(ctypes.Structure):
    _fields_=[('size',w.UINT),('flags',w.DWORD),('kind',w.DWORD),('target',w.HWND),
              ('point',PointShort),('instance',w.DWORD),('sequence',w.DWORD),
              ('arguments',ctypes.c_ulonglong),('extra_size',w.UINT)]


class GestureConfig(ctypes.Structure):
    _fields_=[('kind',w.DWORD),('want',w.DWORD),('block',w.DWORD)]


u.SetWindowsHookExW.argtypes=[ctypes.c_int,MOUSEPROC,w.HINSTANCE,w.DWORD]
u.SetWindowsHookExW.restype=w.HHOOK
u.UnhookWindowsHookEx.argtypes=[w.HHOOK]
u.CallNextHookEx.argtypes=[w.HHOOK,ctypes.c_int,w.WPARAM,w.LPARAM]
u.CallNextHookEx.restype=LRESULT
u.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
u.IsWindowVisible.argtypes=[w.HWND]
u.IsWindow.argtypes=[w.HWND]
u.WindowFromPoint.argtypes=[w.POINT]
u.WindowFromPoint.restype=w.HWND
u.GetCursorPos.argtypes=[ctypes.POINTER(w.POINT)]
u.GetAncestor.argtypes=[w.HWND,w.UINT]
u.GetAncestor.restype=w.HWND
u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
u.GetGestureInfo.argtypes=[w.HANDLE,ctypes.POINTER(GestureInfo)]
u.CloseGestureInfoHandle.argtypes=[w.HANDLE]
u.SetGestureConfig.argtypes=[w.HWND,w.DWORD,w.UINT,ctypes.POINTER(GestureConfig),w.UINT]
c.SetWindowSubclass.argtypes=[w.HWND,SUBCLASSPROC,ctypes.c_size_t,ctypes.c_size_t]
c.RemoveWindowSubclass.argtypes=[w.HWND,SUBCLASSPROC,ctypes.c_size_t]
c.DefSubclassProc.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
c.DefSubclassProc.restype=LRESULT
k.GetModuleHandleW.argtypes=[w.LPCWSTR]
k.GetModuleHandleW.restype=w.HMODULE


class NativeTasksScroll:
    def __init__(self,panel,scroll_delta,scroll_pixels):
        self.panel,self.root=panel,panel.winfo_toplevel()
        self.scroll_delta,self.scroll_pixels=scroll_delta,scroll_pixels
        self.panel_handle=panel.winfo_id()
        self.process=os.getpid()
        self.identity=id(self)
        self.handles=set()
        self.events=deque()
        self.closed=False
        self.pan_y=None
        self.last_wheel=0
        self.stats=dict(raw_wheels=0,window_wheels=0,pans=0,legacy_scrolls=0,applied=0,python_move_callbacks=0)
        self._mouse_proc=MOUSEPROC(self.mouse_message)
        self._window_proc=SUBCLASSPROC(self.window_message)
        self.bridge=None
        self._dispatch_proc=self._window_proc
        self._dispatch_data=0
        try:
            from native_wheel import NativeWheel
            self.bridge=NativeWheel(self.panel_handle)
            self._dispatch_proc=SUBCLASSPROC(self.bridge.subclass_address)
            self._dispatch_data=ctypes.cast(self._window_proc,ctypes.c_void_p).value
            self.hook=self.bridge.token
        except OSError:
            self.hook=u.SetWindowsHookExW(14,self._mouse_proc,k.GetModuleHandleW(None),0)
        self._map_binding=self.root.bind('<Map>',self.mapped,add='+')
        self._attach_job=self.root.after_idle(self.attach_tree)
        self._pump_job=self.root.after(15,self.drain)

    def hit_test(self,x,y):
        if self.closed or not u.IsWindowVisible(self.panel_handle):
            return False
        rect=w.RECT()
        if not u.GetWindowRect(self.panel_handle,ctypes.byref(rect)):
            return False
        if not (rect.left<=x<rect.right and rect.top<=y<rect.bottom):
            return False
        hit=u.WindowFromPoint(w.POINT(x,y))
        owner=w.DWORD()
        u.GetWindowThreadProcessId(hit,ctypes.byref(owner))
        return owner.value==self.process and u.GetAncestor(hit,2)==u.GetAncestor(self.panel_handle,2)

    def mouse_message(self,code,message,data):
        try:
            if code>=0 and message==0x20A:
                info=ctypes.cast(data,ctypes.POINTER(MouseInfo)).contents
                if self.hit_test(info.pt.x,info.pt.y):
                    self.events.append(('wheel',ctypes.c_short(info.data>>16).value))
                    self.last_wheel=time.monotonic()
                    self.stats['raw_wheels']+=1
                    return 1  # Handled here; do not also dispatch it to Tk/native controls.
        except Exception:
            pass
        return u.CallNextHookEx(None,code,message,data)

    def window_message(self,hwnd,message,param,data,identity,reference):
        if message==0x200:self.stats['python_move_callbacks']+=1
        try:
            if message==0x82:  # WM_NCDESTROY
                c.RemoveWindowSubclass(hwnd,self._dispatch_proc,self.identity)
                self.handles.discard(hwnd)
            elif message==0x20A:
                x,y=ctypes.c_short(data&0xffff).value,ctypes.c_short((data>>16)&0xffff).value
                if self.hit_test(x,y):
                    self.events.append(('wheel',ctypes.c_short((param>>16)&0xffff).value))
                    self.last_wheel=time.monotonic()
                    self.stats['window_wheels']+=1
                    return 0
            elif message==0x119:  # WM_GESTURE
                info=GestureInfo();info.size=ctypes.sizeof(info)
                if u.GetGestureInfo(w.HANDLE(data),ctypes.byref(info)) and info.kind==4:
                    if self.pan_y is not None or self.hit_test(info.point.x,info.point.y):
                        y=info.point.y
                        if self.pan_y is not None and not info.flags&1 and time.monotonic()-self.last_wheel>.1:
                            self.events.append(('pixels',self.pan_y-y))
                        self.pan_y=None if info.flags&4 else y
                        self.stats['pans']+=1
                        u.CloseGestureInfoHandle(w.HANDLE(data))
                        return 0
            elif message==0x115:  # Legacy touchpad drivers can send WM_VSCROLL directly.
                point=w.POINT()
                if u.GetCursorPos(ctypes.byref(point)) and self.hit_test(point.x,point.y):
                    action=param&0xffff
                    if action in (0,1,2,3,6,7):
                        if action in (6,7):
                            self.events.append(('position',0 if action==6 else 1))
                        else:
                            amount=self.panel.p(48) if action<2 else int(self.panel.canvas.winfo_height()*.85)
                            self.events.append(('pixels',-amount if action in (0,2) else amount))
                        self.stats['legacy_scrolls']+=1
                        return 0
        except Exception:
            pass
        return c.DefSubclassProc(hwnd,message,param,data)

    def attach_widget(self,widget):
        if self.closed:
            return
        try:
            hwnd=widget.winfo_id()
            owner=w.DWORD()
            u.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
            if owner.value!=self.process or hwnd in self.handles:
                return
            if c.SetWindowSubclass(hwnd,self._dispatch_proc,self.identity,self._dispatch_data):
                self.handles.add(hwnd)
                config=GestureConfig(4,1|2|16,4)  # Pan vertically, including inertia.
                u.SetGestureConfig(hwnd,0,1,ctypes.byref(config),ctypes.sizeof(config))
        except tk.TclError:
            pass

    def attach_tree(self):
        self._attach_job=None
        def visit(widget):
            self.attach_widget(widget)
            for child in widget.winfo_children():
                visit(child)
        if not self.closed:
            visit(self.root)
            wrapper=u.GetAncestor(self.root.winfo_id(),2)
            if wrapper and wrapper not in self.handles:
                if c.SetWindowSubclass(wrapper,self._dispatch_proc,self.identity,self._dispatch_data):
                    self.handles.add(wrapper)

    def mapped(self,event):
        self.attach_widget(event.widget)

    def drain(self):
        self._pump_job=None
        if self.closed:
            return
        if self.bridge:
            for delta in self.bridge.poll():
                self.events.append(('wheel',delta))
                self.last_wheel=time.monotonic()
                self.stats['raw_wheels']+=1
        for _ in range(min(200,len(self.events))):
            kind,amount=self.events.popleft()
            if kind=='wheel':
                self.scroll_delta(amount)
            elif kind=='pixels':
                self.scroll_pixels(amount)
            else:
                self.panel.canvas.yview_moveto(amount)
            self.stats['applied']+=1
        self._pump_job=self.root.after(15,self.drain)

    def report(self):
        return dict(active=not self.closed,raw_hook=bool(self.hook),subclassed_windows=len(self.handles),
                    input_backend='native-thread' if self.bridge else 'python-fallback',
                    hook_thread_id=self.bridge.thread_id if self.bridge else None,**self.stats)

    def stop(self):
        if self.closed:
            return
        self.closed=True
        if self.hook:
            if self.bridge:self.bridge.close()
            else:u.UnhookWindowsHookEx(self.hook)
            self.hook=None
        for hwnd in list(self.handles):
            if u.IsWindow(hwnd):
                c.RemoveWindowSubclass(hwnd,self._dispatch_proc,self.identity)
        self.handles.clear()
        for job in (self._pump_job,self._attach_job):
            if job:
                try:self.root.after_cancel(job)
                except tk.TclError:pass
        self.root.unbind('<Map>',self._map_binding)
