#!/usr/bin/env python3
"""
build_case_study — assemble a FULL business-school-style case study from a real
Gold_Coast sold home and store it in system_monitor.case_study_library.

A case study is the long-form, exhibit-backed version of a Market-tab card:
photo gallery (mirrored to our blob so it never breaks), floor plan, stat
exhibits, the sale timeline as data, the market it launched into, the
Domain-estimate-vs-reality exhibit, and a written multi-section analysis tying
the outcome to Fields principles + the book + research.

This is public information (sold prices, listing history, photos are all on the
public record / Domain), so homes are named. Editorial rules still apply:
factual, data-anchored, no advice, trade-offs framed as value.

Photos are MIRRORED to our own blob (shared.blob_storage, container
`case-studies`) via the existing pipeline pattern, so a withdrawn Domain
listing never breaks an older case study.

Usage:
  python3 -m scripts.property_reports.build_case_study \\
      --suburb varsity_lakes --address "1 Yawl Place" \\
      --concept overpricing --max-photos 14 [--dry-run]

The written analysis is authored separately (LLM or by hand) and merged via
--analysis-json; this script produces the verifiable DATA scaffold + mirrored
media so the narrative is never the thing that can be wrong.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_gold_coast_db, get_client  # noqa: E402
from shared import blob_storage  # noqa: E402
from scripts.property_reports import competitor_matcher as cm  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("build_case_study")

CONTAINER = "case-studies"
LIBRARY_DB = "system_monitor"
LIBRARY_COLL = "case_study_library"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _slugify(address: str) -> str:
    s = re.sub(r",?\s*(QLD|NSW|VIC)\s*\d{4}.*$", "", address, flags=re.I)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


def _full_res(url: str) -> str:
    """Upgrade a 150px rimh2 thumbnail to a full-res render where possible.
    rimh2 thumbnails embed the bucket path; the /fit-in/ form renders large."""
    if "rimh2.domainstatic.com.au" in url and "/fit-in/" not in url:
        # rimh2 URLs already serve full-res when the size segment is dropped;
        # leave as-is if we can't safely transform.
        return url
    return url


def _gather_photo_urls(doc: Dict[str, Any], limit: int) -> List[str]:
    """Best full-res candidate URLs, deduped by filename stem, capped at limit."""
    sources = (
        doc.get("property_images_original")
        or doc.get("scraped_property_images")
        or []
    )
    v2 = doc.get("scraped_data_v2") or {}
    if not sources and isinstance(v2, dict):
        sources = v2.get("image_urls") or []
    if not sources:
        sources = doc.get("property_images") or doc.get("domain_image_urls") or []
    seen, out = set(), []
    for u in sources:
        if not isinstance(u, str) or not u.strip():
            continue
        u = u.strip().rstrip("\\")
        stem = u.split("/")[-1].split("?")[0]
        if stem in seen:
            continue
        seen.add(stem)
        out.append(_full_res(u))
        if len(out) >= limit:
            break
    return out


def _download(url: str) -> Optional[bytes]:
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome120", timeout=40)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        log.warning(f"    download (cffi) failed: {e}")
    try:
        import requests
        r = requests.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        log.warning(f"    download (requests) failed: {e}")
    return None


def _mirror_photos(slug: str, urls: List[str], dry_run: bool) -> List[Dict[str, Any]]:
    """Download each photo and upload to our blob. Returns gallery entries with
    durable URLs. Skips (keeps Domain URL) only if a download fails."""
    gallery: List[Dict[str, Any]] = []
    for i, url in enumerate(urls):
        ext = ".jpg"
        m = re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
        blob_name = f"{slug}/{i:02d}{ext}"
        if dry_run:
            gallery.append({"url": url, "mirrored": False, "blob_name": blob_name})
            continue
        data = _download(url)
        if not data:
            gallery.append({"url": url, "mirrored": False})
            continue
        ct = "image/jpeg" if ext == ".jpg" else f"image/{ext.lstrip('.')}"
        public = blob_storage.upload(CONTAINER, blob_name, data, content_type=ct)
        if public:
            gallery.append({"url": public, "mirrored": True, "bytes": len(data)})
            log.info(f"    ✓ mirrored {i+1}/{len(urls)} → {public}")
        else:
            gallery.append({"url": url, "mirrored": False})
    return gallery


def _sale_timeline(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every sale/listing event from the Domain property-profile timeline, as
    a clean chart-ready series (newest first). is_sold + DOM + method per event."""
    v2 = doc.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    out = []
    for e in (tl or []):
        if not isinstance(e, dict) or e.get("category") != "Sale":
            continue
        out.append({
            "date": str(e.get("event_date"))[:10] if e.get("event_date") else None,
            "price": cm._parse_price(e.get("event_price")),
            "method": e.get("price_description"),
            "is_sold": bool(e.get("is_sold")),
            "days_on_market": e.get("days_on_market"),
        })
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


