import unittest,tempfile,json,math,sqlite3,threading
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch,Mock
from study_core import Store,Timer,COLORS,format_time,MOSCOW
from verify_timer import Clock
from sleep_days import SleepStore
from sleep_stats_core import sleep_report
from stats_core import build_report

class Hardening(unittest.TestCase):
    def setup_store(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        store=Store(Path(folder.name)/'study.db');self.addCleanup(store.close)
        cid=store.save_category('Lesson',COLORS[0]);return store,cid

    def test_finite_storage_durations(self):
        store,cid=self.setup_store()
        for value in [math.inf,math.nan,-1,True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):store.add_time({(cid,'2026-11-02'):value})
        self.assertEqual(store.totals(),{})

    def test_canonical_storage_dates(self):
        store,cid=self.setup_store()
        for value in ['invalid','2026-02-30','20261102']:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):store.add_time({(cid,'2026-11-01'):10,(cid,value):20})
                self.assertEqual(store.totals(),{})

    def test_backward_clock(self):
        store,cid=self.setup_store();clock=Clock();timer=Timer(store,clock.read,clock.wall)
        timer.start(cid,'2026-11-02');clock.value=90;timer.tick();clock.value=100;timer.tick()
        self.assertEqual(timer.category_time(cid),0)
        clock.value=105;timer.pause();self.assertEqual(timer.category_time(cid),5)

    def test_invalid_clock_readings(self):
        store,cid=self.setup_store();clock=Clock();timer=Timer(store,clock.read,clock.wall)
        timer.start(cid,'2026-11-02');clock.value=math.inf;timer.tick()
        clock.value=105;timer.pause();self.assertEqual(timer.category_time(cid),5)
        clock.value=math.nan;other=Timer(store,clock.read,clock.wall)
        other.start(cid,'2026-11-02');clock.value=110;other.tick();clock.value=112;other.pause()
        self.assertEqual(other.session_seconds,2)

    def test_finite_report_totals(self):
        categories=[{'id':1,'title':'A','color':COLORS[0]}]
        for value in [math.inf,math.nan]:
            report=build_report({(1,'2026-11-02'):value},categories,'day',date(2026,11,2))
            self.assertEqual(report.total,0)
            self.assertEqual(report.active_days,0)

    def test_format_invalid_durations(self):
        for value in [math.nan,math.inf,None,'bad']:
            self.assertEqual(format_time(value),'—')
        self.assertEqual(format_time(-5),'00:00:00')

    def test_minimum_group_date(self):
        store,cid=self.setup_store()
        self.assertEqual(store.groups.start(date.min),date.min)
        self.assertEqual(store.groups.end(date.min),date.min)
