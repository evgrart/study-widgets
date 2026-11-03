"""Check that continued study is attributed to the chosen date, not the wall date."""
from datetime import datetime,timedelta
from pathlib import Path
import json
import tempfile
import tkinter as tk
from unittest.mock import patch

from study_core import COLORS,MOSCOW,Store,Timer
from verify_timer import Clock
from widget import App,dpi_setup


def main():
    dpi_setup()
    clock = Clock(datetime(2026,11,4,12,tzinfo=MOSCOW))
    today = clock.now.date()
    yesterday = today-timedelta(days=1)
    with tempfile.TemporaryDirectory() as directory,patch('widget.now_moscow',side_effect=clock.wall):
        folder = Path(directory)
        store = Store(folder/'test.sqlite3')
        a = store.save_category('Алгосы шад',COLORS[0])
        b = store.save_category('ML',COLORS[1])
        store.add_time({(a,str(yesterday)):11587,(b,str(yesterday)):600,(a,str(today)):45})
        timer = Timer(store,clock.read,clock.wall)
        root = tk.Tk()
        root.withdraw()
        app = App(root,folder,timer,native=False)
        root.geometry('860x1300+20000+20000')
        root.deiconify()
        root.update()
        assert app.rows[a]['daily'].cget('text')=='00:00:45'
        assert 'all_time' not in app.rows[a]
        app.change_day(-1)
        assert app.rows[a]['daily'].cget('text')=='03:13:07'
        assert app.rows[b]['daily'].cget('text')=='00:10:00'
        assert 'сегодня' not in app.play.cget('text')
        app.rows[a]['start'].invoke()
        assert app.day==yesterday and timer.active==a and timer.active_day==yesterday
        clock.advance(20)
        timer.tick()
        app.refresh()
        assert app.rows[a]['daily'].cget('text')=='03:13:27'
        assert timer.category_time(a,today)==45
        app.change_day(1)
        assert app.day==today and app.rows[a]['start'].cget('text')=='▶'
        clock.advance(10)
        timer.tick()
        app.refresh()
        assert app.rows[a]['daily'].cget('text')=='00:00:45'
        assert timer.category_time(a,yesterday)==11617
        # Explicitly starting the same subject on another date switches the bucket.
        app.rows[a]['start'].invoke()
        assert timer.active_day==today
        clock.advance(5)
        timer.tick()
        app.refresh()
        assert app.rows[a]['daily'].cget('text')=='00:00:50'
        assert timer.category_time(a,yesterday)==11617
        app.play.invoke()
        assert timer.active is None
        app.change_day(-1)
        app.select(b)
        app.play.invoke()
        assert app.day==yesterday and timer.active_day==yesterday and timer.active==b
        clock.advance(15)
        timer.tick()
        app.play.invoke()
        assert timer.category_time(b,yesterday)==615
        assert timer.category_time(b,today)==0
        app.close()

        restored = Store(folder/'test.sqlite3')
        timer2 = Timer(restored,clock.read,clock.wall)
        root2 = tk.Tk()
        root2.withdraw()
        app2 = App(root2,folder,timer2,native=False)
        assert app2.day==yesterday
        assert app2.rows[a]['daily'].cget('text')=='03:13:37'
        assert app2.rows[b]['daily'].cget('text')=='00:10:15'
        app2.change_day(1)
        assert app2.rows[a]['daily'].cget('text')=='00:00:50'
        assert app2.rows[b]['daily'].cget('text')=='00:00:00'
        app2.close()
    print(json.dumps(dict(selected_date_kept=True,counts_for_selected_day=True,
                          browsing_does_not_reassign_time=True,same_subject_different_dates=True,
                          history_survives_restart=True,view_date_saved=True,numbers_only=True)))


if __name__=='__main__':
    main()
