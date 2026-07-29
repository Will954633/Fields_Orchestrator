#!/usr/bin/env python3
"""
offmarket_coverage_scraper.py — Phase 1 of the Off-Market RL initiative.

Mint off-market HOUSE pages for Gold Coast suburbs so `/off-market/:slug` renders +
indexes for owners who Google their own address, growing the corpus (feedback surface)
for the reinforcement-learning content loop. Spec: 15_Off-Market/Reinforcement_Learning/00_SCOPING.md §7.

Per address (thin orchestrator over EXISTING functions — nothing re-parsed):
  enumerate bare cadastral skeleton
    → scraped_data: use existing scraped_data.property_timeline if present (ZERO fetch),
      else Bright-Data Domain-profile fetch (build_profile_url → fetch_html → _extract_from_html)
    → HOUSES-only filter (features.property_type == "House"; skip strata/UNIT_NUMBER)
    → extract_transactions (Sale-only; the rental-as-sale guard lives in enrich_cadastral)
    → require >=1 real sale (else the page renders but stays noindex — skip)
    → waterfront exclusion (out of scope)
    → write enriched off-market doc: property_type/beds/baths/car/lot + mixed-case address +
      url_slug (generate_slug, frontend-parity, collision-safe) + enriched_data.transactions;
      listing_status stays None (== off-market).

Safety:
  * --dry-run       : compute + report, NO DB writes (default for first look).
  * fetch is OFF by default (--fetch to enable); --max-fetch bounds Bright Data spend.
  * sitemap submission is a SEPARATE tool — this script NEVER pings Google.
  * real (non-dry) runs are wrapped in job_run(...) (CLAUDE.md Rule 7).

Reuse map (recon 2026-07-29): shared.domain_fetch.fetch_html · Feilds_Website/03_For_Sale_Coverage/
domain_profile_scraper.{build_profile_url,_extract_from_html} · scripts/enrich_cadastral.extract_transactions ·
scripts/migrate_url_slugs.generate_slug · shared.waterfront.detect_waterfront.
"""
import argparse
import sys
import time
from datetime import datetime, timezone

# --- import paths for the reused modules ------------------------------------
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, f"{ORCH}/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/03_For_Sale_Coverage")

from shared.db import get_gold_coast_db                     # noqa: E402
from shared.domain_fetch import fetch_html                  # noqa: E402
import domain_profile_scraper as dps                        # noqa: E402
from enrich_cadastral import extract_transactions           # noqa: E402
from migrate_url_slugs import generate_slug                 # noqa: E402

try:
    from src.mongo_client_factory import cosmos_retry       # noqa: E402
except Exception:
    def cosmos_retry(fn, *a, **kw):                         # fallback: no retry wrapper
        return fn(*a, **kw)

try:
    from shared.waterfront import detect_waterfront         # noqa: E402
except Exception:
    detect_waterfront = None

HOUSE_TYPES = {"House", "Duplex", "Semi", "Semi-Detached", "Villa", "Terrace", "Townhouse"}


def title_addr(doc):
    """Build a clean mixed-case display address from cadastral components.
    "12 GERSHWIN COURT NERANG QLD 4211" → "12 Gershwin Court, Nerang QLD 4211"."""
    no = str(doc.get("STREET_NO_1") or "").strip()
    name = str(doc.get("STREET_NAME") or "").strip().title()
    st = str(doc.get("STREET_TYPE") or "").strip().title()
    loc = str(doc.get("LOCALITY") or "").strip().title()
    pc = str(doc.get("POSTCODE") or "").strip()
    street = " ".join(p for p in [no, name, st] if p)
    tail = f"{loc} QLD {pc}".strip()
    return f"{street}, {tail}" if street and tail else (street or tail)


def resolve_scraped_data(doc, allow_fetch, fetch_budget):
    """Return (scraped_data, source, fetched:bool). Uses existing timeline first (0 fetch)."""
    sd = doc.get("scraped_data") or {}
    if sd.get("property_timeline"):
        return sd, "existing_timeline", False
    if not allow_fetch or fetch_budget[0] <= 0:
        return None, "needs_fetch_skipped", False
    addr = doc.get("complete_address") or title_addr(doc)
    url = dps.build_profile_url(addr)
    html = fetch_html(url)
    fetch_budget[0] -= 1
    if not html:
        return None, "fetch_failed", True
    try:
        data = dps._extract_from_html(html)
    except (ValueError, KeyError) as e:
        print(f"  ⚠ malformed Domain HTML for {addr}: {e}")
        return None, "fetch_parse_error", True
    if not data or not data.get("property_timeline"):
        return None, "no_timeline_on_domain", True
    data["url"] = url
    data["scraped_at"] = datetime.now().isoformat()
    return data, "domain_fetch", True


def is_house(sd):
    ft = (sd.get("features") or {}).get("property_type")
    return ft in HOUSE_TYPES


