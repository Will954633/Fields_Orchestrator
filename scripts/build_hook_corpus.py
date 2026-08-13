#!/usr/bin/env python3
"""
build_hook_corpus.py — join the ad headline corpus to its measured outcomes.

Two source collections have never been joined:

  system_monitor.ad_profiles            — ~203 ads, many of them literally article
                                          titles used as ad copy, with lifetime
                                          delivery metrics (impressions, clicks,
                                          CTR, link_clicks, spend, CPC).
  system_monitor.ad_semantic_annotations — 92 ads classified by hook_type,
                                          primary_emotional_lever, tone,
                                          message_theme, value_proposition,
                                          reading_complexity, word/sentence counts.

They join on `ad_id`. This script writes:

  system_monitor.content_hook_corpus     — one doc per ad-headline: text +
                                           classification + measured outcome +
                                           campaign objective (the confounder).
  system_monitor.content_hook_aggregates — per hook_type / emotional_lever /
                                           message_theme rollups, impression-
                                           weighted, with evidence gating.

EVIDENCE DISCIPLINE (read this before quoting any number out of the output)
--------------------------------------------------------------------------
* Every aggregate is IMPRESSION-WEIGHTED (sum clicks / sum impressions), never a
  mean of per-ad CTRs. A 100% CTR on 3 impressions must not move a group mean.
* Every aggregate carries `n_ads`, `total_impressions` and `n_ads_with_delivery`
  so the denominator travels with the number.
* Any group with < MIN_IMPRESSIONS impressions or < MIN_ADS ads is stamped
  `insufficient_evidence: true` and MUST NOT be ranked.
* CTR differences across hook types are CONFOUNDED by campaign optimisation goal
  (OUTCOME_ENGAGEMENT delivery buys cheap in-feed clicks; OUTCOME_TRAFFIC and
  OUTCOME_LEADS do not) and by targeting. `campaign_objective` is recorded on
  every row, and each aggregate carries an `objective_mix` so a reader can
  control for it. `drafts/marketing-test-summary.md` documents an earlier
  "property stories beat market commentary" conclusion that was confounded in
  exactly this way — do not repeat it.

Usage
-----
  python3 scripts/build_hook_corpus.py            # build + write
  python3 scripts/build_hook_corpus.py --dry-run  # build + print, no writes
  python3 scripts/build_hook_corpus.py --show     # print corpus for an agent
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

from shared.db import get_client  # noqa: E402

try:
    from shared.env import load_env  # noqa: E402

    load_env()
except Exception:  # pragma: no cover - env helper is best effort
    pass

# --- evidence gates -------------------------------------------------------
MIN_IMPRESSIONS = 500
MIN_ADS = 3

CORPUS = "content_hook_corpus"
AGGS = "content_hook_aggregates"

CONFOUND_NOTE = (
    "CTR is not comparable across campaign objectives. OUTCOME_ENGAGEMENT "
    "delivery optimises for cheap in-feed interactions and inflates raw CTR "
    "several-fold versus OUTCOME_TRAFFIC / OUTCOME_LEADS. Targeting (broad vs "
    "custom audience, suburb radius) is a second uncontrolled variable. Compare "
    "hooks only WITHIN one objective, and check objective_mix before ranking."
)


def _num(v, default=0):
    return v if isinstance(v, (int, float)) else default


def build_rows(db):
    """Join ad_profiles x ad_semantic_annotations on ad_id."""
    profiles = {d["ad_id"]: d for d in db.ad_profiles.find({}) if d.get("ad_id")}
    annotations = list(db.ad_semantic_annotations.find({}))

    # leads attributable per ad (Facebook lead-form submissions)
    leads_by_ad = Counter()
    for lead in db.fb_leads.find({}, {"ad_id": 1}):
        if lead.get("ad_id"):
            leads_by_ad[lead["ad_id"]] += 1

    # downstream site behaviour per ad (sessions / converters), where computed
    downstream = {
        d["ad_id"]: d
        for d in db.ad_downstream.find(
            {}, {"ad_id": 1, "sessions": 1, "unique_visitors": 1, "converters": 1,
                 "conversion_rate_pct": 1, "attribution_confidence": 1}
        )
        if d.get("ad_id")
    }

    rows, unmatched = [], []
    for ann_doc in annotations:
        ad_id = ann_doc.get("ad_id")
        prof = profiles.get(ad_id)
        if not prof:
            unmatched.append(ad_id)
            continue

        a = ann_doc.get("annotation") or {}
        lt = prof.get("lifetime") or {}
        cs = prof.get("creative_structured") or {}
        cr = prof.get("creative") or {}

        impressions = int(_num(lt.get("impressions")))
        clicks = int(_num(lt.get("clicks")))
        link_clicks = int(_num(lt.get("link_clicks")))
        spend = round(float(_num(lt.get("spend_aud"))), 2)

        # recompute rather than trust the stored ctr/cpc — keeps them consistent
        ctr = round(100.0 * clicks / impressions, 4) if impressions else None
        link_ctr = round(100.0 * link_clicks / impressions, 4) if impressions else None
        cpc = round(spend / clicks, 4) if clicks else None
        cpm = round(1000.0 * spend / impressions, 2) if impressions else None
        cost_per_link_click = round(spend / link_clicks, 4) if link_clicks else None

        dn = downstream.get(ad_id) or {}
        n_leads = leads_by_ad.get(ad_id, 0)

        headline = (
            a.get("headline_text")
            or cs.get("primary_title")
            or cr.get("title")
            or ""
        ).strip()
        body = (cs.get("primary_body") or cr.get("body") or "").strip()

        # The "headline" an agent should learn from is the reader-facing text.
        # Many ads carry no headline field at all — the hook is the opening of
        # the body. Fall back to internal ad_name only as a last resort, and
        # record which we used so nobody mistakes an internal label for copy.
        hook = (a.get("hook_text") or "").strip()
        if headline:
            display_text, text_source = headline, "headline"
        elif hook:
            display_text, text_source = hook, "hook_text"
        elif body:
            display_text, text_source = body[:200], "body"
        else:
            display_text, text_source = (prof.get("name") or ""), "ad_name_internal"

        rows.append(
            {
                "_id": ad_id,
                "ad_id": ad_id,
                "ad_name": prof.get("name") or ann_doc.get("ad_name"),
                # --- the text ---
                "headline_text": headline,
                "headline_present": bool(headline),
                "display_text": display_text,
                "text_source": text_source,
                "hook_text": (a.get("hook_text") or "").strip(),
                "body_text": body,
                # --- the classification ---
                "hook_type": a.get("hook_type"),
                "primary_emotional_lever": a.get("primary_emotional_lever"),
                "emotional_registers": [
                    e.get("emotion") for e in (a.get("emotional_registers") or [])
                ],
                "tone": a.get("tone") or [],
                "message_theme": a.get("message_theme"),
                "value_proposition": a.get("value_proposition"),
                "target_persona": a.get("target_persona"),
                "reading_complexity": a.get("reading_complexity"),
                "copy_word_count": a.get("copy_word_count"),
                "copy_sentence_count": a.get("copy_sentence_count"),
                "cites_numbers": (a.get("specificity") or {}).get("cites_numbers"),
                "cites_suburb": (a.get("specificity") or {}).get("cites_suburb"),
                "cta_hardness": (a.get("cta_semantic") or {}).get("hardness"),
                "one_line_summary": a.get("one_line_summary"),
                # --- the confounders, recorded on every row ---
                "campaign_objective": prof.get("campaign_objective"),
                "campaign_name": prof.get("campaign_name"),
                "adset_name": prof.get("adset_name"),
                "format": ann_doc.get("format") or cr.get("format"),
                "uses_custom_audience": bool(
                    ((prof.get("targeting") or {}).get("custom_audiences") or [])
                ),
                "created_time": prof.get("created_time"),
                "effective_status": prof.get("effective_status"),
                # --- the measured outcome ---
                "impressions": impressions,
                "reach": int(_num(lt.get("reach"))),
                "clicks": clicks,
                "link_clicks": link_clicks,
                "landing_page_views": int(_num(lt.get("landing_page_views"))),
                "spend_aud": spend,
                "ctr_pct": ctr,
                "link_ctr_pct": link_ctr,
                "cpc_aud": cpc,
                "cpm_aud": cpm,
                "cost_per_link_click_aud": cost_per_link_click,
                "post_engagement": int(_num(lt.get("post_engagement"))),
                # --- conversions, where attributable at all ---
                "leads": n_leads,
                "cost_per_lead_aud": round(spend / n_leads, 2) if n_leads else None,
                "downstream_sessions": dn.get("sessions"),
                "downstream_converters": dn.get("converters"),
                "downstream_attribution_confidence": dn.get("attribution_confidence"),
                # --- evidence flags ---
                "has_delivery": impressions > 0,
                "insufficient_evidence": impressions < MIN_IMPRESSIONS,
                "evidence_note": (
                    f"{impressions} impressions — below the {MIN_IMPRESSIONS} "
                    "impression floor; per-ad CTR here is noise."
                )
                if impressions < MIN_IMPRESSIONS
                else None,
                "confound_note": CONFOUND_NOTE,
                "built_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return rows, unmatched, len(profiles), len(annotations)


def _aggregate(rows, key, dimension):
    """Impression-weighted rollup over one classification dimension."""
    buckets = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v:
            buckets[v].append(r)

    out = []
    for value, group in buckets.items():
        imps = sum(r["impressions"] for r in group)
        clicks = sum(r["clicks"] for r in group)
        link_clicks = sum(r["link_clicks"] for r in group)
        spend = round(sum(r["spend_aud"] for r in group), 2)
        leads = sum(r["leads"] for r in group)
        delivered = [r for r in group if r["impressions"] > 0]
        # examples are drawn ONLY from ads that clear the evidence floor
        eligible = sorted(
            (r for r in group if r["impressions"] >= MIN_IMPRESSIONS),
            key=lambda r: r["ctr_pct"] or 0,
        )
        insufficient = imps < MIN_IMPRESSIONS or len(group) < MIN_ADS

        def _example(r):
            if not r:
                return None
            return {
                "ad_id": r["ad_id"],
                "text": r.get("display_text") or r["ad_name"],
                "text_source": r.get("text_source"),
                "ctr_pct": r["ctr_pct"],
                "impressions": r["impressions"],
                "campaign_objective": r["campaign_objective"],
            }

        out.append(
            {
                "_id": f"{dimension}:{value}",
                "dimension": dimension,
                "value": value,
                "n_ads": len(group),
                "n_ads_with_delivery": len(delivered),
                "n_ads_above_evidence_floor": len(eligible),
                "total_impressions": imps,
                "total_clicks": clicks,
                "total_link_clicks": link_clicks,
                "total_spend_aud": spend,
                "total_leads": leads,
                "weighted_ctr_pct": round(100.0 * clicks / imps, 4) if imps else None,
                "weighted_link_ctr_pct": round(100.0 * link_clicks / imps, 4)
                if imps
                else None,
                "weighted_cpc_aud": round(spend / clicks, 4) if clicks else None,
                "weighted_cpm_aud": round(1000.0 * spend / imps, 2) if imps else None,
                "best_example": _example(eligible[-1] if eligible else None),
                "worst_example": _example(eligible[0] if eligible else None),
                "objective_mix": dict(
                    Counter(r["campaign_objective"] for r in delivered)
                ),
                "impressions_by_objective": {
                    o: sum(r["impressions"] for r in delivered
                           if r["campaign_objective"] == o)
                    for o in {r["campaign_objective"] for r in delivered}
                },
                "insufficient_evidence": insufficient,
                "evidence_note": (
                    f"n_ads={len(group)}, impressions={imps} — below the gate "
                    f"({MIN_ADS} ads / {MIN_IMPRESSIONS} impressions). "
                    "Do not rank on this."
                )
                if insufficient
                else f"n_ads={len(group)}, impressions={imps}.",
                "confound_note": CONFOUND_NOTE,
                "rankable": not insufficient,
                "built_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    out.sort(key=lambda d: -d["total_impressions"])
    return out


def _aggregate_within_objective(rows, key):
    """Same rollup, held inside one campaign objective — the only fair compare."""
    out = []
    objectives = {r["campaign_objective"] for r in rows if r["campaign_objective"]}
    for obj in objectives:
        subset = [r for r in rows if r["campaign_objective"] == obj]
        for agg in _aggregate(subset, key, f"{key}|{obj}"):
            agg["_id"] = f"{key}@{obj}:{agg['value']}"
            agg["campaign_objective"] = obj
            agg["dimension"] = key
            agg["controlled_for_objective"] = True
            out.append(agg)
    return out


def build(dry_run=False):
    db = get_client()["system_monitor"]
    rows, unmatched, n_profiles, n_annotations = build_rows(db)

    aggregates = []
    for key in ("hook_type", "primary_emotional_lever", "message_theme"):
        aggregates.extend(_aggregate(rows, key, key))
    # objective-controlled views (only hook_type — the others fragment too far)
    aggregates.extend(_aggregate_within_objective(rows, "hook_type"))

    if not dry_run:
        db[CORPUS].delete_many({})
        if rows:
            db[CORPUS].insert_many(rows)
        db[AGGS].delete_many({})
        if aggregates:
            db[AGGS].insert_many(aggregates)

    return rows, aggregates, unmatched, n_profiles, n_annotations


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def print_build_report(rows, aggregates, unmatched, n_profiles, n_annotations):
    delivered = [r for r in rows if r["impressions"] > 0]
    above = [r for r in rows if r["impressions"] >= MIN_IMPRESSIONS]
    print("=" * 78)
    print("CONTENT HOOK CORPUS — build report")
    print("=" * 78)
    print(f"ad_profiles                    : {n_profiles}")
    print(f"ad_semantic_annotations        : {n_annotations}")
    print(f"joined on ad_id                : {len(rows)}")
    print(f"annotations with no profile    : {len(unmatched)} {unmatched[:5]}")
    print(f"unannotated ads (no hook data) : {n_profiles - len(rows)}")
    print(f"joined rows with any delivery  : {len(delivered)}")
    print(f"joined rows >= {MIN_IMPRESSIONS} impressions : {len(above)}")
    print(f"total impressions in corpus    : {sum(r['impressions'] for r in rows):,}")
    print(f"total spend in corpus          : "
          f"${sum(r['spend_aud'] for r in rows):,.2f}")
    print(f"total attributed leads         : {sum(r['leads'] for r in rows)}")
    print()
    print("objective mix of the JOINED rows:")
    for obj, n in Counter(r["campaign_objective"] for r in rows).most_common():
        imps = sum(r["impressions"] for r in rows if r["campaign_objective"] == obj)
        print(f"  {obj:<22} {n:>3} ads  {imps:>9,} impressions")
    print()
    print(f"aggregate documents written    : {len(aggregates)}")
    print()
    _print_aggregates(aggregates)


def _print_aggregates(aggregates, dims=("hook_type", "primary_emotional_lever",
                                        "message_theme")):
    for dim in dims:
        block = [a for a in aggregates
                 if a["dimension"] == dim and not a.get("controlled_for_objective")]
        if not block:
            continue
        print("-" * 78)
        print(f"BY {dim.upper()}  (impression-weighted; * = insufficient evidence)")
        print("-" * 78)
        print(f"{'':1}{'value':<24}{'n':>4}{'impr':>10}{'clicks':>8}"
              f"{'wCTR%':>8}{'spend':>9}  objective mix")
        for a in block:
            flag = "*" if a["insufficient_evidence"] else " "
            ctr = f"{a['weighted_ctr_pct']:.2f}" if a["weighted_ctr_pct"] is not None else "n/a"
            mix = ",".join(f"{k.replace('OUTCOME_','')}:{v}"
                           for k, v in sorted(a["objective_mix"].items()))
            print(f"{flag}{str(a['value'])[:23]:<24}{a['n_ads']:>4}"
                  f"{a['total_impressions']:>10,}{a['total_clicks']:>8}"
                  f"{ctr:>8}{a['total_spend_aud']:>9.2f}  {mix}")
        print()
        for a in block:
            if a["insufficient_evidence"]:
                continue
            print(f"  [{a['value']}]  n={a['n_ads']}, "
                  f"{a['total_impressions']:,} impressions")
            for label in ("best_example", "worst_example"):
                ex = a.get(label)
                if ex:
                    print(f"    {label.split('_')[0]:<5} {ex['ctr_pct']:.2f}% "
                          f"({ex['impressions']:,} impr, "
                          f"{(ex['campaign_objective'] or '').replace('OUTCOME_','')}): "
                          f"{(ex['text'] or '')[:88]}")
        print()

    controlled = [a for a in aggregates if a.get("controlled_for_objective")
                  and not a["insufficient_evidence"]]
    if controlled:
        print("-" * 78)
        print("HOOK TYPE HELD WITHIN ONE CAMPAIGN OBJECTIVE (the only fair compare)")
        print("-" * 78)
        for obj in sorted({a["campaign_objective"] for a in controlled}):
            print(f"  {obj}")
            for a in sorted((x for x in controlled if x["campaign_objective"] == obj),
                            key=lambda x: -x["total_impressions"]):
                print(f"    {str(a['value'])[:22]:<24} n={a['n_ads']:<3} "
                      f"{a['total_impressions']:>8,} impr   "
                      f"wCTR {a['weighted_ctr_pct']:.2f}%")
        print()
    print("!! " + CONFOUND_NOTE)
    print()


def show(db=None):
    """Agent-readable dump, for reading at cycle start."""
    db = db or get_client()["system_monitor"]
    rows = list(db[CORPUS].find({}))
    aggregates = list(db[AGGS].find({}))
    if not rows:
        print("content_hook_corpus is empty — run build_hook_corpus.py first.")
        return

    print("=" * 78)
    print("CONTENT HOOK CORPUS — what our own headlines actually measured")
    print("=" * 78)
    print(f"{len(rows)} ad-headlines, "
          f"{sum(r['impressions'] for r in rows):,} impressions, "
          f"${sum(r['spend_aud'] for r in rows):,.2f} spend, "
          f"{sum(r['leads'] for r in rows)} attributed leads.")
    print(f"Evidence floor: {MIN_IMPRESSIONS} impressions / {MIN_ADS} ads per group.")
    print()
    _print_aggregates(aggregates)

    above = sorted(
        (r for r in rows if r["impressions"] >= MIN_IMPRESSIONS),
        key=lambda r: -(r["ctr_pct"] or 0),
    )
    print("-" * 78)
    print(f"TOP 15 HEADLINES ABOVE THE EVIDENCE FLOOR "
          f"({len(above)} of {len(rows)} qualify)")
    print("-" * 78)
    for r in above[:15]:
        print(f"  {r['ctr_pct']:>6.2f}%  {r['impressions']:>7,} impr  "
              f"{(r['campaign_objective'] or '').replace('OUTCOME_',''):<12}"
              f"{r['hook_type'] or '-':<18}"
              f"{(r.get('display_text') or r['ad_name'] or '')[:60]}")
    print()
    print("BOTTOM 10 ABOVE THE FLOOR")
    for r in above[-10:]:
        print(f"  {r['ctr_pct']:>6.2f}%  {r['impressions']:>7,} impr  "
              f"{(r['campaign_objective'] or '').replace('OUTCOME_',''):<12}"
              f"{r['hook_type'] or '-':<18}"
              f"{(r.get('display_text') or r['ad_name'] or '')[:60]}")
    print()
    print("READ THIS BEFORE USING THE ABOVE:")
    print("  " + CONFOUND_NOTE)
    print("  Groups marked * are not rankable. Per-ad CTR below the floor is noise.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true",
                    help="print the existing corpus for an agent to read")
    ap.add_argument("--dry-run", action="store_true", help="build but do not write")
    args = ap.parse_args()

    if args.show:
        show()
        return

    rows, aggregates, unmatched, n_profiles, n_annotations = build(args.dry_run)
    print_build_report(rows, aggregates, unmatched, n_profiles, n_annotations)
    if args.dry_run:
        print("(dry run — nothing written)")
    else:
        print(f"wrote system_monitor.{CORPUS} ({len(rows)}) and "
              f"system_monitor.{AGGS} ({len(aggregates)})")


if __name__ == "__main__":
    main()
