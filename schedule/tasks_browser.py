"""Google Tasks integration through its signed-in web UI, in our own Edge profile.

No normal browser profile, password, cookie export, or private Google endpoint is used.
Unknown page layouts fail closed and retain the last successful local snapshot.
"""
import argparse
import ctypes
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from app_paths import ROOT, CODE_ROOT

from tasks_core import TaskStore
from deadline_core import atomic_json, MOSCOW
from playwright.sync_api import TimeoutError as BrowserTimeout, Error as BrowserError

PROFILE = ROOT / 'google-tasks-profile'
STATUS = ROOT / 'google-tasks-status.json'
AUTH = ROOT / 'google-tasks-connected.flag'
ACCOUNT = ROOT / 'google-tasks-account.json'
URL = 'https://tasks.google.com/tasks/?hl=en'
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


class UnsupportedTasksPage(Exception):
    pass


class TemporaryTasksPage(UnsupportedTasksPage):
    """An incomplete page can be retried without discarding cached tasks."""


TRANSIENT_READ_ERRORS = {'no_task_lists', 'list_not_fully_loaded',
                         'completed_rows_incomplete', 'task_pagination_stalled'}


class GoogleLoginRequired(Exception):
    pass


def state(name, **fields):
    value=dict(state=name,checked_at=datetime.now(MOSCOW).isoformat(),pid=os.getpid(),**fields)
    for attempt in range(5):
        try:
            atomic_json(STATUS,value)
            return
        except PermissionError:
            if attempt==4:
                raise
            time.sleep(.05)


def parse_due(label, today=None):
    if not label:
        return None
    today = today or datetime.now(MOSCOW).date()
    label = label.removeprefix('Scheduled for ').strip()
    for relative, offset in [('Today', 0), ('Tomorrow', 1), ('Yesterday', -1)]:
        if re.match(r'^'+relative+r'(?:$|\b)', label):
            return (today+timedelta(days=offset)).isoformat()
    ago=re.fullmatch(r'(\d+) days? ago',label,flags=re.I)
    ahead=re.fullmatch(r'In (\d+) days?',label,flags=re.I)
    if ago or ahead:
        offset=int((ago or ahead)[1])*(-1 if ago else 1)
        try:return (today+timedelta(days=offset)).isoformat()
        except (ValueError,OverflowError) as exc:raise UnsupportedTasksPage('unknown_date_format') from exc
    found = re.search(r'\b('+'|'.join(m[:3]+r'(?:'+m[3:]+r')?' for m in MONTHS)+r')\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?', label)
    if not found:
        raise UnsupportedTasksPage('unknown_date_format')
    month = next(i+1 for i, name in enumerate(MONTHS) if name.startswith(found[1][:3]))
    day = int(found[2])
    if found[3]:
        value = date(int(found[3]), month, day)
    else:
        choices = []
        for year in [today.year-1, today.year, today.year+1]:
            try:
                choices.append(date(year, month, day))
            except ValueError:
                pass
        value = min(choices, key=lambda d: abs((d-today).days))
    return value.isoformat()




def is_own_debugger(process, profile=PROFILE):
    command=process.get('CommandLine') or ''
    path=re.escape(str(profile))
    return (process.get('Name','').casefold()=='msedge.exe'
            and bool(re.search(r'--remote-debugging-port=18763(?:\s|$)',command))
            and bool(re.search(r'--user-data-dir=(?:"'+path+r'"|'+path+r'(?=\s|$|"))',command,re.I)))


