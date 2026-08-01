#!/usr/bin/env python3
"""
normalize_addresses.py — resolve every address we hold on a contact to ONE canonical,
postable form, and record where our stored version disagrees.

Why
---
Nothing may be posted until the address on the envelope is right. Two real defects
found 2026-08-01:

  * `crm_contacts` holds "819 Legend Trail, Robina, QLD **4213**" while both PropRadar
    and `Gold_Coast` say **4226**. Robina is 4226; 4213 is Mudgeeraba/Worongary. Mail
    would misroute.
  * Off-market addresses are rebuilt from slugs, and a slug like
    `13-4-yodelay-street-varsity-lakes` was being rendered "13/4 Yodelay Street" by
    guesswork. (It happens to be right — the cadastral record carries UNIT_NUMBER=13 —
    but it was a guess, and a guess is not good enough for a letterbox.)

Source of truth: the QLD cadastral `complete_address` field already on our `Gold_Coast`
documents — e.g. "13/4 YODELAY STREET VARSITY LAKES QLD 4227". It is the state address
dataset's own standardised form, present on ~98% of cadastral records (11,868/12,088
Robina; 7,742/7,945 Varsity Lakes; 6,979/7,065 Burleigh Waters), and it already resolves
unit numbers, street types and postcodes correctly. PropRadar's canonical address is used
as a second opinion where we've already paid for the lookup (cached only — this script
never spends API calls).

Output goes to system_monitor.address_resolution, deliberately NOT onto crm_contacts:
crm_sync.py rebuilds contact documents hourly with replace_one and only carries forward
an explicit allow-list of fields (crm_sync.py:408-434), so anything written onto a
contact by another process is silently wiped within the hour. A side collection keyed by
the raw address string avoids that trap entirely and is reusable by any consumer.

Usage:
  python3 scripts/normalize_addresses.py --dry-run
  python3 scripts/normalize_addresses.py
  python3 scripts/normalize_addresses.py --show-conflicts
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "propradar"))

from shared.db import get_client
from job_status import job_run
from rental_listings_sync import address_key            # unit|number|street|suburb
from engagement_activity_to_sheet import address_candidates

COLL = "address_resolution"
CADASTRAL_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def titlecase_address(a: str) -> str:
    """'13/4 YODELAY STREET VARSITY LAKES QLD 4227' -> '13/4 Yodelay Street, Varsity
    Lakes QLD 4227'. Australia Post accepts either case; this is for human review."""
    if not a:
        return a
    m = re.match(r"^(.*?)\s+(QLD)\s+(\d{4})$", a.strip(), re.I)
    body, state, pc = (m.group(1), m.group(2).upper(), m.group(3)) if m else (a, "", "")
    words = [w if re.match(r"^\d+/?\d*[A-Za-z]?$", w) else w.capitalize()
             for w in body.split()]
    return (" ".join(words) + (f" {state} {pc}" if state else "")).strip()


def build_cadastral_index(gc_db) -> dict[str, dict]:
    """address_key -> canonical cadastral record. One pass over the 3 core suburbs."""
    idx = {}
    for sub in CADASTRAL_SUBURBS:
        for d in gc_db[sub].find(
                {}, {"complete_address": 1, "address": 1, "POSTCODE": 1,
                     "display_postcode": 1, "url_slug": 1, "UNIT_NUMBER": 1,
                     "LOT": 1, "PLAN": 1, "LOCALITY": 1}):
            canon = d.get("complete_address") or d.get("address")
            if not canon:
                continue
            k = address_key(canon)
            if k and k not in idx:
                idx[k] = {
                    "canonical": titlecase_address(canon),
                    "raw_cadastral": d.get("complete_address"),
                    "postcode": d.get("POSTCODE") or d.get("display_postcode"),
                    "slug": d.get("url_slug"), "collection": sub,
                    "unit_number": d.get("UNIT_NUMBER"),
                    "lot": d.get("LOT"), "plan": d.get("PLAN"),
                }
    return idx


def by_slug(gc_db, slug: str) -> dict | None:
    for sub in CADASTRAL_SUBURBS:
        d = gc_db[sub].find_one(
            {"url_slug": slug},
            {"complete_address": 1, "address": 1, "POSTCODE": 1, "display_postcode": 1,
             "url_slug": 1, "UNIT_NUMBER": 1, "LOT": 1, "PLAN": 1})
        if d and (d.get("complete_address") or d.get("address")):
            canon = d.get("complete_address") or d["address"]
            return {"canonical": titlecase_address(canon),
                    "raw_cadastral": d.get("complete_address"),
                    "postcode": d.get("POSTCODE") or d.get("display_postcode"),
                    "slug": d.get("url_slug"), "collection": sub,
                    "unit_number": d.get("UNIT_NUMBER"), "lot": d.get("LOT"),
                    "plan": d.get("PLAN")}
    return None


