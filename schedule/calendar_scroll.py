"""Pointer-scoped Windows/touchpad scrolling for an overflowing week canvas."""
from native_tasks_scroll import NativeTasksScroll


class CalendarScroll:
    def __init__(self,canvas,p,on_scroll):
        self.canvas,self.p,self.on_scroll = canvas,p,on_scroll
        self.remainder = 0.0
        self.root = canvas.winfo_toplevel()
        self.canvas.configure(yscrollincrement=1)
        self.canvas.bind('<MouseWheel>',self.wheel,add='+')
        self.root_binding = self.root.bind('<MouseWheel>',self.route,add='+')
        self.canvas.bind('<Destroy>',self.destroy,add='+')
        self.native = NativeTasksScroll(self,self.scroll_delta,self.scroll_pixels)
        self.stopped = False

    def __getattr__(self,name):
        return getattr(self.canvas,name)

    def route(self,event):
        if self.root.winfo_containing(event.x_root,event.y_root) is self.canvas:
            return self.wheel(event)

    def wheel(self,event):
        self.scroll_delta(event.delta)
        return 'break'

    def scroll_delta(self,delta):
        self.remainder -= delta*self.p(48)/120
        pixels = int(self.remainder)
        self.remainder -= pixels
        self.scroll_pixels(pixels)

    def scroll_pixels(self,pixels):
        if pixels:
            self.on_scroll()
            self.canvas.yview_scroll(int(pixels),'units')

    def destroy(self,event):
        if event.widget is self.canvas:
            self.stop()

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.native.stop()
        self.root.unbind('<MouseWheel>',self.root_binding)
