"""Interactive local study charts using Tk canvas; no account or web service."""
import math
import tkinter as tk
from tkinter import font as tkfont

from study_core import format_time, now_moscow
from stats_core import build_report, move_period, period_label, short_time, WEEKDAYS
from page_transitions import PageStack

BG = '#16191F'
PANEL = '#20252E'
TEXT = '#F2F3F5'
MUTED = '#9DA5B3'
LINE = '#353C47'
YELLOW = '#F4CF70'


class LegendPane(tk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,bg=PANEL)
        self.p = app.p
        self.canvas = tk.Canvas(self,bg=PANEL,highlightthickness=0,bd=0,yscrollincrement=1,width=1,height=1)
        self.canvas.pack(fill='both',expand=True)
        self.inner = tk.Frame(self.canvas,bg=PANEL)
        self.item = self.canvas.create_window(0,0,window=self.inner,anchor='nw')
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.item,width=e.width))
        self.remainder = 0.0

    def scroll_pixels(self,value):
        self.remainder += value
        amount = int(self.remainder)
        self.remainder -= amount
        self.canvas.yview_scroll(amount,'units')

    def scroll_delta(self,delta):
        self.scroll_pixels(-delta*self.p(40)/120)


class Tooltip:
    def __init__(self, owner):
        self.owner = owner
        self.window = None
        self.label = None
        self.current = None

    def show(self, text, x, y):
        if self.window is None:
            self.window = tk.Toplevel(self.owner)
            self.window.overrideredirect(True)
            self.window.attributes('-topmost', True)
            self.label = tk.Label(self.window, text='', justify='left', bg='#333B48', fg=TEXT,
                                  padx=12, pady=9, font=('Segoe UI', 10), bd=1, relief='solid')
            self.label.pack()
        if text != self.current:
            self.label.configure(text=text)
            self.current = text
            self.window.update_idletasks()
        x = min(x+18, self.owner.winfo_screenwidth()-self.window.winfo_reqwidth()-12)
        y = min(y+20, self.owner.winfo_screenheight()-self.window.winfo_reqheight()-60)
        self.window.geometry(f'+{max(0,x)}+{max(0,y)}')
        self.window.deiconify()

    def hide(self):
        if self.window:
            self.window.withdraw()

    def close(self):
        if self.window:
            self.window.destroy()
            self.window = None


