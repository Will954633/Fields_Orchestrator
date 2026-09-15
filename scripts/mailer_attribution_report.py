#!/usr/bin/env python3
"""
mailer_attribution_report.py — the standing answer to "is the direct-mail method
worth doing?" One funnel per batch: pieces SENT → POSTED → OPENED (QR scanned) →
RETURNED → ENGAGED, plus a per-address detail line with each recipient's on-site
behaviour.

WHY THIS EXISTS
---------------
A mailer's whole point is attribution: without it we cannot tell a $4.80 C4 envelope
that produced a returning, deep-reading owner from one that vanished. The pieces are
address-attributable by slug; the QR now also carries a per-address `lead` token
(build_owner_mailer.ensure_mailer_token → lead-link-visit.mjs) so a scan binds the
device to the address and the nightly lead_web_activity.py pulls that device's FULL
cross-site journey onto the contact. This report rolls all of that up.

WHAT COUNTS AS A GENUINE OPEN (the QA trap, learned 2026-09-15)
--------------------------------------------------------------
An "open" logged BEFORE a batch was lodged with Australia Post is not a recipient —
it is our own proofing scan at generate/print time (one device scanned every OT.1
address on 2026-08-26, the day that batch's PDFs were built). So an off-market
`?from=mailer` hit counts as a genuine open only if its timestamp is on/after the
piece's posted_date (falling back to batch_date + a lead time when posting is
unconfirmed). This filter is principled — it needs no hard-coded QA device id.

SOURCES
  system_monitor.mail_log            one doc per (order, address): sent, posted_date, link_token, opened_*
  PostHog events                     off-market ?from=mailer opens + each device's journey
  system_monitor.crm_contacts        token-era: the bound contact's lead_web.activity/summary

Self-monitoring (Rule 7 + 7b): wrapped in job_run. Zero mailed pieces is a valid
"nothing to measure yet" outcome (no raise); a PostHog/DB failure (could not measure)
raises.

Run:
  python3 scripts/mailer_attribution_report.py                 # all batches
  python3 scripts/mailer_attribution_report.py --order PD-0003 # one batch
  python3 scripts/mailer_attribution_report.py --lead-days 2   # delivery lead time (default 2)
  python3 scripts/mailer_attribution_report.py --json          # machine-readable
"""
from __future__ import annotations

import argparse
import json as _json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client            # noqa: E402
from crm_sync import posthog_query          # noqa: E402 (hardened retry/limit helper)
from job_status import job_run              # noqa: E402
from fridge_engagement_report import summarise as fridge_summarise  # noqa: E402

AEST = timezone(timedelta(hours=10))
_SLUG_RE = re.compile(r"/off-market/([a-z0-9][a-z0-9-]{2,120})", re.I)

# Conversion surfaces — a mailer recipient reaching one of these is the outcome the
# whole funnel is for. Substring match on $pathname.
_CONVERSION_PATHS = ("/analyse-your-home", "/analyse", "/contact", "/book", "/subscribe")


def _parse_ts(s):
    if not s or str(s) == "None":
        return None
    s = str(s).strip().replace("Z", "+00:00")
    for cand in (s, s.split(".")[0] + "+00:00"):
        try:
            d = datetime.fromisoformat(cand)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _slug_of_url(url: str):
    m = _SLUG_RE.search(url or "")
    return m.group(1).lower() if m else None


def _open_cutoff(piece: dict, lead_days: int):
    """The earliest a scan of this piece could be a real recipient: posted_date if
    known, else batch_date + lead_days (mail cannot be scanned before it is delivered).
    Returns an aware datetime, or None if neither date is parseable (then any open counts)."""
    posted = _parse_ts((piece.get("posted_date") or "") + "T00:00:00+00:00"
                       if piece.get("posted_date") else None)
    if posted:
        return posted
    bd = piece.get("batch_date")
    if bd:
        d = _parse_ts(str(bd) + "T00:00:00+00:00")
        if d:
            return d + timedelta(days=lead_days)
    return None