def process_doc(db, coll, doc, args, existing_slugs, fetch_budget):
    """Returns (status, detail_dict). Writes unless args.dry_run."""
    if doc.get("enriched_data", {}).get("transactions"):
        return "already_enriched", {}
    if (doc.get("UNIT_NUMBER") not in (None, "")):
        return "skip_strata_unit", {}

    sd, src, _ = resolve_scraped_data(doc, args.fetch, fetch_budget)
    if sd is None:
        return src, {}                                   # needs_fetch_skipped / fetch_failed / no_timeline

    if not is_house(sd):
        return "skip_not_house", {"type": (sd.get("features") or {}).get("property_type")}

    txns = extract_transactions({"scraped_data": sd})
    if len(txns) < 1:
        return "skip_no_sale", {}                        # would render but stay noindex

    # waterfront out of scope (honour an existing flag; best-effort detect otherwise)
    if doc.get("is_waterfront") is True:
        return "skip_waterfront", {}
    if detect_waterfront is not None:
        try:
            probe = dict(doc); probe["scraped_data"] = sd
            if detect_waterfront(probe).get("is_waterfront"):
                return "skip_waterfront", {}
        except Exception:
            pass

    feats = sd.get("features") or {}
    address = title_addr(doc)
    slug = generate_slug(address, args.suburb.replace("_", " "))
    base = slug
    n = 2
    while slug in existing_slugs:                          # collision-safe within collection
        slug = f"{base}-{n}"; n += 1
    existing_slugs.add(slug)

    update = {
        "address": address,
        "url_slug": slug,
        "property_type": feats.get("property_type") or "House",
        "scraped_data": sd,
        "enriched_data": {**(doc.get("enriched_data") or {}), "transactions": txns},
        "offmarket_coverage": {
            "source": src,
            "minted_at": datetime.now(timezone.utc).isoformat(),
            "sales": len(txns),
        },
    }
    for k_out, k_in in (("bedrooms", "bedrooms"), ("bathrooms", "bathrooms"), ("car_spaces", "car_spaces")):
        v = feats.get(k_in)
        if v is not None:
            update[k_out] = v
    if doc.get("lot_size_sqm") is None and feats.get("land_size"):
        update["lot_size_sqm"] = feats.get("land_size")

    detail = {"slug": slug, "type": update["property_type"], "sales": len(txns),
              "last_sale": txns[0], "source": src, "address": address}
    if not args.dry_run:
        cosmos_retry(coll.update_one, {"_id": doc["_id"]}, {"$set": update})
    return ("would_mint" if args.dry_run else "minted"), detail


def run(args):
    db = get_gold_coast_db()
    coll = db[args.suburb]
    existing_slugs = set(
        d["url_slug"] for d in coll.find(
            {"url_slug": {"$exists": True, "$ne": None}}, {"url_slug": 1}
        ) if d.get("url_slug")
    )
    # queue: skeletons without transactions; timeline-present first (zero fetch)
    q = {"enriched_data.transactions": {"$exists": False},
         "UNIT_NUMBER": {"$in": [None, ""]}}
    cur = coll.find(q).limit(args.limit)
    fetch_budget = [args.max_fetch]
    stats = {}
    minted = []
    processed = 0
    for doc in cur:
        if len([m for m in minted]) >= args.daily_cap:
            break
        status, detail = process_doc(db, coll, doc, args, existing_slugs, fetch_budget)
        stats[status] = stats.get(status, 0) + 1
        processed += 1
        if status in ("minted", "would_mint"):
            minted.append(detail)
            print(f"  ✓ {status}: /off-market/{detail['slug']}  [{detail['type']}, "
                  f"{detail['sales']} sales, last {detail['last_sale']['date']} "
                  f"${int(detail['last_sale']['price']):,}, src={detail['source']}]")
        if args.fetch and args.delay and status not in ("already_enriched", "skip_strata_unit"):
            time.sleep(args.delay)

    print(f"\n=== {args.suburb} — processed {processed} | "
          f"{'DRY-RUN (no writes)' if args.dry_run else 'WROTE to DB'} ===")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:24} {v}")
    print(f"  fetch used: {args.max_fetch - fetch_budget[0]} / {args.max_fetch}")
    return {"suburb": args.suburb, "processed": processed,
            "minted": len(minted), "dry_run": args.dry_run,
            "fetch_used": args.max_fetch - fetch_budget[0], "stats": stats,
            "slugs": [m["slug"] for m in minted]}


def main():
    ap = argparse.ArgumentParser(description="Off-market coverage scraper (Phase 1 RL).")
    ap.add_argument("--suburb", required=True, help="Gold_Coast collection name, e.g. nerang")
    ap.add_argument("--limit", type=int, default=200, help="max skeleton docs to scan")
    ap.add_argument("--daily-cap", type=int, default=500, help="max pages to mint this run")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, NO DB writes")
    ap.add_argument("--fetch", action="store_true", help="allow Bright Data Domain fetch for no-timeline docs")
    ap.add_argument("--max-fetch", type=int, default=5, help="cap Bright Data fetches this run")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between fetches (politeness)")
    args = ap.parse_args()

    print(f"offmarket_coverage_scraper — suburb={args.suburb} limit={args.limit} "
          f"dry_run={args.dry_run} fetch={args.fetch} max_fetch={args.max_fetch}")

    if args.dry_run:
        return run(args)

    # real run → self-monitored (Rule 7)
    try:
        from job_status import job_run
        with job_run("offmarket_coverage_scraper", cadence_hours=24,
                     title="Off-Market Coverage Scraper (houses, daily)") as beat:
            res = run(args)
            beat.detail = f"{args.suburb}: minted {res['minted']} (fetch {res['fetch_used']})"
            beat.metrics = {"minted": res["minted"], "processed": res["processed"],
                            "fetch_used": res["fetch_used"]}
            return res
    except ImportError:
        return run(args)


if __name__ == "__main__":
    main()
