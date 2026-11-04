"""Day-off exclusions are reversible and never erase recorded study or sleep."""
from datetime import date,datetime
from pathlib import Path
import tempfile
import unittest
from study_core import Store,Timer,COLORS,MOSCOW
from stats_core import build_report
from sleep_days import SleepStore


class DaysOffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3'
        self.store=Store(self.path)
        self.cid=self.store.save_category('ML',COLORS[1])
        self.totals={(self.cid,'2026-11-03'):7200,(self.cid,'2026-11-04'):28800}
        self.store.add_time(self.totals)

    def tearDown(self):self.store.close();self.tmp.cleanup()

    def test_persist_and_restore_without_deleting_time(self):
        self.store.set_day_off('2026-11-04',True)
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.days_off(),{'2026-11-04'})
        self.assertEqual(self.store.totals(),self.totals)
        self.store.set_day_off('2026-11-04',False)
        self.assertEqual(self.store.days_off(),set())
        self.assertEqual(self.store.totals(),self.totals)

    def test_all_periods_exclude_total_mean_best_and_categories(self):
        self.store.set_day_off('2026-11-04',True)
        for mode in ('day','week','month'):
            r=build_report(self.totals,self.store.categories(),mode,date(2026,11,4),self.store.days_off())
            self.assertEqual(r.daily_totals[date(2026,11,4)],0)
            self.assertEqual(r.excluded_total,28800)
            self.assertIn(date(2026,11,4),r.days_off)
            self.assertEqual(r.total,0 if mode=='day' else 7200)
            self.assertEqual(r.average_active_day,0 if mode=='day' else 7200)
            self.assertEqual(r.best_day,None if mode=='day' else date(2026,11,3))
        self.assertEqual(self.store.totals(),self.totals)

    def test_all_days_off_and_unmarked_weekends(self):
        self.store.set_day_off('2026-11-03',True);self.store.set_day_off('2026-11-04',True)
        r=build_report(self.totals,self.store.categories(),'week',date(2026,11,4),self.store.days_off())
        self.assertEqual(r.total,0);self.assertEqual(r.active_days,0);self.assertEqual(r.average_active_day,0)
        # Saturday/Sunday are not excluded unless the user marks them.
        r=build_report({(self.cid,'2026-11-08'):600},self.store.categories(),'week',date(2026,11,4),self.store.days_off())
        self.assertEqual(r.total,600)

    def test_awake_ratio_excludes_both_sides_but_sleep_is_retained(self):
        at=lambda d,h:datetime(2026,11,d,h,tzinfo=MOSCOW)
        sleep=SleepStore(self.store.db,wall=lambda:at(5,12))
        sleep.save(at(3,20),at(3,8));sleep.save(at(4,12),at(4,8))
        before=sleep.report(date(2026,11,3),date(2026,11,4))
        self.store.set_day_off('2026-11-04',True)
        r=sleep.activity_report(date(2026,11,3),date(2026,11,4),self.totals,self.store.days_off())
        self.assertEqual(r['study_seconds'],7200)
        self.assertEqual(r['awake_seconds'],44700)
        self.assertAlmostEqual(r['ratio'],7200/44700)
        self.assertEqual(sleep.report(date(2026,11,3),date(2026,11,4)),before)


if __name__=='__main__':unittest.main()
