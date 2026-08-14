#!/usr/bin/env python3
"""
attribute_claims_report.py — who actually used the off-market correction panel.

    python3 scripts/attribute_claims_report.py            # last 30 days
    python3 scripts/attribute_claims_report.py --days 7
    python3 scripts/attribute_claims_report.py --pending  # awaiting verification

⚠ THIS COVERS SUBMISSIONS, NOT IMPRESSIONS. How often the modal FIRED is a
client-side event and lives only in PostHog (`offmarket_claim_shown`); nothing
reaches this collection until someone actually submits. So the conversion rate
needs both halves, and a zero here means either nobody submitted or the modal
never fired — the two are not distinguishable from this side. Check
`offmarket_claim_shown` in PostHog before concluding the feature is unused.
"""
import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
from shared.db import get_client  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--pending", action="store_true",
                    help="only claims still awaiting human verification")
    args = ap.parse_args()

    coll = get_client()["system_monitor"]["attribute_claims"]
    q = {"created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=args.days)}}
    if args.pending:
        q["verified"] = False
        q["status"] = "computed"
    claims = list(coll.find(q).sort("created_at", -1))

    if not claims:
        print(f"No corrections submitted in the last {args.days} days.")
        print("⚠ That is not proof nobody saw the panel — impressions are the")
        print("  `offmarket_claim_shown` event in PostHog, not this collection.")
        return 0

    status = Counter(c.get("status", "?") for c in claims)
    assumed = sum(1 for c in claims if c.get("assumed"))
    valued = [c for c in claims
              if (c.get("provisional") or {}).get("method") == "engine"]

    print(f"\n{len(claims)} correction(s) in the last {args.days} days")
    print(f"  status      : {dict(status)}")
    print(f"  produced a figure : {len(valued)}")
    print(f"  used typical figures : {assumed}  (their own: {len(claims) - assumed})")
    print(f"  distinct addresses   : {len({c['slug'] for c in claims})}")
    print(f"  distinct sessions    : {len({c.get('session_id') for c in claims if c.get('session_id')})}")

    print(f"\n{'when':17} {'address':42} {'gave us':34} {'result':26} session")
    print("-" * 150)
    for c in claims:
        when = c["created_at"].strftime("%d %b %H:%M")
        attrs = ", ".join(f"{k.replace('_sqm','').replace('_',' ')}={v}"
                          for k, v in (c.get("attributes") or {}).items())
        p = c.get("provisional") or {}
        if p.get("method") == "engine":
            res = f"${p['low']:,.0f}-${p['high']:,.0f}"
        elif c.get("status") == "error":
            res = f"ERROR {str(c.get('error'))[:18]}"
        else:
            res = p.get("decline_reason") or c.get("status", "?")
        tag = " [typical]" if c.get("assumed") else ""
        print(f"{when:17} {c['slug'][:42]:42} {attrs[:34]:34} {res[:26]:26} "
              f"{(c.get('session_id') or '-')[:18]}{tag}")

    if not args.pending:
        waiting = coll.count_documents({"verified": False, "status": "computed"})
        if waiting:
            print(f"\n⚠ {waiting} claim(s) awaiting verification. Nothing computed from a")
            print("  reader's figures is published until someone sets verified: true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
