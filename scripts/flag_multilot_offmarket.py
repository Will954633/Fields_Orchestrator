#!/usr/bin/env python3
"""flag_multilot_offmarket.py — reconcile off-market address-identity state.

WHAT THIS DOES
--------------
Off-market address pages are standalone-houses-only, but the cadastre stores one
record per TITLED LOT. Several lots can share one street address with no unit
number, so `url_slug` disambiguates them with a 4-hex `_id` suffix and each lot
became its own page. This job decides, per colliding slug base, which records may
be published.

It writes TWO INDEPENDENT states, because two genuinely different conditions were
previously conflated under one flag (see INCIDENT below):

  offmarket_multilot  (= duplicate suppression; rename planned, see NAMING)
      "another record definitively represents this same real-world entity."
      Set on the redundant records; exactly one survivor stays indexable.

  offmarket_entity_unresolved
      "we cannot yet safely associate the address-level content with this
      cadastral entity." NOT a duplicate claim. Temporarily noindex pending
      entity resolution, and reported to the address-resolution diagnostic.

Three consumers must agree on BOTH flags:
  - offmarket_discovery_nightly.indexed_query()   (deck builder)
  - generate-sitemap.mjs getOffMarketUrls()        (sitemap)
  - off-market.$slug.tsx meta()                    (robots tag)

INCIDENT THIS FIXES (2026-08-07)
--------------------------------
The previous implementation discovered candidates via `N.indexed_query()`, which
itself contains `offmarket_multilot: {"$ne": True}` — the flag this job sets. So a
flagged lot became invisible to its own detector: the next run found 0 collisions,
concluded every flagged record was stale, and released all of them; the run after
re-detected and re-flagged. Measured: a perfect nightly alternation of ~391
flag/release, moving ~390 URLs in and out of the sitemap every 24h and flipping
their robots tag between `index, follow` and `noindex, nofollow`. With a median
off-market recrawl interval of ~18 days, whichever arbitrary state Google caught
persisted for weeks. Both runs exited 0, so the health board stayed green.

The fix is architectural: the desired state is derived ONLY from source evidence
and NEVER reads either flag, so the reconciliation converges.

CLASSIFICATION (hand-verified 2026-08-07 over all 166 groups / 391 records)
--------------------------------------------------------------------------
CONFIRMED_REDUNDANT   -> one survivor, the rest suppressed as duplicates
  A  every member shares one (LOT, PLAN): duplicate cadastral rows for one parcel
     that differ only by ADDRESS_PID. 7 groups.
  B  hard community-title evidence: LOT 9999 (the QLD common-property lot), a
     scheme PROPERTY_NAME, or a UNIT_TYPE. 86 groups.
  B2 >=4 members all sharing one small identical lot area (<=250 sqm) — a
     townhouse/villa complex on structural grounds. 1 group (2 Scottsdale Drive,
     8 lots x 123 sqm).

CONFIRMED_NON_DWELLING -> the dwelling survives, the parcel is suppressed
  C  a 900-series lot that cannot be a home. Two verified shapes only:
       C1 common property: SP plan, >=2000 sqm, >=2.5x the dwelling lot
          (measured 2,131-12,350 sqm against 400-743 sqm dwellings)
       C2 easement/access strip: <=150 sqm (measured 35, 53, 116 sqm)
     9 records across 9 groups, each inspected individually. Deliberately narrow:
     three candidates at 200/218/261 sqm were REJECTED to IDENTITY_UNRESOLVED
     because that is ordinary small-dwelling size here (the confirmed townhouses
     above are 96-123 sqm), so "small" alone cannot imply "not a home".

IDENTITY_UNRESOLVED   -> no duplicate claim, temporarily noindex
  D  everything else, incl. the 36 "duplex-like" pairs. 63 groups.

WHY D IS NOT SIMPLY RELEASED TO THE INDEX
-----------------------------------------
Enrichment is attached by ADDRESS, not by resolved entity: transactions, photos,
valuation and floorplans are identical across every member of a group, while
LOT/PLAN/land area stay record-specific. A D page can therefore combine record A's
land identity with content that belongs to record B. Demonstrated at 4 Tea Gardens
Place: the 116 sqm parcel rendered the 829 sqm house's imagery and valuation while
displaying 116 sqm as its land area. That is a factual-integrity problem, not a
duplicate-content problem, so unresolved records stay noindex until identity is
resolved. See the address-level enrichment propagation diagnostic.

NAMING
------
`offmarket_multilot` now means "entity duplicate", not "multiple lots". Renaming it
to `offmarket_entity_duplicate` is a planned follow-up requiring a coordinated
migration across the three consumers above; it is deliberately NOT bundled here.
Read the flag as: "a different record is the published representation of this
entity."

Usage:
  python3 scripts/flag_multilot_offmarket.py --dry-run   # no writes, prints plan
  python3 scripts/flag_multilot_offmarket.py --report    # per-group diagnostics
  python3 scripts/flag_multilot_offmarket.py             # reconcile
"""
from __future__ import annotations
import argparse
import datetime
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "15_Off-Market", "Page_Redesign_V2"))

