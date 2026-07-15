#!/bin/bash
pkill -f url_tracking_run.py && echo '✅ Scraper stopped' && rm -f ~/scraper/scraper.pid