def _condition(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pvd = doc.get("property_valuation_data") or {}
    if not isinstance(pvd, dict):
        return None
    cs = pvd.get("condition_summary")
    if not cs:
        return None
    return cs if isinstance(cs, dict) else {"summary": str(cs)}


def _market_at_listing(db, suburb_display: str, sale_date: Optional[str]) -> Optional[Dict[str, Any]]:
    """Suburb market state — the conditions the home launched into.

    GUARD: the precomputed series are CURRENT (rolling-12-month) figures. They
    only describe "the market it sold into" when the sale is recent enough to
    fall in that window. For an older teaching case (e.g. a 2023 sale), today's
    median/YoY are NOT the conditions at the time — presenting them as such is a
    false claim. Require the sale within the last ~15 months, else return None
    (the case study simply omits the market exhibit)."""
    try:
        sd = dt.date.fromisoformat(str(sale_date)[:10])
        if (dt.date.today() - sd).days > 460:
            return None
    except Exception:
        return None
    out: Dict[str, Any] = {}
    try:
        ip = db["precomputed_indexed_prices"].find_one(
            {"suburb": suburb_display},
            {"_id": 0, "rolling_12m_median_price": 1, "rolling_12m_yoy_pct": 1,
             "transaction_count": 1},
        )
        if ip:
            out["median_price"] = ip.get("rolling_12m_median_price")
            out["yoy_pct"] = ip.get("rolling_12m_yoy_pct")
            out["transaction_count"] = ip.get("transaction_count")
    except Exception:
        pass
    try:
        dom = db["precomputed_market_charts"].find_one(
            {"suburb": suburb_display, "chart_type": "days_on_market"},
            {"_id": 0, "latest_quarter_median": 1},
        )
        if dom:
            out["suburb_median_dom"] = dom.get("latest_quarter_median")
    except Exception:
        pass
    return out or None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def build(suburb: str, address: str, concept: str, max_photos: int,
          analysis: Optional[Dict[str, Any]], dry_run: bool) -> Optional[Dict[str, Any]]:
    db = get_gold_coast_db()
    doc = db[suburb].find_one({"address": {"$regex": "^" + re.escape(address)}})
    if not doc:
        log.error(f"NOT FOUND: {address} in {suburb}")
        return None

    addr_full = doc.get("address")
    slug = _slugify(addr_full)
    log.info(f"Building case study: {addr_full} (slug={slug}, concept={concept})")

    timeline = _sale_timeline(doc)
    current = next((e for e in timeline if e["is_sold"]), None)

    photo_urls = _gather_photo_urls(doc, max_photos)
    log.info(f"  {len(photo_urls)} photo candidates; mirroring{' (dry-run)' if dry_run else ''}…")
    gallery = _mirror_photos(slug, photo_urls, dry_run)

    dv = doc.get("domain_valuation_at_listing") or {}
    domain_block = None
    # GUARD: the stored Domain estimate is only "at listing" if its capture date
    # is near the sale. Domain estimates drift with the market, so an estimate
    # scraped years after the sale is NOT a valid "estimate vs reality" exhibit
    # (e.g. a 2026 estimate against a 2023 sale). Require within ~120 days of the
    # sale date, else omit the exhibit rather than make a false-precision claim.
    def _estimate_is_contemporaneous() -> bool:
        try:
            est_d = dt.date.fromisoformat(str(dv.get("date"))[:10])
            sale_d = dt.date.fromisoformat(str(current.get("date"))[:10])
            return abs((est_d - sale_d).days) <= 120
        except Exception:
            return False
    if (isinstance(dv, dict) and dv.get("mid") and current and current.get("price")
            and _estimate_is_contemporaneous()):
        diff = (dv["mid"] - current["price"]) / current["price"] * 100
        domain_block = {
            "estimate_mid": dv.get("mid"),
            "estimate_low": dv.get("low"),
            "estimate_high": dv.get("high"),
            "grade": dv.get("accuracy"),
            "estimate_date": dv.get("date"),
            "sale_price": current["price"],
            "diff_pct": round(diff, 1),
            "direction": "above" if diff > 0 else "below",
        }

    suburb_disp = (doc.get("suburb") or suburb.replace("_", " ")).title()
    record: Dict[str, Any] = {
        "case_id": f"{concept}-{slug}",
        "concept": concept,
        "slug": slug,
        "published": False,                       # gate — flip after human review
        "address": addr_full,
        "suburb": suburb_disp,
        "facts": {
            "bedrooms": cm._to_int(doc.get("bedrooms")),
            "bathrooms": cm._to_int(doc.get("bathrooms")),
            "car_spaces": cm._to_int(doc.get("carspaces") or doc.get("car_spaces")),
            "land_sqm": cm._to_int(doc.get("land_size_sqm") or doc.get("lot_size_sqm")),
            "floor_sqm": cm._to_float(doc.get("total_floor_area")),
            "property_type": doc.get("property_type"),
        },
        "outcome": {
            "sale_price": current.get("price") if current else None,
            "sale_date": current.get("date") if current else None,
            "method": current.get("method") if current else None,
            "days_on_market": current.get("days_on_market") if current else None,
        },
        "gallery": gallery,
        "floor_plan": (doc.get("floor_plans_v2_extracted") or doc.get("floor_plans") or [None])[0]
                      if (doc.get("floor_plans_v2_extracted") or doc.get("floor_plans")) else None,
        "condition": _condition(doc),
        "sale_timeline": timeline,
        "market_at_listing": _market_at_listing(
            db, suburb_disp, current.get("date") if current else None),
        "domain_vs_reality": domain_block,
        "agent_description": (doc.get("agents_description") or "")[:1500] or None,
        "listing_url": doc.get("listing_url"),
        "analysis": analysis,                     # written sections, merged separately
        "source_doc_id": str(doc.get("_id")),
        "built_at": dt.datetime.utcnow().isoformat() + "Z",
    }

    if dry_run:
        log.info("  DRY RUN — not writing to DB. Record summary:")
        log.info(json.dumps({k: (f"<{len(v)} items>" if isinstance(v, list) else v)
                             for k, v in record.items()
                             if k in ("case_id", "address", "facts", "outcome",
                                      "domain_vs_reality")}, indent=1, default=str))
        log.info(f"  gallery={len(gallery)} timeline={len(timeline)} "
                 f"condition={'yes' if record['condition'] else 'no'} "
                 f"floor_plan={'yes' if record['floor_plan'] else 'no'}")
        return record

    coll = get_client()[LIBRARY_DB][LIBRARY_COLL]
    coll.update_one({"case_id": record["case_id"]}, {"$set": record}, upsert=True)
    log.info(f"  ✓ upserted case_study_library/{record['case_id']} "
             f"(published=False — review then flip)")
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", required=True, help="collection key, e.g. varsity_lakes")
    ap.add_argument("--address", required=True, help="street address prefix, e.g. '1 Yawl Place'")
    ap.add_argument("--concept", required=True,
                    choices=["overpricing", "well_priced", "auction_vs_pt", "renovation", "comparable"])
    ap.add_argument("--max-photos", type=int, default=14)
    ap.add_argument("--analysis-json", help="path to JSON with the written analysis sections")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    analysis = None
    if args.analysis_json:
        with open(args.analysis_json) as f:
            analysis = json.load(f)

    rec = build(args.suburb, args.address, args.concept, args.max_photos, analysis, args.dry_run)
    return 0 if rec else 1


if __name__ == "__main__":
    raise SystemExit(main())
