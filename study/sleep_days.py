"""Wake-to-bed days; sleep is the gap from bedtime to the next wake."""
from datetime import date, datetime, timedelta
from pathlib import Path
from contextlib import closing
import sqlite3
import re
from study_core import MOSCOW, now_moscow
from sleep_core import stamp, clock_average
from day_groups import DayGroups


def night_day(row):
    return date.fromisoformat(row['day'])


def times_for_day(day,bed_text,wake_text,record=None,end_day=None):
    """A smaller bed clock means the date following the selected wake day."""
    day=date.fromisoformat(str(day));values={}
    for key,text in [('wake_at',wake_text),('bed_at',bed_text)]:
        text=text.strip()
        if not text:values[key]=None;continue
        if not re.fullmatch(r'\d{1,2}:\d{2}',text):
            raise ValueError('Введи только время: ЧЧ:ММ, например 23:30.')
        try:clock=datetime.strptime(text,'%H:%M').time()
        except ValueError as exc:raise ValueError('Часы — от 00 до 23, минуты — от 00 до 59.') from exc
        values[key]=datetime.combine(day,clock,MOSCOW)
    wake,bed=values['wake_at'],values['bed_at']
    if bed and end_day is not None:
        bed=datetime.combine(date.fromisoformat(str(end_day)),bed.timetz())
        if wake and bed.time()<wake.time():bed+=timedelta(days=1)
    elif wake and bed and bed<wake:bed+=timedelta(days=1)
    if record:
        for key,value in [('wake_at',wake),('bed_at',bed)]:
            old=stamp(record[key])
            if old and value and old.replace(second=0,microsecond=0)==value:
                if key=='wake_at':wake=old
                else:bed=old
    return bed,wake


