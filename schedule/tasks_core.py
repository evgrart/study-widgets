"""Private, transactional task cache and a durable queue for Google Tasks."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import hashlib
import sqlite3

from app_paths import ROOT, CODE_ROOT
DATABASE = ROOT / 'google-tasks.sqlite3'
TASKS_SYNC_INTERVAL = 3600


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    due: str | None
    completed: bool = False
    remote_id: str | None = None
    list_id: str = '~default'
    list_title: str = 'My Tasks'
    pending: str = ''
    revision: int = 0
    date_label: str = ''


class TaskStore:
    def __init__(self, path=DATABASE):
        self.path = Path(path)
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due TEXT,
                completed INTEGER NOT NULL DEFAULT 0, remote_id TEXT,
                list_id TEXT NOT NULL DEFAULT '~default', list_title TEXT NOT NULL DEFAULT 'My Tasks',
                pending TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
                date_label TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0,
                UNIQUE(list_id, remote_id))''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def task(row):
        return Task(**{k: bool(row[k]) if k == 'completed' else row[k]
                       for k in Task.__dataclass_fields__})

    def items(self):
        with self.connection() as db:
            return [self.task(r) for r in db.execute(
                'SELECT * FROM tasks WHERE deleted=0 ORDER BY due IS NULL,due,id')]

    def get(self, identity):
        with self.connection() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=? AND deleted=0', (identity,)).fetchone()
            return self.task(row) if row else None

    def toggle(self, identity):
        with self.connection() as db:
            db.execute('''UPDATE tasks SET completed=1-completed, revision=revision+1,
                pending=CASE WHEN remote_id IS NULL THEN 'create' ELSE 'status' END
                WHERE id=? AND deleted=0''', (identity,))

    def seed(self, entries, key='study-plan-2026-11-02'):
        with self.connection() as db:
            for index, entry in enumerate(entries):
                identity = 'local-' + hashlib.sha256(f'{key}/{index}'.encode()).hexdigest()[:24]
                db.execute('''INSERT OR IGNORE INTO tasks(id,title,due,pending)
                              VALUES(?,?,?,'create')''', (identity, entry['title'], entry.get('due')))

    def link(self, identity, remote_id, revision):
        with self.connection() as db:
            db.execute('''UPDATE tasks SET remote_id=?, pending=CASE
                WHEN revision=? THEN '' ELSE 'status' END WHERE id=?''',
                       (remote_id, revision, identity))

    def acknowledge(self, identity, revision):
        with self.connection() as db:
            db.execute("UPDATE tasks SET pending='' WHERE id=? AND revision=?", (identity, revision))

    def merge(self, remote, complete_lists=()):
        """Keep queued local changes; merge a complete, authenticated remote snapshot."""
        with self.connection() as db:
            # Recover safely after a process exit between remote creation and acknowledgement.
            pending = db.execute("SELECT * FROM tasks WHERE pending='create' AND remote_id IS NULL").fetchall()
            for local in pending:
                matches = [r for r in remote if r['title'] == local['title']
                           and r.get('due') == local['due'] and r['list_id'] == local['list_id']]
                if len(matches) > 1:
                    raise ValueError('ambiguous_duplicate_task')
                if len(matches) == 1:
                    r = matches[0]
                    owned = db.execute('SELECT id FROM tasks WHERE list_id=? AND remote_id=?',
                                       (r['list_id'], r['remote_id'])).fetchone()
                    if owned and owned['id'] != local['id']:
                        raise ValueError('remote_task_already_linked')
                    db.execute("UPDATE tasks SET remote_id=?,pending=? WHERE id=?",
                               (r['remote_id'], 'status' if bool(local['completed']) != r['completed'] else '', local['id']))
            seen = set()
            for r in remote:
                key = (r['list_id'], r['remote_id'])
                if key in seen:
                    raise ValueError('duplicate_remote_id')
                seen.add(key)
                old = db.execute('SELECT * FROM tasks WHERE list_id=? AND remote_id=?', key).fetchone()
                if old:
                    if old['pending'] != 'create':
                        # Google hides the scheduled date in completed task rows.
                        due = old['due'] if r['completed'] and not r.get('date_label') and not r.get('due_known') else r.get('due')
                        completed=old['completed'] if old['pending']=='status' else r['completed']
                        db.execute('''UPDATE tasks SET title=?,due=?,completed=?,list_title=?,
                                      date_label=?,deleted=0 WHERE id=?''',
                                   (r['title'], due, completed, r['list_title'],
                                    r.get('date_label', ''), old['id']))
                else:
                    identity = 'remote-' + hashlib.sha256('/'.join(key).encode()).hexdigest()[:24]
                    db.execute('''INSERT INTO tasks(id,title,due,completed,remote_id,list_id,list_title,date_label)
                                  VALUES(?,?,?,?,?,?,?,?)''',
                               (identity, r['title'], r.get('due'), r['completed'], r['remote_id'],
                                r['list_id'], r['list_title'], r.get('date_label', '')))
            for row in db.execute("SELECT id,list_id,remote_id FROM tasks WHERE pending='' AND remote_id IS NOT NULL").fetchall():
                if row['list_id'] in complete_lists and (row['list_id'], row['remote_id']) not in seen:
                    db.execute('UPDATE tasks SET deleted=1 WHERE id=?', (row['id'],))


def week_tasks(items, first_day, completed=False):
    end = first_day + timedelta(days=7)
    return [item for item in items if (completed or not item.completed) and item.due
            and first_day <= date.fromisoformat(item.due) < end]


def sidebar_tasks(items, today):
    """Undated first, unfinished overdue tasks, and today through seven days ahead."""
    finish=today+timedelta(days=7)
    selected=[]
    for task in items:
        if not task.due:
            selected.append(task)
            continue
        due=date.fromisoformat(task.due)
        if (due<today and not task.completed) or today<=due<=finish:
            selected.append(task)
    return sorted(selected,key=lambda t:(t.due is not None,t.due or '',t.title.casefold()))


def task_groups(items, first_day, completed=False):
    selected = week_tasks(items, first_day, completed)
    return [[t for t in selected if t.due == (first_day+timedelta(days=i)).isoformat()] for i in range(7)]
