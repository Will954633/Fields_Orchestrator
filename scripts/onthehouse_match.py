#!/usr/bin/env python3
"""onthehouse_match.py — address matching and subject extraction for onthehouse.com.au.

Shared by every onthehouse backfill so there is ONE matcher, not one per script that
slowly drifts from its siblings.

TWO IDEAS DO THE WORK HERE.

1. THE SITEMAP INDEX IS A RECALL DEVICE, NOT AN AUTHORITY.
   It answers "which URL is probably this home?". It is allowed to be generous — a slug
   like `2-4-riverwalk-ave` is genuinely ambiguous (unit 2 at number 4, or the ranged
   address 2-4?) and cannot be resolved from the slug alone, so we index BOTH readings.

2. THE PAGE IS THE AUTHORITY.
   Every property page carries the subject under `propertyDetail.property` with a parsed
   `address` object — streetNumber, streetName, streetType, unitNumber, suburb — and a
   `formattedAddress`. `subject_of()` reads THAT, and the caller must check the address it
   returns is the one it asked for. So a wrong guess from the index produces NO WRITE
   rather than a wrong write, and the ambiguity above becomes harmless.

   This matters because the first thirteen `"shortAddress"` blocks on a page are NEIGHBOURS
   and recent nearby sales. On `4-dexter-cl-robina` the subject is the fourteenth. Any
   scan-and-take-the-first approach reads a different house's bedrooms.

⚠ WHY THE MATCH MUST BE UNIT-EXACT. A substring or fuzzy match silently assigns a
BUILDING's attributes to an apartment: `61 Investigator Dr` occurs inside the slug
`4608-61-investigator-drive`. That produced 3 wrong rows in 12 in an early sampler while
reporting "20 of 25 resolved". Bedrooms feed valuations, comparables and the price index,
so a wrong bedroom count is strictly worse than no bedroom count.

⚠ THREE SPELLING TRAPS, all of which cause MISSES (never wrong matches) and so are
invisible unless measured:
  * `ST IVES DRIVE` (ours) is published as BOTH `st-ives-dr` and `saint-ives-dr`.
  * A ranged street number under a unit uses a DOUBLE dash: `7-8--14-st-ives-dr`
    is unit 7 at 8-14 St Ives Dr.
  * Street types vary: we write `Cr`, they write `Cres`; `trail`/`trl`,
    `parkway`/`pkwy`, `quay`/`qys`, `point`/`pnt`.
Measured over the three suburbs these cost ~1,400 recoverable matches.

⚠ `beds: 0` MEANS UNKNOWN, NOT A STUDIO. onthehouse returns 0 for absent. Reject it.
Same for `floorSize: 0` and `landSize: 0`.
"""
from __future__ import annotations

import json
import re

# ---------------------------------------------------------------------------
# Street-type vocabulary. Every variant collapses to ONE canonical token so that
# our spelling and theirs meet in the middle. Applied to the LAST token only,
# which is the street-type position.
# ---------------------------------------------------------------------------
_TYPE_CANON = {
    "street": "st", "str": "st", "st": "st",
    "road": "rd", "rd": "rd",
    "drive": "dr", "drv": "dr", "dr": "dr",
    "avenue": "ave", "av": "ave", "ave": "ave",
    "court": "ct", "crt": "ct", "ct": "ct",
    "crescent": "cres", "cres": "cres", "cr": "cres",
    "place": "pl", "pl": "pl",
    "parade": "pde", "pde": "pde",
    "lane": "ln", "ln": "ln",
    "close": "cl", "cl": "cl",
    "terrace": "tce", "tce": "tce",
    "boulevard": "bvd", "blvd": "bvd", "bvd": "bvd",
    "esplanade": "esp", "esp": "esp",
    "circuit": "cct", "cct": "cct",
    "circle": "cir", "cir": "cir",
    "parkway": "pkwy", "pkwy": "pkwy", "pway": "pkwy",
    "trail": "trl", "trl": "trl",
    "quay": "qy", "qys": "qy", "qy": "qy",
    "point": "pnt", "pnt": "pnt", "pt": "pnt",
    "grove": "gr", "grv": "gr", "gr": "gr",
    "highway": "hwy", "hwy": "hwy",
    "square": "sq", "sq": "sq",
    "way": "way", "view": "view", "rise": "rise", "walk": "walk",
    "green": "green", "chase": "chase", "mews": "mews", "vista": "vista",
}


