#!/usr/bin/env python3
"""
Continuous Monitor - Continuously monitor properties for new URLs
"""

import asyncio
import re
from pymongo import MongoClient
from typing import List, Dict, Optional
from datetime import datetime, timezone
UTC = timezone.utc
import json
import os
from pathlib import Path

from url_tracker import URLTracker
from robust_extractor import RobustPropertyExtractor
from hybrid_extraction_poc import HybridExtractor
from gpt_verifier import gpt_verify_listing, gpt_extract_listing
from direct_agency_scraper import DirectAgencyScraper, ROBINA_AGENCIES


class AgencyLinkFilter:
    """Filter search results for agency links"""

    # URL path segments that indicate non-listing pages — reject these
    REJECT_PATH_PATTERNS = [
        '/about', '/contact', '/team', '/people/', '/office/',
        '/suburb-profiles/', '/suburb-profile/', '/recent-sales/',
        '/appraisal', '/blog', '/news', '/careers', '/awards',
        '/corporate-search/',        # PRD search result indexes
        'listings/sold?',            # Harcourts paginated sold indexes
        'listings/buy?',             # Harcourts paginated for-sale indexes
        'listings/sold?page',
        '/listings/page/',           # Paginated listing indexes (robinarealty etc)
        '/exclusive-listings',       # Agent listing index pages
        '/recently-sold',            # Agent "recently sold" index pages (karynodea etc)
        '/mermaid-beach/people/',    # Agent profile pages
        '/agency/',                  # Agency profile pages (realty.com.au/agency/...)
        'sitemap',                   # XML sitemaps (prd.com.au/canberra/sitemap-listings.xml)
        '.xml',                      # Any XML file
        '.pdf',                      # PDF documents
        '/properties/sold?',         # Ray White paginated sold index (/properties/sold?category=...)
        '/properties/buy?',          # Ray White paginated buy index
        '/properties/lease?',        # Ray White paginated lease index
        '/properties/sold ',         # Ray White sold index with trailing space (edge case)
        'ratemyagent.com.au',        # Third-party review site
        'facebook.com',              # Social media
        'instagram.com',
        'youtube.com',
        'dental',                    # Non-real-estate domains
        'demolition',
        'haveyoursay',
        'gchaveyoursay',
        'astras.com.au',             # Prestige agency — not returning extractable data
        '/attachment/',              # robinarealty image attachment URLs (not listing pages)
        '/reviews/',                 # coastal.com.au agent review pages
        '/property-search/',         # PRD property-search index (no status info)
        '/corporate-search/',        # PRD corporate-search index (already present but belt-and-braces)
        '/listing-search/',          # Generic paginated listing search pages
        '/suburb/',                  # Suburb profile pages (various agencies)
        'harcourts.net/au/buy',      # Harcourts paginated buy index
        'harcourts.net/au/sold',     # Harcourts paginated sold index
        'harcourts.net/au/rent',     # Harcourts paginated rent index
        '/agent-profile/',           # Agent profile pages
        '/agent/',                   # Agent profile pages (various)
        'ratemyagent.com.au',        # Already in list but ensure it's here
        '/property-hub/people',      # Harcourts agent-profile pages
        '/au/office',                # harcourts.net office pages
        '/aspire/',                  # RE/MAX Aspire suburb-profile hub
        'remaxgc.com.au/suburb-profiles',  # RE/MAX suburb profiles (belt+braces)
        'coastal.com.au/suburb-profiles',  # coastal suburb profiles
    ]

    # Bare homepage domains — any URL whose path is empty or just a country code (/au)
    HOMEPAGE_DOMAINS = [
        'harcourts.net',
        'prdburleighheads.com.au',
        'raywhite.com',
        'lj.hooker.com.au',
        'ljhooker.com.au',
        'realestate.com.au',
        'domain.com.au',
        'century21.com.au',
        'barryplant.com.au',
        'mcgrath.com.au',
        'mcdermottresidential.com.au',
        'gcsr.com.au',
        'robinarealty.com.au',
        'raywhiterobina.com.au',
        'raywhitetmg.com.au',
        'raywhitemalanandco.com.au',
        'orrentopolansky.com.au',
        'crasto.com.au',
        'robinafn.com.au',
        'remaxgc.com.au',
    ]

    def __init__(self, trigger_words_file: str):
        self.trigger_words = []

        with open(trigger_words_file, 'r') as f:
            for line in f:
                word = line.strip().rstrip(',')
                if word and not word.startswith('#'):
                    self.trigger_words.append(word.lower())

    def is_valid_listing_url(self, url: str) -> bool:
        """
        Return False if the URL is clearly not a property listing page.
        Rejects agency homepages, suburb profiles, agent pages, paginated indexes, etc.
        """
        from urllib.parse import urlparse
        url_lower = url.lower()

        # Reject known non-listing path patterns
        for pattern in self.REJECT_PATH_PATTERNS:
            if pattern in url_lower:
                return False

        # Reject bare homepage URLs (e.g. https://harcourts.net/au or https://raywhite.com/)
        # A listing URL always has a meaningful path like /properties/... or /listing/12345
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip('/')
            # If the path is empty or just a 2-letter country code (/au, /us) it's a homepage
            if path == '' or (len(path) <= 3 and path.lstrip('/').isalpha()):
                for domain in self.HOMEPAGE_DOMAINS:
                    if domain in parsed.netloc.lower():
                        return False
            # Reject Ray White bare sold/buy/lease index paths (no listing ID after)
            # Valid: /properties/sold-residential/qld/robina/house/1234567
            # Invalid: /properties/sold  or  /properties/buy
            if re.match(r'^/properties/(sold|buy|lease|leased)$', path, re.IGNORECASE):
                return False
            # Reject agent profile pages — single-segment path that is just a person's name slug
            # e.g. coastal.com.au/cindy-liu/ — path is /cindy-liu (one word-hyphen-word segment)
            # Valid listing paths always have multiple segments: /listing/r2-123456-...
            path_segments = [s for s in path.split('/') if s]
            if len(path_segments) == 1 and re.match(r'^[a-z]+-[a-z]+(-[a-z]+)?$', path_segments[0]):
                return False
        except Exception:
            pass

        return True

    def filter_agency_links(self, search_results: List[Dict], searched_address: str = '') -> List[Dict]:
        """
        Filter search results to only valid agency listing links.

        Args:
            search_results: Raw results from SearXNG
            searched_address: The property address that was searched (used for street number check)
        """
        agency_results = []

        # Extract street number from searched address for validation (e.g. "61" from "61 AUK AVENUE...")
        searched_street_num = ''
        if searched_address:
            # Handle unit/apartment format like "107/170" — take the last number before the street name
            num_match = re.match(r'^(?:\d+/)?(\d+)\s', searched_address.strip())
            if num_match:
                searched_street_num = num_match.group(1)

        for result in search_results:
            url = result['url']
            url_lower = url.lower()

            # Fix 1: Reject non-listing URLs before doing anything else
            if not self.is_valid_listing_url(url):
                continue

            # Check agency keyword match
            matched_keyword = None
            for trigger in self.trigger_words:
                if trigger in url_lower:
                    matched_keyword = trigger
                    break

            if not matched_keyword:
                continue

            # Fix 2: Street number check — if we have a searched number and the URL contains
            # a different number, it's likely a nearby property result, not this one.
            # We only reject if the URL explicitly contains a street number that doesn't match.
            if searched_street_num:
                title = result.get('title', '')
                # Extract street number from result title (most reliable signal)
                title_num_match = re.match(r'^(\d+)(?:/\d+)?\s', title.strip())
                if title_num_match:
                    result_street_num = title_num_match.group(1)
                    if result_street_num != searched_street_num:
                        continue  # Wrong property — skip

            agency_results.append({
                **result,
                'agency_keyword': matched_keyword
            })

        return agency_results


