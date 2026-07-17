#!/usr/bin/env python3
"""
ad_query.py — Brain 2 query layer: join semantic annotation × downstream × spend
and answer pattern questions across the whole account.

Sources (all in system_monitor):
  ad_profiles          — structure + lifetime performance (creative_structured, lifetime;
                         now surfaces reach + post-engagement, not just impr/CTR/spend)
  ad_semantic_annotations — Opus high-effort content annotation
  ad_downstream        — PostHog attribution (confidence-labelled) — ON-SITE conversions
  lead_attribution     — native Meta lead-form submissions — OFF-SITE conversions
                         (built by lead_attribution_build.py; convert on Facebook, never
                         touch the site, so they are invisible to ad_downstream)

Commands:
  python3 scripts/brain2/ad_query.py rollup
      Account-wide pattern rollup: format dist, emotional-lever dist, hook dist,
      and performance aggregated by lever / by format / by hook.
  python3 scripts/brain2/ad_query.py compare --by primary_emotional_lever
  python3 scripts/brain2/ad_query.py compare --by format
  python3 scripts/brain2/ad_query.py compare --by hook_type
      Performance table grouped by any annotation dimension.
  python3 scripts/brain2/ad_query.py converters
      Every ad that produced an address entry, with its full semantic + journey
      profile, and how converters differ from the rest (exact-attributed only).
  python3 scripts/brain2/ad_query.py leads
      Native Meta lead-form conversions by ad / campaign, with intent + cost-per-lead.
  python3 scripts/brain2/ad_query.py ad --id <AD_ID>
      Full joined dossier for one ad.

Numbers are lifetime FB metrics; conversions are from ad_downstream (exact conf).
"""
import sys, json, argparse
from collections import defaultdict
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402


def load():
    db = get_client()["system_monitor"]
    prof = {d["_id"]: d for d in db.ad_profiles.find({"creative_structured": {"$exists": True}})}
    ann = {d["ad_id"]: d for d in db.ad_semantic_annotations.find({})}
    down = {d["_id"]: d for d in db.ad_downstream.find({})}
    # native Facebook lead-form conversions (built by lead_attribution_build.py) —
    # these convert ON Meta, so they never appear in the PostHog-based downstream.
    leads_by_ad = defaultdict(int)
    for d in db.lead_attribution.find({"_id": {"$ne": "_summary"}, "internal_test": False}):
        if d.get("ad_id"):
            leads_by_ad[d["ad_id"]] += 1
    rows = []
    for aid, p in prof.items():
        a = ann.get(aid, {}).get("annotation", {})
        d = down.get(aid, {})
        lt = p.get("lifetime", {}) or {}
        rows.append({
            "ad_id": aid, "name": p.get("name", ""),
            "format": p.get("creative_structured", {}).get("format", ""),
            "objective": p.get("campaign_objective", ""),
            "lever": a.get("primary_emotional_lever"),
            "hook": a.get("hook_type"),
            "theme": a.get("message_theme"),
            "persona": a.get("target_persona"),
            "tone": a.get("tone", []),
            "cta_hardness": (a.get("cta_semantic") or {}).get("hardness"),
            "cites_numbers": (a.get("specificity") or {}).get("cites_numbers"),
            "annotated": bool(a),
            "impressions": lt.get("impressions") or 0,
            "reach": lt.get("reach") or 0,
            "link_clicks": lt.get("link_clicks") or 0,
            "lpv": lt.get("landing_page_views") or 0,
            "spend": lt.get("spend_aud") or 0,
            "ctr": lt.get("ctr") or 0,
            "cpc": lt.get("cpc_aud") or 0,
            # engagement (already collected, previously not surfaced)
            "post_engagement": lt.get("post_engagement") or 0,
            "post_reaction": lt.get("post_reaction") or 0,
            "post_save": lt.get("post_save") or 0,
            "video_views": lt.get("video_views") or 0,
            "attr_conf": d.get("attribution_confidence"),
            "sessions": d.get("sessions") or 0,
            "converters": d.get("converters") or 0,
            # native Meta lead-form conversions (off-site; not in PostHog downstream)
            "leads": leads_by_ad.get(aid, 0),
        })
    return rows


