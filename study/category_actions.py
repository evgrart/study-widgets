"""Small anchored category menu with a reversible day-only reset."""
import tkinter as tk

PANEL,TEXT,MUTED,LINE='#20252E','#F2F3F5','#9DA5B3','#3B424F'


class CategoryActions:
    def __init__(self,app,category,day,anchor):
        self.app,self.category,self.day=app,category,day
        self.removed=None
        p=app.p
        window=self.window=tk.Toplevel(app.root)
        window.withdraw()
        window.overrideredirect(True)
        window.transient(app.root)
        window.configure(bg=LINE)
        body=tk.Frame(window,bg=PANEL,padx=p(14),pady=p(12))
        body.pack(fill='both',expand=True,padx=1,pady=1)
        self.summary=tk.Label(body,text='',
                              bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w')
        self.action=tk.Button(body,text='Очистить за день',command=self.clear,
            bg=PANEL,fg='#F1A0AA',activebackground='#3A2931',activeforeground='#FFD6DC',
            disabledforeground=MUTED,bd=0,relief='flat',anchor='w',cursor='hand2',
            font=('Segoe UI',10),padx=p(8),pady=p(8))
        self.action.pack(fill='x')
        if app.timer.category_time(category['id'],day)<=0:self.action.configure(state='disabled')
        self.outside_binding=app.root.bind('<Button-1>',lambda event:self.close(),add='+')
        window.bind('<Escape>',lambda event:self.close())
        window.bind('<FocusOut>',lambda event:window.after_idle(self.check_focus))
        window.update_idletasks()
        width=max(p(130),window.winfo_reqwidth());height=window.winfo_reqheight()
        x=min(anchor.winfo_rootx()+p(8),app.root.winfo_screenwidth()-width-p(8))
        y=anchor.winfo_rooty()-height-p(6)
        if y<app.root.winfo_rooty():y=anchor.winfo_rooty()+anchor.winfo_height()+p(6)
        y=max(0,min(y,app.root.winfo_screenheight()-height-p(8)))
        window.geometry(f'{width}x{height}+{max(0,x)}+{y}')
        window.deiconify();window.lift();window.focus_force()

    def clear(self):
        try:
            self.removed=self.app.timer.clear_category_day(self.category['id'],self.day)
        except Exception:
            self.summary.configure(text='Не удалось сохранить. Попробуй ещё раз.',fg='#F1A0AA')
            self.summary.pack(fill='x',before=self.action)
            return
        self.app.category_time_changed()
        self.summary.pack_forget()
        self.action.configure(text='↶  Отменить',command=self.undo,fg=TEXT,
                              activebackground=LINE,activeforeground=TEXT)

    def undo(self):
        if self.removed is None:return
        try:self.app.timer.restore_category_time(self.removed)
        except Exception:
            self.summary.configure(text='Не удалось восстановить. Попробуй ещё раз.',fg='#F1A0AA')
            self.summary.pack(fill='x',before=self.action)
            return
        self.removed=None
        self.app.category_time_changed()
        self.close()

    def check_focus(self):
        if not self.window.winfo_exists():return
        focused=self.window.focus_get()
        if focused is None or focused.winfo_toplevel()!=self.window:self.close()

    def close(self):
        if getattr(self.app,'category_actions',None) is self:self.app.category_actions=None
        if self.outside_binding:
            self.app.root.unbind('<Button-1>',self.outside_binding)
            self.outside_binding=None
        if self.window.winfo_exists():self.window.destroy()
        self.app.root.after_idle(self.app.dark_title)