from shared.db import get_client
from job_status import job_run

# --- state fields -----------------------------------------------------------
DUP_FLAG = "offmarket_multilot"              # see NAMING above
UNRESOLVED_FLAG = "offmarket_entity_unresolved"
REASON_FIELD = "offmarket_suppression_reason"  # "redundant" | "non_dwelling"

SUFFIX = re.compile(r"-[0-9a-f]{4}$")

# --- CONFIRMED_NON_DWELLING thresholds (hand-verified; see CLASSIFICATION) ---
PARCEL_LOT_MIN = 900        # QLD DCDB reserves the 900-series for support parcels
CP_MIN_SQM = 2000.0         # common property: verified range 2,131-12,350 sqm
CP_MIN_RATIO = 2.5          # ...and always >=3x the dwelling lot in the verified set
STRIP_MAX_SQM = 150.0       # easement/access handle: verified 35, 53, 116 sqm
UNIFORM_MAX_SQM = 250.0     # B2 complex: verified 123 sqm; 96 sqm elsewhere
UNIFORM_MIN_MEMBERS = 4

# --- mass-release guard -----------------------------------------------------
# A detector returning far fewer suppressions than last time is far more likely to
# be broken than to reflect reality. Failing to detect is NOT proof that every
# previous detection is obsolete — that inference is exactly what caused the
# oscillation. Trip on absolute AND proportional change so the guard stays
# meaningful at any scale, and never hard-code a specific expected count.
GUARD_MIN_ABS_DROP = 40     # ignore small movements entirely
GUARD_MAX_DROP_PCT = 0.40   # >40% fewer than the last stable state = refuse to act
GUARD_STATE_COLL = "offmarket_identity_state"


def _nightly():
    """The deck builder owns the suburb list and the eligibility rules."""
    import offmarket_discovery_nightly as N
    return N


def suburbs(N, gc):
    # Frozen suburbs are still SERVED, so they still need correct state.
    return list(dict.fromkeys(N.target_suburbs(gc) + list(N.frozen_suburbs(gc))))


def candidate_query(N):
    """Eligibility WITHOUT either suppression flag.

    THE LOAD-BEARING LINE OF THIS FILE. `indexed_query()` legitimately excludes
    both flags — it answers "what is published right now" — but discovery must ask
    "what exists in the source data", or the job cancels its own previous run.
    Never pass `N.indexed_query()` to the detector.
    """
    q = dict(N.indexed_query())
    q.pop(DUP_FLAG, None)
    q.pop(UNRESOLVED_FLAG, None)
    return q


PROJECTION = {
    "url_slug": 1, "LOT": 1, "PLAN": 1, "PROPERTY_NAME": 1, "UNIT_TYPE": 1,
    "lot_size_sqm": 1, "ADDRESS_PID": 1, "address": 1,
}


def _sqm(m):
    try:
        return float(m.get("lot_size_sqm") or 0) or None
    except (TypeError, ValueError):
        return None


def _lot_int(m):
    lot = str(m.get("LOT") or "")
    return int(lot) if lot.isdigit() else None


def _plan(m):
    return str(m.get("PLAN") or "")


