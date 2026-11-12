"""Run only isolated tests, with disposable state and no account access."""
from pathlib import Path
import argparse,os,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[1]
TESTS={
    'study':['verify_timer','verify_stats','verify_sleep','verify_sleep_days','verify_sleep_stats',
             'verify_days_off','verify_sleepless','verify_naps','verify_category_clear'],
    'schedule':['verify_widget','verify_deadlines','verify_tasks','verify_tasks_headless','verify_tasks_login'],
}
GUI={'study':['verify_gui.py','verify_selected_day.py','verify_category_clear_gui.py',
              'verify_sleepless_gui.py','verify_naps_gui.py'],
     'schedule':['verify_tasks_pagination.py','verify_tasks_speed.py','verify_public_gui.py']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--gui',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='widgets-tests-') as folder:
        env=dict(os.environ,STUDY_WIDGET_DATA_DIR=str(Path(folder)/'study'),
                 SCHEDULE_WIDGET_DATA_DIR=str(Path(folder)/'schedule'),PYTHONUTF8='1')
        for app,modules in TESTS.items():
            subprocess.run([sys.executable,'-m','unittest',*modules],cwd=ROOT/app,env=env,check=True)
        if args.gui:
            for app,files in GUI.items():
                for filename in files:subprocess.run([sys.executable,filename],cwd=ROOT/app,env=env,check=True)
    print('Isolated tests passed.')

if __name__=='__main__':main()
