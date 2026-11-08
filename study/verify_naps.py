"""Daytime sleep stays within the same logical day, even after a sleepless night."""
from datetime import date,datetime,timedelta
from pathlib import Path
import tempfile,unittest
from study_core import Store,MOSCOW
from sleep_days import SleepStore
from sleep_stats_core import sleep_report

def at(day,hour=0,minute=0):return datetime(2026,11,day,hour,minute,tzinfo=MOSCOW)

class NapTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'test.sqlite3'
        self.store=Store(self.path);self.now=at(9,12)
        self.data=SleepStore(self.store.db,wall=lambda:self.now)
    def tearDown(self):self.store.close();self.folder.cleanup()
    def test_nap_subtracts_from_awake_without_splitting_day(self):
        self.data.save(wake=at(8,8));raw=self.data.records()
        self.data.save_nap(at(8,13),at(8,14,30))
        self.now=at(8,18)
        report=self.data.activity_report(date(2026,11,8),date(2026,11,8),{(1,'2026-11-08'):3600})
        self.assertEqual(report['awake_seconds'],8.5*3600)
        self.assertAlmostEqual(report['ratio'],1/8.5)
        self.assertEqual(self.data.records(),raw)
        self.assertIsNotNone(self.data.current())
        stats=sleep_report(self.data,date(2026,11,8),date(2026,11,8),{})
        self.assertEqual(stats['nap_seconds'],5400);self.assertEqual(stats['mean_seconds'],5400)
        self.assertIsNone(stats['bed']['mean']);self.assertIsNone(stats['wake']['mean'])
    def test_nap_after_sleepless_night_keeps_day_merged_and_night_counted(self):
        self.data.save(wake=at(7,8));self.data.set_sleepless(date(2026,11,7),True)
        row=self.data.logical_records()[0]
        self.data.save_selected(at(8,23),at(7,8),row,date(2026,11,7))
        self.data.save_nap(at(7,14),at(7,15))
        self.data.save_nap(at(8,13),at(8,14,30))
        self.assertEqual(self.store.groups.start(date(2026,11,8)),date(2026,11,7))
        stats=sleep_report(self.data,date(2026,11,7),date(2026,11,8),{})
        self.assertEqual(stats['sleepless_nights'],1);self.assertEqual(stats['nap_seconds'],9000)
        self.assertEqual(stats['totals'][date(2026,11,7)],9000)
        self.assertIsNone(stats['totals'][date(2026,11,8)])
        self.assertEqual(stats['activity']['awake_seconds'],39*3600+25*60-9000)
    def test_multiple_naps_edit_delete_and_persistence(self):
        first=self.data.save_nap(at(8,12),at(8,13))
        second=self.data.save_nap(at(8,16),at(8,16,30))
        self.data.save_nap(at(8,12),at(8,13,15),first)
        self.data.delete_nap(second)
        self.store.close();self.store=Store(self.path);self.data=SleepStore(self.store.db,wall=lambda:self.now)
        self.assertEqual(len(self.data.naps()),1);self.assertEqual(self.data.naps()[0]['seconds'],4500)
    def test_invalid_future_and_overlapping_naps_rejected(self):
        self.data.save_nap(at(8,13),at(8,14))
        for begin,end in [(at(8,14),at(8,13)),(at(8,13),at(8,13)),(at(8,23),at(9,1)),
                          (at(10,13),at(10,14)),(at(8,13,30),at(8,14,30))]:
            with self.assertRaises(ValueError):self.data.save_nap(begin,end)
        self.assertEqual(len(self.data.naps()),1)
    def test_night_overlap_cannot_be_counted_twice(self):
        self.data.save_nap(at(8,14),at(8,15))
        self.data.save(at(8,13),at(8,8));self.data.save(wake=at(8,16))
        with self.assertRaises(ValueError):self.data.save_nap(at(8,13,30),at(8,14))
        stats=sleep_report(self.data,date(2026,11,8),date(2026,11,8),{})
        self.assertEqual(stats['nap_seconds'],0);self.assertEqual(stats['mean_seconds'],2*3600+35*60)
    def test_day_off_and_partial_awake_window(self):
        self.data.save(wake=at(8,14));self.data.save_nap(at(8,13),at(8,15))
        self.now=at(8,18)
        report=self.data.activity_report(date(2026,11,8),date(2026,11,8),{})
        self.assertEqual(report['awake_seconds'],3*3600)
        report=self.data.activity_report(date(2026,11,8),date(2026,11,8),{(1,'2026-11-08'):100},{'2026-11-08'})
        self.assertEqual(report['study_seconds'],0);self.assertEqual(report['awake_seconds'],0)

if __name__=='__main__':unittest.main()
