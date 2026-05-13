#!/usr/bin/env python3
"""
Direct Agency Listing Scraper for Robina

Bypasses SearXNG by scraping listing pages directly from real estate agency
websites. Extracts property URLs, addresses, and listing statuses.

Tested agencies (Robina coverage):
  Ray White Robina, Ray White TMG, Ray White Malan & Co,
  RE/MAX GC, GCSR, Astras, McDermott Residential,
  Robina Realty, Robina Village RE, First National Robina, Coastal

Known limitation: Harcourts search is JS SPA — location filter doesn't render
server-side. McGrath uses Vercel challenge — blocked from datacenter IPs.
"""

import asyncio
import random
import re
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, quote_plus
from playwright.async_api import async_playwright


ANTI_DETECT_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--no-sandbox',
    '--disable-dev-shm-usage',
]

# UA rotation pool — mirrors robust_extractor.USER_AGENTS. Pick one per agency.
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
"""

# Adaptive backoff — if an agency returns 403/429, skip it for this many
# cycles. Backoff doubles on consecutive failures, caps at 24 cycles
# (~12 hours at 30-min cadence).
DEFAULT_BACKOFF_CYCLES = 4
MAX_BACKOFF_CYCLES = 24

# In-process per-agency state — reset on service restart. Tracks last
# failure time, consecutive failure count, and cooldown-until cycle.
# Keyed by agency name. Lives at module level so the same DirectAgencyScraper
# instance across cycles shares state.
_AGENCY_HEALTH: dict = {}


def _backoff_state(agency_name: str) -> dict:
    return _AGENCY_HEALTH.setdefault(
        agency_name,
        {'consecutive_failures': 0, 'cooldown_until': None, 'last_status': None},
    )


def _agency_should_skip(agency_name: str) -> bool:
    """True if the agency is in cooldown and shouldn't be hit this cycle."""
    state = _AGENCY_HEALTH.get(agency_name)
    if not state or not state.get('cooldown_until'):
        return False
    return datetime.utcnow() < state['cooldown_until']


def _agency_record_outcome(agency_name: str, status: int, hard_failure: bool = False) -> None:
    """Update health state after an agency request. status=0 means error."""
    state = _backoff_state(agency_name)
    state['last_status'] = status
    if hard_failure or status in (403, 404, 429, 503):
        state['consecutive_failures'] += 1
        backoff = min(MAX_BACKOFF_CYCLES, DEFAULT_BACKOFF_CYCLES * (2 ** (state['consecutive_failures'] - 1)))
        # 30-min cycles → backoff cycles ≈ backoff * 30 min
        state['cooldown_until'] = datetime.utcnow() + timedelta(minutes=30 * backoff)
        print(f"   ⏸  {agency_name}: backoff {backoff} cycles (consecutive failures: {state['consecutive_failures']})")
    else:
        # Success — reset
        if state['consecutive_failures'] > 0:
            print(f"   ✅ {agency_name}: recovered after {state['consecutive_failures']} failures")
        state['consecutive_failures'] = 0
        state['cooldown_until'] = None

# Address regex: matches "12 Smith Street, Robina" or "4/12 Smith St Robina"
# Also handles "34-38 Street", "14b Street", unit formats "2301/22-34 Street"
ADDR_RE = re.compile(
    r'(\d+[A-Za-z]?\s*(?:[/ -]\s*\d+(?:-\d+)?\s+)?'
    r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+'
    r'(?:Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Court|Ct|Crt|Place|Pl|'
    r'Circuit|Cct|Close|Cl|Crescent|Cres|Way|Boulevard|Blvd|'
    r'Parade|Pde|Lane|Ln|Terrace|Tce))'
    r'\s*,?\s*Robina',
    re.IGNORECASE,
)

# Listing URL patterns — property/listing paths with numeric IDs
LISTING_URL_RE = re.compile(
    r'/(propert|listing|sold|for-sale|sale|residential-for-sale)/.*\d',
    re.IGNORECASE,
)


