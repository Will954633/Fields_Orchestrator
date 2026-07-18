#!/usr/bin/env python3
"""
address_category.py — Brain 2: classify a SEARCHED address by its listing state.

Given an address a visitor searched or valued (from a PostHog journey — either a
/property/<slug> entry path or an analyse-your-home submit), look it up in the
Gold_Coast property database and return an owner-vs-buyer intent category:

  current_listing   listing_status = for_sale OR under_contract (active market)
  withdrawn_listing listing_status = withdrawn, withdrawn within 12 months
  recent_listing    listing_status = sold, sold within 12 months
                    (NB: may be BUYERS who watched the sale, not the owner)
  likely_home_owner matched in DB but none of the above (sold >12mo ago, or never
                    transacted) — an INFERENCE, not confirmed ownership
  out_of_coverage   address not found in Gold_Coast at all (can't classify)

Ordering is top-down, first match wins (see classify()). Rules agreed with Will
2026-07-19. under_contract folds into current_listing; unmatched addresses are
out_of_coverage (never defaulted to home_owner); home-owner is stored as an
inference.

Usage (standalone test):
  python3 scripts/brain2/address_category.py "16 Collingwood Avenue, Robina"
  python3 scripts/brain2/address_category.py --self-test
"""
import os, re, sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402
from bson import ObjectId  # noqa: E402

CATEGORIES = ("current_listing", "withdrawn_listing", "recent_listing",
              "likely_home_owner", "out_of_coverage")
LABELS = {"current_listing": "Current listing", "withdrawn_listing": "Withdrawn listing",
          "recent_listing": "Recent listing (sold <12mo)", "likely_home_owner": "Home owner",
          "out_of_coverage": "Out of coverage"}

# words that are street TYPES, not part of the searchable street NAME
_TYPE_WORDS = {"street", "st", "road", "rd", "avenue", "ave", "av", "drive", "dr",
               "court", "ct", "place", "pl", "lane", "ln", "way", "close", "cl",
               "parade", "pde", "crescent", "cres", "boulevard", "blvd", "terrace",
               "tce", "circuit", "cct", "esplanade", "esp", "grove", "gr", "rise",
               "highway", "hwy", "parkway", "pkwy", "loop", "walk", "quay", "cove",
               "promenade", "pocket", "outlook", "view", "vista", "ridge", "run",
               "link", "mews", "green", "gardens", "gdns", "row", "square", "sq"}
_STATE_TOKENS = {"qld", "nsw", "vic", "act", "sa", "wa", "nt", "tas", "australia"}
_UNIT_WORDS = {"unit", "u", "apt", "apartment", "villa", "lot", "shop", "level",
               "suite", "flat", "townhouse"}


def _win_days(days=365):
    return datetime.now(timezone.utc) - timedelta(days=days)