class SleepStore:
    def __init__(self,db,wall=None):
        self.db,self.wall=db,wall or now_moscow
        self.revision=0
        self.groups=DayGroups(db)
        self._migrate()
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS sleep_naps (
                id INTEGER PRIMARY KEY,day TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS sleep_diary (
                wake_id INTEGER PRIMARY KEY REFERENCES sleep_days(id) ON DELETE CASCADE,
                latency_minutes INTEGER CHECK(latency_minutes BETWEEN 0 AND 180),
                awake_minutes INTEGER CHECK(awake_minutes BETWEEN 0 AND 1440),
                quality INTEGER CHECK(quality BETWEEN 1 AND 5),
                notes TEXT NOT NULL DEFAULT '')''')

    @property
    def latency_minutes(self):
        row=self.db.execute("SELECT value FROM settings WHERE key='sleep_latency_minutes'").fetchone()
        try:
            value=int(row[0]) if row else 25
            return value if 0<=value<=180 else 25
        except (ValueError,TypeError):return 25

    def set_latency_minutes(self,minutes):
        if isinstance(minutes,bool) or not isinstance(minutes,int) or not 0<=minutes<=180:
            raise ValueError('Укажи целое число минут от 0 до 180.')
        with self.db:
            self.db.execute("INSERT INTO settings(key,value) VALUES('sleep_latency_minutes',?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(minutes),))
        self.revision+=1

    def _migrate(self):
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sleep_days'").fetchone():return
        old_exists=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sleep_records'").fetchone()
        old=[dict(r) for r in self.db.execute('SELECT * FROM sleep_records')] if old_exists else []
        if old:
            path=self.db.execute('PRAGMA database_list').fetchone()[2]
            if path:
                backup=Path(path).parent/'backups'/('before-wake-bed-'+now_moscow().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
                backup.parent.mkdir(parents=True,exist_ok=True)
                with closing(sqlite3.connect(backup)) as dest:self.db.backup(dest)
        with self.db:
            self.db.execute('''CREATE TABLE sleep_days (
                id INTEGER PRIMARY KEY, day TEXT NOT NULL, wake_at TEXT, bed_at TEXT,
                CHECK(wake_at IS NOT NULL OR bed_at IS NOT NULL))''')
            # Preserve the original table and regroup its exact timestamped marks.
            events=sorted(set((r[key],key) for r in old for key in ('wake_at','bed_at') if r[key]),
                          key=lambda e:(e[0],0 if e[1]=='wake_at' else 1))
            current=None
            for value,kind in events:
                if kind=='wake_at':
                    current=self.db.execute('INSERT INTO sleep_days(day,wake_at) VALUES(?,?)',
                                            (stamp(value).date().isoformat(),value)).lastrowid
                elif current is not None:
                    self.db.execute('UPDATE sleep_days SET bed_at=? WHERE id=?',(value,current));current=None
                else:self.db.execute('INSERT INTO sleep_days(day,bed_at) VALUES(?,?)',(stamp(value).date().isoformat(),value))

    def records(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM sleep_days ORDER BY day DESC,COALESCE(wake_at,bed_at) DESC,id DESC')]

    def nap_records(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM sleep_naps ORDER BY start_at,id')]

    def naps(self):
        return [dict(r,start=stamp(r['start_at']),end=stamp(r['end_at']),
            seconds=(stamp(r['end_at'])-stamp(r['start_at'])).total_seconds()) for r in self.nap_records()]

    def save_nap(self,start,end,record_id=None):
        start,end=stamp(start),stamp(end)
        if not start or not end or end<=start:raise ValueError('Пробуждение должно быть позже засыпания.')
        if start.date()!=end.date():raise ValueError('Укажи дневной сон в пределах одного календарного дня.')
        if end>self.wall()+timedelta(minutes=1):raise ValueError('Запиши дневной сон после пробуждения.')
        for nap in self.naps():
            if nap['id']!=record_id and start<nap['end'] and nap['start']<end:
                raise ValueError('Этот сон пересекается с другим дневным сном.')
        for episode in self.episodes():
            if start<episode['wake'] and episode['bed']<end:
                raise ValueError('Этот период уже входит в запись ночного сна.')
        with self.db:
            if record_id is None:
                record_id=self.db.execute('INSERT INTO sleep_naps(day,start_at,end_at) VALUES(?,?,?)',
                    (str(start.date()),start.isoformat(),end.isoformat())).lastrowid
            elif self.db.execute('UPDATE sleep_naps SET day=?,start_at=?,end_at=? WHERE id=?',
                    (str(start.date()),start.isoformat(),end.isoformat(),record_id)).rowcount!=1:
                raise ValueError('Запись дневного сна уже удалена.')
        self.revision+=1;return record_id

    def delete_nap(self,record_id):
        with self.db:self.db.execute('DELETE FROM sleep_naps WHERE id=?',(record_id,))
        self.revision+=1

    def logical_records(self):
        grouped={};result=[]
        for row in self.records():grouped.setdefault(str(self.groups.start(row['day'])),[]).append(row)
        for night in self.groups.nights():grouped.setdefault(str(self.groups.start(night)),[])
        for day,rows in grouped.items():
            end=str(self.groups.end(day))
            if day==end:result.extend(rows);continue
            wakes=[r for r in rows if r['wake_at']]
            first=min(wakes,key=lambda r:r['wake_at']) if wakes else None
            beds=[r for r in rows if r['day']==end and r['bed_at']]
            last=max(beds,key=lambda r:r['bed_at']) if beds else None
            edit=self.db.execute('SELECT wake_at,bed_at,end_day FROM merged_sleep_edits WHERE day=? AND end_day<=? ORDER BY end_day DESC LIMIT 1',(day,end)).fetchone()
            identity=first or last or (rows[0] if rows else None)
            result.append(dict(id=identity['id'] if identity else None,day=day,
                wake_at=edit[0] if edit else first['wake_at'] if first else None,
                bed_at=edit[1] if edit and edit[2]==end else last['bed_at'] if last else None,
                end_day=end,source_ids=tuple(r['id'] for r in rows)))
        return sorted(result,key=lambda r:(r['day'],r['wake_at'] or r['bed_at'] or ''),reverse=True)

    def set_sleepless(self,day,enabled):
        day=date.fromisoformat(str(day))
        if enabled and day>=self.wall().date():raise ValueError('Выбери прошедший день: отметка объединит его со следующим.')
        self.groups.set(day,enabled);self.revision+=1

    def save_selected(self,bed,wake,row,day):
        start=self.groups.start(day);end=self.groups.end(day)
        if start==end:return self.save(bed,wake,row['id'] if row else None,day)
        bed,wake=stamp(bed),stamp(wake)
        if not bed and not wake:raise ValueError('Укажи хотя бы время пробуждения или сна.')
        if wake and wake>self.wall()+timedelta(minutes=1):raise ValueError('Это пробуждение ещё не наступило.')
        if bed and wake and bed<wake:raise ValueError('Время сна должно быть после пробуждения.')
        for other in self.logical_records():
            if other['day']==str(start):continue
            ow,ob=stamp(other['wake_at']),stamp(other['bed_at'])
            if wake and bed and ow and ob and wake<ob and ow<bed:raise ValueError('Этот день пересекается с другой записью.')
        identity=row['id'] if row else None
        if identity is None:identity=self.save(wake=wake,bed=None if wake else bed,day=start if wake else end)
        with self.db:self.db.execute('INSERT INTO merged_sleep_edits(day,end_day,wake_at,bed_at) VALUES(?,?,?,?) '
            'ON CONFLICT(day,end_day) DO UPDATE SET wake_at=excluded.wake_at,bed_at=excluded.bed_at',
            (str(start),str(end),wake.isoformat() if wake else None,bed.isoformat() if bed else None))
        self.revision+=1;return identity

    def delete_selected(self,row):
        if 'source_ids' not in row:return self.delete(row['id'])
        with self.db:
            for rid in row['source_ids']:self.db.execute('DELETE FROM sleep_days WHERE id=?',(rid,))
            self.db.execute('DELETE FROM merged_sleep_edits WHERE day=? AND end_day=?',(row['day'],row['end_day']))
        self.revision+=1

    def current(self):
        now=self.wall().astimezone(MOSCOW)
        occurred=[]
        for row in self.logical_records():
            times=[stamp(row[k]) for k in ('wake_at','bed_at') if row[k] and stamp(row[k])<=now]
            if times:occurred.append((max(times),row['id'],row))
        latest=max(occurred,key=lambda item:item[:2])[2] if occurred else None
        return latest if latest and latest['wake_at'] and (not latest['bed_at'] or stamp(latest['bed_at'])>now) else None

    def save(self,bed=None,wake=None,record_id=None,day=None):
        bed,wake=stamp(bed),stamp(wake);now=self.wall().astimezone(MOSCOW)
        if bed is None and wake is None:raise ValueError('Укажи хотя бы время пробуждения или сна.')
        if (wake and wake>now+timedelta(minutes=1)) or (bed and bed>now+timedelta(minutes=1)):
            raise ValueError('Это время ещё не наступило. Проверь выбранный день.')
        if bed and wake and bed<wake:raise ValueError('Время сна должно быть после пробуждения.')
        selected_day=date.fromisoformat(str(day)) if day else (wake or bed).date()
        with self.db:
            if record_id is not None and not self.db.execute('SELECT 1 FROM sleep_days WHERE id=?',(record_id,)).fetchone():
                raise ValueError('Запись уже удалена.')
            for row in self.records():
                if row['id']==record_id:continue
                other_bed,other_wake=stamp(row['bed_at']),stamp(row['wake_at'])
                if wake and other_wake==wake:raise ValueError('Это пробуждение уже записано.')
                if bed and other_bed==bed:raise ValueError('Это время сна уже записано.')
                if wake and bed and other_wake and other_bed and wake<other_bed and other_wake<bed:
                    raise ValueError('Этот день пересекается с другой записью. Проверь время.')
            values=(selected_day.isoformat(),wake.isoformat() if wake else None,bed.isoformat() if bed else None)
            if record_id is None:
                record_id=self.db.execute('INSERT INTO sleep_days(day,wake_at,bed_at) VALUES(?,?,?)',values).lastrowid
            else:self.db.execute('UPDATE sleep_days SET day=?,wake_at=?,bed_at=? WHERE id=?',values+(record_id,))
        self.revision+=1
        return record_id

    def mark_wake(self):
        now=self.wall();current=self.current()
        if current and self.groups.start(now.date())==self.groups.start(current['day']):return current['id']
        if current and stamp(current['wake_at']).date()==now.date():return current['id']
        return self.save(wake=now)

    def mark_bed(self,day=None):
        now=self.wall();current=self.current()
        selected=self.groups.start(day if day is not None else current['day'] if current else now.date())
        if self.groups.end(selected)>selected:
            row=next((r for r in self.logical_records() if r['day']==str(selected)),None)
            return self.save_selected(now,row['wake_at'] if row else None,row,selected)
        if day is not None:
            selected=date.fromisoformat(str(day))
            if selected>now.date():raise ValueError('Выбранный день ещё не наступил.')
            row=next((r for r in self.records() if night_day(r)==selected),None)
            if row:
                bed=stamp(row['bed_at'])
                if bed and 0<=(now-bed).total_seconds()<60:return row['id']
                return self.save(now,row['wake_at'],row['id'],row['day'])
            return self.save(bed=now,day=selected)
        if current:return self.save(now,current['wake_at'],current['id'],current['day'])
        latest=next((r for r in self.records() if r['bed_at']),None)
        if latest and 0<=(now-stamp(latest['bed_at'])).total_seconds()<60:return latest['id']
        return self.save(bed=now)

    def delete(self,record_id):
        with self.db:self.db.execute('DELETE FROM sleep_days WHERE id=?',(record_id,))
        self.revision+=1

    def sleep_intervals(self):
        return [(e['sleep_start'],e['wake']) for e in self.episodes()]

    def diary(self):
        return {r['wake_id']:dict(r) for r in self.db.execute('SELECT * FROM sleep_diary')}

    def save_diary(self,wake_id,latency=None,awake=None,quality=None,notes=''):
        for value,minimum,maximum in ((latency,0,180),(awake,0,1440),(quality,1,5)):
            if value is not None and (isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum):
                raise ValueError('Проверь минуты и оценку качества от 1 до 5.')
        episode=next((e for e in self.episodes() if e['wake_id']==wake_id),None)
        if episode is None:raise ValueError('Для этой ночи нужны обе отметки: сон и пробуждение.')
        if len(notes)>1000:raise ValueError('Заметка должна быть короче 1000 символов.')
        if (latency is not None or awake is not None) and ((latency if latency is not None else self.latency_minutes)+(awake or 0))*60>episode['window_seconds']:
            raise ValueError('Засыпание и пробуждения длиннее всего периода сна. Проверь отметки.')
        with self.db:
            self.db.execute('''INSERT INTO sleep_diary(wake_id,latency_minutes,awake_minutes,quality,notes)
                VALUES(?,?,?,?,?) ON CONFLICT(wake_id) DO UPDATE SET latency_minutes=excluded.latency_minutes,
                awake_minutes=excluded.awake_minutes,quality=excluded.quality,notes=excluded.notes''',
                (wake_id,latency,awake,quality,notes.strip()))
        self.revision+=1

    def episodes(self):
        """Completed, ordered bed→wake pairs; missing marks are never invented."""
        records=self.logical_records();details=self.diary();default=self.latency_minutes
        now=self.wall().astimezone(MOSCOW)
        events=sorted((stamp(r[k]),k,r['id'],r['day']) for r in records for k in ('wake_at','bed_at') if r[k] and stamp(r[k])<=now)
        bed=None;result=[]
        for when,kind,rid,day in events:
            if kind=='bed_at':bed=(when,rid)
            elif bed and when>bed[0]:
                detail=details.get(rid,{})
                latency=detail.get('latency_minutes')
                used=default if latency is None else latency
                awake=detail.get('awake_minutes')
                window=(when-bed[0]).total_seconds()
                result.append(dict(wake_id=rid,bed_id=bed[1],day=day,bed=bed[0],wake=when,
                    sleep_start=min(bed[0]+timedelta(minutes=used),when),
                    seconds=max(0,window-(used+(awake or 0))*60),window_seconds=window,
                    latency_minutes=used,latency_reported=latency is not None,
                    awake_minutes=awake,quality=detail.get('quality'),notes=detail.get('notes',''),
                    needs_review=window>24*3600 or window<(used+(awake or 0))*60))
                bed=None
        return result

    def report(self,start,end):
        if start==end:start=end=self.groups.start(start)
        rows=[r for r in self.logical_records() if start<=night_day(r)<=end]
        intervals=[e for e in self.episodes() if start<=date.fromisoformat(e['day'])<=end]
        durations=[e['seconds'] for e in intervals]
        return dict(rows=rows,complete=len(intervals),
                    latency_minutes=self.latency_minutes,
                    average_seconds=sum(durations)/len(durations) if durations else None,
                    average_bed=clock_average(r['bed_at'] for r in rows if r['bed_at'] and stamp(r['bed_at'])<=self.wall()),
                    average_wake=clock_average(r['wake_at'] for r in rows))

    def activity_report(self,start,end,study_totals,days_off=()):
        if start==end:start=end=self.groups.start(start)
        study_totals=self.groups.totals(study_totals)
        now=self.wall().astimezone(MOSCOW);daily={}
        naps=self.naps()
        latency=timedelta(minutes=self.latency_minutes)
        latencies={e['bed_id']:timedelta(minutes=e['latency_minutes']) for e in self.episodes()}
        rows=[r for r in self.logical_records() if r['wake_at']]
        wakes=sorted(stamp(r['wake_at']) for r in rows)
        excluded={str(d) for d in days_off}
        for row in rows:
            wake=stamp(row['wake_at'])
            if not start<=night_day(row)<=end or wake>now or row['day'] in excluded:continue
            end_points=[now]
            if row['bed_at']:end_points.append(stamp(row['bed_at'])+latencies.get(row['id'],latency))
            end_points.extend(w for w in wakes if w>wake)
            boundary=min(end_points)
            seconds=max(0,(boundary-wake).total_seconds())
            seconds-=sum(max(0,(min(nap['end'],boundary)-max(nap['start'],wake)).total_seconds()) for nap in naps)
            seconds=max(0,seconds)
            daily[row['day']]=daily.get(row['day'],0)+seconds
        study_by_day={d:sum(s for (_,day),s in study_totals.items() if day==d) for d in daily}
        awake=sum(daily.values());study=sum(study_by_day.values())
        return dict(awake_seconds=awake,study_seconds=study,ratio=study/awake if awake>0 else None,
                    daily={d:dict(awake_seconds=s,study_seconds=study_by_day[d],ratio=study_by_day[d]/s if s>0 else None) for d,s in daily.items()})