def is_non_dwelling_parcel(m, members):
    """True only for the two hand-verified shapes. Conservative by construction:
    anything else — including a merely small lot — is left for entity resolution."""
    lot = _lot_int(m)
    if lot is None or lot < PARCEL_LOT_MIN:
        return None
    size = _sqm(m)
    if size is None:
        return None
    if size <= STRIP_MAX_SQM:
        return "strip"
    others = [s for s in (_sqm(x) for x in members if x["_id"] != m["_id"]) if s]
    if not others:
        return None
    if (size >= CP_MIN_SQM and _plan(m).startswith("SP")
            and size / max(min(others), 1.0) >= CP_MIN_RATIO):
        return "common_property"
    return None


def is_confirmed_redundant(members):
    """A / B / B2 — the whole group provably describes one published entity."""
    if len({(m.get("LOT"), m.get("PLAN")) for m in members}) == 1:
        return "duplicate_cadastral_record"          # A
    if any(str(m.get("LOT")) == "9999" for m in members):
        return "common_property_lot_9999"            # B
    if any(m.get("PROPERTY_NAME") for m in members):
        return "community_title_scheme_name"         # B
    if any(m.get("UNIT_TYPE") for m in members):
        return "unit_type_present"                   # B
    sizes = {_sqm(m) for m in members}
    if (len(members) >= UNIFORM_MIN_MEMBERS and len(sizes) == 1
            and next(iter(sizes)) and next(iter(sizes)) <= UNIFORM_MAX_SQM):
        return "uniform_small_lots"                  # B2
    return None


def choose_survivor(members):
    """Deterministic and stable — a survivor that can change between runs would
    reintroduce oscillation in a new form, so live search data is deliberately NOT
    an input here (see the note in the module docstring's follow-ups). The
    unsuffixed slug is the URL Google already knows in practice, which gives us
    search continuity without the instability.

    1. the established unsuffixed slug
    2. the most complete cadastral identity
    3. lowest ADDRESS_PID
    """
    def key(m):
        slug = m.get("url_slug") or ""
        unsuffixed = 0 if SUFFIX.search(slug) else 1
        completeness = sum(1 for f in ("LOT", "PLAN", "lot_size_sqm") if m.get(f))
        pid = m.get("ADDRESS_PID")
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            pid = 1 << 62
        return (-unsuffixed, -completeness, pid)
    return sorted(members, key=key)[0]


def classify_group(base, members):
    """-> dict(state, duplicates=[(id, reason)], unresolved=[id], survivor=id|None)"""
    out = {"base": base, "duplicates": [], "unresolved": [], "survivor": None,
           "state": None, "detail": None, "size": len(members)}

    reason = is_confirmed_redundant(members)
    if reason:
        survivor = choose_survivor(members)
        out.update(state="CONFIRMED_REDUNDANT", detail=reason, survivor=survivor["_id"],
                   duplicates=[(m["_id"], "redundant") for m in members
                               if m["_id"] != survivor["_id"]])
        return out

    parcels = [(m, k) for m in members for k in [is_non_dwelling_parcel(m, members)] if k]
    parcel_ids = {m["_id"] for m, _ in parcels}
    rest = [m for m in members if m["_id"] not in parcel_ids]

    if parcels and len(rest) == 1:
        out.update(state="CONFIRMED_NON_DWELLING",
                   detail=",".join(sorted({k for _, k in parcels})),
                   survivor=rest[0]["_id"],
                   duplicates=[(m["_id"], "non_dwelling") for m, _ in parcels])
        return out

    if parcels and len(rest) > 1:
        # e.g. 9 Maidstone Place: a 35 sqm strip plus two plausible house lots on
        # different plans. Suppress only what is proven; the remainder is unresolved.
        out.update(state="CONFIRMED_NON_DWELLING+UNRESOLVED",
                   detail=",".join(sorted({k for _, k in parcels})),
                   duplicates=[(m["_id"], "non_dwelling") for m, _ in parcels],
                   unresolved=[m["_id"] for m in rest])
        return out

    out.update(state="IDENTITY_UNRESOLVED", detail="address_identity_unresolved",
               unresolved=[m["_id"] for m in members])
    return out


