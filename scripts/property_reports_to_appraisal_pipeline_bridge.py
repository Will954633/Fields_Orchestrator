#!/usr/bin/env python3
"""Bridge sync — property_reports (mini-site funnel) → appraisal_pipeline (ops review).

The mini-site (`/your-home/:slug`) funnel is address-only — the seller enters
their address and nothing else. Each entry creates a `property_reports` doc.

The existing ops dashboard (`AppraisalPipelinePanel.tsx`) reads from
`appraisal_pipeline` — a separate collection with an email-required schema
from the previous multi-step form flow. We're retiring the old form, but
during the transition the unified review surface is `appraisal_pipeline`.

This script mirrors property_reports → appraisal_pipeline:
    - Idempotent (uses `property_reports_slug` on the pipeline record as the
      join key — never duplicates).
    - email/name/phone left null (mini-site has no contact data; print is
      the delivery channel).
    - delivery_method = "print_only" — flags the new flow vs. the old
      email-required path.
    - stage defaults to `report_generating` so the analyst panel surfaces
      it immediately.

Run modes:
    --once  (default) — sync any unmirrored property_reports docs and exit
    --watch          — poll every 60s for new docs (run under systemd or
                       trigger-poller)

Per framework doc strategic choice (Will 2026-05-15): bridge for Phase A,
generalize the panel to read from both collections in Phase B.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.db import get_client  # type: ignore
from scripts.appraisal_template import data_pull, pick_highlight  # type: ignore


def find_subject_by_slug(slug: str) -> dict | None:
    """Find the Gold_Coast property doc matching this property_reports slug.
    Uses normalised address matching since slug → address → DB is fuzzy."""
    street, suburb = slug_to_address(slug)
    if not street or not suburb:
        return None
    db = get_client()["Gold_Coast"]
    suburb_key = suburb.lower().replace(" ", "_")
    coll = db[suburb_key]
    # Normalised match — DB stores complete_address uppercase
    norm_street = street.lower().strip()
    norm_suburb = suburb.lower().strip()
    for doc in coll.find({
        "$or": [
            {"street_address": {"$regex": f"^{street}$", "$options": "i"}},
            {"complete_address": {"$regex": street, "$options": "i"}},
        ]
    }, {"_id": 1, "street_address": 1, "complete_address": 1, "bedrooms": 1, "bathrooms": 1, "carspaces": 1, "land_size_sqm": 1, "property_valuation_data": 1}).limit(5):
        comp_addr = (doc.get("complete_address") or "").lower()
        if norm_street in comp_addr and norm_suburb in comp_addr:
            return doc
    return None


def compute_highlight_candidates(subject_doc: dict) -> list[dict]:
    """Run the highlight ranker for this subject and return the top-5 candidate
    list ready to embed on the pipeline record. Pruned for UI display —
    drops the raw filter dict (not useful in the ops UI; preserved in the
    substantiation file at render time).

    When the ranker returns nothing (median home with no distinguishing rarity),
    always append a bedroom-count fallback so the ops dashboard picker UI
    surfaces something the analyst can choose. Without this, the picker hides
    entirely and the analyst can't select a §01R highlight.
    """
    ranked = pick_highlight.rank(subject_doc, top_n=5)
    out = [
        {
            "key": c["key"],
            "description": c["description"],
            "count": c["count"],
            "universe_total": c["universe_total"],
            "ratio_str": c["ratio_str"],
            "share_pct": round(c["share"] * 100, 1),
        }
        for c in ranked
    ]
    if not out:
        # Bedroom-count fallback — always meaningful, always available.
        from scripts.appraisal_template import data_pull as _dp
        from shared.db import get_client as _gc
        beds = subject_doc.get("bedrooms") or 4
        catchment = _dp.catchment_for(subject_doc)
        f_total = _dp.universe_filter()
        f_match = {**f_total, "bedrooms": beds}
        _db = _gc()["Gold_Coast"]
        try:
            universe_total = sum(_db[s].count_documents(f_total) for s in catchment)
            match_count = sum(_db[s].count_documents(f_match) for s in catchment)
        except Exception:
            universe_total, match_count = 0, 0
        n_words = ["zero","one","two","three","four","five","six","seven","eight","nine"]
        beds_word = n_words[beds] if 0 <= beds <= 9 else str(beds)
        out.append({
            "key": "bedroom_count_fallback",
            "description": f"{beds_word} bedrooms",
            "count": match_count,
            "universe_total": universe_total,
            "ratio_str": f"{match_count}/{universe_total}" if universe_total else "—",
            "share_pct": round(100 * match_count / universe_total, 1) if universe_total else 0,
        })
    return out


def slug_to_address(slug: str) -> tuple[str, str]:
    """Parse "13-terrace-court-merrimac" → ("13 Terrace Court", "Merrimac").

    Heuristic: last token is the suburb (may be multi-word for "varsity-lakes"
    etc. — handled by the suburb list). Everything before that is the street
    address.
    """
    KNOWN_SUBURBS = {
        "merrimac": "Merrimac",
        "robina": "Robina",
        "varsity-lakes": "Varsity Lakes",
        "burleigh-waters": "Burleigh Waters",
        "burleigh-heads": "Burleigh Heads",
        "mermaid-beach": "Mermaid Beach",
        "mermaid-waters": "Mermaid Waters",
        "surfers-paradise": "Surfers Paradise",
        "broadbeach-waters": "Broadbeach Waters",
        "main-beach": "Main Beach",
        "palm-beach": "Palm Beach",
        "tugun": "Tugun",
        "currumbin-waters": "Currumbin Waters",
        "elanora": "Elanora",
    }
    slug_lower = slug.lower()
    for suburb_slug, suburb_display in KNOWN_SUBURBS.items():
        suffix = "-" + suburb_slug
        if slug_lower.endswith(suffix):
            street_slug = slug_lower[: -len(suffix)]
            street = " ".join(w.capitalize() for w in street_slug.split("-"))
            return street, suburb_display
    # Fallback — last token is the suburb
    parts = slug_lower.split("-")
    street = " ".join(w.capitalize() for w in parts[:-1])
    suburb = parts[-1].capitalize()
    return street, suburb


def build_pipeline_record_from_property_report(pr: dict) -> dict:
    """Compose the appraisal_pipeline record from a property_reports doc."""
    slug = pr.get("slug", "")
    street, suburb = slug_to_address(slug)
    now = datetime.now(timezone.utc)

    # Recommendation already finalised on the property_reports? If so, jump
    # ahead in the pipeline to `draft_ready`. Otherwise start at
    # `report_generating` so the analyst sees it queued for review.
    rec = pr.get("recommendation") or {}
    has_finalised = bool(rec.get("listing_price") or pr.get("valuation_finalised_at"))
    stage = "draft_ready" if has_finalised else "report_generating"

    address = f"{street}, {suburb}, QLD" if street and suburb else slug

    # Look up the subject in Gold_Coast and pre-compute highlight candidates
    # so the ops UI surfaces them without round-tripping through Python.
    subject_doc = find_subject_by_slug(slug)
    candidates: list[dict] = []
    subject_oid = None
    if subject_doc:
        subject_oid = str(subject_doc["_id"])
        try:
            candidates = compute_highlight_candidates(subject_doc)
        except Exception:
            candidates = []

    return {
        "property_reports_slug": slug,
        "subject_property_id": subject_oid,
        "highlight_candidates": candidates,
        "highlight_chosen_key": candidates[0]["key"] if candidates else None,
        "source": "mini_site",
        "delivery_method": "print_only",
        # Address-only funnel: no contact data captured at entry.
        "email": None,
        "name": None,
        "phone": None,
        "address": address,
        "suburb": suburb,
        "suburb_key": suburb.lower().replace(" ", "_"),
        "stage": stage,
        "stage_history": [
            {"stage": stage, "at": now, "by": "bridge_sync"},
        ],
        # Pre-populate the recommendation if we already have one from
        # property_reports — saves the analyst re-deriving it.
        "recommendation": rec or None,
        "valuation_finalised_at": pr.get("valuation_finalised_at"),
        "created_at": pr.get("created_at") or now,
        "updated_at": now,
        "bridged_at": now,
        "bridged_from": str(pr["_id"]),
    }


def sync_once(verbose: bool = True, refresh: bool = False) -> dict:
    """Mirror unmirrored property_reports docs into appraisal_pipeline. If
    `refresh=True`, also re-populate highlight_candidates on already-bridged
    records (useful when the cohort changes or the candidate ranker updates).
    """
    sm = get_client()["system_monitor"]
    counts = {
        "property_reports_total": 0,
        "already_bridged": 0,
        "newly_bridged": 0,
        "refreshed": 0,
        "errors": 0,
    }

    for pr in sm.property_reports.find({}):
        counts["property_reports_total"] += 1
        slug = pr.get("slug")
        if not slug:
            if verbose:
                print(f"  [skip] property_reports {pr['_id']} has no slug")
            continue

        existing = sm.appraisal_pipeline.find_one({"property_reports_slug": slug})
        if existing:
            counts["already_bridged"] += 1
            if refresh:
                try:
                    new_record = build_pipeline_record_from_property_report(pr)
                    # Refresh only the volatile cohort-derived fields, preserve
                    # everything else (especially analyst-edited fields).
                    sm.appraisal_pipeline.update_one(
                        {"_id": existing["_id"]},
                        {"$set": {
                            "subject_property_id": new_record["subject_property_id"],
                            "highlight_candidates": new_record["highlight_candidates"],
                            "highlight_chosen_key": existing.get("highlight_chosen_key") or new_record["highlight_chosen_key"],
                            "updated_at": datetime.now(timezone.utc),
                            "candidates_refreshed_at": datetime.now(timezone.utc),
                        }},
                    )
                    counts["refreshed"] += 1
                    if verbose:
                        nc = len(new_record["highlight_candidates"])
                        print(f"  [↻] {slug} → refreshed ({nc} candidates)")
                except Exception as e:
                    counts["errors"] += 1
                    if verbose:
                        print(f"  [err] refresh {slug}: {e}")
            else:
                if verbose:
                    print(f"  [skip] {slug} → already bridged (pipeline _id={existing['_id']})")
            continue

        try:
            record = build_pipeline_record_from_property_report(pr)
            result = sm.appraisal_pipeline.insert_one(record)
            counts["newly_bridged"] += 1

            # Fire a process-300 trigger so trigger-poller invokes V4 to
            # actually render the PDF. Mini-site requests previously stalled
            # at `report_generating` because no trigger was being fired.
            # Skip if the record was bridged in already-finalised state
            # (draft_ready means a prior render exists, no auto-trigger needed).
            if record["stage"] == "report_generating":
                sm.trigger_requests.insert_one({
                    "process_id": "300",
                    "process_name": "Generate Appraisal Report (V4) — Bridge auto-trigger",
                    "phase": "appraisal",
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                    "triggered_by": "bridge_sync",
                    "note": str(result.inserted_id),
                    "started_at": None, "finished_at": None,
                    "exit_code": None, "output_tail": None,
                })

            if verbose:
                trigger_note = " · trigger fired" if record["stage"] == "report_generating" else ""
                print(
                    f"  [+] {slug} → pipeline _id={result.inserted_id} "
                    f"stage={record['stage']} address={record['address']} "
                    f"({len(record['highlight_candidates'])} candidates){trigger_note}"
                )
        except Exception as e:
            counts["errors"] += 1
            if verbose:
                print(f"  [err] {slug}: {e}")

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Poll every 60s instead of running once")
    parser.add_argument("--refresh", action="store_true", help="Re-populate highlight_candidates on already-bridged records")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-record logs")
    args = parser.parse_args()

    if args.watch:
        print("Bridge sync — watch mode (60s poll)")
        while True:
            t0 = time.time()
            counts = sync_once(verbose=not args.quiet, refresh=args.refresh)
            if counts["newly_bridged"] or counts["refreshed"]:
                print(f"  {datetime.now().isoformat(timespec='seconds')} — synced {counts['newly_bridged']} new, {counts['refreshed']} refreshed ({time.time()-t0:.1f}s)")
            sleep_for = max(60 - (time.time() - t0), 5)
            time.sleep(sleep_for)
    else:
        print(f"Bridge sync — once. Started: {datetime.now().isoformat(timespec='seconds')}")
        counts = sync_once(verbose=not args.quiet, refresh=args.refresh)
        print(f"\nTotals: {counts}")


if __name__ == "__main__":
    main()
