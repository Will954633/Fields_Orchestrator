#!/usr/bin/env python3
"""
select_teaser_leads.py — pick the next N owner-teaser mailing leads, reproducibly.

Audience (identical to PD-0002 / Fields_OT.1): people who viewed an /off-market/<slug>
page having arrived ORGANICALLY from Google, for the target suburbs. Ownership is
inferred from the self-address lookup (organic-pivot research: ~94% of organic
off-market visitors view a single address = an owner looking up their own home).

Source of truth: system_monitor.organic_journeys, filtered
    {is_offmarket: true, referring_domain: /google/i}
which is organic-by-construction (the journey builder drops every paid channel).
Ranked by engagement (deck card-views, then dwell, pageviews, session count).

Each candidate slug is resolved against Gold_Coast.<suburb> by url_slug to get its
real postal address and property_type; only detached **Houses** are kept (the teaser
pipeline + valuation envelope are house-only), and anything currently for_sale is
dropped (we do not mail homes listed with another agent).

Excludes every address we have already mailed — read from ALL of:
  * system_monitor.fulfilment_work_orders  (items[].slug)         — PD-0001
  * every manifest.csv passed via --exclude-manifest             — PD-0002, ...
  * scripts.test_addresses.TEST_ADDRESS_SLUGS
The mail_log collection is also consulted if present.

Writes the ranked [{slug, address}] list to --out (committed) AND to the path the
build driver reads (default /tmp/teaser_build_list_all98.json, overridable by the
TEASER_BUILD_LIST env var). Over-provision N (~65) to net 50 after the build-time
guards (PropRadar mailability + live 200 check + holding-band copy guard).

Usage:
  python3 select_teaser_leads.py --n 65 \
      --exclude-manifest .../pronto_batch_2026-08-26_bled/layup/manifest.csv \
      --out lead_lists/PD-0003_candidates.json
"""
from __future__ import annotations
import argparse, ast, csv, json, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from shared.db import get_client, get_gold_coast_db  # noqa: E402

OFF = re.compile(r"^/off-market/([a-z0-9][a-z0-9-]{2,80})/?$", re.I)
SUFFIX = {"robina": "robina", "varsity-lakes": "varsity_lakes",
          "burleigh-waters": "burleigh_waters"}


def exclusion_set(db, manifests):
    excl = set()
    for d in db["fulfilment_work_orders"].find({}):
        items = d.get("items")
        items = ast.literal_eval(items) if isinstance(items, str) else (items or [])
        for it in items:
            s = it.get("slug") if isinstance(it, dict) else None
            if s:
                excl.add(s.lower())
    for mf in manifests:
        with open(mf) as fh:
            for row in csv.DictReader(fh):
                if row.get("slug"):
                    excl.add(row["slug"].lower())
    if "mail_log" in db.list_collection_names():
        for d in db["mail_log"].find({}, {"slug": 1}):
            if d.get("slug"):
                excl.add(d["slug"].lower())
    try:
        import scripts.test_addresses as T
        excl |= {s.lower() for s in getattr(T, "TEST_ADDRESS_SLUGS", [])}
    except Exception:
        pass
    return excl


def ranked_candidates(db):
    """distinct off-market/google slugs -> best engagement tuple, ranked desc."""
    person = defaultdict(lambda: {"slugs": set(), "cards": 0, "dur": 0, "pv": 0, "sess": 0})
    for j in db["organic_journeys"].find(
            {"is_offmarket": True, "referring_domain": {"$regex": "google", "$options": "i"}}):
        P = person[j.get("distinct_id")]
        for p in [j.get("entry_path"), *(j.get("pages") or [])]:
            m = OFF.match((p or "").strip())
            if m and m.group(1).lower().endswith(tuple(SUFFIX)):
                P["slugs"].add(m.group(1).lower())
        P["cards"] = max(P["cards"], j.get("offmarket_card_views") or 0)
        P["dur"] += j.get("duration_s") or 0
        P["pv"] += j.get("pageviews") or 0
        P["sess"] += 1
    best = {}
    for P in person.values():
        key = (P["cards"], round(P["dur"]), P["pv"], P["sess"])
        for s in P["slugs"]:
            if s not in best or key > best[s]:
                best[s] = key
    return sorted(best.items(), key=lambda x: x[1], reverse=True)


def resolve_house(gc, slug):
    """Return (address, property_type, listing_status) if this slug is a resolvable
    detached House not currently for_sale, else None."""
    coll = None
    for suf, cname in SUFFIX.items():
        if slug.endswith(suf):
            coll = cname
            break
    if not coll:
        return None
    d = gc[coll].find_one(
        {"url_slug": slug},
        {"address": 1, "complete_address": 1, "property_type": 1, "listing_status": 1})
    if not d:
        return None
    ptype = d.get("property_type")
    if ptype != "House":                      # detached houses only
        return None
    if d.get("listing_status") == "for_sale":  # never mail a currently-listed home
        return None
    addr = d.get("address") or d.get("complete_address")
    if not addr:
        return None
    return addr, ptype, d.get("listing_status")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=65, help="candidates to emit (over-provision to net 50)")
    ap.add_argument("--exclude-manifest", action="append", default=[],
                    help="manifest.csv of a prior batch to exclude (repeatable)")
    ap.add_argument("--exclude-slugs-json", action="append", default=[],
                    help="JSON file to exclude: a list of slug strings, or of dicts "
                         "carrying a 'slug' key (e.g. a prior _build_results.json). Repeatable.")
    ap.add_argument("--out", required=True, help="committed output json path")
    ap.add_argument("--build-list", default=os.environ.get(
        "TEASER_BUILD_LIST", "/tmp/teaser_build_list_all98.json"),
        help="also write the list here for run_teaser_batch.py to read")
    args = ap.parse_args()

    db = get_client()["system_monitor"]
    gc = get_gold_coast_db()

    excl = exclusion_set(db, args.exclude_manifest)
    for jf in args.exclude_slugs_json:
        for e in json.load(open(jf)):
            s = e if isinstance(e, str) else (e.get("slug") if isinstance(e, dict) else None)
            if s:
                excl.add(s.lower())
    ranked = ranked_candidates(db)
    print(f"exclusion set: {len(excl)} slugs | ranked pool: {len(ranked)} slugs")

    out = []
    skipped = defaultdict(int)
    for slug, key in ranked:
        if len(out) >= args.n:
            break
        if slug in excl:
            skipped["already_mailed"] += 1
            continue
        r = resolve_house(gc, slug)
        if not r:
            skipped["not_house_or_unresolved"] += 1
            continue
        addr, ptype, lst = r
        out.append({"slug": slug, "address": addr,
                    "engagement": {"cards": key[0], "dwell_s": key[1], "pv": key[2], "sess": key[3]}})

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1)
    # build driver reads {slug,address}; keep the engagement for the record only
    json.dump([{"slug": e["slug"], "address": e["address"]} for e in out],
              open(args.build_list, "w"), indent=1)

    print(f"selected {len(out)} house candidates "
          f"(skipped: {dict(skipped)})")
    print(f"  committed -> {args.out}")
    print(f"  build list -> {args.build_list}")
    for i, e in enumerate(out, 1):
        print(f"  {i:>3}  {e['address']}")


if __name__ == "__main__":
    main()