def stored_postcode(a: str) -> str | None:
    """The POSTCODE in an address string — not the first 4-digit number in it.

    Unit numbers are routinely 4 digits on the Gold Coast ("1604/3 Main Street",
    "4210/61 Investigator Drive", "2611/42 Laver Drive"), so a naive \\b\\d{4}\\b
    reads the unit as a postcode and reports a conflict on every apartment.
    Only accept a code that follows a state token or ends the string.
    """
    a = (a or "").strip().rstrip(",")
    m = re.search(r"\b(?:QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s*,?\s*(\d{4})\b", a, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(?<![\d/])(\d{4})\s*$", a)   # trailing, and not part of "1604/3"
    return m.group(1) if m else None


def resolve(raw: str, slug: str | None, gc_db, idx: dict, pr_cache: dict) -> dict:
    """Canonical form for one stored address, with provenance and any conflict."""
    out = {"_id": (address_key(raw) or raw.lower()), "raw": raw, "slug": slug,
           "resolved_at": datetime.now(timezone.utc), "conflicts": []}

    hit = (by_slug(gc_db, slug) if slug else None) or idx.get(address_key(raw) or "")
    if hit:
        out.update({k: hit[k] for k in
                    ("canonical", "postcode", "collection", "unit_number", "lot", "plan")})
        out["source"] = "qld_cadastral"
        out["cadastral_slug"] = hit.get("slug")
        # A unit number the cadastral record confirms is no longer a guess.
        out["unit_confirmed"] = bool(hit.get("unit_number"))
    else:
        pr = pr_cache.get(re.sub(r"\s+", " ", raw.lower().replace(",", " ")).strip())
        if pr and pr.get("canonical_address"):
            out["canonical"] = titlecase_address(pr["canonical_address"].replace(", QLD,", " QLD"))
            out["postcode"] = stored_postcode(pr["canonical_address"])
            out["source"] = "propradar"
        else:
            out["canonical"] = raw
            out["source"] = "unresolved"
            out["conflicts"].append("no cadastral or PropRadar record — address UNVERIFIED")

    # Cadastral POSTCODE can be null on scraped (non-cadastral) records — fall back to
    # the postcode inside the canonical address itself, or 819 Legend Trail's real
    # 4213-vs-4226 conflict goes undetected.
    if not out.get("postcode"):
        out["postcode"] = stored_postcode(out.get("canonical") or "")
    sp, rp = stored_postcode(raw), out.get("postcode")
    if sp and rp and sp != rp:
        out["conflicts"].append(
            f"stored postcode {sp} disagrees with {out['source']} {rp} — "
            f"mail addressed to {sp} could misroute")
    out["ok_to_post"] = out["source"] != "unresolved" and not any(
        "misroute" in c for c in out["conflicts"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-conflicts", action="store_true")
    args = ap.parse_args()

    client = get_client()
    db, gc_db = client["system_monitor"], client["Gold_Coast"]

    with job_run("normalize_addresses", cadence_hours=24,
                 title="Contact Address Normalisation") as beat:
        idx = build_cadastral_index(gc_db)
        print(f"cadastral index: {len(idx)} addresses")
        pr_cache = {d["_id"]: d for d in db["propradar_market_status"].find({})}

        wanted = {}
        for c in db.crm_contacts.find({}):
            for x in address_candidates(c):
                if x["address"] and x["address"] not in wanted:
                    wanted[x["address"]] = x.get("slug")
        print(f"{len(wanted)} distinct address(es) referenced by contacts")

        rows = [resolve(a, s, gc_db, idx, pr_cache) for a, s in wanted.items()]
        stats = {
            "addresses": len(rows),
            "resolved_cadastral": sum(1 for r in rows if r["source"] == "qld_cadastral"),
            "resolved_propradar": sum(1 for r in rows if r["source"] == "propradar"),
            "unresolved": sum(1 for r in rows if r["source"] == "unresolved"),
            "postcode_conflicts": sum(1 for r in rows
                                      if any("misroute" in c for c in r["conflicts"])),
            "ok_to_post": sum(1 for r in rows if r["ok_to_post"]),
        }
        for k, v in stats.items():
            print(f"  {k}: {v}")

        if args.show_conflicts or args.dry_run:
            for r in rows:
                if r["conflicts"] and "misroute" in " ".join(r["conflicts"]):
                    print(f"\n  CONFLICT  {r['raw']}\n      -> {r['canonical']}"
                          f"\n      {r['conflicts'][0]}")

        if not args.dry_run:
            for r in rows:
                db[COLL].replace_one({"_id": r["_id"]}, r, upsert=True)
            print(f"\nwrote {len(rows)} record(s) to system_monitor.{COLL}")

        beat.detail = (f"{stats['ok_to_post']}/{stats['addresses']} postable; "
                       f"{stats['postcode_conflicts']} postcode conflict(s), "
                       f"{stats['unresolved']} unresolved")
        beat.metrics = stats
    client.close()


if __name__ == "__main__":
    main()
