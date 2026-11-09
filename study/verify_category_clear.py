"""Day-scoped reset, active sessions, undo and durable statistics."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from study_core import Store,Timer,COLORS
from stats_core import build_report
from verify_timer import Clock


class ClearTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.folder.name)/'test.sqlite3')
        self.a=self.store.save_category('ML',COLORS[0]);self.b=self.store.save_category('C++',COLORS[1])
        self.store.add_time({(self.a,'2026-11-03'):3600,(self.a,'2026-11-04'):1800,
                             (self.b,'2026-11-03'):600})
        self.clock=Clock();self.timer=Timer(self.store,self.clock.read,self.clock.wall)

    def tearDown(self):
        self.timer.close();self.folder.cleanup()

    def test_reset_preserves_other_days_and_categories_and_persists(self):
        removed=self.timer.clear_category_day(self.a,'2026-11-03')
        self.assertEqual(removed,{(self.a,'2026-11-03'):3600})
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),0)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-04'),1800)
        self.assertEqual(self.timer.category_time(self.b,'2026-11-03'),600)
        self.assertEqual(self.store.totals(),self.timer.totals)
        reopened=Store(self.store.path)
        try:self.assertNotIn((self.a,'2026-11-03'),reopened.totals())
        finally:reopened.close()
        report=build_report(self.timer.totals,self.store.categories(),'day',date(2026,11,3))
        self.assertEqual(report.total,600)

    def test_running_category_flushes_then_pauses_and_can_start_from_zero(self):
        self.timer.start(self.a,'2026-11-03');self.clock.advance(17.5)
        removed=self.timer.clear_category_day(self.a,'2026-11-03')
        self.assertEqual(removed[(self.a,'2026-11-03')],3617.5)
        self.assertIsNone(self.timer.active);self.assertEqual(self.timer.session_seconds,0)
        self.clock.advance(100);self.timer.tick()
        self.assertEqual(self.timer.day_time('2026-11-03'),600)
        self.timer.start(self.a,'2026-11-03');self.clock.advance(5);self.timer.pause()
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),5)

    def test_other_active_category_is_not_paused(self):
        self.timer.start(self.b,'2026-11-03');self.clock.advance(10)
        self.timer.clear_category_day(self.a,'2026-11-03')
        self.assertEqual(self.timer.active,self.b)
        self.clock.advance(5);self.timer.pause()
        self.assertEqual(self.timer.category_time(self.b,'2026-11-03'),615)

    def test_same_category_running_on_another_day_is_not_paused(self):
        self.timer.start(self.a,'2026-11-04');self.clock.advance(10)
        self.timer.clear_category_day(self.a,'2026-11-03')
        self.assertEqual(self.timer.active,self.a)
        self.assertEqual(self.timer.active_day,date(2026,11,4))
        self.assertEqual(self.timer.session_seconds,10)

    def test_undo_adds_original_amount_without_overwriting_new_study(self):
        removed=self.timer.clear_category_day(self.a,'2026-11-03')
        self.timer.start(self.a,'2026-11-03');self.clock.advance(7)
        self.timer.restore_category_time(removed)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),3607)
        self.assertEqual(self.store.totals(),self.timer.totals)

    def test_merged_day_reset_and_undo_preserve_original_date_buckets(self):
        original=self.timer.totals.copy();self.store.groups.set('2026-11-03',True)
        removed=self.timer.clear_category_day(self.a,'2026-11-04')
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),0)
        self.timer.restore_category_time(removed)
        self.store.groups.set('2026-11-03',False)
        self.assertEqual(self.timer.totals,original)

    def test_failed_reset_does_not_pause_or_forget_pending_study(self):
        self.timer.start(self.a,'2026-11-03');self.clock.advance(12)
        with patch.object(self.store,'clear_category_day',side_effect=OSError('Disk error')):
            with self.assertRaises(OSError):self.timer.clear_category_day(self.a,'2026-11-03')
        self.assertEqual(self.timer.active,self.a)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),3612)
        self.assertEqual(self.store.totals(),self.timer.totals)


if __name__=='__main__':unittest.main()
