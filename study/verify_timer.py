"""Isolated regression checks. Never touches the user's timer database."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from study_core import COLORS, MOSCOW, Store, Timer, format_time


class Clock:
    def __init__(self, wall=None):
        self.value = 100.0
        self.now = wall or datetime(2026, 11, 3, 12, tzinfo=MOSCOW)

    def advance(self, awake=0, asleep=0):
        self.value += awake
        self.now += timedelta(seconds=awake+asleep)

    def read(self):
        return self.value

    def wall(self):
        return self.now


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path)
        self.a = self.store.save_category("Алгоритмы", COLORS[0])
        self.b = self.store.save_category("Математика", COLORS[1])
        self.clock = Clock()
        self.timer = Timer(self.store, self.clock.read, self.clock.wall)

    def tearDown(self):
        self.timer.close()
        self.temp.cleanup()

    def test_switch_pause_and_no_double_count(self):
        self.timer.start(self.a)
        self.clock.advance(10)
        self.timer.start(self.b)
        self.clock.advance(20)
        self.timer.pause()
        self.clock.advance(900)
        self.timer.tick()
        self.assertAlmostEqual(self.timer.category_time(self.a), 10)
        self.assertAlmostEqual(self.timer.category_time(self.b), 20)
        self.assertAlmostEqual(self.timer.day_time("2026-11-03"), 30)
        self.timer.flush()
        self.timer.flush()
        self.assertAlmostEqual(sum(self.store.totals().values()), 30)

    def test_fractional_intervals_and_restart_paused(self):
        self.timer.start(self.a)
        for _ in range(12):
            self.clock.advance(.25)
            self.timer.tick()
        self.timer.flush()
        other_store = Store(self.path)
        try:
            other = Timer(other_store, self.clock.read, self.clock.wall)
            self.assertIsNone(other.active)
            self.assertAlmostEqual(other.category_time(self.a), 3)
        finally:
            other_store.close()

    def test_midnight_split(self):
        self.clock.now = datetime(2026, 11, 3, 23, 59, 58, tzinfo=MOSCOW)
        self.timer.start(self.a)
        self.clock.advance(5)
        self.timer.tick()
        self.assertAlmostEqual(self.timer.category_time(self.a, "2026-11-03"), 2)
        self.assertAlmostEqual(self.timer.category_time(self.a, "2026-11-04"), 3)

    def test_sleep_excluded_even_across_midnight(self):
        self.clock.now = datetime(2026, 11, 3, 23, 55, tzinfo=MOSCOW)
        self.timer.start(self.a)
        self.clock.advance(awake=20)
        self.timer.tick()
        self.clock.advance(asleep=8*3600)
        self.timer.tick()
        self.clock.advance(awake=3)
        self.timer.pause()
        self.assertAlmostEqual(self.timer.category_time(self.a), 23)
        self.assertAlmostEqual(self.timer.category_time(self.a, "2026-11-03"), 20)
        self.assertAlmostEqual(self.timer.category_time(self.a, "2026-11-04"), 3)

    def test_wall_clock_change_cannot_inflate_total(self):
        self.timer.start(self.a)
        self.clock.advance(10)
        self.clock.now -= timedelta(hours=1)
        self.timer.pause()
        self.assertAlmostEqual(self.timer.category_time(self.a), 10)

    def test_rename_preserves_history_and_rejects_duplicate(self):
        self.timer.start(self.a)
        self.clock.advance(15)
        self.timer.pause()
        self.store.save_category("Алгосы", COLORS[2], self.a)
        with self.assertRaises(ValueError):
            self.store.save_category("  АЛГОСЫ  ", COLORS[3])
        self.assertAlmostEqual(self.timer.category_time(self.a), 15)
        self.assertEqual(self.store.categories()[0]["title"], "Алгосы")

    def test_failed_checkpoint_retains_pending_time_for_retry(self):
        self.timer.start(self.a)
        self.clock.advance(11)
        self.timer.tick()
        original = self.store.add_time
        def fail(amounts):
            raise OSError("simulated write failure")
        self.store.add_time = fail
        with self.assertRaises(OSError):
            self.timer.flush()
        self.store.add_time = original
        self.assertTrue(self.timer.pending)
        self.timer.flush()
        self.assertEqual(sum(self.store.totals().values()), 11)
        self.assertFalse(self.timer.pending)

    def test_repeated_start_and_resume(self):
        self.timer.start(self.a)
        self.clock.advance(5)
        self.timer.start(self.a)
        self.clock.advance(7)
        self.timer.pause()
        self.assertAlmostEqual(self.timer.session_seconds, 12)
        self.clock.advance(90)
        self.timer.start(self.a)
        self.clock.advance(3)
        self.timer.pause()
        self.assertAlmostEqual(self.timer.session_seconds, 3)
        self.assertAlmostEqual(self.timer.category_time(self.a), 15)

    def test_long_duration_format(self):
        self.assertEqual(format_time(100*3600+65), "100:01:05")

    def test_selected_day_kept_across_midnight_and_sleep(self):
        selected = datetime(2026,11,3,tzinfo=MOSCOW).date()
        self.clock.now = datetime(2026,11,4,23,59,58,tzinfo=MOSCOW)
        self.timer.start(self.a,selected)
        self.clock.advance(awake=5,asleep=8*3600)
        self.timer.pause()
        self.assertAlmostEqual(self.timer.category_time(self.a,selected),5)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-04'),0)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-05'),0)

    def test_category_date_switch_preserves_each_bucket(self):
        self.timer.start(self.a,'2026-11-03')
        self.clock.advance(10)
        self.timer.start(self.a,'2026-11-04')
        self.clock.advance(20)
        self.timer.pause()
        self.assertEqual(self.timer.category_time(self.a,'2026-11-03'),10)
        self.assertEqual(self.timer.category_time(self.a,'2026-11-04'),20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
