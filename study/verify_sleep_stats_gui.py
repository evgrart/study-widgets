"""Real Tk navigation, diary editing and scrolling with an isolated running timer."""
from datetime import datetime,date
from pathlib import Path
import json,tempfile,sys,time,ctypes
import tkinter as tk
from unittest.mock import patch
from study_core import Store,Timer,MOSCOW,COLORS
from sleep_days import SleepStore
from verify_timer import Clock
from widget import App,dpi_setup

def at(d,h=0,m=0):return datetime(2026,11,d,h,m,tzinfo=MOSCOW)

dpi_setup();clock=Clock(at(10,12))
with tempfile.TemporaryDirectory() as folder,patch('widget.now_moscow',side_effect=clock.wall), \
     patch('sleep_view.now_moscow',side_effect=clock.wall),patch('sleep_days.now_moscow',side_effect=clock.wall), \
     patch('sleep_stats_view.now_moscow',side_effect=clock.wall):
    folder=Path(folder);store=Store(folder/'test.db');cid=store.save_category('ML',COLORS[1])
    store.add_time({(cid,'2026-11-04'):3600})
    data=SleepStore(store.db,clock.wall)
    for day in range(1,10):data.save(at(day,23),at(day,8))
    data.save(wake=at(10,8))
    raw=data.records()
    timer=Timer(store,clock.read,clock.wall);root=tk.Tk();root.withdraw()
    errors=[];root.report_callback_exception=lambda *e:errors.append(str(e[1]))
    app=App(root,folder,timer,native=True)
    root.geometry('860x1300+20000+20000');root.deiconify();root.update()
    app.toggle(cid);app.show_page('sleep');root.update()
    assert not hasattr(app.sleep_page,'cards')
    app.stats_button.invoke();root.update()
    stats=app.stats;pane=stats.sleep_page
    stats.window.geometry('1800x1200+20000+20000');root.update()
    assert stats.section=='sleep' and pane.winfo_ismapped() and not stats.study_page.winfo_ismapped()
    pane.anchor=date(2026,11,4);pane.set_mode('week');root.update();pane.draw_chart()
    assert pane.report['completed_days']==7
    assert pane.chart.find_withtag('sleep-bar') and pane.hits
    assert pane.native.report()['raw_hook']
    old_buttons=dict(pane.entry_buttons);pane.refresh();assert pane.entry_buttons==old_buttons
    episode=next(e for e in pane.report['episodes'] if e['day']=='2026-11-04')
    pane.edit_episode(episode);root.update()
    pane.diary_values['awake_minutes'].set('9999');pane.diary_save();root.update()
    assert pane.dialog.winfo_exists() and pane.diary_error.cget('text')
    pane.diary_values['latency_minutes'].set('15');pane.diary_values['awake_minutes'].set('30')
    pane.diary_values['quality'].set('4');pane.diary_save();root.update()
    assert not pane.dialog.winfo_exists()
    assert pane.report['latency_n']==1 and pane.report['quality']==4
    assert data.records()==raw and timer.active==cid
    clock.advance(8);timer.tick();stats.refresh()
    assert timer.category_time(cid,'2026-11-10')==8
    stats.section_buttons['study'].invoke();root.update()
    assert stats.study_page.winfo_ismapped() and not pane.winfo_ismapped()
    stats.section_buttons['sleep'].invoke();root.update();assert pane.winfo_ismapped()
    pane.set_mode('month');root.update();pane.scroll_pixels(1500);root.update()
    assert pane.canvas.yview()[0]>0
    pane.set_mode('day');root.update();assert not pane.entries.winfo_ismapped()
    assert pane.cards['spread'].cget('text')=='—'
    pane.open_log(date(2026,11,4),episode['wake_id']);root.update()
    assert stats.window.state()=='withdrawn' and app.page=='sleep'
    assert app.sleep_page.anchor==date(2026,11,4) and app.sleep_page.focus_record['id']==episode['wake_id']
    app.stats_button.invoke();root.update();assert app.stats is stats and stats.section=='sleep'
    stats.timer_button.invoke();root.update();assert app.page=='timer' and stats.window.state()=='withdrawn'
    assert timer.active==cid
    if '--preview' in sys.argv:
        from capture_window import capture
        root.geometry('860x1300+80+50');root.update()
        app.show_stats('sleep');pane.anchor=date(2026,11,4);pane.set_mode('week')
        stats.window.geometry('2020x1400+220+40');stats.window.attributes('-topmost',True)
        stats.window.lift();root.update();time.sleep(.7);root.update()
        capture(ctypes.windll.user32.GetParent(stats.window.winfo_id()),Path(__file__).parent/'sleep-statistics-preview.bmp',screen=True)
    app.close();assert not errors,errors
    store=Store(folder/'test.db');assert SleepStore(store.db).diary()[episode['wake_id']]['quality']==4
    store.close()
print(json.dumps(dict(separate_sections=True,logging_retained=True,chart=True,missing_data=True,
    optional_diary=True,native_scroll=True,no_timer_interruption=True,return_navigation=True,persisted=True)))
