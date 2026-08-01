# onthehouse.com.au — scraping notes & handoff

**Written 2026-08-01** after building the for-lease guard (`scripts/rental_listings_sync.py`).
Everything below was **measured live from this VM**, not inferred from docs. Where a number
is a measurement, the sample size is stated.

Purpose of this doc: give a separate session enough to evaluate a **parallel onthehouse
ingest** alongside the nightly Domain orchestrator, without re-deriving any of it.

---

## 1. Why this source matters

We currently have three property-data sources and each has a hole:

| Source | Covers | Hole |
|---|---|---|
| Domain scrape (nightly orchestrator) | for sale, sold, withdrawn | Akamai-blocks our IP → **every request costs Bright Data proxy spend**; sold capture runs ~40-50% below PropRadar (memory `data_source_undercapture_reset`); **no lease state at all** |
| PropRadar API (Hobby, 20k calls/mo) | current listings, sold, AVM, DOM | **No lease/rental data whatsoever** (see §6); `/properties/search` is a listing+sold index, not a cadastral DB; 2 calls per address |
| QLD cadastral (in `Gold_Coast`) | every address, lot/plan | static — no market state |

**onthehouse fills all three holes at once**: rent + sale + sold, per-suburb indexes,
**direct fetch from this VM with no proxy**, and structured JSON rather than HTML.

It is CoreLogic-backed (images come from `images.corelogic.asia`, ids are `clPropertyId`),
so it is a genuinely independent second opinion on Domain.

---

## 2. Access — no Bright Data needed

Plain `curl_cffi` with Chrome impersonation works. **No proxy, no API key, no auth.**

```python
from curl_cffi import requests as cffi
r = cffi.get(url, impersonate="chrome120", timeout=45)   # 200 OK
```

Observed: no rate limiting hit at ~1 request/1.5s across ~60 requests. No CAPTCHA, no 403.
Be a polite client anyway — `PAGE_PAUSE_S = 1.5` in the existing script.

Pages are **large**: 0.5-2.8 MB each. This dominates runtime, not the pause. Budget
accordingly (the first 12-suburb rental sync took ~15 min before the stop rule was fixed).

⚠ Untested: whether sustained daily volume attracts blocking. Start conservative, and
treat a fetch failure as UNKNOWN, never as "no results" (see §7).

---

## 3. URL patterns (all verified 200)

```
https://www.onthehouse.com.au/property-for-rent/qld/{suburb}-{postcode}
https://www.onthehouse.com.au/property-for-sale/qld/{suburb}-{postcode}
https://www.onthehouse.com.au/sold/qld/{suburb}-{postcode}
https://www.onthehouse.com.au/property/qld/{suburb}-{postcode}/{slug}      # profile
https://www.onthehouse.com.au/property-for-rent/qld/{suburb}-{postcode}/{slug}
```

- suburb slug is lowercase-hyphenated + postcode, e.g. `burleigh-waters-4220`.
- Pagination: `?page=N` (verified: page 2 returns a different set). `?pageSize=` is IGNORED.
- The property-profile slug carries a trailing numeric id, e.g.
  `70-burleigh-st-burleigh-waters-qld-4220-5272685`. **Note the abbreviated street type**
  (`st`, not `street`) — building these URLs from our own addresses will need care.
- A sale-listing URL and a rent-listing URL for the same property use different prefixes;
  guessing the wrong one 404s.

---

## 4. The data is embedded JSON, not HTML — parse that

Do **not** scrape the rendered cards. Every index page embeds structured records:

```json
{"category":"RentalListing","clPropertyId":"47726159","othPropertyId":"3895546",
 "address":{"formattedAddress":"70/22 BARBET PL, BURLEIGH WATERS, QLD 4220",
            "unitNumber":"70","streetNumber":"22","streetName":"BARBET",
            "streetType":"PL","suburb":"BURLEIGH WATERS","stateCode":"QLD",
            "postCode":"4220","location":{...}},
 "beds":2,"baths":1,"carSpaces":2,"type":"Unit",
 "listing":{"listedDate":"2026-07-28","listedDateTime":"...","lastModifiedDateTime":"...",
            "agency":{"agencyId","name","email","phoneNumber","logo","agents":[...]},
            "description":"...","displayPrice","showPrice","inspectionTimes","hasVirtualTour"},
 "id":"18769089"}
```