def norm_street(s: str, suburb_key: str | None = None) -> str:
    """Slugify a street name and canonicalise its type token.

    `Brooklyn Crescent`, `Brooklyn Cres` and `Brooklyn Cr` all become `brooklyn-cres`.
    `SAINT IVES DRIVE` and `St Ives Dr` both become `st-ives-dr`.

    ⚠ THE SUBURB MUST COME OFF FIRST. Type canonicalisation applies to the LAST token, so
    while a trailing `robina` is still attached the last token is the suburb and the street
    type is never canonicalised — `1/1 Acacia Court Robina` stayed `acacia-court` and did
    not match `acacia-ct`. That silently broke every address written with its suburb
    included, which is most of ours.
    """
    s = (s or "").lower().replace(",", " ")
    s = re.sub(r"\bqld\b|\bnsw\b|\bvic\b|\b\d{4}\b", " ", s)
    parts = [p for p in re.split(r"[^a-z0-9]+", s) if p]
    if suburb_key:
        sub = [p for p in suburb_key.split("_") if p]
        while len(parts) > len(sub) and parts[-len(sub):] == sub:
            parts = parts[:-len(sub)]
    if not parts:
        return ""
    # `saint` -> `st` anywhere it is a NAME prefix. Never touch the final token, where
    # `st` means Street: `12 Saint Ives Dr` vs `12 Ives St` must not converge.
    parts = [("st" if p == "saint" else p) if i < len(parts) - 1 else p
             for i, p in enumerate(parts)]
    parts[-1] = _TYPE_CANON.get(parts[-1], parts[-1])
    return "-".join(parts)


# A street number, optionally a range: `12`, `12a`, `8-14`, `217-219`.
_NUM = r"\d+[a-zA-Z]?(?:\s*-\s*\d+[a-zA-Z]?)?"


def parse_address(a: str, suburb_key: str | None = None):
    """(unit, street_number, street_slug). `unit` is None when the address has none.

    ⚠ THE UNIT NUMBER IS THE ENTIRE POINT. `4608/61 Investigator Dr` and
    `61 Investigator Dr` must produce different tuples — that is what stops a building's
    record standing in for one of its apartments.
    """
    a = (a or "").strip()
    a = re.sub(r"^\s*(?:unit|apt|apartment|lot)\s+", "", a, flags=re.I)
    m = re.match(rf"^\s*(\d+[a-zA-Z]?)\s*[/\\]\s*({_NUM})\s+(.*)$", a)
    if m:
        return (m.group(1).lower(), re.sub(r"\s+", "", m.group(2).lower()),
                norm_street(m.group(3), suburb_key))
    m = re.match(rf"^\s*({_NUM})\s+(.*)$", a)
    if m:
        return None, re.sub(r"\s+", "", m.group(1).lower()), norm_street(m.group(2), suburb_key)
    return None, None, norm_street(a, suburb_key)


def key_of(address: str, suburb_key: str):
    """Normalised (unit, number, street, suburb). None when there is no street number."""
    unit, num, street = parse_address(address, suburb_key)
    if not num or not street:
        return None
    return (unit or "", num, street, suburb_key)


def slug_keys(slug: str, suburb_key: str):
    """Every plausible key for a sitemap slug — this is RECALL, the page decides truth.

    `7-8--14-st-ives-dr`  -> unit 7 at 8-14 (the double dash is a range)
    `112-2-4-riverwalk-ave` -> unit 112 at 2-4
    `2-4-riverwalk-ave`   -> AMBIGUOUS: unit 2 at 4, or the ranged address 2-4.
                             Both are returned; `subject_of()` settles it.
    """
    out = []

    def add(addr):
        k = key_of(addr, suburb_key)
        if k and k not in out:
            out.append(k)

    # A double dash is a range separator: `<unit>-<lo>--<hi>-<street>`.
    if "--" in slug:
        left, right = slug.split("--", 1)
        lp = left.split("-")
        rp = right.split("-")
        if len(lp) >= 2 and re.fullmatch(r"\d+[a-z]?", lp[-1]) and rp and re.fullmatch(r"\d+[a-z]?", rp[0]):
            unit = "-".join(lp[:-1])
            add(f"{unit}/{lp[-1]}-{rp[0]} " + " ".join(rp[1:]))
            if not re.fullmatch(r"\d+[a-z]?", unit):        # no unit: `8--14-st-ives-dr`
                add(f"{lp[-1]}-{rp[0]} " + " ".join(rp[1:]))
        return out

    parts = slug.split("-")
    isnum = lambda x: bool(re.fullmatch(r"\d+[a-z]?", x))            # noqa: E731
    if len(parts) >= 4 and isnum(parts[0]) and isnum(parts[1]) and isnum(parts[2]):
        add(f"{parts[0]}/{parts[1]}-{parts[2]} " + " ".join(parts[3:]))
    if len(parts) >= 3 and isnum(parts[0]) and isnum(parts[1]):
        add(f"{parts[0]}/{parts[1]} " + " ".join(parts[2:]))         # unit / number
        add(f"{parts[0]}-{parts[1]} " + " ".join(parts[2:]))         # ranged number
    if parts and isnum(parts[0]):
        add(" ".join(parts))                                         # plain number
    return out


