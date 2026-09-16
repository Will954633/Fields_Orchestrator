# The Two Sold-Data Pipelines — and the Recurring "Recent Data Looks Wrong" Error

**Owner:** ops · **Created:** 2026-09-16 · **Status:** living doc
**Read this before building, editing, or trusting any metric that counts *recent* sales
(days-on-market, sales volume, median price, absorption, "X sold in the last N months").**

---

## 1. One-paragraph summary

We hold Gold Coast sold data in **two independent pipelines that disagree about the
recent past**. `scraped_data.property_timeline` (our per-property scrape history) is
**complete for old months but badly under-filled for the last ~2–10 months**, because a
sale only enters a property's timeline when we *re-scrape that property* after Domain
posts the sale — and the sales we're slowest to re-scrape are the quick ones. Any recent-
window metric built on `property_timeline` is therefore **under-counted and biased slow /
low-volume**, and it "heals" over the following year as the backfill catches up.
`system_monitor.domain_sold` (a fresh Domain `searchListings` cron) does **not** have this
lag and is the correct source for recent windows. Every time "the recent numbers look
wrong," this is almost always why.

---

## 2. The two pipelines

| | `scraped_data.property_timeline` (+ `listing_status='sold'`) | `system_monitor.domain_sold` |
|---|---|---|
| What it is | Per-property Domain sale **history**, accumulated every time we scrape that property | Fresh Domain **`searchListings`** cron pulling the newest sold listings per suburb |
| Keyed on | `Gold_Coast.{suburb}` docs | `suburb_key` = `"{suburb}-{postcode}"` (e.g. `robina-4226`) |
| DOM field | `...property_timeline[].days_on_market` | `dom_days` |
| Type field | resolved (`classified_property_type`→features→`property_type`) | `dwelling` = `house`/`unit`/`other` (already normalised) |
| Recent-window completeness | **Poor** — fills in over ~2–12 months | **Good** — near-complete current snapshot |
| Old-window completeness | **Excellent** — years of accumulation | Good (searchListings reaches back ~2016) |
| Bias in recent window | **Slow / low-volume** (see §3) | Minimal |
| Right for | 12-month+ / historical / seasonal baselines | **Recent trailing windows (3m, "current", last N months)** |

There is also **PropRadar** (`Gold_Coast.propradar_sold`, target suburbs only) as an
independent yardstick, and REA/Domain public figures. Use them to sanity-check.

---

## 3. Why `property_timeline` under-captures recent months (the mechanism)

A sale enters a property's timeline **only when we re-scrape that specific property** and
Domain has by then posted the sale to its history. That makes capture **correlated with
how long the home was listed**:

- **Long-campaign home (high DOM):** sat in our nightly for-sale scrape for months, so we
  were already pulling its page. The night Domain marks it sold, we catch it fast →
  **present in the recent bucket.**
- **Short-campaign home (low DOM):** listed briefly, entered/left the market between our
  passes; once off-market we stop scraping it, so its sold event only lands on a later
  sweep — often **months later** → **missing from the recent bucket, arrives later.**

Two consequences, both toward the present:

1. **Volume looks collapsed** — recent months show a fraction of their true sale count.
2. **DOM/median looks inflated slow** — because the sales we *have* captured skew
   long-campaign, and the quick ones haven't landed yet.

Both **self-correct** as the backfill fills in, which is why the 12-month figure (mostly
old, filled months) stays honest while the trailing-3-month figure is wrong.

> ⚠️ **Do not compare a fresh month to a year-old month in `property_timeline`.** Old
> months have had a year+ to accumulate backfilled history and read ~2–3× higher than
> they did when fresh. That comparison **overstates** any recent "drop" — it is an
> artifact of the baseline, not the market. (This is how a genuine ~30% recent shortfall
> was first mis-read as an "8× collapse".)

---

## 4. How it has manifested (same root cause, different symptoms)

- **DOM inflation (2026-09-16).** "How Long Are GC Homes Taking to Sell?" showed **houses
  3-month median 61d (n=317)** while the sibling "Big Cities" chart — same panel, same
  type, same window, sourced from `domain_sold` — showed **39d (n=780)**. At 12 months
  they agreed (28 vs 29). Two charts on one public page contradicting each other.
  → Fixed by re-sourcing the chart to `domain_sold` (61→40). See `build_gc_dom_by_type.py`.
- **Per-suburb DOM (same day).** Robina's stored `robina_days_on_market.trailing_3m` = **50d
  (n=31)** vs `domain_sold` **40d** and PropRadar **37d** and REA ~same. **Still outstanding**
  — `calculate_days_on_market_data` in `precompute_market_charts.py` reads the old sources.
