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


# GC-WIDE scope (added 2026-09-12, Will's go-ahead): every Gold_Coast suburb
# collection whose slug exists in onthehouse's own suburb_profiles sitemap
# (82 total incl. CORE; slugs are therefore known-good, not guessed). The
# 2026-08-01 measurement note above ("40-suburb sweep, 683 requests, 16.9 min,
# zero blocks — expansion is a later decision") is the load precedent; the
# later decision arrived when the GC-wide overview page needed coast-wide sold
# currency (wide-suburb Domain timeline capture died Nov 2025 — see fix-history
# 2026-09-12 [GC-OVERVIEW-STALE-TAIL+SAMPLE-SIZES]).
WIDE = [
    {"slug": "advancetown-4211", "collection": "advancetown", "suburb": "advancetown"},
    {"slug": "alberton-4207", "collection": "alberton", "suburb": "alberton"},
    {"slug": "arundel-4214", "collection": "arundel", "suburb": "arundel"},
    {"slug": "ashmore-4214", "collection": "ashmore", "suburb": "ashmore"},
    {"slug": "austinville-4213", "collection": "austinville", "suburb": "austinville"},
    {"slug": "beechmont-4211", "collection": "beechmont", "suburb": "beechmont"},
    {"slug": "benowa-4217", "collection": "benowa", "suburb": "benowa"},
    {"slug": "biggera-waters-4216", "collection": "biggera_waters", "suburb": "biggera waters"},
    {"slug": "bilinga-4225", "collection": "bilinga", "suburb": "bilinga"},
    {"slug": "bonogin-4213", "collection": "bonogin", "suburb": "bonogin"},
    {"slug": "broadbeach-4218", "collection": "broadbeach", "suburb": "broadbeach"},
    {"slug": "broadbeach-waters-4218", "collection": "broadbeach_waters", "suburb": "broadbeach waters"},
    {"slug": "bundall-4217", "collection": "bundall", "suburb": "bundall"},
    {"slug": "burleigh-heads-4220", "collection": "burleigh_heads", "suburb": "burleigh heads"},
    {"slug": "carrara-4211", "collection": "carrara", "suburb": "carrara"},
    {"slug": "cedar-creek-4207", "collection": "cedar_creek", "suburb": "cedar creek"},
    {"slug": "chevron-island-4217", "collection": "chevron_island", "suburb": "chevron island"},
    {"slug": "clagiraba-4211", "collection": "clagiraba", "suburb": "clagiraba"},
    {"slug": "clear-island-waters-4226", "collection": "clear_island_waters", "suburb": "clear island waters"},
    {"slug": "coolangatta-4225", "collection": "coolangatta", "suburb": "coolangatta"},
    {"slug": "coombabah-4216", "collection": "coombabah", "suburb": "coombabah"},
    {"slug": "coomera-4209", "collection": "coomera", "suburb": "coomera"},
    {"slug": "currumbin-4223", "collection": "currumbin", "suburb": "currumbin"},
    {"slug": "currumbin-valley-4223", "collection": "currumbin_valley", "suburb": "currumbin valley"},
    {"slug": "currumbin-waters-4223", "collection": "currumbin_waters", "suburb": "currumbin waters"},
    {"slug": "elanora-4221", "collection": "elanora", "suburb": "elanora"},
    {"slug": "gaven-4211", "collection": "gaven", "suburb": "gaven"},
    {"slug": "gilberton-4208", "collection": "gilberton", "suburb": "gilberton"},
    {"slug": "gilston-4211", "collection": "gilston", "suburb": "gilston"},
    {"slug": "guanaba-4210", "collection": "guanaba", "suburb": "guanaba"},
    {"slug": "helensvale-4212", "collection": "helensvale", "suburb": "helensvale"},
    {"slug": "highland-park-4211", "collection": "highland_park", "suburb": "highland park"},
    {"slug": "hollywell-4216", "collection": "hollywell", "suburb": "hollywell"},
    {"slug": "hope-island-4212", "collection": "hope_island", "suburb": "hope island"},
    {"slug": "jacobs-well-4208", "collection": "jacobs_well", "suburb": "jacobs well"},
    {"slug": "kingsholme-4208", "collection": "kingsholme", "suburb": "kingsholme"},
    {"slug": "labrador-4215", "collection": "labrador", "suburb": "labrador"},
    {"slug": "lower-beechmont-4211", "collection": "lower_beechmont", "suburb": "lower beechmont"},
    {"slug": "luscombe-4207", "collection": "luscombe", "suburb": "luscombe"},
    {"slug": "main-beach-4217", "collection": "main_beach", "suburb": "main beach"},
    {"slug": "maudsland-4210", "collection": "maudsland", "suburb": "maudsland"},
    {"slug": "mermaid-beach-4218", "collection": "mermaid_beach", "suburb": "mermaid beach"},
    {"slug": "mermaid-waters-4218", "collection": "mermaid_waters", "suburb": "mermaid waters"},
    {"slug": "merrimac-4226", "collection": "merrimac", "suburb": "merrimac"},
    {"slug": "miami-4220", "collection": "miami", "suburb": "miami"},
    {"slug": "molendinar-4214", "collection": "molendinar", "suburb": "molendinar"},
    {"slug": "mount-nathan-4211", "collection": "mount_nathan", "suburb": "mount nathan"},
    {"slug": "mudgeeraba-4213", "collection": "mudgeeraba", "suburb": "mudgeeraba"},
    {"slug": "natural-bridge-4211", "collection": "natural_bridge", "suburb": "natural bridge"},
    {"slug": "nerang-4211", "collection": "nerang", "suburb": "nerang"},
    {"slug": "neranwood-4213", "collection": "neranwood", "suburb": "neranwood"},
    {"slug": "norwell-4208", "collection": "norwell", "suburb": "norwell"},
    {"slug": "numinbah-valley-4211", "collection": "numinbah_valley", "suburb": "numinbah valley"},
    {"slug": "ormeau-4208", "collection": "ormeau", "suburb": "ormeau"},
    {"slug": "ormeau-hills-4208", "collection": "ormeau_hills", "suburb": "ormeau hills"},
    {"slug": "oxenford-4210", "collection": "oxenford", "suburb": "oxenford"},
    {"slug": "pacific-pines-4211", "collection": "pacific_pines", "suburb": "pacific pines"},
    {"slug": "palm-beach-4221", "collection": "palm_beach", "suburb": "palm beach"},
    {"slug": "paradise-point-4216", "collection": "paradise_point", "suburb": "paradise point"},
    {"slug": "parkwood-4214", "collection": "parkwood", "suburb": "parkwood"},
    {"slug": "pimpama-4209", "collection": "pimpama", "suburb": "pimpama"},
    {"slug": "reedy-creek-4227", "collection": "reedy_creek", "suburb": "reedy creek"},
    {"slug": "runaway-bay-4216", "collection": "runaway_bay", "suburb": "runaway bay"},
    {"slug": "south-stradbroke-4216", "collection": "south_stradbroke", "suburb": "south stradbroke"},
    {"slug": "southport-4215", "collection": "southport", "suburb": "southport"},
    {"slug": "springbrook-4213", "collection": "springbrook", "suburb": "springbrook"},
    {"slug": "stapylton-4207", "collection": "stapylton", "suburb": "stapylton"},
    {"slug": "steiglitz-4207", "collection": "steiglitz", "suburb": "steiglitz"},
    {"slug": "surfers-paradise-4217", "collection": "surfers_paradise", "suburb": "surfers paradise"},
    {"slug": "tallai-4213", "collection": "tallai", "suburb": "tallai"},
    {"slug": "tallebudgera-4228", "collection": "tallebudgera", "suburb": "tallebudgera"},
    {"slug": "tallebudgera-valley-4228", "collection": "tallebudgera_valley", "suburb": "tallebudgera valley"},
    {"slug": "tugun-4224", "collection": "tugun", "suburb": "tugun"},
    {"slug": "upper-coomera-4209", "collection": "upper_coomera", "suburb": "upper coomera"},
    {"slug": "willow-vale-4209", "collection": "willow_vale", "suburb": "willow vale"},
    {"slug": "wongawallan-4210", "collection": "wongawallan", "suburb": "wongawallan"},
    {"slug": "woongoolba-4207", "collection": "woongoolba", "suburb": "woongoolba"},
    {"slug": "worongary-4213", "collection": "worongary", "suburb": "worongary"},
    {"slug": "yatala-4207", "collection": "yatala", "suburb": "yatala"},
]

ALL_GC = CORE + WIDE
BY_SLUG.update({s["slug"]: s for s in WIDE})
