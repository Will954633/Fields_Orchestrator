#!/usr/bin/env python3
"""
Search-Based Sold Property Monitor
====================================
Replaces the per-property-page-visit approach (old step 103) with a search-results-based
detection method. Instead of opening 120+ individual Chrome pages, this loads 2-3 Domain
sold-listings search pages per suburb and cross-references listing IDs.

Also detects "Under Contract" / "Under Offer" status from the for-sale search pages.

Improvements over old monitor:
  - 97% fewer page loads (2-3 pages vs 120+)
  - Captures sale_method (private treaty / auction)
  - Captures agent name + agency from search cards
  - Detects under_contract / under_offer as intermediate state
  - CosmosDB 429 retry with backoff

Usage:
    python3 search_based_sold_monitor.py --suburbs "Robina:4226" "Varsity Lakes:4227" "Burleigh Waters:4220"
    python3 search_based_sold_monitor.py --all
    python3 search_based_sold_monitor.py --test
    python3 search_based_sold_monitor.py --report

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("ERROR: selenium not installed")
    sys.exit(1)

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

# Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast'
PAGE_LOAD_WAIT = 5
SCROLL_WAIT = 1.0
BETWEEN_PAGE_DELAY = 3
SOLD_PAGES_TO_CHECK = 3      # Check first N pages of sold results (~60 most recent)
FOR_SALE_PAGES_TO_CHECK = 5   # Check for-sale pages for under_contract detection

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

SUBURBS_JSON = os.path.join(
    os.path.dirname(__file__), '..', '..', 'Property_Data_Scraping',
    '03_Gold_Coast', 'Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold',
    'gold_coast_suburbs.json'
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_sold_date(text: str) -> Optional[str]:
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        return f"{year}-{MONTH_MAP[month_str]:02d}-{day:02d}"
    return None


def parse_sold_price(text: str) -> Optional[str]:
    m = re.search(r'\$[\d,]+', text)
    return m.group(0) if m else None


def parse_sale_method(text: str) -> Optional[str]:
    lower = text.lower()
    if "auction" in lower:
        return "auction"
    if "private treaty" in lower:
        return "private treaty"
    if "expression" in lower:
        return "expression of interest"
    return None


def parse_features(card) -> Dict:
    features = {}
    text = card.get_text(" ", strip=True)
    beds = re.search(r'(\d+)\s*Beds?', text, re.IGNORECASE)
    baths = re.search(r'(\d+)\s*Baths?', text, re.IGNORECASE)
    park = re.search(r'(\d+)\s*Parking', text, re.IGNORECASE)
    if beds: features["bedrooms"] = int(beds.group(1))
    if baths: features["bathrooms"] = int(baths.group(1))
    if park: features["parking"] = int(park.group(1))
    land = re.search(r'([\d,]+)\s*m²', text)
    if land:
        features["land_size"] = land.group(0)
        features["land_size_sqm"] = int(land.group(1).replace(",", ""))
    ptype = re.search(r'(House|Townhouse|Apartment|Unit|Villa|Duplex|Land|Studio|Acreage|Rural)\s*$', text, re.IGNORECASE)
    if ptype: features["property_type"] = ptype.group(1).title()
    return features


def extract_agent_from_card(card) -> Tuple[Optional[str], Optional[str]]:
    """Extract agent name and agency from a listing card."""
    text = card.get_text(" | ", strip=True)
    parts = text.split(" | ")
    agent_name = None
    agency_name = None
    # Agent/agency typically appear between the sold method line and the price
    for part in parts:
        part = part.strip()
        if not part or part.startswith("$") or part.startswith("Sold") or part.startswith("Price"):
            continue
        if re.match(r'^\d', part):  # address or number
            continue
        if part.isupper() and len(part) > 2:  # suburb (all caps)
            continue
        if re.match(r'^\d+\s*(Beds?|Baths?|Parking)', part, re.IGNORECASE):
            continue
        if re.search(r'm²|House|Townhouse|Apartment|Unit|Villa', part, re.IGNORECASE):
            continue
        # Likely agent or agency
        if not agent_name:
            agent_name = part
        elif not agency_name:
            agency_name = part
            break
    return agent_name, agency_name


def extract_listing_urls(html: str) -> List[Dict]:
    """Extract listing IDs and URLs from a search results page."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(attrs={"data-testid": re.compile(r'^listing-\d+$')})
    results = []
    for card in cards:
        testid = card.get("data-testid", "")
        listing_id = testid.replace("listing-", "")
        link = card.find("a", href=re.compile(r'-\d{7,10}$'))
        listing_url = None
        if link:
            href = link["href"]
            listing_url = href if href.startswith("http") else f"https://www.domain.com.au{href}"
        card_text = card.get_text(" ", strip=True)
        results.append({
            "listing_id": listing_id,
            "listing_url": listing_url,
            "card_text": card_text,
            "card": card,
        })
    return results


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def retry_db(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "16500" in err or "429" in err or "RequestRateTooLarge" in err:
                m = re.search(r'RetryAfterMs=(\d+)', err)
                wait = int(m.group(1)) / 1000.0 if m else (1.0 * (attempt + 1))
                time.sleep(min(wait, 5.0))
                continue
            raise
    return fn()


# ---------------------------------------------------------------------------
# Main monitor
# ---------------------------------------------------------------------------

class SearchBasedSoldMonitor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.driver = None
        conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or MONGODB_URI
        self.client = MongoClient(conn_str)
        self.db = self.client[DATABASE_NAME]
        self.client.admin.command("ping")
        print(f"  MongoDB connected — {DATABASE_NAME}")

    def setup_driver(self):
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-software-rasterizer")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--js-flags=--max-old-space-size=256")
        opts.add_argument("--window-size=1920,1080")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        svc = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=svc, options=opts)
        self.driver.set_page_load_timeout(60)
        print("  Chrome WebDriver ready (headless)")

    def quit_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def load_page(self, url: str) -> str:
        self.driver.get(url)
        time.sleep(PAGE_LOAD_WAIT)
        for _ in range(5):
            self.driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(SCROLL_WAIT)
        return self.driver.page_source

    # ------------------------------------------------------------------
    # Sold detection via search results
    # ------------------------------------------------------------------
    def get_recently_sold_from_domain(self, suburb_name: str, postcode: str) -> List[Dict]:
        """Fetch recently sold listings from Domain search results."""
        slug = suburb_name.lower().replace(" ", "-")
        base = f"https://www.domain.com.au/sold-listings/{slug}-qld-{postcode}/?ssubs=0"
        all_sold = []

        pages = SOLD_PAGES_TO_CHECK
        if self.test_mode:
            pages = 1

        for page_num in range(1, pages + 1):
            url = base if page_num == 1 else f"{base}&page={page_num}"
            print(f"  [SOLD] Page {page_num}: {url}")
            try:
                html = self.load_page(url)
                cards_data = extract_listing_urls(html)
                if not cards_data:
                    break
                print(f"    Found {len(cards_data)} listing cards")

                for cd in cards_data:
                    ct = cd["card_text"]
                    agent_name, agency_name = extract_agent_from_card(cd["card"])
                    rec = {
                        "listing_id": cd["listing_id"],
                        "listing_url": cd["listing_url"],
                        "sold_date": parse_sold_date(ct),
                        "sale_price": parse_sold_price(ct),
                        "sale_method": parse_sale_method(ct),
                        "agent_name": agent_name,
                        "agency_name": agency_name,
                        **parse_features(cd["card"]),
                    }
                    all_sold.append(rec)

                if page_num < pages:
                    time.sleep(BETWEEN_PAGE_DELAY)
            except Exception as e:
                print(f"    ERROR: {e}")
                break

        # Deduplicate by listing_id
        seen = set()
        unique = []
        for r in all_sold:
            lid = r.get("listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(r)
        return unique

    # ------------------------------------------------------------------
    # Under Contract detection via for-sale search results
    # ------------------------------------------------------------------
    def get_under_contract_from_domain(self, suburb_name: str, postcode: str) -> List[Dict]:
        """Fetch under-contract/under-offer listings from Domain for-sale search (including under offer)."""
        slug = suburb_name.lower().replace(" ", "-")
        # Domain for-sale page WITHOUT excludeunderoffer shows under-offer properties
        base = f"https://www.domain.com.au/sale/{slug}-qld-{postcode}/?ssubs=0"
        all_uc = []

        pages = FOR_SALE_PAGES_TO_CHECK
        if self.test_mode:
            pages = 1

        for page_num in range(1, pages + 1):
            url = base if page_num == 1 else f"{base}&page={page_num}"
            print(f"  [UC] Page {page_num}: {url}")
            try:
                html = self.load_page(url)
                cards_data = extract_listing_urls(html)
                if not cards_data:
                    break

                for cd in cards_data:
                    ct = cd["card_text"].lower()
                    # Detect under contract / under offer / deposit taken
                    is_uc = any(phrase in ct for phrase in [
                        "under contract", "under offer", "deposit taken",
                        "offer accepted", "conditional"
                    ])
                    if is_uc:
                        all_uc.append({
                            "listing_id": cd["listing_id"],
                            "listing_url": cd["listing_url"],
                            "card_text": cd["card_text"],
                        })

                if page_num < pages:
                    time.sleep(BETWEEN_PAGE_DELAY)
            except Exception as e:
                print(f"    ERROR: {e}")
                break

        # Deduplicate
        seen = set()
        unique = []
        for r in all_uc:
            lid = r.get("listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(r)
        return unique

    # ------------------------------------------------------------------
    # DB operations
    # ------------------------------------------------------------------
    def process_sold_for_suburb(self, suburb_name: str, postcode: str) -> Dict:
        """Cross-reference Domain sold listings with our for_sale records."""
        collection_name = suburb_name.lower().replace(" ", "_")
        collection = self.db[collection_name]

        # Get sold listings from Domain
        domain_sold = self.get_recently_sold_from_domain(suburb_name, postcode)
        print(f"  {suburb_name}: {len(domain_sold)} recently sold on Domain")

        # Get our active listings (include valuation fields for margin of error calc)
        our_active = list(retry_db(lambda: list(collection.find(
            {"listing_status": "for_sale"},
            {"listing_url": 1, "address": 1, "_id": 1, "price": 1,
             "domain_valuation_at_listing": 1, "scraped_data.valuation": 1}
        ))))
        print(f"  {suburb_name}: {len(our_active)} active for_sale in DB")

        # Build lookup by listing_id from URL
        active_by_lid = {}
        for doc in our_active:
            url = doc.get("listing_url", "")
            m = re.search(r'-(\d{7,10})$', url)
            if m:
                active_by_lid[m.group(1)] = doc

        stats = {"sold_detected": 0, "already_sold": 0, "not_in_db": 0, "errors": 0}
        now = datetime.utcnow().isoformat()

        for sold_rec in domain_sold:
            lid = sold_rec.get("listing_id")
            if not lid:
                continue

            if lid in active_by_lid:
                doc = active_by_lid[lid]
                # This property is in our DB as for_sale but Domain says it's sold
                update_fields = {
                    "listing_status": "sold",
                    "sold_date": sold_rec.get("sold_date"),
                    "sale_price": sold_rec.get("sale_price"),
                    "sale_method": sold_rec.get("sale_method"),
                    "selling_agent": sold_rec.get("agent_name"),
                    "selling_agency": sold_rec.get("agency_name"),
                    "detection_method": "search_results_cross_reference",
                    "sold_detection_date": now,
                    "last_updated": now,
                }
                # Preserve listing price
                update_fields["listing_price"] = doc.get("price")

                # Compute Domain valuation margin of error
                domain_val = (doc.get("domain_valuation_at_listing")
                              or doc.get("scraped_data", {}).get("valuation"))
                sale_price_str = sold_rec.get("sale_price")
                if domain_val and domain_val.get("mid") and sale_price_str:
                    try:
                        sale_price_num = int(re.sub(r'[^\d]', '', sale_price_str))
                        mid = domain_val["mid"]
                        low = domain_val.get("low")
                        high = domain_val.get("high")
                        error_dollars = sale_price_num - mid
                        error_pct = round((error_dollars / mid) * 100, 2)
                        within_range = (low and high
                                        and low <= sale_price_num <= high)
                        # Snapshot the valuation used for this calculation
                        if not doc.get("domain_valuation_at_listing"):
                            update_fields["domain_valuation_at_listing"] = {
                                **domain_val,
                                "captured_at": now,
                                "source": "scraped_data_snapshot_at_sold"
                            }
                        update_fields["domain_valuation_accuracy"] = {
                            "domain_mid": mid,
                            "domain_low": low,
                            "domain_high": high,
                            "sale_price": sale_price_num,
                            "error_dollars": error_dollars,
                            "error_pct": error_pct,
                            "within_range": bool(within_range),
                            "computed_at": now,
                        }
                        print(f"      Domain valuation accuracy: {error_pct:+.1f}% (${error_dollars:+,})")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

                # Remove None values
                update_fields = {k: v for k, v in update_fields.items() if v is not None}

                try:
                    retry_db(lambda: collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": update_fields}
                    ))
                    stats["sold_detected"] += 1
                    addr = doc.get("address", "N/A")[:50]
                    print(f"    SOLD: {addr} -> {sold_rec.get('sold_date')} {sold_rec.get('sale_price', 'withheld')}")
                except Exception as e:
                    stats["errors"] += 1
                    print(f"    ERROR updating {doc.get('address')}: {e}")
            else:
                # Check if already in DB as sold
                existing = retry_db(lambda: collection.find_one(
                    {"listing_url": {"$regex": f"-{lid}$"}, "listing_status": "sold"}
                ))
                if existing:
                    stats["already_sold"] += 1
                else:
                    stats["not_in_db"] += 1

        return stats

    def process_under_contract_for_suburb(self, suburb_name: str, postcode: str) -> Dict:
        """Detect and flag under-contract properties."""
        collection_name = suburb_name.lower().replace(" ", "_")
        collection = self.db[collection_name]

        uc_listings = self.get_under_contract_from_domain(suburb_name, postcode)
        print(f"  {suburb_name}: {len(uc_listings)} under contract/offer on Domain")

        # Get our active listings
        our_active = list(retry_db(lambda: list(collection.find(
            {"listing_status": "for_sale"},
            {"listing_url": 1, "address": 1, "_id": 1, "listing_status": 1}
        ))))

        active_by_lid = {}
        for doc in our_active:
            url = doc.get("listing_url", "")
            m = re.search(r'-(\d{7,10})$', url)
            if m:
                active_by_lid[m.group(1)] = doc

        stats = {"under_contract_detected": 0, "already_uc": 0, "not_in_db": 0}
        now = datetime.utcnow().isoformat()

        for uc_rec in uc_listings:
            lid = uc_rec.get("listing_id")
            if not lid:
                continue

            if lid in active_by_lid:
                doc = active_by_lid[lid]
                # Already marked?
                if doc.get("listing_status") == "under_contract":
                    stats["already_uc"] += 1
                    continue

                try:
                    retry_db(lambda: collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "listing_status": "under_contract",
                            "under_contract_detected_at": now,
                            "under_contract_source_text": uc_rec.get("card_text", "")[:200],
                            "last_updated": now,
                        }}
                    ))
                    stats["under_contract_detected"] += 1
                    addr = doc.get("address", "N/A")[:50]
                    print(f"    UNDER CONTRACT: {addr}")
                except Exception as e:
                    print(f"    ERROR: {e}")
            else:
                stats["not_in_db"] += 1

        return stats

    def run(self, suburbs: List[Tuple[str, str]]):
        """Main entry point."""
        print(f"\n{'='*70}")
        print(f"  Search-Based Sold Monitor")
        print(f"  Suburbs: {len(suburbs)}")
        print(f"{'='*70}")

        self.setup_driver()
        total_sold = {"sold_detected": 0, "already_sold": 0, "not_in_db": 0, "errors": 0}
        total_uc = {"under_contract_detected": 0, "already_uc": 0, "not_in_db": 0}

        try:
            for suburb_name, postcode in suburbs:
                print(f"\n--- {suburb_name} ({postcode}) ---")

                # Phase 1: Detect sold properties
                sold_stats = self.process_sold_for_suburb(suburb_name, postcode)
                for k in total_sold:
                    total_sold[k] += sold_stats.get(k, 0)

                # Phase 2: Detect under contract
                uc_stats = self.process_under_contract_for_suburb(suburb_name, postcode)
                for k in total_uc:
                    total_uc[k] += uc_stats.get(k, 0)

                print(f"  Results — sold: {sold_stats}, under_contract: {uc_stats}")

        finally:
            print(f"\n{'='*70}")
            print(f"  TOTALS")
            print(f"  Sold: {total_sold}")
            print(f"  Under Contract: {total_uc}")
            print(f"{'='*70}")
            self.quit_driver()

        return total_sold, total_uc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_suburbs_from_json() -> List[Tuple[str, str]]:
    path = SUBURBS_JSON
    if not os.path.exists(path):
        # Fallback path
        path = os.path.join(
            '/home/fields/Property_Data_Scraping/03_Gold_Coast',
            'Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold',
            'gold_coast_suburbs.json'
        )
    with open(path) as f:
        data = json.load(f)
    return [(s['name'], s['postcode']) for s in data['suburbs']]


