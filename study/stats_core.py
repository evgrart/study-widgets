"""Calendar ranges and study reports, computed only from recorded daily totals."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = ('январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
          'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь')
WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


def period_bounds(mode, anchor):
    if mode == 'day':
        return anchor, anchor
    if mode == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if mode == 'month':
        return anchor.replace(day=1), anchor.replace(day=monthrange(anchor.year, anchor.month)[1])
    raise ValueError('Unknown report period')


def move_period(mode, anchor, delta):
    if mode == 'day':
        return anchor + timedelta(days=delta)
    if mode == 'week':
        return anchor + timedelta(days=7*delta)
    if mode == 'month':
        absolute = anchor.year*12 + anchor.month-1 + delta
        year, month = divmod(absolute, 12)
        month += 1
        return date(year, month, min(anchor.day, monthrange(year, month)[1]))
    raise ValueError('Unknown report period')


def period_label(mode, anchor):
    start, end = period_bounds(mode, anchor)
    if mode == 'day':
        return f'{WEEKDAYS[start.weekday()]}, {start:%d.%m.%Y}'
    if mode == 'month':
        return f'{MONTHS[start.month-1].capitalize()} {start.year}'
    if start.year != end.year:
        return f'{start:%d.%m.%Y} — {end:%d.%m.%Y}'
    return f'{start:%d.%m} — {end:%d.%m.%Y}'


def short_time(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f'{hours} ч {minutes:02} мин'
    if minutes:
        return f'{minutes} мин'
    return f'{seconds} с'


@dataclass(frozen=True)
class Report:
    mode: str
    start: date
    end: date
    days: tuple
    categories: tuple
    series: dict
    category_totals: dict
    daily_totals: dict
    total: float
    active_days: int
    average_active_day: float
    best_day: date | None
    first_recorded_day: date | None
    days_off: tuple = ()
    excluded_total: float = 0.0


def build_report(totals, categories, mode, anchor, days_off=()):
    start, end = period_bounds(mode, anchor)
    days = tuple(start + timedelta(days=i) for i in range((end-start).days+1))
    category_ids = {c['id'] for c in categories}
    series = {day: {cid: 0.0 for cid in category_ids} for day in days}
    first = None
    excluded = {date.fromisoformat(str(d)) for d in days_off}
    excluded_total = 0.0
    for (cid, raw_day), seconds in totals.items():
        if cid not in category_ids or seconds <= 0:
            continue
        day = date.fromisoformat(raw_day)
        first = day if first is None else min(first, day)
        if start <= day <= end:
            if day in excluded:
                excluded_total += seconds
                continue
            series[day][cid] += seconds
    cat_totals = {cid: sum(series[day][cid] for day in days) for cid in category_ids}
    daily = {day: sum(series[day].values()) for day in days}
    total = sum(daily.values())
    active = sum(value > 0 for value in daily.values())
    best = max(days, key=lambda day: daily[day]) if active else None
    ordered = tuple(sorted((dict(c) for c in categories), key=lambda c: (-cat_totals[c['id']], c['id'])))
    return Report(mode, start, end, days, ordered, series, cat_totals, daily, total,
                  active, total/active if active else 0.0, best, first,
                  tuple(d for d in days if d in excluded),excluded_total)