class AgencyConfig:
    """Configuration for a single agency's listing page(s)."""
    def __init__(self, name, urls, wait_sel=None, wait_time=3,
                 robina_filter=True, link_pattern=None):
        self.name = name
        self.urls = urls  # list of URLs to scrape
        self.wait_sel = wait_sel  # CSS selector to wait for
        self.wait_time = wait_time  # seconds to sleep after load
        self.robina_filter = robina_filter  # only keep Robina URLs
        self.link_pattern = link_pattern  # custom regex for listing links


# All Robina agency configs
ROBINA_AGENCIES = [
    AgencyConfig(
        'Ray White Robina',
        ['https://raywhiterobina.com.au/properties/residential-for-sale'
         '?suburbPostCode=Robina+4226&sort=creationTime+desc'],
        wait_sel='a[href*="/properties/"]',
        link_pattern=re.compile(r'/properties/residential-for-sale/qld/robina', re.I),
    ),
    AgencyConfig(
        'Ray White TMG',
        ['https://raywhitetmg.com.au/properties/residential-for-sale'
         '?suburbPostCode=Robina+4226&sort=creationTime+desc'],
        wait_sel='a[href*="/properties/"]',
        link_pattern=re.compile(r'/properties/residential-for-sale/qld/robina', re.I),
    ),
    AgencyConfig(
        'Ray White Malan & Co',
        ['https://raywhitemalanandco.com.au/properties/residential-for-sale'
         '?suburbPostCode=Robina+4226&sort=creationTime+desc'],
        wait_sel='a[href*="/properties/"]',
        link_pattern=re.compile(r'/properties/residential-for-sale/qld/robina', re.I),
    ),
    AgencyConfig(
        'RE/MAX GC',
        ['https://www.remaxgc.com.au/buy'],
        wait_sel='a[href*="/property/"]',
        wait_time=4,
        link_pattern=re.compile(r'/property/\w+-qld-robina', re.I),
    ),
    AgencyConfig(
        'GCSR',
        ['https://gcsr.com.au/buy/'],
        wait_sel='a[href*="/property/"]',
        wait_time=3,
        link_pattern=re.compile(r'/property/.*robina', re.I),
    ),
    AgencyConfig(
        'Astras',
        ['https://www.astras.com.au/'],
        wait_time=4,
    ),
    AgencyConfig(
        'McDermott Residential',
        ['https://mcdermottresidential.com.au/listings'
         '?saleOrRental=Sale&status=available_under_contract'
         '&suburb=Robina&sortby=dateListed-desc'],
        wait_time=5,
        link_pattern=re.compile(r'/listings/.*robina', re.I),
    ),
    AgencyConfig(
        'Robina Realty',
        ['https://robinarealty.com.au/'],
        wait_time=3,
        link_pattern=re.compile(r'/listing/[lr]\d+', re.I),
        robina_filter=False,  # homepage shows all listings; filter by address
    ),
    AgencyConfig(
        'Robina Village RE',
        [
            'https://robinavillagerealestate.com.au/houses-for-sale',
            'https://robinavillagerealestate.com.au/units-for-sale',
        ],
        wait_time=3,
        link_pattern=re.compile(r'/property/\d+/', re.I),
        robina_filter=False,
    ),
    AgencyConfig(
        'First National Robina',
        ['https://www.robinafn.com.au/Real-Estate-Search/Residential-Real-Estate'],
        wait_time=4,
    ),
    AgencyConfig(
        'Coastal',
        ['https://www.coastal.com.au/properties-for-sale/'],
        wait_sel='a[href*="/property/"]',
        wait_time=3,
        link_pattern=re.compile(r'/property/\w+-qld-', re.I),
        robina_filter=False,  # no Robina filter on their site
    ),
    AgencyConfig(
        'Ray White Surfers Paradise',
        ['https://raywhitesurfersparadise.com.au/properties/residential-for-sale'
         '?suburbPostCode=Robina+4226&sort=creationTime+desc'],
        wait_sel='a[href*="/properties/"]',
        link_pattern=re.compile(r'/properties/residential-for-sale/qld/robina', re.I),
    ),
]