def main():
    parser = argparse.ArgumentParser(description="Search-based sold property monitor")
    parser.add_argument('--suburbs', nargs='+', help='Suburbs as "Name:postcode"')
    parser.add_argument('--all', action='store_true', help='All 52 suburbs')
    parser.add_argument('--test', action='store_true', help='Test mode (1 page per suburb)')
    parser.add_argument('--report', action='store_true', help='Print sold report')
    parser.add_argument('--max-concurrent', type=int, default=1, help='(kept for CLI compat, not used)')
    parser.add_argument('--parallel-properties', type=int, default=1, help='(kept for CLI compat, not used)')
    args = parser.parse_args()

    # Monitor client for ops dashboard
    _process_id = "104" if args.all else "103"
    _pipeline = "orchestrator_weekly" if args.all else "orchestrator_daily"
    monitor = MonitorClient(
        system="orchestrator", pipeline=_pipeline,
        process_id=_process_id, process_name="Monitor Sold Properties (Search-Based)"
    ) if _MONITOR_AVAILABLE else None
    if monitor:
        monitor.start()

    if args.report:
        conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or MONGODB_URI
        client = MongoClient(conn_str)
        db = client[DATABASE_NAME]
        print(f"\n{'='*70}\nSOLD PROPERTIES REPORT\n{'='*70}")
        collections = [c for c in db.list_collection_names()
                       if not c.startswith('system.') and c not in (
                           'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots')]
        total = 0
        for coll_name in sorted(collections):
            count = db[coll_name].count_documents({"listing_status": "sold"})
            uc_count = db[coll_name].count_documents({"listing_status": "under_contract"})
            if count > 0 or uc_count > 0:
                print(f"  {coll_name:30s}  sold={count}  under_contract={uc_count}")
                total += count
        print(f"\nTotal sold: {total}\n{'='*70}")
        client.close()
        return

    # Parse suburbs
    if args.suburbs:
        suburbs = []
        for s in args.suburbs:
            name, postcode = s.split(":")
            suburbs.append((name.strip(), postcode.strip()))
    elif args.all:
        suburbs = load_suburbs_from_json()
    elif args.test:
        suburbs = [("Robina", "4226"), ("Varsity Lakes", "4227"), ("Burleigh Waters", "4220")]
    else:
        # Default: target market
        suburbs = [("Robina", "4226"), ("Varsity Lakes", "4227"), ("Burleigh Waters", "4220")]

    scraper = SearchBasedSoldMonitor(test_mode=args.test)
    sold_stats, uc_stats = scraper.run(suburbs)

    if monitor:
        monitor.complete(details={
            "sold": sold_stats,
            "under_contract": uc_stats,
        })


if __name__ == "__main__":
    main()