def build_index(sitemap_xml: str, suburb_key: str):
    """key -> url for every addressable property in a suburb sitemap.

    Returns (index, stats). Slugs that carry no street number — `lot-880-...`,
    `heights-dr-...` — are unbuilt land or street stubs and are counted, not silently
    dropped, so a change in their share is visible.
    """
    idx, stats = {}, {"locs": 0, "no_number": 0, "collisions": 0}
    for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap_xml):
        stats["locs"] += 1
        tail = loc.rsplit("/", 1)[-1]
        m = re.match(r"(.+?)-qld-\d{4}-(\d+)$", tail)
        if not m:
            stats["no_number"] += 1
            continue
        keys = slug_keys(m.group(1), suburb_key)
        if not keys:
            stats["no_number"] += 1
            continue
        for k in keys:
            if k in idx and idx[k] != loc:
                stats["collisions"] += 1
                continue                    # first writer wins; page verification decides
            idx.setdefault(k, loc)
    return idx, stats


# ---------------------------------------------------------------------------
# Subject extraction — structural, not positional.
# ---------------------------------------------------------------------------
def _span(html: str, start: int) -> str:
    return html[start:start + 3000]


def subject_of(html: str, suburb_key: str):
    """Attributes for the page's OWN property, or None.

    Reads `propertyDetail.property`, the object the page is actually about, rather than
    scanning `"shortAddress"` blocks — of which a page carries a dozen belonging to
    NEIGHBOURS. Returns the address it found so the caller can verify it got the home it
    asked for.
    """
    i = html.find('"propertyDetail"')
    if i < 0:
        return None
    j = html.find('"property":{', i)
    if j < 0:
        return None
    seg = _span(html, j)

    def num(field):
        m = re.search(rf'"{field}":\s*(\d+)', seg)
        return int(m.group(1)) if m else 0

    def txt(field):
        m = re.search(rf'"{field}":\s*"([^"]*)"', seg)
        return m.group(1) if m else None

    formatted = txt("formattedAddress")
    if not formatted:
        return None

    # Prefer the STRUCTURED address — no parsing guesswork about unit vs street number.
    unit = txt("unitNumber")
    snum = txt("streetNumber")
    sname = txt("streetName")
    stype = txt("streetType")
    if snum and sname:
        addr = f"{unit}/{snum} " if unit else f"{snum} "
        addr += f"{sname} {stype or ''}".strip()
        key = key_of(addr, suburb_key)
    else:
        key = key_of(formatted, suburb_key)

    lat = re.search(r'"lat":\s*(-?\d+\.\d+)', seg)
    lon = re.search(r'"lon":\s*(-?\d+\.\d+)', seg)

    beds, baths = num("beds"), num("baths")
    floor, land = num("floorSize"), num("landSize")
    year, cars = num("yearBuilt"), num("carSpaces")
    return {
        "key": key,
        "formatted_address": formatted,
        # 0 is onthehouse's "unknown" in every one of these fields, never a real value.
        "bedrooms": beds if 0 < beds <= 9 else None,
        "bathrooms": baths if 0 < baths <= 9 else None,
        "car_spaces": cars if 0 < cars <= 12 else None,
        "floor_area_sqm": floor if 20 <= floor <= 2000 else None,
        "land_size_sqm": land if 20 <= land <= 20000 else None,
        "year_built": year if 1850 <= year <= 2030 else None,
        "latitude": float(lat.group(1)) if lat else None,
        "longitude": float(lon.group(1)) if lon else None,
    }
