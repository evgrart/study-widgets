"""Bounded Google Tasks synchronizer, safe to run with the widget closed."""
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time
from shad_background import OwnProcessJob
from deadline_core import atomic_json, read_json, MOSCOW

from app_paths import ROOT, CODE_ROOT
STATUS = ROOT/'google-tasks-status.json'


def run():
    job, process, result, terminal = None, None, 1, None
    try:
        job = OwnProcessJob()
        process = subprocess.Popen([str(Path(sys.executable).with_name('python.exe')),
            str(CODE_ROOT/'tasks_browser.py'), '--once'], cwd=str(ROOT), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        job.assign(process)
        started = time.monotonic()
        while time.monotonic()-started < 150:
            if process.poll() is not None:
                result = process.returncode
                break
            status = read_json(STATUS, {})
            if status.get('pid')==process.pid and status.get('state') in {'ok','login_required','error','unsupported'}:
                terminal = terminal or time.monotonic()
                if time.monotonic()-terminal>10:
                    result = 0 if status['state'] in {'ok','login_required'} else 1
                    break
            time.sleep(.25)
        else:
            atomic_json(STATUS, {'state':'error','error':'background_timeout','checked_at':datetime.now(MOSCOW).isoformat()})
    except Exception as error:
        atomic_json(STATUS, {'state':'error','error':type(error).__name__,'checked_at':datetime.now(MOSCOW).isoformat()})
    finally:
        if job:
            job.close()
        if process:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                result = 1
        atomic_json(ROOT/'google-tasks-background-last-run.json',
                    {'finished_at':datetime.now(MOSCOW).isoformat(),'result':result})
    return result


if __name__=='__main__':
    sys.exit(run())
