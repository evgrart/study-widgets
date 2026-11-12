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
