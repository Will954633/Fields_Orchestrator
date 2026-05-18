#!/usr/bin/env python3
"""
Address-level coverage audit for target market suburbs.

Joins the cadastral baseline (PSMA/GNAF addresses in Gold_Coast.<suburb>) against
every data-coverage dimension we capture per property:

  - Listing presence (ever listed, currently active, sold)
  - Image sources (current + recovered):
      * scraped_data_v2.image_urls / hero_image_url   (May 2026 Domain re-scrape)
      * scraped_data_apr01_recovered.images           (Apr 1 mongodump merge, Phase 1)
      * scraped_data_recently_sold_apr01_recovered    (Phase 2 address-match)
      * scraped_data_for_sale_apr01_recovered         (Phase 2 address-match)
      * property_images_original / scraped_property_images / property_images
  - Floor plans (floor_plans, scraped_floor_plans, floor_plans_original)
  - Photo analysis (image_analysis, ollama_image_analysis)
  - Floor-plan analysis (ollama_floor_plan_analysis, floor_plan_analysis)
  - Satellite analysis (satellite_analysis)
  - Valuation (valuation_data, iteration_08_valuation, domain_valuation_at_listing)

Three modes:

  --summary             Per-suburb % coverage table (default)
  --csv                 Per-address coverage rows → logs/coverage/addresses_<suburb>.csv
  --address "1 Glenside Dr Robina"
                        Single-address lookup, prints full coverage report
  --check-urls N        Spot-check N random image URLs per sidecar source for liveness

Outputs go to logs/coverage/.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()

DB_NAME = "Gold_Coast"
TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
LOG_DIR = REPO_ROOT / "logs" / "coverage"


# ---------------------------------------------------------------------------
# Address normalisation
# ---------------------------------------------------------------------------

_NORM_RE = re.compile(r"[^A-Z0-9 ]+")


def norm_address(value: Any) -> str:
    """Uppercase, strip punctuation, collapse whitespace. Survives 'Dr' vs 'Drive'
    only partially — falls back to substring match for free-text lookups."""
    if not value:
        return ""
    s = str(value).upper()
    s = _NORM_RE.sub(" ", s)
    return " ".join(s.split())


def reconstruct_cadastral_address(doc: Dict[str, Any]) -> str:
    """Build a human-readable address from cadastral fields if no listing address."""
    parts = []
    unit = doc.get("UNIT_NUMBER")
    no1 = doc.get("STREET_NO_1")
    no2 = doc.get("STREET_NO_2")
    name = doc.get("STREET_NAME")
    stype = doc.get("STREET_TYPE")
    loc = doc.get("LOCALITY")
    pc = doc.get("POSTCODE")
    if not name:
        return doc.get("address") or doc.get("complete_address") or doc.get("street_address") or ""
    num = f"{no1}" if no1 else ""
    if no2:
        num += f"-{no2}"
    if unit:
        num = f"{unit}/{num}" if num else str(unit)
    street = " ".join(p for p in [name, stype] if p)
    line = " ".join(p for p in [num, street] if p)
    tail = ", ".join(p for p in [loc, "QLD", str(pc) if pc else None] if p)
    return f"{line}, {tail}" if tail else line


# ---------------------------------------------------------------------------
# Coverage dimensions
# ---------------------------------------------------------------------------

def _nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return len(value) > 0
    return True


def image_counts(doc: Dict[str, Any]) -> Dict[str, int]:
    """Count usable images from each source on the doc."""
    v2 = doc.get("scraped_data_v2") or {}
    apr01 = doc.get("scraped_data_apr01_recovered") or {}
    apr01_rs = doc.get("scraped_data_recently_sold_apr01_recovered") or {}
    apr01_fs = doc.get("scraped_data_for_sale_apr01_recovered") or {}

    return {
        "v2_images": len(v2.get("image_urls") or []) + (1 if v2.get("hero_image_url") else 0),
        "apr01_images": len(apr01.get("images") or []),
        "apr01_recently_sold_images": len(apr01_rs.get("images") or []),
        "apr01_for_sale_images": len(apr01_fs.get("images") or []),
        "property_images": len(doc.get("property_images") or []),
        "property_images_original": len(doc.get("property_images_original") or []),
        "scraped_property_images": len(doc.get("scraped_property_images") or []),
    }


def floor_plan_counts(doc: Dict[str, Any]) -> Dict[str, int]:
    apr01 = doc.get("scraped_data_apr01_recovered") or {}
    apr01_rs = doc.get("scraped_data_recently_sold_apr01_recovered") or {}
    apr01_fs = doc.get("scraped_data_for_sale_apr01_recovered") or {}
    return {
        "floor_plans": len(doc.get("floor_plans") or []),
        "floor_plans_original": len(doc.get("floor_plans_original") or []),
        "scraped_floor_plans": len(doc.get("scraped_floor_plans") or []),
        "v2_extracted_floor_plans": len(doc.get("floor_plans_v2_extracted") or []),
        "apr01_floor_plans": len(apr01.get("floor_plans") or []),
        "apr01_rs_floor_plans": len(apr01_rs.get("floor_plans") or []),
        "apr01_fs_floor_plans": len(apr01_fs.get("floor_plans") or []),
    }


def coverage_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one cadastral/listing doc into a coverage row."""
    imgs = image_counts(doc)
    fps = floor_plan_counts(doc)
    total_images = sum(imgs.values())
    total_floor_plans = sum(fps.values())

    listing_status = doc.get("listing_status")
    ever_listed = bool(
        listing_status
        or doc.get("listing_url")
        or doc.get("first_listed_date")
        or doc.get("history")
        or doc.get("price_history")
    )

    return {
        "address": doc.get("address") or doc.get("complete_address") or reconstruct_cadastral_address(doc),
        "street_address": doc.get("street_address"),
        "suburb": (doc.get("suburb") or doc.get("LOCALITY") or "").title(),
        "postcode": doc.get("postcode") or doc.get("POSTCODE"),
        "_id": str(doc.get("_id")),
        "listing_status": listing_status,
        "ever_listed": ever_listed,
        "is_cadastral_baseline": bool(doc.get("STREET_NAME")),
        "lot_size_sqm": doc.get("lot_size_sqm") or doc.get("lot_size_calc_sqm"),

        # image coverage
        "total_images": total_images,
        "has_any_image": total_images > 0,
        **{f"img_{k}": v for k, v in imgs.items()},

        # floor plans
        "total_floor_plans": total_floor_plans,
        "has_any_floor_plan": total_floor_plans > 0,
        **{f"fp_{k}": v for k, v in fps.items()},

        # analysis
        "has_image_analysis": _nonempty(doc.get("image_analysis")) or _nonempty(doc.get("ollama_image_analysis")),
        "has_floor_plan_analysis": _nonempty(doc.get("ollama_floor_plan_analysis")) or _nonempty(doc.get("floor_plan_analysis")),
        "has_satellite_analysis": _nonempty(doc.get("satellite_analysis")),

        # valuation
        "has_valuation_data": _nonempty(doc.get("valuation_data")),
        "has_catboost_valuation": _nonempty(doc.get("iteration_08_valuation")),
        "has_domain_valuation": _nonempty(doc.get("domain_valuation_at_listing")),

        # recovery / enrichment status
        "apr01_recovered": _nonempty(doc.get("apr01_recovery_at")),
        "images_blob_uploaded_at": doc.get("images_blob_uploaded_at"),
        "v2_scraped": _nonempty(doc.get("scraped_data_v2")),
        "v2_scrape_failed": _nonempty(doc.get("scraped_v2_failed_at")),
    }


