"""Address join key — the integration risk, isolated in one place.

onthehouse has no Domain listing id, so every join against Gold_Coast is by address.
The key is `unit|number|street name|suburb`, with the street TYPE dropped entirely
rather than normalised: sources abbreviate it inconsistently (PL/PLACE, CCT/CIRCUIT,
DR/DRIVE, TRL/TRAIL) and uppercase unpredictably, while number + street name + suburb
is already unique in practice. This matches `rental_listings_sync.address_key()`, which
is live, so all three onthehouse collections join to each other on the same key.

Verified 2026-08-01 on the real crawl: property type agreed on 769/769 matched sold
pairs and sale price on 539/554 (97% identical to the dollar) — a key that was merging
different homes could not produce that. `collisions()` below re-checks the one risk the
dropped street type creates, and is exercised by the sync jobs' self-test.
"""
from __future__ import annotations

import re
from collections import defaultdict

# Types are dropped, so this set only has to RECOGNISE a token as a street type.
STREET_TYPES = {
    "st", "street", "rd", "road", "ave", "av", "avenue", "dr", "drive", "ct", "court",
    "pl", "place", "cres", "crescent", "cct", "circuit", "circut", "cir", "circle",
    "bvd", "blvd", "boulevard", "pde", "parade", "tce", "terrace", "ln", "lane", "way",
    "trl", "trail", "cl", "close", "gr", "grove", "esp", "esplanade", "pkwy", "parkway",
    "sq", "square", "tr", "track", "rise", "view", "views", "vista", "walk", "mews",
    "loop", "link", "chase", "pnt", "point", "hwy", "highway", "gdns", "gardens",
    "green", "bend", "key", "keys", "quay", "ridge", "glen", "hts", "heights", "cove",
    "crest", "outlook", "retreat", "grange", "run", "row", "end", "mall", "arc", "arcade",
}
_NOISE = {"unit", "apt", "apartment", "lot", "the", "sold", "qld", "nsw"}
_MONTHS = set("jan feb mar apr may jun jul aug sep oct nov dec january february march "
              "april june july august september october november december".split())


def _clean(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def address_key(address: str, suburb: str | None = None) -> str | None:
    """Join key from a free-text address.

    ALWAYS PASS `suburb` WHEN YOU KNOW IT — e.g. from the Gold_Coast collection you are
    querying. Many for-sale docs store `street_address` as "10 Malvern Place" with no
    suburb at all; without the hint the suburb parses empty and this returns None, which
    looks exactly like "no such address" rather than "unparseable". That mistake silently
    cut a core-suburb join from 111 matches to 4.

    Handles the shapes actually present in Gold_Coast:
      "70/22 Barbet Place, Burleigh Waters QLD 4220"
      "1/17 Sunbird Street Burleigh  Waters"          (no comma, doubled space)
      "Sold 3 Carpentaria Court, Robina, QLD 4226 on 08 Dec 2025 - 2020397929"
      "1302/3 & 1302a/3 Main Street, Varsity Lakes"   (two units, take the first)
      "UNIT 4/4 Cotinga Crescent, Burleigh Waters"
    """
    a = (address or "").lower()
    a = re.sub(r"^sold\s+", "", a)             # sold docs prefix the address
    a = re.split(r"\s+on\s+\d", a)[0]          # ...and suffix " on 08 Dec 2025 - 2020..."
    # "1302/3 & 1302a/3 Main Street" is ONE home listed under two unit numbers. Drop the
    # second unit token only — a blanket `&.*` cut also ate the street name and suburb.
    a = re.sub(r"\s*&\s*\d+[a-z]?\s*/\s*\d+", "", a)
    a = re.sub(r"\bqld\b|\bnsw\b", " ", a)
    # Strip the POSTCODE, not every 4-digit number. `\b4\d{3}\b` also matched high-rise
    # unit numbers — "4204/12-14 Executive Drive" lost its unit and keyed as 12|14, and
    # 4103/61, 4507/61 and 4708/61 Investigator Drive all collapsed onto one key.
    # A postcode is the trailing number; a unit number never is.
    a = re.sub(r"\b\d{4}\b\s*(?=$)", " ", a.rstrip())

    parts = [p.strip() for p in a.split(",") if p.strip()]
    if len(parts) >= 2:
        street, sub = parts[0], parts[1]
    else:
        street, sub = (parts[0] if parts else ""), ""
        toks = _clean(street).split()
        cut = next((i for i, t in enumerate(toks) if t in STREET_TYPES), None)
        if cut is not None:                     # no comma: suburb is whatever trails the type
            street, sub = " ".join(toks[:cut + 1]), " ".join(toks[cut + 1:])
    if suburb:
        sub = suburb

    street = _clean(street)
    street = re.sub(r"(\d+)[a-z]\b", r"\1", street)   # 83a -> 83, 1302a -> 1302
    nums, name, words = [], [], []
    for t in street.split():
        if t in _NOISE or t in _MONTHS:
            continue
        if re.match(r"^[\d/\-]+$", t):
            for p in re.split(r"/", t):
                p = p.split("-")[0]                   # "12-14" -> 12
                if p.isdigit():
                    nums.append(str(int(p)))
            continue
        words.append(t)
        if t not in STREET_TYPES:
            name.append(t)
    # Some street NAMES are made entirely of street-TYPE words — "The Esplanade",
    # "View Street", "Vantage Point Drive". Stripping types then leaves nothing and the
    # address became unjoinable. Fall back to the words minus the final one, which is
    # the actual type.
    if not name and words:
        name = words[:-1] or words
    sub = " ".join(w for w in _clean(sub).split() if w not in _NOISE)
    if not nums or not name or not sub:
        return None
    unit, number = (nums[0], nums[1]) if len(nums) >= 2 else ("", nums[0])
    return f"{unit}|{number}|{' '.join(name)}|{sub}"


def collisions(pairs) -> dict:
    """{key: {distinct addresses}} where one key claims more than one real address.

    Dropping the street type is the deliberate looseness in this key; this is how we
    keep it honest. `pairs` is an iterable of (key, original_address).
    """
    seen = defaultdict(set)
    for key, addr in pairs:
        if key:
            seen[key].add(re.sub(r"\s+", " ", (addr or "").strip().lower()))
    return {k: v for k, v in seen.items() if len(v) > 1}
