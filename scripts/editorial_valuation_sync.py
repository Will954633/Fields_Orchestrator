#!/usr/bin/env python3
"""
editorial_valuation_sync.py — the durable link between valuation recompute and
property editorial (ai_analysis).

WHY THIS EXISTS
---------------
`ai_analysis` (the LLM editorial on /property pages) is frozen at generation
time. `valuation_data` recomputes on its own precompute cadence (step 18 /
precompute_valuations.py) — and because "comparables keep arriving", a property's
valuation refreshes roughly weekly EVEN WHEN its own inputs are unchanged. There
was no link invalidating editorial when the valuation moved, so a batch recompute
(2026-09-09→14) silently left 62 of 68 published editorials arguing from a
valuation snapshot that no longer exists — some quoting comp ranges that had
changed by >10%, and (worst) >$2M homes whose range the model had suppressed
still quoting a specific $ band. See fix-history 2026-09-15
[EDITORIAL-VALUATION-DESYNC] and memory editorial_valuation_staleness_and_freshness_gate.

WHAT IT DOES (nightly, after step 18 + step 120)
------------------------------------------------
For every published editorial in the target-market suburbs it compares
`ai_analysis.generated_at` against `valuation_data.computed_at`
(the ONLY reliable valuation timestamp) and CLASSIFIES the desync:

  * envelope_leak     — valuation now envelope-suppressed AND the editorial leaks
                        a $ range/worth for the subject (the acute case).  CRITICAL.
  * envelope_flip     — suppression state changed since the editorial was written
                        (valued↔suppressed) — the whole framing is now wrong.
  * material          — the valuation range moved >10% or the comparable set
                        changed vs the snapshot the editorial was written against.
  * stale_no_baseline — desynced but the editorial predates snapshot-recording, so
                        drift can't be measured; regenerated conservatively.
  * minor             — computed_at advanced but the numbers barely moved (the
                        common steady-state weekly-refresh case). NOT queued.

It FLAGS each listing on the doc (`ai_analysis.valuation_sync`) and enqueues the
regen-worthy ones onto `system_monitor.editorial_regen_queue`. It does NOT
regenerate (that costs ~$10/property on Opus-Max and is Will-triggered via
`generate_property_ai_analysis.py --stale-valuation`), and it does NOT publish.

It NEVER weakens the render-time `editorial_fresh` gate — that stays the acute
mitigation; this is the durable, content-level follow-up.

SELF-MONITORING (CLAUDE.md Rule 7 / 7b)
---------------------------------------
Wrapped in job_run(cadence_hours=24). The heartbeat asserts an OUTCOME, not merely
that nothing threw:
  * raises if a desync WAS detected but ZERO rows were enqueued (write path broken);
  * raises if not a single published+valued editorial could be read (upstream broken).
There is deliberately NO watermark/cursor: the flag is derived state recomputed in
full every run from current timestamps, so a failed run leaves prior flags intact
and the next run simply re-derives — nothing to advance, nothing to lose.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Load our own environment (Rule 7 checklist #3). shared.db also falls back
#     to config/settings.yaml, so the DB connection works even without .env. ---
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client, cosmos_retry  # noqa: E402

# Reuse the EXACT helpers the generator uses, so classification never drifts from
# the guard that produced the content (single source of truth for "suppressed?"
# and "does this text leak a $ figure?").
sys.path.insert(0, str(_ROOT / "scripts" / "backend_enrichment"))
from generate_property_ai_analysis import (  # noqa: E402
    TARGET_SUBURBS,
    _valuation_suppressed,
    _valuation_snapshot,
    _scan_envelope_dollar_leak,
)

sys.path.insert(0, str(_ROOT / "scripts"))
from job_status import job_run  # noqa: E402

MATERIAL_PCT = 10.0        # a range bound moving >10% is a material valuation change
COMP_JACCARD_MIN = 0.5     # comp-set overlap below this = the evidence base changed

# --- Price-absence contradiction (added 2026-09-15, see fix-history
#     [EDITORIAL-PRICE-ABSENCE-DESYNC]). This class is INVISIBLE to the valuation
#     checks below: the agent publishing a price guide does not touch
#     `valuation_data.computed_at`, so a page can be factually false while every
#     valuation timestamp says "fresh". It is checked BEFORE the desync gate.
_ABSENCE_RE = re.compile(
    r"no (price )?guide|without a (price )?guide|no (asking )?price\b"
    r"|no price (tag|yet|on the sign|is published)"
    r"|price is (not|never) (published|disclosed)|guide (was )?withdrawn",
    re.I,
)
# A real published figure, as opposed to a campaign placeholder that legitimately
# carries no number ("Auction", "Contact Agent", "Offers Close 22 August"...).
_PRICE_PLACEHOLDER_RE = re.compile(
    r"^(auction|contact agent|eoi|expressions|for sale$|just listed|price on|poa"
    r"|best offers|present all offers|under offer|submit all|by negotiation"
    r"|new to market|offers close|deadline)",
    re.I,
)
_MONEY_RE = re.compile(r"\$\s?[\d,]{6,}")
# Our own audit fields + archived originals must never be scanned.
_SKIP_KEYS = {"reframed_reason", "absence_reframed_at", "valuation_sync"}


def _walk_strings(obj, path=""):
    """Yield (dotted_path, text) for every string in ai_analysis, skipping
    private (`_`-prefixed), archived (`*_previous`) and audit-only fields."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_") or k.endswith("_previous") or k in _SKIP_KEYS:
                continue
            yield from _walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")


