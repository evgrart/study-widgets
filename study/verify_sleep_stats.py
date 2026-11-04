"""Scientific bookkeeping: missing data, midnight, optional diary and reversible flags."""
from datetime import date,datetime,timedelta
from pathlib import Path
import tempfile,unittest
from study_core import Store,MOSCOW
from sleep_days import SleepStore
from sleep_stats_core import sleep_report,timing

def at(d,h=0,m=0):return datetime(2026,11,d,h,m,tzinfo=MOSCOW)

class SleepStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'sleep.db'
        self.store=Store(self.path);self.data=SleepStore(self.store.db,wall=lambda:at(10,12))
        self.data.save(at(3,23),at(3,8))
        self.four=self.data.save(at(4,23,30),at(4,8))
        self.five=self.data.save(wake=at(5,7,30))
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def report(self,start=4,end=6):return sleep_report(self.data,date(2026,11,start),date(2026,11,end),{})
    def test_missing_days_do_not_become_zero(self):
        r=self.report()
        self.assertEqual(r['completed_days'],2);self.assertEqual(r['missing_days'],1)
        self.assertIsNone(r['totals'][date(2026,11,6)])
        self.assertEqual(r['mean_seconds'],8*3600+5*60)
        self.assertEqual(r['median_seconds'],r['mean_seconds'])
        self.assertEqual(r['bed']['mean'],'23:15')
        self.assertEqual(r['wake']['mean'],'07:45');self.assertAlmostEqual(r['wake']['sd_minutes'],15)
        self.assertEqual(r['latency_n'],0);self.assertEqual(r['awake_n'],0)
    def test_diary_changes_estimate_not_raw_marks(self):
        original=self.data.records()
        self.data.save_diary(self.four,10,20,4,'Late coffee')
        episode=next(e for e in self.data.episodes() if e['wake_id']==self.four)
        self.assertEqual(episode['seconds'],8*3600+30*60)
        self.assertTrue(episode['latency_reported']);self.assertEqual(episode['awake_minutes'],20)
        self.assertEqual(self.data.records(),original)
        self.assertEqual(self.data.report(date(2026,11,4),date(2026,11,4))['average_seconds'],episode['seconds'])
        self.assertEqual(self.report()['quality'],4);self.assertEqual(self.report()['quality_n'],1)
        self.store.close();self.store=Store(self.path);self.data=SleepStore(self.store.db,wall=lambda:at(10,12))
        self.assertEqual(self.data.diary()[self.four]['notes'],'Late coffee')
        self.assertEqual(self.data.records(),original)
    def test_blank_is_unknown_not_measured_zero(self):
        self.data.save_diary(self.four,0,0,5)
        self.data.save_diary(self.four,None,None,None)
        r=self.report();self.assertEqual(r['latency_n'],0);self.assertEqual(r['awake_n'],0)
        self.assertIsNone(r['quality']);self.assertEqual(r['mean_seconds'],8*3600+5*60)
    def test_midnight_and_single_observation(self):
        result=timing([at(3,23,50),at(4,0,10)])
        self.assertEqual(result['mean'],'00:00');self.assertAlmostEqual(result['sd_minutes'],10)
        self.assertIsNone(timing([at(4,8)])['sd_minutes'])
        self.assertIsNone(timing([at(4,0),at(4,12)])['mean'])
    def test_future_days_not_counted_as_missing(self):
        r=self.report(4,20)
        self.assertEqual(r['expected_days'],7);self.assertEqual(r['missing_days'],5)
    def test_multiple_periods_are_added_per_day(self):
        self.data.save(at(5,13),at(5,12))
        self.data.save(wake=at(5,14))
        r=self.report(5,5)
        self.assertEqual(r['mean_seconds'],8*3600+10*60)
        self.assertEqual(r['wake']['mean'],'07:30')
    def test_off_day_excludes_study_but_keeps_sleep(self):
        totals={(1,'2026-11-04'):3600}
        normal=sleep_report(self.data,date(2026,11,4),date(2026,11,5),totals)
        excluded=sleep_report(self.data,date(2026,11,4),date(2026,11,5),totals,{'2026-11-04'})
        self.assertEqual(normal['mean_seconds'],excluded['mean_seconds'])
        self.assertEqual(excluded['activity']['study_seconds'],0)
    def test_invalid_or_discontinuous_nights_are_not_trusted(self):
        self.data.save(bed=at(7,23));self.data.save(wake=at(10,8))
        r=self.report(10,10)
        self.assertEqual(r['review_n'],1);self.assertIsNone(r['mean_seconds'])
        self.assertEqual(r['completed_days'],0)
        for args in [(181,0,3),(10,-1,3),(10,1,0),(10,1,6),(10,1000,3)]:
            with self.assertRaises(ValueError):self.data.save_diary(self.four,*args)
    def test_diary_follows_wake_identity_and_cascades_on_delete(self):
        self.data.save_diary(self.four,15,0,3)
        self.data.delete(self.four)
        self.assertNotIn(self.four,self.data.diary())
        with self.assertRaises(ValueError):self.data.save_diary(self.four,10,0,4)

if __name__=='__main__':unittest.main()
