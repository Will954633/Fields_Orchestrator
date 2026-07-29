#!/usr/bin/env python3
"""
onsite_signal.py — milestone M3: the ONSITE per-user SENSOR — surface hot individual visitors.

The SENSE half of the Onsite sub-workflow — the same pattern as ads_signal.py / seo_signal.py,
but per-PERSON instead of per-page/per-ad. Read-only over `lead_worklist` (known individuals +
their seller conclusion), `organic_journeys` (behavioural intent, rolled to distinct_id) and the
shared `rl_reward_ledger` (milestone lifts as scoring guide); writes `system_monitor.rl_onsite_signal`
(+ history). The STEER half is the onsite cycle that reads this + the reward ledger and Telegrams Will
so he can call/contact a hot visitor WHILE THEY ARE WARM (and queue the rest).

Two angles into "who is hot right now":
  1. KNOWN leads — lead_worklist rows whose `seller_intent.label` is a real intent (frustrated vendor
     on_market_expiring/stale, pre-market withdrawn, engaged owner researching, browsing while unlisted).
     Scored by label weight + behavioural hotness + contact completeness; contact (email/phone/address)
     is carried on the row so the cycle can act. Conclusion text is the human reason.
  2. ANONYMOUS-but-high-intent journeys — distinct_ids that hit high-value milestones (searched an
     in-coverage / home-owner address ~26x lift, submitted an address ~31x, viewed >=2 properties,
     returned across >1 session, off-market qualify). No PII — behaviour + distinct_id only.

Nothing here contacts anyone — surfacing is Tier-3 (the cycle drafts + telegrams Will).

Usage: python3 onsite_signal.py [--dry-run]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_onsite_signal"

# --- KNOWN-lead seller_intent labels that indicate REAL intent (exclude no_cross_signal / None) ---
# weight = how ready-to-sell-through-us the label reads; reason/action drive the cycle's outreach.
LABEL_PLAYBOOK = {
    "pre_market_withdrawn":      (30, "pre-market seller (withdrawn) — send appraisal + Will call"),
    "on_market_expiring":        (28, "frustrated vendor (listing expiring) — Will call"),
    "on_market_stale":           (26, "frustrated vendor (stale listing) — Will call"),
    "home_identified_not_listed":(22, "pre-market seller (home identified, unlisted) — send appraisal"),
    "engaged_owner_researching": (18, "engaged owner researching own home — surface valuation"),
    "browsing_while_unlisted":   (14, "owner browsing while unlisted — surface valuation"),
    "on_market_fresh":           (10, "on market fresh (has an agent) — monitor, soft touch"),
    "on_market_active":          (10, "on market (agency stage unknown) — verify then soft touch"),
    "viewing_listings_home_unknown": (8, "viewing listings, home unknown — nurture"),
}


def _mask(v, keep=3):
    """Mask PII for the dry-run summary — keep is fine in the stored doc, not on screen."""
    if not v:
        return "—"
    v = str(v)
    return (v[:keep] + "***") if len(v) > keep else "***"


def build(dry_run=False):
    sm = get_client()["system_monitor"]

    # reward-ledger milestone lifts — the scoring guide for anonymous behaviour.
    ledger = sm["rl_reward_ledger"].find_one({"_id": "latest"}) or {}
    lift = {m.get("milestone"): float(m.get("lift_vs_base") or 1.0)
            for m in (ledger.get("milestones") or [])}

    def L(name, default):
        return lift.get(name, default)

    # ------------------------------------------------------------------ 1. KNOWN leads
    known = []
    for d in sm["lead_worklist"].find({}):
        if d.get("is_test") or d.get("priority") == "test":
            continue
        si = d.get("seller_intent") or {}
        label = si.get("label")
        if label not in LABEL_PLAYBOOK:
            continue
        weight, action = LABEL_PLAYBOOK[label]
        hotness = float(si.get("hotness") or 0)
        email, phone = d.get("email"), d.get("phone")
        contact_bonus = (4 if email else 0) + (6 if phone else 0)
        score = round(weight + min(hotness, 60) * 0.3 + contact_bonus, 1)
        known.append({
            "type": "known",
            "lead_key": d.get("lead_key"),
            "name": (d.get("name") or "").strip() or None,
            "address": d.get("address"),
            "email": email, "phone": phone,
            "has_email": bool(email), "has_phone": bool(phone),
            "intent_label": label,
            "intent_reason": si.get("conclusion") or d.get("reason"),
            "recommended_action": action,
            "hotness": round(hotness, 1),
            "priority": d.get("priority"),
            "updated_at": str(d.get("updated_at") or ""),
            "intent_score": score,
        })
    known.sort(key=lambda r: -r["intent_score"])

    # ------------------------------------------------------------------ 2. ANON journeys → distinct_id
    by_user = defaultdict(list)
    for j in sm["organic_journeys"].find({}):
        did = j.get("distinct_id") or j.get("session_id")
        if did:
            by_user[did].append(j)

    IN_COVERAGE = {"current_listing", "recent_listing", "withdrawn_listing", "likely_home_owner"}
    HOME_OWNER = {"likely_home_owner", "home_owner"}

    anon = []
    for did, js in by_user.items():
        sessions = len(js)
        cats = {j.get("searched_address_category") for j in js}
        offmarket_events = set(e for j in js for e in (j.get("offmarket_events") or []))
        n_props = sum(len(j.get("properties_viewed") or []) for j in js)
        submitted = [a for j in js for a in (j.get("addresses_submitted") or [])]
        searches = sum(int(j.get("n_searches") or 0) for j in js)
        converted = any(j.get("converted") for j in js)
        last = max((str(j.get("t_last") or j.get("t_first") or "") for j in js), default="")

        milestones, reasons = [], []
        score = 0.0
        if submitted:
            milestones.append("submitted_address"); score += L("submitted_address", 31.0)
            reasons.append(f"submitted address ({len(submitted)}x)")
        if cats & HOME_OWNER:
            milestones.append("searched_home_owner_address"); score += L("searched_address", 26.0)
            reasons.append("searched a likely-home-owner address")
        if n_props >= 2:
            milestones.append("viewed_multiple_properties"); score += L("viewed_multiple_properties", 7.4)
            reasons.append(f"viewed {n_props} properties")
        if sessions > 1:
            milestones.append("return_visit"); score += L("return_visit", 6.4)
            reasons.append(f"returned across {sessions} sessions")
        if cats & IN_COVERAGE:
            milestones.append("search_in_coverage"); score += L("search_in_coverage", 3.0)
            reasons.append("searched an in-coverage address")
        if "offmarket_qualify" in offmarket_events:
            milestones.append("offmarket_qualified"); score += L("offmarket_qualified", 0.83)
            reasons.append("off-market qualify")
        if "offmarket_menu_sell" in offmarket_events:
            milestones.append("offmarket_intent_sell"); score += L("offmarket_intent_sell", 0.71)
            reasons.append("off-market intent-to-sell")

        # HOT = hit at least one high-value pre-reward milestone (not just a stray pageview)
        hot = bool({"submitted_address", "searched_home_owner_address",
                    "viewed_multiple_properties", "return_visit", "offmarket_qualified"} & set(milestones))
        if not hot:
            continue

        if "submitted_address" in milestones or cats & HOME_OWNER:
            action = "returning address-searcher — surface valuation / retarget"
        elif "viewed_multiple_properties" in milestones or sessions > 1:
            action = "engaged buyer/owner — retarget with matched listings"
        else:
            action = "warm anonymous — nurture"

        anon.append({
            "type": "anon",
            "distinct_id": did,
            "sessions": sessions,
            "properties_viewed": n_props,
            "n_searches": searches,
            "addresses_submitted": len(submitted),
            "converted": converted,
            "milestones": milestones,
            "intent_reason": "; ".join(reasons),
            "recommended_action": action,
            "last_seen": last,
            "intent_score": round(score, 1),
        })
    anon.sort(key=lambda r: -r["intent_score"])

    # ------------------------------------------------------------------ merge + rank
    hot_individuals = sorted(known + anon, key=lambda r: -r["intent_score"])[:25]

    snapshot = {
        "kind": "onsite_signal_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "totals": {
            "known_hot": len(known),
            "anon_hot": len(anon),
            "known_with_phone": sum(1 for r in known if r["has_phone"]),
            "known_with_email": sum(1 for r in known if r["has_email"]),
            "distinct_users_seen": len(by_user),
            "lead_worklist_rows": sm["lead_worklist"].estimated_document_count(),
        },
        "hot_individuals": hot_individuals,
        "note": ("M3 onsite per-user SENSOR. Surfaces HIGH-INTENT individuals — known leads by "
                 "seller_intent + anonymous distinct_ids by behavioural milestone (reward-ledger "
                 "lifts as guide) — so the onsite cycle can Telegram Will to call/contact them "
                 "while warm and queue the rest. Read-only; surfacing is Tier-3 (draft + telegram)."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    print(f"\n=== ONSITE SIGNAL (per-user) — {t['known_hot']} known hot "
          f"({t['known_with_phone']} w/phone, {t['known_with_email']} w/email), "
          f"{t['anon_hot']} anon hot / {t['distinct_users_seen']} distinct users ===")
    known = [r for r in s["hot_individuals"] if r["type"] == "known"]
    anon = [r for r in s["hot_individuals"] if r["type"] == "anon"]
    print(f"\nKNOWN leads ({len(known)} in top list):")
    for r in known[:8]:
        who = _mask(r.get("email") or r.get("name") or r.get("lead_key"))
        ph = _mask(r.get("phone"), keep=4)
        print(f"  [{r['intent_score']:>5}] {r['intent_label'][:24]:<24} {who:<9} ph={ph:<8} "
              f"{(r.get('address') or '—')[:34]:<34} → {r['recommended_action'][:38]}")
    print(f"\nANON high-intent ({len(anon)} in top list):")
    for r in anon[:8]:
        print(f"  [{r['intent_score']:>5}] {r['distinct_id'][:12]:<12} s={r['sessions']} "
              f"props={r['properties_viewed']} sub={r['addresses_submitted']}  "
              f"{r['intent_reason'][:44]:<44} → {r['recommended_action'][:30]}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_onsite_signal", cadence_hours=24, title="General RL — Onsite per-user sensor") as beat:
            s = build(dry_run=False)
            _summary(s)
            beat.detail = (f"{s['totals']['known_hot']} known hot, {s['totals']['anon_hot']} anon hot; "
                           f"{s['totals']['known_with_phone']} w/phone")
    else:
        s = build(dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
