import unittest,tempfile,json,math,sqlite3,threading
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch,Mock
import tasks_core as tasks
import calendar_core as calendar
import deadline_core as deadlines
from icalendar import Calendar

class Hardening(unittest.TestCase):
    def store(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        return tasks.TaskStore(Path(folder.name)/'tasks.db')
    def remote(self,**values):
        row=dict(remote_id='task',list_id='list',list_title='My Tasks',title='Lesson',
                 due='2026-11-02',completed=False,date_label='Scheduled for Nov 2, 2026')
        row.update(values);return row

    def test_new_task_database_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            store=tasks.TaskStore(Path(folder)/'new'/'nested'/'tasks.db')
            self.assertEqual(store.items(),[])

    def test_snapshot_iterator(self):
        store=self.store();store.seed([{'title':'Lesson','due':'2026-11-02'}])
        store.merge(iter([self.remote(list_id='~default')]),['~default'])
        item=store.items()[0]
        self.assertFalse(item.pending)
        self.assertEqual(item.remote_id,'task')

    def test_complete_lists_iterator(self):
        store=self.store();store.merge([self.remote(remote_id=str(i),list_id='a') for i in range(3)],['a'])
        store.merge([],iter(['a']))
        self.assertEqual(store.items(),[])

    def test_remote_identity_delimiters(self):
        store=self.store()
        store.merge([self.remote(list_id='a/b',remote_id='c'),self.remote(list_id='a',remote_id='b/c')])
        self.assertEqual(len(store.items()),2)
        self.assertEqual(len({t.id for t in store.items()}),2)

    def test_remote_due_validation(self):
        store=self.store();store.merge([self.remote()]);before=store.items()
        with self.assertRaises(ValueError):store.merge([self.remote(due='not-a-date')],['list'])
        self.assertEqual(store.items(),before)

    def test_blank_seed_title(self):
        store=self.store()
        with self.assertRaises(ValueError):store.seed([{'title':'   ','due':None}])
        self.assertEqual(store.items(),[])

    def test_seed_due_validation(self):
        store=self.store()
        with self.assertRaises(ValueError):
            store.seed([{'title':'Valid','due':None},{'title':'Invalid','due':'2026-02-30'}])
        self.assertEqual(store.items(),[])

    def test_toggle_deleted_task(self):
        store=self.store()
        with self.assertRaises(ValueError):store.toggle('missing')


    def test_layout_clipped_intervals(self):
        day=date(2026,11,2);start=datetime(2026,11,2,10,tzinfo=calendar.MOSCOW)
        events=[calendar.Appointment('outside','Old',start-timedelta(days=2),start-timedelta(days=1)),
        calendar.Appointment('invalid','Reversed',start,start-timedelta(hours=1))]
        self.assertEqual(calendar.arrange(events,day),[])

    def test_linear_overlap_grouping(self):
        class Counted(datetime):
            comparisons=0
            def __gt__(self,other):
                Counted.comparisons+=1
                return super().__gt__(other)
        day=date(2026,11,2);start=Counted(2026,11,2,10,tzinfo=calendar.MOSCOW)
        end=Counted(2026,11,2,12,tzinfo=calendar.MOSCOW)
        events=[calendar.Appointment(str(i),str(i),start,end) for i in range(80)]
        self.assertEqual(len(calendar.arrange(events,day)),80)
        self.assertLess(Counted.comparisons,80*8)

    def test_blank_calendar_summary(self):
        payload=b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:empty\r\nDTSTART:20261102T100000\r\nDTEND:20261102T110000\r\nSUMMARY:   \r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        events=calendar.week_events(calendar.parse_calendar(payload),date(2026,11,2))
        self.assertEqual(events[0].title,'Без названия')

    def test_deadline_cache_root(self):
        with patch.object(deadlines,'read_json',return_value=[]):
            self.assertEqual(deadlines.load_deadlines(),([],None))