There is **no `__NEXT_DATA__` block** — the records sit loose in the HTML. Extract them by
finding `{"category":"<X>"` and **brace-matching** (string-aware, so braces inside
`description` don't break it). A working implementation is
`rental_listings_sync._json_objects()` — reuse it rather than rewriting.

### `category` values seen per page type

| Page | Categories present |
|---|---|
| `/property-for-rent/...` | `RentalListing` ×25/page |
| `/property-for-sale/...` | `SaleListing` ×25/page |
| `/sold/...` | `Property` ×24/page, `RecentlySold` ×1 (the latter is just a suburb header) |
| `/property/...` (profile) | `Property` ×11, `SaleListing` ×6, `RentalListing` ×5, `property` ×2 |

### Field shapes

**`SaleListing`** adds over RentalListing: `floorSize`, `landSize`, `landSizeUnit`,
`underOffer`, `recentlySold`, `isSoldListing`, `hasVirtualTour`,
`listing.displayPrice`/`showPrice`/`inspectionTimes`.

**`Property`** (on the sold index) is the richest:
```
clPropertyId, othPropertyId, address{...}, beds, baths, carSpaces, yearBuilt, type,
landSizeUnit, legalAttributes,
guesstimate{price, calculationDate, errorRate, fromPrice, toPrice, confidence},   # AVM
lastSale{eventDate, salePrice, saleSource, sellingAgency{...}, type},
recentlySold, isRestrictedSource, isSoldListing, links[]
```

---

## 5. Measured data quality (this is the important part)

**Sold index, 144 `recentlySold` records across Robina / Burleigh Waters / Varsity Lakes,
2 pages each:**

- **82%** carry a real `lastSale.salePrice` (the other 18% are `salePrice: 0` = withheld)
- **98%** carry an AVM `guesstimate` (price + from/to range + confidence + errorRate)
- Sale dates spanned **2026-04-28 → 2026-07-29**

Compare against what we already know:
- Our Domain sold scrape caps around **Feb 2026** and captures ~53-66% of PropRadar
  (memory `monthly_sold_refresh_and_capture_rate`, `data_source_undercapture_reset`).
- The PropRadar sold feed reached **23 Jul 2026** and has **no DOM and no list price**.

⇒ **onthehouse looks fresher than both, with 82% price coverage and a free AVM, at zero
marginal cost.** That is the headline reason to evaluate a parallel ingest. It should be
verified on a larger sample before anyone relies on it.

⚠ Do NOT assume `salePrice: 0` means $0 — it means withheld. Filter it out, never store it.

---

## 6. What onthehouse does NOT give you / traps

1. **Index pages include SURROUNDING suburbs.** Querying `burleigh-waters-4220` returned
   **157 records of which only 11 were actually Burleigh Waters** (58 Burleigh Heads,
   31 Robina, 25 Varsity Lakes, 17 Miami, 15 Mermaid Waters). File every record under its
   OWN `address.suburb`/`postCode`, never under the suburb you queried. This also breaks
   the naive "stop paging when no new record appears" rule — page after page keeps
   yielding new *neighbouring* records. Stop on growth of the **target** suburb.
   (It's also a bonus: 12 queried suburbs produced 348 rentals across 20+ suburbs.)
2. **Reconcile only after all fetches complete.** A Burleigh Waters rental first seen via
   the Robina page would be wrongly deactivated by the Burleigh Waters pass otherwise.
3. **Street types are abbreviated** (`PL`, `DR`, `CCT`) and addresses are UPPERCASE. Join on
   a key that drops the street type entirely — see `address_key()` / `key_from_components()`
   in `rental_listings_sync.py` (verified 5/5 on real pairs, incl. `12-14` number ranges).
4. **PropRadar has no lease data** — confirmed three ways so nobody re-tests it:
   `/properties/{id}.rental` is an AVM estimate (`confidence: "low"`);
   `/suburbs/QLD/{s}/listings?listing_type=rent` **silently ignores** the param (the echoed
   `query` object omits it) and returns sale listings; `/suburbs/QLD/{s}/rentals` 404s.
   That is why this scraper exists.
5. **Property-profile pages are one request each** — fine for enrichment of a known set,
   not for enumeration. Use the suburb indexes to enumerate.
6. The profile page states status in plain prose too, e.g.
   *"This Property is currently listed for sale with Realty Blue - BURLEIGH HEADS"* — useful
   as a human-readable cross-check, but parse the JSON for anything programmatic.

---

## 7. Failure handling (non-negotiable)

A failed or empty scrape must **never** be read as "no listings here" — that would silently
clear every address in the suburb and, downstream, green-light a mail-out to an owner who
is actively selling or leasing.

`parse_suburb()` returns `None` on fetch failure (distinct from `[]`), and `sync()` only
deactivates records inside suburbs whose index it actually fetched. Keep that property in
anything new.

---

## 8. Code that already exists (reuse, don't rewrite)

| File | What it gives you |
|---|---|
| `scripts/rental_listings_sync.py` | Full working ingest: `_json_objects()` brace-matching parser, `address_key()` / `key_from_components()` join keys, per-suburb pagination with a time budget, true-suburb filing, deferred reconciliation, `active`/`ended_at` lifecycle, `job_run` heartbeat. **The template for a sale/sold ingest — swap `_REC_START` to `SaleListing` / `Property`.** |
| `scripts/propradar/market_status.py` | The consumer side: `check()` (cached 7d) + `verdict()` — how sale + lease status combine into a mailability decision, incl. the 90-day Form 6 window. |
| `scripts/propradar/propradar_client.py` | PropRadar wrapper, for cross-verification. |
| `shared/domain_fetch.py` | Domain-via-Bright-Data, for comparison of cost/complexity. |

**Live now:** `system_monitor.rental_listings` — 348 active listings, cron 23:30 daily,
heartbeat `rental_listings_sync` on the Systems Health sheet.

---

## 9. Suggested questions for the parallel-ingest session

1. Does onthehouse sold data actually beat our Domain capture at scale? Sample a full
   quarter across the 3 core suburbs and compare counts + prices against PropRadar
   (`propradar_client.fetch_all_sold`) and `Gold_Coast listing_status:sold`.
2. Is `guesstimate` (their AVM) any good? We have 2,153 real sold outcomes to backtest it
   against — cheap validation, and a possible second opinion alongside our comparable-sales
   `reconciled_valuation`.
3. Can the **sale** index replace some Bright Data spend in the nightly Domain run, or is
   Domain still needed for DOM / price history / withdrawn detection? (PropRadar DOM is
   current-campaign only; onthehouse gives `listedDate`, from which DOM is derivable.)
4. Does the `links[]` array on each record expose a stable per-property URL we can use to
   build profile URLs without guessing the abbreviated-street-type slug?
5. Broadening: the suburb indexes make it cheap to cover suburbs beyond our core three.
   Where does that help (off-market coverage, comparables) vs just adding noise?
6. Legal/ToS review before any large-scale ingest — that call is Will's, not the agent's.