# ---------------------------------------------------------------------------
# Iteration helpers
# ---------------------------------------------------------------------------

# Only the fields we read — cuts payload per doc by ~95% (cadastral docs are ~200KB).
PROJECTION = {
    "_id": 1, "address": 1, "complete_address": 1, "street_address": 1, "suburb": 1,
    "listing_status": 1, "listing_url": 1, "first_listed_date": 1, "history": 1, "price_history": 1,
    "STREET_NAME": 1, "STREET_TYPE": 1, "STREET_NO_1": 1, "STREET_NO_2": 1,
    "UNIT_NUMBER": 1, "LOCALITY": 1, "POSTCODE": 1, "postcode": 1,
    "lot_size_sqm": 1, "lot_size_calc_sqm": 1,
    # image arrays — only length is used, but mongo returns full arrays. Acceptable.
    "property_images": 1, "property_images_original": 1, "scraped_property_images": 1,
    "floor_plans": 1, "floor_plans_original": 1, "scraped_floor_plans": 1,
    "floor_plans_v2_extracted": 1,
    "image_analysis": 1, "ollama_image_analysis": 1,
    "ollama_floor_plan_analysis": 1, "floor_plan_analysis": 1,
    "satellite_analysis": 1,
    "valuation_data": 1, "iteration_08_valuation": 1, "domain_valuation_at_listing": 1,
    "scraped_data_v2": 1,
    "scraped_data_apr01_recovered": 1,
    "scraped_data_recently_sold_apr01_recovered": 1,
    "scraped_data_for_sale_apr01_recovered": 1,
    "apr01_recovery_at": 1, "images_blob_uploaded_at": 1, "scraped_v2_failed_at": 1,
}


