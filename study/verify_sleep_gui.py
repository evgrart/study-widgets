"""Exercise real tab controls with disposable data and a running study session."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
import json
from study_core import Store, Timer, MOSCOW, COLORS
from verify_timer import Clock
from widget import App, dpi_setup


def main():
    dpi_setup()
    clock=Clock(datetime(2026,11,4,12,tzinfo=MOSCOW))
    with tempfile.TemporaryDirectory() as directory, \
         patch('widget.now_moscow',side_effect=clock.wall), \
         patch('sleep_view.now_moscow',side_effect=clock.wall), \
         patch('sleep_days.now_moscow',side_effect=clock.wall):
        folder=Path(directory)
        store=Store(folder/'test.sqlite3')
        cid=store.save_category('ML',COLORS[1])
        store.add_time({(cid,'2026-11-04'):3600})
        timer=Timer(store,clock.read,clock.wall)
        root=tk.Tk();root.withdraw()
        errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        app=App(root,folder,timer,native=False)
        root.geometry('860x1300+20000+20000');root.deiconify();root.update()
        app.toggle(cid)
        app.tab_buttons['sleep'].invoke();root.update()
        pane=app.sleep_page
        assert app.page=='sleep' and pane.winfo_ismapped()
        assert not app.timer_page.winfo_ismapped()
        assert timer.active==cid
        assert [child.cget('text') for child in pane.status_actions.winfo_children()]==['Удалить запись']
        pane.times['wake_at'].master.event_generate('<Button-1>');root.update()
        assert pane.dialog.winfo_exists()
        assert pane.editor_values['wake_at'].get()=='' and pane.editor_values['bed_at'].get()==''
        pane.dialog.destroy()
        assert pane.data.latency_minutes==25
        pane.latency_button.invoke();root.update()
        pane.latency_value.set('-5');pane.latency_save();root.update()
        assert pane.latency_dialog.winfo_exists() and pane.latency_error.cget('text')
        pane.latency_value.set('30');pane.latency_save();root.update()
        assert not pane.latency_dialog.winfo_exists() and pane.data.latency_minutes==30
        assert pane.latency_button.cget('text')=='Засыпание: 30 мин' and timer.active==cid
        clock.advance(20);timer.tick()
        assert timer.category_time(cid,'2026-11-04')==3620
        pane.wake_button.invoke();root.update()
        assert len(pane.data.records())==1 and pane.data.records()[0]['bed_at'] is None
        assert pane.times['wake_at'].cget('text')=='12:00'
        assert pane.times['bed_at'].cget('text')=='—'
        assert not hasattr(pane,'cards')  # Analytics moved to Statistics → Sleep.
        row=pane.data.records()[0]
        pane.times['bed_at'].event_generate('<Button-1>');root.update()
        assert pane.dialog.winfo_exists() and pane.editor_values['wake_at'].get()=='12:00'
        body=pane.dialog.winfo_children()[0]
        assert not any(isinstance(child,tk.Button) and child.cget('text')=='Удалить запись' for child in body.winfo_children())
        pane.editor_values['bed_at'].set('25:00')
        pane.editor_save();root.update()
        assert pane.dialog.winfo_exists() and pane.editor_error.cget('text')
        pane.editor_values['bed_at'].set('13:00')
        pane.editor_save();root.update()
        assert not pane.dialog.winfo_exists()
        assert pane.data.current() is not None and timer.active==cid
        assert pane.times['bed_at'].cget('text')=='13:00'
        clock.advance(3600);pane.refresh(force=True)
        assert pane.data.current() is None
        clock.advance(20*3600)
        pane.wake_button.invoke();root.update()
        assert pane.data.current() and pane.bed_button.cget('state')=='normal'
        clock.advance(3600)
        pane.bed_button.invoke();root.update()
        assert pane.data.current() is None
        assert len(pane.data.records())==2
        rid=pane.data.records()[0]['id']
        with patch('sleep_view.messagebox.askyesno',return_value=False):pane.delete_current.invoke()
        assert len(pane.data.records())==2
        with patch('sleep_view.messagebox.askyesno',return_value=True):pane.delete_current.invoke()
        assert len(pane.data.records())==1
        assert pane.delete_current.cget('text')=='Удалить запись'
        assert list(pane.editor_values)==['wake_at','bed_at']
        for index in range(1,25):
            wake=datetime(2026,10,index,8,tzinfo=MOSCOW)
            pane.data.save(wake+timedelta(hours=15),wake)
        pane.anchor=datetime(2026,11,4).date();pane.refresh(force=True)
        before=len(pane.data.records())
        pane.bed_button.invoke();root.update()
        assert pane.anchor==datetime(2026,11,4).date()
        assert pane.period.cget('text')=='04.11.2026'
        assert len(pane.data.records())==before
        assert not any(r['day']=='2026-11-05' for r in pane.data.records())
        selected=next(r for r in pane.data.records() if r['day']=='2026-11-04')
        assert selected['bed_at']==clock.now.isoformat()
        assert pane.times['wake_at'].cget('text')==selected['wake_at'][11:16]
        assert pane.times['bed_at'].cget('text')==selected['bed_at'][11:16]
        app.tab_buttons['timer'].invoke();root.update()
        assert app.page=='timer' and app.timer_page.winfo_ismapped()
        assert timer.active==cid and timer.active_day==datetime(2026,11,4).date()
        app.close()
        store=Store(folder/'test.sqlite3')
        from sleep_days import SleepStore
        assert len(SleepStore(store.db).records())==25
        store.close()
        assert not errors,errors
    print(json.dumps(dict(sleep_tab=True,study_keeps_running=True,partial_wake=True,
                         edit_validated=True,mark_buttons=True,selected_day_preserved=True,persisted=True)))


if __name__=='__main__':main()
