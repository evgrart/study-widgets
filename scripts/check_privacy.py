"""Scan all tracked text and optionally every Git blob before publication."""
from pathlib import Path
import argparse,re,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
BAD_NAMES=re.compile(r'(^|/)(?:[^/]*-profile|backups|browser_vendor|vendor|\.venv)(?:/|$)|'
    r'(?:\.sqlite3(?:-wal|-shm)?|\.db|\.log|\.bmp|\.exe|\.dll|\.lnk)$|'
    r'(?:^|/)(?:config\.json|status\.json|google-tasks-account\.json|shad-deadlines\.json|tasks_plan\.json)$',re.I)
BAD_TEXT=[
    re.compile(rb'private-[0-9a-f]{16,}',re.I),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'[A-Z]:[\\/]+Users[\\/]+(?!Public\b|example\b)[^\s"\']+',re.I),
    re.compile(rb'https://lk\.dataschool\.yandex\.ru/users/[^\s"\']+/classes\.ics'),
]
EMAIL=re.compile(rb'[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})')

def public_commit_email(value):
    value=value.lower()
    return value==b'noreply@github.com' or value.endswith(b'@users.noreply.github.com')


def check(path,data):
    issues=[]
    if BAD_NAMES.search(path):issues.append('runtime/binary file')
    if path.endswith('.ico'):return issues
    if any(pattern.search(data) for pattern in BAD_TEXT):issues.append('private credential/path pattern')
    if any(not public_commit_email(match[0]) and match[1].lower() not in (b'example.test',b'example.com') for match in EMAIL.finditer(data)):
        issues.append('non-example email address')
    return issues

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--history',action='store_true');args=parser.parse_args()
    problems=[];count=0
    tracked=git('ls-files','-z').decode().split('\0')
    for name in filter(None,tracked):
        count+=1
        issues=check(name,(ROOT/name).read_bytes())
        if issues:problems.append((name,issues))
    if args.history:
        for line in git('rev-list','--objects','--all').decode().splitlines():
            oid,_,path=line.partition(' ')
            if not path or git('cat-file','-t',oid).strip()!=b'blob':continue
            issues=check(path,git('cat-file','blob',oid))
            if issues:problems.append(('history:'+path,issues))
            count+=1
        for line in git('log','--all','--format=%ae%n%ce').splitlines():
            if not public_commit_email(line):problems.append(('commit metadata',['non-private author email required']))
    for path,issues in problems:print(path+': '+', '.join(issues))
    if problems:raise SystemExit(1)
    print(f'Privacy check passed: {count} files/blobs inspected.')

if __name__=='__main__':main()
