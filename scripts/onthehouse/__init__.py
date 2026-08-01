"""onthehouse.com.au ingest — a second, independent opinion on Domain.

Measured 2026-08-01 across Robina / Varsity Lakes / Burleigh Waters (houses only,
like-for-like against Domain records refreshed within 14 days):

  for sale : Domain 176, OTH 181, matched 126  -> 72% overlap, OTH adds +31%
  sold 12m : Domain 508, OTH 618, matched 439  -> Domain sees 74% of the union

Where they agree they REALLY agree — 539/554 matched sale prices identical to the
dollar, and property type agreed on 769/769 matched pairs — so the ~26-28% each side
misses is genuine coverage, not a join artefact. Neither source alone is complete.

Consequences that shape every module here:
  - Domain stays the system of record. onthehouse has no floor plans, no usable images
    (CoreLogic signed/watermarked CDN), no withdrawn state and no price history, all of
    which steps 6/11/106/108/120 depend on. We write to our OWN collections and join on
    an address key; we never write into Gold_Coast.
  - ABSENCE IS NOT EVIDENCE. 24% of genuinely-live Domain listings are missing from the
    onthehouse index, so "not in onthehouse" must never be read as "not for sale".
  - Sold is a hard rolling 12-month window (verified: the index stops at exactly 12
    months even when paged to exhaustion). It is an overlay, never a truncation of the
    deeper history we already hold.

See scripts/ONTHEHOUSE_SCRAPING.md for access notes, URL patterns and field shapes.
"""
