"""Legacy night-oriented storage and shared clock helpers; current UI uses sleep_days."""
from datetime import date, datetime, timedelta
import math
import re
from study_core import MOSCOW, now_moscow


def stamp(value):
    if value is None or value == '':
        return None
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Укажи дату и время по Москве.')
    return result.astimezone(MOSCOW)


def clock_average(values):
    """Circular average: 23:00 and 01:00 average to 00:00, not noon."""
    values = [stamp(v) for v in values if v]
    if not values:
        return None
    angles = [(v.hour*3600+v.minute*60+v.second)*2*math.pi/86400 for v in values]
    x, y = sum(math.cos(a) for a in angles), sum(math.sin(a) for a in angles)
    if math.hypot(x,y) < 1e-8:
        return None
    minutes = round((math.atan2(y,x) % (2*math.pi))*1440/(2*math.pi)) % 1440
    return f'{minutes//60:02}:{minutes%60:02}'


def night_day(row):
    return stamp(row['wake_at'] or row['bed_at']).date()


def times_for_day(day, bed_text, wake_text, record=None):
    """The chosen sleep date is the wake date; an overnight bed is the day before."""
    day = date.fromisoformat(str(day))
    values = {}
    for key,text in [('bed_at',bed_text),('wake_at',wake_text)]:
        text = text.strip()
        if not text:
            values[key] = None
            continue
        if not re.fullmatch(r'\d{1,2}:\d{2}',text):
            raise ValueError('Введи только время: ЧЧ:ММ, например 23:30.')
        try:
            time = datetime.strptime(text,'%H:%M').time()
        except ValueError as exc:
            raise ValueError('Часы — от 00 до 23, минуты — от 00 до 59.') from exc
        values[key] = datetime.combine(day,time,MOSCOW)
    bed,wake = values['bed_at'],values['wake_at']
    if record and all((stamp(record[k]).strftime('%H:%M') if record[k] else '')==text.strip()
                      for k,text in [('bed_at',bed_text),('wake_at',wake_text)]):
        return stamp(record['bed_at']),stamp(record['wake_at'])
    if bed and wake and bed>=wake:
        bed-=timedelta(days=1)
    if record and bed and not wake and record['bed_at']:
        bed=bed.replace(year=stamp(record['bed_at']).year,month=stamp(record['bed_at']).month,day=stamp(record['bed_at']).day)
    # Keep existing seconds if the time and inferred date have not changed.
    if record:
        for key,value in [('bed_at',bed),('wake_at',wake)]:
            old=stamp(record[key])
            if old and value and old.replace(second=0,microsecond=0)==value:
                if key=='bed_at':bed=old
                else:wake=old
    return bed,wake


