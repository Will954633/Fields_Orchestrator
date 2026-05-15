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

    return {
        "property_reports_slug": slug,
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


def sync_once(verbose: bool = True) -> dict:
    """Mirror any unmirrored property_reports docs into appraisal_pipeline.
    Returns counts dict."""
    sm = get_client()["system_monitor"]
    counts = {"property_reports_total": 0, "already_bridged": 0, "newly_bridged": 0, "errors": 0}

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
            if verbose:
                print(f"  [skip] {slug} → already bridged (pipeline _id={existing['_id']})")
            continue

        try:
            record = build_pipeline_record_from_property_report(pr)
            result = sm.appraisal_pipeline.insert_one(record)
            counts["newly_bridged"] += 1
            if verbose:
                print(
                    f"  [+] {slug} → pipeline _id={result.inserted_id} "
                    f"stage={record['stage']} address={record['address']}"
                )
        except Exception as e:
            counts["errors"] += 1
            if verbose:
                print(f"  [err] {slug}: {e}")

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Poll every 60s instead of running once")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-record logs")
    args = parser.parse_args()

    if args.watch:
        print("Bridge sync — watch mode (60s poll)")
        while True:
            t0 = time.time()
            counts = sync_once(verbose=not args.quiet)
            if counts["newly_bridged"]:
                print(f"  {datetime.now().isoformat(timespec='seconds')} — synced {counts['newly_bridged']} new ({time.time()-t0:.1f}s)")
            sleep_for = max(60 - (time.time() - t0), 5)
            time.sleep(sleep_for)
    else:
        print(f"Bridge sync — once. Started: {datetime.now().isoformat(timespec='seconds')}")
        counts = sync_once(verbose=not args.quiet)
        print(f"\nTotals: {counts}")


if __name__ == "__main__":
    main()
