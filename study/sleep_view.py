"""Sleep tab in the study timer; all records stay in the local SQLite database."""
from datetime import date, datetime, timedelta
import os
import tkinter as tk
from tkinter import messagebox
from sleep_days import SleepStore, stamp, night_day, times_for_day
from study_core import MOSCOW, format_time, now_moscow

BG, PANEL, TEXT, MUTED = '#16191F', '#20252E', '#F2F3F5', '#9DA5B3'
ACCENT, LINE, ERROR = '#AFC3F2', '#303640', '#F09898'


def short_duration(seconds):
    if seconds is None:
        return '—'
    minutes = max(0,int(seconds)//60)
    return f'{minutes//60} ч {minutes%60:02} мин'


class SleepPane(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent,bg=BG)
        self.app, self.p = app, app.p
        self.data = SleepStore(app.store.db)
        self.anchor = app.day
        self.mode = 'day'
        self.signature = None
        self.last_second = None
        self.native = None
        self.remainder = 0.0
        self.dialog = None
        self.latency_dialog = None
        self.nap_dialog=None;self.nap_signature=None
        self.focus_record = None
        self.focus_id = None
        self.delete_buttons = {}
        self.canvas = tk.Canvas(self,bg=BG,highlightthickness=0,bd=0,yscrollincrement=1,width=1,height=1)
        self.canvas.pack(fill='both',expand=True)
        self.inner = tk.Frame(self.canvas,bg=BG,padx=self.p(22),pady=self.p(8))
        self.item = self.canvas.create_window(0,0,window=self.inner,anchor='nw')
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize)
        app.label(self.inner,'Сон',17,bold=True).pack(anchor='w')
        self.status = app.label(self.inner,'',10,color=ACCENT)
        self.status.configure(justify='left',anchor='w',wraplength=self.p(335))
        self.status.pack(fill='x',pady=(self.p(7),self.p(12)))
        status_actions=tk.Frame(self.inner,bg=BG)
        self.status_actions=status_actions
        status_actions.pack(fill='x',pady=(0,self.p(10)))
        self.delete_current=app.button(status_actions,'Удалить запись',lambda:self.delete_record(self.focus_record),small=True)
        self.delete_current.pack(side='left')
        actions = tk.Frame(self.inner,bg=BG)
        actions.pack(fill='x')
        actions.columnconfigure((0,1),weight=1,uniform='actions')
        self.bed_button = app.button(actions,'Лёг спать',self.mark_bed,primary=True)
        self.bed_button.grid(row=0,column=1,sticky='ew',padx=(self.p(5),0))
        self.wake_button = app.button(actions,'Проснулся',self.mark_wake,primary=True)
        self.wake_button.grid(row=0,column=0,sticky='ew',padx=(0,self.p(5)))
        manual = tk.Frame(self.inner,bg=BG)
        manual.pack(fill='x',pady=(self.p(8),self.p(12)))
        self.latency_button=app.button(manual,'',self.edit_latency,small=True)
        self.latency_button.pack(side='left')
        self.nap_button=app.button(manual,'+ Дневной сон',self.edit_nap,small=True)
        self.nap_button.pack(side='left',padx=(self.p(6),0))
        self.error = app.label(self.inner,'',9,color=ERROR)
        self.error.configure(wraplength=self.p(335),justify='left')
        self.error.pack(fill='x')
        nav=tk.Frame(self.inner,bg=BG)
        nav.pack(fill='x',pady=(0,self.p(9)))
        app.button(nav,'‹',lambda:self.navigate(-1),small=True).pack(side='left')
        self.period=app.label(nav,'',10,color=MUTED)
        self.period.pack(side='left',expand=True)
        app.button(nav,'›',lambda:self.navigate(1),small=True).pack(side='left')
        app.button(nav,'Сегодня',self.today,small=True).pack(side='right',padx=(self.p(5),0))
        self.day_off=tk.BooleanVar(value=False)
        self.off_check=tk.Checkbutton(self.inner,text='Выходной',variable=self.day_off,command=self.toggle_day_off,
                       bg=BG,fg=MUTED,activebackground=BG,activeforeground=TEXT,selectcolor=PANEL,
                       bd=0,highlightthickness=0,font=('Segoe UI',9),cursor='hand2')
        self.off_check.pack(anchor='w',pady=(0,self.p(9)))
        self.sleepless=tk.BooleanVar(value=False)
        self.sleepless_check=tk.Checkbutton(self.inner,text='Не спал',variable=self.sleepless,command=self.toggle_sleepless,
                       bg=BG,fg=MUTED,activebackground=BG,activeforeground=TEXT,selectcolor=PANEL,
                       bd=0,highlightthickness=0,font=('Segoe UI',9),cursor='hand2')
        self.sleepless_check.pack(anchor='w',pady=(0,self.p(9)))
        times=tk.Frame(self.inner,bg=BG)
        times.pack(fill='x',pady=(self.p(4),0))
        self.times={}
        for column,(key,title) in enumerate([('wake_at','Проснулся'),('bed_at','Лёг спать')]):
            times.columnconfigure(column,weight=1,uniform='times')
            card=tk.Frame(times,bg=PANEL,padx=self.p(12),pady=self.p(12),cursor='hand2',takefocus=True)
            card.grid(row=0,column=column,sticky='ew',padx=(0,self.p(6) if column==0 else 0))
            heading=app.label(card,title,9,color=MUTED)
            heading.pack(anchor='w')
            label=app.label(card,'—',19,color=ACCENT,bold=True)
            label.pack(anchor='w',pady=(self.p(5),0));self.times[key]=label
            for target in (card,heading,label):
                target.configure(cursor='hand2')
                target.bind('<Button-1>',lambda event,key=key:self.edit(self.focus_record,field=key))
            for sequence in ('<Return>','<space>'):
                card.bind(sequence,lambda event,key=key:self.edit(self.focus_record,field=key))
        activity=tk.Frame(self.inner,bg=PANEL,padx=self.p(12),pady=self.p(12))
        self.activity_box=activity
        self.nap_list=tk.Frame(self.inner,bg=BG)
        activity.pack(fill='x',pady=(self.p(10),0))
        app.label(activity,'Учёба / бодрствование',12,bold=True).pack(anchor='w')
        self.activity_percent=app.label(activity,'—',24,color=ACCENT,bold=True)
        self.activity_percent.pack(anchor='w',pady=(self.p(6),0))
        self.activity_detail=app.label(activity,'',10,color=MUTED)
        self.activity_detail.configure(justify='left',anchor='w',wraplength=self.p(335))
        self.activity_detail.pack(fill='x',pady=(self.p(3),0))
        self.refresh(force=True)
        if app.native_enabled and os.name=='nt':
            from native_scroll import NativeStudyScroll
            self.native=NativeStudyScroll(self,self.scroll_delta,self.scroll_pixels)

    def scroll_pixels(self,value):
        self.remainder+=value
        amount=int(self.remainder)
        self.remainder-=amount
        self.canvas.yview_scroll(amount,'units')

    def resize(self,event):
        self.canvas.itemconfigure(self.item,width=event.width)
        width=max(self.p(200),event.width-self.p(46))
        for name in ('status','error','off_check','activity_detail'):
            label=getattr(self,name,None)
            if label:label.configure(wraplength=max(self.p(160),width))

    def scroll_delta(self,value):
        self.scroll_pixels(-value*self.p(40)/120)

    def navigate(self,direction):
        self.anchor+=timedelta(days=direction)
        self.focus_id=None
        self.refresh(force=True)

    def today(self):
        self.anchor=now_moscow().date()
        self.focus_id=None
        self.refresh(force=True)

    def toggle_day_off(self):
        self.app.store.set_day_off(self.anchor,self.day_off.get())
        self.app.refresh()
        if self.app.stats:self.app.stats.refresh(force=True)
        self.refresh(force=True)

    def mark_bed(self):
        self._mark(lambda:self.data.mark_bed(self.anchor))

    def toggle_sleepless(self):
        self.app.timer.tick();self.app.timer.flush()
        try:self.data.set_sleepless(self.anchor,self.sleepless.get())
        except ValueError as exc:
            self.error.configure(text=str(exc));self.refresh(force=True);return
        self.error.configure(text='');self.focus_id=None
        self.app.refresh();self.refresh(force=True)
        if self.app.stats:self.app.stats.refresh(force=True)

    def mark_wake(self):
        self._mark(self.data.mark_wake)

    def refresh_naps(self):
        start=self.data.groups.start(self.anchor)
        rows=[r for r in self.data.nap_records() if self.data.groups.start(r['day'])==start]
        signature=(self.anchor,tuple(tuple(r.values()) for r in rows))
        if signature==self.nap_signature:return
        self.nap_signature=signature
        for child in self.nap_list.winfo_children():child.destroy()
        if not rows:self.nap_list.pack_forget();return
        if not self.nap_list.winfo_manager():self.nap_list.pack(fill='x',pady=self.p(8),before=self.activity_box)
        for row in rows:
            box=tk.Frame(self.nap_list,bg=PANEL,padx=self.p(10),pady=self.p(8));box.pack(fill='x',pady=(0,self.p(5)))
            begin,end=stamp(row['start_at']),stamp(row['end_at'])
            caption=f'Дневной сон · {begin:%d.%m %H:%M}–{end:%H:%M}'
            label=self.app.label(box,caption,10,color=ACCENT)
            label.pack(side='left',expand=True,fill='x');label.configure(cursor='hand2')
            label.bind('<Button-1>',lambda event,r=row:self.edit_nap(r))
            self.app.button(box,'Удалить',lambda r=row:self.delete_nap(r),small=True).pack(side='right')

    def naps_changed(self):
        self.refresh(force=True)
        if self.app.stats:self.app.stats.refresh(force=True)

    def delete_nap(self,row):
        if not messagebox.askyesno('Удалить дневной сон','Удалить этот дневной сон?',parent=self.app.root):return
        self.data.delete_nap(row['id']);self.naps_changed()

    def edit_nap(self,row=None):
        if self.nap_dialog and self.nap_dialog.winfo_exists():self.nap_dialog.lift();return
        day=date.fromisoformat(row['day']) if row else self.anchor
        dialog=tk.Toplevel(self.app.root);self.nap_dialog=dialog
        dialog.title('Дневной сон');dialog.configure(bg=BG);dialog.transient(self.app.root)
        dialog.resizable(False,False);dialog.grab_set()
        body=tk.Frame(dialog,bg=BG,padx=self.p(20),pady=self.p(18));body.pack(fill='both',expand=True)
        self.app.label(body,f'Дневной сон · {day:%d.%m.%Y}',12,bold=True).pack(anchor='w',pady=(0,self.p(12)))
        values={}
        for key,title,column in [('start','Уснул · ЧЧ:ММ','start_at'),('end','Проснулся · ЧЧ:ММ','end_at')]:
            self.app.label(body,title,10,bold=True).pack(anchor='w')
            values[key]=tk.StringVar(value=stamp(row[column]).strftime('%H:%M') if row else '')
            entry=tk.Entry(body,textvariable=values[key],bg=PANEL,fg=TEXT,insertbackground=TEXT,
                font=('Segoe UI',12),relief='flat',width=26)
            entry.pack(fill='x',ipady=self.p(7),pady=(self.p(6),self.p(12)))
        error=self.app.label(body,'',9,color=ERROR);error.configure(wraplength=self.p(300),justify='left');error.pack(fill='x')
        def save(event=None):
            try:
                end,begin=times_for_day(day,values['end'].get(),values['start'].get())
                self.data.save_nap(begin,end,row['id'] if row else None)
            except ValueError as exc:error.configure(text=str(exc));return
            dialog.destroy();self.naps_changed()
        self.app.button(body,'Сохранить',save,primary=True).pack(fill='x',pady=(self.p(10),0))
        dialog.bind('<Return>',save);dialog.bind('<Escape>',lambda event:dialog.destroy())
        dialog.update_idletasks();self.app.dark_title(dialog)
        dialog.geometry(f'+{max(0,self.app.root.winfo_x()+self.p(25))}+{max(0,self.app.root.winfo_y()+self.p(80))}')
        self.nap_values,self.nap_save,self.nap_error=values,save,error

    def edit_latency(self):
        if self.latency_dialog and self.latency_dialog.winfo_exists():
            self.latency_dialog.lift();return
        dialog=tk.Toplevel(self.app.root)
        self.latency_dialog=dialog
        dialog.title('Время засыпания');dialog.configure(bg=BG)
        dialog.transient(self.app.root);dialog.resizable(False,False)
        body=tk.Frame(dialog,bg=BG,padx=self.p(20),pady=self.p(18));body.pack(fill='both',expand=True)
        self.app.label(body,'Обычно засыпаю за, мин',11,bold=True).pack(anchor='w')
        self.latency_value=tk.StringVar(value=str(self.data.latency_minutes))
        entry=tk.Spinbox(body,from_=0,to=180,textvariable=self.latency_value,width=5,
            bg=PANEL,fg=TEXT,insertbackground=TEXT,buttonbackground=PANEL,
            font=('Segoe UI',14),relief='flat')
        entry.pack(fill='x',pady=self.p(10))
        self.latency_error=self.app.label(body,'',9,color=ERROR)
        self.latency_error.configure(wraplength=self.p(300),justify='left');self.latency_error.pack(fill='x')
        def save(event=None):
            try:self.data.set_latency_minutes(int(self.latency_value.get().strip()))
            except ValueError:
                self.latency_error.configure(text='Укажи целое число минут от 0 до 180.');return
            dialog.destroy();self.refresh(force=True)
        self.latency_save=save
        self.app.button(body,'Сохранить',save,primary=True).pack(fill='x',pady=(self.p(10),0))
        dialog.bind('<Return>',save);dialog.bind('<Escape>',lambda event:dialog.destroy())
        dialog.update_idletasks();self.app.dark_title(dialog)
        dialog.geometry(f'+{max(0,self.app.root.winfo_x()+self.p(30))}+{max(0,self.app.root.winfo_y()+self.p(100))}')
        dialog.grab_set();entry.focus_set();entry.selection_range(0,'end')

    def _mark(self,action):
        try:record_id=action()
        except ValueError as exc:self.error.configure(text=str(exc));return
        except Exception:self.error.configure(text='Не удалось сохранить отметку. Попробуй ещё раз.');return
        self.error.configure(text='')
        row=next((r for r in self.data.logical_records() if r['id']==record_id),None)
        if row:self.anchor=night_day(row)
        self.refresh(force=True)

    def refresh(self,force=False):
        now=now_moscow()
        second=int(now.timestamp())
        if not force and self.last_second==second:return
        self.last_second=second
        self.latency_button.configure(text=f'Засыпание: {self.data.latency_minutes} мин')
        days_off=self.app.store.days_off()
        start=self.data.groups.start(self.anchor);end=self.data.groups.end(self.anchor)
        off=str(start) in days_off
        if self.day_off.get()!=off:self.day_off.set(off)
        self.sleepless.set(str(self.anchor) in self.data.groups.nights())
        self.period.configure(text=f'{self.anchor:%d.%m.%Y}' if start==end else f'{start:%d.%m} — {end:%d.%m.%Y}')
        self.refresh_naps()
        records=self.data.logical_records()
        selected=[r for r in records if night_day(r)==start]
        self.focus_record=next((r for r in selected if r['id']==self.focus_id),selected[0] if selected else None)
        for key,label in self.times.items():
            when=stamp(self.focus_record[key]) if self.focus_record and self.focus_record[key] else None
            text=when.strftime('%H:%M') if when else '—'
            if label.cget('text')!=text:label.configure(text=text)
        activity=self.data.activity_report(self.anchor,self.anchor,self.app.timer.totals,days_off)
        ratio=activity['ratio']
        percent=f'{ratio*100:.1f} %' if ratio is not None else '—'
        detail=('Выходной' if off else
                f'{short_duration(activity["study_seconds"])} учёбы / {short_duration(activity["awake_seconds"])} бодрствования'
                if ratio is not None else '')
        for label,text in ((self.activity_percent,percent),(self.activity_detail,detail)):
            if label.cget('text')!=text:label.configure(text=text)
        current=self.focus_record if self.focus_record and self.focus_record['wake_at'] and (
            not self.focus_record['bed_at'] or stamp(self.focus_record['bed_at'])>now) else None
        self.delete_current.configure(state='normal' if self.focus_record else 'disabled')
        if current:
            wake=stamp(current['wake_at'])
            duration=short_duration((now-wake).total_seconds())
            self.status.configure(text=f'Проснулся {wake:%d.%m в %H:%M} · бодрствую {duration}')
        elif self.focus_record:
            self.status.configure(text='')
        else:
            self.status.configure(text='Сначала отметь «Проснулся», затем «Лёг спать».')
        if self.status.cget('text'):
            if not self.status.winfo_manager():
                self.status.pack(fill='x',pady=(self.p(7),self.p(12)),before=self.status_actions)
        else:self.status.pack_forget()
        self.bed_button.configure(state='normal')

    def delete_record(self,row,parent=None):
        if not row:return False
        period=f'{night_day(row):%d.%m.%Y}'
        if row.get('end_day'):period+=f' — {date.fromisoformat(row["end_day"]):%d.%m.%Y}'
        if not messagebox.askyesno('Удалить запись',f'Удалить запись за {period}?',parent=parent or self.app.root):return False
        self.data.delete_selected(row)
        self.error.configure(text='')
        self.refresh(force=True)
        return True

    def edit(self,row=None,field=None):
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            if field in self.editor_entries:
                self.editor_entries[field].focus_set();self.editor_entries[field].selection_range(0,'end')
            return
        dialog=tk.Toplevel(self.app.root)
        self.dialog=dialog
        dialog.title('Изменить сон' if row else 'Добавить сон')
        dialog.configure(bg=BG)
        dialog.transient(self.app.root)
        dialog.resizable(False,False)
        dialog.grab_set()
        body=tk.Frame(dialog,bg=BG,padx=self.p(20),pady=self.p(18))
        body.pack(fill='both',expand=True)
        selected_day=self.data.groups.start(night_day(row) if row else self.anchor)
        end_day=self.data.groups.end(selected_day)
        self.app.label(body,f'День {selected_day:%d.%m.%Y}',12,color=ACCENT,bold=True).pack(anchor='w',pady=(0,self.p(6)))
        self.app.label(body,'Сначала пробуждение, затем сон',9,color=MUTED).pack(anchor='w',pady=(0,self.p(16)))
        values={};original={};entries={}
        for key,title in [('wake_at','Проснулся'),('bed_at','Лёг спать')]:
            self.app.label(body,f'{title} · ЧЧ:ММ',10,bold=True).pack(anchor='w')
            value=stamp(row[key]) if row and row[key] else None
            original[key]=value.strftime('%H:%M') if value else ''
            values[key]=tk.StringVar(value=original[key])
            entry=tk.Entry(body,textvariable=values[key],bg=PANEL,fg=TEXT,insertbackground=TEXT,
                           font=('Segoe UI',12),relief='flat',width=26)
            entry.pack(fill='x',pady=(self.p(6),self.p(15)),ipady=self.p(7))
            entries[key]=entry
        self.app.label(body,'Если время сна меньше времени пробуждения,\nэто сон на следующие сутки. Время Москвы.',9,color=MUTED).pack(anchor='w')
        preview=self.app.label(body,'',9,color=ACCENT)
        preview.configure(wraplength=self.p(310),justify='left')
        preview.pack(fill='x',pady=(self.p(8),0))

        def show_dates(*args):
            try:
                bed,wake=times_for_day(selected_day,values['bed_at'].get(),values['wake_at'].get(),row,end_day if end_day>selected_day else None)
                parts=[]
                if wake:parts.append(f'Встал: {wake:%d.%m в %H:%M}')
                if bed:parts.append(f'Лёг: {bed:%d.%m в %H:%M}')
                preview.configure(text='  ·  '.join(parts))
            except ValueError:preview.configure(text='')

        for value in values.values():value.trace_add('write',show_dates)
        show_dates()
        error=self.app.label(body,'',9,color=ERROR)
        error.configure(wraplength=self.p(310),justify='left')
        error.pack(fill='x',pady=self.p(10))

        def save(event=None):
            try:
                bed,wake=times_for_day(selected_day,values['bed_at'].get(),values['wake_at'].get(),row,end_day if end_day>selected_day else None)
                self.data.save_selected(bed,wake,row,selected_day)
            except ValueError as exc:
                error.configure(text=str(exc))
                return
            except Exception:error.configure(text='Не удалось сохранить. Попробуй ещё раз.');return
            dialog.destroy();self.refresh(force=True)

        self.app.button(body,'Сохранить',save,primary=True).pack(fill='x')
        dialog.bind('<Return>',save)
        dialog.bind('<Escape>',lambda e:dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(f'+{max(0,self.app.root.winfo_x()+self.p(20))}+{max(0,self.app.root.winfo_y()+self.p(45))}')
        self.editor_values,self.editor_save,self.editor_error=values,save,error
        self.editor_entries=entries
        if field in entries:
            entries[field].focus_set();entries[field].selection_range(0,'end')

    def close(self):
        if self.native:self.native.stop()
        if self.dialog and self.dialog.winfo_exists():self.dialog.destroy()
        if self.nap_dialog and self.nap_dialog.winfo_exists():self.nap_dialog.destroy()