def _parse_date(v):
    """Best-effort parse of a sold/withdrawn date (str or datetime) -> aware UTC."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s[:len(fmt)+6], fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    return None


def parse_search_address(text, known_suburbs=None):
    """(street_no, street_core, suburb_key) from an address string or /property slug.
    street_core = street name WITHOUT the type word (matches address_search_index).
    Multi-word suburbs (Reedy Creek, Varsity Lakes) are resolved by greedily matching
    the trailing tokens against known_suburbs (the set of Gold_Coast suburb keys)."""
    if not text:
        return None, None, None
    t = str(text).lower()
    t = t.replace("/property/", "").replace("/", " ")
    t = re.sub(r"[.,]", " ", t).replace("-", " ")
    toks = [x for x in t.split() if x]
    # drop postcode + state tokens
    toks = [x for x in toks if x not in _STATE_TOKENS and not re.match(r"^\d{4}$", x)]
    if not toks:
        return None, None, None
    # strip leading unit/lot words: "unit 4 4 cotinga" -> "4 4 cotinga"
    while toks and toks[0] in _UNIT_WORDS:
        toks = toks[1:]
    # consume the leading run of numbers. In AU unit addresses the slug is
    # <unit>-<street_no>-<street name> (e.g. 86-251-varsity-parade = unit 86,
    # 251 Varsity Parade). The STREET number is the LAST number in that run;
    # earlier numbers are the unit and are discarded (the index keys on street no).
    street_no = None
    while toks and re.match(r"^\d+[a-z]?$", toks[0]):
        street_no = toks[0]
        toks = toks[1:]
    if not toks:
        return street_no, None, None
    # suburb = greedily match trailing 3/2/1 tokens against known suburb keys;
    # fall back to the single last token when we have no known-suburb set.
    suburb_key, n_sub = toks[-1], 1
    if known_suburbs:
        for n in (3, 2, 1):
            if len(toks) > n:
                cand = "_".join(toks[-n:])
                if cand in known_suburbs:
                    suburb_key, n_sub = cand, n
                    break
    body = toks[:-n_sub] or toks               # everything before suburb = street
    core = [w for w in body if w not in _TYPE_WORDS]
    street_core = " ".join(core).strip() or (body[0] if body else None)
    return street_no, street_core, suburb_key


class AddressClassifier:
    """Loads address_search_index once; resolves searched addresses to listing state."""

    def __init__(self, db=None):
        self.gc = db or get_client()["Gold_Coast"]
        self.idx = {}      # (suburb_key, street_no) -> list of index rows
        self.subkeys = set(self.gc.list_collection_names())
        for r in self.gc["address_search_index"].find(
                {}, {"street_no": 1, "street_name": 1, "suburb_key": 1, "source_id": 1}):
            sk = (r.get("suburb_key") or "").lower()
            sn = str(r.get("street_no") or "").lower().strip()
            if not sk or not sn:
                continue
            self.idx.setdefault((sk, sn), []).append(r)

    def _match_index(self, street_no, street_core, suburb_key):
        rows = self.idx.get((suburb_key, street_no), [])
        if not rows:
            return None
        if street_core:
            first = street_core.split()[0]
            for r in rows:
                nm = str(r.get("street_name") or "").lower()
                if nm == street_core or first in nm.split() or nm.split()[:1] == [first]:
                    return r
        return rows[0] if len(rows) == 1 else None

    _PROJ = {"listing_status": 1, "sold_date": 1, "sale_date": 1,
             "withdrawn_date": 1, "withdrawn_detected_at": 1}

    def _doc_for(self, row):
        sk = (row.get("suburb_key") or "").lower()
        if sk not in self.subkeys:
            return None
        sid = row.get("source_id")
        for key in (lambda: ObjectId(sid), lambda: sid):
            try:
                d = self.gc[sk].find_one({"_id": key()}, self._PROJ)
                if d:
                    return d
            except Exception:
                continue
        return None

    def _match_collection(self, street_no, street_core, suburb_key):
        """Fallback when address_search_index misses (it omits some sold/unit
        properties that DO exist in the suburb collection). Match on the
        street_address field, tolerating the unit-slash form '2/35 Killarney'."""
        if suburb_key not in self.subkeys or not street_no or not street_core:
            return None
        first = re.escape(street_core.split()[0])
        no = re.escape(street_no)
        # (start | slash | space) <street_no> <sep> ... <street name word>
        rx = rf"(^|/|\s){no}[a-z]?\s+.*{first}"
        try:
            return self.gc[suburb_key].find_one(
                {"street_address": {"$regex": rx, "$options": "i"}}, self._PROJ)
        except Exception:
            return None

    def classify(self, address):
        """-> (category, detail dict). detail carries matched status/date for audit."""
        sn, core, sub = parse_search_address(address, known_suburbs=self.subkeys)
        detail = {"street_no": sn, "street_core": core, "suburb_key": sub, "matched": False}
        if not sn or not sub:
            return "out_of_coverage", detail
        row = self._match_index(sn, core, sub)
        doc = self._doc_for(row) if row else None
        if not doc:
            doc = self._match_collection(sn, core, sub)   # index-miss fallback
            if doc:
                detail["match_source"] = "collection_fallback"
        if not doc:
            return "out_of_coverage", detail
        detail["matched"] = True
        st = doc.get("listing_status")
        detail["listing_status"] = st
        cutoff = _win_days(365)
        if st in ("for_sale", "under_contract"):
            return "current_listing", detail
        if st == "withdrawn":
            wd = _parse_date(doc.get("withdrawn_date") or doc.get("withdrawn_detected_at"))
            detail["withdrawn_date"] = str(wd.date()) if wd else None
            if wd and wd >= cutoff:
                return "withdrawn_listing", detail
            return "likely_home_owner", detail          # withdrawn >12mo ago
        if st == "sold":
            sd = _parse_date(doc.get("sold_date") or doc.get("sale_date"))
            detail["sold_date"] = str(sd.date()) if sd else None
            if sd and sd >= cutoff:
                return "recent_listing", detail
            return "likely_home_owner", detail          # sold >12mo ago
        return "likely_home_owner", detail              # in DB, never transacted


def _self_test():
    c = AddressClassifier()
    print(f"loaded index keys: {len(c.idx)}")
    tests = ["16 Collingwood Avenue, Robina", "/property/16-collingwood-avenue-robina",
             "4 Springvale Street Robina QLD 4226", "20 Federal Place Robina",
             "3 Woodland Drive, Reedy Creek, QLD 4227",       # multi-word suburb
             "18 Silvabank Drive, Varsity Lakes, QLD 4227",   # multi-word suburb
             "999 Nowhere Street, Atlantis"]
    for t in tests:
        cat, d = c.classify(t)
        print(f"  {cat:18} {LABELS[cat]:28} <- {t}")
        print(f"       {d}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    elif len(sys.argv) > 1:
        c = AddressClassifier()
        cat, d = c.classify(sys.argv[1])
        print(cat, "|", LABELS[cat])
        print(d)
    else:
        print(__doc__)
