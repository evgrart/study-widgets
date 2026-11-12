"""Reversible links between calendar dates after explicitly sleepless nights."""
from datetime import date,timedelta


class DayGroups:
    def __init__(self,db):
        self.db=db
        db.executescript('''CREATE TABLE IF NOT EXISTS sleepless_nights(day TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS merged_sleep_edits(
                day TEXT NOT NULL,end_day TEXT NOT NULL,wake_at TEXT,bed_at TEXT,
                PRIMARY KEY(day,end_day));''')

    def nights(self):return {r[0] for r in self.db.execute('SELECT day FROM sleepless_nights')}

    def start(self,day):
        day=date.fromisoformat(str(day));nights=self.nights()
        while day>date.min and (day-timedelta(days=1)).isoformat() in nights:day-=timedelta(days=1)
        return day

    def end(self,day):
        day=self.start(day);nights=self.nights()
        while day.isoformat() in nights:day+=timedelta(days=1)
        return day

    def set(self,day,enabled):
        day=date.fromisoformat(str(day)).isoformat()
        with self.db:
            if enabled:self.db.execute('INSERT OR IGNORE INTO sleepless_nights(day) VALUES(?)',(day,))
            else:self.db.execute('DELETE FROM sleepless_nights WHERE day=?',(day,))

    def totals(self,values):
        result={}
        for (cid,day),seconds in values.items():
            key=(cid,str(self.start(day)));result[key]=result.get(key,0)+seconds
        return result
