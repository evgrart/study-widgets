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
