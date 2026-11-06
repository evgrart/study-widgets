"""Login redirects cannot lose a valid connection or start visible task automation."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,MagicMock,PropertyMock,patch
import tempfile,unittest
from tasks_browser import (wait_for_login,login_and_sync,TasksBrowser,BrowserError,GoogleLoginRequired)

class LoginTests(unittest.TestCase):
    def account(self):return Mock(read_text=Mock(return_value='{"email":"fixture@example.test"}'))
    def signed_page(self):
        page=Mock();page.url='https://tasks.google.com/tasks/'
        page.get_by_role.return_value.count.return_value=1
        page.get_by_role.return_value.get_attribute.return_value='Google Account: fixture@example.test'
        return page
    def test_login_survives_closed_original_tab(self):
        old=Mock();type(old).url=PropertyMock(side_effect=BrowserError('Page was closed'))
        new=self.signed_page();context=Mock()
        type(context).pages=PropertyMock(side_effect=[[old],[new]])
        browser=Mock();browser.contexts=[context]
        with patch('tasks_browser.ACCOUNT',self.account()),patch('tasks_browser.AUTH') as auth,patch('tasks_browser.time.sleep'):
            self.assertTrue(wait_for_login(browser,timeout=5))
            auth.touch.assert_called_once()
        old.wait_for_timeout.assert_not_called()
    def test_closed_login_window_uses_saved_session_verification(self):
        browser=Mock();browser.contexts=[];ticks=iter(range(20))
        with patch('tasks_browser.ACCOUNT',self.account()),patch('tasks_browser.time.monotonic',side_effect=lambda:next(ticks)),patch('tasks_browser.time.sleep'):
            self.assertFalse(wait_for_login(browser,timeout=20))
    def test_wrong_account_is_not_accepted(self):
        page=self.signed_page();page.get_by_role.return_value.get_attribute.return_value='Google Account: other@example.test'
        browser=Mock();browser.contexts=[SimpleNamespace(pages=[page])]
        with patch('tasks_browser.ACCOUNT',self.account()),patch('tasks_browser.AUTH') as auth:
            with self.assertRaises(GoogleLoginRequired):wait_for_login(browser)
            auth.touch.assert_not_called()
    def test_auth_marker_survives_a_later_page_error(self):
        page=self.signed_page();account=page.get_by_role.return_value
        account.click.side_effect=BrowserError('Network interrupted while loading task list')
        with tempfile.TemporaryDirectory() as folder,patch('tasks_browser.ACCOUNT',self.account()),patch('tasks_browser.AUTH',Path(folder)/'connected'):
            with self.assertRaises(BrowserError):TasksBrowser(page).ready()
            self.assertTrue((Path(folder)/'connected').exists())
    def test_task_sync_happens_headlessly_after_login(self):
        driver=Mock();events=[]
        with patch('tasks_browser.subprocess.Popen'),patch('tasks_browser.urlopen',return_value=MagicMock()), \
             patch('tasks_browser.own_debugger_running',return_value=True),patch('tasks_browser.wait_for_login',return_value=True), \
             patch('tasks_browser.state'),patch('tasks_browser.close_setup_browser',side_effect=lambda d:events.append('close')), \
             patch('tasks_browser.sync_in_background',side_effect=lambda d:events.append('headless')),patch('tasks_browser.synchronize') as headed_sync:
            login_and_sync(driver)
        self.assertEqual(events,['close','headless']);headed_sync.assert_not_called()
    def test_manual_refresh_recovers_existing_profile_without_old_flag(self):
        import widget
        with tempfile.TemporaryDirectory() as folder,patch('widget.ROOT',Path(folder)):
            (Path(folder)/'google-tasks-profile').mkdir()
            app=SimpleNamespace(start_tasks_process=Mock())
            widget.WeekWidget.refresh_tasks(app,True)
            app.start_tasks_process.assert_called_once_with()

if __name__=='__main__':unittest.main()