class SleepStore:
    def __init__(self, db, wall=None):
        self.db, self.wall = db, wall or now_moscow
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sleep_records (
                id INTEGER PRIMARY KEY,
                bed_at TEXT,
                wake_at TEXT,
                CHECK(bed_at IS NOT NULL OR wake_at IS NOT NULL)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_sleep
                ON sleep_records((1)) WHERE bed_at IS NOT NULL AND wake_at IS NULL;
        ''')
        self.revision = 0

    def records(self):
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM sleep_records ORDER BY COALESCE(wake_at,bed_at) DESC,id DESC')]

    def current(self):
        row = self.db.execute('SELECT * FROM sleep_records WHERE bed_at IS NOT NULL AND wake_at IS NULL').fetchone()
        return dict(row) if row else None

    def save(self, bed=None, wake=None, record_id=None):
        bed, wake = stamp(bed), stamp(wake)
        now = self.wall().astimezone(MOSCOW)
        if bed is None and wake is None:
            raise ValueError('Укажи хотя бы время сна или пробуждения.')
        if any(v and v > now+timedelta(minutes=1) for v in (bed,wake)):
            raise ValueError('Это время ещё не наступило. Проверь дату.')
        if bed and wake and wake <= bed:
            raise ValueError('Пробуждение должно быть позже засыпания. Проверь даты.')
        with self.db:
            if record_id is not None and not self.db.execute('SELECT 1 FROM sleep_records WHERE id=?',(record_id,)).fetchone():
                raise ValueError('Запись уже удалена.')
            for row in self.records():
                if row['id']==record_id:
                    continue
                other_bed, other_wake = stamp(row['bed_at']), stamp(row['wake_at'])
                if bed and not wake and other_bed and not other_wake:
                    raise ValueError('Уже отмечен сон без пробуждения. Заверши или исправь его.')
                if bed and other_bed:
                    end, other_end = wake or now, other_wake or now
                    if bed < other_end and other_bed < end:
                        raise ValueError('Этот сон пересекается с другой записью. Проверь время.')
                if not bed and wake and not other_bed and other_wake == wake:
                    raise ValueError('Это пробуждение уже записано.')
            values = (bed.isoformat() if bed else None,wake.isoformat() if wake else None)
            if record_id is None:
                record_id = self.db.execute('INSERT INTO sleep_records(bed_at,wake_at) VALUES(?,?)',values).lastrowid
            else:
                self.db.execute('UPDATE sleep_records SET bed_at=?,wake_at=? WHERE id=?',values+(record_id,))
        self.revision += 1
        return record_id

    def mark_bed(self):
        if self.current():
            raise ValueError('Сон уже отмечен. Нажми «Проснулся» или исправь запись.')
        return self.save(bed=self.wall())

    def mark_wake(self):
        current = self.current()
        now = self.wall()
        # The first morning can be recorded without inventing last night's bedtime.
        if not current:
            latest = next((r for r in self.records() if r['wake_at']),None)
            if latest and 0 <= (now-stamp(latest['wake_at'])).total_seconds() < 60:
                return latest['id']
            return self.save(wake=now)
        return self.save(current['bed_at'],now,current['id'])

    def delete(self, record_id):
        with self.db:
            self.db.execute('DELETE FROM sleep_records WHERE id=?',(record_id,))
        self.revision += 1

    def report(self, start, end):
        rows = [r for r in self.records() if start <= night_day(r) <= end]
        complete = [r for r in rows if r['bed_at'] and r['wake_at']]
        durations = [(stamp(r['wake_at'])-stamp(r['bed_at'])).total_seconds() for r in complete]
        return dict(rows=rows,complete=len(complete),
                    average_seconds=sum(durations)/len(durations) if durations else None,
                    average_bed=clock_average(r['bed_at'] for r in rows),
                    average_wake=clock_average(r['wake_at'] for r in rows))

    def activity_report(self, start, end, study_totals):
        """Study credited to each wake date / marked awake time on those dates.

        Repeated wakes split an awake interval instead of counting it twice.
        Naps create multiple intervals on a day, whose durations are added.
        Historical study remains assigned to the date chosen in the study timer.
        """
        now = self.wall().astimezone(MOSCOW)
        rows = self.records()
        beds = sorted(stamp(r['bed_at']) for r in rows if r['bed_at'])
        wakes = sorted(set(stamp(r['wake_at']) for r in rows if r['wake_at']))
        daily = {}
        for index, wake in enumerate(wakes):
            if not start <= wake.date() <= end or wake > now:
                continue
            following = [now]
            following.extend(b for b in beds if wake <= b <= now)
            if index+1 < len(wakes) and wakes[index+1] <= now:
                following.append(wakes[index+1])
            boundary = min(following)
            key = wake.date().isoformat()
            daily[key] = daily.get(key,0.0)+max(0,(boundary-wake).total_seconds())
        study_by_day = {day:sum(s for (_,d),s in study_totals.items() if d==day) for day in daily}
        awake = sum(daily.values())
        study = sum(study_by_day.values())
        return dict(awake_seconds=awake,study_seconds=study,
                    ratio=study/awake if awake>0 else None,
                    daily={d:dict(awake_seconds=s,study_seconds=study_by_day[d],
                                  ratio=study_by_day[d]/s if s>0 else None) for d,s in daily.items()})
