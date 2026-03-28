#!/usr/bin/env python3
"""
refresh_absorption_snapshots.py — Delete current month's absorption rate snapshots
so the next API request recomputes them from fresh data.

Run on the 1st of each month AFTER the nightly pipeline completes.
Cron: 0 22 1 * * (10 PM AEST on the 1st — after 20:30 pipeline)

The market-insights.mjs Netlify function will recompute and store new
snapshots on the next request for each suburb.
"""

import sys
import os
from datetime import datetime

# Add parent for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import get_client

def main():
    client = get_client()
    db = client['system_monitor']
    collection = db['absorption_rate_snapshots']

    # Current month in AEST
    now = datetime.utcnow()
    # UTC+10 for AEST
    aest_hour = now.hour + 10
    aest_day = now.day
    aest_month = now.month
    aest_year = now.year
    if aest_hour >= 24:
        aest_day += 1
        aest_hour -= 24
        # Simplified — good enough for month boundary
        if aest_day > 28:
            import calendar
            max_day = calendar.monthrange(aest_year, aest_month)[1]
            if aest_day > max_day:
                aest_day = 1
                aest_month += 1
                if aest_month > 12:
                    aest_month = 1
                    aest_year += 1

    current_month = f"{aest_year}-{aest_month:02d}"
    print(f"Deleting absorption rate snapshots for month: {current_month}")

    result = collection.delete_many({"month": current_month})
    print(f"Deleted {result.deleted_count} snapshot(s)")
    print("Next API request for each suburb will recompute fresh values.")

    client.close()

if __name__ == '__main__':
    main()
