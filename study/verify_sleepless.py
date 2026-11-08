"""Merging nights preserves raw records and money-like daily study totals."""
from datetime import date,datetime,timedelta
from pathlib import Path
import tempfile,unittest
from study_core import Store,Timer,MOSCOW,COLORS
from sleep_days import SleepStore,times_for_day
from sleep_stats_core import sleep_report

def at(day,hour=0):return datetime(2026,11,day,hour,tzinfo=MOSCOW)

class SleeplessTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'test.sqlite3'
        self.store=Store(self.path);self.now=at(9,12)
        self.sleep=SleepStore(self.store.db,wall=lambda:self.now)
        self.cid=self.store.save_category('ML',COLORS[0])
        self.store.add_time({(self.cid,'2026-11-07'):3600,(self.cid,'2026-11-08'):7200})
        self.first=self.sleep.save(at(7,23),at(7,8))
        self.second=self.sleep.save(at(8,23),at(8,9))
        self.raw=self.sleep.records();self.amounts=self.store.totals()
    def tearDown(self):self.store.close();self.folder.cleanup()
    def mark(self):self.sleep.set_sleepless(date(2026,11,7),True)
    def test_merge_and_undo_preserve_both_original_records_and_totals(self):
        self.mark();rows=self.sleep.logical_records()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['wake_at'],at(7,8).isoformat())
        self.assertEqual(rows[0]['bed_at'],at(8,23).isoformat())
        timer=Timer(self.store,clock=lambda:0)
        self.assertEqual(timer.day_time(date(2026,11,7)),10800)
        self.assertEqual(timer.day_time(date(2026,11,8)),10800)
        self.assertEqual(timer.category_time(self.cid,date(2026,11,8)),10800)
        self.assertEqual(self.sleep.records(),self.raw);self.assertEqual(self.store.totals(),self.amounts)
        self.sleep.set_sleepless(date(2026,11,7),False)
        self.assertEqual(self.sleep.logical_records(),self.raw)
        self.assertEqual(timer.day_time(date(2026,11,7)),3600)
    def test_no_fake_sleep_and_awake_percentage_uses_combined_day(self):
        self.mark()
        self.assertEqual(self.sleep.episodes(),[])
        report=self.sleep.activity_report(date(2026,11,8),date(2026,11,8),self.amounts)
        self.assertEqual(report['study_seconds'],10800)
        self.assertEqual(report['awake_seconds'],39*3600+25*60)
        stats=sleep_report(self.sleep,date(2026,11,7),date(2026,11,8),self.amounts)
        self.assertEqual(stats['sleepless_nights'],1);self.assertIsNone(stats['mean_seconds'])
    def test_chain_two_nights_and_restore(self):
        self.mark();self.sleep.set_sleepless(date(2026,11,8),True)
        self.assertEqual(self.store.groups.start(date(2026,11,9)),date(2026,11,7))
        self.assertEqual(self.store.groups.end(date(2026,11,7)),date(2026,11,9))
        self.assertIsNone(self.sleep.logical_records()[0]['bed_at'])
        self.assertEqual(sleep_report(self.sleep,date(2026,11,7),date(2026,11,9),self.amounts)['sleepless_nights'],2)
        self.sleep.set_sleepless(date(2026,11,8),False)
        self.assertEqual(self.sleep.logical_records()[0]['bed_at'],at(8,23).isoformat())
    def test_edit_and_actual_marks_on_group_do_not_destroy_originals(self):
        self.mark();row=self.sleep.logical_records()[0]
        bed,wake=times_for_day(date(2026,11,7),'22:00','08:00',row,date(2026,11,8))
        self.assertEqual(bed,at(8,22));self.sleep.save_selected(bed,wake,row,date(2026,11,8))
        self.assertEqual(self.sleep.logical_records()[0]['bed_at'],at(8,22).isoformat())
        self.assertEqual(self.sleep.records(),self.raw)
        self.sleep.set_sleepless(date(2026,11,7),False)
        self.assertEqual(self.sleep.logical_records(),self.raw)
    def test_continuing_timer_and_reopening_database(self):
        clock=[0.];timer=Timer(self.store,clock=lambda:clock[0],wall=lambda:self.now)
        timer.start(self.cid,date(2026,11,8));clock[0]+=60;timer.tick();self.mark()
        clock[0]+=30;timer.tick();timer.flush()
        self.assertEqual(timer.category_time(self.cid,date(2026,11,7)),10890)
        self.assertEqual(timer.active,self.cid);self.assertEqual(timer.active_day,date(2026,11,8))
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.groups.nights(),{'2026-11-07'})
        self.assertEqual(sum(self.store.groups.totals(self.store.totals()).values()),10890)
    def test_day_off_applies_to_whole_logical_day(self):
        self.mark();self.store.set_day_off(date(2026,11,8),True)
        self.assertEqual(self.store.days_off(),{'2026-11-07'})
        report=self.sleep.activity_report(date(2026,11,7),date(2026,11,8),self.amounts,self.store.days_off())
        self.assertEqual(report['study_seconds'],0)
    def test_week_boundary_does_not_count_merged_time_twice(self):
        self.sleep.set_sleepless(date(2026,11,8),True)
        self.store.add_time({(self.cid,'2026-11-09'):1800})
        amounts=self.store.totals()
        self.assertEqual(self.store.groups.totals(amounts)[(self.cid,'2026-11-08')],9000)
        self.assertEqual(self.sleep.activity_report(date(2026,11,9),date(2026,11,15),amounts)['study_seconds'],0)
    def test_missing_entries_are_not_guessed_as_sleepless(self):
        self.assertEqual(sleep_report(self.sleep,date(2026,11,1),date(2026,11,8),self.amounts)['sleepless_nights'],0)
        with self.assertRaises(ValueError):self.sleep.set_sleepless(date(2026,11,10),True)

if __name__=='__main__':unittest.main()