def iter_suburb_rows(db, suburb: str) -> Iterable[Dict[str, Any]]:
    for doc in db[suburb].find({}, PROJECTION).batch_size(200):
        yield coverage_row(doc)


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def pct(num: int, denom: int) -> str:
    return f"{100*num/denom:.1f}%" if denom else "—"


def summarise(rows: List[Dict[str, Any]], suburb: str) -> Dict[str, Any]:
    total = len(rows)
    cadastral = sum(1 for r in rows if r["is_cadastral_baseline"])
    ever_listed = sum(1 for r in rows if r["ever_listed"])
    active = sum(1 for r in rows if r["listing_status"] == "for_sale")
    sold = sum(1 for r in rows if r["listing_status"] == "sold")
    under_contract = sum(1 for r in rows if r["listing_status"] == "under_contract")

    any_img = sum(1 for r in rows if r["has_any_image"])
    any_fp = sum(1 for r in rows if r["has_any_floor_plan"])
    img_analysis = sum(1 for r in rows if r["has_image_analysis"])
    fp_analysis = sum(1 for r in rows if r["has_floor_plan_analysis"])
    sat = sum(1 for r in rows if r["has_satellite_analysis"])
    val = sum(1 for r in rows if r["has_valuation_data"])

    apr01 = sum(1 for r in rows if r["apr01_recovered"])
    v2 = sum(1 for r in rows if r["v2_scraped"])
    v2_failed = sum(1 for r in rows if r["v2_scrape_failed"])

    # source-specific image presence
    src_counts = {key: 0 for key in [
        "img_v2_images", "img_apr01_images",
        "img_apr01_recently_sold_images", "img_apr01_for_sale_images",
        "img_property_images", "img_property_images_original", "img_scraped_property_images",
    ]}
    for r in rows:
        for k in src_counts:
            if r.get(k, 0) > 0:
                src_counts[k] += 1

    # source-specific floor-plan presence
    fp_src_counts = {key: 0 for key in [
        "fp_floor_plans", "fp_floor_plans_original", "fp_scraped_floor_plans",
        "fp_v2_extracted_floor_plans",
        "fp_apr01_floor_plans", "fp_apr01_rs_floor_plans", "fp_apr01_fs_floor_plans",
    ]}
    for r in rows:
        for k in fp_src_counts:
            if r.get(k, 0) > 0:
                fp_src_counts[k] += 1

    # records WITH listing history but NO image at all (the real gap)
    listed_no_img = sum(1 for r in rows if r["ever_listed"] and not r["has_any_image"])

    return {
        "suburb": suburb,
        "total": total,
        "cadastral": cadastral,
        "ever_listed": ever_listed,
        "active": active,
        "sold": sold,
        "under_contract": under_contract,
        "any_image": any_img,
        "any_floor_plan": any_fp,
        "image_analysis": img_analysis,
        "floor_plan_analysis": fp_analysis,
        "satellite_analysis": sat,
        "valuation_data": val,
        "apr01_recovered": apr01,
        "v2_scraped": v2,
        "v2_failed": v2_failed,
        "listed_no_image": listed_no_img,
        "src_counts": src_counts,
        "fp_src_counts": fp_src_counts,
    }


