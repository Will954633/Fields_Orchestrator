#!/usr/bin/env python3
"""
ads_signal.py — 3rd domain (M2a): the ADS (paid) SENSOR — cost-per-identified-seller.

The SENSE half of the Ads sub-workflow. Read-only over `ad_daily_metrics` (spend) + `fb_leads`
(real conversions) + `ad_profiles` (campaign structure); writes `system_monitor.rl_ads_signal`.
Nothing else in the stack ties ad SPEND to real seller outcomes — that's the cost-as-reward gap
(00_SCOPING §5.1). This computes cost-per-lead per ad/campaign and flags scale/cull candidates,
separating the out-of-market TEST leads from real ones.

Coordinates with — does not replace — the FB funnel (copy discovery) + ad_lifecycle (cull/promote):
the Ads cycle proposes budget/scale moves (spend = Tier-3 → draft+telegram), it never spends itself.

Usage: python3 ads_signal.py [--dry-run] [--days 14]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_ads_signal"


def build(days=14, dry_run=False):
    sm = get_client()["system_monitor"]
    cut = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")

    # ad_id -> campaign via ad_profiles
    prof = {}
    for p in sm["ad_profiles"].find({}, {"ad_id": 1, "campaign_name": 1, "campaign_objective": 1,
                                         "effective_status": 1, "name": 1}):
        prof[p.get("ad_id")] = p

    # spend per ad (window)
    ads = defaultdict(lambda: {"spend": 0.0, "impressions": 0, "clicks": 0, "view_content": 0,
                               "landing_page_views": 0, "name": None})
    for d in sm["ad_daily_metrics"].find({"date": {"$gte": cut}}):
        a = ads[d.get("ad_id")]
        a["spend"] += float(d.get("spend_aud") or 0)
        a["impressions"] += int(d.get("impressions") or 0)
        a["clicks"] += int(d.get("clicks") or 0)
        a["view_content"] += int(d.get("view_content") or 0)
        a["landing_page_views"] += int(d.get("landing_page_views") or 0)
        a["name"] = d.get("ad_name") or a["name"]

    # real vs test leads per ad (window). TWO conversion surfaces, both matter:
    #  (1) fb_leads      = Facebook Instant-Form submissions (on-FB lead ads).
    #  (2) all_conversions = on-SITE "Analyse Your Home" address submits from PAID traffic,
    #      attributed to the ad via utm_content=ad_id (organic_journey_build 1b). Traffic-
    #      objective ads (AYH videos) convert HERE and were previously invisible to this sensor
    #      — counting only fb_leads is what produced the false "0 leads / ∞" for such ads.
    leads_real = defaultdict(int)
    leads_test = defaultdict(int)
    for l in sm["fb_leads"].find({}):
        try:
            ct = str(l.get("created_time") or "")[:10]
            if ct and ct < cut:
                continue
        except Exception:
            pass
        aid = l.get("ad_id")
        # test = out-of-market copy discovery (test_market) OR an internal self-test (is_test,
        # e.g. Will's own AYH submit). Both must be kept OUT of real GC seller CPL — the latter
        # was previously counted as a real lead (the report's phantom "1 lead, no intent").
        is_test = bool(l.get("test_market")) or str(l.get("is_test")).lower() in ("true", "1")
        if is_test:
            leads_test[aid] += 1
        else:
            leads_real[aid] += 1

    # (2) on-site paid conversions per ad_id (window)
    web_conv = defaultdict(int)
    for d in sm["all_conversions"].find({"is_paid": True, "ad_id": {"$nin": [None, ""]}},
                                        {"ad_id": 1, "submitted_at": 1}):
        try:
            sd = str(d.get("submitted_at") or "")[:10]
            if sd and sd < cut:
                continue
        except Exception:
            pass
        web_conv[d.get("ad_id")] += 1

    rows = []
    for aid, a in ads.items():
        if a["spend"] <= 0 and not (leads_real.get(aid) or leads_test.get(aid) or web_conv.get(aid)):
            continue
        p = prof.get(aid, {})
        real, test = leads_real.get(aid, 0), leads_test.get(aid, 0)
        web = web_conv.get(aid, 0)               # on-site AYH submits attributed to this ad
        conv = real + web                        # GC-served conversions (form + on-site), the true reward
        cpl_real = round(a["spend"] / real, 2) if real else None
        cpc_conv = round(a["spend"] / conv, 2) if conv else None   # cost per GC conversion (form+site)
        flags = []
        if a["spend"] >= 15 and conv == 0 and test == 0:
            flags.append("wasteful")            # spend, no conversions at all → cull candidate
        if cpc_conv is not None and cpc_conv <= 8:
            flags.append("scale")               # ≤$8/conversion → scale candidate
        elif cpc_conv is not None and cpc_conv <= 25:
            flags.append("watch")
        if web:
            flags.append("web_converter")       # converts on-site (traffic ad), not via Instant Form
        if test and not conv:
            flags.append("test_only")           # out-of-market copy test, not GC-served
        rows.append({
            "ad_id": aid, "ad_name": (a["name"] or p.get("name") or "")[:60],
            "campaign": p.get("campaign_name"), "objective": p.get("campaign_objective"),
            "status": p.get("effective_status"),
            "spend_aud": round(a["spend"], 2), "impressions": a["impressions"], "clicks": a["clicks"],
            "ctr": round(a["clicks"] / a["impressions"], 4) if a["impressions"] else 0,
            "real_leads": real, "web_leads": web, "conversions": conv, "test_leads": test,
            "cost_per_real_lead": cpl_real, "cost_per_conversion": cpc_conv, "flags": flags,
        })
    rows.sort(key=lambda r: (-(("scale" in r["flags"])), -(r["conversions"]), -r["spend_aud"]))

    # campaign rollup
    camp = defaultdict(lambda: {"spend": 0.0, "real_leads": 0, "web_leads": 0, "conversions": 0, "test_leads": 0})
    for r in rows:
        c = camp[r["campaign"] or "—"]
        c["spend"] += r["spend_aud"]; c["real_leads"] += r["real_leads"]
        c["web_leads"] += r["web_leads"]; c["conversions"] += r["conversions"]; c["test_leads"] += r["test_leads"]
    campaigns = [{"campaign": k, **v,
                  "cost_per_conversion": round(v["spend"] / v["conversions"], 2) if v["conversions"] else None}
                 for k, v in camp.items()]
    campaigns.sort(key=lambda c: -c["spend"])

    # M2c onboarding: surface what the FB-funnel + ad_lifecycle loops DID (their action log) into the
    # shared view, so the ads cycle + conductor see them and grade them against the one reward.
    recent_actions = []
    for d in sm["ad_decisions"].find({}).sort("_id", -1).limit(12):
        recent_actions.append({"date": d.get("date"), "type": d.get("type"),
                               "title": (d.get("title") or "")[:70], "tags": d.get("tags")})

    tot_spend = sum(r["spend_aud"] for r in rows)
    tot_real = sum(r["real_leads"] for r in rows)
    tot_web = sum(r["web_leads"] for r in rows)
    tot_conv = sum(r["conversions"] for r in rows)
    snapshot = {
        "kind": "ads_signal_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "window_days": days,
        "totals": {"spend_aud": round(tot_spend, 2),
                   "real_leads": tot_real,              # FB Instant-Form leads
                   "web_leads": tot_web,                # on-site AYH submits attributed to a paid ad
                   "conversions": tot_conv,             # form + on-site GC conversions (the true reward)
                   "test_leads": sum(r["test_leads"] for r in rows),
                   "blended_cost_per_conversion": round(tot_spend / tot_conv, 2) if tot_conv else None,
                   "active_ads": len(rows)},
        "scale_candidates": [r for r in rows if "scale" in r["flags"]][:12],
        "cull_candidates": [r for r in rows if "wasteful" in r["flags"]][:12],
        "campaigns": campaigns,
        "top_ads": rows[:20],
        "recent_ad_actions": recent_actions,   # FB-funnel + ad_lifecycle actions, onboarded (M2c)
        "note": ("SENSE half of the Ads sub-workflow. Ties ad spend → real seller leads = cost-per-"
                 "identified-seller (cost-as-reward). Spend moves are Tier-3 (draft+telegram Will); "
                 "the cycle never spends. Coordinates with FB funnel + ad_lifecycle."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    print(f"\n=== ADS SIGNAL ({s['window_days']}d) — ${t['spend_aud']} spend, {t['conversions']} conv"
          f" (form={t['real_leads']} + web={t['web_leads']}, {t['test_leads']} test), "
          f"blended cost/conv {t['blended_cost_per_conversion']} ===")
    print(f"\nSCALE candidates ({len(s['scale_candidates'])}):")
    for r in s["scale_candidates"][:6]:
        print(f"  {r['ad_name'][:34]:<34} ${r['spend_aud']:>6} {r['conversions']}c (f{r['real_leads']}/w{r['web_leads']}) cost/conv={r['cost_per_conversion']}")
    print(f"\nCULL candidates ({len(s['cull_candidates'])}):")
    for r in s["cull_candidates"][:6]:
        print(f"  {r['ad_name'][:34]:<34} ${r['spend_aud']:>6} 0c  [{r['status']}]")
    print("\nBy campaign:")
    for c in s["campaigns"][:6]:
        print(f"  {(c['campaign'] or '—')[:40]:<40} ${c['spend']:>7.0f}  conv={c['conversions']} (f{c['real_leads']}/w{c['web_leads']}) test={c['test_leads']} cost/conv={c['cost_per_conversion']}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_ads_signal", cadence_hours=24, title="General RL — Ads (paid) sensor") as beat:
            s = build(days=args.days, dry_run=False)
            _summary(s)
            beat.detail = (f"${s['totals']['spend_aud']} / {s['totals']['conversions']} conv "
                           f"(form {s['totals']['real_leads']} + web {s['totals']['web_leads']}); "
                           f"{len(s['scale_candidates'])} scale, {len(s['cull_candidates'])} cull")
    else:
        s = build(days=args.days, dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