def desired_state(gc, N, sub):
    """Derived ONLY from source evidence. Never reads DUP_FLAG/UNRESOLVED_FLAG."""
    by = defaultdict(list)
    for r in gc[sub].find(candidate_query(N), PROJECTION):
        slug = r.get("url_slug")
        if slug:
            by[SUFFIX.sub("", slug)].append(r)
    groups = [classify_group(b, ms) for b, ms in by.items() if len(ms) > 1]
    dup, unres = {}, set()
    for g in groups:
        for _id, why in g["duplicates"]:
            dup[_id] = why
        unres.update(g["unresolved"])
    return groups, dup, unres


def _guard(mon, desired_total, unresolved_total):
    """Refuse to act on an implausible collapse. Returns (ok, message)."""
    prior = mon[GUARD_STATE_COLL].find_one({"_id": "last_stable"}) or {}
    for label, now, key in (("duplicate", desired_total, "duplicates"),
                            ("unresolved", unresolved_total, "unresolved")):
        was = prior.get(key)
        if not was:
            continue
        drop = was - now
        if drop >= GUARD_MIN_ABS_DROP and drop / was > GUARD_MAX_DROP_PCT:
            return False, (f"{label} desired set collapsed {was} -> {now} "
                           f"({drop / was:.0%} drop, threshold {GUARD_MAX_DROP_PCT:.0%}). "
                           f"Failing closed WITHOUT mutating — a detector that stops "
                           f"detecting is not evidence that prior detections are obsolete.")
    return True, ""


