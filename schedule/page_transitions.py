"""Small retained-page slide transition; no screenshots, fades or timer state changes."""
import time
import tkinter as tk


class PageStack:
    def __init__(self,parent,duration=0):
        self.parent=parent;self.duration=duration/1000
        self.current=None;self.previous=None;self.job=None
        parent.bind('<Destroy>',lambda e:self.stop() if e.widget is parent else None,add='+')

    def stop(self):
        if self.job is not None:
            try:self.parent.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None

    def settle(self):
        self.stop()
        if self.previous is not None:
            self.previous.place_forget();self.previous=None
        if self.current is not None:
            self.current.place(x=0,y=0,relwidth=1,relheight=1)

    def show(self,page,direction=1,animate=True):
        if self.current is page:
            self.settle();return
        self.settle();old=self.current;self.current=page
        # Avoid animating hidden/off-screen windows (including verification fixtures).
        visible=(self.parent.winfo_ismapped() and self.parent.winfo_width()>1
                 and 0<=self.parent.winfo_rootx()<self.parent.winfo_screenwidth()
                 and 0<=self.parent.winfo_rooty()<self.parent.winfo_screenheight())
        if not old or not animate or not visible:
            if old:old.place_forget()
            page.place(x=0,y=0,relwidth=1,relheight=1);page.lift();return
        self.previous=old;started=time.perf_counter();sign=1 if direction>=0 else -1
        page.place(x=sign*self.parent.winfo_width(),y=0,relwidth=1,relheight=1);page.lift()
        def step():
            progress=min(1,(time.perf_counter()-started)/self.duration)
            fraction=1-(1-progress)**3
            width=self.parent.winfo_width()
            old.place_configure(x=round(-sign*width*fraction))
            page.place_configure(x=round(sign*width*(1-fraction)))
            if progress>=1:self.settle()
            else:self.job=self.parent.after(15,step)
        self.job=self.parent.after(0,step)
