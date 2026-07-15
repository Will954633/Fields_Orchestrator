#!/bin/bash
# Wait for network to be ready
sleep 15
cd /home/projects/scraper
export PYTHONUNBUFFERED=1
exec /home/projects/scraper/venv/bin/python3 -u url_tracking_run.py >> /home/projects/scraper/scraper.log 2>&1
