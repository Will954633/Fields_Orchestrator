#!/usr/bin/env python3
"""
ad_query.py — Brain 2 query layer: join semantic annotation × downstream × spend
and answer pattern questions across the whole account.

Sources (all in system_monitor):
  ad_profiles          — structure + lifetime performance (creative_structured, lifetime)
  ad_semantic_annotations — Opus high-effort content annotation
  ad_downstream        — PostHog attribution (confidence-labelled)

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
            "link_clicks": lt.get("link_clicks") or 0,
            "lpv": lt.get("landing_page_views") or 0,
            "spend": lt.get("spend_aud") or 0,
            "ctr": lt.get("ctr") or 0,
            "cpc": lt.get("cpc_aud") or 0,
            "attr_conf": d.get("attribution_confidence"),
            "sessions": d.get("sessions") or 0,
            "converters": d.get("converters") or 0,
        })
    return rows


def agg(rows):
    n = len(rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["link_clicks"] for r in rows)
    lpv = sum(r["lpv"] for r in rows)
    spend = sum(r["spend"] for r in rows)
    sess = sum(r["sessions"] for r in rows)
    conv = sum(r["converters"] for r in rows)
    ctr = (100 * clicks / impr) if impr else 0
    cplpv = (spend / lpv) if lpv else 0
    return {"ads": n, "impr": impr, "clicks": clicks, "lpv": lpv, "spend": round(spend, 2),
            "ctr%": round(ctr, 2), "cost/lpv": round(cplpv, 2),
            "sessions": sess, "converters": conv}


def print_group(rows, key, title):
    groups = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if isinstance(v, list):
            v = ",".join(v) if v else "(none)"
        groups[v if v is not None else "(unannotated)"].append(r)
    print(f"\n=== performance by {title} ===")
    hdr = f"{'group':<26} {'ads':>4} {'impr':>7} {'ctr%':>5} {'LPV':>5} {'$/LPV':>6} {'spend':>7} {'sess':>5} {'conv':>4}"
    print(hdr); print("-" * len(hdr))
    for g, rs in sorted(groups.items(), key=lambda kv: -agg(kv[1])["impr"]):
        a = agg(rs)
        print(f"{str(g)[:26]:<26} {a['ads']:>4} {a['impr']:>7} {a['ctr%']:>5} "
              f"{a['lpv']:>5} {a['cost/lpv']:>6} {a['spend']:>7} {a['sessions']:>5} {a['converters']:>4}")


def cmd_rollup(rows):
    print("=" * 70)
    print("BRAIN 2 — ACCOUNT-WIDE AD ROLLUP")
    print("=" * 70)
    a = agg(rows)
    print(f"Ads: {a['ads']} | annotated: {sum(r['annotated'] for r in rows)} | "
          f"lifetime spend ${a['spend']} | impr {a['impr']} | LPV {a['lpv']} | "
          f"attributed sessions {a['sessions']} | address-entries {a['converters']}")
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
    ap.add_argument("cmd", choices=["rollup", "compare", "converters", "ad"])
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
    elif args.cmd == "ad":
        cmd_ad(rows, args.id)


if __name__ == "__main__":
    main()
