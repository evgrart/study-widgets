from datetime import date,datetime
from pathlib import Path
import tempfile,tkinter as tk
from unittest.mock import patch
from study_core import Store,Timer,MOSCOW,COLORS
from widget import App,dpi_setup
from verify_timer import Clock

dpi_setup();clock=Clock(datetime(2026,11,9,10,tzinfo=MOSCOW))
with tempfile.TemporaryDirectory() as folder,patch('widget.now_moscow',side_effect=clock.wall), \
     patch('sleep_view.now_moscow',side_effect=clock.wall),patch('sleep_days.now_moscow',side_effect=clock.wall), \
     patch('sleep_stats_view.now_moscow',side_effect=clock.wall):
    store=Store(Path(folder)/'test.sqlite3');cid=store.save_category('ML',COLORS[0])
    timer=Timer(store,clock.read,clock.wall);root=tk.Tk();root.withdraw();errors=[]
    root.report_callback_exception=lambda *args:errors.append(str(args[1]))
    app=App(root,Path(folder),timer,native=False);app.day=date(2026,11,8);app.follow_today=False
    root.geometry('860x1300+20000+20000');root.deiconify();root.update();app.show_page('sleep');root.update()
    pane=app.sleep_page;pane.data.save(wake=datetime(2026,11,8,8,tzinfo=MOSCOW));pane.refresh(force=True)
    original=pane.data.records();app.toggle(cid)
    pane.nap_button.invoke();root.update();pane.nap_values['start'].set('14:00');pane.nap_values['end'].set('13:00')
    pane.nap_save();root.update();assert pane.nap_dialog.winfo_exists() and pane.nap_error.cget('text')
    pane.nap_values['end'].set('15:00');pane.nap_save();root.update()
    assert not pane.nap_dialog.winfo_exists() and len(pane.data.naps())==1
    assert pane.nap_list.winfo_manager() and pane.data.records()==original and timer.active==cid
    app.show_stats();root.update();stats=app.stats.sleep_page;stats.mode='day';stats.anchor=date(2026,11,8)
    stats.refresh(force=True);root.update();assert stats.report['nap_seconds']==3600
    assert stats.chart.find_withtag('sleep-nap') and 'эпизодов: 1' in stats.nap_total.cget('text')
    with patch('sleep_view.messagebox.askyesno',return_value=True):pane.delete_nap(pane.data.nap_records()[0])
    assert not pane.data.naps() and not pane.nap_list.winfo_manager()
    assert pane.data.records()==original and timer.active==cid
    app.close();assert not errors,errors
print('Nap editor, validation, selected-day list, graph, deletion and running timer verified')