class StatsWindow:
    def __init__(self, app):
        self.app, self.p = app, app.p
        self.window = tk.Toplevel(app.root)
        self.window.title('Статистика')
        self.window.configure(bg=BG)
        self.window.bind('<Map>',lambda event:app.dark_title(self.window) if event.widget is self.window else None,add='+')
        self.window.after_idle(lambda:app.dark_title(self.window))
        self.window.transient(app.root)
        icon = app.folder / 'study.ico'
        if icon.exists():
            self.window.iconbitmap(str(icon))
        width = min(self.p(1030), int(self.window.winfo_screenwidth()*.9))
        height = min(self.p(730), int(self.window.winfo_screenheight()*.87))
        self.window.geometry(f'{width}x{height}+{max(0,(self.window.winfo_screenwidth()-width)//2)}+{self.p(24)}')
        self.window.minsize(min(self.p(760),width), min(self.p(570),height))
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda e: self.close())
        self.mode = app.store.setting('stats_mode', 'week')
        if self.mode not in ('day', 'week', 'month'):
            self.mode = 'week'
        self.anchor = app.day
        self.follow_current = self.anchor == now_moscow().date()
        self.hidden_by_owner = False
        self.signature = None
        self.report = None
        self.hits = {}
        self.day_regions = []
        self.legend_rows = {}
        self.tooltip = Tooltip(self.window)
        self.layout_job = None
        self.closed = False
        self.native = None
        self.section='study'
        self.sleep_page=None

        heading = tk.Frame(self.window, bg=BG)
        heading.pack(fill='x', padx=self.p(24), pady=(self.p(18),self.p(12)))
        self.label(heading, 'Статистика', 17, bold=True).pack(side='left')
        self.timer_button=app.button(heading,'Таймер',self.return_to_timer,small=True)
        self.timer_button.pack(side='right')
        sections=tk.Frame(self.window,bg=BG)
        sections.pack(fill='x',padx=self.p(24),pady=(0,self.p(10)))
        self.section_buttons={}
        for section,title in [('study','Учёба'),('sleep','Сон')]:
            button=app.button(sections,title,lambda key=section:self.show_section(key),small=True)
            button.pack(side='left',padx=(0,self.p(5)));self.section_buttons[section]=button
        self.pages=tk.Frame(self.window,bg=BG)
        self.pages.pack(fill='both',expand=True)
        self.page_stack=PageStack(self.pages)
        self.study_page=tk.Frame(self.pages,bg=BG)
        toolbar = tk.Frame(self.study_page, bg=BG)
        toolbar.pack(fill='x', padx=self.p(24), pady=(0,self.p(16)))
        self.mode_buttons = {}
        for mode, title in (('day','День'),('week','Неделя'),('month','Месяц')):
            button = app.button(toolbar, title, lambda m=mode: self.set_mode(m), small=True)
            button.pack(side='left', padx=(0,self.p(4)))
            self.mode_buttons[mode] = button
        app.button(toolbar, 'Сегодня', self.today, small=True).pack(side='right', padx=(self.p(10),0))
        app.button(toolbar, '›', lambda: self.navigate(1), small=True).pack(side='right')
        self.period = self.label(toolbar, '', 11, bold=True)
        self.period.pack(side='right', padx=self.p(14))
        app.button(toolbar, '‹', lambda: self.navigate(-1), small=True).pack(side='right')

        summary = tk.Frame(self.study_page, bg=BG)
        summary.pack(fill='x', padx=self.p(24), pady=(0,self.p(18)))
        self.cards = []
        for index in range(3):
            summary.columnconfigure(index, weight=1, uniform='cards')
            card = tk.Frame(summary, bg=PANEL, padx=self.p(17), pady=self.p(12))
            card.grid(row=0, column=index, sticky='nsew', padx=(0,self.p(10) if index<2 else 0))
            title = self.label(card, '', 9, color=MUTED)
            title.pack(anchor='w')
            value = self.label(card, '', 21, color=YELLOW if index==0 else TEXT, bold=True)
            value.pack(anchor='w', pady=(self.p(4),self.p(1)))
            note = self.label(card, '', 9, color=MUTED)
            note.pack(anchor='w')
            self.cards.append((title,value,note))

        body = tk.Frame(self.study_page, bg=BG)
        body.pack(fill='both', expand=True, padx=self.p(24))
        body.columnconfigure(0, weight=3, uniform='charts')
        body.columnconfigure(1, weight=2, uniform='charts')
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=PANEL)
        left.grid(row=0, column=0, sticky='nsew', padx=(0,self.p(12)))
        self.chart_title = self.label(left, '', 12, bold=True)
        self.chart_title.pack(anchor='w', padx=self.p(18), pady=(self.p(16),self.p(3)))
        self.chart_note = self.label(left, '', 9, color=MUTED)
        self.chart_note.pack(anchor='w', padx=self.p(18), pady=(0,self.p(8)))
        self.chart = tk.Canvas(left, bg=PANEL, highlightthickness=0, bd=0,width=1,height=1)
        self.chart.pack(fill='both', expand=True, padx=self.p(8), pady=(0,self.p(12)))
        right = tk.Frame(body, bg=PANEL)
        right.grid(row=0, column=1, sticky='nsew')
        self.label(right, 'Распределение времени', 12, bold=True).pack(anchor='w', padx=self.p(18), pady=(self.p(16),self.p(3)))
        self.ring = tk.Canvas(right, bg=PANEL, highlightthickness=0, bd=0, width=1,height=self.p(175))
        self.ring.pack(fill='x', padx=self.p(14), pady=(self.p(5),self.p(8)))
        self.legend_pane = LegendPane(right,app)
        self.legend_pane.pack(fill='both', expand=True, padx=self.p(18), pady=(0,self.p(14)))
        self.legend = self.legend_pane.inner
        self.empty_legend = self.label(self.legend, 'В этом периоде пока нет записей', 10, color=MUTED)
        self.empty_legend.configure(wraplength=self.p(240), justify='left')
        self.footer = self.label(self.study_page, '', 9, color=MUTED)
        self.footer.pack(fill='x', padx=self.p(24), pady=self.p(12))
        self.footer.configure(anchor='w')
        for canvas in (self.chart,self.ring):
            canvas.bind('<Configure>', self.on_resize)
            canvas.bind('<Motion>', lambda event,c=canvas: self.hover(c,event))
            canvas.bind('<Leave>', lambda e: self.tooltip.hide())
        self.chart.bind('<Button-1>', self.click_day)
        self.window.bind('<Unmap>', lambda e: self.tooltip.hide(), add='+')
        self.window.bind('<MouseWheel>',self.wheel,add='+')
        if app.native is not None:
            from native_scroll import NativeStudyScroll
            self.native = NativeStudyScroll(self.legend_pane,self.legend_pane.scroll_delta,self.legend_pane.scroll_pixels)
        self.refresh(force=True)
        self.show_section('study')

    def show_section(self,section):
        if section not in ('study','sleep'):return
        self.tooltip.hide()
        if section=='sleep' and self.sleep_page is None:
            from sleep_stats_view import SleepStatsPane
            self.sleep_page=SleepStatsPane(self.pages,self)
        self.section=section
        page=self.study_page if section=='study' else self.sleep_page
        self.page_stack.show(page,direction=1 if section=='sleep' else -1)
        for key,button in self.section_buttons.items():
            button.configure(bg=YELLOW if key==section else PANEL,fg=BG if key==section else TEXT)
        self.refresh()

    def label(self, parent, text, size, color=TEXT, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color, bd=0,
                        font=('Segoe UI',size,'bold' if bold else 'normal'))

    def set_mode(self, mode):
        self.mode = mode
        self.app.store.set_setting('stats_mode', mode)
        self.tooltip.hide()
        self.refresh(force=True)

    def navigate(self, delta):
        self.anchor = move_period(self.mode,self.anchor,delta)
        self.follow_current = False
        self.tooltip.hide()
        self.refresh(force=True)

    def today(self):
        self.anchor = now_moscow().date()
        self.follow_current = True
        self.refresh(force=True)

    def on_resize(self,event=None):
        if self.layout_job:
            self.window.after_cancel(self.layout_job)
        self.layout_job = self.window.after(60,self.redraw)

    def refresh(self, force=False):
        if self.closed:
            return
        if self.section=='sleep':
            self.sleep_page.refresh(force=force)
            return
        if self.follow_current:
            self.anchor = now_moscow().date()
        signature = (self.mode,self.anchor,
                     tuple((cid,day,int(seconds)) for (cid,day),seconds in sorted(self.app.timer.totals.items())),
                     tuple((c['id'],c['title'],c['color']) for c in self.app.categories),
                     tuple(sorted(self.app.store.days_off())),tuple(sorted(self.app.store.groups.nights())))
        if not force and signature == self.signature:
            return
        self.signature = signature
        grouped=self.app.store.groups.totals(self.app.timer.totals)
        anchor=self.app.store.groups.start(self.anchor) if self.mode=='day' else self.anchor
        self.report = build_report(grouped,self.app.categories,self.mode,anchor,self.app.store.days_off())
        report = self.report
        self.period.configure(text=period_label(self.mode,anchor))
        if self.mode=='day' and report.days_off:
            self.period.configure(text=period_label(self.mode,anchor)+' · Выходной')
        for mode,button in self.mode_buttons.items():
            button.configure(bg=YELLOW if mode==self.mode else PANEL, fg=BG if mode==self.mode else TEXT)
        if self.mode == 'day':
            active = [c for c in report.categories if report.category_totals[c['id']] > 0]
            leader = active[0] if active else None
            items = [('За день',short_time(report.total),'записанное время'),
                     ('Категорий',str(len(active)),'с занятиями в этот день'),
                     ('Больше всего',self.trim(leader['title'],23) if leader else '—',
                      short_time(report.category_totals[leader['id']]) if leader else 'пока нет записей')]
        else:
            items = [('Всего за период',short_time(report.total),'по всем категориям'),
                     ('В среднем за учебный день',short_time(report.average_active_day),''),
                     ('Дней с занятиями',str(report.active_days),
                      f'максимум {report.best_day:%d.%m}: {short_time(report.daily_totals[report.best_day])}' if report.best_day else 'пока нет записей')]
        if self.mode=='day' and report.days_off:
            items=[('Выходной','—','не участвует в учебной статистике'),
                   ('Сохранено в таймере',short_time(report.excluded_total),'время не удалено'),
                   ('Учёт в статистике','Выключен','сними отметку, чтобы вернуть день')]
        elif report.days_off:
            items[0]=(items[0][0],items[0][1],f'без выходных · исключено дней: {len(report.days_off)}')
            items[1]=(items[1][0],items[1][1],'дни с записями, кроме выходных')
        for (title,value,note),(a,b,c) in zip(self.cards,items):
            title.configure(text=a)
            value.configure(text=b,font=('Segoe UI',16 if len(b)>17 else 21,'bold'))
            note.configure(text=c)
        self.chart_title.configure(text='Время по категориям' if self.mode=='day' else 'Время по дням')
        self.chart_note.configure(text='Наведи на полосу — покажу точное время' if self.mode=='day' else 'Выходные выделены отдельно · нажми на день')
        first = f'История с {report.first_recorded_day:%d.%m.%Y}' if report.first_recorded_day else 'История появится после первого занятия'
        self.footer.configure(text=first+'  ·  Москва')
        self.update_legend()
        self.redraw()

    @staticmethod
    def trim(text,length):
        return text if len(text)<=length else text[:length-1]+'…'

    def update_legend(self):
        report = self.report
        active = [c for c in report.categories if report.category_totals[c['id']]>0]
        if not active:
            self.empty_legend.configure(text='Выходной — учебное время не учитывается' if self.mode=='day' and report.days_off else 'За период нет учитываемых занятий' if report.days_off else 'В этом периоде пока нет записей')
            self.empty_legend.pack(anchor='w',pady=self.p(12))
        else:
            self.empty_legend.pack_forget()
        ids = {c['id'] for c in active}
        for cid in list(self.legend_rows):
            if cid not in ids:
                self.legend_rows.pop(cid)['frame'].destroy()
        for category in active:
            cid = category['id']
            if cid not in self.legend_rows:
                row = tk.Frame(self.legend,bg=PANEL)
                dot = self.label(row,'●',10)
                dot.pack(side='left',padx=(0,self.p(7)))
                numbers = tk.Frame(row,bg=PANEL)
                numbers.pack(side='right')
                duration = self.label(numbers,'',10,bold=True)
                duration.pack(anchor='e')
                share = self.label(numbers,'',8,color=MUTED)
                share.pack(anchor='e')
                title = self.label(row,'',10)
                title.configure(anchor='w',justify='left')
                title.pack(side='left',fill='x',expand=True)
                self.legend_rows[cid] = dict(frame=row,dot=dot,title=title,duration=duration,share=share)
            row = self.legend_rows[cid]
            seconds = report.category_totals[cid]
            row['dot'].configure(fg=category['color'])
            row['title'].configure(text=category['title'],wraplength=self.p(150))
            row['duration'].configure(text=short_time(seconds))
            row['share'].configure(text=f'{seconds/report.total:.1%}'.replace('.',','))
        # Repack only when the order changes; normal timer updates keep the widgets.
        order = tuple(c['id'] for c in active)
        if getattr(self,'legend_order',None) != order:
            for row in self.legend_rows.values():
                row['frame'].pack_forget()
            for cid in order:
                self.legend_rows[cid]['frame'].pack(fill='x',pady=self.p(5))
            self.legend_order = order

    def redraw(self):
        self.layout_job = None
        if self.closed or self.report is None or self.section!='study':
            return
        for canvas in (self.chart,self.ring):
            canvas.delete('all')
        self.hits.clear()
        self.day_regions.clear()
        self.draw_ring()
        if self.mode=='day':
            self.draw_categories()
        else:
            self.draw_days()

    def draw_ring(self):
        canvas,report = self.ring,self.report
        width,height = max(canvas.winfo_width(),self.p(280)), max(canvas.winfo_height(),self.p(170))
        size = min(width-self.p(25),height-self.p(14))
        cx,cy = width/2,height/2
        bounds = (cx-size/2,cy-size/2,cx+size/2,cy+size/2)
        canvas.create_oval(*bounds,fill=LINE,outline='')
        start = 90
        for category in report.categories:
            seconds = report.category_totals[category['id']]
            if seconds<=0 or not report.total:
                continue
            fraction = seconds/report.total
            if fraction>=.999999999:
                item = canvas.create_oval(*bounds,fill=category['color'],outline='')
            else:
                item = canvas.create_arc(*bounds,start=start,extent=-fraction*360,style='pieslice',
                                         fill=category['color'],outline=PANEL,width=self.p(2))
            self.hits[(canvas,item)] = f"{category['title']}\n{format_time(seconds)} · {fraction:.1%}".replace('.',',')
            start -= fraction*360
        inner = size*.69
        canvas.create_oval(cx-inner/2,cy-inner/2,cx+inner/2,cy+inner/2,fill=PANEL,outline='')
        day_off=self.mode=='day' and bool(report.days_off)
        canvas.create_text(cx,cy-self.p(9),text='Выходной' if day_off else short_time(report.total),fill=TEXT,font=('Segoe UI',14,'bold'))
        canvas.create_text(cx,cy+self.p(15),text='не учитывается' if day_off else 'всего' if report.total else 'пока нет записей',fill=MUTED,font=('Segoe UI',9))

    def draw_categories(self):
        canvas,report = self.chart,self.report
        width,height = max(canvas.winfo_width(),self.p(350)),max(canvas.winfo_height(),self.p(230))
        if report.days_off:
            canvas.create_text(width/2,height/2-self.p(14),text='Выходной',fill='#E5BC79',font=('Segoe UI',17,'bold'),tags='day-off')
            canvas.create_text(width/2,height/2+self.p(18),text='Этот день исключён из учебной статистики.\nЗаписанное время сохранено в таймере.',fill=MUTED,
                               font=('Segoe UI',10),width=width-self.p(35),justify='center')
            return
        categories = [c for c in report.categories if report.category_totals[c['id']]>0]
        if not categories:
            self.draw_empty(canvas,width,height)
            return
        left,right = self.p(12),width-self.p(13)
        maximum = max(report.category_totals.values())
        step = min(self.p(54),(height-self.p(8))/len(categories))
        for index,category in enumerate(categories):
            seconds = report.category_totals[category['id']]
            y = self.p(8)+index*step
            title = self.trim(category['title'],max(12,int(width/self.p(11))-14))
            canvas.create_text(left,y,anchor='nw',text=title,fill=TEXT,font=('Segoe UI',10))
            canvas.create_text(right,y,anchor='ne',text=short_time(seconds),fill=MUTED,font=('Segoe UI',10))
            bar_y = y+self.p(25)
            canvas.create_rectangle(left,bar_y,right,bar_y+self.p(10),fill=LINE,outline='')
            item = canvas.create_rectangle(left,bar_y,left+(right-left)*seconds/maximum,bar_y+self.p(10),fill=category['color'],outline='')
            self.hits[(canvas,item)] = f"{category['title']}\n{format_time(seconds)} · {seconds/report.total:.1%}".replace('.',',')

    @staticmethod
    def axis_step(maximum):
        raw = max(60,maximum/4)
        for step in (60,120,300,600,900,1800,3600,7200,14400,21600,43200,86400):
            if step>=raw:
                return step
        power = 10**math.floor(math.log10(raw))
        return next(factor*power for factor in (1,2,5,10) if factor*power>=raw)

    def draw_days(self):
        canvas,report = self.chart,self.report
        width,height = max(canvas.winfo_width(),self.p(350)),max(canvas.winfo_height(),self.p(230))
        left,right,top,bottom = self.p(55),width-self.p(13),self.p(22),height-self.p(45)
        maximum = max(report.daily_totals.values(),default=0)
        step = self.axis_step(maximum)
        upper = max(step,math.ceil(maximum/step)*step)
        count = int(round(upper/step))
        for index in range(count+1):
            value = index*step
            y = bottom-(bottom-top)*value/upper
            canvas.create_line(left,y,right,y,fill=LINE)
            label = (f'{value/3600:g} ч' if upper>=3600 else f'{value/60:g} м').replace('.',',')
            canvas.create_text(left-self.p(8),y,anchor='e',text=label,fill=MUTED,font=('Segoe UI',8))
        slot = (right-left)/len(report.days)
        bar_width = slot*(.60 if self.mode=='week' else .72)
        today = now_moscow().date()
        for index,day in enumerate(report.days):
            center = left+(index+.5)*slot
            x1,x2 = center-bar_width/2,center+bar_width/2
            is_off=day in report.days_off
            if is_off:
                canvas.create_rectangle(center-slot/2+1,top,center+slot/2-1,bottom,fill='#35303B',outline='',tags='day-off')
                canvas.create_text(center,top+self.p(12),text='Вых.' if self.mode=='week' else '·',fill='#E5BC79',font=('Segoe UI',9,'bold'),tags='day-off')
            elif day==today:
                canvas.create_rectangle(center-slot/2+1,top,center+slot/2-1,bottom,fill='#283342',outline='')
            y = bottom
            for category in sorted(report.categories,key=lambda c:c['id']):
                seconds = report.series[day][category['id']]
                if seconds<=0:
                    continue
                new_y = y-(bottom-top)*seconds/upper
                canvas.create_rectangle(x1,new_y,x2,y,fill=category['color'],outline='')
                y = new_y
            if self.mode=='week':
                canvas.create_text(center,bottom+self.p(14),text=WEEKDAYS[day.weekday()],fill='#E5BC79' if is_off else TEXT,font=('Segoe UI',9,'bold'))
                canvas.create_text(center,bottom+self.p(31),text=f'{day:%d.%m}',fill=MUTED,font=('Segoe UI',8))
                if report.daily_totals[day]>0:
                    canvas.create_text(center,y-self.p(9),text=short_time(report.daily_totals[day]),fill=MUTED,font=('Segoe UI',8))
            elif day.day==1 or day.day%5==0 or day==report.end:
                canvas.create_text(center,bottom+self.p(16),text=str(day.day),fill=MUTED,font=('Segoe UI',8))
            lines = [f'{WEEKDAYS[day.weekday()]}, {day:%d.%m.%Y}',f'Всего: {format_time(report.daily_totals[day])}']
            lines += [f"{c['title']}: {format_time(report.series[day][c['id']])}" for c in report.categories if report.series[day][c['id']]>0]
            if report.daily_totals[day]==0:
                lines.append('Занятий не записано')
            if is_off:
                lines=[f'{WEEKDAYS[day.weekday()]}, {day:%d.%m.%Y}',
                       'Выходной — исключён из учебной статистики','Записанное время сохранено в таймере']
            self.day_regions.append((center-slot/2,top,center+slot/2,bottom+self.p(40),day,'\n'.join(lines)))
        if not report.total:
            self.draw_empty(canvas,(right-left),bottom-top,offset=(left,top))

    def draw_empty(self,canvas,width,height,offset=(0,0)):
        x,y = offset
        excluded=bool(self.report.days_off)
        canvas.create_text(x+width/2,y+height/2-self.p(12),text='Нет учитываемых занятий' if excluded else 'Пока нет записей',fill=TEXT,font=('Segoe UI',13,'bold'))
        canvas.create_text(x+width/2,y+height/2+self.p(15),text='Выходные не входят в подсчёт' if excluded else 'Запусти таймер — занятия появятся здесь',fill=MUTED,
                           font=('Segoe UI',9),width=width-self.p(24),justify='center')

    def hover(self,canvas,event):
        text = None
        if canvas==self.chart and self.mode!='day':
            for x1,y1,x2,y2,day,description in self.day_regions:
                if x1<=event.x<=x2 and y1<=event.y<=y2:
                    text = description
                    break
            canvas.configure(cursor='hand2' if text else '')
        else:
            items = canvas.find_overlapping(event.x,event.y,event.x,event.y)
            if items:
                text = self.hits.get((canvas,items[-1]))
        if text:
            self.tooltip.show(text,event.x_root,event.y_root)
        else:
            self.tooltip.hide()

    def click_day(self,event):
        if self.mode=='day':
            return
        for x1,y1,x2,y2,day,description in self.day_regions:
            if x1<=event.x<=x2 and y1<=event.y<=y2:
                self.anchor = day
                self.follow_current = day==now_moscow().date()
                self.set_mode('day')
                return

    def return_to_timer(self):
        self.tooltip.hide()
        self.hidden_by_owner=False
        self.window.withdraw()
        self.app.show_page('timer')
        self.app.show()

    def hide(self):
        self.hidden_by_owner = self.window.state()!='withdrawn'
        self.tooltip.hide()
        self.window.withdraw()

    def wheel(self,event):
        if self.section=='sleep':
            self.sleep_page.scroll_delta(event.delta)
            return 'break'
        pane = self.legend_pane
        x,y = event.x_root,event.y_root
        if pane.winfo_rootx()<=x<pane.winfo_rootx()+pane.winfo_width() and pane.winfo_rooty()<=y<pane.winfo_rooty()+pane.winfo_height():
            pane.scroll_delta(event.delta)
            return 'break'

    def restore(self):
        if self.hidden_by_owner:
            self.hidden_by_owner = False
            self.window.deiconify()
            self.refresh(force=True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.tooltip.close()
        if self.native:
            self.native.stop()
        if self.sleep_page:self.sleep_page.close()
        if self.layout_job:
            self.window.after_cancel(self.layout_job)
        self.window.destroy()
        self.app.stats = None
