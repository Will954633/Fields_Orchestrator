#!/usr/bin/env python3
"""
Coverage Check Script - Domain vs Database Listing Count Comparison
Created: 2026-02-25

For each suburb in gold_coast_suburbs.json, fetches the current for-sale property count
from Domain.com.au and compares it to the count in Gold_Coast_Currently_For_Sale.
Logs a WARNING when counts differ so scraping gaps are easy to spot.

Log file: /home/fields/Fields_Orchestrator/logs/coverage_check.log
  - Appended every run, never overwritten
  - One line per suburb per run — easy to grep

USAGE:
  python3 scripts/coverage_check.py                          # Check all suburbs in gold_coast_suburbs.json
  python3 scripts/coverage_check.py --suburbs "Robina:4226"  # Check specific suburb(s)
  python3 scripts/coverage_check.py --no-fail                # Exit 0 even when gaps found (orchestrator use)
"""

import os
import sys
import json
import time
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pymongo import MongoClient

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Paths
SUBURBS_JSON = Path(__file__).parent.parent.parent / (
    "Property_Data_Scraping/03_Gold_Coast/"
    "Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/gold_coast_suburbs.json"
)
LOG_FILE = Path(__file__).parent.parent / "logs" / "coverage_check.log"

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast'

# How long to wait for Domain page to load before reading content
PAGE_LOAD_WAIT = 8

# Domain URL template — swap in suburb slug (e.g. "robina-qld-4226")
DOMAIN_URL_TEMPLATE = "https://www.domain.com.au/sale/{slug}/?excludeunderoffer=1&ssubs=0"

# data-testid for the count element: <h1 data-testid="summary">...<strong>54 Properties</strong>...
COUNT_PATTERN = re.compile(r'<strong[^>]*>\s*(\d+)\s+Propert', re.IGNORECASE)


def load_suburbs_from_json(path: Path) -> List[Dict]:
    """Load suburb list from gold_coast_suburbs.json."""
    try:
        with open(path) as f:
            data = json.load(f)
        suburbs = data.get('suburbs', [])
        if not suburbs:
            print(f"WARNING: No suburbs found in {path}")
        return suburbs
    except Exception as e:
        print(f"ERROR: Failed to load suburbs from {path}: {e}")
        return []


def parse_suburbs_arg(arg: str) -> List[Dict]:
    """Parse --suburbs 'Name:postcode,...' into suburb dicts."""
    suburbs = []
    for part in arg.split(','):
        part = part.strip()
        if ':' in part:
            name, postcode = part.split(':', 1)
            name = name.strip()
            postcode = postcode.strip()
            slug = f"{name.lower().replace(' ', '-')}-qld-{postcode}"
            suburbs.append({'name': name, 'postcode': postcode, 'slug': slug})
        else:
            print(f"WARNING: Skipping malformed suburb arg '{part}' (expected Name:postcode)")
    return suburbs


def setup_driver(max_retries=3) -> webdriver.Chrome:
    """Create headless Chrome WebDriver with retry logic."""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-extensions')
    options.add_argument('--window-size=1280,800')
    service = Service('/usr/bin/chromedriver')
    for attempt in range(1, max_retries + 1):
        try:
            return webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"  WebDriver creation failed (attempt {attempt}/{max_retries}): {e}", flush=True)
            # Kill any zombie Chrome processes
            import subprocess as _sp
            for _pat in ['chromedriver', 'chrome_crashpad', 'chrome']:
                _sp.run(['pkill', '-9', '-f', _pat], capture_output=True, timeout=5)
            time.sleep(5)
            if attempt == max_retries:
                raise


def fetch_domain_count(driver: webdriver.Chrome, suburb: Dict) -> Optional[int]:
    """
    Fetch the for-sale property count from Domain for a given suburb.
    Returns the integer count, or None on failure.
    """
    slug = suburb.get('slug', '')
    url = DOMAIN_URL_TEMPLATE.format(slug=slug)
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(PAGE_LOAD_WAIT)
        html = driver.page_source
        match = COUNT_PATTERN.search(html)
        if match:
            return int(match.group(1))
        # Fallback: look for data-testid="summary"
        summary_match = re.search(
            r'data-testid="summary"[^>]*>.*?<strong[^>]*>(\d+)\s+Propert',
            html, re.IGNORECASE | re.DOTALL
        )
        if summary_match:
            return int(summary_match.group(1))
        print(f"  WARNING: Could not extract count from Domain page for {suburb['name']} ({url})")
        return None
    except TimeoutException:
        print(f"  WARNING: Timeout loading Domain page for {suburb['name']}")
        return None
    except WebDriverException as e:
        print(f"  WARNING: WebDriver error for {suburb['name']}: {e}")
        return None


