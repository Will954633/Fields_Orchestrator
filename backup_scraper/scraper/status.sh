#!/bin/bash
SCRAPER_ROOT="/home/projects/scraper"
echo "============================================"
echo "SCRAPER STATUS"
echo "============================================"
if pgrep -f url_tracking_run.py > /dev/null; then
    echo "✅ RUNNING  PID:" $(pgrep -f url_tracking_run.py)
else
    echo "❌ NOT RUNNING"
fi
echo ""
echo "Last 20 log lines:"
tail -20 "$SCRAPER_ROOT/scraper.log" 2>/dev/null || echo "No log found at $SCRAPER_ROOT/scraper.log"
echo ""
echo "Last cycle summary:"
grep -E "\[Pass.*done\]|new URLs|Cycle" "$SCRAPER_ROOT/scraper.log" 2>/dev/null | tail -5
echo "============================================"
