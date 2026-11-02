"""Offline checks for durable task edits, date handling and crash recovery."""
from datetime import date
from pathlib import Path
import tempfile
import unittest

from tasks_core import Task, TaskStore, week_tasks, sidebar_tasks
from tasks_browser import parse_due, UnsupportedTasksPage, is_own_debugger, PROFILE


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.folder.name)/'tasks.db')
        self.entries = [{'title':'Read lesson','due':'2026-11-02'}, {'title':'Later','due':'2026-11-09'},
                        {'title':'No date','due':None}]
        self.store.seed(self.entries, 'fixture')

    def tearDown(self):
        self.folder.cleanup()

    def first(self):
        return next(t for t in self.store.items() if t.title=='Read lesson')

    def remote(self, **fields):
        return dict(remote_id='remote-1', list_id='~default', list_title='My Tasks',
                    title='Read lesson', due='2026-11-02', completed=False,
                    date_label='Scheduled for Today', **fields)

    def test_seed_is_idempotent(self):
        self.store.seed(self.entries, 'fixture')
        self.assertEqual(len(self.store.items()), 3)

    def test_retry_recovers_existing_remote_creation(self):
        self.store.merge([self.remote()], ['~default'])
        self.assertEqual(len(self.store.items()), 3)
        self.assertEqual(self.first().remote_id, 'remote-1')
        self.assertFalse(self.first().pending)

    def test_offline_completion_survives_restart(self):
        self.store.toggle(self.first().id)
        reopened = TaskStore(self.store.path)
        task = next(t for t in reopened.items() if t.title=='Read lesson')
        self.assertTrue(task.completed)
        self.assertEqual(task.pending, 'create')

    def test_stale_ack_does_not_drop_new_edit(self):
        self.store.merge([self.remote()], ['~default'])
        self.store.toggle(self.first().id)
        old = self.first()
        self.store.toggle(old.id)
        self.store.acknowledge(old.id, old.revision)
        self.assertEqual(self.first().pending, 'status')
        self.assertFalse(self.first().completed)

    def test_remote_completion_keeps_scheduled_day(self):
        self.store.merge([self.remote()], ['~default'])
        row=self.remote()
        row.update(completed=True, due=None, date_label='')
        self.store.merge([row], ['~default'])
        self.assertEqual(self.first().due, '2026-11-02')
        self.assertTrue(self.first().completed)

    def test_remote_changes_do_not_overwrite_queued_edit(self):
        self.store.merge([self.remote()], ['~default'])
        self.store.toggle(self.first().id)
        self.store.merge([self.remote()], ['~default'])
        self.assertTrue(self.first().completed)
        self.assertEqual(self.first().pending, 'status')

    def test_new_already_completed_task_has_its_scheduled_date(self):
        row=self.remote();row.update(remote_id='new-completed',title='Replacement lesson',
            completed=True,due='2026-11-04',date_label='Scheduled for Yesterday',due_known=True)
        self.store.merge([row],['~default'])
        task=next(t for t in self.store.items() if t.remote_id=='new-completed')
        self.assertEqual(task.due,'2026-11-04')
        self.assertTrue(task.completed)

    def test_explicit_removed_date_on_completed_task_clears_cache(self):
        self.store.merge([self.remote()],['~default'])
        row=self.remote();row.update(completed=True,due=None,date_label='',due_known=True)
        self.store.merge([row],['~default'])
        self.assertIsNone(self.first().due)

    def test_remote_rename_and_reschedule_merge_while_completion_is_pending(self):
        self.store.merge([self.remote()], ['~default'])
        identity=self.first().id
        self.store.toggle(identity)
        remote=self.remote();remote.update(title='Renamed lesson',due='2026-11-05',date_label='Scheduled for Today')
        self.store.merge([remote],['~default'])
        task=self.store.get(identity)
        self.assertEqual(task.title,'Renamed lesson')
        self.assertEqual(task.due,'2026-11-05')
        self.assertTrue(task.completed)
        self.assertEqual(task.pending,'status')
        self.assertEqual(task.revision,1)

    def test_remote_delete_does_not_remove_unsent_tasks(self):
        self.store.merge([self.remote()], ['~default'])
        self.store.merge([], ['~default'])
        self.assertEqual({t.title for t in self.store.items()}, {'Later','No date'})

    def test_same_title_on_different_days_is_not_deduplicated(self):
        self.store.seed([{'title':'Read lesson','due':'2026-11-03'}], 'other-plan')
        self.store.merge([self.remote()], ['~default'])
        tasks=[t for t in self.store.items() if t.title=='Read lesson']
        self.assertEqual(len(tasks), 2)
        self.assertEqual(sum(t.remote_id is not None for t in tasks), 1)

    def test_week_excludes_next_monday_and_undated_tasks(self):
        self.assertEqual([t.title for t in week_tasks(self.store.items(), date(2026,11,2))], ['Read lesson'])

    def test_sidebar_overdue_and_rolling_week(self):
        rows=[Task('old','Old unfinished','2026-10-01'),Task('old-done','Old done','2026-11-04',True),
              Task('today','Today done','2026-11-05',True),Task('week','Week ahead','2026-11-12'),
              Task('later','Too far','2026-11-13'),Task('none','Undated',None),
              Task('none-done','Undated completed',None,True)]
        shown=sidebar_tasks(rows,date(2026,11,5))
        self.assertEqual({t.id for t in shown},{'old','today','week','none','none-done'})
        self.assertTrue(all(t.due is None for t in shown[:2]))
        self.assertNotIn('today',{t.id for t in sidebar_tasks(rows,date(2026,11,6))})

    def test_sidebar_year_boundary(self):
        rows=[Task('end','End','2027-01-06'),Task('after','After','2027-01-07')]
        self.assertEqual([t.id for t in sidebar_tasks(rows,date(2026,12,30))],['end'])

    def test_relative_dates(self):
        self.assertEqual(parse_due('Scheduled for Tomorrow', date(2026,11,2)), '2026-11-03')
        self.assertEqual(parse_due('Scheduled for Yesterday', date(2026,11,2)), '2026-11-01')
        self.assertEqual(parse_due('Scheduled for 2 days ago',date(2026,11,5)),'2026-11-03')
        self.assertEqual(parse_due('Scheduled for 1 day ago',date(2026,1,1)),'2025-12-31')
        self.assertEqual(parse_due('Scheduled for In 2 days',date(2026,12,31)),'2027-01-02')

    def test_reuse_only_our_browser_profile(self):
        own={'Name':'msedge.exe','CommandLine':f'msedge.exe --user-data-dir="{PROFILE}" --remote-debugging-port=18763 --new-window'}
        self.assertTrue(is_own_debugger(own))
        self.assertFalse(is_own_debugger(dict(own,Name='other.exe')))
        self.assertFalse(is_own_debugger(dict(own,CommandLine='msedge.exe --user-data-dir=C:\\NormalProfile --remote-debugging-port=18763')))
        self.assertFalse(is_own_debugger(dict(own,CommandLine=own['CommandLine'].replace('18763','18764'))))

    def test_absolute_dates_and_year_boundary(self):
        self.assertEqual(parse_due('Scheduled for Wed, Nov 4', date(2026,11,2)), '2026-11-04')
        self.assertEqual(parse_due('Scheduled for Jan 3', date(2026,12,30)), '2027-01-03')
        self.assertEqual(parse_due('Scheduled for January 3, 2028', date(2026,12,30)), '2028-01-03')

    def test_unknown_date_is_not_silently_erased(self):
        with self.assertRaises(UnsupportedTasksPage):
            parse_due('Scheduled for unknown', date(2026,11,2))


if __name__=='__main__':
    unittest.main()
