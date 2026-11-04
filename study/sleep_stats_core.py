"""Descriptive sleep diary statistics; no diagnostic scores or invented missing nights."""
from datetime import date,timedelta
import math
import statistics


def timing(values):
    values=list(values)
    if not values:return dict(mean=None,sd_minutes=None,n=0)
    minutes=[v.hour*60+v.minute+v.second/60 for v in values]
    sx=sum(math.sin(m*math.tau/1440) for m in minutes)
    cx=sum(math.cos(m*math.tau/1440) for m in minutes)
    if math.hypot(sx,cx)/len(values)<1e-7:return dict(mean=None,sd_minutes=None,n=len(values))
    center=(math.atan2(sx,cx)*1440/math.tau)%1440
    rounded=round(center)%1440
    deviations=[(m-center+720)%1440-720 for m in minutes]
    return dict(mean=f'{rounded//60:02}:{rounded%60:02}',
                sd_minutes=statistics.pstdev(deviations) if len(values)>=2 else None,n=len(values))


def sleep_report(data,start,end,study_totals,days_off=()):
    if start==end:start=end=data.groups.start(start)
    episodes=[e for e in data.episodes() if start<=date.fromisoformat(e['day'])<=end]
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    daily={day:[e for e in episodes if e['day']==day.isoformat() and not e['needs_review']] for day in days}
    naps=[]
    all_episodes=data.episodes()
    for nap in data.naps():
        day=data.groups.start(nap['day'])
        if not start<=day<=end:continue
        # If a night is later edited across an existing nap, do not count it twice.
        overlap=sum(max(0,(min(nap['end'],e['wake'])-max(nap['start'],e['bed'])).total_seconds()) for e in all_episodes)
        naps.append(dict(nap,logical_day=str(day),counted_seconds=max(0,nap['seconds']-overlap)))
    nap_daily={day:[n for n in naps if n['logical_day']==str(day)] for day in days}
    nap_totals={d:sum(n['counted_seconds'] for n in group) for d,group in nap_daily.items()}
    totals={d:sum(e['seconds'] for e in group)+nap_totals[d] if group or nap_daily[d] else None for d,group in daily.items()}
    recorded=[value for value in totals.values() if value is not None]
    primary=[max(group,key=lambda e:e['seconds']) for group in daily.values() if group]
    qualities=[e['quality'] for e in episodes if e['quality'] is not None]
    today=data.wall().date()
    expected=sum(d<=today and data.groups.start(d)==d for d in days)
    completed_days=sum((bool(group) or bool(nap_daily[d])) and d<=today for d,group in daily.items())
    activity=data.activity_report(start,end,study_totals,days_off)
    return dict(start=start,end=end,days=days,episodes=episodes,daily=daily,totals=totals,
        naps=naps,nap_daily=nap_daily,nap_totals=nap_totals,nap_seconds=sum(nap_totals.values()),
        mean_seconds=statistics.mean(recorded) if recorded else None,
        median_seconds=statistics.median(recorded) if recorded else None,
        min_seconds=min(recorded) if recorded else None,max_seconds=max(recorded) if recorded else None,
        completed_days=completed_days,expected_days=expected,missing_days=max(0,expected-completed_days),
        bed=timing(e['bed'] for e in primary),wake=timing(e['wake'] for e in primary),
        quality=statistics.mean(qualities) if qualities else None,quality_n=len(qualities),
        latency_n=sum(e['latency_reported'] for e in episodes),awake_n=sum(e['awake_minutes'] is not None for e in episodes),
        review_n=sum(e['needs_review'] for e in episodes),activity=activity,
        sleepless_days=tuple(sorted(d for d in data.groups.nights() if start.isoformat()<=d<=end.isoformat())),
        sleepless_nights=sum(start.isoformat()<=d<=end.isoformat() for d in data.groups.nights()),
        off_days=tuple(sorted(str(d) for d in days_off if start.isoformat()<=str(d)<=end.isoformat())))
