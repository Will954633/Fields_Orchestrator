#!/usr/bin/env python3
"""
lead_attribution_build.py — Brain 2: turn native Facebook lead-form submissions
(system_monitor.fb_leads) into an attributed conversion surface.

Why this exists: the rest of Brain 2 (ad_downstream, organic_journeys, ad_query)
is a *website-session* attribution engine built on PostHog. A Meta Instant Form
converts ON Facebook — the person never lands on the site, so PostHog never sees
them and they are invisible to the rollup. This builder reads fb_leads directly,
joins each lead to its ad / campaign / spend, scores intent, and writes:

  system_monitor.lead_attribution   — one summary doc (_id="_summary") +
                                       one enriched doc per lead

so lead-form conversions sit alongside on-site address-entries in ad_query.

Attribution: fb_leads now carries ad_id/campaign_id/platform/is_organic (captured
by fb-lead-puller.py). Leads with is_organic=True (organic form post, no ad) are
bucketed under ad_id=None. Spend/CTR are joined from ad_profiles.lifetime when the
ad exists there (brand-new ads may not be profiled yet — handled gracefully).

Usage:
    python3 scripts/brain2/lead_attribution_build.py
    python3 scripts/brain2/lead_attribution_build.py --show   # print summary too
"""
import os, sys, argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402

# Seller-side AYH forms are a different funnel (address -> mini-site -> report),
# fulfilled elsewhere; tag them so buyer-brief lead counts stay clean.
AYH_FORM_IDS = {"1735418400974915"}
# Internal test addresses/emails to exclude from real-lead counts.
INTERNAL_EMAILS = {"will@fieldsestate.com.au", "rossmax06@gmail.com"}

# High-intent heuristics per form family (buyer brief). Kept explicit and cheap;
# these are the structured fields the forms actually collect.
HOT_TIMEFRAMES = {"now", "0_3_months", "3_6_months"}


def intent_score(fields):
    """0-3 cheap intent score from the buyer-brief structured fields."""
    s = 0
    tf = str(fields.get("timeframe", "")).lower()
    if tf in HOT_TIMEFRAMES:
        s += 2
    elif tf and "watching" not in tf:
        s += 1
    if str(fields.get("owns_gc_home", "")).lower() == "yes":
        s += 1  # owns a GC home -> also a potential seller
    return s


def build():
    db = get_client()["system_monitor"]
    leads = list(db.fb_leads.find({}))
    prof = {d["_id"]: d for d in db.ad_profiles.find({}, {"lifetime": 1, "name": 1})}

    enriched, per_ad, per_campaign, per_form = [], defaultdict(list), defaultdict(list), defaultdict(list)
    now = datetime.now(timezone.utc).isoformat()

    for L in leads:
        fields = L.get("fields", {})
        email = str(fields.get("email", "")).lower()
        is_ayh = L.get("form_id") in AYH_FORM_IDS
        internal = email in INTERNAL_EMAILS
        ad_id = L.get("ad_id")  # None for organic form posts
        lt = (prof.get(ad_id) or {}).get("lifetime", {}) if ad_id else {}
        doc = {
            "_id": L["_id"],
            "created_time": L.get("created_time"),
            "form_id": L.get("form_id"), "form_name": L.get("form_name"),
            "funnel": "seller_ayh" if is_ayh else "buyer_brief",
            "internal_test": internal,
            "ad_id": ad_id, "ad_name": L.get("ad_name"),
            "campaign_id": L.get("campaign_id"), "campaign_name": L.get("campaign_name"),
            "platform": L.get("platform"), "is_organic": bool(L.get("is_organic")),
            "intent_score": intent_score(fields),
            "fields": fields,
            "ad_spend_lifetime": lt.get("spend_aud"),
            "ad_impressions_lifetime": lt.get("impressions"),
            "ad_reach_lifetime": lt.get("reach"),
            "computed_at": now,
        }
        enriched.append(doc)
        if internal or is_ayh:
            continue  # keep aggregates to real buyer leads
        per_ad[ad_id].append(doc)
        per_campaign[L.get("campaign_name")].append(doc)
        per_form[L.get("form_name")].append(doc)

    real = [d for d in enriched if not d["internal_test"] and d["funnel"] == "buyer_brief"]

    def rollup(bucket):
        out = []
        for key, ds in bucket.items():
            spend = next((d["ad_spend_lifetime"] for d in ds if d["ad_spend_lifetime"] is not None), None)
            out.append({
                "key": key, "leads": len(ds),
                "hot_leads": sum(1 for d in ds if d["intent_score"] >= 2),
                "owns_gc_home": sum(1 for d in ds if str(d["fields"].get("owns_gc_home", "")).lower() == "yes"),
                "ad_spend_lifetime": spend,
                "cost_per_lead": round(spend / len(ds), 2) if spend else None,
            })
        return sorted(out, key=lambda r: -r["leads"])

    summary = {
        "_id": "_summary",
        "computed_at": now,
        "total_leads": len(leads),
        "real_buyer_leads": len(real),
        "seller_ayh_leads": sum(1 for d in enriched if d["funnel"] == "seller_ayh" and not d["internal_test"]),
        "internal_test_leads": sum(1 for d in enriched if d["internal_test"]),
        "hot_leads": sum(1 for d in real if d["intent_score"] >= 2),
        "owns_gc_home_leads": sum(1 for d in real if str(d["fields"].get("owns_gc_home", "")).lower() == "yes"),
        "by_ad": rollup(per_ad),
        "by_campaign": rollup(per_campaign),
        "by_form": rollup(per_form),
        "area_dist": dict(Counter(str(d["fields"].get("area", "?")).lower() for d in real)),
        "timeframe_dist": dict(Counter(str(d["fields"].get("timeframe", "?")).lower() for d in real)),
    }

    coll = db.lead_attribution
    coll.replace_one({"_id": "_summary"}, summary, upsert=True)
    for d in enriched:
        coll.replace_one({"_id": d["_id"]}, d, upsert=True)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    s = build()
    print(f"[{s['computed_at']}] lead_attribution built — "
          f"{s['real_buyer_leads']} real buyer leads ({s['hot_leads']} hot, "
          f"{s['owns_gc_home_leads']} own a GC home), "
          f"{s['seller_ayh_leads']} seller/AYH, {s['internal_test_leads']} internal")
    if args.show:
        import json
        print(json.dumps({k: v for k, v in s.items() if k != "_id"}, indent=2, default=str))


if __name__ == "__main__":
    main()
