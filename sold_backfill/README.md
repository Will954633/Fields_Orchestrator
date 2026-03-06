# Sold Property Backfill — Domain.com.au

Scrapes Domain.com.au's **sold-listings search results** for target suburbs and updates the `Gold_Coast` database with sold records. Designed to fill the gap left by the reactive sold monitor (step 103), which only catches sales for properties already tracked as `listing_status: "for_sale"`.

## Why this exists

The nightly pipeline's sold monitor (step 103 — `monitor_sold_properties.py`) checks each active listing on Domain to see if it has been marked as sold. This misses:

- Properties that sold before they were ever scraped into our system
- Properties that were delisted and re-listed as sold between scrape cycles
- Properties sold by agents who don't update Domain promptly (delayed status change)

This scraper goes directly to Domain's sold-listings search, which is the canonical source of all completed sales.

## Quick start

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a

# Default: 3 target suburbs, last 60 days
python3 sold_backfill/scrape_recent_sold.py

# Single suburb
python3 sold_backfill/scrape_recent_sold.py --suburb robina

# Wider window
python3 sold_backfill/scrape_recent_sold.py --days 90

# Preview only (no DB writes)
python3 sold_backfill/scrape_recent_sold.py --dry-run --verbose
```

## How it works

1. **Search results scraping** — Loads `domain.com.au/sold-listings/<suburb>-qld-<postcode>/?ssubs=0` with headless Chrome. Paginates through results (20 per page, most recent first).

2. **Card parsing** — Extracts from each listing card directly (no need to visit individual property pages):
   - Sold date (e.g. "Sold by private treaty 06 Mar 2026")
   - Sale price (e.g. "$1,877,000") or "Price Withheld"
   - Sale method (private treaty / auction / expression of interest)
   - Address, beds, baths, parking, land size, property type

3. **Cutoff** — Stops paginating when it hits a sold date older than the `--days` window (default 60).

4. **DB matching** — For each scraped record, tries to find an existing document in `Gold_Coast.<suburb>`:
   - Match by `listing_url` (exact, indexed)
   - Match by listing ID suffix in URL
   - Match by exact address
   - Match by street portion (case-insensitive prefix)

5. **Update/Insert** — Matched records get `listing_status: "sold"` + sold details. Unmatched records are inserted as new documents.

## Target suburbs

| Suburb | Postcode | Collection |
|--------|----------|------------|
| Robina | 4226 | `robina` |
| Varsity Lakes | 4227 | `varsity_lakes` |
| Burleigh Waters | 4220 | `burleigh_waters` |

To add more suburbs, edit the `TARGET_SUBURBS` list in `scrape_recent_sold.py`.

## CosmosDB rate limiting

The script handles Azure CosmosDB 429 (TooManyRequests) errors automatically:
- Retries up to 3 times per operation with backoff
- Extracts `RetryAfterMs` from error response when available
- Paces DB operations with a 0.5s delay every 5 records

## Output fields written

For **updated** records:
- `listing_status` → `"sold"`
- `sold_date` → `"YYYY-MM-DD"`
- `sale_price` → `"$X,XXX,XXX"` (or None if withheld)
- `sale_method` → `"private treaty"` / `"auction"` / `"expression of interest"`
- `sold_updated_at` → ISO timestamp
- `sold_scrape_source` → `"domain_sold_listings_backfill"`

For **new** records (all the above plus):
- `address`, `listing_url`, `suburb`, `postcode`, `state`
- `bedrooms`, `bathrooms`, `parking`, `land_size`, `land_size_sqm`, `property_type`
- `created_at` → ISO timestamp

## First run results (2026-03-06)

| Suburb | Scraped | Already correct | Updated | New inserts |
|--------|---------|----------------|---------|-------------|
| Robina | 62 | 18 | 3 | 41 |
| Varsity Lakes | 41 | 6 | 2 | 33 |
| Burleigh Waters | 25 | 11 | 0 | 14 |
| **Total** | **128** | **35** | **5** | **88** |

## Files

- `scrape_recent_sold.py` — Main scraper script (also at `scripts/scrape_recent_sold.py`)
- `README.md` — This file
