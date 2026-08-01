"""Suburb scope for the onthehouse ingest.

CORE only (Will, 2026-08-01): the southern-end target market. A 40-suburb sweep was
measured first (683 requests / 16.9 min / zero blocks) and deliberately pulled back —
expansion is a later decision, not a default.

Slugs are `{suburb}-{postcode}` and were verified against onthehouse's own
sitemap/suburb_profiles.xml, so none of them 404. `collection` is the Gold_Coast
collection to join against; `suburb` is the plain name to pass to
matching.address_key(suburb=...), which is required for docs whose stored address
carries no suburb.
"""
from __future__ import annotations

CORE = [
    {"slug": "robina-4226",          "collection": "robina",          "suburb": "robina"},
    {"slug": "varsity-lakes-4227",   "collection": "varsity_lakes",   "suburb": "varsity lakes"},
    {"slug": "burleigh-waters-4220", "collection": "burleigh_waters", "suburb": "burleigh waters"},
]

# Measured 2026-08-01 for the core three (houses, both index types):
#   sale  17 pages / 0.7 min      sold (deep) 60 pages / 3.0 min
# The nightly sold pass is shallow (SOLD_PAGES_NIGHTLY) once the backfill has run.
BY_SLUG = {s["slug"]: s for s in CORE}


def slugs() -> list[str]:
    return [s["slug"] for s in CORE]