def _price_contradictions(prop: dict) -> list:
    """Editorial copy claiming the listing carries no price, on a listing that
    now publishes a real figure. Returns [(field_path, snippet), ...]."""
    price = (prop.get("price") or "").strip()
    if not _MONEY_RE.search(price) or _PRICE_PLACEHOLDER_RE.match(price):
        return []   # genuinely unpriced campaign — absence framing is TRUE
    out = []
    for fpath, text in _walk_strings(prop.get("ai_analysis") or {}):
        m = _ABSENCE_RE.search(text)
        if m:
            out.append((fpath, text[max(0, m.start() - 40):m.start() + 90]))
    return out


def _to_naive(dt):
    """Coerce a datetime (or ISO string) to naive UTC for comparison."""
    if dt is None:
        return None
    if isinstance(dt, str):
        from dateutil import parser as _p
        dt = _p.parse(dt)
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _pct_move(old, new):
    if not old or not new:
        return None
    return abs(new - old) / abs(old) * 100.0


def _classify(prop: dict) -> dict | None:
    """Return a valuation_sync record for a published editorial, or None if the
    doc isn't a published+valued editorial (i.e. out of scope for this check)."""
    ai = prop.get("ai_analysis") or {}
    vd = prop.get("valuation_data") or {}
    if ai.get("status") != "published" or not ai.get("generated_at") or not vd.get("computed_at"):
        return None

    gen = _to_naive(ai.get("generated_at"))
    comp = _to_naive(vd.get("computed_at"))
    desynced = bool(gen and comp and gen < comp)

    now_snap = _valuation_snapshot(prop)          # the CURRENT valuation
    base = ai.get("valuation_snapshot") or {}      # what the editorial was written against
    envelope_now = _valuation_suppressed(prop)
    envelope_at_gen = base.get("envelope_suppressed") if base else None

    rec = {
        "status": "fresh",
        "severity": "fresh",
        "needs_regen": False,
        "detected_at": datetime.now(timezone.utc),
        "editorial_generated_at": gen,
        "valuation_computed_at": comp,
        "envelope_now": envelope_now,
        "envelope_at_gen": envelope_at_gen,
        "baseline": "snapshot" if base else "none",
        "range_delta_pct": None,
        "leaks": [],
        "price_contradictions": [],
        "listing_price": prop.get("price"),
    }

    # 0) CRITICAL — the page says the listing has no price, and it does.
    #    Checked BEFORE the desync gate on purpose: a price guide published by the
    #    agent never advances `valuation_data.computed_at`, so this class is
    #    invisible to every timestamp comparison below. 10 live pages carried this
    #    falsehood for up to 43 days before the 2026-09-15 manual sweep.
    price_bad = _price_contradictions(prop)
    if price_bad:
        rec.update(
            status="stale",
            severity="price_contradiction",
            needs_regen=True,
            price_contradictions=[{"field": f, "snippet": s} for f, s in price_bad],
        )
        return rec

    if not desynced:
        # Editorial is at least as new as the valuation — nothing to do. Still
        # recorded so a previously-flagged, now-regenerated page is cleared.
        return rec

    rec["status"] = "stale"

    # 1) CRITICAL — envelope-suppressed home whose editorial leaks a $ range/worth.
    leaks = _scan_envelope_dollar_leak(ai) if envelope_now else []
    if leaks:
        rec.update(severity="envelope_leak", needs_regen=True, leaks=leaks)
        return rec

    # 2) Envelope suppression FLIPPED since the editorial was written.
    if envelope_at_gen is not None and bool(envelope_at_gen) != bool(envelope_now):
        rec.update(severity="envelope_flip", needs_regen=True)
        return rec
    if base and not base.get("comp_addresses") and envelope_now and not envelope_at_gen:
        rec.update(severity="envelope_flip", needs_regen=True)
        return rec

    # 3) MATERIAL drift measured against the snapshot the editorial was built on.
    if base:
        dlow = _pct_move(base.get("range_low"), now_snap.get("range_low"))
        dhigh = _pct_move(base.get("range_high"), now_snap.get("range_high"))
        deltas = [d for d in (dlow, dhigh) if d is not None]
        rec["range_delta_pct"] = round(max(deltas), 1) if deltas else None
        old_comps = set(base.get("comp_addresses") or [])
        new_comps = set(now_snap.get("comp_addresses") or [])
        if old_comps or new_comps:
            inter = len(old_comps & new_comps)
            union = len(old_comps | new_comps) or 1
            comp_jaccard = inter / union
        else:
            comp_jaccard = 1.0
        material = (rec["range_delta_pct"] is not None and rec["range_delta_pct"] > MATERIAL_PCT) \
            or comp_jaccard < COMP_JACCARD_MIN
        if material:
            rec.update(severity="material", needs_regen=True)
        else:
            rec.update(severity="minor", needs_regen=False)
        return rec

    # 4) No baseline snapshot (editorial predates snapshot-recording). Can't
    #    measure drift, so flag conservatively — the one-time sweep gives it a
    #    snapshot, after which steady-state uses the material-drift path above.
    rec.update(severity="stale_no_baseline", needs_regen=True)
    return rec