def own_debugger_running():
    """Reuse only our dedicated Edge profile, never a normal browser window."""
    script='''$listener=Get-NetTCPConnection -LocalPort 18763 -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' } | Select-Object -First 1;
        if($listener){Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$listener.OwningProcess) |
        Select-Object Name,CommandLine | ConvertTo-Json -Compress}'''
    shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result=subprocess.run([str(shell),'-NoProfile','-Command',script],capture_output=True,
                              encoding='utf-8',errors='replace',timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode==0 and bool(result.stdout.strip()) and is_own_debugger(json.loads(result.stdout))
    except (OSError,ValueError,subprocess.TimeoutExpired):return False


def close_setup_browser(driver):
    """Release only our old login browser before background headless sync."""
    if not own_debugger_running():return
    browser=driver.chromium.connect_over_cdp('http://127.0.0.1:18763',timeout=10000)
    try:
        try:browser.new_browser_cdp_session().send('Browser.close')
        except Exception:
            pass  # Closing the browser can close the transport before its reply.
    finally:
        try:browser.close()
        except Exception:pass
    finish=time.monotonic()+8
    while time.monotonic()<finish:
        try:
            with urlopen('http://127.0.0.1:18763/json/version',timeout=.5):pass
        except OSError:return
        time.sleep(.15)
    raise TemporaryTasksPage('setup_browser_busy')


def sync_in_background(driver):
    """Background jobs never reuse a visible tab or fall back to a headed window."""
    close_setup_browser(driver)
    context=driver.chromium.launch_persistent_context(str(PROFILE),channel='msedge',headless=False,
        locale='en-US',viewport={'width':1500,'height':1100},timeout=30000,
        args=['--no-first-run','--no-default-browser-check','--disable-extensions'],accept_downloads=False)
    try:
        synchronize(context.pages[0] if context.pages else context.new_page())
    finally:context.close()


def wait_for_login(browser,timeout=20*60):
    """Google may replace or close its original tab during account redirects."""
    expected=json.loads(ACCOUNT.read_text(encoding='utf-8'))['email']
    finish=time.monotonic()+timeout;empty_since=None
    while time.monotonic()<finish:
        if not browser.is_connected():raise TemporaryTasksPage('login_window_closed')
        pages=[page for context in browser.contexts for page in context.pages]
        if not pages:
            empty_since=empty_since or time.monotonic()
            if time.monotonic()-empty_since>=3:return False  # Verify saved cookies headlessly.
        else:empty_since=None
        for page in pages:
            try:
                if urlsplit(page.url).hostname!='tasks.google.com':continue
                account=page.get_by_role('button',name=re.compile('^Google Account:'))
                if not account.count():continue
                label=account.get_attribute('aria-label') or ''
                if expected.casefold() not in label.casefold():raise GoogleLoginRequired('wrong_google_account')
                AUTH.touch();return True
            except BrowserError:continue  # Redirects can invalidate any observed page handle.
        time.sleep(.5)
    raise GoogleLoginRequired('login_timeout')


def login_and_sync(driver):
    """Visible browser is for login only; task reads and writes remain headless."""
    state('connecting')
    edge=Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
    subprocess.Popen([str(edge),f'--user-data-dir={PROFILE}',
        '--remote-debugging-address=127.0.0.1','--remote-debugging-port=18763',
        '--no-first-run','--no-default-browser-check','--new-window',URL],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urlopen('http://127.0.0.1:18763/json/version',timeout=1):break
        except OSError:time.sleep(.25)
    if not own_debugger_running():raise TemporaryTasksPage('setup_browser_not_ready')
    browser=driver.chromium.connect_over_cdp('http://127.0.0.1:18763',timeout=15000)
    try:wait_for_login(browser)
    finally:
        try:browser.close()
        except Exception:pass
    close_setup_browser(driver)
    state('syncing')
    sync_in_background(driver)


class TasksBrowser:
    def __init__(self, page):
        self.page = page
        page.set_default_timeout(10000)

    def ready(self):
        self.page.goto(URL, wait_until='domcontentloaded', timeout=30000)
        if urlsplit(self.page.url).hostname != 'tasks.google.com':
            # A still-valid session can briefly visit Google Accounts for renewal.
            try:
                self.page.wait_for_url(re.compile(r'^https://tasks\.google\.com/tasks/'), timeout=12000)
            except Exception:
                if urlsplit(self.page.url).hostname == 'accounts.google.com':
                    raise GoogleLoginRequired('google_login_required')
                raise UnsupportedTasksPage('unexpected_google_page')
        self.page.get_by_role('button', name=re.compile('^Google Account:')).wait_for(timeout=20000)
        label = self.page.get_by_role('button', name=re.compile('^Google Account:')).get_attribute('aria-label')
        expected = json.loads(ACCOUNT.read_text(encoding='utf-8'))['email']
        if expected.casefold() not in label.casefold():
            raise GoogleLoginRequired('wrong_google_account')
        AUTH.touch()  # Account verification must survive a later parsing/network failure.
        self.page.get_by_role('menuitem', name='All tasks', exact=True).click()
        self.page.locator('[data-task-list-id][data-num-completed]').first.wait_for(timeout=20000)

    def snapshot(self, read_dates=True):
        """Retry asynchronous list updates; reload once before the final attempt."""
        self.snapshot_deadline=time.monotonic()+40
        for attempt in range(4):
            try:
                if attempt==3:self.ready()
                return self._snapshot_once(read_dates=read_dates)
            except (UnsupportedTasksPage,BrowserTimeout) as error:
                reason='task_page_timeout' if isinstance(error,BrowserTimeout) else str(error)
                if not isinstance(error,BrowserTimeout) and reason not in TRANSIENT_READ_ERRORS:
                    raise
                if attempt==3 or time.monotonic()>=self.snapshot_deadline:
                    raise TemporaryTasksPage(reason) from error
                self.page.wait_for_timeout((300,800,1600)[attempt])

    def _snapshot_once(self, read_dates=True):
        sections = self.page.locator('[data-task-list-id][data-num-completed]')
        if not sections.count():
            raise UnsupportedTasksPage('no_task_lists')
        for section in sections.all():
            expand = section.get_by_role('button', name='Completed tasks section', exact=True)
            if expand.count() and expand.get_attribute('aria-expanded') != 'true':
                expand.click()
                self.page.wait_for_function('(e)=>e.getAttribute("aria-expanded")==="true"', arg=expand.element_handle())
            self.load_more_tasks(section)
        rows = sections.evaluate_all('''(sections)=>sections.map(section=>({
            list_id:section.getAttribute('data-task-list-id'),
            list_title:section.querySelector('h2')?.textContent,
            expected_completed:Number(section.getAttribute('data-num-completed')),
            tasks:[...section.querySelectorAll('[role="listitem"][data-id]')].map(row=>({
                remote_id:row.getAttribute('data-id'),
                title:row.querySelector('[data-aria-label="Task title"]')?.getAttribute('data-rendered-value'),
                completed:row.querySelector('button[aria-label^="Mark completed"]')?.getAttribute('aria-pressed')==='true',
                date_label:row.querySelector('[role="button"][aria-label^="Scheduled for "]')?.getAttribute('aria-label')||''
            })).filter(t=>t.title)
        }))''')
        result, lists = [], []
        for section in rows:
            if not section['list_title']:
                raise UnsupportedTasksPage('list_not_fully_loaded')
            if sum(t['completed'] for t in section['tasks']) != section['expected_completed']:
                raise UnsupportedTasksPage('completed_rows_incomplete')
        for section in rows:
            lists.append(section['list_id'])
            for task in section['tasks']:
                if read_dates and task['completed'] and not task['date_label']:
                    task['date_label']=self.completed_date_label(task['remote_id'])
                    task['due_known']=True
                task.update(list_id=section['list_id'], list_title=section['list_title'],
                            due=parse_due(task['date_label']) if read_dates else None)
                result.append(task)
        return result, lists

    def load_more_tasks(self, section):
        """Google pages completed tasks in batches; never merge a partial list."""
        more=section.get_by_role('button',name='Load more tasks',exact=True)
        titles=section.locator('[role="listitem"][data-id] [data-aria-label="Task title"]')
        for _ in range(100):
            if not more.count() or not more.is_visible():return
            before=titles.count()
            more.click()
            finish=min(time.monotonic()+12,getattr(self,'snapshot_deadline',time.monotonic()+12))
            while time.monotonic()<finish:
                if titles.count()>before or not more.count() or not more.is_visible():break
                self.page.wait_for_timeout(100)
            else:raise UnsupportedTasksPage('task_pagination_stalled')
        raise UnsupportedTasksPage('task_pagination_limit')

    def completed_date_label(self, remote_id):
        """Read the scheduled date in the editor; completion time is unrelated."""
        row=self.row(remote_id)
        row.locator('[data-aria-label="Task title"]').click()
        try:
            row.get_by_role('textbox',name='Task title',exact=True).wait_for(state='visible')
            date_button=row.locator('[role="button"][aria-label^="Scheduled for "]')
            if date_button.count():
                label=date_button.get_attribute('aria-label')
                try:parse_due(label)
                except UnsupportedTasksPage:return self.picker_date_label(date_button)
                return label
            # An explicitly empty editor date is authoritative too.
            row.get_by_role('button',name='Add date/time',exact=True).wait_for(state='visible')
            return ''
        finally:
            # Blur without editing the title/date or toggling completion.
            row.locator('xpath=ancestor::*[@data-num-completed][1]').locator('h2').click()



    def row(self, remote_id):
        # IDs are observed Google row IDs, not code or selectors supplied by tasks.
        return self.page.locator('[role="listitem"][data-id]').filter(
            has=self.page.locator('[data-task-id='+json.dumps(remote_id)+']')).first

    def set_completed(self, task):
        row = self.row(task.remote_id)
        button = row.get_by_role('button', name=re.compile('^Mark completed:'))
        pressed = button.get_attribute('aria-pressed') == 'true'
        if pressed != task.completed:
            button.click()
        finish=time.monotonic()+12
        while time.monotonic()<finish:
            try:
                # Expand/reload rows, without opening every completed task's date editor.
                self.snapshot()
                check=self.row(task.remote_id).get_by_role('button',name=re.compile('^Mark completed:'))
                if check.count() and (check.get_attribute('aria-pressed')=='true')==task.completed:
                    return
            except UnsupportedTasksPage as error:
                if str(error)!='completed_rows_incomplete':
                    raise
            self.page.wait_for_timeout(300)
        raise UnsupportedTasksPage('completion_not_confirmed')

    def create(self, task):
        section = self.page.locator('[data-task-list-id][data-num-completed]').filter(
            has=self.page.get_by_role('heading', name=task.list_title, exact=True))
        if section.count() != 1:
            raise UnsupportedTasksPage('target_list_missing')
        section.get_by_role('button', name='Add a task', exact=True).click()
        title = self.page.get_by_role('textbox', name='Task title', exact=True)
        title.fill(task.title)
        if task.due:
            self.page.get_by_role('button', name='Add date/time', exact=True).click()
            dialog = self.page.get_by_role('dialog', name='Date picker', exact=True)
            dialog.wait_for()
            due = date.fromisoformat(task.due)
            name = f'{due.day} {MONTHS[due.month-1]} {due.year}'
            for _ in range(120):
                target = dialog.get_by_role('button', name=name, exact=True)
                if target.count():
                    target.click()
                    break
                caption = dialog.get_by_role('region', name='Calendar').inner_text().splitlines()[0]
                found = re.search(r'('+'|'.join(MONTHS)+r') (\d{4})', caption)
                if not found:
                    raise UnsupportedTasksPage('unknown_calendar_month')
                current = (int(found[2]), MONTHS.index(found[1])+1)
                dialog.get_by_role('button', name='Next month' if (due.year,due.month)>current else 'Previous month').click()
            else:
                raise UnsupportedTasksPage('date_too_far')
            dialog.get_by_role('button', name='Done', exact=True).click()
            dialog.wait_for(state='hidden')
        section.get_by_role('heading', name=task.list_title, exact=True).click()
        # Wait for the row's saved ID and scheduled date, not only the editor's text.
        finish = time.monotonic()+12
        while time.monotonic() < finish:
            remote, _ = self.snapshot()
            matches = [r for r in remote if r['title']==task.title and r['due']==task.due and r['list_id']==task.list_id]
            if len(matches) == 1:
                return matches[0]['remote_id']
            if len(matches)>1:
                raise UnsupportedTasksPage('ambiguous_created_task')
            self.page.wait_for_timeout(300)
        raise UnsupportedTasksPage('creation_not_confirmed')


def synchronize(page):
    browser=TasksBrowser(page);browser.ready();store=TaskStore()
    remote,lists=browser.snapshot();store.merge(remote,lists);sent=[]
    for item in store.items():
        task=store.get(item.id)
        if task.pending=='create':
            remote_id=browser.create(task);store.link(task.id,remote_id,-1);task=store.get(task.id)
        if task.pending=='status':browser.set_completed(task);sent.append(task)
        state('syncing',count=len(store.items()))
    browser.ready();remote,lists=browser.snapshot()
    for task in sent:
        confirmed=next((r for r in remote if r['remote_id']==task.remote_id and r['list_id']==task.list_id),None)
        if not confirmed or confirmed['completed']!=task.completed:raise UnsupportedTasksPage('server_did_not_confirm_change')
        store.acknowledge(task.id,task.revision)
    store.merge(remote,lists);AUTH.touch()
    state('ok',count=len(store.items()),pending=sum(bool(t.pending) for t in store.items()),updated_at=datetime.now(MOSCOW).isoformat())



def main(attach=False, login=False):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\StudyWidgetsGoogleTasksSync')
    if ctypes.get_last_error()==183:
        return 0
    try:
        if not attach and not login and not AUTH.exists() and not PROFILE.exists():
            state('login_required')
            return 0
        from playwright.sync_api import sync_playwright
        state('syncing')
        with sync_playwright() as driver:
            if login:
                login_and_sync(driver)
            elif attach:
                if not own_debugger_running():raise TemporaryTasksPage('setup_browser_not_ready')
                browser=driver.chromium.connect_over_cdp('http://127.0.0.1:18763',timeout=15000)
                try:
                    context=browser.contexts[0]
                    page=next((p for p in context.pages if urlsplit(p.url).hostname=='tasks.google.com'),None) or context.new_page()
                    state('syncing')
                    synchronize(page)
                finally:
                    try:
                        browser.close()  # Detach from an existing setup window.
                    except Exception:
                        pass
            else:
                sync_in_background(driver)
        return 0
    except GoogleLoginRequired as error:
        AUTH.unlink(missing_ok=True)
        state('login_required',reason=str(error))
        return 1
    except Exception as error:
        temporary=isinstance(error,(TemporaryTasksPage,BrowserError))
        state('unsupported' if isinstance(error,UnsupportedTasksPage) and not temporary else 'error',
              error=type(error).__name__,retryable=temporary,
              reason=str(error) if isinstance(error,UnsupportedTasksPage) else None)
        return 1
    finally:
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle(mutex)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--attach',action='store_true')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--login',action='store_true')
    args=parser.parse_args()
    sys.exit(main(args.attach,args.login))
