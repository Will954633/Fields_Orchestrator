"""
addr_match.py — canonical address normalisation for matching PropRadar records to
our Gold_Coast property documents. Shared by the ingest/link scripts.

Handles the format drift observed between the two sources:
  PropRadar : "26 Ballyliffen Court, Robina, QLD, 4226"
  ours (cad): "26 Ballyliffen Crt, Robina QLD 4226"
  ours (sold): ", Robina, QLD 4226"  (empty street -> normalises to "")
"""
from __future__ import annotations

import re

ABBREV = {
    "ST": "STREET", "RD": "ROAD", "CT": "COURT", "CRT": "COURT", "AVE": "AVENUE",
    "AV": "AVENUE", "CR": "CRESCENT", "CRES": "CRESCENT", "DR": "DRIVE", "DRV": "DRIVE",
    "PL": "PLACE", "BLVD": "BOULEVARD", "PDE": "PARADE", "CL": "CLOSE", "TCE": "TERRACE",
    "LN": "LANE", "WY": "WAY", "CCT": "CIRCUIT", "HWY": "HIGHWAY", "PKWY": "PARKWAY",
    "ESP": "ESPLANADE",
}


def normalize_address(addr: str, suburb: str, postcode) -> str:
    if not addr:
        return ""
    s = addr.upper().strip()
    sub = re.escape(suburb.upper())
    pc = re.escape(str(postcode))
    # strip the locality tail only (suburb+state+postcode) so a suburb name inside
    # a street ("Robina Town Centre Drive") is preserved
    s = re.sub(rf"[,\s]+{sub}[,\s]+QLD[,\s]+{pc}\.?\s*$", "", s)
    s = re.sub(rf"[,\s]+QLD[,\s]+{pc}\.?\s*$", "", s)   # tail without suburb
    s = re.sub(rf"[,\s]+{sub}\s*$", "", s)              # trailing bare suburb
    s = s.replace(",", " ")
    s = re.sub(r"\s*/\s*", "/", s)      # unit slash: "21 / 10" -> "21/10"
    s = re.sub(r"\s*-\s*", "-", s)      # number ranges: "22 - 34" -> "22-34"
    s = re.sub(r"[^A-Z0-9/\- ]", " ", s)
    toks = [ABBREV.get(t, t) for t in s.split()]
    return " ".join(toks).strip()