def _normalise_address(addr_raw):
    """Normalise an address for comparison."""
    addr = addr_raw.strip().rstrip(',').strip()
    # Remove trailing 'Robina' / 'ROBINA' for the street portion
    addr = re.sub(r',?\s*Robina\s*$', '', addr, flags=re.I).strip()
    # Normalise whitespace
    addr = re.sub(r'\s+', ' ', addr)
    # Convert space-separated unit numbers to slash format
    # e.g. "1 40 Leopardwood Circuit" → "1/40 Leopardwood Circuit"
    # e.g. "3 1-7 Pine Valley Drive" → "3/1-7 Pine Valley Drive"
    addr = re.sub(r'^(\d+[A-Za-z]?)\s+(\d+(?:-\d+)?)\s+([A-Z])', r'\1/\2 \3', addr)
    return addr


def _extract_address_from_url(url):
    """Try to extract an address from a listing URL slug."""
    path = urlparse(url).path
    # Strip listing ID prefix: /listing/l39019316-17-broadview-place-robina-...
    path_clean = re.sub(r'/[lr]?\d{6,}-', '/', path)
    # Also strip trailing listing IDs: ...-robina-qld-1408273
    path_clean = re.sub(r'-\d{6,}$', '', path_clean)

    # Match: /32-outrigger-drive-robina or /4-12-smith-street-robina
    m = re.search(
        r'(\d+[a-z]?(?:-\d+)?)-([a-z]+-(?:[a-z]+-)*'
        r'(?:street|st|road|rd|drive|dr|avenue|ave|court|ct|place|pl|'
        r'circuit|cct|close|cl|crescent|cres|way|boulevard|blvd|'
        r'parade|pde|lane|ln|terrace|tce))-robina',
        path_clean, re.I,
    )
    if m:
        num = m.group(1).replace('-', '/')
        street = m.group(2).replace('-', ' ').title()
        return f"{num} {street}"
    return None