- **"Volume collapse."** Raw `is_sold` timeline counts read Mar 481 → Aug 119 for 2026,
  which looked like a market crash; PropRadar showed volume roughly flat (mild winter
  softening). The "collapse" was capture lag + the fresh-vs-backfilled baseline error.
- **Related past incidents:** the sold capture-rate / under-capture resets
  (`monthly_sold_refresh_and_capture_rate`, `data_source_undercapture_reset` in memory) are
  the same family — recent sold data being treated as complete when it isn't.

---

## 5. Diagnostic playbook — is a "recent looks wrong" number this bug?

Run these before concluding a recent metric reflects the market:

1. **Compare `n` across sources for the same window.** Pull the count from `domain_sold`
   (and PropRadar for target suburbs) for the identical suburb/type/window. If
   `property_timeline`'s n is materially lower, it's under-captured — stop trusting its
   median/volume for that window.
2. **Check the 12-month figure.** If the trailing-12m median from the *same* source is
   sane (e.g. ~28d) but the trailing-3m is wild (e.g. 61d), the recent window is the
   problem, not the market — the 12m has backfilled, the 3m hasn't.
3. **Prior-year seasonality test.** Measure the same calendar months in 2023/24/25 (fully
   settled). If they show no such dip/spike, the current one is capture, not seasonality.
   (GC winter JJA/MAM sold-volume ratio is ~0.9–1.0 historically; 2026 read 0.43 —
   artifact.)
4. **Independent yardstick.** Cross-check against PropRadar (`propradar_sold`) and public
   REA/Domain. If they disagree with `property_timeline` recent numbers, believe them.
5. **`first_listed_timestamp` is a real list date** (validated 2026-09-16: median diff 0d
   vs Domain's own DOM). You can compute list→sold DOM from it for spot checks.

---

## 6. The rule (guardrail)

- **Recent windows (trailing 3m / "current" / "last N months", N ≲ 12) → use
  `domain_sold`** (or PropRadar for the three target suburbs). Never `property_timeline`
  alone.
- **Historical / 12-month+ / seasonal baselines → `property_timeline` is fine** (it's
  complete there and reaches back further with type resolution).
- **Never compare a fresh month against a year-backfilled month in `property_timeline`.**
- **Any new recent-sales metric** (absorption, months-of-supply numerator, "sold this
  month", price momentum) must state its source and pass the §5 checks. Prefer
  `domain_sold`; if you must use `property_timeline` for a recent window, lag the window
  or disclose the incompleteness.
- **When two surfaces show the same metric, they must use the same source.** The bug that
  made this doc necessary was two same-page charts on two different pipelines.

---

## 7. Status: fixed vs outstanding

| Surface | Source | Status |
|---|---|---|
| "How Long Are GC Homes Taking to Sell?" (`gc_dom_by_type.json`) | `domain_sold` | ✅ Fixed 2026-09-16 |
| "Do Homes Sell Faster… Big Cities?" (`gc_vs_capitals_dom.json`) | `domain_sold` | ✅ Already correct |
| Per-suburb DOM charts (`{suburb}_days_on_market`, `calculate_days_on_market_data`) | `property_timeline` + `listing_status` | ⚠️ **Outstanding** — same defect (Robina 50 vs true ~40) |
| Per-suburb **sales volume** & **median price** recent quarters (`precompute_market_charts.py`) | `property_timeline` + `listing_status` | ⚠️ **Audit** — recent quarters likely under-captured the same way |
| Absorption / months-of-supply recent sold-rate | mixed (PropRadar preferred) | ⚠️ Audit (see market-pressure scoping) |

**Immediate next task:** rewire `calculate_days_on_market_data` (per-suburb DOM) to
`domain_sold` — same change as `build_gc_dom_by_type.py`, houses-only (`dwelling='house'`),
preserving the full `{suburb}_days_on_market` schema — then verify across all suburb pages,
not just Robina.

---

## 8. References
- `scripts/build_gc_dom_by_type.py` — the fixed GC-wide builder (docstring explains the switch)
- `scripts/capitals_dom/build_capitals_dom_json.py` — the already-correct `domain_sold` reader (reuse `_gc_panel_slugs`)
- `08_Market_Narrative_Engine/precompute_market_charts.py` — the per-suburb builder still on the old sources
- `logs/fix-history/2026-09-16.md` — `[DOM-TIMELINE-RECENCY-UNDERCAPTURE]`
- Memory: `gc_dom_by_type_chart`, `monthly_sold_refresh_and_capture_rate`, `data_source_undercapture_reset`, `market_pressure_metrics_scoping`
- `AGENTS.md` sold-source table (already flags `property_timeline` as "Weeks — Domain publishing lag")
