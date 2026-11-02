"""Google Tasks: unfinished overdue tasks and a rolling week ahead."""
from datetime import date, datetime
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from native_tasks_scroll import NativeTasksScroll
from deadline_core import MOSCOW
from tasks_core import sidebar_tasks

BG, PANEL, TEXT, MUTED = '#0c121c', '#141f2e', '#f1f6ff', '#a8b8cc'


def sidebar_today():
    return datetime.now(MOSCOW).date()


class TasksPanel(tk.Frame):
    def __init__(self, parent, p, font, toggle, connect, refresh):
        super().__init__(parent, bg=PANEL, width=p(285))
        self.p, self.font, self.toggle, self.connect = p, font, toggle, connect
        self.completed_font = tkfont.Font(root=self,font=font(12))
        self.completed_font.configure(overstrike=True)
        self.pack_propagate(False)
        self.items, self.state, self.first_day = [], {}, date.today()
        header = tk.Frame(self, bg=PANEL)
        header.pack(fill='x', padx=p(10), pady=(p(10), p(4)))
        tk.Label(header, text='Google Tasks', bg=PANEL, fg=TEXT, font=font(14, True)).pack(side='left')
        tk.Button(header, text='↻', command=refresh, bg=PANEL, fg=MUTED, relief='flat',
                  font=font(15), cursor='hand2').pack(side='right')
        self.status = tk.Label(self, bg=PANEL, fg=MUTED, font=font(10), anchor='w',
                               justify='left', wraplength=p(260), height=3)
        self.status.pack(fill='x', padx=p(12), pady=p(5))
        self.connect_button = tk.Button(self, text='Подключить Google Tasks', command=connect,
            bg='#315f88', fg=TEXT, relief='flat', font=font(11), cursor='hand2')
        content = tk.Frame(self, bg=PANEL)
        self.content = content
        content.pack(fill='both', expand=True, padx=p(6), pady=p(6))
        self.canvas = tk.Canvas(content, bg=PANEL, highlightthickness=0, width=p(265), yscrollincrement=1)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.cards = tk.Frame(self.canvas, bg=PANEL)
        self.check_controls, self._row_vars, self._row_signatures = {}, {}, {}
        self._headers, self._layout_keys = {}, ()
        self._scroll_job, self._wrap_width = None, None
        self.check_vars, self.visible_ids = [], []
        self.empty_label = tk.Label(self.cards, text='Задач нет',
            bg=PANEL, fg=MUTED, font=font(11), wraplength=p(245), justify='left')
        self.window = self.canvas.create_window(0, 0, window=self.cards, anchor='nw')
        self.cards.bind('<Configure>', lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self.resize)
        tk.Button(self, text='Открыть Google Tasks ↗', command=lambda:webbrowser.open('https://tasks.google.com/tasks/'),
                  bg=PANEL, fg='#89c7ff', relief='flat', font=font(10), cursor='hand2').pack(fill='x', pady=p(8))
        self._wheel_remainder=0.0
        self._scroll_tag=f'GoogleTasksScroll-{id(self)}'
        self.bind_class(self._scroll_tag, '<MouseWheel>', self.wheel)
        self.tag_scroll_area(self)
        self._wheel_root=self.winfo_toplevel()
        self._wheel_binding=self._wheel_root.bind('<MouseWheel>',self.route_wheel,add='+')
        self.bind('<Destroy>',self.cleanup_scroll,add='+')
        self.native_scroll=NativeTasksScroll(self,self.scroll_delta,self.scroll_pixels)

    def tag_scroll_area(self, widget):
        tags=widget.bindtags()
        if self._scroll_tag not in tags:
            widget.bindtags((self._scroll_tag,)+tags)
        for child in widget.winfo_children():
            self.tag_scroll_area(child)
        if hasattr(self,'native_scroll'):
            self.native_scroll.attach_widget(widget)

    def route_wheel(self, event):
        # Windows can deliver the wheel to the focused widget rather than the pointer.
        target=self._wheel_root.winfo_containing(event.x_root,event.y_root)
        while target is not None:
            if target is self:
                return self.wheel(event)
            target=getattr(target,'master',None)
        return None

    def cleanup_scroll(self, event):
        if event.widget is self:
            self.native_scroll.stop()
            try:
                self._wheel_root.unbind('<MouseWheel>',self._wheel_binding)
                self.unbind_class(self._scroll_tag,'<MouseWheel>')
            except tk.TclError:
                pass

    def resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        width=max(80, event.width-self.p(42))
        if width != self._wrap_width:
            self._wrap_width=width
            for child in self.check_controls.values():
                child.configure(wraplength=width)

    def wheel(self, event):
        self.scroll_delta(event.delta)
        return 'break'

    def scroll_delta(self, delta):
        # Retain subpixel input: precision touchpads frequently emit deltas below 120.
        distance=self._wheel_remainder-delta*self.p(48)/120
        pixels=int(distance)
        self._wheel_remainder=distance-pixels
        if pixels:
            self.scroll_pixels(pixels)

    def scroll_pixels(self,pixels):
        self.canvas.yview_scroll(int(pixels),'units')

    def update_data(self, items, state, first_day):
        self.items, self.state, self.first_day = items, state, first_day
        self.render()

    def refresh_day(self):
        if getattr(self,'rendered_day',None)!=sidebar_today():
            self.render()

    def render(self):
        scroll = self.canvas.yview()[0]
        state = self.state.get('state', 'login_required')
        message = {'login_required':'Войди в Google для синхронизации.',
                   'connecting':'Войди в Google в отдельном окне Edge.',
                   'syncing':'Синхронизация с Google…',
                   'ok':'',
                   'error':'Нет обновления. Изменения сохранены локально.',
                   'unsupported':'Страница Google изменилась. Сохранённая копия оставлена.'}.get(state, 'Проверяю подключение…')
        pending = sum(bool(t.pending) for t in self.items)
        if self.state.get('retryable'):
            message='Временный сбой Google. Повторю синхронизацию автоматически.'
        if pending:
            message += f'\nОжидают отправки: {pending}'
        if self.status.cget('text') != message:
            self.status.configure(text=message)
        if message:
            if not self.status.winfo_manager():
                self.status.pack(fill='x',padx=self.p(12),pady=self.p(5),before=self.content)
        else:
            self.status.pack_forget()
        if state in {'login_required', 'connecting'}:
            if not self.connect_button.winfo_manager():
                self.connect_button.pack(fill='x', padx=self.p(12), pady=self.p(6), before=self.status)
            button_state='disabled' if state=='connecting' else 'normal'
            if self.connect_button.cget('state') != button_state:
                self.connect_button.configure(state=button_state)
        elif self.connect_button.winfo_manager():
            self.connect_button.pack_forget()
        self.rendered_day=sidebar_today()
        items=sidebar_tasks(self.items,self.rendered_day)
        self.visible_ids = [t.id for t in items]
        visible=set(self.visible_ids)
        days={task.due for task in items}
        for identity in set(self.check_controls)-visible:
            self.check_controls.pop(identity).destroy()
            self._row_vars.pop(identity)
            self._row_signatures.pop(identity, None)
        for day in set(self._headers)-days:
            self._headers.pop(day).destroy()
        previous = object()
        layout=[]
        for task in items:
            if task.due != previous:
                if task.due not in self._headers:
                    text = date.fromisoformat(task.due).strftime('%d.%m.%Y') if task.due else 'Без даты'
                    self._headers[task.due]=tk.Label(self.cards, text=text, bg=PANEL,
                        fg='#8fe0bf', font=self.font(11, True), anchor='w')
                    self.tag_scroll_area(self._headers[task.due])
                layout.append(('header',task.due))
                previous = task.due
            title = task.title + ('  ⟳' if task.pending else '')
            if task.id not in self.check_controls:
                value=tk.BooleanVar(value=task.completed)
                check=tk.Checkbutton(self.cards, variable=value,
                    command=lambda identity=task.id:self.toggle(identity), bg='#192d32',
                    selectcolor=BG, activebackground='#23423e', activeforeground=TEXT,
                    relief='flat', anchor='w', justify='left',
                    wraplength=max(80, self.canvas.winfo_width()-self.p(42)),
                    padx=self.p(6), pady=self.p(8), cursor='hand2')
                self.tag_scroll_area(check)
                self.check_controls[task.id]=check
                self._row_vars[task.id]=value
            value=self._row_vars[task.id]
            if value.get() != task.completed:
                value.set(task.completed)
            signature=(title,task.completed)
            if self._row_signatures.get(task.id) != signature:
                self.check_controls[task.id].configure(text=title,
                    fg=MUTED if task.completed else TEXT,
                    font=self.completed_font if task.completed else self.font(12))
                self._row_signatures[task.id]=signature
            layout.append(('task',task.id))
        self.check_vars=[self._row_vars[identity] for identity in self.visible_ids]
        if not layout:
            layout=[('empty',None)]
        layout=tuple(layout)
        if layout != self._layout_keys:
            self.empty_label.pack_forget()
            before=None
            for kind,key in reversed(layout):
                if kind=='task':
                    child=self.check_controls[key]
                    options=dict(fill='x',pady=(0,self.p(4)))
                elif kind=='header':
                    child=self._headers[key]
                    options=dict(fill='x',padx=self.p(7),pady=(self.p(12),self.p(5)))
                else:
                    child=self.empty_label
                    options=dict(pady=self.p(15))
                if before is not None:
                    options['before']=before
                child.pack(**options)
                before=child
            self._layout_keys=layout
            if self._scroll_job is None:
                self._scroll_job=self.after_idle(lambda:self.restore_scroll(scroll))

    def restore_scroll(self, position):
        self._scroll_job=None
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(position)
