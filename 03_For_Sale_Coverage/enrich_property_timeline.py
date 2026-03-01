#!/usr/bin/env python3
"""
Enrich Property Timeline Script
Last Updated: 24/02/2026

Description:
Extracts transaction history from Gold_Coast database and enriches
Gold_Coast_Currently_For_Sale per-suburb collections with historical sale data.
This enables Capital Gain calculations on the frontend.

Output Fields:
- transactions: Array of {date, price, source} objects for each historical sale

Usage:
    python enrich_property_timeline.py
"""

import os
from pymongo import MongoClient
from datetime import datetime
import sys
import re
import time

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

try:
    from domain_profile_scraper import build_profile_url, scrape_profiles_batch
    _SCRAPER_AVAILABLE = True
except ImportError:
    _SCRAPER_AVAILABLE = False


# Patterns for junk/unmatchable listings that should be skipped
_JUNK_PATTERNS = [
    re.compile(r'^\s*ID:\d+/', re.IGNORECASE),
    re.compile(r'^\s*Type\s+[A-Za-z]\b', re.IGNORECASE),
    re.compile(r'^\s*Lot\s+\d+/', re.IGNORECASE),
    re.compile(r'^\s*[A-Za-z\s]+,\s*QLD\s+\d{4}\s*[-–]'),
    re.compile(r'^\s*[A-Za-z\s]+,\s*QLD\s+\d{4}\s*$'),
]


def _is_junk_listing(address: str) -> bool:
    """Check if a listing has an unmatchable address (off-plan, no street, etc.)."""
    if not address:
        return True
    return any(p.match(address) for p in _JUNK_PATTERNS)


