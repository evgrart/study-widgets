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