def fetch_offmarket_mailer_hits():
    """Every off-market ?from=mailer pageview, grouped by slug. Returns
    slug -> {devices:set, first:dt, last:dt, views:int, by_device:{did:[ts,...]}}."""
    rows = posthog_query("""
        SELECT distinct_id, properties.$current_url AS url, timestamp
        FROM events
        WHERE event = '$pageview'
          AND properties.$current_url LIKE '%/off-market/%'
          AND (properties.$current_url LIKE '%from=mailer%'
               OR properties.utm_source = 'mailer')
        ORDER BY timestamp
    """)
    per = defaultdict(lambda: {"devices": set(), "first": None, "last": None,
                               "views": 0, "by_device": defaultdict(list)})
    for did, url, ts in rows:
        slug = _slug_of_url(url)
        if not slug:
            continue
        t = _parse_ts(ts)
        d = per[slug]
        d["devices"].add(did)
        d["views"] += 1
        d["by_device"][did].append(t)
        if t and (d["first"] is None or t < d["first"]):
            d["first"] = t
        if t and (d["last"] is None or t > d["last"]):
            d["last"] = t
    return per


def fetch_device_journeys(all_ids):
    """Per device: total pageviews, distinct visit-days, and whether they reached a
    conversion surface — the 'returned / engaged' signal beyond the off-market page."""
    if not all_ids:
        return {}
    idlist = "','".join(i.replace("'", "") for i in all_ids)
    rows = posthog_query(f"""
        SELECT distinct_id,
               count() AS pvs,
               count(distinct toDate(timestamp)) AS days,
               countIf({' OR '.join("properties.$pathname LIKE '%" + p + "%'" for p in _CONVERSION_PATHS)}) AS conv,
               min(timestamp) AS first_seen,
               max(timestamp) AS last_seen
        FROM events
        WHERE event = '$pageview' AND distinct_id IN ('{idlist}')
        GROUP BY distinct_id
    """)
    return {r[0]: {"pvs": int(r[1] or 0), "days": int(r[2] or 0),
                   "conv": int(r[3] or 0), "first": _parse_ts(r[4]),
                   "last": _parse_ts(r[5])} for r in rows}


def _is_offmarket_flow(flow) -> bool:
    """OT.1 / OTN.1 teasers put the QR at /off-market/<slug>?from=mailer. The PD-0001
    flows (Fields_01.1 / 02.1) used the OLDER /your-home/<slug> scheme, so an off-market
    ?from=mailer open can NEVER have come from a PD-0001 piece — attributing one to it
    would be a category error. 'OT' matches Fields_OT.1 + Fields_OTN.1 and not 01/02."""
    return "OT" in (flow or "")