def render_summary_md(summaries: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append(f"# Address Coverage Audit — {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    lines.append("")
    lines.append("Per-suburb coverage across the cadastral baseline (every PSMA/GNAF address).")
    lines.append("Percentages are share of the suburb's total docs.")
    lines.append("")

    # Top-line table
    lines.append("## Coverage by suburb")
    lines.append("")
    lines.append("| Suburb | Total | Cadastral | Ever listed | Active | Sold | Any image | Any floor plan | Image analysis | FP analysis | Satellite | Valuation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in summaries:
        t = s["total"]
        lines.append(
            f"| {s['suburb']} | {t} | {s['cadastral']} ({pct(s['cadastral'], t)}) | "
            f"{s['ever_listed']} ({pct(s['ever_listed'], t)}) | {s['active']} | {s['sold']} | "
            f"{s['any_image']} ({pct(s['any_image'], t)}) | "
            f"{s['any_floor_plan']} ({pct(s['any_floor_plan'], t)}) | "
            f"{s['image_analysis']} ({pct(s['image_analysis'], t)}) | "
            f"{s['floor_plan_analysis']} ({pct(s['floor_plan_analysis'], t)}) | "
            f"{s['satellite_analysis']} ({pct(s['satellite_analysis'], t)}) | "
            f"{s['valuation_data']} ({pct(s['valuation_data'], t)}) |"
        )
    lines.append("")

    # Recovery / re-scrape outcome (the apr01 + v2 audit)
    lines.append("## Image-recovery outcome (apr01 mongodump merge + v2 re-scrape)")
    lines.append("")
    lines.append("| Suburb | apr01 recovered | v2 scraped | v2 failed | Listed but NO image |")
    lines.append("|---|---:|---:|---:|---:|")
    for s in summaries:
        t = s["total"]
        lines.append(
            f"| {s['suburb']} | {s['apr01_recovered']} ({pct(s['apr01_recovered'], t)}) | "
            f"{s['v2_scraped']} ({pct(s['v2_scraped'], t)}) | "
            f"{s['v2_failed']} | {s['listed_no_image']} |"
        )
    lines.append("")

    # Per-source breakdown
    lines.append("## Image source presence (records with >0 images from that source)")
    lines.append("")
    src_labels = {
        "img_v2_images": "v2 re-scrape",
        "img_apr01_images": "apr01 Phase 1 (_id match)",
        "img_apr01_recently_sold_images": "apr01 Phase 2 (recently_sold)",
        "img_apr01_for_sale_images": "apr01 Phase 2 (for_sale)",
        "img_property_images": "property_images (current)",
        "img_property_images_original": "property_images_original",
        "img_scraped_property_images": "scraped_property_images",
    }
    header = "| Suburb | " + " | ".join(src_labels.values()) + " |"
    sep = "|---|" + "---:|" * len(src_labels)
    lines.append(header)
    lines.append(sep)
    for s in summaries:
        cells = [s["suburb"]]
        for k in src_labels:
            cells.append(f"{s['src_counts'][k]}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Floor-plan source breakdown
    lines.append("## Floor-plan source presence (records with >0 floor plans from that source)")
    lines.append("")
    fp_labels = {
        "fp_floor_plans": "floor_plans (legacy)",
        "fp_floor_plans_original": "floor_plans_original (Domain CDN)",
        "fp_v2_extracted_floor_plans": "v2-extracted (GPT vision)",
        "fp_scraped_floor_plans": "scraped_floor_plans",
        "fp_apr01_floor_plans": "apr01 Phase 1",
        "fp_apr01_rs_floor_plans": "apr01 Phase 2 (recently_sold)",
        "fp_apr01_fs_floor_plans": "apr01 Phase 2 (for_sale)",
    }
    header = "| Suburb | " + " | ".join(fp_labels.values()) + " |"
    sep = "|---|" + "---:|" * len(fp_labels)
    lines.append(header)
    lines.append(sep)
    for s in summaries:
        cells = [s["suburb"]]
        for k in fp_labels:
            cells.append(f"{s['fp_src_counts'].get(k, 0)}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    # Stable column order: identity first, then booleans/counts
    head = [
        "_id", "address", "street_address", "suburb", "postcode",
        "listing_status", "ever_listed", "is_cadastral_baseline", "lot_size_sqm",
        "total_images", "has_any_image",
        "total_floor_plans", "has_any_floor_plan",
        "has_image_analysis", "has_floor_plan_analysis", "has_satellite_analysis",
        "has_valuation_data", "has_catboost_valuation", "has_domain_valuation",
        "apr01_recovered", "v2_scraped", "v2_scrape_failed", "images_blob_uploaded_at",
    ]
    tail = [k for k in rows[0].keys() if k not in head]
    cols = head + tail
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Address lookup
# ---------------------------------------------------------------------------

def lookup_address(db, query: str) -> List[Dict[str, Any]]:
    """Free-text lookup. Tries exact normalised match across target suburbs first,
    then substring."""
    qnorm = norm_address(query)
    hits: List[Tuple[str, Dict[str, Any]]] = []
    for suburb in TARGET_SUBURBS:
        # Use a regex on multiple address fields
        rx = re.compile(re.escape(query.split(",")[0].strip()), re.IGNORECASE)
        for doc in db[suburb].find({
            "$or": [
                {"address": {"$regex": rx}},
                {"complete_address": {"$regex": rx}},
                {"street_address": {"$regex": rx}},
            ]
        }, PROJECTION).limit(20):
            hits.append((suburb, doc))

        # Also cadastral-only (no listing address): match by STREET_NO_1 + STREET_NAME
        # Parse "1 Glenside Dr" → STREET_NO_1=1, STREET_NAME=GLENSIDE
        m = re.match(r"^\s*(\d+[A-Za-z]?)\s+([A-Za-z][A-Za-z\s'-]+?)(?:\s+(Dr|Drive|Rd|Road|St|Street|Ave|Avenue|Ct|Court|Cres|Crescent|Pl|Place|Way|Cl|Close|Tce|Terrace|Pde|Parade|Lane|Ln|Cct|Circuit|Bvd|Boulevard))?\b", query)
        if m:
            no = m.group(1)
            name = m.group(2).strip().upper()
            for doc in db[suburb].find({
                "STREET_NO_1": no,
                "STREET_NAME": name,
                "UNIT_NUMBER": None,
            }, PROJECTION).limit(10):
                hits.append((suburb, doc))

    # De-dup by _id
    seen = set()
    unique = []
    for s, d in hits:
        key = (s, str(d["_id"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append((s, d))
    return [{"suburb": s, **coverage_row(d)} for s, d in unique]


def render_address_report(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No matches.\n"
    out = []
    for r in rows:
        out.append("=" * 70)
        out.append(f"Address:           {r['address'] or '(cadastral only — no listing address)'}")
        out.append(f"_id:               {r['_id']}")
        out.append(f"Suburb / postcode: {r['suburb']} {r['postcode'] or ''}")
        out.append(f"Listing status:    {r['listing_status'] or '— never listed —'}")
        out.append(f"Ever listed:       {r['ever_listed']}")
        out.append(f"Lot size:          {r['lot_size_sqm']}")
        out.append("")
        out.append(f"  Images:          total={r['total_images']}  (any={r['has_any_image']})")
        for k in [
            "img_v2_images", "img_apr01_images",
            "img_apr01_recently_sold_images", "img_apr01_for_sale_images",
            "img_property_images", "img_property_images_original", "img_scraped_property_images",
        ]:
            out.append(f"    {k:42s} {r.get(k, 0)}")
        out.append(f"  Floor plans:     total={r['total_floor_plans']}  (any={r['has_any_floor_plan']})")
        for k in [
            "fp_floor_plans", "fp_floor_plans_original", "fp_scraped_floor_plans",
            "fp_apr01_floor_plans", "fp_apr01_rs_floor_plans", "fp_apr01_fs_floor_plans",
        ]:
            out.append(f"    {k:42s} {r.get(k, 0)}")
        out.append("")
        out.append(f"  image_analysis:        {r['has_image_analysis']}")
        out.append(f"  floor_plan_analysis:   {r['has_floor_plan_analysis']}")
        out.append(f"  satellite_analysis:    {r['has_satellite_analysis']}")
        out.append(f"  valuation_data:        {r['has_valuation_data']}")
        out.append(f"  catboost_valuation:    {r['has_catboost_valuation']}")
        out.append(f"  domain_valuation:      {r['has_domain_valuation']}")
        out.append("")
        out.append(f"  apr01_recovered:       {r['apr01_recovered']}")
        out.append(f"  v2_scraped:            {r['v2_scraped']}  (failed={r['v2_scrape_failed']})")
        out.append(f"  images_blob_uploaded:  {r['images_blob_uploaded_at']}")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# URL liveness spot-check
# ---------------------------------------------------------------------------

def spot_check_urls(db, sample_n: int = 5) -> str:
    """Pull a few image URLs per source and HEAD them to check liveness."""
    try:
        from curl_cffi import requests as cffi
    except ImportError:
        return "curl_cffi not available — skipping URL spot-check.\n"

    lines = ["", "## URL liveness spot-check", ""]
    sources = [
        ("scraped_data_v2.image_urls", "scraped_data_v2", "image_urls"),
        ("scraped_data_apr01_recovered.images", "scraped_data_apr01_recovered", "images"),
        ("property_images_original", "property_images_original", None),
    ]
    for label, field, sub in sources:
        urls = []
        for suburb in TARGET_SUBURBS:
            q = {field: {"$exists": True, "$ne": None}}
            for doc in db[suburb].find(q, {field: 1}).limit(50):
                arr = doc.get(field) if sub is None else (doc.get(field) or {}).get(sub) or []
                if isinstance(arr, list):
                    for u in arr:
                        if isinstance(u, str) and u.startswith("http"):
                            urls.append(u)
                        elif isinstance(u, dict) and u.get("url"):
                            urls.append(u["url"])
        if not urls:
            lines.append(f"- **{label}**: no URLs to check")
            continue
        sample = random.sample(urls, min(sample_n, len(urls)))
        ok, dead = 0, 0
        for u in sample:
            try:
                r = cffi.head(u, impersonate="chrome120", timeout=10, allow_redirects=True)
                if r.status_code < 400:
                    ok += 1
                else:
                    dead += 1
            except Exception:
                dead += 1
        lines.append(f"- **{label}**: {ok}/{len(sample)} live, {dead}/{len(sample)} dead/timeout")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburbs", nargs="+", default=TARGET_SUBURBS,
                    help=f"Suburb collections to audit (default: {TARGET_SUBURBS})")
    ap.add_argument("--summary", action="store_true", help="Per-suburb summary (default if no other mode)")
    ap.add_argument("--csv", action="store_true", help="Write per-address CSV files")
    ap.add_argument("--address", help="Lookup a specific address across target suburbs")
    ap.add_argument("--check-urls", type=int, default=0, metavar="N",
                    help="HEAD N random URLs per image source to check liveness")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    client = get_client()
    db = client[DB_NAME]

    if args.address:
        rows = lookup_address(db, args.address)
        print(render_address_report(rows))
        return 0

    summaries = []
    all_rows: Dict[str, List[Dict[str, Any]]] = {}
    for suburb in args.suburbs:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] scanning {suburb}...", file=sys.stderr)
        rows = list(iter_suburb_rows(db, suburb))
        all_rows[suburb] = rows
        summaries.append(summarise(rows, suburb))

    if args.csv:
        for suburb, rows in all_rows.items():
            out = LOG_DIR / f"addresses_{suburb}.csv"
            write_csv(rows, out)
            print(f"  → {out} ({len(rows)} rows)", file=sys.stderr)

    md = render_summary_md(summaries)
    if args.check_urls > 0:
        md += spot_check_urls(db, args.check_urls)

    out_md = LOG_DIR / f"address_audit_{datetime.now().strftime('%Y-%m-%d')}.md"
    out_md.write_text(md)
    print(md)
    print(f"\nWritten: {out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