class ContinuousMonitor:
    """Continuously monitor properties for new URLs"""

    LOCAL_URI = 'mongodb://localhost:27017/'

    # Cycle pacing — sleep between cycles to avoid hammering agency sites.
    # ~7 min cycles (continuous) got us blocked at RE/MAX + Coastal in April.
    CYCLE_INTERVAL_SECONDS = int(os.environ.get('SCRAPER_CYCLE_INTERVAL_SECONDS', 30 * 60))

    def __init__(
        self,
        suburbs: List[str] = ['robina', 'varsity_lakes', 'burleigh_waters'],
        concurrency: int = 10,
        json_output_dir: str = "discovered_urls"
    ):
        """Initialize continuous monitor"""
        self.suburbs = suburbs
        self.concurrency = concurrency
        self.json_output_dir = json_output_dir

        # Single local Mongo client — source cadastral, URL tracking, and discoveries
        # all live in the same Gold_Coast database now (Azure Cosmos retired May 2026).
        self.local_client = MongoClient(self.LOCAL_URI)
        self.source_db = self.local_client['Gold_Coast']

        # URLTracker writes to local Gold_Coast DB (collections: property_url_tracking,
        # new_url_discoveries) and updates the suburb collection with current snapshot.
        self.tracker = URLTracker(self.LOCAL_URI)

        # Create JSON output directory
        Path(json_output_dir).mkdir(parents=True, exist_ok=True)
        for suburb in suburbs:
            Path(f"{json_output_dir}/{suburb}").mkdir(parents=True, exist_ok=True)

        # Load agency filters per suburb
        self.agency_filters = {}
        for suburb in suburbs:
            try:
                trigger_file = f"Real_Estate_Agencies/{suburb.capitalize()}.md"
                self.agency_filters[suburb] = AgencyLinkFilter(trigger_file)
                print(f"✅ Loaded agency filter for {suburb}")
            except FileNotFoundError:
                print(f"⚠️  No agency filter found for {suburb}, will use all URLs")
                self.agency_filters[suburb] = None

        print(f"✅ Continuous Monitor initialized")
        print(f"   Suburbs: {', '.join(suburbs)}")
        print(f"   Concurrency: {concurrency}")

    async def check_property(
        self,
        doc: Dict,
        suburb: str,
        agency_filter: Optional[AgencyLinkFilter]
    ) -> int:
        """
        Check one property for new URLs

        Args:
            doc: Property document from MongoDB
            suburb: Suburb name
            agency_filter: Agency link filter

        Returns:
            Number of new URLs found
        """
        address = doc.get('complete_address', 'Unknown')

        new_urls = []
        try:
            # Step 1: Search
            # Fix 17: title-case + quote the address for precise SearXNG matching
            search_query = '"' + address.title() + '"'
            search_results = await self.searcher.search(search_query, num_results=10)

            if search_results:
                # Step 2: Filter for agency URLs
                if agency_filter:
                    current_url_data = agency_filter.filter_agency_links(search_results, searched_address=address)
                else:
                    current_url_data = [
                        {'url': r['url'], 'title': r.get('title', ''), 'agency_keyword': 'unknown'}
                        for r in search_results
                    ]

                if current_url_data:
                    # Step 3: Detect new URLs
                    new_urls = self.tracker.detect_new_urls(address, suburb, current_url_data)

                    # Step 4: Update tracking
                    self.tracker.update_tracking(address, suburb, current_url_data, doc.get('_id'))

                    # Step 5: Process new URLs (scrape & extract)
                    if new_urls:
                        await self.process_new_urls(address, suburb, new_urls)
                else:
                    self.tracker.update_tracking(address, suburb, [], doc.get('_id'))
            else:
                self.tracker.update_tracking(address, suburb, [], doc.get('_id'))

        except Exception as e:
            print(f"\n   ⚠️  Error checking {address}: {str(e)[:50]}")

        # Fix 20c: Recheck ALWAYS runs — even when SearXNG returns 0 results
        try:
            await self.recheck_for_sale_urls(address, suburb)
        except Exception as e:
            print(f"\n   ⚠️  Recheck error {address}: {str(e)[:50]}")

        return len(new_urls)

    async def process_new_urls(
        self,
        address: str,
        suburb: str,
        new_url_data: List[Dict]
    ):
        """
        Scrape and extract data from new URLs

        Args:
            address: Property address
            suburb: Suburb name
            new_url_data: List of new URL dicts
        """
        for url_data in new_url_data:
            try:
                url = url_data['url']
                agency = url_data.get('agency_keyword', 'unknown')

                # Full scrape
                extractor = RobustPropertyExtractor(url)
                raw_data = await extractor.run_extraction()

                if not raw_data:
                    continue

                # Fix 16: skip pages with no title AND no body text (dead/blank pages)
                text_blob = raw_data.get('data', {}).get('text', {})
                page_title = (text_blob.get('page_title') or '').strip()
                body_text  = (text_blob.get('body') or text_blob.get('content') or '').strip()
                if not page_title and not body_text:
                    print(f"   ⏭  SKIP blank page: {url}")
                    continue

                # Fix 12: full pipeline — extract + filter images + build document
                hybrid = HybridExtractor(use_ai_fallback=False)
                extracted_data = hybrid.extract_property_data(raw_data)

                # GPT nano fallback: if address missing or key fields missing, ask GPT
                visible_text = text_blob.get('visible_text', '')
                needs_gpt = (
                    not extracted_data.get('address')
                    or not extracted_data.get('listing_status')
                    or (not extracted_data.get('bedrooms') and not extracted_data.get('bathrooms'))
                )
                if needs_gpt and visible_text and len(visible_text) > 100:
                    print(f"   [GPT extracting: {url[:60]}]")
                    gpt_result = await gpt_extract_listing(
                        page_title, visible_text, target_suburb=suburb.title()
                    )
                    if gpt_result:
                        gpt_addr = gpt_result.get('page_address')
                        gpt_suburb = (gpt_result.get('suburb') or '').lower()
                        gpt_status = gpt_result.get('listing_status')

                        # Fill in missing address
                        if not extracted_data.get('address') and gpt_addr:
                            extracted_data['address'] = gpt_addr
                            print(f"   GPT address: {gpt_addr}")

                        # Fill in missing listing status
                        if not extracted_data.get('listing_status') and gpt_status:
                            extracted_data['listing_status'] = gpt_status

                        # Fill in missing numeric fields
                        for field in ('bedrooms', 'bathrooms', 'carspaces'):
                            if not extracted_data.get(field) and gpt_result.get(field):
                                extracted_data[field] = gpt_result[field]

                        # Fill in missing price
                        if not extracted_data.get('sale_price') and gpt_result.get('sale_price'):
                            extracted_data['sale_price'] = gpt_result['sale_price']

                        # Fill in missing property type
                        if not extracted_data.get('property_type') and gpt_result.get('property_type'):
                            extracted_data['property_type'] = gpt_result['property_type']

                        # Mark extraction method as hybrid
                        if any(gpt_result.get(f) for f in ('page_address', 'bedrooms', 'bathrooms', 'sale_price')):
                            extracted_data['extraction_method'] = 'HYBRID_RULE_GPT'

                        # Suburb validation: if GPT says it's not our target suburb, flag it
                        if gpt_suburb and suburb.lower() not in gpt_suburb and gpt_suburb not in suburb.lower():
                            print(f"   [GPT SUBURB MISMATCH: page is {gpt_suburb}, expected {suburb}]")
                            extracted_data['suburb_mismatch'] = gpt_suburb

                filtered_images = hybrid.filter_images(raw_data)
                extracted = hybrid.create_mongodb_document(extracted_data, raw_data, filtered_images)

                # Fix 15: verify page address matches GIS search address
                page_address = extracted_data.get('address') or ''
                verified_address, address_match = self._verify_address(address, page_address, raw_data)
                if not address_match:
                    print(f"   \u26a0\ufe0f  ADDR MISMATCH: searched='{address}' page='{verified_address}'")

                # Record discovery in MongoDB
                discovery_id = self.tracker.record_discovery(
                    address, suburb, url_data,
                    raw_data, extracted
                )

                # Save to JSON file
                json_path = self.save_to_json(
                    address, suburb, agency, url,
                    raw_data, extracted,
                    verified_address=verified_address,
                    address_match=address_match
                )

                # Mark as saved
                self.tracker.mark_json_saved(discovery_id, json_path)

            except Exception as e:
                print(f"\n   ⚠️  Error processing {url_data['url']}: {str(e)[:50]}")
                continue


    def _verify_address(self, gis_address: str, page_address: str, raw_data: dict):
        """
        Fix 15: Compare GIS search address against what the page actually says.
        Returns (verified_address, address_match).
        """
        def num_street(addr):
            m = re.match(r"(\d+[A-Z]?(?:/\d+[A-Z]?)?)\s+(\w+)", (addr or "").strip().upper())
            if not m:
                return (None, None)
            # Normalise alphanumeric numbers: "8A" -> "8", "1A/2" -> "1/2"
            num = re.sub(r"[A-Z]", "", m.group(1))
            return (num, m.group(2))

        candidate = page_address
        if not candidate:
            title = (raw_data.get("data", {}).get("text", {})
                     .get("page_title", "") or "")
            m = re.search(
                r"(\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?\s+[A-Za-z ]+"
                r"(?:Street|St|Road|Rd|Drive|Dr|Court|Ct|Avenue|Ave|Place|Pl"
                r"|Crescent|Cres|Circuit|Cct|Way|Boulevard|Blvd|Terrace|Tce"
                r"|Lane|Ln|Parade|Pde|Close|Cl|Chase|Grove|Gr|Highway|Hwy"
                r"|Rise|Glen|View|Loop|Link|Track|Row|Mews|Square|Sq)"
                r",\s*[A-Za-z ]+,\s*QLD(?:\s+\d{4})?)",
                title, re.IGNORECASE
            )
            candidate = m.group(1) if m else ""

        verified = candidate or gis_address
        gis_num,  gis_st  = num_street(gis_address)
        page_num, page_st = num_street(verified)
        if gis_num and page_num:
            match = (gis_num == page_num and gis_st == page_st)
        else:
            match = True
        return verified, match

    def _write_unknown(self, address: str, suburb: str, reason: str = ""):
        """
        Write a synthetic 'unknown' status JSON for a property whose recheck
        produced no confirmable URL (all mismatched or no qualifying URLs).
        This becomes the most-recent file, so the next cycle's gate won't recheck
        until new evidence (a fresh matched for_sale URL) is found.
        """
        minimal_extracted = {
            'listing_status': 'unknown',
            'address': address,
            'suburb': suburb,
            'extraction_method': f'recheck_inconclusive:{reason}',
            'extraction_confidence': 0,
            'missing_fields': [],
            'sale_price': None,
            'sold_date': None,
            'bedrooms': None,
            'bathrooms': None,
            'carspaces': None,
            'land_size_sqm': None,
            'property_type': None,
            'features': [],
        }
        self.save_to_json(
            address, suburb, 'recheck',
            '', {}, minimal_extracted,
            verified_address=address, address_match=False
        )

    async def recheck_for_sale_urls(self, address: str, suburb: str):
        """
        Fix 20: Re-fetch known for_sale URLs on every cycle.
        Logs every URL checked and result. Saves result regardless of status.

        Uses most-recent-file status (not max-priority) for the gate, so a freshly
        written 'unknown' (all URLs mismatched) or 'sold'/'leased' stops further
        rechecking without being overridden by an older for_sale file.
        """
        import glob as _glob, json as _json

        addr_slug = re.sub(r'[^A-Z0-9]', '-', address.upper())
        existing_files = sorted(_glob.glob(f"{self.json_output_dir}/{suburb}/*_{addr_slug}_*.json"))

        # Gate: only recheck if the MOST RECENT file for this address says for_sale.
        # Using most-recent (not max-priority) means a freshly written 'unknown' from
        # a previous recheck can stop further rechecking until new evidence arrives.
        current_best = None
        if existing_files:
            try:
                d = _json.load(open(existing_files[-1]))
                current_best = d.get('listing_status') or (d.get('extracted_data') or {}).get('listing_status')
            except Exception:
                pass

        if current_best != 'for_sale':
            return

        tracking_doc = self.tracker.tracking_collection.find_one({
            "complete_address": address, "suburb": suburb
        })
        if not tracking_doc:
            print(f"   ❓ RECHECK {address}: no tracking doc → marking unknown")
            self._write_unknown(address, suburb, reason="no_tracking_doc")
            return

        known_urls = tracking_doc.get("known_urls", [])
        for_sale_urls = [
            u for u in known_urls
            if (
                re.search(r"/\d{4,}|/[a-z0-9]{6,}(?:/|$)", u["url"].lower())
                and not any(x in u["url"].lower() for x in (
                    "/sold-", "/leased-", "/residential-for-rent/", "/commercial-for-rent/"
                ))
                and any(x in u["url"].lower() for x in (
                    "/residential-for-sale/", "/for-sale/", "/properties/",
                    "/property/", "/listing/", "raywhite.com/", "harcourts",
                    "coastal.com.au/property", "remax", "mcgrath", "prd.com.au"
                ))
            )
        ]

        if not for_sale_urls:
            print(f"   ❓ RECHECK {address}: no qualifying URLs → marking unknown")
            self._write_unknown(address, suburb, reason="no_qualifying_urls")
            return

        print(f"   🔍 RECHECK {address}: {min(len(for_sale_urls), 3)} URL(s)")

        any_url_processed = False
        for url_entry in for_sale_urls[:3]:
            url = url_entry["url"]
            try:
                extractor = RobustPropertyExtractor(url)
                raw_data = await extractor.run_extraction()
                if not raw_data:
                    print(f"      ↳ {url[:70]}  ->  [no data]")
                    continue

                hybrid = HybridExtractor(use_ai_fallback=False)
                extracted_data = hybrid.extract_property_data(raw_data)
                new_status = extracted_data.get("listing_status")

                # Fix 22: Skip URLs where the page belongs to a different address.
                page_address = extracted_data.get("address") or ""
                verified_address, address_match = self._verify_address(address, page_address, raw_data)
                # Skip if body OR title address doesn't match.
                if not address_match:
                    display_addr = (page_address or verified_address or '')[:40]
                    print(f"      ↳ {url[:70]}  ->  [ADDR MISMATCH: page='{display_addr}'] skip")
                    continue

                # GPT fallback: when rules found no address candidate from body or title,
                # ask GPT to read the page and identify the address and status.
                # Detected by: page_address empty AND verified_address fell back to gis_address.
                rules_had_no_candidate = (
                    not page_address
                    and verified_address.upper().split(',')[0].strip() == address.upper().split(',')[0].strip()
                )
                if rules_had_no_candidate:
                    visible_text = raw_data.get('data', {}).get('text', {}).get('visible_text', '') or ''
                    page_title_raw = raw_data.get('data', {}).get('text', {}).get('page_title', '') or ''
                    if len(visible_text) > 500:
                        print(f"      ↳ {url[:70]}  ->  [GPT verifying...]")
                        gpt = await gpt_verify_listing(address, page_title_raw, visible_text)
                        if gpt:
                            gpt_addr = gpt.get('page_address') or ''
                            gpt_status = gpt.get('listing_status') or ''
                            if not gpt_addr:
                                # GPT says this is a generic/search page — not a specific listing
                                print(f"      ↳ {url[:70]}  ->  [GPT: generic page] skip")
                                continue
                            _, gpt_match = self._verify_address(address, gpt_addr, {})
                            if not gpt_match:
                                print(f"      ↳ {url[:70]}  ->  [GPT ADDR MISMATCH: '{gpt_addr[:40]}'] skip")
                                continue
                            print(f"      ↳ {url[:70]}  ->  GPT confirmed: {gpt_addr[:40]} | {gpt_status}")
                            # Override rule-based status with GPT's reading if more definitive
                            if gpt_status in ('sold', 'leased') and new_status == 'for_sale':
                                extracted_data['listing_status'] = gpt_status
                                new_status = gpt_status

                print(f"      ↳ {url[:70]}  ->  {new_status}")
                any_url_processed = True

                # Save regardless of status (full observability)
                filtered_images = hybrid.filter_images(raw_data)
                extracted = hybrid.create_mongodb_document(extracted_data, raw_data, filtered_images)
                url_data = {
                    "url": url,
                    "agency_keyword": url_entry.get("agency_keyword", "unknown"),
                    "title": url_entry.get("title", ""),
                    "recheck": True,
                }
                discovery_id = self.tracker.record_discovery(
                    address, suburb, url_data, raw_data, extracted
                )
                json_path = self.save_to_json(
                    address, suburb, url_entry.get("agency_keyword", "unknown"),
                    url, raw_data, extracted,
                    verified_address=verified_address, address_match=address_match
                )
                self.tracker.mark_json_saved(discovery_id, json_path)

                if new_status in ("sold", "leased"):
                    print(f"   🔄 STATUS CHANGE: {address} -> {new_status} (re-check)")
                    break  # Fix 20b: stop checking — don't let later URLs overwrite
                elif new_status == "for_sale":
                    print(f"   ✅ CONFIRMED FOR SALE: {address}")
                else:
                    print(f"   ❓ INCONCLUSIVE: {address} -> {new_status}")

            except Exception as e:
                print(f"      ↳ {url[:70]}  ->  [error: {str(e)[:50]}]")

        # All URLs were skipped (address mismatch) — property status is unknown
        # pending a new matched URL being discovered by SearXNG.
        if not any_url_processed:
            print(f"   ❓ RECHECK {address}: all URLs mismatched → marking unknown")
            self._write_unknown(address, suburb, reason="all_urls_mismatched")


    def save_to_json(
        self,
        address: str,
        suburb: str,
        agency: str,
        url: str,
        raw_data: Dict,
        extracted_data: Dict,
        verified_address: str = None,
        address_match: bool = True
    ) -> str:
        """
        Save discovery to JSON file

        Args:
            address: Property address
            suburb: Suburb name
            agency: Agency keyword
            url: URL discovered
            raw_data: Raw scraped data
            extracted_data: Extracted property data

        Returns:
            Path to JSON file
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

        # Clean address for filename
        clean_address = address.replace(' ', '-').replace('/', '-')[:50]

        filename = f"{timestamp}_{clean_address}_{agency}.json"
        filepath = f"{self.json_output_dir}/{suburb}/{filename}"

        data = {
            'listing_status': extracted_data.get('listing_status'),
            'discovery_info': {
                'address': address,
                'suburb': suburb,
                'new_url': url,
                'agency_keyword': agency,
                'discovered_at': now.isoformat(),
                'verified_address': verified_address or address,
                'address_match': address_match,
            },
            'raw_data': raw_data,
            'extracted_data': extracted_data
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        return filepath

    async def monitor_suburb_batch(
        self,
        suburb: str,
        docs: List[Dict],
        agency_filter: Optional[AgencyLinkFilter],
        batch_num: int,
        total_batches: int
    ) -> int:
        """Process a batch of properties in parallel"""
        tasks = [
            self.check_property(doc, suburb, agency_filter)
            for doc in docs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count new URLs (ignore exceptions)
        new_urls_count = sum(r for r in results if isinstance(r, int))

        return new_urls_count

    def _get_for_sale_addresses(self, suburb: str) -> List[str]:
        """
        Return addresses whose most-recent JSON file has listing_status=for_sale.
        Used to build the recheck pass without re-reading all of MongoDB.
        """
        import glob as _glob, json as _json, os as _os
        from collections import defaultdict

        files_by_addr: dict = defaultdict(list)
        pattern = f"{self.json_output_dir}/{suburb}/*.json"
        for fp in _glob.glob(pattern):
            try:
                d = _json.load(open(fp))
                addr = (d.get('discovery_info') or {}).get('address')
                if addr:
                    files_by_addr[addr].append((_os.path.basename(fp), fp))
            except Exception:
                pass

        for_sale = []
        for addr, entries in files_by_addr.items():
            entries.sort(key=lambda x: x[0], reverse=True)
            try:
                d = _json.load(open(entries[0][1]))
                status = d.get('listing_status') or (d.get('extracted_data') or {}).get('listing_status')
                if status == 'for_sale':
                    for_sale.append(addr)
            except Exception:
                pass
        return for_sale

    async def monitor_suburb(self, suburb: str, cycle: int) -> Dict:
        """
        Monitor all properties in a suburb — two-pass architecture:

        Pass 0 — Direct agency scrape:
            Scrape listing pages directly from configured agency websites.

        Pass 1 — Playwright rechecks (concurrency=10, memory-limited, ~10-15 min):
            Only properties whose most-recent file says for_sale get rechecked.
        """
        import time as _time

        print(f"\n{'=' * 80}")
        print(f"{suburb.upper()} (Cycle {cycle})")
        print(f"{'=' * 80}")

        source_collection = self.source_db[suburb.lower()]
        agency_filter = self.agency_filters.get(suburb)
        total = source_collection.count_documents({})
        print(f"Total properties: {total:,}")

        # Fetch all docs once — used by Pass 0 (GIS matching)
        all_docs = list(source_collection.find(
            {}, {'complete_address': 1, '_id': 1}
        ))

        # ── PASS 0: Direct agency listing pages ────────────────────────────
        # Scrape listing pages from all configured agencies for this suburb.
        # Discovered URLs are fed into the normal pipeline for scraping/extraction.
        t_p0 = _time.time()
        direct_new_urls = 0
        if suburb.lower() == 'robina':
            print(f"\n[Pass 0] Direct agency scrape — {len(ROBINA_AGENCIES)} agencies")
            try:
                direct_scraper = DirectAgencyScraper(suburb='Robina', postcode='4226')
                direct_results = await direct_scraper.scrape_all()

                # Build a map of all GIS addresses in this suburb for matching
                gis_addresses = {
                    doc.get('complete_address', '').upper(): doc.get('complete_address', '')
                    for doc in all_docs
                    if doc.get('complete_address')
                }

                # For each agency, match discovered addresses to GIS addresses
                # and feed new listing URLs into the pipeline
                for agency_data in direct_results.get('by_agency', []):
                    agency_name = agency_data.get('agency', 'unknown')
                    agency_key = agency_name.lower().replace(' ', '')

                    for listing_url in agency_data.get('listing_urls', []):
                        url_data = [{
                            'url': listing_url,
                            'title': '',
                            'agency_keyword': agency_key,
                        }]

                        # Try to match to a GIS address using discovered addresses
                        # For now use the listing URL's address slug as the key
                        from direct_agency_scraper import _extract_address_from_url
                        url_addr = _extract_address_from_url(listing_url)
                        matched_gis = None
                        if url_addr:
                            addr_upper = url_addr.upper()
                            for gis_upper, gis_orig in gis_addresses.items():
                                if addr_upper in gis_upper or gis_upper.startswith(addr_upper.split()[0]):
                                    # Rough match — check street number + first word
                                    parts = addr_upper.split()
                                    if len(parts) >= 2 and parts[0] in gis_upper and parts[1] in gis_upper:
                                        matched_gis = gis_orig
                                        break

                        # Use matched GIS address, or the URL-derived address
                        address_key = matched_gis or url_addr or listing_url

                        new_urls = self.tracker.detect_new_urls(
                            address_key, suburb, url_data
                        )
                        if new_urls:
                            self.tracker.update_tracking(address_key, suburb, url_data)
                            try:
                                await self.process_new_urls(address_key, suburb, new_urls)
                                direct_new_urls += len(new_urls)
                            except Exception as e:
                                print(f"   ⚠️  Direct scrape error: {str(e)[:50]}")

            except Exception as e:
                print(f"   ⚠️  Pass 0 error: {str(e)[:80]}")

        elapsed_p0 = _time.time() - t_p0
        print(f"\n[Pass 0 done] {direct_new_urls} new URLs processed in {elapsed_p0:.0f}s")

        # ── PASS 1: Playwright rechecks for for_sale properties ───────────────
        for_sale_addrs = self._get_for_sale_addresses(suburb)
        recheck_sem = asyncio.Semaphore(self.concurrency)  # keep at 10 — Playwright is memory-heavy
        t1 = _time.time()

        print(f"\n[Pass 1] Playwright rechecks — {len(for_sale_addrs)} for_sale properties at concurrency={self.concurrency}")

        async def recheck_one(address):
            async with recheck_sem:
                try:
                    await self.recheck_for_sale_urls(address, suburb)
                except Exception as e:
                    print(f"\n   ⚠️  Recheck error {address[:40]}: {str(e)[:50]}")

        await asyncio.gather(*[recheck_one(addr) for addr in for_sale_addrs])

        elapsed2 = _time.time() - t1
        print(f"\n[Pass 1 done] {len(for_sale_addrs)} rechecks in {elapsed2:.0f}s")
        print(f"\n✅ {suburb} complete | agency scrape: {elapsed_p0:.0f}s | rechecks: {elapsed2:.0f}s | new URLs: {direct_new_urls}")

        return {
            'suburb': suburb,
            'processed': total,
            'new_urls': direct_new_urls
        }

    async def run_forever(self):
        """Continuously monitor all suburbs in a loop"""
        cycle = 0

        print("\n" + "=" * 80)
        print("CONTINUOUS URL TRACKING MONITOR")
        print("=" * 80)
        print(f"Suburbs: {', '.join(self.suburbs)}")
        print(f"Recheck concurrency: {self.concurrency}")
        print("Press Ctrl+C to stop")
        print("=" * 80)

        try:
            while True:
                cycle += 1
                cycle_start = datetime.now(UTC)

                print(f"\n{'=' * 80}")
                print(f"CYCLE {cycle} - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'=' * 80}")

                cycle_stats = []

                for suburb in self.suburbs:
                    stats = await self.monitor_suburb(suburb, cycle)
                    cycle_stats.append(stats)

                cycle_end = datetime.now(UTC)
                duration = (cycle_end - cycle_start).total_seconds()

                # Cycle summary
                print(f"\n{'=' * 80}")
                print(f"CYCLE {cycle} SUMMARY")
                print(f"{'=' * 80}")
                print(f"Duration: {duration/60:.1f} minutes")
                print(f"Properties checked: {sum(s['processed'] for s in cycle_stats):,}")
                print(f"New URLs discovered: {sum(s['new_urls'] for s in cycle_stats)}")
                for stats in cycle_stats:
                    print(f"  - {stats['suburb']}: {stats['new_urls']}")
                print(f"{'=' * 80}")

                # Throttle — sleep so we run at most one cycle per CYCLE_INTERVAL_SECONDS.
                # If a cycle already took longer than the interval, start the next immediately.
                sleep_seconds = max(0, self.CYCLE_INTERVAL_SECONDS - duration)
                if sleep_seconds > 0:
                    print(f"\n💤 Sleeping {sleep_seconds/60:.1f} min before CYCLE {cycle + 1}...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    print(f"\nStarting CYCLE {cycle + 1}...")

        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("⚠️  MONITOR STOPPED BY USER")
            print("=" * 80)
            print(f"Completed {cycle} cycle(s)")
            print("All data saved to MongoDB and JSON files")
            print("=" * 80)


if __name__ == "__main__":
    # This will be used by url_tracking_run.py
    pass
