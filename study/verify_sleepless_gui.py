"""Exercise the new night checkbox, timer totals and sleep statistics together."""
from datetime import datetime,date
from pathlib import Path
import tempfile,tkinter as tk
from unittest.mock import patch
from study_core import Store,Timer,MOSCOW,COLORS
from widget import App,dpi_setup
from verify_timer import Clock

dpi_setup();clock=Clock(datetime(2026,11,9,10,tzinfo=MOSCOW))
with tempfile.TemporaryDirectory() as folder, \
     patch('widget.now_moscow',side_effect=clock.wall), \
     patch('sleep_view.now_moscow',side_effect=clock.wall), \
     patch('sleep_days.now_moscow',side_effect=clock.wall), \
     patch('sleep_stats_view.now_moscow',side_effect=clock.wall):
    root=tk.Tk();root.withdraw();errors=[]
    root.report_callback_exception=lambda *args:errors.append(str(args[1]))
    store=Store(Path(folder)/'test.sqlite3');cid=store.save_category('ML',COLORS[0])
    store.add_time({(cid,'2026-11-07'):3600,(cid,'2026-11-08'):7200})
    timer=Timer(store,clock.read,clock.wall);app=App(root,Path(folder),timer,native=False)
    app.day=date(2026,11,8);app.follow_today=False
    root.geometry('860x1300+20000+20000');root.deiconify();root.update()
    app.show_page('sleep');root.update();pane=app.sleep_page
    pane.data.save(None,datetime(2026,11,7,8,tzinfo=MOSCOW))
    pane.anchor=date(2026,11,7);pane.refresh(force=True)
    app.toggle(cid);pane.sleepless_check.invoke();root.update()
    assert pane.sleepless.get() and not pane.error.cget('text')
    assert pane.period.cget('text')=='07.11 — 08.11.2026'
    assert timer.active==cid and timer.day_time(date(2026,11,7))==10800
    assert pane.times['wake_at'].cget('text')=='08:00'
    assert pane.times['bed_at'].cget('text')=='—'
    pane.times['bed_at'].event_generate('<Button-1>');root.update()
    pane.editor_values['bed_at'].set('23:00');pane.editor_save();root.update()
    assert not pane.dialog.winfo_exists()
    assert pane.data.logical_records()[0]['bed_at']=='2026-11-08T23:00:00+03:00'
    app.show_stats();root.update();stats=app.stats.sleep_page
    stats.mode='week';stats.anchor=date(2026,11,7);stats.refresh(force=True);root.update()
    assert stats.sleepless_total.cget('text')=='Ночей без сна: 1'
    assert stats.chart.find_withtag('sleepless-night')
    pane.sleepless_check.invoke();root.update()
    assert not pane.sleepless.get()
    assert timer.day_time(date(2026,11,7))==3600
    assert timer.day_time(date(2026,11,8))==7200
    assert timer.active==cid
    app.close();assert not errors,errors
print('Sleepless checkbox, merged editor, live timer, graph and undo verified')
