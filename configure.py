"""Configure your own calendar and Google account without secrets in shell history."""
from getpass import getpass
import importlib.util
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit


def write_json(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    spec=importlib.util.spec_from_file_location('schedule_paths',Path(__file__).parent/'schedule/app_paths.py')
    paths=importlib.util.module_from_spec(spec);spec.loader.exec_module(paths)
    config_path=paths.ROOT/'config.json'
    try:config=json.loads(config_path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):config={}
    if not isinstance(config,dict):config={}
    url=getpass('Google Calendar secret iCal URL (blank: keep current): ').strip()
    if url:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname!='calendar.google.com' or not parsed.path.endswith('.ics'):
            raise SystemExit('Expected an HTTPS iCal URL from Google Calendar.')
        config['feed_url']=url
    if 'feed_url' not in config:config['feed_url']=''
    config.setdefault('refresh_seconds',120)
    write_json(config_path,config)
    email=input('Google Tasks account email (blank: keep current): ').strip()
    if email:
        if '@' not in email or '\n' in email:raise SystemExit('Invalid email.')
        write_json(paths.ROOT/'google-tasks-account.json',{'email':email})
    print('Saved locally. Open Schedule, then connect Google Tasks or LMS SHAD in its sidebar.')


if __name__=='__main__':main()
