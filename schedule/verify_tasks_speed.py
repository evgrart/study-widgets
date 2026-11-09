"""Real-page date-picker fixture and sync ordering/confirmation regressions."""
from pathlib import Path
from datetime import date
import tempfile
import unittest
from unittest.mock import patch,Mock
from tasks_browser import TasksBrowser,parse_calendar_date,synchronize,UnsupportedTasksPage
from tasks_core import TaskStore
from playwright.sync_api import sync_playwright


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store=TaskStore(Path(self.folder.name)/'tasks.db')
        self.rows=[dict(remote_id=str(i),title=f'Task {i}',list_id='list',list_title='My Tasks',
                       due='2026-11-02',date_label='Scheduled for Nov 2, 2026',completed=False) for i in range(2)]
        self.store.merge(self.rows,['list'])

    def run_sync(self,reader):
        with patch('tasks_browser.TasksBrowser',return_value=reader),patch('tasks_browser.TaskStore',return_value=self.store), \
             patch('tasks_browser.AUTH'),patch('tasks_browser.state'):
            synchronize(Mock())

    def test_read_only_sync_reads_dates_once_without_reloading(self):
        reader=Mock();reader.snapshot.return_value=(self.rows,['list'])
        self.run_sync(reader)
        reader.ready.assert_called_once()
        reader.snapshot.assert_called_once_with(read_dates=True)

    def test_two_edits_are_sent_before_reading_completed_dates(self):
        for item in self.store.items():self.store.toggle(item.id)
        final=[dict(r,completed=True) for r in self.rows]
        events=[];reader=Mock()
        def snapshot(read_dates=True):
            events.append(('snapshot',read_dates))
            return (final if read_dates else self.rows),['list']
        reader.snapshot.side_effect=snapshot
        reader.set_completed.side_effect=lambda task:events.append(('send',task.remote_id))
        self.run_sync(reader)
        self.assertEqual(events[0],('snapshot',False))
        self.assertEqual([kind for kind,_ in events],['snapshot','send','send','snapshot'])
        self.assertTrue(all(t.completed and not t.pending for t in self.store.items()))
        self.assertTrue(all(t.due=='2026-11-02' for t in self.store.items()))

    def test_unconfirmed_server_change_remains_queued(self):
        task=self.store.items()[0];self.store.toggle(task.id)
        reader=Mock();reader.snapshot.return_value=(self.rows,['list'])
        with self.assertRaisesRegex(UnsupportedTasksPage,'server_did_not_confirm'):
            self.run_sync(reader)
        self.assertTrue(self.store.get(task.id).completed)
        self.assertEqual(self.store.get(task.id).pending,'status')

    def test_light_snapshot_cannot_create_falsely_undated_completed_task(self):
        task=self.store.items()[0];self.store.toggle(task.id)
        light=[dict(r,completed=True,due=None,date_label='') for r in self.rows]
        reader=Mock();reader.snapshot.side_effect=[(light,['list']),UnsupportedTasksPage('network')]
        before=self.store.items()
        with self.assertRaises(UnsupportedTasksPage):self.run_sync(reader)
        self.assertEqual(self.store.items(),before)

    def test_exact_picker_date_is_not_guessed_from_rounded_label(self):
        self.assertEqual(parse_calendar_date('30 October 2026 Selected'),date(2026,10,30))
        with self.assertRaises(UnsupportedTasksPage):parse_calendar_date('1 week ago')


def check_real_picker():
    with sync_playwright() as driver:
        browser=driver.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page();reader=TasksBrowser(page)
            page.set_content('''<section data-task-list-id="list" data-num-completed="1"><h2>My Tasks</h2>
                <div role="listitem" data-id="row"><span data-task-id="row" data-aria-label="Task title" data-rendered-value="Lesson">Lesson</span>
                <button aria-label="Mark completed: Lesson" aria-pressed="true"></button>
                <div role="button" aria-label="Scheduled for 1 week ago" onclick="document.querySelector('dialog').showModal()">1 week ago</div></div></section>
                <dialog aria-label="Date picker"><span id="day">30 October 2026</span><span id="selected">Selected</span>
                <button data-date-num="30" aria-pressed="true" aria-labelledby="day selected"></button>
                <button onclick="window.cancelled=true;document.querySelector('dialog').close()">Cancel</button>
                <button onclick="window.saved=true">Done</button></dialog>''')
            rows,lists=reader._snapshot_once()
            assert rows[0]['due']=='2026-10-30' and lists==['list']
            assert page.evaluate('window.cancelled===true && window.saved!==true')
            # Lightweight checkbox confirmation must not inspect any scheduled date.
            with patch.object(reader,'exact_date_label',side_effect=AssertionError('Date read')):
                rows,_=reader._snapshot_once(read_dates=False)
                assert rows[0]['due'] is None
        finally:browser.close()


if __name__=='__main__':
    unittest.main(exit=False)
    check_real_picker()
    print('Exact date picker read and lightweight snapshot: OK')