def agg(rows):
    n = len(rows)
    impr = sum(r["impressions"] for r in rows)
    reach = sum(r["reach"] for r in rows)
    clicks = sum(r["link_clicks"] for r in rows)
    lpv = sum(r["lpv"] for r in rows)
    spend = sum(r["spend"] for r in rows)
    sess = sum(r["sessions"] for r in rows)
    conv = sum(r["converters"] for r in rows)
    engage = sum(r["post_engagement"] for r in rows)
    leads = sum(r["leads"] for r in rows)
    ctr = (100 * clicks / impr) if impr else 0
    cplpv = (spend / lpv) if lpv else 0
    return {"ads": n, "impr": impr, "reach": reach, "clicks": clicks, "lpv": lpv,
            "spend": round(spend, 2), "ctr%": round(ctr, 2), "cost/lpv": round(cplpv, 2),
            "engage": engage, "sessions": sess, "converters": conv, "leads": leads}


def print_group(rows, key, title):
    groups = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if isinstance(v, list):
            v = ",".join(v) if v else "(none)"
        groups[v if v is not None else "(unannotated)"].append(r)
    print(f"\n=== performance by {title} ===")
    hdr = (f"{'group':<26} {'ads':>4} {'impr':>7} {'reach':>6} {'ctr%':>5} {'LPV':>5} "
           f"{'$/LPV':>6} {'spend':>7} {'engag':>6} {'sess':>5} {'conv':>4} {'lead':>4}")
    print(hdr); print("-" * len(hdr))
    for g, rs in sorted(groups.items(), key=lambda kv: -agg(kv[1])["impr"]):
        a = agg(rs)
        print(f"{str(g)[:26]:<26} {a['ads']:>4} {a['impr']:>7} {a['reach']:>6} {a['ctr%']:>5} "
              f"{a['lpv']:>5} {a['cost/lpv']:>6} {a['spend']:>7} {a['engage']:>6} "
              f"{a['sessions']:>5} {a['converters']:>4} {a['leads']:>4}")


def cmd_rollup(rows):
    print("=" * 70)
    print("BRAIN 2 — ACCOUNT-WIDE AD ROLLUP")
    print("=" * 70)
    a = agg(rows)
    print(f"Ads: {a['ads']} | annotated: {sum(r['annotated'] for r in rows)} | "
          f"lifetime spend ${a['spend']} | impr {a['impr']} | reach {a['reach']} | "
          f"LPV {a['lpv']} | post-engagement {a['engage']}")
    print(f"CONVERSIONS: on-site address-entries {a['converters']} (from {a['sessions']} attributed sessions) "
          f"| off-site lead-form submissions {a['leads']}")
    for key, title in [("format", "format"), ("lever", "emotional lever"),
                       ("hook", "hook type"), ("theme", "message theme"),
                       ("cta_hardness", "CTA hardness"), ("cites_numbers", "cites numbers")]:
        print_group(rows, key, title)


def cmd_compare(rows, by):
    print_group(rows, by, by)


