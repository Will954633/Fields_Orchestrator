#!/bin/bash
exec 1>/home/projects/scraper/scraper.log
exec 2>&1
cd /home/projects/scraper
export PYTHONUNBUFFERED=1
exec /home/projects/scraper/venv/bin/python3 -u url_tracking_run.py
