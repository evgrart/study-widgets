"""Check cross-midnight sleep, incomplete marks, corrections, and awake ratios."""
from datetime import datetime, timedelta, date
from pathlib import Path
import tempfile
import unittest
from study_core import Store, MOSCOW
from sleep_core import SleepStore, clock_average, times_for_day


def at(day,hour=0,minute=0):
    return datetime(2026,11,day,hour,minute,tzinfo=MOSCOW)


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'study.sqlite3'
        self.store=Store(self.path)
        self.now=at(10,12)
        self.sleep=SleepStore(self.store.db,wall=lambda:self.now)

    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def test_midnight_and_restart(self):
        self.now=at(3,23,30);self.sleep.mark_bed()
        self.store.close();self.store=Store(self.path)
        self.sleep=SleepStore(self.store.db,wall=lambda:self.now)
        self.now=at(4,7,30);self.sleep.mark_wake()
        report=self.sleep.report(date(2026,11,4),date(2026,11,4))
        self.assertEqual(report['complete'],1)
        self.assertEqual(report['average_seconds'],8*3600)
        self.assertIsNone(self.sleep.current())

    def test_first_wake_not_guessed_and_double_click_safe(self):
        self.sleep.mark_wake();self.sleep.mark_wake()
        self.assertEqual(len(self.sleep.records()),1)
        report=self.sleep.report(self.now.date(),self.now.date())
        self.assertIsNone(report['average_seconds'])
        self.assertIsNone(report['average_bed'])
        self.assertEqual(report['average_wake'],'12:00')

    def test_single_open_and_validation_do_not_change_data(self):
        self.sleep.mark_bed()
        with self.assertRaises(ValueError):self.sleep.mark_bed()
        with self.assertRaises(ValueError):self.sleep.save(at(10,12),at(10,11))
        with self.assertRaises(ValueError):self.sleep.save(at(11))
        self.assertEqual(len(self.sleep.records()),1)

    def test_edit_and_overlap(self):
        first=self.sleep.save(at(3,23),at(4,7))
        second=self.sleep.save(at(4,23),at(5,7))
        with self.assertRaises(ValueError):self.sleep.save(at(4,6),at(4,9),second)
        self.sleep.save(at(3,23),at(4,8),first)
        report=self.sleep.report(date(2026,11,4),date(2026,11,4))
        self.assertEqual(report['average_seconds'],9*3600)
        self.sleep.delete(first)
        self.assertEqual(len(self.sleep.records()),1)

    def test_average_wraps_midnight(self):
        self.assertEqual(clock_average([at(3,23),at(4,1)]),'00:00')
        self.assertIsNone(clock_average([]))
        self.assertIsNone(clock_average([at(3,0),at(3,12)]))

    def test_time_only_infers_selected_night_and_daytime_nap(self):
        day=date(2026,11,4)
        bed,wake=times_for_day(day,'23:30','08:00')
        self.assertEqual(bed,at(3,23,30));self.assertEqual(wake,at(4,8))
        bed,wake=times_for_day(day,'01:30','09:00')
        self.assertEqual(bed,at(4,1,30));self.assertEqual(wake,at(4,9))
        bed,wake=times_for_day(day,'13:00','14:00')
        self.assertEqual(bed,at(4,13));self.assertEqual(wake,at(4,14))
        bed,wake=times_for_day(date(2026,11,1),'23:00','07:00')
        self.assertEqual(bed.date(),date(2026,10,31))

    def test_time_only_incomplete_and_unchanged_records(self):
        day=date(2026,11,4)
        self.assertEqual(times_for_day(day,'','08:00'),(None,at(4,8)))
        self.assertEqual(times_for_day(day,'23:00',''),(at(4,23),None))
        original={'bed_at':at(2,23).replace(second=12).isoformat(),'wake_at':at(4,8).replace(second=31).isoformat()}
        self.assertEqual(times_for_day(day,'23:00','08:00',original),
                         (at(2,23).replace(second=12),at(4,8).replace(second=31)))
        for value in ['25:00','08:60','2026-11-04 23:30','8','08:0']:
            with self.assertRaises(ValueError):times_for_day(day,value,'09:00')

    def test_awake_after_midnight_uses_wake_date(self):
        self.sleep.save(at(3,23),at(4,8))
        self.sleep.save(at(5,1),at(5,9))
        report=self.sleep.activity_report(date(2026,11,4),date(2026,11,4),{(1,'2026-11-04'):8.5*3600,(2,'2026-11-03'):999})
        self.assertEqual(report['awake_seconds'],17*3600)
        self.assertEqual(report['study_seconds'],8.5*3600)
        self.assertEqual(report['ratio'],.5)

    def test_naps_and_repeated_wakes_not_double_counted(self):
        self.sleep.save(wake=at(4,8))
        self.sleep.save(at(4,13),at(4,14))
        self.sleep.save(at(4,23),at(5,8))
        report=self.sleep.activity_report(date(2026,11,4),date(2026,11,4),{(1,'2026-11-04'):7*3600})
        self.assertEqual(report['awake_seconds'],14*3600)
        self.assertEqual(report['ratio'],.5)
        self.sleep.save(wake=at(4,10))
        report=self.sleep.activity_report(date(2026,11,4),date(2026,11,4),{(1,'2026-11-04'):7*3600})
        self.assertEqual(report['awake_seconds'],14*3600)

    def test_current_awake_time_and_unknown(self):
        self.assertIsNone(self.sleep.activity_report(self.now.date(),self.now.date(),{})['ratio'])
        self.sleep.save(wake=at(10,8))
        report=self.sleep.activity_report(self.now.date(),self.now.date(),{(1,'2026-11-10'):3600})
        self.assertEqual(report['ratio'],.25)
        self.now+=timedelta(hours=1)
        self.assertEqual(self.sleep.activity_report(self.now.date(),self.now.date(),{})['awake_seconds'],5*3600)


if __name__=='__main__':unittest.main()
