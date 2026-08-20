#!/usr/bin/env python3
"""
campaign_lead_report.py — on-demand report over system_monitor.campaign_leads.

Buyer-enquiry capture for the Fields buyer-acquisition conjunction campaigns
(e.g. 93 Burleigh Street). Each lead is written by
`netlify/functions/campaign-lead.mjs` and carries an `interest` answer chosen
from a fixed dropdown. The WHOLE POINT of capturing `interest` is to learn
which buyer thesis (land / renovate / rebuild / shed / downstairs / just
curious) actually pulls enquiries across a campaign — so the interest
breakdown is the headline output of this tool.

This is an ON-DEMAND report, not a scheduled job. Per CLAUDE.md Rule 7 it needs
no heartbeat (no cadence, nothing runs it on a schedule). It is READ-ONLY on
the database.

Rule 8 note: field names below were confirmed against the actual writer
(campaign-lead.mjs) and a live db_fields check, not guessed. The stored lead
shape is: name, phone, email, interest, message, property_slug, source,
posthog_distinct_id, consent, user_agent, created_at (ISO str), created_at_date
(Date).

Rule 7b applied to a read (Rule 8): a zero result is reported as an OUTCOME, not
a bare "nothing found". Before reporting "0 leads" the tool verifies (a) the
collection exists and (b) the slug is a real registered conjunction property —
so "campaign not yet generating enquiries" is distinguished from "query broken /
wrong slug".

Usage:
    python3 scripts/campaign_lead_report.py --slug 93-burleigh-street-burleigh-waters
    python3 scripts/campaign_lead_report.py --all
    python3 scripts/campaign_lead_report.py --slug ... --no-pii     # redact phone/email
    python3 scripts/campaign_lead_report.py --slug ... --json
    python3 scripts/campaign_lead_report.py --slug ... --recent 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

# Make `shared` / `scripts` importable whether run from repo root or scripts/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import get_client  # noqa: E402

# conjunction_register is used to validate the slug and (if present) read the
# campaign's intended primary thesis. Import defensively so the report still
# works if that module is ever moved.
try:
    from scripts import conjunction_register as reg  # type: ignore
except Exception:  # pragma: no cover
    try:
        import conjunction_register as reg  # type: ignore
    except Exception:
        reg = None

COLLECTION = "campaign_leads"

# The fixed interest dropdown on the landing form. Kept in canonical order so a
# category with zero leads still shows up as 0 (absence is signal too). These
# are the exact option strings the form submits.
INTEREST_OPTIONS = [
    "The land and location",
    "Renovating it",
    "Rebuilding / the future potential",
    "The shed / workshop / parking",
    "Space for extended family (the downstairs)",
    "Just want to know more",
]

# Fields on a conjunction-register doc that, if present, name the campaign's
# INTENDED primary thesis (free-text; not in the register's KNOWN_FIELDS today,
# so we look for any of these and use the first found).
_THESIS_FIELDS = ("primary_thesis", "intended_thesis", "thesis", "primary_interest")


def _coll():
    return get_client()["system_monitor"][COLLECTION]


def _collection_exists() -> bool:
    return COLLECTION in get_client()["system_monitor"].list_collection_names()


def _intended_thesis(slug: str):
    """Return the campaign's intended primary thesis from the conjunction
    register, or None if not recorded / register unavailable."""
    if reg is None or not slug:
        return None
    try:
        d = reg.get(slug)
    except Exception:
        return None
    if not d:
        return None
    for f in _THESIS_FIELDS:
        v = d.get(f)
        if v:
            return str(v)
    return None


def _is_registered_conjunction(slug: str) -> bool:
    if reg is None or not slug:
        return False
    try:
        return bool(reg.get(slug))
    except Exception:
        return False


def _redact(value: str, keep: int = 0) -> str:
    if not value:
        return ""
    return "[redacted]"


def _day_of(lead: dict) -> str:
    """AEST-agnostic day bucket. created_at is an ISO-8601 string; fall back to
    created_at_date (a datetime) if the string is missing/unparseable."""
    ca = lead.get("created_at")
    if isinstance(ca, str) and ca:
        try:
            return datetime.fromisoformat(ca.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    cad = lead.get("created_at_date")
    if isinstance(cad, datetime):
        return cad.date().isoformat()
    return "(undated)"


def _analyse(leads: list[dict], recent_n: int, no_pii: bool) -> dict:
    total = len(leads)

    # Breakdown by interest — the headline. Seed with the canonical options so
    # zero-count categories are visible, then fold in any unexpected values.
    interest_counts: Counter = Counter({opt: 0 for opt in INTEREST_OPTIONS})
    for l in leads:
        key = (l.get("interest") or "").strip() or "(not stated)"
        interest_counts[key] += 1
    # Order: canonical options first (by count desc), then extras (by count desc).
    interest_ranked = sorted(
        interest_counts.items(),
        key=lambda kv: (-kv[1], INTEREST_OPTIONS.index(kv[0]) if kv[0] in INTEREST_OPTIONS else 999, kv[0]),
    )

    # Leads over time (by day).
    by_day: dict = defaultdict(int)
    for l in leads:
        by_day[_day_of(l)] += 1
    by_day_sorted = sorted(by_day.items())

    # Contactability + consent.
    with_phone = sum(1 for l in leads if (l.get("phone") or "").strip())
    with_email = sum(1 for l in leads if (l.get("email") or "").strip())
    with_both = sum(1 for l in leads
                    if (l.get("phone") or "").strip() and (l.get("email") or "").strip())
    consented = sum(1 for l in leads if l.get("consent") is True)

    # Most recent N enquiries (sorted by created_at desc).
    def _sort_key(l):
        return l.get("created_at") or ""
    recent = sorted(leads, key=_sort_key, reverse=True)[:recent_n]
    recent_out = []
    for l in recent:
        recent_out.append({
            "created_at": l.get("created_at"),
            "name": l.get("name") or "(no name)",
            "interest": (l.get("interest") or "").strip() or "(not stated)",
            "phone": _redact(l.get("phone")) if no_pii else (l.get("phone") or ""),
            "email": _redact(l.get("email")) if no_pii else (l.get("email") or ""),
            "message": l.get("message") or "",
            "consent": bool(l.get("consent") is True),
            "source": l.get("source") or "",
        })

    # Signal: which interest leads (highest non-empty, canonical or extra).
    leading = None
    leading_count = 0
    for k, v in interest_ranked:
        if v > 0:
            leading, leading_count = k, v
            break

    return {
        "total": total,
        "interest_ranked": interest_ranked,
        "by_day": by_day_sorted,
        "with_phone": with_phone,
        "with_email": with_email,
        "with_both": with_both,
        "consented": consented,
        "consent_rate": (consented / total) if total else 0.0,
        "recent": recent_out,
        "leading_interest": leading,
        "leading_count": leading_count,
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _bar(count: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = int(round((count / total) * width))
    return "█" * filled + "·" * (width - filled)


def _render_campaign(slug: str, leads: list[dict], recent_n: int, no_pii: bool) -> str:
    a = _analyse(leads, recent_n, no_pii)
    total = a["total"]
    intended = _intended_thesis(slug)
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"Campaign: {slug}")
    out.append("=" * 64)
    out.append(f"Total leads: {total}")
    if no_pii:
        out.append("(--no-pii: phone/email redacted for sharing)")
    out.append("")

    # Interest breakdown — the headline.
    out.append("Interest breakdown (which thesis is pulling):")
    for k, v in a["interest_ranked"]:
        pct = (v / total * 100) if total else 0.0
        out.append(f"  {v:>3}  {pct:5.1f}%  {_bar(v, total)}  {k}")
    out.append("")

    # Leads over time.
    out.append("Leads by day:")
    for day, n in a["by_day"]:
        out.append(f"  {day}  {n}")
    out.append("")

    # Contactability + consent.
    out.append("Contactability:")
    out.append(f"  Left a phone : {a['with_phone']}")
    out.append(f"  Left an email: {a['with_email']}")
    out.append(f"  Left both    : {a['with_both']}")
    out.append(f"  Consented    : {a['consented']} ({a['consent_rate']*100:.0f}%)")
    out.append("")

    # Signal summary.
    out.append("Signal:")
    if total == 0:
        out.append("  No leads yet — nothing to read.")
    else:
        out.append(f"  Leading thesis: \"{a['leading_interest']}\" "
                   f"({a['leading_count']}/{total}, {a['leading_count']/total*100:.0f}%)")
        if intended:
            match = (a["leading_interest"] or "").strip().lower() == intended.strip().lower()
            verdict = "MATCHES" if match else "does NOT match"
            out.append(f"  Intended primary thesis (register): \"{intended}\"")
            out.append(f"  → Enquiries {verdict} the intended thesis.")
        else:
            out.append("  Intended primary thesis: not recorded in conjunction register "
                       "— reporting observed ranking only.")
    out.append("")

    # Recent enquiries.
    out.append(f"Most recent {min(recent_n, total)} enquir{'y' if min(recent_n, total)==1 else 'ies'}:")
    if not a["recent"]:
        out.append("  (none)")
    for r in a["recent"]:
        out.append(f"  • {r['created_at']}  {r['name']}")
        out.append(f"      interest: {r['interest']}")
        contact = []
        if r["phone"]:
            contact.append(f"phone {r['phone']}")
        if r["email"]:
            contact.append(f"email {r['email']}")
        if contact:
            out.append(f"      contact:  {', '.join(contact)}  (consent: {'yes' if r['consent'] else 'no'})")
        if r["message"]:
            out.append(f"      message:  {r['message']}")
    out.append("")
    return "\n".join(out)


def _campaign_json(slug: str, leads: list[dict], recent_n: int, no_pii: bool) -> dict:
    a = _analyse(leads, recent_n, no_pii)
    return {
        "slug": slug,
        "total": a["total"],
        "interest_breakdown": [{"interest": k, "count": v} for k, v in a["interest_ranked"]],
        "by_day": [{"day": d, "count": n} for d, n in a["by_day"]],
        "contactability": {
            "with_phone": a["with_phone"],
            "with_email": a["with_email"],
            "with_both": a["with_both"],
            "consented": a["consented"],
            "consent_rate": round(a["consent_rate"], 4),
        },
        "signal": {
            "leading_interest": a["leading_interest"],
            "leading_count": a["leading_count"],
            "intended_thesis": _intended_thesis(slug),
        },
        "recent": a["recent"],
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Report over system_monitor.campaign_leads")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="report on one campaign (property_slug)")
    g.add_argument("--all", action="store_true", help="report on every slug present in campaign_leads")
    ap.add_argument("--recent", type=int, default=5, help="how many recent enquiries to show (default 5)")
    ap.add_argument("--no-pii", action="store_true", help="redact phone/email (safe to share)")
    ap.add_argument("--json", dest="as_json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # Rule 7b/Rule 8: verify the collection exists before inferring absence.
    if not _collection_exists():
        msg = ("campaign_leads collection does not exist in system_monitor — "
               "the capture function may never have run. This is NOT '0 leads'; "
               "it is a missing collection. Check netlify/functions/campaign-lead.mjs.")
        if args.as_json:
            print(json.dumps({"error": "collection_missing", "message": msg}, indent=2))
        else:
            print(msg)
        return 2

    coll = _coll()

    # --- single slug ---
    if args.slug:
        slug = args.slug.strip()
        leads = list(coll.find({"property_slug": slug}))
        if not leads:
            # Distinguish "no leads yet" from "query broken / wrong slug".
            registered = _is_registered_conjunction(slug)
            if not registered:
                msg = (f"0 leads for {slug!r} — AND this slug is not in the conjunction "
                       f"register. Check the slug is spelled exactly as the landing form "
                       f"submits it (e.g. 93-burleigh-street-burleigh-waters). "
                       f"This is likely a wrong slug, not an empty campaign.")
                code = 2
            else:
                msg = (f"0 leads for {slug} — campaign not yet generating enquiries. "
                       f"(Slug confirmed as a registered conjunction property; the "
                       f"collection exists and is reachable — the campaign simply has "
                       f"no enquiries yet.)")
                code = 0
            if args.as_json:
                print(json.dumps({
                    "slug": slug, "total": 0,
                    "registered_conjunction": registered,
                    "message": msg,
                }, indent=2))
            else:
                print(msg)
            return code

        if args.as_json:
            print(json.dumps(_campaign_json(slug, leads, args.recent, args.no_pii),
                             indent=2, default=str))
        else:
            print(_render_campaign(slug, leads, args.recent, args.no_pii))
        return 0

    # --- all slugs ---
    all_leads = list(coll.find({}))
    if not all_leads:
        msg = ("0 leads across ALL campaigns — no enquiries captured yet. "
               "(campaign_leads collection exists and is reachable; it is empty. "
               "This is 'no leads yet', not a broken query.)")
        if args.as_json:
            print(json.dumps({"total": 0, "campaigns": [], "message": msg}, indent=2))
        else:
            print(msg)
        return 0

    # Group by slug.
    by_slug: dict = defaultdict(list)
    for l in all_leads:
        by_slug[l.get("property_slug") or "(no slug)"].append(l)

    if args.as_json:
        payload = {
            "total": len(all_leads),
            "campaigns": [
                _campaign_json(slug, leads, args.recent, args.no_pii)
                for slug, leads in sorted(by_slug.items(), key=lambda kv: -len(kv[1]))
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"campaign_leads: {len(all_leads)} total across {len(by_slug)} campaign(s)\n")
        for slug, leads in sorted(by_slug.items(), key=lambda kv: -len(kv[1])):
            print(_render_campaign(slug, leads, args.recent, args.no_pii))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