def build(order_filter=None, lead_days=2):
    db = get_client()["system_monitor"]

    q = {"order_number": order_filter} if order_filter else {}
    pieces = list(db["mail_log"].find(q))
    by_slug = defaultdict(list)
    for p in pieces:
        by_slug[p["slug"]].append(p)
    hits = fetch_offmarket_mailer_hits()

    # SINGLE-ATTRIBUTION. Each genuine open is credited to exactly one piece: among the
    # off-market-scheme pieces for that slug whose delivery cutoff precedes the open,
    # the one with the LATEST cutoff (the most recent mailing that could have caused it).
    # No cutoff precedes it → pre-lodgement, i.e. our own proofing scan → dropped.
    opened = {}          # piece _id -> {"ts": dt, "dev": did}
    for slug, h in hits.items():
        cand = [p for p in by_slug.get(slug, [])
                if _is_offmarket_flow(p.get("flow_code")) or p.get("link_token")]
        if not cand:
            continue
        cuts = [(p, _open_cutoff(p, lead_days)) for p in cand]
        for did, tss in h["by_device"].items():
            for t in sorted(x for x in tss if x):
                elig = [(p, c) for p, c in cuts if c is not None and t >= c]
                if not elig:
                    continue                       # QA / pre-lodgement for every candidate
                p = max(elig, key=lambda pc: pc[1])[0]
                rec = opened.get(p["_id"])
                if rec is None or t < rec["ts"]:
                    opened[p["_id"]] = {"ts": t, "dev": did}
                break                              # first genuine open per device per slug

    # token-era: mail_log.opened_at stamped by lead-link-visit.mjs is authoritative
    for p in pieces:
        mo = _parse_ts(p.get("opened_at"))
        if mo:
            rec = opened.get(p["_id"])
            if rec is None or mo < rec["ts"]:
                opened[p["_id"]] = {"ts": mo,
                                    "dev": p.get("opened_distinct_id") or p.get("link_token")}

    devices = {r["dev"] for r in opened.values() if r["dev"]}
    devices |= {p["link_token"] for p in pieces if p.get("link_token")}
    journeys = fetch_device_journeys(devices)

    batches = defaultdict(lambda: {"sent": 0, "posted": 0, "opened": 0, "returned": 0,
                                   "engaged": 0, "converted": 0, "flow": None,
                                   "batch_date": None, "posted_date": None,
                                   "scheme_tracked": True, "rows": []})

    for p in pieces:
        order = p.get("order_number") or "?"
        b = batches[order]
        b["sent"] += 1
        b["flow"] = b["flow"] or p.get("flow_code")
        b["batch_date"] = b["batch_date"] or p.get("batch_date")
        b["posted_date"] = b["posted_date"] or p.get("posted_date")
        if not (_is_offmarket_flow(p.get("flow_code")) or p.get("link_token")):
            b["scheme_tracked"] = False           # PD-0001 /your-home — not this report's scheme
        if p.get("posted_date"):
            b["posted"] += 1

        rec = opened.get(p["_id"])
        jr = journeys.get(rec["dev"]) if rec else None
        jr = jr or journeys.get(p.get("link_token")) or {}
        returned = (jr.get("days", 0) or 0) >= 2
        engaged = (jr.get("pvs", 0) or 0) >= 3
        converted = (jr.get("conv", 0) or 0) > 0

        if rec:
            b["opened"] += 1
            b["returned"] += 1 if returned else 0
            b["engaged"] += 1 if engaged else 0
            b["converted"] += 1 if converted else 0

        b["rows"].append({
            "slug": p["slug"], "address": p.get("address") or p["slug"],
            "opened_at": rec["ts"].astimezone(AEST).strftime("%Y-%m-%d %H:%M") if rec else None,
            "opened_ts": rec["ts"] if rec else None,           # aware dt, for the backfill
            "device": rec["dev"] if rec else None,             # the scanner's distinct_id
            "piece_id": p["_id"], "order": order,
            "pageviews": jr.get("pvs"), "visit_days": jr.get("days"),
            "returned": returned if rec else None,
            "converted": converted if rec else None,
        })

    return batches


