"""Local study timers: one running subject, durable daily totals, Moscow dates."""
from __future__ import annotations

import ctypes
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import time
from day_groups import DayGroups

MOSCOW = timezone(timedelta(hours=3))
COLORS = ("#F4CF70", "#97CFA8", "#91BFEF", "#C6AAEB", "#EEA6AD", "#8CD3CF")


def now_moscow():
    return datetime.now(MOSCOW)


def awake_seconds():
    """Windows unbiased interrupt time excludes sleep and hibernation."""
    value = ctypes.c_ulonglong()
    if not ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
        raise ctypes.WinError()
    return value.value / 10_000_000


def format_time(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                normalized TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_totals (
                category_id INTEGER NOT NULL REFERENCES categories(id),
                day TEXT NOT NULL,
                seconds REAL NOT NULL CHECK(seconds>=0),
                PRIMARY KEY(category_id, day)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS days_off (
                day TEXT PRIMARY KEY
            );
        """)
        self.groups=DayGroups(self.db)

    def categories(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM categories ORDER BY id")]

    def days_off(self):
        return {str(self.groups.start(row[0])) for row in self.db.execute('SELECT day FROM days_off')}

    def set_day_off(self, day, enabled):
        day = str(self.groups.start(day))
        with self.db:
            if enabled:self.db.execute('INSERT OR IGNORE INTO days_off(day) VALUES(?)',(day,))
            else:
                for row in self.db.execute('SELECT day FROM days_off').fetchall():
                    if str(self.groups.start(row[0]))==day:self.db.execute('DELETE FROM days_off WHERE day=?',(row[0],))

    def save_category(self, title, color, category_id=None):
        title = " ".join(title.split())
        if not title:
            raise ValueError("Напиши название категории.")
        if len(title) > 80:
            raise ValueError("Название должно быть не длиннее 80 символов.")
        if color not in COLORS:
            raise ValueError("Выбери цвет категории.")
        try:
            with self.db:
                if category_id is None:
                    cur = self.db.execute(
                        "INSERT INTO categories(title,normalized,color) VALUES(?,?,?)",
                        (title, title.casefold(), color),
                    )
                    return cur.lastrowid
                cur = self.db.execute(
                    "UPDATE categories SET title=?,normalized=?,color=? WHERE id=?",
                    (title, title.casefold(), color, category_id),
                )
                if cur.rowcount != 1:
                    raise ValueError("Категория не найдена.")
                return category_id
        except sqlite3.IntegrityError as exc:
            raise ValueError("Такая категория уже есть.") from exc

    def add_time(self, amounts):
        with self.db:
            for (category_id, day), seconds in amounts.items():
                if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
                    raise ValueError('invalid_study_date')
                if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:
                    raise ValueError('invalid_study_duration')
                if seconds > 0:
                    self.db.execute("""
                        INSERT INTO daily_totals(category_id,day,seconds) VALUES(?,?,?)
                        ON CONFLICT(category_id,day) DO UPDATE SET seconds=seconds+excluded.seconds
                    """, (category_id, day, seconds))

    def totals(self):
        return {(r["category_id"], r["day"]): r["seconds"]
                for r in self.db.execute("SELECT * FROM daily_totals")}

    def clear_category_day(self, category_id, day):
        start,end=str(self.groups.start(day)),str(self.groups.end(day))
        with self.db:
            removed={(row['category_id'],row['day']):row['seconds'] for row in self.db.execute(
                'SELECT * FROM daily_totals WHERE category_id=? AND day BETWEEN ? AND ?',
                (category_id,start,end))}
            self.db.execute('DELETE FROM daily_totals WHERE category_id=? AND day BETWEEN ? AND ?',
                            (category_id,start,end))
        return removed

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))

    def close(self):
        self.db.close()


class Timer:
    def __init__(self, store, clock=awake_seconds, wall=now_moscow):
        self.store, self.clock, self.wall = store, clock, wall
        self.active = None
        self.active_day = None
        self.selected = None
        self.session_seconds = 0.0
        self.totals = store.totals()
        self.pending = {}
        reading=clock()
        self._last = reading if math.isfinite(reading) else None
        self._saved_at = time.monotonic()

    def tick(self):
        current = self.clock()
        if not math.isfinite(current):return
        if self._last is None:
            self._last=current
            return
        elapsed = max(0.0, current - self._last)
        self._last = max(self._last,current)
        if self.active is None or elapsed <= 0:
            return
        if self.active_day is not None:
            key = (self.active,self.active_day.isoformat())
            self.totals[key] = self.totals.get(key,0.0)+elapsed
            self.pending[key] = self.pending.get(key,0.0)+elapsed
            self.session_seconds += elapsed
            return
        end = self.wall().astimezone(MOSCOW)
        start = end - timedelta(seconds=elapsed)
        # Attribute awake time only, including when the laptop resumes on a new date.
        while start < end:
            midnight = datetime.combine(start.date() + timedelta(days=1), datetime.min.time(), MOSCOW)
            boundary = min(midnight, end)
            seconds = (boundary - start).total_seconds()
            key = (self.active, start.date().isoformat())
            self.totals[key] = self.totals.get(key, 0.0) + seconds
            self.pending[key] = self.pending.get(key, 0.0) + seconds
            start = boundary
        self.session_seconds += elapsed

    def start(self, category_id, day=None):
        selected_day = date.fromisoformat(str(day)) if day is not None else None
        if category_id not in {c["id"] for c in self.store.categories()}:
            raise ValueError("Выбери категорию.")
        self.tick()
        if self.active == category_id and self.active_day == selected_day:
            return
        self.flush()
        self.active = self.selected = category_id
        self.active_day = selected_day
        self.session_seconds = 0.0

    def pause(self):
        self.tick()
        self.flush()
        self.active = None
        self.active_day = None

    def flush(self):
        if self.pending:
            self.store.add_time(self.pending)
            self.pending.clear()  # Only acknowledge after the transaction succeeds.
        self._saved_at = time.monotonic()

    def checkpoint(self):
        self.tick()
        if time.monotonic() - self._saved_at >= 5:
            self.flush()

    def clear_category_day(self, category_id, day):
        selected=self.store.groups.start(day)
        if category_id not in {c['id'] for c in self.store.categories()}:
            raise ValueError('Категория не найдена.')
        self.tick()
        self.flush()
        removed=self.store.clear_category_day(category_id,day)
        for key in removed:self.totals.pop(key,None)
        active_day=self.active_day or self.wall().astimezone(MOSCOW).date()
        if self.active==category_id and self.store.groups.start(active_day)==selected:
            self.active=None
            self.active_day=None
            self.session_seconds=0.0
        return removed

    def restore_category_time(self, amounts):
        self.tick()
        self.flush()
        self.store.add_time(amounts)
        for key,seconds in amounts.items():
            self.totals[key]=self.totals.get(key,0.0)+seconds

    def category_time(self, category_id, day=None):
        selected=str(self.store.groups.start(day)) if day is not None else None
        return sum(seconds for (cid, date), seconds in self.totals.items()
                   if cid == category_id and (selected is None or str(self.store.groups.start(date))==selected))

    def day_time(self, day):
        selected=str(self.store.groups.start(day))
        return sum(seconds for (_, date), seconds in self.totals.items() if str(self.store.groups.start(date))==selected)

    def close(self):
        self.pause()
        self.store.close()