def _regen_command(suburbs):
    return (
        "bash -c 'source /home/fields/venv/bin/activate && "
        "set -a && source /home/fields/Fields_Orchestrator/.env && set +a && "
        "export ANTHROPIC_BACKEND= USE_CLAUDE_MAX=1 EDITORIAL_MODEL=claude-opus-4-8 "
        "COMPACT_COMPARABLES=1 THINKING_MODE=adaptive THINKING_EFFORT=medium && "
        "python3 scripts/backend_enrichment/generate_property_ai_analysis.py --stale-valuation'"
    )


def run(dry_run: bool = False, suburbs=None) -> dict:
    suburbs = suburbs or list(TARGET_SUBURBS)
    client = get_client()
    gc = client["Gold_Coast"]
    queue = client["system_monitor"]["editorial_regen_queue"]

    scanned = enqueued = cleared = 0
    by_sev: dict[str, int] = {}
    worklist = []

    for suburb in suburbs:
        docs = cosmos_retry(
            lambda s=suburb: list(gc[s].find(
                {"listing_status": "for_sale", "ai_analysis.status": "published"},
                {"address": 1, "url_slug": 1, "price": 1, "ai_analysis": 1,
                 "valuation_data": 1},
            )),
            f"edsync_{suburb}",
        )
        for prop in docs:
            rec = _classify(prop)
            if rec is None:
                continue
            scanned += 1
            by_sev[rec["severity"]] = by_sev.get(rec["severity"], 0) + 1

            if rec["needs_regen"]:
                worklist.append({
                    "suburb": suburb,
                    "address": prop.get("address"),
                    "url_slug": prop.get("url_slug"),
                    "severity": rec["severity"],
                    "range_delta_pct": rec["range_delta_pct"],
                    "editorial_generated_at": rec["editorial_generated_at"],
                    "valuation_computed_at": rec["valuation_computed_at"],
                })

            if dry_run:
                continue

            # Flag the doc (idempotent, derived state — no watermark).
            try:
                cosmos_retry(
                    lambda s=suburb, _id=prop["_id"], r=rec: gc[s].update_one(
                        {"_id": _id}, {"$set": {"ai_analysis.valuation_sync": r}}),
                    f"edsync_flag_{suburb}",
                )
            except Exception as e:
                print(f"[ERROR] flag write failed for {prop.get('address')}: {e}")
                continue

            if rec["needs_regen"]:
                enqueued += 1
                cosmos_retry(
                    lambda _id=prop["_id"], p=prop, s=suburb, r=rec: queue.replace_one(
                        {"_id": _id},
                        {
                            "_id": _id,
                            "suburb": s,
                            "address": p.get("address"),
                            "url_slug": p.get("url_slug"),
                            "severity": r["severity"],
                            "range_delta_pct": r["range_delta_pct"],
                            "editorial_generated_at": r["editorial_generated_at"],
                            "valuation_computed_at": r["valuation_computed_at"],
                            "detected_at": r["detected_at"],
                            "resolved": False,
                        },
                        upsert=True,
                    ),
                    "edsync_enqueue",
                )
            else:
                # Now fresh / minor — clear any prior open queue entry.
                res = cosmos_retry(
                    lambda _id=prop["_id"]: queue.update_one(
                        {"_id": _id, "resolved": False},
                        {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc)}}),
                    "edsync_resolve",
                )
                if getattr(res, "modified_count", 0):
                    cleared += 1

    desync = sum(v for k, v in by_sev.items() if k not in ("fresh",))
    regen_worthy = len(worklist)

    print("\n=== editorial ↔ valuation sync ===")
    print(f"scanned (published+valued): {scanned}")
    print(f"by severity: {by_sev}")
    print(f"desynced: {desync}  |  regen-worthy: {regen_worthy}  |  "
          f"{'would enqueue' if dry_run else 'enqueued'}: {regen_worthy if dry_run else enqueued}  |  cleared: {cleared}")
    if worklist:
        print("\nRegen worklist (severity | suburb | address):")
        _SEV_ORDER = {"price_contradiction": 0, "envelope_leak": 1}
        for w in sorted(worklist, key=lambda x: (_SEV_ORDER.get(x["severity"], 9), x["suburb"], x["address"] or "")):
            dp = f" Δ{w['range_delta_pct']}%" if w.get("range_delta_pct") else ""
            print(f"  {w['severity']:<18} {w['suburb']:<16} {w['address']}{dp}")
        print("\nTo regenerate the flagged set (Will-run — regenerates to DRAFT, then "
              "verify vs current valuation and publish):")
        print("  " + _regen_command(suburbs))

    client.close()
    return {
        "scanned": scanned, "desync": desync, "regen_worthy": regen_worthy,
        "enqueued": (regen_worthy if dry_run else enqueued), "cleared": cleared,
        "by_severity": by_sev,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report only — write no flags and enqueue nothing.")
    ap.add_argument("--suburb", help="Restrict to one suburb (default: all target suburbs).")
    args = ap.parse_args()
    suburbs = [args.suburb] if args.suburb else None

    if args.dry_run:
        run(dry_run=True, suburbs=suburbs)
        return

    with job_run("editorial_valuation_sync", cadence_hours=24,
                 title="Editorial ↔ Valuation Sync") as beat:
        res = run(dry_run=False, suburbs=suburbs)
        beat.metrics = res
        beat.detail = (f"{res['scanned']} scanned, {res['desync']} desynced, "
                       f"{res['enqueued']} enqueued for regen, {res['cleared']} cleared")

        # --- Rule 7b: assert an OUTCOME, not merely that nothing threw. ---
        if res["scanned"] == 0:
            # We expect published editorials WITH valuations to exist in the target
            # suburbs. Reading zero means the query/connection is broken upstream,
            # not that the book is genuinely empty.
            raise RuntimeError(
                "editorial_valuation_sync scanned 0 published+valued editorials — "
                "upstream read is broken, not an empty book.")
        if res["desync"] > 0 and res["enqueued"] == 0 and res["regen_worthy"] > 0:
            # Desync detected and regen-worthy rows identified, but none were
            # enqueued — the write path failed. Do not report success.
            raise RuntimeError(
                f"detected {res['desync']} desynced editorials ({res['regen_worthy']} "
                f"regen-worthy) but enqueued 0 — flag/queue write path is broken.")


if __name__ == "__main__":
    main()
