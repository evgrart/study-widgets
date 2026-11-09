"""Exercise the anchored action, reset and undo with disposable study data."""
from datetime import date
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
from study_core import Store,Timer,COLORS
from verify_timer import Clock
from widget import App,dpi_setup

dpi_setup()
with tempfile.TemporaryDirectory() as folder:
    store=Store(Path(folder)/'test.sqlite3');a=store.save_category('ML',COLORS[0]);b=store.save_category('C++',COLORS[1])
    store.add_time({(a,'2026-11-03'):3600,(b,'2026-11-03'):600})
    clock=Clock();timer=Timer(store,clock.read,clock.wall)
    with patch('widget.now_moscow',side_effect=clock.wall):
        root=tk.Tk();errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        app=App(root,Path(folder),timer,native=False)
        root.geometry('900x1300+20000+20000');app.day=date(2026,11,3);app.follow_today=False;root.update()
        row=app.rows[a]['row'];app.toggle(a);clock.advance(5);app.tick()
        app.rows[a]['title'].event_generate('<Button-1>');root.update()
        assert app.category_actions is None  # An ordinary click only selects the category.
        app.rows[a]['title'].event_generate('<Button-3>');root.update()
        menu=app.category_actions;assert menu is not None
        menu.window.geometry('+20000+20000');root.update()
        assert menu.action.cget('text')=='Очистить'
        assert menu.window.winfo_height()<app.p(60)
        assert app.timer.active==a  # Opening a menu does not change a running session.
        menu.action.invoke();root.update()
        assert app.rows[a]['daily'].cget('text')=='00:00:00'
        assert app.total.cget('text')=='00:10:00'
        assert timer.active is None and app.rows[a]['row'] is row
        assert menu.action.cget('text')=='↶  Отменить'
        menu.action.invoke();root.update()
        assert app.category_actions is None
        assert app.rows[a]['daily'].cget('text')=='01:00:05'
        app.show_category_actions(a);root.update()
        assert app.category_actions is not None
        app.change_day(1);root.update();assert app.category_actions is None
        app.show_category_actions(a);root.update()
        assert app.category_actions.action.cget('state')=='disabled'
        app.hide();root.update();assert app.category_actions is None
        assert app.restore_session(dict(created_at=clock.wall().isoformat(),awake_seconds=clock.read(),
            category=a,active_day='2026-11-04',view_day='2026-11-03',session_seconds=123))
        assert app.day==date(2026,11,3) and timer.active_day==date(2026,11,4)
        app.close();assert not errors,errors
print('Category click, anchored reset, undo, paused session, totals and dismissal: OK')
