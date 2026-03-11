#!/usr/bin/env python3
"""
Scrape Recently Sold Properties from Domain.com.au
===================================================
Scrapes the sold-listings search results for target suburbs and updates
the Gold_Coast database with sold records from the last N days.

Uses curl_cffi with Chrome impersonation (no Selenium/Chrome needed).

Usage:
    python3 scripts/scrape_recent_sold.py                     # Default: 3 suburbs, last 60 days
    python3 scripts/scrape_recent_sold.py --days 90           # Last 90 days
    python3 scripts/scrape_recent_sold.py --suburb robina     # Single suburb
    python3 scripts/scrape_recent_sold.py --dry-run           # Preview only, no DB writes
    python3 scripts/scrape_recent_sold.py --verbose           # Extra logging

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    pip install curl_cffi
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
from bs4 import BeautifulSoup

try:
    from curl_cffi.requests import Session
except ImportError:
    print("ERROR: curl_cffi not installed. pip install curl_cffi")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TARGET_SUBURBS = [
    {"name": "Robina", "postcode": "4226", "collection": "robina"},
    {"name": "Varsity Lakes", "postcode": "4227", "collection": "varsity_lakes"},
    {"name": "Burleigh Waters", "postcode": "4220", "collection": "burleigh_waters"},
]

DATABASE_NAME = "Gold_Coast"
MAX_PAGES = 15          # Safety cap per suburb
BETWEEN_PAGE_DELAY = 3  # Seconds between search result pages
HTTP_RETRIES = 3        # Number of HTTP fetch attempts
HTTP_RETRY_DELAY = 5    # Seconds between HTTP retries

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_sold_date(text: str) -> Optional[str]:
    """Parse sold date from card text like 'Sold by private treaty 06 Mar 2026'.
    Returns ISO date string YYYY-MM-DD or None."""
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP[m.group(2).lower()[:3]]
        year = int(m.group(3))
        return f"{year}-{month:02d}-{day:02d}"
    return None


def parse_sold_price(text: str) -> Optional[str]:
    """Extract sold price like '$1,877,000' from card text. Returns string or None."""
    m = re.search(r'\$[\d,]+', text)
    if m:
        return m.group(0)
    return None


def parse_sold_method(text: str) -> Optional[str]:
    """Extract sale method from card text."""
    lower = text.lower()
    if "auction" in lower:
        return "auction"
    if "private treaty" in lower:
        return "private treaty"
    if "expression" in lower:
        return "expression of interest"
    return None


def parse_features(card) -> Dict:
    """Extract beds, baths, parking, land size, property type from listing card."""
    features = {}
    text = card.get_text(" ", strip=True)

    # Beds / Baths / Parking  — pattern: "3 Beds 2 Baths 2 Parking"
    beds_m = re.search(r'(\d+)\s*Beds?', text, re.IGNORECASE)
    baths_m = re.search(r'(\d+)\s*Baths?', text, re.IGNORECASE)
    park_m = re.search(r'(\d+)\s*Parking', text, re.IGNORECASE)
    if beds_m:
        features["bedrooms"] = int(beds_m.group(1))
    if baths_m:
        features["bathrooms"] = int(baths_m.group(1))
    if park_m:
        features["parking"] = int(park_m.group(1))

    # Land size — "568m²"
    land_m = re.search(r'([\d,]+)\s*m²', text)
    if land_m:
        features["land_size"] = land_m.group(0)
        features["land_size_sqm"] = int(land_m.group(1).replace(",", ""))

    # Property type — last word-like token (House, Townhouse, Apartment, Unit, etc.)
    type_m = re.search(r'(House|Townhouse|Apartment|Unit|Villa|Duplex|Land|Studio|Acreage|Rural)\s*$', text, re.IGNORECASE)
    if type_m:
        features["property_type"] = type_m.group(1).title()

    return features


def normalize_address(address: str) -> str:
    """Normalize address for matching."""
    if not address:
        return ""
    n = address.upper().replace(",", "").replace(".", "").strip()
    n = re.sub(r'\s+', ' ', n)
    # Normalize unit separator
    n = re.sub(r'^(\d+)\s+(\d+)\s+', r'\1/\2 ', n)
    n = re.sub(r'\bUNIT\s+', '', n)
    n = re.sub(r'\bSTREET\b', 'ST', n)
    n = re.sub(r'\bROAD\b', 'RD', n)
    n = re.sub(r'\bDRIVE\b', 'DR', n)
    n = re.sub(r'\bAVENUE\b', 'AVE', n)
    n = re.sub(r'\bCOURT\b', 'CT', n)
    n = re.sub(r'\bPARADE\b', 'PDE', n)
    n = re.sub(r'\bCRESCENT\b', 'CRES', n)
    n = re.sub(r'\bCIRCUIT\b', 'CCT', n)
    n = re.sub(r'\bPLACE\b', 'PL', n)
    n = re.sub(r'\bCLOSE\b', 'CL', n)
    return n


def extract_address_from_card(card) -> Optional[str]:
    """Extract the street address + suburb from a listing card."""
    text = card.get_text(" | ", strip=True)
    # Pattern: after price, before Beds — "18 Anglesea Court | , | ROBINA"
    # or "<address> | , | <SUBURB>"
    parts = text.split(" | ")
    # Find the parts that look like an address
    for i, part in enumerate(parts):
        part = part.strip()
        # Skip sold method, price, agent, property type, features
        if re.match(r'^(Sold |Price |\$|Beds|Baths|Parking|\d+m²)', part, re.IGNORECASE):
            continue
        # Address typically starts with a number or unit
        if re.match(r'^\d', part) and len(part) > 5:
            # Next part might be ", SUBURB"
            suburb = None
            for j in range(i+1, min(i+3, len(parts))):
                candidate = parts[j].strip().strip(",").strip()
                if candidate and candidate.isupper() and len(candidate) > 2 and not candidate.isdigit():
                    suburb = candidate.title()
                    break
            if suburb:
                return f"{part}, {suburb}"
            return part
    return None


def extract_address_from_url(url: str, suburb_name: str, postcode: str) -> str:
    """Fallback: extract address from Domain URL slug."""
    path = url.replace("https://www.domain.com.au/", "")
    path = re.sub(r'-\d{7,10}$', '', path)
    parts = path.split("-")

    # Find state marker
    for i, part in enumerate(parts):
        if part == "qld":
            suburb_start = max(0, i - len(suburb_name.lower().split()))
            street_parts = parts[:suburb_start]
            street = " ".join(street_parts).title()
            return f"{street}, {suburb_name}, QLD {postcode}"

    return " ".join(parts).title()


def extract_listing_id(url: str) -> Optional[str]:
    """Extract Domain listing ID from URL."""
    m = re.search(r'-(\d{7,10})$', url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class RecentSoldScraper:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.session = None
        self.db = None

        # Connect to MongoDB
        conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
        if not conn_str:
            print("ERROR: COSMOS_CONNECTION_STRING not set")
            sys.exit(1)
        self.mongo_client = MongoClient(conn_str)
        self.db = self.mongo_client[DATABASE_NAME]
        self.mongo_client.admin.command("ping")
        print(f"  MongoDB connected — database: {DATABASE_NAME}")

    def setup_session(self):
        """Create a curl_cffi session with Chrome impersonation."""
        self.session = Session(impersonate="chrome120")
        print("  HTTP session ready (curl_cffi, chrome120 impersonation)", flush=True)

    def close_session(self):
        """Close the HTTP session."""
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None

    def fetch_page(self, url: str) -> str:
        """Fetch a URL with retry logic. Returns HTML string."""
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 429:
                    wait = HTTP_RETRY_DELAY * attempt
                    print(f"    Rate limited (429), waiting {wait}s (attempt {attempt}/{HTTP_RETRIES})", flush=True)
                    time.sleep(wait)
                    continue
                elif resp.status_code == 403:
                    print(f"    Blocked (403) on attempt {attempt}/{HTTP_RETRIES}", flush=True)
                    if attempt < HTTP_RETRIES:
                        time.sleep(HTTP_RETRY_DELAY)
                    continue
                else:
                    print(f"    HTTP {resp.status_code} on attempt {attempt}/{HTTP_RETRIES}", flush=True)
                    if attempt < HTTP_RETRIES:
                        time.sleep(HTTP_RETRY_DELAY)
                    continue
            except Exception as e:
                print(f"    Fetch error (attempt {attempt}/{HTTP_RETRIES}): {e}", flush=True)
                if attempt < HTTP_RETRIES:
                    time.sleep(HTTP_RETRY_DELAY)
                continue

        print(f"    FAILED to fetch {url} after {HTTP_RETRIES} attempts", flush=True)
        return ""

    def parse_listing_cards(self, html: str, suburb_info: Dict) -> List[Dict]:
        """Parse all listing cards from a search results page."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Find all listing cards by data-testid="listing-NNNNNNN"
        cards = soup.find_all(attrs={"data-testid": re.compile(r'^listing-\d+$')})
        for card in cards:
            testid = card.get("data-testid", "")
            listing_id = testid.replace("listing-", "")

            # Find the property URL within the card
            link = card.find("a", href=re.compile(r'-\d{7,10}$'))
            listing_url = None
            if link:
                href = link["href"]
                listing_url = href if href.startswith("http") else f"https://www.domain.com.au{href}"

            # Get all card text
            card_text = card.get_text(" ", strip=True)

            # Extract sold date
            sold_date = parse_sold_date(card_text)

            # Extract sold price
            sold_price = parse_sold_price(card_text)

            # Extract sale method
            sale_method = parse_sold_method(card_text)

            # Extract address from card
            address = extract_address_from_card(card)
            if not address and listing_url:
                address = extract_address_from_url(
                    listing_url, suburb_info["name"], suburb_info["postcode"]
                )

            # Build full address with suburb + state + postcode
            full_address = address
            if address and suburb_info["name"] not in address:
                full_address = f"{address}, {suburb_info['name']}, QLD {suburb_info['postcode']}"
            elif address and "QLD" not in address:
                full_address = f"{address}, QLD {suburb_info['postcode']}"

            # Extract features
            features = parse_features(card)

            record = {
                "listing_id": listing_id,
                "listing_url": listing_url,
                "address": full_address,
                "sold_date": sold_date,
                "sale_price": sold_price,
                "sale_method": sale_method,
                **features,
            }
            results.append(record)

            if self.verbose:
                price_str = sold_price or "withheld"
                print(f"    {full_address or 'N/A':50s} | {sold_date or 'N/A':10s} | {price_str}")

        return results

    def scrape_suburb(self, suburb_info: Dict, cutoff_date: str) -> List[Dict]:
        """Scrape all recently sold properties for a suburb, stopping at cutoff_date."""
        slug = suburb_info["name"].lower().replace(" ", "-")
        postcode = suburb_info["postcode"]
        base_url = f"https://www.domain.com.au/sold-listings/{slug}-qld-{postcode}/?ssubs=0"

        print(f"\n{'='*70}")
        print(f"  Scraping {suburb_info['name']} (cutoff: {cutoff_date})")
        print(f"{'='*70}")

        all_records = []
        page_num = 1
        hit_cutoff = False

        while page_num <= MAX_PAGES and not hit_cutoff:
            url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
            print(f"  Page {page_num}: {url}")

            try:
                html = self.fetch_page(url)
                if not html:
                    print(f"    Empty response — stopping pagination")
                    break

                records = self.parse_listing_cards(html, suburb_info)

                if not records:
                    print(f"    No listings found — stopping pagination")
                    break

                print(f"    Found {len(records)} listings on this page")

                for rec in records:
                    sd = rec.get("sold_date")
                    if sd and sd < cutoff_date:
                        print(f"    Hit cutoff date ({sd} < {cutoff_date}) — stopping")
                        hit_cutoff = True
                        break
                    all_records.append(rec)

                page_num += 1
                if not hit_cutoff and page_num <= MAX_PAGES:
                    time.sleep(BETWEEN_PAGE_DELAY)

            except Exception as e:
                print(f"    ERROR on page {page_num}: {e}")
                break

        # Deduplicate by listing_id
        seen = set()
        unique = []
        for rec in all_records:
            lid = rec.get("listing_id") or rec.get("listing_url")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(rec)

        print(f"\n  {suburb_info['name']}: {len(unique)} sold properties found (after dedup)")
        return unique

    @staticmethod
    def _retry_db(fn, max_retries=3):
        """Retry a DB operation with backoff on CosmosDB 429 rate limits."""
        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                err_str = str(e)
                if "16500" in err_str or "429" in err_str or "RequestRateTooLarge" in err_str:
                    # Extract RetryAfterMs if present
                    m = re.search(r'RetryAfterMs=(\d+)', err_str)
                    wait = int(m.group(1)) / 1000.0 if m else (1.0 * (attempt + 1))
                    wait = min(wait, 5.0)
                    time.sleep(wait)
                    continue
                raise
        # Final attempt without catching
        return fn()

    def _find_existing(self, collection, rec: Dict) -> Optional[Dict]:
        """Find an existing record matching a sold property. Rate-limit friendly."""
        listing_url = rec.get("listing_url")
        listing_id = rec.get("listing_id")
        address = rec.get("address")

        # Method 1: exact listing_url match (uses index, cheap)
        if listing_url:
            existing = self._retry_db(lambda: collection.find_one({"listing_url": listing_url}))
            if existing:
                return existing

        # Method 2: listing_url ending with listing_id (uses index on listing_url)
        if not listing_url and listing_id:
            existing = self._retry_db(
                lambda: collection.find_one({"listing_url": {"$regex": f"-{listing_id}$"}})
            )
            if existing:
                return existing

        # Method 3: exact address match (no regex, cheap)
        if address:
            existing = self._retry_db(lambda: collection.find_one({"address": address}))
            if existing:
                return existing

            # Method 3b: street portion match — use exact prefix, not regex
            street_part = address.split(",")[0].strip()
            if street_part:
                existing = self._retry_db(lambda: collection.find_one({"address": street_part}))
                if existing:
                    return existing
                # Try case-insensitive regex but only on the short street part
                existing = self._retry_db(
                    lambda: collection.find_one({"address": {"$regex": f"^{re.escape(street_part)}", "$options": "i"}})
                )
                if existing:
                    return existing

        return None

    def update_database(self, records: List[Dict], suburb_info: Dict) -> Dict:
        """Update Gold_Coast database with sold records."""
        collection = self.db[suburb_info["collection"]]
        stats = {"matched": 0, "updated": 0, "inserted": 0, "skipped": 0, "errors": 0}

        for i, rec in enumerate(records):
            # Pace DB operations: small delay every 5 records
            if i > 0 and i % 5 == 0:
                time.sleep(0.5)

            try:
                address = rec.get("address")
                listing_url = rec.get("listing_url")

                if not address and not listing_url:
                    stats["skipped"] += 1
                    continue

                existing = self._find_existing(collection, rec)
                now = datetime.utcnow().isoformat()

                if existing:
                    stats["matched"] += 1
                    # Check if already marked as sold with same date
                    if existing.get("listing_status") == "sold" and existing.get("sold_date") == rec.get("sold_date"):
                        stats["skipped"] += 1
                        if self.verbose:
                            print(f"    SKIP (already sold): {address}")
                        continue

                    update_fields = {
                        "listing_status": "sold",
                        "sold_updated_at": now,
                        "sold_scrape_source": "domain_sold_listings_backfill",
                    }
                    if rec.get("sold_date"):
                        update_fields["sold_date"] = rec["sold_date"]
                    if rec.get("sale_price"):
                        update_fields["sale_price"] = rec["sale_price"]
                    if rec.get("sale_method"):
                        update_fields["sale_method"] = rec["sale_method"]

                    if not self.dry_run:
                        self._retry_db(lambda: collection.update_one(
                            {"_id": existing["_id"]},
                            {"$set": update_fields}
                        ))
                    stats["updated"] += 1
                    print(f"    UPDATE: {address} -> sold {rec.get('sold_date')} {rec.get('sale_price', 'price withheld')}")

                else:
                    new_doc = {
                        "address": address,
                        "listing_url": listing_url,
                        "listing_status": "sold",
                        "sold_date": rec.get("sold_date"),
                        "sale_price": rec.get("sale_price"),
                        "sale_method": rec.get("sale_method"),
                        "suburb": suburb_info["name"],
                        "postcode": suburb_info["postcode"],
                        "state": "QLD",
                        "sold_scrape_source": "domain_sold_listings_backfill",
                        "created_at": now,
                        "sold_updated_at": now,
                    }
                    for key in ["bedrooms", "bathrooms", "parking", "land_size", "land_size_sqm", "property_type"]:
                        if rec.get(key) is not None:
                            new_doc[key] = rec[key]

                    if not self.dry_run:
                        try:
                            self._retry_db(lambda: collection.insert_one(new_doc))
                        except Exception as insert_err:
                            if "duplicate" in str(insert_err).lower():
                                stats["skipped"] += 1
                                continue
                            raise
                    stats["inserted"] += 1
                    print(f"    INSERT: {address} -> sold {rec.get('sold_date')} {rec.get('sale_price', 'price withheld')}")

            except Exception as e:
                stats["errors"] += 1
                print(f"    ERROR processing {rec.get('address', 'unknown')}: {e}")

        return stats

    def run(self, suburbs: List[Dict], days: int):
        """Main entry point."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        print(f"\nRecently Sold Scraper — backfill (curl_cffi)")
        print(f"  Suburbs: {', '.join(s['name'] for s in suburbs)}")
        print(f"  Cutoff date: {cutoff} ({days} days)")
        print(f"  Dry run: {self.dry_run}")

        self.setup_session()
        total_stats = {"matched": 0, "updated": 0, "inserted": 0, "skipped": 0, "errors": 0}

        try:
            for suburb_info in suburbs:
                records = self.scrape_suburb(suburb_info, cutoff)
                if records:
                    stats = self.update_database(records, suburb_info)
                    for k in total_stats:
                        total_stats[k] += stats[k]
                    print(f"\n  {suburb_info['name']} DB stats: {stats}")
                else:
                    print(f"\n  {suburb_info['name']}: no new sold records found")
        finally:
            self.close_session()

        print(f"\n{'='*70}")
        print(f"  TOTAL: {total_stats}")
        if self.dry_run:
            print(f"  (DRY RUN — no changes written)")
        print(f"{'='*70}")
        return total_stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape recently sold properties from Domain.com.au")
    parser.add_argument("--days", type=int, default=60, help="How many days back to scrape (default: 60)")
    parser.add_argument("--suburb", type=str, help="Single suburb to scrape (robina, varsity_lakes, burleigh_waters)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no database writes")
    parser.add_argument("--verbose", action="store_true", help="Extra logging")
    args = parser.parse_args()

    suburbs = TARGET_SUBURBS
    if args.suburb:
        key = args.suburb.lower().replace(" ", "_")
        suburbs = [s for s in TARGET_SUBURBS if s["collection"] == key]
        if not suburbs:
            print(f"ERROR: Unknown suburb '{args.suburb}'. Options: robina, varsity_lakes, burleigh_waters")
            sys.exit(1)

    scraper = RecentSoldScraper(dry_run=args.dry_run, verbose=args.verbose)
    scraper.run(suburbs, args.days)


if __name__ == "__main__":
    main()