class DirectAgencyScraper:
    """Scrapes listing pages from all configured agencies for a suburb."""

    def __init__(self, suburb='Robina', postcode='4226', agencies=None):
        self.suburb = suburb
        self.postcode = postcode
        self.agencies = agencies or ROBINA_AGENCIES
        self._results = {}

    async def scrape_harcourts(self, page):
        """
        Scrape Harcourts using their typeahead API + listing page.
        Two-pronged: API gives listing IDs/URLs, listing page gives addresses.
        """
        agency_data = {
            'agency': 'Harcourts',
            'listing_urls': [],
            'addresses': [],
            'errors': [],
        }

        # Prong 1: Typeahead API — returns individual listing IDs + addresses
        api_url = (
            f'https://harcourts.net/api/locations'
            f'?locale=au&status=current&query={self.suburb}'
        )
        try:
            resp = await page.goto(api_url, wait_until='domcontentloaded', timeout=10000)
            if resp and resp.status == 200:
                body = await page.locator('body').inner_text()
                data = json.loads(body)
                for entry in data.get('data', []):
                    if entry.get('searchType') != 'listingId':
                        continue
                    name = entry.get('name', '')
                    url_path = entry.get('url', '')
                    if url_path:
                        full_url = f'https://harcourts.net{url_path}'
                        if full_url not in agency_data['listing_urls']:
                            agency_data['listing_urls'].append(full_url)
                    # Extract address from name (e.g. "5 Montreal Crescent ROBINA QLD 4226 L16453579")
                    m = re.match(
                        r'(.+?)\s+(?:ROBINA|Robina)\s+QLD\s+\d{4}\s+[LR]',
                        name,
                    )
                    if m:
                        addr = _normalise_address(m.group(1).title())
                        if addr and addr not in agency_data['addresses']:
                            agency_data['addresses'].append(addr)
                print(f"  API: {len(agency_data['listing_urls'])} URLs, "
                      f"{len(agency_data['addresses'])} addresses")
        except Exception as e:
            agency_data['errors'].append(f"API error: {str(e)[:80]}")

        # Prong 2: Listing page with location ID — scrape addresses from body text
        listing_url = (
            'https://harcourts.net/au/listings/buy'
            f'?location={self.suburb}-4023&include-suburb=1&category=buy'
        )
        try:
            resp = await page.goto(listing_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(5)
            if resp and resp.status == 200:
                body = await page.locator('body').inner_text()
                matches = ADDR_RE.findall(body)
                for m_addr in matches:
                    norm = _normalise_address(m_addr)
                    if norm and norm not in agency_data['addresses']:
                        agency_data['addresses'].append(norm)
                # Also get listing links from the page
                all_links = await page.locator('a[href*="/listing/"]').all()
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and re.search(r'[lLrR]\d{5,}', href):
                            full = href if href.startswith('http') else f'https://harcourts.net{href}'
                            if 'robina' in full.lower() and full not in agency_data['listing_urls']:
                                agency_data['listing_urls'].append(full)
                    except:
                        continue
                print(f"  Page: +{len(matches)} addr matches from body")
        except Exception as e:
            agency_data['errors'].append(f"Listing page error: {str(e)[:80]}")

        return agency_data

    async def scrape_agency(self, page, config):
        """Scrape a single agency's listing page(s). Honors per-agency adaptive backoff."""
        agency_data = {
            'agency': config.name,
            'listing_urls': [],
            'addresses': [],
            'errors': [],
            'skipped_backoff': False,
        }

        # Skip if in cooldown
        if _agency_should_skip(config.name):
            state = _AGENCY_HEALTH[config.name]
            remaining_min = max(0, (state['cooldown_until'] - datetime.utcnow()).total_seconds() / 60)
            fails = state.get('consecutive_failures', 0)
            print(f"   ⏸  {config.name}: skipping (cooldown {remaining_min:.1f} min remaining, failures: {fails})")
            agency_data['skipped_backoff'] = True
            return agency_data

        # Jitter — small random delay so concurrent agency hits don't all
        # fire at the same instant (helps when agencies share a CDN edge).
        await asyncio.sleep(random.uniform(0.5, 2.5))

        for url in config.urls:
            try:
                resp = await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                status = resp.status if resp else 0

                if status in (403, 404, 429):
                    agency_data['errors'].append(f"HTTP {status} on {url}")
                    _agency_record_outcome(config.name, status)
                    continue

                # Wait for content
                if config.wait_sel:
                    try:
                        await page.wait_for_selector(config.wait_sel, timeout=8000)
                    except Exception:
                        pass

                await asyncio.sleep(config.wait_time)

                # Extract listing URLs
                all_links = await page.locator('a[href]').all()
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if not href or href.startswith(('mailto:', 'tel:', 'javascript:')):
                            continue
                        abs_url = urljoin(url, href)

                        is_listing = False
                        if config.link_pattern:
                            is_listing = bool(config.link_pattern.search(abs_url))
                        else:
                            is_listing = bool(LISTING_URL_RE.search(abs_url))

                        if is_listing and abs_url not in agency_data['listing_urls']:
                            # Filter to Robina if configured
                            if config.robina_filter and 'robina' not in abs_url.lower():
                                # Still check if URL contains a Robina address
                                url_addr = _extract_address_from_url(abs_url)
                                if not url_addr:
                                    continue
                            agency_data['listing_urls'].append(abs_url)
                    except Exception:
                        continue

                # Extract addresses from page text
                body = await page.locator('body').inner_text()
                matches = ADDR_RE.findall(body)
                for m in matches:
                    norm = _normalise_address(m)
                    if norm and norm not in agency_data['addresses']:
                        agency_data['addresses'].append(norm)

                # Also extract addresses from listing URLs
                for listing_url in agency_data['listing_urls']:
                    url_addr = _extract_address_from_url(listing_url)
                    if url_addr:
                        norm = _normalise_address(url_addr)
                        if norm and norm not in agency_data['addresses']:
                            agency_data['addresses'].append(norm)

            except Exception as e:
                agency_data['errors'].append(f"{url}: {str(e)[:100]}")
                _agency_record_outcome(config.name, 0, hard_failure=True)

        # Record success if we got any results without 403/429
        if agency_data['listing_urls'] or agency_data['addresses']:
            _agency_record_outcome(config.name, 200)
        elif not agency_data['errors']:
            # 200 response but no listings — neutral, don't penalise
            pass

        return agency_data

    async def scrape_all(self):
        """Scrape all configured agencies and return combined results."""
        print("=" * 60)
        print(f"DIRECT AGENCY SCRAPER — {self.suburb} {self.postcode}")
        print("=" * 60)
        start = datetime.now()

        all_listing_urls = []
        all_addresses = set()
        agency_results = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=ANTI_DETECT_ARGS)

            async def make_context():
                """Fresh context with a fresh UA — pickier WAFs (Cloudflare,
                Vercel) fingerprint on UA + cookies. Per-agency rotation gives
                each agency a clean session."""
                ua = random.choice(USER_AGENTS)
                ctx = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=ua,
                    extra_http_headers={
                        'Accept-Language': 'en-AU,en;q=0.9',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    },
                )
                await ctx.add_init_script(INIT_SCRIPT)
                return ctx, ua

            for config in self.agencies:
                print(f"\n--- {config.name} ---")
                ctx, ua = await make_context()
                page = await ctx.new_page()
                print(f"   UA: {ua.split(')')[0].split('(')[-1][:30]}")
                try:
                    data = await self.scrape_agency(page, config)
                finally:
                    await ctx.close()
                agency_results.append(data)

                if data.get('skipped_backoff'):
                    continue
                print(f"  Listing URLs: {len(data['listing_urls'])}")
                print(f"  Addresses: {len(data['addresses'])}")
                if data['errors']:
                    for err in data['errors']:
                        print(f"  ERROR: {err}")

                for u in data['listing_urls']:
                    if u not in all_listing_urls:
                        all_listing_urls.append(u)
                for a in data['addresses']:
                    all_addresses.add(a)

            # Harcourts — special handler (API + listing page)
            print(f"\n--- Harcourts ---")
            ctx, _ = await make_context()
            page = await ctx.new_page()
            try:
                harcourts_data = await self.scrape_harcourts(page)
            finally:
                await ctx.close()
            agency_results.append(harcourts_data)
            print(f"  Listing URLs: {len(harcourts_data['listing_urls'])}")
            print(f"  Addresses: {len(harcourts_data['addresses'])}")
            if harcourts_data['errors']:
                for err in harcourts_data['errors']:
                    print(f"  ERROR: {err}")
            for u in harcourts_data['listing_urls']:
                if u not in all_listing_urls:
                    all_listing_urls.append(u)
            for a in harcourts_data['addresses']:
                all_addresses.add(a)

            await browser.close()

        elapsed = (datetime.now() - start).total_seconds()

        results = {
            'scrape_date': datetime.now().isoformat(),
            'suburb': self.suburb,
            'postcode': self.postcode,
            'elapsed_seconds': round(elapsed, 1),
            'summary': {
                'total_listing_urls': len(all_listing_urls),
                'total_unique_addresses': len(all_addresses),
                'agencies_scraped': len(agency_results),
            },
            'addresses': sorted(all_addresses),
            'listing_urls': all_listing_urls,
            'by_agency': agency_results,
        }

        print(f"\n{'=' * 60}")
        print(f"RESULTS SUMMARY")
        print(f"{'=' * 60}")
        print(f"Agencies scraped: {len(agency_results)}")
        print(f"Total listing URLs: {len(all_listing_urls)}")
        print(f"Unique Robina addresses: {len(all_addresses)}")
        print(f"Time: {elapsed:.1f}s")
        print(f"\nAddresses found:")
        for a in sorted(all_addresses):
            print(f"  {a}")

        return results


async def main():
    scraper = DirectAgencyScraper(suburb='Robina', postcode='4226')
    results = await scraper.scrape_all()

    outfile = 'direct_agency_results.json'
    with open(outfile, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {outfile}")


if __name__ == '__main__':
    asyncio.run(main())