def normalize_address(address):
    """Normalize address for matching: lowercase, strip commas and extra spaces."""
    if not address:
        return ""
    s = str(address).lower()
    s = s.replace(',', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_address_no_postcode(address):
    """Normalize address without trailing postcode - for fallback matching when postcodes differ."""
    s = normalize_address(address)
    # Strip trailing 4-digit postcode (Gold_Coast GIS postcodes are often wrong)
    s = re.sub(r'\s+\d{4}$', '', s).strip()
    return s


# Street type abbreviation map for slug normalisation
STREET_ABBREVS = {
    'crt': 'court', 'ct': 'court',
    'st': 'street',
    'tce': 'terrace', 'ter': 'terrace',
    'dr': 'drive',
    'ave': 'avenue', 'av': 'avenue',
    'rd': 'road',
    'pl': 'place',
    'cres': 'crescent', 'cr': 'crescent',
    'cir': 'circuit', 'cct': 'circuit',
    'blvd': 'boulevard',
    'pde': 'parade',
    'hwy': 'highway',
    'ln': 'lane',
}


def extract_listing_slug(listing_url):
    """Extract normalised slug from a for-sale listing URL.

    Input:  https://www.domain.com.au/7-23-peppertree-circuit-robina-qld-4226-2020620409
    Output: 7-23-peppertree-circuit-robina-qld-4226
    """
    if not listing_url or 'domain.com.au/' not in listing_url:
        return ''
    path = listing_url.split('domain.com.au/')[-1].strip('/')
    # Strip trailing listing ID (purely numeric segment after last hyphen)
    parts = path.rsplit('-', 1)
    if len(parts) == 2 and parts[1].isdigit():
        path = parts[0]
    return _normalise_slug(path)


def extract_profile_slug(profile_url):
    """Extract normalised slug from a Gold_Coast property-profile URL.

    Input:  https://www.domain.com.au/property-profile/5-chantilly-place-robina-qld-4226
    Output: 5-chantilly-place-robina-qld-4226
    """
    if not profile_url or '/property-profile/' not in profile_url:
        return ''
    slug = profile_url.split('/property-profile/')[-1].strip('/')
    return _normalise_slug(slug)


def _normalise_slug(slug):
    """Expand street abbreviations and remove duplicate consecutive words in a URL slug."""
    parts = slug.lower().split('-')
    # Expand abbreviations
    parts = [STREET_ABBREVS.get(p, p) for p in parts]
    # Remove consecutive duplicate words (e.g. drive-drive → drive)
    deduped = [parts[0]] if parts else []
    for p in parts[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    return '-'.join(deduped)


def _timeline_to_transactions(timeline):
    """Convert a scraped property_timeline to frontend transaction format (sold events only)."""
    transactions = []
    for event in (timeline or []):
        if event.get('is_sold') and event.get('price'):
            try:
                price = event.get('price')
                if isinstance(price, str):
                    price = int(float(price.replace('$', '').replace(',', '').strip()))
                else:
                    price = int(price)
                if price > 0:
                    transactions.append({
                        'date': event.get('date'),
                        'price': price,
                        'source': 'Gold_Coast_DB'
                    })
            except (ValueError, TypeError):
                continue
    transactions.sort(key=lambda x: x.get('date', ''))
    return transactions


def _match_timeline_to_gc(scraped_timeline, gc_collection, min_matches=2):
    """Try to find a Gold_Coast document whose timeline shares >= min_matches
    identical (date, price) sold events with the scraped timeline.

    Returns the Gold_Coast document _id if matched, else None.
    """
    # Build set of (date, price) from scraped timeline
    scraped_events = set()
    for event in (scraped_timeline or []):
        if event.get('is_sold') and event.get('date') and event.get('price'):
            try:
                price = int(event['price']) if not isinstance(event['price'], int) else event['price']
                scraped_events.add((event['date'], price))
            except (ValueError, TypeError):
                continue

    if len(scraped_events) < min_matches:
        return None

    # Scan Gold_Coast documents with timeline data
    for gc_doc in gc_collection.find(
        {'scraped_data.property_timeline': {'$exists': True}},
        {'scraped_data.property_timeline': 1, 'complete_address': 1}
    ).batch_size(500):
        gc_timeline = (gc_doc.get('scraped_data') or {}).get('property_timeline', [])
        match_count = 0
        for event in gc_timeline:
            if event.get('is_sold') and event.get('date') and event.get('price'):
                try:
                    price = int(event['price']) if not isinstance(event['price'], int) else event['price']
                    if (event['date'], price) in scraped_events:
                        match_count += 1
                        if match_count >= min_matches:
                            return gc_doc['_id']
                except (ValueError, TypeError):
                    continue

    return None


def _run_pass3_profile_scrape(for_sale_db, gc_db, for_sale_suburbs, exclude):
    """Pass 3: Scrape Domain property-profile pages for still-unmatched properties,
    then match via timeline or create new Gold_Coast documents."""

    if not _SCRAPER_AVAILABLE:
        print("\n⚠ Pass 3 skipped: domain_profile_scraper not available")
        return 0, 0, 0, 0

    print("\n" + "=" * 80)
    print("PASS 3: Domain Property Profile Scrape for Unmatched Properties")
    print("=" * 80)

    # Collect unmatched properties across all suburbs (excluding junk)
    unmatched_by_suburb = {}
    total_unmatched = 0
    total_junk = 0
    for suburb in for_sale_suburbs:
        if suburb in exclude:
            continue
        docs = list(for_sale_db[suburb].find(
            {'transactions': {'$exists': False}},
            {'address': 1, 'listing_url': 1}
        ))
        valid = []
        for doc in docs:
            addr = doc.get('address', '')
            if _is_junk_listing(addr):
                total_junk += 1
                continue
            valid.append(doc)
        if valid:
            unmatched_by_suburb[suburb] = valid
            total_unmatched += len(valid)

    print(f"Found {total_unmatched} unmatched properties across {len(unmatched_by_suburb)} suburbs")
    if total_junk:
        print(f"Skipped {total_junk} junk listings (off-plan, no address, etc.)")

    if total_unmatched == 0:
        print("Nothing to scrape.")
        return 0, 0, 0, 0

    # Build list of (fs_id, address, profile_url) for all unmatched
    scrape_targets = []
    for suburb, docs in unmatched_by_suburb.items():
        for doc in docs:
            addr = doc.get('address', '')
            profile_url = build_profile_url(addr)
            scrape_targets.append((doc['_id'], addr, profile_url, suburb))

    # Scrape all profile pages
    print(f"\nScraping {len(scrape_targets)} Domain property-profile pages...")
    batch_input = [(t[0], t[1], t[2]) for t in scrape_targets]
    scraped_results = scrape_profiles_batch(batch_input, delay=3.0)

    pass3_matched = 0
    pass3_created = 0
    pass3_no_profile = 0
    pass3_errors = 0

    for fs_id, address, profile_url, suburb in scrape_targets:
        scraped = scraped_results.get(fs_id)
        if not scraped:
            pass3_no_profile += 1
            continue

        scraped_timeline = scraped.get('property_timeline', [])
        transactions = _timeline_to_transactions(scraped_timeline)

        # Write transactions to for-sale property if we got any
        if transactions:
            try:
                for_sale_db[suburb].update_one(
                    {'_id': fs_id},
                    {'$set': {
                        'transactions': transactions,
                        'transactions_updated': datetime.now(),
                        'transactions_source': 'domain_profile_scrape'
                    }}
                )
                pass3_matched += 1
                print(f"  ✓ {address}: {len(transactions)} transactions written")
            except Exception as e:
                print(f"  ✗ Error writing transactions for {address}: {e}")
                pass3_errors += 1

        # Try to match to existing Gold_Coast document via timeline
        gc_collection = gc_db[suburb]
        gc_match_id = None
        if len(scraped_timeline) >= 2:
            try:
                gc_match_id = _match_timeline_to_gc(scraped_timeline, gc_collection, min_matches=2)
            except Exception as e:
                print(f"  ✗ Timeline match error for {address}: {e}")

        if gc_match_id:
            # Update existing Gold_Coast doc with fresh scraped_data
            try:
                gc_collection.update_one(
                    {'_id': gc_match_id},
                    {'$set': {
                        'scraped_data': scraped,
                        'scraped_at': datetime.now(),
                        'matched_from_for_sale': address,
                    }}
                )
                print(f"    → Matched to existing Gold_Coast doc {gc_match_id}")
            except Exception as e:
                print(f"    ✗ Error updating Gold_Coast doc: {e}")
        else:
            # Create new Gold_Coast document
            try:
                # Build complete_address from for-sale address (uppercase, no commas)
                complete_address = address.upper().replace(',', '').strip()
                complete_address = re.sub(r'\s+', ' ', complete_address)

                new_gc_doc = {
                    'complete_address': complete_address,
                    'LOCALITY': suburb.upper().replace('_', ' '),
                    'POSTCODE': re.search(r'\d{4}', address).group() if re.search(r'\d{4}', address) else None,
                    'scraped_data': scraped,
                    'scraped_at': datetime.now(),
                    'created_by': 'enrich_property_timeline_pass3',
                    'created_at': datetime.now(),
                    'source_for_sale_address': address,
                }
                result = gc_collection.insert_one(new_gc_doc)
                pass3_created += 1
                print(f"    → Created new Gold_Coast doc {result.inserted_id}")
            except Exception as e:
                print(f"    ✗ Error creating Gold_Coast doc for {address}: {e}")
                pass3_errors += 1

    print(f"\nPass 3 complete: {pass3_matched} transactions written, "
          f"{pass3_created} new Gold_Coast docs created, "
          f"{pass3_no_profile} no profile page, {pass3_errors} errors")

    return pass3_matched, pass3_created, pass3_errors, pass3_no_profile


def enrich_property_timeline():
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="12", process_name="Enrich Property Timeline"
    ) if _MONITOR_AVAILABLE else None
    if monitor: monitor.start()

    print("=" * 80)
    print("ENRICH PROPERTY TIMELINE - Starting")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        client = MongoClient(mongo_uri, retryWrites=False, tls=True, tlsAllowInvalidCertificates=True)
        # Source: Gold_Coast has scraped_data.property_timeline
        gc_db = client['Gold_Coast']
        # Target: Gold_Coast_Currently_For_Sale per-suburb collections
        for_sale_db = client['Gold_Coast_Currently_For_Sale']
        print("✓ Connected to MongoDB")
        print(f"✓ Source: Gold_Coast database")
        print(f"✓ Target: Gold_Coast_Currently_For_Sale database\n")
    except Exception as e:
        print(f"✗ Failed to connect to MongoDB: {e}")
        sys.exit(1)

    # Get for-sale suburbs (exclude metadata collections)
    exclude = {'suburb_statistics', 'suburb_median_prices', 'change_detection_snapshots'}
    try:
        for_sale_suburbs = [c for c in for_sale_db.list_collection_names() if c not in exclude]
        print(f"Found {len(for_sale_suburbs)} for-sale suburb collections\n")
        print("-" * 80)
    except Exception as e:
        print(f"✗ Failed to list for-sale collections: {e}")
        sys.exit(1)

    total_properties_checked = 0
    total_with_timeline = 0
    total_updated = 0
    total_errors = 0

    for suburb_idx, suburb in enumerate(for_sale_suburbs, 1):
        print(f"\n[{suburb_idx}/{len(for_sale_suburbs)}] Processing suburb: {suburb}")

        try:
            for_sale_collection = for_sale_db[suburb]

            # Load all for-sale properties for this suburb into lookup dicts
            # Primary: normalized address (without postcode) -> _id
            # Fallback: URL slug from listing_url -> _id
            for_sale_lookup = {}
            for_sale_slug_lookup = {}
            for doc in for_sale_collection.find({}, {'address': 1, 'listing_url': 1}):
                addr = doc.get('address', '')
                if addr:
                    norm = normalize_address_no_postcode(addr)
                    for_sale_lookup[norm] = doc['_id']
                listing_url = doc.get('listing_url', '')
                if listing_url:
                    slug = extract_listing_slug(listing_url)
                    if slug:
                        for_sale_slug_lookup[slug] = doc['_id']

            if not for_sale_lookup:
                print(f"  - {suburb}: No for-sale properties, skipping")
                continue

            # Check if Gold_Coast has this suburb
            if suburb not in gc_db.list_collection_names():
                print(f"  - {suburb}: Not in Gold_Coast database, skipping")
                continue

            gc_collection = gc_db[suburb]

            suburb_updated = 0

            suburb_slug_matched = 0

            for gc_property in gc_collection.find({}, {'complete_address': 1, 'scraped_data': 1}):
                total_properties_checked += 1

                try:
                    gc_address = gc_property.get('complete_address', '')
                    scraped = gc_property.get('scraped_data') or {}
                    timeline = scraped.get('property_timeline', [])

                    if not gc_address or not timeline:
                        continue

                    # Convert timeline to frontend format (sold events only)
                    transactions = []
                    for event in timeline:
                        if event.get('is_sold') and event.get('price'):
                            try:
                                price = event.get('price')
                                if isinstance(price, str):
                                    price = int(float(price.replace('$', '').replace(',', '').strip()))
                                else:
                                    price = int(price)
                                if price > 0:
                                    transactions.append({
                                        'date': event.get('date'),
                                        'price': price,
                                        'source': 'Gold_Coast_DB'
                                    })
                            except (ValueError, TypeError):
                                continue

                    if not transactions:
                        continue

                    total_with_timeline += 1
                    transactions.sort(key=lambda x: x.get('date', ''))

                    # Pass 1: Match Gold_Coast address against for-sale lookup (postcode stripped)
                    norm_gc = normalize_address_no_postcode(gc_address)
                    for_sale_id = for_sale_lookup.get(norm_gc)

                    # Pass 2: URL slug fallback
                    if for_sale_id is None:
                        gc_url = scraped.get('url', '')
                        gc_slug = extract_profile_slug(gc_url)
                        if gc_slug:
                            for_sale_id = for_sale_slug_lookup.get(gc_slug)
                            if for_sale_id:
                                suburb_slug_matched += 1

                    if for_sale_id is None:
                        continue

                    result = for_sale_collection.update_one(
                        {'_id': for_sale_id},
                        {'$set': {'transactions': transactions, 'transactions_updated': datetime.now()}}
                    )

                    if result.modified_count > 0:
                        total_updated += 1
                        suburb_updated += 1

                except Exception as e:
                    total_errors += 1
                    if total_errors <= 5:
                        print(f"  ✗ Error processing property: {e}")
                    continue

            if suburb_updated > 0:
                slug_note = f" ({suburb_slug_matched} via URL slug)" if suburb_slug_matched else ""
                print(f"  ✓ {suburb}: {suburb_updated} properties updated with transaction history{slug_note}")
            else:
                print(f"  - {suburb}: No matching properties found")

        except Exception as e:
            print(f"  ✗ Error processing suburb {suburb}: {e}")
            continue

    # --- Pass 3: Scrape Domain profiles for still-unmatched properties ---
    pass3_matched, pass3_created, pass3_errors, pass3_no_profile = _run_pass3_profile_scrape(
        for_sale_db, gc_db, for_sale_suburbs, exclude
    )
    total_updated += pass3_matched
    total_errors += pass3_errors

    print("\n" + "=" * 80)
    print("ENRICH PROPERTY TIMELINE - Complete")
    print("=" * 80)
    print(f"Pass 1+2: Gold_Coast properties checked: {total_properties_checked}")
    print(f"Pass 1+2: Properties with timeline data: {total_with_timeline}")
    print(f"Pass 1+2: For-sale properties updated: {total_updated - pass3_matched}")
    print(f"Pass 3:   Profile scrape matches: {pass3_matched}")
    print(f"Pass 3:   New Gold_Coast docs created: {pass3_created}")
    print(f"Pass 3:   No profile page (404): {pass3_no_profile}")
    print(f"Total for-sale properties updated: {total_updated}")
    print(f"Errors: {total_errors}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    if monitor:
        monitor.log_metric("properties_checked", total_properties_checked)
        monitor.log_metric("properties_with_timeline", total_with_timeline)
        monitor.log_metric("properties_updated", total_updated)
        monitor.log_metric("pass3_profile_matches", pass3_matched)
        monitor.log_metric("pass3_gc_docs_created", pass3_created)
        monitor.log_metric("pass3_no_profile", pass3_no_profile)
        monitor.finish(status="success" if total_errors == 0 else "failed")


if __name__ == '__main__':
    enrich_property_timeline()
