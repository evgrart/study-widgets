"""Scrollable deadline list alongside the existing week grid."""
import tkinter as tk
import webbrowser
from native_tasks_scroll import NativeTasksScroll

from deadline_core import ASSIGNMENTS_URL, deadline_label, visible_deadlines

BG, PANEL, TEXT, MUTED = '#0c121c', '#141f2e', '#f1f6ff', '#a8b8cc'


class DeadlinePanel(tk.Frame):
    def __init__(self, parent, p, font, connect, refresh):
        super().__init__(parent, bg=PANEL, width=p(285))
        self.p, self.font, self.connect, self.refresh = p, font, connect, refresh
        self.pack_propagate(False)
        self.items, self.state, self.updated_at = [], {}, None
        self._cards_signature=None
        title = tk.Frame(self, bg=PANEL)
        title.pack(fill='x', padx=p(12), pady=(p(12), p(4)))
        tk.Label(title,text='LMS ШАД',bg=PANEL,fg=TEXT,font=font(14,True)).pack(side='left')
        self.refresh_button=tk.Button(title,text='↻',command=self.refresh_or_connect,bg=PANEL,fg=MUTED,
                  relief='flat',bd=0,font=font(15),cursor='hand2')
        self.refresh_button.pack(side='right')
        self.status = tk.Label(self, bg=PANEL, fg=MUTED, font=font(10), justify='left',
                               anchor='w', wraplength=p(260))
        self.status.pack(fill='x', padx=p(12), pady=(0, p(8)))
        content = tk.Frame(self, bg=PANEL)
        self.content=content
        content.pack(fill='both', expand=True, padx=p(8), pady=p(5))
        self.canvas = tk.Canvas(content, bg=PANEL, highlightthickness=0, width=p(260),yscrollincrement=1)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.cards = tk.Frame(self.canvas, bg=PANEL)
        self.window = self.canvas.create_window(0, 0, window=self.cards, anchor='nw')
        self.cards.bind('<Configure>', lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self.resize)
        self.canvas.bind('<MouseWheel>', self.wheel)
        tk.Button(self, text='Открыть задания ↗', command=lambda:webbrowser.open(ASSIGNMENTS_URL),
                  bg=PANEL, fg='#89c7ff', relief='flat', font=font(10), cursor='hand2').pack(
                      fill='x', padx=p(10), pady=(0, p(8)))
        self._wheel_remainder=0.0
        self._scroll_tag=f'DeadlinesScroll-{id(self)}'
        self.bind_class(self._scroll_tag,'<MouseWheel>',self.wheel)
        self.tag_scroll_area(self)
        self._wheel_root=self.winfo_toplevel()
        self._wheel_binding=self._wheel_root.bind('<MouseWheel>',self.route_wheel,add='+')
        self.bind('<Destroy>',self.cleanup_scroll,add='+')
        self.native_scroll=NativeTasksScroll(self,self.scroll_delta,self.scroll_pixels)

    def tag_scroll_area(self,widget):
        tags=widget.bindtags()
        if self._scroll_tag not in tags:widget.bindtags((self._scroll_tag,)+tags)
        for child in widget.winfo_children():self.tag_scroll_area(child)
        if hasattr(self,'native_scroll'):self.native_scroll.attach_widget(widget)

    def route_wheel(self,event):
        target=self._wheel_root.winfo_containing(event.x_root,event.y_root)
        while target is not None:
            if target is self:return self.wheel(event)
            target=getattr(target,'master',None)

    def cleanup_scroll(self,event):
        if event.widget is self:
            self.native_scroll.stop()
            try:
                self._wheel_root.unbind('<MouseWheel>',self._wheel_binding)
                self.unbind_class(self._scroll_tag,'<MouseWheel>')
            except tk.TclError:pass

    def resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        for label in self.cards.winfo_children():
            for child in label.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(wraplength=max(50, event.width-self.p(25)))

    def wheel(self, event):
        self.scroll_delta(event.delta)
        return 'break'

    def scroll_delta(self,delta):
        distance=self._wheel_remainder-delta*self.p(48)/120
        pixels=int(distance)
        self._wheel_remainder=distance-pixels
        if pixels:self.scroll_pixels(pixels)

    def scroll_pixels(self,pixels):
        self.canvas.yview_scroll(int(pixels),'units')

    def update_data(self, items, state, updated_at):
        self.items, self.state, self.updated_at = items, state, updated_at
        self.render()

    def refresh_or_connect(self):
        if self.state.get('state','login_required')=='login_required':self.connect()
        else:self.refresh()

    def render(self):
        scroll = self.canvas.yview()[0]
        state = self.state.get('state', 'login_required')
        messages = {
            'login_required': 'Подключи аккаунт, чтобы загрузить задания.',
            'connecting': 'Открыт вход в Яндекс. Войди в аккаунт ШАДа.',
            'syncing': 'Проверяю задания…',
            'busy': 'Подключение ШАДа уже выполняется…',
            'error': 'Не удалось обновить. Повторю автоматически.',
            'unsupported': 'Страница заданий изменилась. Сохранённые сроки оставлены.',
            'ok': '',
        }
        message = messages.get(state, messages['error'])
        self.status.configure(text=message)
        if message:
            if not self.status.winfo_manager():
                self.status.pack(fill='x',padx=self.p(12),pady=(0,self.p(8)),before=self.content)
        else:
            self.status.pack_forget()
        self.refresh_button.configure(state='disabled' if state in {'connecting','syncing','busy'} else 'normal')
        items = visible_deadlines(self.items)
        signature=(state if not items else None,tuple((item,deadline_label(item)) for item in items))
        if signature==self._cards_signature:return
        self._cards_signature=signature
        for child in self.cards.winfo_children():
            child.destroy()
        if not items:
            text = 'Незавершённых заданий нет' if state == 'ok' else 'Дедлайны появятся после подключения'
            tk.Label(self.cards, text=text, bg=PANEL, fg=MUTED, font=self.font(11),
                     wraplength=self.p(220), justify='left', anchor='w').pack(fill='x', pady=self.p(12))
        width = max(self.p(180), self.canvas.winfo_width()-self.p(25))
        for item in items:
            card = tk.Frame(self.cards, bg='#202339', cursor='hand2')
            card.pack(fill='x', pady=(0, self.p(8)))
            due, color = deadline_label(item)
            texts = [(due, color, self.font(10, True)),
                     (item.title, TEXT, self.font(12, True)),
                     (item.course, MUTED, self.font(10)),
                     (item.status, MUTED, self.font(10))]
            for text, fg, font in texts:
                if not text:
                    continue
                label = tk.Label(card, text=text, bg='#202339', fg=fg, font=font,
                                 wraplength=width, justify='left', anchor='w', cursor='hand2')
                label.pack(fill='x', padx=self.p(9), pady=(self.p(5), self.p(4)))
                label.bind('<Button-1>', lambda event, url=item.url:webbrowser.open(url))
                label.bind('<MouseWheel>', self.wheel)
            card.bind('<Button-1>', lambda event, url=item.url:webbrowser.open(url))
            card.bind('<MouseWheel>', self.wheel)
        self.tag_scroll_area(self.cards)
        self.cards.update_idletasks()
        self.canvas.yview_moveto(scroll)
