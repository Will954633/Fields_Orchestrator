#!/usr/bin/env python3
"""
Stage 0 — Data Pull (the internal + external ground-truth pack).

Runs FIRST so no later LLM stage ever *recalls* a number. Builds:
  * internal_pack.json — live Fields data for the core three suburbs (prices with
    reliability flags, volume, DOM, live listing counts) + the audience-demand digest
    from system_monitor.search_intent_analysis (demand, fears, velocity, per-suburb,
    content gaps, reddit sentiment).
  * an external source registry (what the deep-research stages must fetch live) — we do
    NOT pre-fetch external figures here; the researcher fetches + cites them, which keeps
    provenance on the claim. Internal figures, by contrast, are SUPPLIED and never recalled
    (the union-medians lesson, [UNION-MEDIANS-REVERTED-NIGHTLY]).

Output artifact: data/<cycle>/internal_pack.json
Zero-output assertion (Rule 7b): if zero live listings across all three suburbs OR the
indexed-price store returns nothing, RAISE — the pipeline is broken, not the market empty.
"""
from __future__ import annotations

import argparse
import json
import sys

import mce_common as mc


# ---------------------------------------------------------------- external registry
# The reputable sources / endpoints the deep-research stages must consult. Kept here so the
# list is auditable and versioned, not buried in a prompt.
EXTERNAL_SOURCES = {
    "national": [
        "RBA cash rate + latest media release + Statement on Monetary Policy (rba.gov.au)",
        "ABS: CPI, WPI (wages), Monthly Household Spending Indicator, Lending Indicators, "
        "Building Approvals, Regional Population, Regional Internal Migration (abs.gov.au)",
        "Cotality/CoreLogic Home Value Index (monthly + daily) by capital",
        "PropTrack Home Price Index + market outlook (proptrack.com.au)",
        "Westpac-Melbourne Institute Consumer Sentiment + House Price Expectations + "
        "'time to buy a dwelling'",
    ],
    "queensland": [
        "QGSO population + regional migration + dwelling data (qgso.qld.gov.au)",
        "REIQ quarterly median house/unit by LGA",
        "QLD Treasury / state budget housing measures",
    ],
    "gold_coast": [
        "Cotality/PropTrack Gold Coast SA4 figures",
        "Gold Coast Bulletin / myGC local property coverage",
        "Local REIQ / agent commentary + council development notices",
    ],
    "policy": [
        "2026 negative-gearing & CGT reform: Treasury/ATO/Parliament progress + "
        "Grattan/PropTrack/bank modelling",
    ],
}


def _digest_search_intent(sm) -> dict:
    """Compact the newest search_intent_analysis doc into the signals MCE actually uses."""
    d = sm["search_intent_analysis"].find_one(sort=[("analysed_at", -1)])
    if not d:
        return {"available": False}

    clusters = d.get("clusters") or []
    fears = (d.get("fears") or {}).get("by_type") or {}
    trends = (d.get("trends_analysis") or {}).get("by_volume") or []
    questions = d.get("questions") or []
    gaps = (d.get("content_gaps") or {}).get("gaps") or []
    importance = (d.get("importance") or {}).get("top_queries") or []
    reddit = d.get("reddit_pulse") or {}
    suburbs = d.get("suburbs") or {}

    return {
        "available": True,
        "date": d.get("date"),
        "analysed_at": d.get("analysed_at"),
        "lookback_days": d.get("lookback_days"),
        "total_records": d.get("total_records"),
        "source_counts": d.get("source_counts"),
        # topic candidates: phrase clusters ranked by how much they are searched
        "clusters": [{"phrase": c.get("phrase"), "query_count": c.get("query_count"),
                      "frequency": c.get("frequency"),
                      "sample": (c.get("sample_queries") or [])[:4]}
                     for c in clusters[:25]],
        # demand: the questions people actually ask, by frequency
        "top_questions": [{"q": q.get("question"), "freq": q.get("frequency"),
                           "sources": q.get("sources")} for q in questions[:25]],
        # editorial-answerability candidates: demand we do NOT yet cover
        "content_gaps": [{"q": g.get("question"), "freq": g.get("frequency"),
                          "sources": g.get("sources")} for g in gaps[:20]],
        # psychology: fear taxonomy with volumes
        "fears": {ftype: {"count": fv.get("count"),
                          "top": [s.get("text") for s in (fv.get("signals") or [])[:5]]}
                  for ftype, fv in fears.items()},
        # velocity/novelty: brand-new queries this window
        "velocity": {"new_query_count": (d.get("velocity") or {}).get("new_query_count"),
                     "sample": ((d.get("velocity") or {}).get("new_queries") or [])[:15]},
        # trend direction from Google Trends
        "trends": [{"kw": t.get("keyword"), "recent_avg": t.get("recent_avg"),
                    "direction": t.get("trend_direction")} for t in trends[:12]],
        # importance-scored top queries (a pre-ranked demand signal)
        "importance_top": [{"q": i.get("query"), "score": i.get("score"),
                            "is_fear": i.get("is_fear"), "sources": i.get("sources")}
                           for i in importance[:20]],
        # sentiment from Reddit AusProperty etc.
        "reddit_sentiment": reddit.get("sentiment"),
        # per-suburb query/fear/lifestyle breakdown
        "suburbs": {s: {"total_queries": (suburbs.get(s) or {}).get("total_queries"),
                        "questions": ((suburbs.get(s) or {}).get("questions") or [])[:6],
                        "fears": ((suburbs.get(s) or {}).get("fears") or [])[:4]}
                    for s in mc.TARGET_SUBURBS if s in suburbs},
    }