def get_db_count(db, suburb: Dict) -> int:
    """Count active for-sale documents in the suburb's collection."""
    collection_name = suburb['name'].lower().replace(' ', '_').replace('-', '_')
    try:
        collection = db[collection_name]
        return collection.count_documents({"listing_status": "for_sale"})
    except Exception as e:
        print(f"  WARNING: Failed to count DB docs for {suburb['name']}: {e}")
        return -1


def get_db_sold_count(db, suburb: Dict, days: int = 30) -> int:
    """Count sold documents in the last N days."""
    collection_name = suburb['name'].lower().replace(' ', '_').replace('-', '_')
    cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime('%Y-%m-%d')
    try:
        collection = db[collection_name]
        return collection.count_documents({
            "listing_status": "sold",
            "sold_date": {"$gte": cutoff}
        })
    except Exception:
        return -1


def fetch_domain_sold_count(driver: webdriver.Chrome, suburb: Dict) -> Optional[int]:
    """Fetch the sold property count from Domain for a given suburb (last 30 days approx)."""
    slug = suburb.get('slug', '')
    url = f"https://www.domain.com.au/sold-listings/{slug}/?ssubs=0"
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(PAGE_LOAD_WAIT)
        html = driver.page_source
        # Domain sold page H1: "5571 Properties sold in Robina, QLD, 4226"
        match = re.search(r'(\d+)\s+Propert\w+\s*sold\s+in', html, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    except Exception:
        return None


def write_log(lines: List[str]):
    """Append lines to the persistent coverage_check.log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        for line in lines:
            f.write(line + '\n')


def main():
    parser = argparse.ArgumentParser(
        description='Check Domain for-sale counts vs database counts per suburb',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/coverage_check.py
  python3 scripts/coverage_check.py --suburbs "Robina:4226,Varsity Lakes:4227"
  python3 scripts/coverage_check.py --no-fail
        """
    )
    parser.add_argument('--suburbs', type=str, help='Comma-separated Name:postcode pairs to check')
    parser.add_argument('--no-fail', action='store_true',
                        help='Exit 0 even when coverage gaps found (for orchestrator integration)')
    args = parser.parse_args()

    if not SELENIUM_AVAILABLE:
        print("ERROR: Selenium not installed. Cannot fetch Domain counts.")
        sys.exit(1)

    # Load suburb list
    if args.suburbs:
        suburbs = parse_suburbs_arg(args.suburbs)
    else:
        suburbs = load_suburbs_from_json(SUBURBS_JSON)

    if not suburbs:
        print("ERROR: No suburbs to check.")
        sys.exit(1)

    run_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'=' * 70}")
    print(f"COVERAGE CHECK")
    print(f"{'=' * 70}")
    print(f"Timestamp: {run_ts}")
    print(f"Suburbs to check: {len(suburbs)}")
    print(f"Log file: {LOG_FILE}")
    print(f"{'=' * 70}\n")

    # Connect to MongoDB
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000, tlsAllowInvalidCertificates=True)
        client.admin.command('ping')
        db = client[DATABASE_NAME]
        print("MongoDB connected.\n")
    except Exception as e:
        print(f"ERROR: MongoDB connection failed: {e}")
        sys.exit(1)

    # Setup Chrome
    try:
        driver = setup_driver()
        print("Chrome WebDriver ready.\n")
    except Exception as e:
        print(f"ERROR: Failed to start Chrome WebDriver: {e}")
        client.close()
        sys.exit(1)

    results = []
    gaps_found = 0

    try:
        for suburb in suburbs:
            name = suburb.get('name', 'Unknown')
            print(f"Checking {name}...", flush=True)

            domain_count = fetch_domain_count(driver, suburb)
            db_count = get_db_count(db, suburb)

            if domain_count is None:
                status = 'DOMAIN_UNAVAILABLE'
                flag = 'WARN'
                diff = None
                diff_str = 'N/A'
            elif db_count < 0:
                status = 'DB_ERROR'
                flag = 'WARN'
                diff = None
                diff_str = 'N/A'
            elif domain_count == db_count:
                status = 'OK'
                flag = 'OK'
                diff = 0
                diff_str = '0'
            else:
                diff = db_count - domain_count  # negative = we have fewer than Domain
                status = 'GAP'
                flag = 'ERROR'
                gaps_found += 1
                diff_str = str(diff)

            results.append({
                'suburb': name,
                'domain_count': domain_count,
                'db_count': db_count,
                'diff': diff,
                'status': status,
            })

            # Console output
            if flag == 'OK':
                print(f"  OK     Domain={domain_count}  DB={db_count}")
            elif flag == 'WARN':
                print(f"  WARN   Domain={domain_count}  DB={db_count}  ({status})")
            else:
                missing = domain_count - db_count if domain_count and db_count >= 0 else '?'
                print(f"  ERROR  Domain={domain_count}  DB={db_count}  (missing {missing} properties)")

        # --- SOLD COVERAGE CHECK ---
        print(f"\n{'=' * 70}")
        print(f"SOLD COVERAGE CHECK (last 30 days)")
        print(f"{'=' * 70}\n")
        sold_results = []
        for suburb in suburbs:
            name = suburb.get('name', 'Unknown')
            db_sold = get_db_sold_count(db, suburb, days=30)
            print(f"  {name:30s}  DB sold (30d): {db_sold}")
            sold_results.append({'suburb': name, 'db_sold_30d': db_sold})

        # Write results to system_monitor.data_integrity for OPS dashboard
        try:
            monitor_db = client["system_monitor"]
            di_col = monitor_db["data_integrity"]
            now_utc = datetime.utcnow()
            for r in results:
                suburb_key = r['suburb'].lower().replace(' ', '_')
                domain_ct = r.get('domain_count') or 0
                db_ct = r.get('db_count') or 0

                # Determine status for OPS dashboard
                if r['status'] == 'OK':
                    di_status = 'ok'
                elif r['status'] == 'GAP' and db_ct < domain_ct:
                    di_status = 'critical'  # Missing listings
                elif r['status'] == 'GAP' and db_ct > domain_ct:
                    di_status = 'ok'  # We have more than Domain — not a problem
                else:
                    di_status = 'warning'

                # Count enriched properties (with valuation_data)
                enriched = 0
                try:
                    enriched = db.get_collection(suburb_key).count_documents({"valuation_data": {"$exists": True}})
                except Exception:
                    pass

                di_col.update_one(
                    {"_id": suburb_key},
                    {"$set": {
                        "check_name": f"coverage_{suburb_key}",
                        "check_type": "data_coverage",
                        "suburb": suburb_key,
                        "status": di_status,
                        "checked_at": now_utc,
                        "db_count": db_ct,
                        "enriched_count": enriched,
                        "enrichment_ratio": round(enriched / db_ct, 3) if db_ct > 0 else 0,
                        "total_listings": db_ct,
                        "domain_count": domain_ct,
                        "last_updated": now_utc,
                        "last_listing_update": now_utc,
                        "coverage": {
                            "valuation": {
                                "count": enriched,
                                "ratio": round(enriched / db_ct, 3) if db_ct > 0 else None,
                                "status": "ok" if (db_ct > 0 and enriched / db_ct >= 0.7) else ("critical" if db_ct > 0 else "unknown"),
                            },
                        },
                    }},
                    upsert=True,
                )
            print(f"\nWrote {len(results)} records to system_monitor.data_integrity")
        except Exception as e:
            print(f"WARNING: Failed to write data_integrity: {e}")

    finally:
        driver.quit()
        client.close()

    # Print summary
    print(f"\n{'=' * 70}")
    print(f"COVERAGE CHECK SUMMARY")
    print(f"{'=' * 70}")
    print(f"Suburbs checked: {len(results)}")
    print(f"Coverage gaps:   {gaps_found}")
    if gaps_found:
        print(f"\nSUBURBS WITH GAPS:")
        for r in results:
            if r['status'] == 'GAP':
                missing = r['domain_count'] - r['db_count']
                print(f"  {r['suburb']:30s}  Domain={r['domain_count']}  DB={r['db_count']}  missing={missing}")
    else:
        print("No coverage gaps detected.")
    print(f"{'=' * 70}\n")
    print(f"Full log appended to: {LOG_FILE}")

    # Write to persistent log file
    log_lines = []
    log_lines.append(f"")
    log_lines.append(f"{'=' * 70}")
    log_lines.append(f"COVERAGE CHECK RUN: {run_ts}")
    log_lines.append(f"{'=' * 70}")
    for r in results:
        if r['status'] == 'OK':
            log_lines.append(
                f"[OK   ] {run_ts}  {r['suburb']:30s}  Domain={r['domain_count']}  DB={r['db_count']}"
            )
        elif r['status'] == 'GAP':
            missing = r['domain_count'] - r['db_count']
            log_lines.append(
                f"[ERROR] {run_ts}  {r['suburb']:30s}  Domain={r['domain_count']}  DB={r['db_count']}  MISSING={missing}"
            )
        else:
            log_lines.append(
                f"[WARN ] {run_ts}  {r['suburb']:30s}  Domain={r['domain_count']}  DB={r['db_count']}  STATUS={r['status']}"
            )
    log_lines.append(f"TOTAL: {len(results)} suburbs checked, {gaps_found} gap(s) found")
    log_lines.append(f"{'=' * 70}")
    write_log(log_lines)

    # Exit code
    if args.no_fail:
        sys.exit(0)
    else:
        sys.exit(1 if gaps_found else 0)


if __name__ == '__main__':
    main()
