#!/usr/bin/env python3
import os, sys, subprocess

log = open('/home/projects/scraper/scraper.log', 'a', buffering=1)
os.chdir('/home/projects/scraper')
os.environ['PYTHONUNBUFFERED'] = '1'

p = subprocess.Popen(
    ['/home/projects/scraper/venv/bin/python3', '-u', 'url_tracking_run.py'],
    stdout=log, stderr=log,
    close_fds=True,
    start_new_session=True,
)
with open('/home/projects/scraper/scraper.pid', 'w') as f:
    f.write(str(p.pid))
print(f'Started PID={p.pid}')
