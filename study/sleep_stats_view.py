"""Sleep statistics and optional morning diary, inside the shared statistics window."""
from datetime import date,timedelta
import math
from pathlib import Path
import tkinter as tk
import webbrowser
from sleep_days import SleepStore
from sleep_stats_core import sleep_report
from stats_core import period_bounds,period_label,move_period,short_time
from study_core import now_moscow

BG,PANEL,TEXT,MUTED,ACCENT='#16191F','#20252E','#F2F3F5','#9DA5B3','#AFC3F2'
SOURCES=[('Consensus Sleep Diary · 2012','https://pmc.ncbi.nlm.nih.gov/articles/PMC3250369/'),
         ('Регулярность сна · 2021','https://pubmed.ncbi.nlm.nih.gov/33864369/'),
         ('Рекомендация AASM/SRS для взрослых','https://pmc.ncbi.nlm.nih.gov/articles/PMC4442216/'),
         ('Дневник сна NIH','https://www.nhlbi.nih.gov/resources/sleep-diary')]


class SleepStatsPane(tk.Frame):
    def __init__(self,parent,owner):
        super().__init__(parent,bg=BG)
        self.owner,self.app,self.p=owner,owner.app,owner.p
        self.data=SleepStore(self.app.store.db)
        self.anchor=self.app.day
        self.mode=self.app.store.setting('sleep_stats_mode','week')
        if self.mode not in ('day','week','month'):self.mode='week'
        self.signature=None;self.entry_signature=None;self.chart_signature=None;self.report=None;self.hits=[]
        self.remainder=0.;self.native=None;self.dialog=None;self.entry_buttons={}
        self.canvas=tk.Canvas(self,bg=BG,bd=0,highlightthickness=0,yscrollincrement=1)
        self.canvas.pack(fill='both',expand=True)
        self.inner=tk.Frame(self.canvas,bg=BG,padx=self.p(24),pady=self.p(8))
        self.item=self.canvas.create_window(0,0,window=self.inner,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.item,width=e.width))
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        toolbar=tk.Frame(self.inner,bg=BG);toolbar.pack(fill='x',pady=(0,self.p(10)))
        self.mode_buttons={}
        for mode,title in [('day','День'),('week','Неделя'),('month','Месяц')]:
            b=self.app.button(toolbar,title,lambda m=mode:self.set_mode(m),small=True)
            b.pack(side='left',padx=(0,self.p(4)));self.mode_buttons[mode]=b
        self.app.button(toolbar,'Как читать',self.method,small=True).pack(side='right')
        self.app.button(toolbar,'К отметкам',lambda:self.open_log(self.anchor),small=True).pack(side='right',padx=self.p(6))
        nav=tk.Frame(self.inner,bg=BG);nav.pack(fill='x',pady=(0,self.p(14)))
        self.app.button(nav,'‹',lambda:self.navigate(-1),small=True).pack(side='left')
        self.period=self.label(nav,'',12,bold=True);self.period.pack(side='left',expand=True)
        self.app.button(nav,'›',lambda:self.navigate(1),small=True).pack(side='left')
        self.app.button(nav,'Сегодня',self.today,small=True).pack(side='right',padx=(self.p(8),0))
        cards=tk.Frame(self.inner,bg=BG);cards.pack(fill='x')
        self.cards={}
        for i,(key,title) in enumerate([('duration','Сон за день ≈'),('bed','Ложусь'),('wake','Просыпаюсь'),('spread','Разброс пробуждения')]):
            cards.columnconfigure(i,weight=1,uniform='cards')
            card=tk.Frame(cards,bg=PANEL,padx=self.p(12),pady=self.p(11))
            card.grid(row=0,column=i,sticky='nsew',padx=(0,self.p(8) if i<3 else 0))
            self.label(card,title,9,color=MUTED).pack(anchor='w')
            value=self.label(card,'—',20,bold=True,color=ACCENT);value.pack(anchor='w',pady=(self.p(5),0))
            self.cards[key]=value
        self.coverage=self.label(self.inner,'',9,color=MUTED)
        self.coverage.pack(anchor='w',pady=self.p(9))
        self.sleepless_total=self.label(self.inner,'',12,bold=True,color=ACCENT)
        self.sleepless_total.pack(anchor='w',pady=(0,self.p(9)))
        self.nap_total=self.label(self.inner,'',10,color='#97CFA8')
        self.nap_total.pack(anchor='w',pady=(0,self.p(9)))
        chart_box=tk.Frame(self.inner,bg=PANEL);chart_box.pack(fill='x')
        self.label(chart_box,'Длительность по дню пробуждения',12,bold=True).pack(anchor='w',padx=self.p(14),pady=(self.p(12),0))
        self.chart=tk.Canvas(chart_box,bg=PANEL,bd=0,highlightthickness=0,height=self.p(200))
        self.chart.pack(fill='x',padx=self.p(8),pady=self.p(8))
        self.chart.bind('<Configure>',lambda e:self.draw_chart())
        self.chart.bind('<Motion>',self.hover);self.chart.bind('<Leave>',lambda e:self.owner.tooltip.hide())
        self.detail=tk.Frame(self.inner,bg=PANEL,padx=self.p(14),pady=self.p(11))
        self.detail.pack(fill='x',pady=self.p(12))
        self.overview=self.label(self.detail,'',10);self.overview.pack(anchor='w')
        self.activity=self.label(self.detail,'',10);self.activity.pack(anchor='w',pady=(self.p(7),0))
        self.note=self.label(self.detail,'',9,color=MUTED);self.note.pack(anchor='w',pady=(self.p(7),0))
        self.detail_button=self.app.button(self.detail,'Уточнить сон',self.edit_primary,small=True)
        self.detail_button.pack(anchor='w',pady=(self.p(8),0))
        self.entries=tk.Frame(self.inner,bg=BG)
        self.entries.pack(fill='x')
        if self.app.native_enabled:
            from native_scroll import NativeStudyScroll
            self.native=NativeStudyScroll(self,self.scroll_delta,self.scroll_pixels)
        self.bind('<MouseWheel>',self.wheel,add='+')
        self.refresh(force=True)

    def label(self,parent,text,size,color=TEXT,bold=False):
        return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,bd=0,anchor='w',justify='left',
                        font=('Segoe UI',size,'bold' if bold else 'normal'))

    def scroll_pixels(self,value):
        self.remainder+=value;whole=int(self.remainder);self.remainder-=whole
        self.canvas.yview_scroll(whole,'units')

    def scroll_delta(self,delta):self.scroll_pixels(-delta*self.p(40)/120)
    def wheel(self,event):self.scroll_delta(event.delta);return 'break'

    def set_mode(self,mode):
        self.mode=mode;self.app.store.set_setting('sleep_stats_mode',mode)
        self.canvas.yview_moveto(0);self.refresh(force=True)

    def navigate(self,direction):
        self.anchor=move_period(self.mode,self.anchor,direction);self.refresh(force=True)

    def today(self):self.anchor=now_moscow().date();self.refresh(force=True)

    def refresh(self,force=False):
        rows=self.data.logical_records();diary=self.data.diary()
        signature=(self.mode,self.anchor,tuple(tuple(r.values()) for r in rows),
                   tuple((k,tuple(v.values())) for k,v in sorted(diary.items())),self.data.latency_minutes,
                   tuple(sorted(self.app.store.days_off())),int(sum(self.app.timer.totals.values())),now_moscow().strftime('%Y-%m-%d %H:%M'),
                   tuple(sorted(self.data.groups.nights())),tuple(tuple(r.values()) for r in self.data.nap_records()))
        if not force and signature==self.signature:return
        self.signature=signature
        start,end=period_bounds(self.mode,self.anchor)
        self.report=sleep_report(self.data,start,end,self.app.timer.totals,self.app.store.days_off())
        r=self.report
        self.period.configure(text=period_label(self.mode,self.anchor))
        for mode,b in self.mode_buttons.items():b.configure(bg=ACCENT if mode==self.mode else PANEL,fg=BG if mode==self.mode else TEXT)
        self.cards['duration'].configure(text=short_time(r['mean_seconds']) if r['mean_seconds'] is not None else '—')
        self.cards['bed'].configure(text=r['bed']['mean'] or '—')
        self.cards['wake'].configure(text=r['wake']['mean'] or '—')
        sd=r['wake']['sd_minutes'];self.cards['spread'].configure(text=f'{sd:.0f} мин' if sd is not None else '—')
        self.coverage.configure(text=f'Заполнено дней: {r["completed_days"]} из {r["expected_days"]} · пропуски не считаются нулевым сном')
        self.sleepless_total.configure(text=f'Ночей без сна: {r["sleepless_nights"]}')
        self.nap_total.configure(text=f'Дневной сон: {short_time(r["nap_seconds"])} · эпизодов: {len(r["naps"])}')
        quality=f'{r["quality"]:.1f}/5 · оценок: {r["quality_n"]}' if r['quality'] is not None else 'нет оценок'
        median=short_time(r['median_seconds']) if r['median_seconds'] is not None else '—'
        self.overview.configure(text=f'Медиана: {median}   ·   Качество: {quality}')
        a=r['activity'];ratio=a['ratio']
        self.activity.configure(text=(f'Учёба / бодрствование: {ratio:.1%} · {short_time(a["study_seconds"])} / {short_time(a["awake_seconds"])}' if ratio is not None else 'Учёба / бодрствование: —')+(f' · выходных исключено: {len(r["off_days"])}' if r['off_days'] else ''))
        self.note.configure(text=f'Засыпание уточнено: {r["latency_n"]}/{len(r["episodes"])} · пробуждения: {r["awake_n"]}/{len(r["episodes"])}'+(' · проверь короткие или противоречивые записи' if r['review_n'] else ''))
        self.detail_button.configure(state='normal' if r['episodes'] else 'disabled')
        if self.mode=='day':self.entries.pack_forget()
        elif not self.entries.winfo_manager():self.entries.pack(fill='x')
        entry_signature=(self.mode,self.anchor,tuple(tuple(r.values()) for r in rows),signature[3],self.data.latency_minutes,signature[-2:])
        if force or entry_signature!=self.entry_signature:
            self.entry_signature=entry_signature
            for child in self.entries.winfo_children():child.destroy()
            self.entry_buttons={}
            for e in reversed(r['episodes']):
                row=tk.Frame(self.entries,bg=PANEL,padx=self.p(12),pady=self.p(9));row.pack(fill='x',pady=(0,self.p(6)))
                self.app.button(row,'Отметки',lambda episode=e:self.open_log(date.fromisoformat(episode['day']),episode['wake_id']),small=True).pack(side='right',padx=(self.p(6),0))
                b=self.app.button(row,'Уточнить',lambda episode=e:self.edit_episode(episode),small=True)
                b.pack(side='right');self.entry_buttons[e['wake_id']]=b
                duration='проверь отметки' if e['needs_review'] else f'≈ {short_time(e["seconds"])}'
                self.label(row,f'{date.fromisoformat(e["day"]):%d.%m.%Y} · {duration}',11,bold=True).pack(anchor='w')
                source='по дневнику' if e['latency_reported'] else f'засыпание +{e["latency_minutes"]} мин'
                self.label(row,f'{e["bed"]:%d.%m %H:%M} → {e["wake"]:%d.%m %H:%M} · {source}',9,color=MUTED).pack(anchor='w',pady=(self.p(3),0))
        if force or self.chart_signature!=entry_signature:
            self.chart_signature=entry_signature;self.draw_chart()

    def draw_chart(self):
        if not self.report:return
        c=self.chart;c.delete('all');self.hits=[]
        width,height=c.winfo_width(),c.winfo_height()
        if width<20 or height<20:return
        r=self.report;left,right,top,bottom=self.p(40),width-self.p(8),self.p(15),height-self.p(27)
        maximum=max([10]+[(v or 0)/3600 for v in r['totals'].values()]);maximum=math.ceil(maximum/2)*2
        for h in range(0,maximum+1,2):
            y=bottom-(bottom-top)*h/maximum
            c.create_line(left,y,right,y,fill='#353C47')
            c.create_text(left-self.p(5),y,text=f'{h} ч',fill=MUTED,anchor='e',font=('Segoe UI',8))
        step=(right-left)/len(r['days'])
        for i,day in enumerate(r['days']):
            x=left+step*i;value=r['totals'][day];x1,x2=x+step*.17,x+step*.83
            if value is None:
                c.create_text(x+step/2,bottom-self.p(9),text='—',fill=MUTED,font=('Segoe UI',9))
            else:
                y=bottom-(bottom-top)*(value/3600)/maximum
                c.create_rectangle(x1,y,x2,max(y+1,bottom),fill=ACCENT,outline='',tags='sleep-bar')
                if r['nap_totals'][day]>0:
                    boundary=bottom-(bottom-top)*((value-r['nap_totals'][day])/3600)/maximum
                    c.create_rectangle(x1,y,x2,max(y+1,boundary),fill='#97CFA8',outline='',tags='sleep-nap')
            if len(r['days'])<=7 or i%3==0:
                c.create_text(x+step/2,bottom+self.p(12),text=f'{day:%d.%m}',fill=MUTED,font=('Segoe UI',8))
            if day.isoformat() in r['sleepless_days']:
                c.create_text(x+step/2,top,text='●',fill='#EEA6AD',font=('Segoe UI',10),tags='sleepless-night')
            group=r['daily'][day]
            tip=f'{day:%d.%m.%Y}\n'+('Нет завершённых записей' if value is None else f'Сон ≈ {short_time(value)} · периодов: {len(group)+len(r["nap_daily"][day])}')
            if r['nap_totals'][day]:tip+=f'\nДневной сон: {short_time(r["nap_totals"][day])}'
            if any(e['awake_minutes'] is None for e in group):tip+='\nНочное бодрствование не уточнено'
            self.hits.append((x,top,x+step,bottom,tip))

    def hover(self,event):
        hit=next((h for h in self.hits if h[0]<=event.x<h[2] and h[1]<=event.y<=h[3]),None)
        if hit:self.owner.tooltip.show(hit[4],event.x_root,event.y_root)
        else:self.owner.tooltip.hide()

    def open_log(self,day,record_id=None):
        self.owner.hidden_by_owner=False;self.owner.window.withdraw()
        self.app.show_page('sleep');self.app.sleep_page.anchor=day;self.app.sleep_page.focus_id=record_id
        self.app.sleep_page.refresh(force=True);self.app.show()

    def edit_primary(self):
        if self.report['episodes']:self.edit_episode(max(self.report['episodes'],key=lambda e:e['seconds']))

    def edit_episode(self,episode):
        if self.dialog and self.dialog.winfo_exists():self.dialog.lift();return
        dialog=tk.Toplevel(self.owner.window);self.dialog=dialog
        dialog.title('Дневник сна');dialog.configure(bg=BG);dialog.transient(self.owner.window);dialog.resizable(False,False)
        body=tk.Frame(dialog,bg=BG,padx=self.p(18),pady=self.p(14));body.pack(fill='both',expand=True)
        self.label(body,f'Пробуждение {episode["wake"]:%d.%m.%Y}',12,bold=True).pack(anchor='w')
        values=self.data.diary().get(episode['wake_id'],{})
        self.diary_values={}
        for key,title in [('latency_minutes','Засыпал, мин'),('awake_minutes','Пробуждения после засыпания, мин'),('quality','Качество сна · 1 плохо, 5 отлично'),('notes','Заметка')]:
            self.label(body,title,10).pack(anchor='w',pady=(self.p(9),self.p(3)))
            value=values.get(key);variable=tk.StringVar(value='' if value is None else str(value))
            self.diary_values[key]=variable
            tk.Entry(body,textvariable=variable,bg=PANEL,fg=TEXT,insertbackground=TEXT,font=('Segoe UI',11),relief='flat',width=38).pack(fill='x',ipady=self.p(4))
        self.label(body,f'Пусто = неизвестно. Засыпание по умолчанию: {self.data.latency_minutes} мин.',8,color=MUTED).pack(anchor='w',pady=self.p(8))
        error=self.label(body,'',9,color='#F09898');error.configure(wraplength=self.p(330));error.pack(fill='x')
        def save():
            try:
                parsed={k:int(v.get()) if v.get().strip() else None for k,v in self.diary_values.items() if k!='notes'}
                self.data.save_diary(episode['wake_id'],parsed['latency_minutes'],parsed['awake_minutes'],parsed['quality'],self.diary_values['notes'].get())
            except ValueError as exc:error.configure(text=str(exc));return
            dialog.destroy();self.refresh(force=True)
        self.diary_save=save;self.diary_error=error
        self.app.button(body,'Сохранить',save,primary=True).pack(fill='x',pady=(self.p(8),0))
        dialog.bind('<Escape>',lambda e:dialog.destroy());dialog.update_idletasks();self.app.dark_title(dialog);dialog.grab_set()

    def method(self):
        dialog=tk.Toplevel(self.owner.window);dialog.title('Как читать статистику сна');dialog.configure(bg=BG)
        body=tk.Frame(dialog,bg=BG,padx=self.p(20),pady=self.p(18));body.pack(fill='both',expand=True)
        text=('Отмечай отход ко сну и окончательное пробуждение. Утром можно уточнить засыпание, ночное бодрствование и качество сна.\n\n'
              'Сон ≈ пробуждение − отход ко сну − засыпание − ночное бодрствование. Пустое поле пробуждений означает, что они не учтены.\n\n'
              'Среднее и медиана считаются по заполненным дням. Все завершённые периоды за день пробуждения суммируются; время режима берётся из самого длинного периода. Пропуски не равны нулю.\n\n'
              'Периоды длиннее 24 часов и противоречивые отметки сохраняются для проверки, но не входят в средние.\n\n'
              'Разброс — стандартное отклонение времени пробуждения с учётом полуночи. Это описание режима, а не диагноз или оценка здоровья. Для одной записи разброс не вычисляется.\n\n'
              'Сравнивай недели после 1–2 недель последовательных записей. Для взрослых 18–60 лет AASM рекомендует регулярно спать 7 часов и более; это не индивидуальный порог и не вывод по одной ночи.\n\n'
              'Выходной исключается из доли учёбы, но сохраняется в статистике сна. Доля учёбы не показывает причинную связь сна и продуктивности.')
        label=self.label(body,text,10);label.configure(wraplength=self.p(580));label.pack(fill='x')
        for title,url in SOURCES:self.app.button(body,title,lambda link=url:webbrowser.open(link),small=True).pack(anchor='w',pady=self.p(3))
        self.app.button(body,'Закрыть',dialog.destroy,small=True).pack(anchor='e')
        dialog.update_idletasks();self.app.dark_title(dialog)

    def close(self):
        if self.native:self.native.stop()
        if self.dialog and self.dialog.winfo_exists():self.dialog.destroy()