def render(batches) -> str:
    out = []
    tot = {"sent": 0, "posted": 0, "opened": 0, "returned": 0, "engaged": 0, "converted": 0}
    for order in sorted(batches):
        b = batches[order]
        for k in tot:
            tot[k] += b[k]
        rate = (100.0 * b["opened"] / b["sent"]) if b["sent"] else 0.0
        note = "" if b["scheme_tracked"] else "  ⚠ /your-home QR — not tracked by this report"
        out.append(f"\n━━ {order}  ({b['flow'] or '?'})  batch {b['batch_date'] or '?'}"
                   f"  posted {b['posted_date'] or '—'} ━━{note}")
        out.append(f"   sent {b['sent']:>3} · posted {b['posted']:>3} · "
                   f"OPENED {b['opened']:>3} ({rate:.0f}%) · returned {b['returned']} · "
                   f"engaged {b['engaged']} · converted {b['converted']}")
        for r in sorted(b["rows"], key=lambda x: (x["opened_at"] is None, x["opened_at"] or "")):
            if not r["opened_at"]:
                continue
            flags = []
            if r["returned"]:
                flags.append("returned")
            if r["converted"]:
                flags.append("CONVERTED")
            out.append(f"      ✓ {r['opened_at']}  {r['address']:<42} "
                       f"{r['pageviews'] or '?'} pvs / {r['visit_days'] or '?'}d"
                       f"{'  ['+', '.join(flags)+']' if flags else ''}")
    o = tot
    orate = (100.0 * o["opened"] / o["sent"]) if o["sent"] else 0.0
    out.append(f"\n═══ ALL BATCHES: sent {o['sent']} · posted {o['posted']} · "
               f"OPENED {o['opened']} ({orate:.0f}%) · returned {o['returned']} · "
               f"engaged {o['engaged']} · converted {o['converted']}")
    return "\n".join(out)


def render_fridge(s) -> str:
    """Fridge magnets ship 2 per envelope, but their QR is a GENERIC stock magnet
    pointing at /fridge with no slug/token — so a scan is NOT attributable to an
    address or a batch (confirmed w/ Will 2026-09-15). Measured over time only; the
    only address link is when a visitor self-types their address on the page."""
    a, w = s["all_time"], s["window"]
    lines = [
        "\n🧲 FRIDGE MAGNETS — aggregate only (generic QR → /fridge; NOT per-address/per-batch)",
        f"   all-time: {a['devices']} devices · {a['opened']} opened · {a['engaged']} engaged · "
        f"{a['address_entered']} typed an address → {a['crm_households']} CRM households",
        f"   last {s['days']}d: {w['new_devices']} new · {w['opened']} opened · "
        f"{w['engaged']} engaged · {w['address_entered']} typed an address",
    ]
    if a["devices"] == 0:
        lines.append("   (no scans recorded yet)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order")
    ap.add_argument("--lead-days", type=int, default=2,
                    help="delivery lead time added to batch_date when posted_date is unknown")
    ap.add_argument("--fridge-days", type=int, default=30,
                    help="rolling window for the aggregate fridge-magnet block")
    ap.add_argument("--no-fridge", action="store_true", help="skip the fridge aggregate section")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    with job_run("mailer_attribution_report", cadence_hours=24,
                 title="Mailer Attribution (ROI funnel)") as beat:
        batches = build(a.order, a.lead_days)
        sent = sum(b["sent"] for b in batches.values())
        opened = sum(b["opened"] for b in batches.values())
        # Rule 7b: no pieces recorded at all is a real failure of the measurement
        # (mail_log should never be empty once any batch has shipped), not "no work".
        if sent == 0:
            raise RuntimeError("mail_log has zero pieces — cannot measure mailer ROI "
                               "(expected at least the shipped batches)")
        fridge = None
        if not a.no_fridge:
            try:
                fridge = fridge_summarise(get_client()["system_monitor"], a.fridge_days)
            except Exception as e:  # aggregate extra — never fail the mailer funnel on it
                print(f"(fridge summary unavailable: {e})", file=sys.stderr)

        beat.metrics = {"sent": sent, "opened": opened,
                        "open_rate_pct": round(100.0 * opened / sent, 1),
                        "fridge_devices": (fridge or {}).get("all_time", {}).get("devices")}
        beat.detail = f"{opened}/{sent} mailer opens across {len(batches)} batches"

        if a.json:
            out = {o: {k: v for k, v in b.items()} for o, b in batches.items()}
            if fridge:
                out["_fridge_aggregate"] = fridge
            print(_json.dumps(out, default=str, indent=2))
        else:
            print(render(batches))
            if fridge:
                print(render_fridge(fridge))


if __name__ == "__main__":
    main()
