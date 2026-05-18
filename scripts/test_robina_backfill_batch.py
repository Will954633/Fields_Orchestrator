#!/usr/bin/env python3
"""Test batch backfill for Robina addresses missing image coverage.

Reuses scrape_property_profiles.py machinery on a hand-picked batch of _ids
(saved to /tmp/robina_test_batch_ids.json by an earlier discovery step) and
reports per-record before → after coverage so we can see whether Domain has
profile data for cadastral addresses missing from our index.

Run:
    python3 scripts/test_robina_backfill_batch.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bson import ObjectId
from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore
from shared.domain_fetch import fetch_html  # type: ignore

load_env()

# Reuse the parser and URL builder from the production scraper
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scrape_property_profiles import build_profile_url, parse_property_profile  # type: ignore

BATCH_FILE = Path("/tmp/robina_test_batch_ids.json")
SUBURB = "robina"
TIMEOUT = 120
DELAY_BETWEEN = 2.0  # seconds between dispatch (be polite)


def short_addr(doc: dict) -> str:
    unit = doc.get("UNIT_NUMBER")
    parts = [
        str(unit) + "/" if unit else "",
        str(doc.get("STREET_NO_1") or ""),
        str(doc.get("STREET_NAME") or "").title(),
        str(doc.get("STREET_TYPE") or "").title(),
    ]
    return " ".join(p for p in parts if p).strip()


def snapshot(doc: dict) -> dict:
    """Pre/post coverage snapshot."""
    sv2 = doc.get("scraped_data_v2") or {}
    apr01 = doc.get("scraped_data_apr01_recovered") or {}
    return {
        "has_v2": bool(doc.get("scraped_data_v2")),
        "v2_image_count": len(sv2.get("image_urls") or []),
        "v2_hero_image": sv2.get("hero_image_url"),
        "has_apr01": bool(doc.get("scraped_data_apr01_recovered")),
        "apr01_image_count": len(apr01.get("images") or []),
        "domain_hero_image_url": doc.get("domain_hero_image_url"),
        "scraped_v2_failed_at": doc.get("scraped_v2_failed_at"),
        "scraped_v2_failed_reason": doc.get("scraped_v2_failed_reason"),
        "valuation_lower": (sv2.get("valuation") or {}).get("lower"),
        "valuation_mid": (sv2.get("valuation") or {}).get("mid"),
        "comp_sales_count": len(sv2.get("comparable_sales") or []),
    }


def run_one(db, doc_id: str) -> dict:
    """Fetch + parse + write one record. Returns a result row."""
    coll = db[SUBURB]
    before = coll.find_one({"_id": ObjectId(doc_id)})
    if not before:
        return {"_id": doc_id, "status": "NOT_FOUND"}

    addr = short_addr(before)
    pre = snapshot(before)

    url = build_profile_url(before)
    if not url:
        return {"_id": doc_id, "address": addr, "status": "NO_URL", "url": None,
                "before": pre, "after": pre}

    t0 = time.time()
    html = fetch_html(url, timeout=TIMEOUT)
    fetch_ms = int((time.time() - t0) * 1000)

    if not html:
        coll.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"scraped_v2_failed_at": dt.datetime.utcnow(),
                      "scraped_v2_failed_reason": "fetch"}},
        )
        return {"_id": doc_id, "address": addr, "status": "FETCH_FAIL", "url": url,
                "fetch_ms": fetch_ms, "before": pre, "after": snapshot(coll.find_one({"_id": ObjectId(doc_id)}))}

    parsed = parse_property_profile(html)
    if not parsed:
        # Save a snippet to disk for diagnosis
        snippet_path = Path(f"/tmp/robina_parse_fail_{doc_id}.html")
        snippet_path.write_text(html[:5000])
        coll.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"scraped_v2_failed_at": dt.datetime.utcnow(),
                      "scraped_v2_failed_reason": "parse"}},
        )
        return {"_id": doc_id, "address": addr, "status": "PARSE_FAIL", "url": url,
                "fetch_ms": fetch_ms, "html_len": len(html),
                "snippet_at": str(snippet_path),
                "before": pre, "after": snapshot(coll.find_one({"_id": ObjectId(doc_id)}))}

    # Write success
    now = dt.datetime.utcnow()
    set_doc = {
        "scraped_data_v2": parsed,
        "scraped_at_v2": now,
        "scraped_url_v2": url,
        "domain_hero_image_url": parsed.get("hero_image_url"),
        "domain_image_urls": parsed.get("image_urls"),
    }
    if parsed.get("address_line"):
        set_doc["address"] = parsed["address_line"]
    coll.update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": set_doc, "$unset": {"scraped_v2_failed_at": "", "scraped_v2_failed_reason": ""}},
    )
    after = snapshot(coll.find_one({"_id": ObjectId(doc_id)}))
    return {"_id": doc_id, "address": addr, "status": "SUCCESS", "url": url,
            "fetch_ms": fetch_ms, "before": pre, "after": after,
            "parsed_image_count": parsed.get("image_count"),
            "parsed_comp_sales": len(parsed.get("comparable_sales") or [])}


def main() -> int:
    if not BATCH_FILE.exists():
        print(f"ERROR: {BATCH_FILE} not found. Run the discovery step first.", file=sys.stderr)
        return 2

    ids = json.loads(BATCH_FILE.read_text())
    print(f"Test batch: {len(ids)} Robina records")
    print(f"Source: {BATCH_FILE}")
    print()

    client = get_client()
    db = client["Gold_Coast"]

    results = []
    for i, doc_id in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] {doc_id} ...", end=" ", flush=True)
        try:
            res = run_one(db, doc_id)
        except Exception as e:
            print(f"EXCEPTION: {type(e).__name__}: {e}")
            results.append({"_id": doc_id, "status": "EXCEPTION", "error": str(e)})
            continue
        print(f"{res['status']} ({res.get('fetch_ms', '-')}ms)")
        results.append(res)
        if i < len(ids):
            time.sleep(DELAY_BETWEEN)

    print()
    print("=" * 76)
    print("RESULTS")
    print("=" * 76)
    status_counts = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    for s, c in sorted(status_counts.items()):
        print(f"  {s}: {c}")
    print()

    print("Per-record detail:")
    for r in results:
        print()
        print(f"  {r['_id']} — {r.get('address', '?')}")
        print(f"    status: {r['status']}    url: {r.get('url', '-')}")
        if "before" in r:
            b, a = r["before"], r["after"]
            changed = [k for k in b if b.get(k) != a.get(k)]
            if changed:
                for k in changed:
                    print(f"    Δ {k}: {b.get(k)!r:.80} → {a.get(k)!r:.80}")
            else:
                print(f"    (no change in DB)")
        if r.get("parsed_image_count") is not None:
            print(f"    parsed_image_count={r['parsed_image_count']}  comp_sales={r['parsed_comp_sales']}")
        if r.get("snippet_at"):
            print(f"    parse-fail snippet: {r['snippet_at']}")

    # Save full json
    out = Path(REPO_ROOT / "logs" / "coverage" / f"robina_test_batch_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, default=str, indent=2))
    print(f"\nFull results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
