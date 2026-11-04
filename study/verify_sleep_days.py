"""Wake-first dates, sleep between days, deletion, and lossless migration."""
from datetime import date,datetime,timedelta
from pathlib import Path
import tempfile
import unittest
from study_core import Store,MOSCOW
from sleep_days import SleepStore,times_for_day,clock_average


def at(day,hour=0,minute=0):return datetime(2026,11,day,hour,minute,tzinfo=MOSCOW)


class DaysTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3'
        self.store=Store(self.path);self.now=at(10,12)
        self.data=SleepStore(self.store.db,wall=lambda:self.now)

    def tearDown(self):self.store.close();self.tmp.cleanup()

    def test_wake_then_bed_after_midnight_and_next_sleep(self):
        self.now=at(4,8);rid=self.data.mark_wake()
        self.now=at(5,1);self.assertEqual(self.data.mark_bed(),rid)
        row=self.data.records()[0];self.assertEqual(row['day'],'2026-11-04')
        self.assertEqual(row['bed_at'],at(5,1).isoformat());self.assertIsNone(self.data.current())
        self.store.close();self.store=Store(self.path);self.data=SleepStore(self.store.db,wall=lambda:self.now)
        self.now=at(5,9);self.data.mark_wake()
        report=self.data.report(date(2026,11,5),date(2026,11,5))
        self.assertEqual(report['average_seconds'],7*3600+35*60)
        self.assertEqual(self.data.activity_report(date(2026,11,4),date(2026,11,4),{})['awake_seconds'],17*3600+25*60)

    def test_clicks_idempotent(self):
        self.data.mark_wake();self.data.mark_wake();self.assertEqual(len(self.data.records()),1)
        self.assertIsNone(self.data.report(self.now.date(),self.now.date())['average_seconds'])
        self.now+=timedelta(hours=2)
        self.data.mark_bed();self.data.mark_bed();self.assertEqual(len(self.data.records()),1)

    def test_future_bedtime_after_midnight_is_saved_without_ending_day_early(self):
        self.now=at(7,1)
        bed,wake=times_for_day(date(2026,11,6),'2:30','11:30')
        rid=self.data.save(bed,wake,day=date(2026,11,6))
        self.assertEqual(self.data.records()[0]['bed_at'],at(7,2,30).isoformat())
        self.assertEqual(self.data.current()['id'],rid)
        self.assertEqual(self.data.report(date(2026,11,6),date(2026,11,6))['average_bed'],None)
        awake=self.data.activity_report(date(2026,11,6),date(2026,11,6),{})['awake_seconds']
        self.assertEqual(awake,13.5*3600)
        self.now=at(7,3)
        self.assertIsNone(self.data.current())
        self.now=at(7,10);self.data.mark_wake()
        self.assertEqual(self.data.episodes()[0]['bed'],bed)

    def test_future_bedtime_can_be_replaced_by_actual_bed_button(self):
        self.now=at(6,20)
        rid=self.data.save(at(7,2,30),at(6,11,30),day=date(2026,11,6))
        self.now=at(6,23)
        self.assertEqual(self.data.mark_bed(),rid)
        self.assertEqual(self.data.records()[0]['bed_at'],self.now.isoformat())
        self.assertIsNone(self.data.current())

    def test_bed_click_after_midnight_updates_selected_wake_day(self):
        rid=self.data.save(at(5,3,25),at(4,10,50))
        self.now=at(5,3,56)
        self.assertEqual(self.data.mark_bed(date(2026,11,4)),rid)
        rows=self.data.records()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['day'],'2026-11-04')
        self.assertEqual(rows[0]['wake_at'],at(4,10,50).isoformat())
        self.assertEqual(rows[0]['bed_at'],self.now.isoformat())
        self.now+=timedelta(seconds=1)
        self.assertEqual(self.data.mark_bed(date(2026,11,4)),rid)
        self.assertEqual(self.data.records(),rows)

    def test_selected_day_without_wake_keeps_its_day(self):
        self.now=at(5,3,56)
        self.data.mark_bed(date(2026,11,4))
        row=self.data.records()[0]
        self.assertEqual(row['day'],'2026-11-04')
        self.assertEqual(row['bed_at'],self.now.isoformat())
        self.assertIsNone(row['wake_at'])
        with self.assertRaises(ValueError):self.data.mark_bed(date(2026,11,6))

    def test_time_only_rule(self):
        d=date(2026,11,4)
        self.assertEqual(times_for_day(d,'23:30','08:00'),(at(4,23,30),at(4,8)))
        self.assertEqual(times_for_day(d,'01:30','09:00'),(at(5,1,30),at(4,9)))
        self.assertEqual(times_for_day(d,'13:00','10:00'),(at(4,13),at(4,10)))
        self.assertEqual(times_for_day(d,'10:00','10:00'),(at(4,10),at(4,10)))
        bed,wake=times_for_day(date(2026,11,30),'01:00','09:00')
        self.assertEqual(bed.date(),date(2026,12,1))
        self.assertEqual(wake.date(),date(2026,11,30))

    def test_empty_bad_and_unchanged_times(self):
        d=date(2026,11,4)
        self.assertEqual(times_for_day(d,'','08:00'),(None,at(4,8)))
        self.assertEqual(times_for_day(d,'23:00',''),(at(4,23),None))
        record={'wake_at':at(4,8).replace(second=12).isoformat(),'bed_at':at(5,1).replace(second=34).isoformat()}
        self.assertEqual(times_for_day(d,'01:00','08:00',record),(at(5,1).replace(second=34),at(4,8).replace(second=12)))
        for t in ['25:00','08:60','4.11.2026 23:00','08:0']:
            with self.assertRaises(ValueError):times_for_day(d,t,'09:00')

    def test_edit_delete_and_validation(self):
        rid=self.data.save(at(4,23),at(4,8))
        self.data.save(at(5,1),at(4,8),rid)
        self.assertEqual(self.data.records()[0]['bed_at'],at(5,1).isoformat())
        with self.assertRaises(ValueError):self.data.save(at(4,7),at(4,8),rid)
        with self.assertRaises(ValueError):self.data.save(wake=at(11))
        with self.assertRaises(ValueError):self.data.save(at(4,16),at(4,12))
        self.data.delete(rid);self.assertEqual(self.data.records(),[])

    def test_awake_ratio_and_naps(self):
        self.data.save(at(4,13),at(4,8))
        self.data.save(at(4,23),at(4,14))
        r=self.data.activity_report(date(2026,11,4),date(2026,11,4),{(1,'2026-11-04'):7*3600})
        self.assertEqual(r['awake_seconds'],14*3600+50*60);self.assertAlmostEqual(r['ratio'],7*3600/(14*3600+50*60))
        self.assertEqual(self.data.report(date(2026,11,4),date(2026,11,4))['average_seconds'],35*60)

    def test_latency_is_configurable_and_preserves_original_marks(self):
        self.assertEqual(self.data.latency_minutes,25)
        self.data.save(at(4,23,50),at(4,8));self.data.save(wake=at(5,6,50))
        original=self.data.records()
        start,end=date(2026,11,5),date(2026,11,5)
        self.assertEqual(self.data.report(start,end)['average_seconds'],6*3600+35*60)
        self.assertEqual(self.data.sleep_intervals(),[(at(5,0,15),at(5,6,50))])
        self.data.set_latency_minutes(0)
        self.assertEqual(self.data.report(start,end)['average_seconds'],7*3600)
        self.data.set_latency_minutes(40)
        self.assertEqual(self.data.report(start,end)['average_seconds'],6*3600+20*60)
        self.assertEqual(self.data.records(),original)
        self.store.close();self.store=Store(self.path);self.data=SleepStore(self.store.db)
        self.assertEqual(self.data.latency_minutes,40)
        self.assertEqual(self.data.records(),original)

    def test_latency_cannot_count_future_awake_time_or_negative_sleep(self):
        self.data.save(at(4,12),at(4,8))
        self.now=at(4,12,10)
        report=self.data.activity_report(date(2026,11,4),date(2026,11,4),{})
        self.assertEqual(report['awake_seconds'],4*3600+10*60)
        self.now=at(4,12,20);self.data.mark_wake()
        report=self.data.report(date(2026,11,4),date(2026,11,4))
        self.assertEqual(report['average_seconds'],0)
        report=self.data.activity_report(date(2026,11,4),date(2026,11,4),{})
        self.assertEqual(report['awake_seconds'],4*3600+20*60)
        for value in (-1,181,1.5,True,'25'):
            with self.assertRaises(ValueError):self.data.set_latency_minutes(value)

    def test_current_ratio_and_circular_means(self):
        self.assertIsNone(self.data.activity_report(self.now.date(),self.now.date(),{})['ratio'])
        self.data.save(wake=at(10,8))
        self.assertEqual(self.data.activity_report(self.now.date(),self.now.date(),{(1,'2026-11-10'):3600})['ratio'],.25)
        self.assertEqual(clock_average([at(3,23),at(4,1)]),'00:00')

    def test_legacy_migration_retains_exact_marks_and_archive(self):
        self.store.db.execute('DROP TABLE sleep_days')
        self.store.db.execute('CREATE TABLE sleep_records(id INTEGER PRIMARY KEY,bed_at TEXT,wake_at TEXT)')
        original=[(at(3,23).isoformat(),at(4,8).isoformat()),(at(5,1).isoformat(),at(5,9).isoformat())]
        self.store.db.executemany('INSERT INTO sleep_records(bed_at,wake_at) VALUES(?,?)',original);self.store.db.commit()
        self.data=SleepStore(self.store.db,wall=lambda:self.now)
        new=self.data.records()
        self.assertEqual(sorted(x for pair in original for x in pair),sorted(r[k] for r in new for k in ('wake_at','bed_at') if r[k]))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sleep_records').fetchone()[0],2)
        self.assertTrue(list((self.path.parent/'backups').glob('before-wake-bed-*.sqlite3')))
        SleepStore(self.store.db)
        self.assertEqual(len(self.data.records()),3)


if __name__=='__main__':unittest.main()
