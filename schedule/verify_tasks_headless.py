"""A visible setup browser must never be used for periodic task automation."""
import unittest
from unittest.mock import Mock, patch
from tasks_browser import sync_in_background, PROFILE


class BackgroundBrowserTests(unittest.TestCase):
    def setUp(self):
        self.driver=Mock()
        self.context=self.driver.chromium.launch_persistent_context.return_value
        self.page=Mock();self.context.pages=[self.page]

    def test_normal_sync_is_headless_and_no_visible_tab_is_attached(self):
        with patch('tasks_browser.own_debugger_running',return_value=False),patch('tasks_browser.synchronize') as sync:
            sync_in_background(self.driver)
        self.driver.chromium.connect_over_cdp.assert_not_called()
        args=self.driver.chromium.launch_persistent_context.call_args
        self.assertEqual(args.args,(str(PROFILE),))
        self.assertIs(args.kwargs['headless'],True)
        sync.assert_called_once_with(self.page)
        self.context.close.assert_called_once()

    def test_leftover_login_browser_is_closed_before_headless_launch(self):
        setup=self.driver.chromium.connect_over_cdp.return_value
        with patch('tasks_browser.own_debugger_running',return_value=True), \
             patch('tasks_browser.urlopen',side_effect=OSError),patch('tasks_browser.synchronize') as sync:
            sync_in_background(self.driver)
        setup.new_browser_cdp_session.return_value.send.assert_called_once_with('Browser.close')
        setup.new_page.assert_not_called()
        self.assertIs(self.driver.chromium.launch_persistent_context.call_args.kwargs['headless'],True)
        sync.assert_called_once_with(self.page)

    def test_failure_does_not_launch_a_visible_fallback(self):
        self.driver.chromium.launch_persistent_context.side_effect=RuntimeError('Profile unavailable')
        with patch('tasks_browser.own_debugger_running',return_value=False), \
             patch('tasks_browser.subprocess.Popen') as headed,patch('tasks_browser.synchronize') as sync:
            with self.assertRaises(RuntimeError):sync_in_background(self.driver)
        headed.assert_not_called();sync.assert_not_called()
        self.driver.chromium.connect_over_cdp.assert_not_called()

    def test_failed_sync_still_closes_its_headless_context(self):
        with patch('tasks_browser.own_debugger_running',return_value=False), \
             patch('tasks_browser.synchronize',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):sync_in_background(self.driver)
        self.context.close.assert_called_once()


if __name__=='__main__':unittest.main()
