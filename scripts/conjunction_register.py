#!/usr/bin/env python3
"""
conjunction_register.py — first-class registry of "conjunction properties".

A *conjunction property* is a home LISTED BY ANOTHER AGENCY for which Fields is
running a buyer-acquisition conjunction (Fields finds the buyer; the listing
agent keeps the vendor relationship and the listing). Example: 93 Burleigh
Street, listed by Tyler Benson / Coomera Realty.

Because the vendor is *someone else's client*, our own automated systems must
NOT treat that property like an ordinary lead or an ordinary listing:

  * We must never prospect the vendor to switch/re-list ("seller-prospecting").
  * We must never publish an adverse positioning verdict ("Overpriced", leaked
    non-published editorial) on the listing agent's property.

This module is the single source of truth those guards consult. It is a pure
library + CLI — NO scheduled component — so per Rule 7 it needs no heartbeat.
If it ever grows a scheduled sweep, wrap that sweep in job_status.job_run and
assert its zero-output path (Rule 7/7b).

Storage: system_monitor.conjunction_properties, one document per property,
keyed by `property_slug` (unique).

Public API:
    upsert(slug, **fields)          -> dict   (the stored doc)
    get(slug)                       -> dict|None
    list_active()                   -> list[dict]  (campaign_status != 'closed')
    is_conjunction(x)               -> bool   (x = slug | address | Gold_Coast _id)

CLI:
    python3 scripts/conjunction_register.py --list
    python3 scripts/conjunction_register.py --show SLUG
    python3 scripts/conjunction_register.py --add slug=... address=... ...
    python3 scripts/conjunction_register.py --set SLUG field=value [field=value ...]
    python3 scripts/conjunction_register.py --seed-93   # seed 93 Burleigh Street
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

# Make `shared` importable whether run from repo root or scripts/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import get_client  # noqa: E402

COLLECTION = "conjunction_properties"

# Canonical field set (documented so callers/CLI don't have to guess). Extra
# free-text fields are allowed via **fields, but these are the known ones.
KNOWN_FIELDS = (
    "property_slug", "address", "property_id", "listing_agent", "listing_agency",
    "fee_basis", "approval_status", "campaign_status", "landing_url",
    "lead_source_tag", "inspection_at", "agreement_expiry_note",
    "created_at", "updated_at",
)

_CAMPAIGN_STATES = {"draft", "live", "paused", "closed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coll():
    return get_client()["system_monitor"][COLLECTION]


def _norm_addr(s: str) -> str:
    """Loose address/slug normaliser for matching: lowercase, strip everything
    that isn't a letter or digit. '93 Burleigh Street, Burleigh Waters, QLD 4220'
    and '93-burleigh-street-burleigh-waters' both collapse toward the same
    prefix, so we compare on the leading token set rather than exact equality."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def upsert(slug: str, **fields) -> dict:
    """Create or update the conjunction doc for `slug`. Returns the stored doc.
    `created_at` is set once; `updated_at` on every write."""
    if not slug:
        raise ValueError("property_slug is required")
    coll = _coll()
    now = _now()
    fields.pop("property_slug", None)  # slug is the key, not a mutable field
    cs = fields.get("campaign_status")
    if cs is not None and cs not in _CAMPAIGN_STATES:
        raise ValueError(f"campaign_status must be one of {sorted(_CAMPAIGN_STATES)}, got {cs!r}")
    set_doc = {**fields, "property_slug": slug, "updated_at": now}
    coll.update_one(
        {"property_slug": slug},
        {"$set": set_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return get(slug)


def get(slug: str) -> dict | None:
    return _coll().find_one({"property_slug": slug})


def list_active() -> list[dict]:
    """Every conjunction whose campaign is not closed. (Guards still treat a
    'closed' conjunction as a conjunction — see is_conjunction — but operational
    listings are the active ones.)"""
    return list(_coll().find({"campaign_status": {"$ne": "closed"}}).sort("property_slug", 1))


# A tiny in-process cache so a guard that calls is_conjunction() in a per-row
# loop doesn't hammer Cosmos. Registry is small and changes rarely; a guard run
# is short-lived. Call _reset_cache() in tests if you mutate mid-process.
_CACHE: dict | None = None


def _load_all() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = list(_coll().find({}))
    return _CACHE


def _reset_cache() -> None:
    global _CACHE
    _CACHE = None


def is_conjunction(address_or_slug_or_id) -> bool:
    """True if the given identifier refers to a registered conjunction property.

    Accepts:
      * a property_slug ('93-burleigh-street-burleigh-waters')
      * a Gold_Coast _id (str or ObjectId) matching a doc's property_id
      * a free-text address ('93 Burleigh Street, Burleigh Waters, QLD 4220')
      * a whole property document dict (uses its _id / url_slug / address)

    Matching is deliberately generous: an exact slug/id hit, or a normalised
    address-prefix overlap. A registry MISS returns False — but note a False is
    'not registered', which for this guard is the safe default (we only suppress
    prospecting/verdicts for KNOWN conjunctions; a genuine own-listing is fine).
    """
    if address_or_slug_or_id is None:
        return False

    # Accept a full property document.
    if isinstance(address_or_slug_or_id, dict):
        doc = address_or_slug_or_id
        for cand in (doc.get("url_slug"), doc.get("_id"), doc.get("address"),
                     doc.get("complete_address")):
            if cand is not None and is_conjunction(cand):
                return True
        return False

    x = str(address_or_slug_or_id).strip()
    if not x:
        return False
    x_norm = _norm_addr(x)

    for d in _load_all():
        if d.get("property_slug") and str(d["property_slug"]) == x:
            return True
        if d.get("property_id") and str(d["property_id"]) == x:
            return True
        # normalised address / slug overlap (prefix either way)
        for key in ("address", "property_slug"):
            val = d.get(key)
            if not val:
                continue
            v_norm = _norm_addr(str(val))
            if v_norm and x_norm and (v_norm.startswith(x_norm) or x_norm.startswith(v_norm)):
                return True
    return False


# --------------------------------------------------------------------------- #
# Seed data
# --------------------------------------------------------------------------- #
def seed_93_burleigh() -> dict:
    """Seed the 93 Burleigh Street conjunction (Tyler Benson / Coomera Realty)."""
    return upsert(
        "93-burleigh-street-burleigh-waters",
        address="93 Burleigh Street, Burleigh Waters, QLD 4220",
        property_id="690bd81b8b8f546592617fbb",
        listing_agent="Tyler Benson",
        listing_agency="Coomera Realty",
        fee_basis="buyer-acquisition conjunction (Fields finds buyer; listing agent keeps vendor)",
        approval_status={"page_cleared": False, "cleared_at": None},
        campaign_status="draft",
        landing_url="https://fieldsestate.com.au/93-burleigh-street/",
        lead_source_tag="campaign_landing_93_burleigh",
        inspection_at="2026-08-22T13:00:00+10:00",  # Sat 22 Aug 2026 1pm AEST
        agreement_expiry_note="Listed by Coomera Realty — do NOT prospect vendor to switch/re-list.",
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _kv_pairs(items: list[str]) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"expected field=value, got {it!r}")
        k, v = it.split("=", 1)
        # bool coercion for convenience
        if v.lower() in ("true", "false"):
            v = (v.lower() == "true")
        out[k.strip()] = v
    return out


def _print_doc(d: dict) -> None:
    if not d:
        print("(not found)")
        return
    width = max(len(k) for k in d)
    for k in sorted(d, key=lambda k: (k not in KNOWN_FIELDS, k)):
        if k == "_id":
            continue
        print(f"  {k:<{width}} : {d[k]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Conjunction property register")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list active conjunctions")
    g.add_argument("--show", metavar="SLUG", help="show one conjunction")
    g.add_argument("--add", nargs="+", metavar="field=value",
                   help="upsert; must include property_slug=...")
    g.add_argument("--set", nargs="+", metavar="SLUG field=value",
                   help="update fields on an existing SLUG")
    g.add_argument("--seed-93", action="store_true", help="seed 93 Burleigh Street")
    args = ap.parse_args()

    if args.list:
        rows = list_active()
        print(f"{len(rows)} active conjunction propert{'y' if len(rows)==1 else 'ies'}:")
        for d in rows:
            print(f"\n• {d.get('property_slug')}  [{d.get('campaign_status')}]")
            print(f"    {d.get('address')}")
            print(f"    listed by {d.get('listing_agent')} / {d.get('listing_agency')}")
            print(f"    landing: {d.get('landing_url')}")
        return 0

    if args.show:
        _print_doc(get(args.show))
        return 0

    if args.seed_93:
        d = seed_93_burleigh()
        print("Seeded:")
        _print_doc(d)
        return 0

    if args.add:
        kv = _kv_pairs(args.add)
        slug = kv.pop("property_slug", None) or kv.pop("slug", None)
        if not slug:
            raise SystemExit("--add requires property_slug=...")
        d = upsert(slug, **kv)
        print("Upserted:")
        _print_doc(d)
        return 0

    if args.set:
        slug = args.set[0]
        if "=" in slug:
            raise SystemExit("--set SLUG field=value ... (first arg is the slug, no '=')")
        if not get(slug):
            raise SystemExit(f"no conjunction with slug {slug!r} (use --add to create)")
        kv = _kv_pairs(args.set[1:])
        d = upsert(slug, **kv)
        print("Updated:")
        _print_doc(d)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