def run(dry_run=False, report=False):
    N = _nightly()
    gc = N._gc()
    mon = get_client()["system_monitor"]

    all_groups, desired_dup, desired_unres = [], {}, set()
    per_sub = {}
    for sub in suburbs(N, gc):
        groups, dup, unres = desired_state(gc, N, sub)
        per_sub[sub] = (groups, dup, unres)
        all_groups += groups
        desired_dup.update(dup)
        desired_unres.update(unres)

    st = {
        "collision_groups": len(all_groups),
        "confirmed_redundant_groups": sum(1 for g in all_groups if g["state"] == "CONFIRMED_REDUNDANT"),
        "confirmed_non_dwelling_groups": sum(1 for g in all_groups if g["state"].startswith("CONFIRMED_NON_DWELLING")),
        "unresolved_identity_groups": sum(1 for g in all_groups if "UNRESOLVED" in g["state"]),
        "desired_duplicate_suppressions": len(desired_dup),
        "desired_unresolved_records": len(desired_unres),
        "survivors": sum(1 for g in all_groups if g["survivor"]),
        "dup_before": 0, "unres_before": 0,
        "dup_added": 0, "dup_released": 0,
        "unres_added": 0, "unres_resolved": 0,
        "dup_after": 0, "unres_after": 0,
        "indexable_after": 0, "invariant": "not_run", "guard": "ok",
    }

    if report:
        for g in sorted(all_groups, key=lambda g: (g["state"], g["base"])):
            print(f"{g['state']:<34} n={g['size']} {g['base']:<46} {g['detail']}")
        return st

    for sub, (groups, dup, unres) in per_sub.items():
        st["dup_before"] += gc[sub].count_documents({DUP_FLAG: True})
        st["unres_before"] += gc[sub].count_documents({UNRESOLVED_FLAG: True})

    ok, msg = _guard(mon, len(desired_dup), len(desired_unres))
    if not ok:
        st["guard"] = "TRIPPED"
        print(f"\nGUARD TRIPPED: {msg}")
        raise RuntimeError(f"mass-release guard tripped: {msg}")

    for sub, (groups, dup, unres) in per_sub.items():
        cur_dup = {d["_id"] for d in gc[sub].find({DUP_FLAG: True}, {"_id": 1})}
        cur_unres = {d["_id"] for d in gc[sub].find({UNRESOLVED_FLAG: True}, {"_id": 1})}
        to_flag = set(dup) - cur_dup
        to_release = cur_dup - set(dup)
        to_unres = unres - cur_unres
        to_resolve = cur_unres - unres
        print(f"{sub:20s} groups={len(groups):>4} "
              f"dup: desired={len(dup):>4} +{len(to_flag):<4} -{len(to_release):<4} | "
              f"unresolved: desired={len(unres):>4} +{len(to_unres):<4} -{len(to_resolve):<4}")
        if dry_run:
            continue
        for _id in to_flag:
            gc[sub].update_one({"_id": _id},
                               {"$set": {DUP_FLAG: True, REASON_FIELD: dup[_id]},
                                "$unset": {UNRESOLVED_FLAG: ""}})
            st["dup_added"] += 1
        if to_release:
            st["dup_released"] += gc[sub].update_many(
                {"_id": {"$in": list(to_release)}},
                {"$unset": {DUP_FLAG: "", REASON_FIELD: ""}}).modified_count
        if to_unres:
            st["unres_added"] += gc[sub].update_many(
                {"_id": {"$in": list(to_unres)}},
                {"$set": {UNRESOLVED_FLAG: True}}).modified_count
        if to_resolve:
            st["unres_resolved"] += gc[sub].update_many(
                {"_id": {"$in": list(to_resolve)}},
                {"$unset": {UNRESOLVED_FLAG: ""}}).modified_count
        # Keep the reason current for records already flagged.
        for _id, why in dup.items():
            if _id in cur_dup:
                gc[sub].update_one({"_id": _id}, {"$set": {REASON_FIELD: why}})

    if dry_run:
        return st

    for sub in per_sub:
        st["dup_after"] += gc[sub].count_documents({DUP_FLAG: True})
        st["unres_after"] += gc[sub].count_documents({UNRESOLVED_FLAG: True})
        st["indexable_after"] += gc[sub].count_documents(_nightly().indexed_query())

    st["invariant"] = ("pass" if st["dup_after"] == len(desired_dup)
                       and st["unres_after"] == len(desired_unres) else "FAIL")
    mon[GUARD_STATE_COLL].update_one(
        {"_id": "last_stable"},
        {"$set": {"duplicates": len(desired_dup), "unresolved": len(desired_unres),
                  "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}},
        upsert=True)

    # Diagnostics — these are data-quality findings, not SEO state. Kept out of the
    # suppression flags on purpose so nobody rebuilds "multilot" logic around them.
    mon["offmarket_entity_diagnostics"].delete_many({})
    mon["offmarket_entity_diagnostics"].insert_many([
        {"base": g["base"], "state": g["state"], "detail": g["detail"], "members": g["size"],
         "logged_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        for g in all_groups if "UNRESOLVED" in g["state"]
    ] or [{"base": None, "state": "none", "detail": "no unresolved groups", "members": 0,
           "logged_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}])
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute and print, write nothing")
    ap.add_argument("--report", action="store_true", help="per-group classification")
    args = ap.parse_args()
    if args.dry_run or args.report:
        st = run(dry_run=True, report=args.report)
        if not args.report:
            print(f"\ndry-run: {st['collision_groups']} groups | "
                  f"desired duplicates={st['desired_duplicate_suppressions']} "
                  f"unresolved={st['desired_unresolved_records']} "
                  f"survivors={st['survivors']}")
        return
    with job_run("flag_multilot_offmarket", cadence_hours=24,
                 title="Off-Market Entity Identity Reconciliation") as beat:
        st = run()
        beat.detail = (
            f"{st['collision_groups']} collision groups "
            f"({st['confirmed_redundant_groups']} redundant, "
            f"{st['confirmed_non_dwelling_groups']} non-dwelling, "
            f"{st['unresolved_identity_groups']} unresolved); "
            f"duplicates {st['dup_before']}->{st['dup_after']} "
            f"(+{st['dup_added']}/-{st['dup_released']}); "
            f"unresolved {st['unres_before']}->{st['unres_after']} "
            f"(+{st['unres_added']}/-{st['unres_resolved']}); "
            f"invariant={st['invariant']}")
        beat.metrics = st
        print("\n" + beat.detail)
        if st["invariant"] != "pass":
            raise RuntimeError(f"reconciliation invariant FAILED: {st}")


if __name__ == "__main__":
    main()
