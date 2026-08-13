"""Address normalisation for the ID4ME autocomplete endpoint.

The endpoint is fussy in two ways discovered by testing against it:

  * Commas kill matches. "27 huntingdale crescent, robina, qld 4226" returns
    nothing; the same string without commas resolves fine.
  * Abbreviated street types kill matches. "27 huntingdale cres" returns an
    empty list, "27 huntingdale crescent" returns the address.

So we expand abbreviations and strip punctuation before querying, and fall back
through progressively looser variants until something resolves.
"""

import re

STREET_TYPES = {
    "st": "street", "str": "street",
    "rd": "road",
    "ave": "avenue", "av": "avenue",
    "cres": "crescent", "cr": "crescent", "crs": "crescent",
    "dr": "drive", "drv": "drive",
    "ct": "court", "crt": "court",
    "pl": "place",
    "tce": "terrace", "ter": "terrace",
    "pde": "parade",
    "hwy": "highway",
    "ln": "lane",
    "cl": "close",
    "blvd": "boulevard", "bvd": "boulevard",
    "gr": "grove", "grv": "grove",
    "wy": "way",
    "cct": "circuit",
    "esp": "esplanade",
    "sq": "square",
    "tr": "track",
}

STATES = {"qld", "nsw", "vic", "sa", "wa", "tas", "nt", "act"}


def clean(address: str) -> str:
    """Strip punctuation and expand abbreviated street types."""
    text = address.replace(",", " ").replace(".", " ")
    text = re.sub(r"\s+", " ", text).strip()
    words = [STREET_TYPES.get(w.lower(), w) for w in text.split(" ")]
    return " ".join(words)


def variants(address: str) -> list[str]:
    """Progressively looser query strings, most specific first.

    Autocomplete sometimes misses on the fully-qualified string but matches on
    street + suburb, so we keep shorter fallbacks ready rather than reporting a
    miss on the first attempt.
    """
    full = clean(address)
    out = [full]

    words = full.split(" ")
    # Drop a trailing 4-digit postcode.
    if words and re.fullmatch(r"\d{4}", words[-1]):
        words = words[:-1]
        out.append(" ".join(words))
    # Drop a trailing state abbreviation.
    if words and words[-1].lower() in STATES:
        words = words[:-1]
        out.append(" ".join(words))

    seen, unique = set(), []
    for v in out:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            unique.append(v)
    return unique
