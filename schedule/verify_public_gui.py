"""Account-free rendering check, including completed fonts and scale changes."""
from pathlib import Path
from datetime import date
from unittest.mock import patch
import tempfile,tkinter as tk
import widget
from tasks_core import TaskStore

with tempfile.TemporaryDirectory() as folder:
    store=TaskStore(Path(folder)/'tasks.db')
    rows=[dict(remote_id=str(i),list_id='fixture',list_title='My Tasks',title=f'Example task {i}',
               due=f'2026-11-{2+i%7:02}',completed=i%3==0,date_label='') for i in range(24)]
    store.merge(rows,['fixture'])
    with patch('widget.TaskStore',return_value=store),patch.object(widget.WeekWidget,'refresh_tasks'), \
         patch.object(widget.WeekWidget,'refresh_deadlines'),patch.object(widget.WeekWidget,'write_health'),patch('widget.save_config'):
        root=tk.Tk();root.withdraw();errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        app=widget.WeekWidget(root,dict(feed_url='',refresh_seconds=120,desktop_mode=False,
                                      topmost=False,autostart=False,maximized=False,side_view='tasks'))
        app.refresh=lambda *args:None
        root.geometry('1800x1000+20000+20000');root.deiconify();root.update()
        app.calendar=widget.parse_calendar((Path(__file__).parent.parent/'examples/calendar.ics').read_bytes())
        app.first_day=date(2026,11,2);app.follow_today=False
        for scale in (1.0,2.0,3.0):
            root.tk.call('tk','scaling',scale);app.draw();root.update_idletasks()
            assert len(app.task_boxes)==24
            expected=app.measure_font(app.font(10,True)).metrics('linespace')
            for item in app.canvas.find_withtag('task-title'):
                font=app.canvas.itemcget(item,'font')
                assert int(root.tk.call('font','metrics',font,'-linespace'))==expected
                assert int(root.tk.splitlist(font)[1])==-app.p(10)
        assert not errors,errors
        app.quit()
print('Account-free week rendering and stable completed fonts: OK')