def _internal_numbers(gc) -> dict:
    """Per-suburb live listing counts + a pointer to the reliability-flagged price pack."""
    out = {}
    for s in mc.TARGET_SUBURBS:
        try:
            out[s] = {
                "for_sale": gc[s].count_documents({"listing_status": "for_sale"}),
                "sold": gc[s].count_documents({"listing_status": "sold"}),
            }
        except Exception as e:
            out[s] = {"error": f"{type(e).__name__}: {e}"}
    return out


def build_pack(cycle: str) -> dict:
    sm = mc.get_sm()
    gc = mc.get_gc()

    # The reliability-flagged suburb price/volume/DOM block — reuse the proven builder so
    # MCE and the mindset brief cite identical figures.
    from homeowner_mindset import fields_data_pack
    fields_md = fields_data_pack(gc)

    counts = _internal_numbers(gc)
    intent = _digest_search_intent(sm)

    total_for_sale = sum(v.get("for_sale", 0) for v in counts.values()
                         if isinstance(v.get("for_sale"), int))

    pack = {
        "cycle": cycle,
        "built_at": mc.now_tz().isoformat(timespec="seconds"),
        "suburbs": mc.TARGET_SUBURBS,
        "display_names": mc.DISPLAY_NAMES,
        "listing_counts": counts,
        "total_live_listings": total_for_sale,
        "fields_price_pack_md": fields_md,          # hand this to LLMs verbatim
        "search_intent": intent,                     # demand / fear / velocity digest
        "external_sources": EXTERNAL_SOURCES,        # what deep-research must fetch live
        "reliability_note": (
            "Fields figures in fields_price_pack_md are SUPPLIED — never recalled or "
            "restated from any other source. A quarter flagged reliable=false cannot "
            "support a quarter-on-quarter narrative. Valuation design envelope is "
            "$1,000,000-$2,000,000 for detached houses; outside it, suppress point figures."
        ),
    }

    # Rule 7b: assert an outcome, don't merely fail to throw.
    if total_for_sale == 0:
        raise RuntimeError("Stage 0: zero live listings across all three suburbs — scrape "
                           "pipeline is broken, not the market empty")
    if "NO DATA" in fields_md and fields_md.count("NO DATA") == len(mc.TARGET_SUBURBS):
        raise RuntimeError("Stage 0: precomputed_indexed_prices returned nothing for any "
                           "target suburb — union-median pipeline is broken")
    if not intent.get("available"):
        # Not fatal (demand layer is additive), but must be loud.
        print("    ! Stage 0: search_intent_analysis unavailable — topic ranking and "
              "psychology will run without the demand layer", file=sys.stderr)

    return pack


def render_pack_md(pack: dict, *, include_demand: bool = True) -> str:
    """A markdown rendering of the internal pack for LLM prompts."""
    lines = [pack["fields_price_pack_md"], ""]
    lines.append("LIVE LISTING COUNTS (Fields scrape — supplied, do not restate from memory):")
    for s in pack["suburbs"]:
        c = pack["listing_counts"].get(s, {})
        lines.append(f"- {pack['display_names'].get(s, s)}: {c.get('for_sale')} for sale, "
                     f"{c.get('sold')} sold on record")
    intent = pack.get("search_intent") or {}
    if include_demand and intent.get("available"):
        lines += ["", "AUDIENCE DEMAND SIGNAL (Fields search-intent, "
                  f"{intent.get('lookback_days')}d, {intent.get('total_records')} records, "
                  f"as at {intent.get('date')}):"]
        lines.append("- Top fear categories: " + ", ".join(
            f"{k} (n={v.get('count')})" for k, v in (intent.get("fears") or {}).items()))
        lines.append("- Most-asked questions: " + "; ".join(
            q["q"] for q in (intent.get("top_questions") or [])[:8]))
        rs = intent.get("reddit_sentiment") or {}
        if rs:
            lines.append(f"- Reddit AusProperty sentiment: fear={rs.get('fear')}, "
                         f"neutral={rs.get('neutral')}, hope={rs.get('hope')}")
    return "\n".join(lines)


def run(cycle: str) -> dict:
    pack = build_pack(cycle)
    path = mc.save_artifact(cycle, "internal_pack.json", pack)
    intent = pack.get("search_intent") or {}
    print(f"    ✓ Stage 0: internal_pack.json — {pack['total_live_listings']} live listings, "
          f"demand-layer={'yes' if intent.get('available') else 'NO'} "
          f"({len(intent.get('clusters') or [])} clusters, "
          f"{len(intent.get('content_gaps') or [])} gaps)", file=sys.stderr)
    return pack


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 0 — data pull")
    ap.add_argument("--cycle", default=mc.cycle_id())
    ap.add_argument("--print-md", action="store_true", help="print the prompt markdown block")
    a = ap.parse_args()
    pack = run(a.cycle)
    if a.print_md:
        print(render_pack_md(pack))
    else:
        print(json.dumps({k: v for k, v in pack.items()
                          if k not in ("fields_price_pack_md", "search_intent")}, indent=2,
                         default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