def cmd_converters(rows):
    conv = [r for r in rows if r["converters"] > 0]
    exact = [r for r in rows if r["attr_conf"] == "exact"]
    non = [r for r in exact if r["converters"] == 0]
    print("=" * 70)
    print("ADS THAT PRODUCED AN ADDRESS ENTRY (exact attribution)")
    print("=" * 70)
    for r in sorted(conv, key=lambda x: -x["converters"]):
        print(f"\n▶ {r['name'][:60]}")
        print(f"   {r['converters']} conv / {r['sessions']} sess | format={r['format']} "
              f"lever={r['lever']} hook={r['hook']} theme={r['theme']}")
        print(f"   persona={r['persona']} cta={r['cta_hardness']} cites_numbers={r['cites_numbers']} tone={r['tone']}")
    print("\n" + "=" * 70)
    print("CONVERTERS vs NON-CONVERTERS (exact-attributed ads only)")
    print("=" * 70)

    def dist(rs, k):
        c = defaultdict(int)
        for r in rs:
            v = r.get(k)
            if isinstance(v, list):
                v = ",".join(v) if v else "(none)"
            c[v] += 1
        tot = len(rs) or 1
        return {kk: f"{vv} ({round(100*vv/tot)}%)" for kk, vv in sorted(c.items(), key=lambda x: -x[1])}
    for k in ["lever", "hook", "format", "theme", "cta_hardness", "cites_numbers"]:
        print(f"\n{k}:")
        print(f"   converters ({len(conv)}): {dist(conv, k)}")
        print(f"   non-conv   ({len(non)}): {dist(non, k)}")


def cmd_leads(rows):
    db = get_client()["system_monitor"]
    s = db.lead_attribution.find_one({"_id": "_summary"})
    print("=" * 70)
    print("NATIVE FACEBOOK LEAD-FORM CONVERSIONS (off-site — not in PostHog)")
    print("=" * 70)
    if not s:
        print("No lead_attribution summary yet — run lead_attribution_build.py")
        return
    print(f"real buyer leads: {s['real_buyer_leads']} | hot (timeframe ≤6mo): {s['hot_leads']} | "
          f"own a GC home: {s['owns_gc_home_leads']} | seller/AYH: {s['seller_ayh_leads']} | "
          f"internal test: {s['internal_test_leads']}")
    print("\n=== leads by ad (real buyer leads only) ===")
    hdr = f"{'ad_id':<22} {'leads':>5} {'hot':>4} {'owns':>4} {'spend$':>7} {'$/lead':>7}"
    print(hdr); print("-" * len(hdr))
    prof = {r["ad_id"]: r for r in rows}
    for b in s.get("by_ad", []):
        cpl = b["cost_per_lead"]
        print(f"{str(b['key'])[:22]:<22} {b['leads']:>5} {b['hot_leads']:>4} {b['owns_gc_home']:>4} "
              f"{(b['ad_spend_lifetime'] or 0):>7} {(cpl if cpl is not None else '—'):>7}")
        nm = (prof.get(b["key"], {}) or {}).get("name")
        if nm:
            print(f"    ↳ {nm[:64]}")
    print("\n=== leads by campaign ===")
    for b in s.get("by_campaign", []):
        cpl = f"${b['cost_per_lead']}/lead" if b["cost_per_lead"] is not None else "spend n/a"
        print(f"  {b['leads']:>2}  {str(b['key'])[:50]:<50} {cpl}")
    print(f"\narea: {s.get('area_dist')}\ntimeframe: {s.get('timeframe_dist')}")


def cmd_ad(rows, aid):
    db = get_client()["system_monitor"]
    p = db.ad_profiles.find_one({"_id": aid})
    a = db.ad_semantic_annotations.find_one({"ad_id": aid})
    d = db.ad_downstream.find_one({"_id": aid})
    print(json.dumps({
        "name": p.get("name") if p else None,
        "creative_structured": p.get("creative_structured") if p else None,
        "lifetime": p.get("lifetime") if p else None,
        "annotation": a.get("annotation") if a else None,
        "downstream": {k: v for k, v in (d or {}).items() if k != "_id"},
    }, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rollup", "compare", "converters", "leads", "ad"])
    ap.add_argument("--by", default="format")
    ap.add_argument("--id")
    args = ap.parse_args()
    rows = load()
    if args.cmd == "rollup":
        cmd_rollup(rows)
    elif args.cmd == "compare":
        cmd_compare(rows, args.by)
    elif args.cmd == "converters":
        cmd_converters(rows)
    elif args.cmd == "leads":
        cmd_leads(rows)
    elif args.cmd == "ad":
        cmd_ad(rows, args.id)


if __name__ == "__main__":
    main()
