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
import ast
import re
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

# Lead-side gates. These are DELIBERATELY unreachable at current volume — the
# whole account has produced single-digit qualified seller leads. Nothing on the
# lead side is rankable yet; the point of recording it is that the pattern
# becomes visible as volume accumulates, not that it can be read today.
MIN_LEADS = 10          # per group, before cost-per-lead means anything
MIN_QUALIFIED_LEADS = 5  # per group, before cost-per-QUALIFIED-lead means anything

# The zero-qualified finding is gated on SPEND, not impressions. An ad that spent
# real money and returned no qualified seller is a cost FACT and holds at any
# volume; an impression floor is a gate on CTR *reliability* and would have
# silently dropped AN3 (99 impr) and AN28 (201 impr) — the two ads that most
# clearly demonstrate cheap clicks with zero intent. $10 ~ the funnel's own
# $15/ad kill threshold.
MIN_LEAD_SPEND = 10.0

LEAD_EVIDENCE_NOTE = (
    "LEAD NUMBERS ARE NOT RANKABLE. Across 34 tested homeowner angles the account "
    "has produced ~7 raw leads and 3 qualified ones. A hook with 1 qualified lead "
    "and a hook with 0 are the same measurement. Treat every cost-per-qualified-lead "
    "figure as a placeholder that accrues meaning later, never as a comparison."
)

CORPUS = "content_hook_corpus"
AGGS = "content_hook_aggregates"
FINDINGS = "content_hook_findings"

CONFOUND_NOTE = (
    "CTR is not comparable across campaign objectives. OUTCOME_ENGAGEMENT "
    "delivery optimises for cheap in-feed interactions and inflates raw CTR "
    "several-fold versus OUTCOME_TRAFFIC / OUTCOME_LEADS. Targeting (broad vs "
    "custom audience, suburb radius) is a second uncontrolled variable. Compare "
    "hooks only WITHIN one objective, and check objective_mix before ranking."
)


def _num(v, default=0):
    return v if isinstance(v, (int, float)) else default


# --------------------------------------------------------------------------
# lead quality
# --------------------------------------------------------------------------
def _lead_fields(lead):
    """fb_leads.fields is stored as a python-repr STRING, not a sub-document."""
    f = lead.get("fields")
    if isinstance(f, dict):
        return f
    if isinstance(f, str):
        try:
            v = ast.literal_eval(f)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


_AU_PHONE = re.compile(r"^(?:\+?61|0)[2-478]\d{8}$")


def _contactable(phone):
    """A lead we cannot ring is not a qualified seller lead.

    The homeowner-funnel ledger recorded '4 quality leads'; one of them
    (AN2_missmillion_light, 2026-07-29) submitted +93413572138 — an Afghanistan
    country code on a Gold Coast homeowner form. Verified correction: 3, not 4.
    This is derived from the raw phone number rather than hard-coded per angle,
    so the same defect is caught in future leads automatically.
    """
    if not phone:
        return False, "no_phone"
    p = re.sub(r"[\s()-]", "", str(phone))
    if not _AU_PHONE.match(p):
        return False, f"non_au_phone:{p[:4]}"
    return True, None


def grade_leads(db):
    """Per-ad lead ledger with QUALITY, not just count.

    Grades (mutually exclusive):
      qualified            — selling_intent == yes AND a contactable AU number.
      unqualified_intent   — form answered selling_intent == no. A real person,
                             explicitly not a seller. Junk for this funnel.
      unqualified_contact  — stated selling intent but unreachable / fake number.
      ungraded             — form carries no selling-intent question at all
                             (the Buyer Brief / carousel buyer forms). Quality is
                             UNKNOWN, not zero — never count these as failures.
      excluded             — is_test (Will's own submissions). Dropped entirely.
    """
    per_ad = defaultdict(lambda: {
        "leads": 0, "qualified": 0, "unqualified_intent": 0,
        "unqualified_contact": 0, "ungraded": 0, "excluded": 0,
        "grades": [], "test_market": False,
    })
    for lead in db.fb_leads.find({}):
        ad_id = lead.get("ad_id")
        if not ad_id:
            continue
        rec = per_ad[ad_id]
        if str(lead.get("is_test")).lower() == "true":
            rec["excluded"] += 1
            continue
        if str(lead.get("test_market")).lower() == "true":
            rec["test_market"] = True

        f = _lead_fields(lead)
        intent = str(f.get("selling_intent", "")).strip().lower()
        ok, why = _contactable(f.get("phone_number"))

        if not intent:
            grade, reason = "ungraded", "form has no selling-intent question"
        elif intent in ("no", "false", "n"):
            grade, reason = "unqualified_intent", "answered selling_intent = no"
        elif not ok:
            grade, reason = "unqualified_contact", why
        else:
            grade, reason = "qualified", "selling_intent = yes + contactable AU number"

        rec["leads"] += 1
        rec[grade] += 1
        rec["grades"].append({"lead_id": lead.get("_id"), "grade": grade,
                              "reason": reason})
    return per_ad


def build_rows(db):
    """Join ad_profiles x ad_semantic_annotations on ad_id."""
    profiles = {d["ad_id"]: d for d in db.ad_profiles.find({}) if d.get("ad_id")}
    annotations = list(db.ad_semantic_annotations.find({}))

    # leads attributable per ad, GRADED for quality (not just counted)
    lead_ledger = grade_leads(db)

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
        ld = lead_ledger.get(ad_id) or {}
        n_leads = ld.get("leads", 0)
        n_qualified = ld.get("qualified", 0)
        n_ungraded = ld.get("ungraded", 0)
        is_lead_optimised = prof.get("campaign_objective") == "OUTCOME_LEADS"

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
                "is_lead_optimised": is_lead_optimised,
                "leads": n_leads,
                "cost_per_lead_aud": round(spend / n_leads, 2) if n_leads else None,
                # --- lead QUALITY: the thing CTR cannot see ---
                "qualified_leads": n_qualified,
                "unqualified_intent_leads": ld.get("unqualified_intent", 0),
                "unqualified_contact_leads": ld.get("unqualified_contact", 0),
                "ungraded_leads": n_ungraded,
                "excluded_test_leads": ld.get("excluded", 0),
                "lead_grades": ld.get("grades", []),
                "test_market_lead_source": bool(ld.get("test_market")),
                "cost_per_qualified_lead_aud": (
                    round(spend / n_qualified, 2) if n_qualified else None
                ),
                # An ad that bought traffic and produced no qualified seller is
                # the corpus's most useful negative signal — name it on the row.
                "high_ctr_zero_qualified": bool(
                    is_lead_optimised
                    and impressions >= MIN_IMPRESSIONS
                    and (ctr or 0) > 0
                    and n_qualified == 0
                    and n_ungraded == 0
                ),
                "lead_insufficient_evidence": n_qualified < MIN_QUALIFIED_LEADS,
                "lead_evidence_note": LEAD_EVIDENCE_NOTE,
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
        qualified = sum(r["qualified_leads"] for r in group)
        ungraded = sum(r["ungraded_leads"] for r in group)
        unq_intent = sum(r["unqualified_intent_leads"] for r in group)
        unq_contact = sum(r["unqualified_contact_leads"] for r in group)
        lead_group = [r for r in group if r["is_lead_optimised"]]
        lead_spend = round(sum(r["spend_aud"] for r in lead_group), 2)
        lead_imps = sum(r["impressions"] for r in lead_group)
        lead_clicks = sum(r["clicks"] for r in lead_group)
        zero_qual = [r for r in group if r["high_ctr_zero_qualified"]]
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
                # --- the CTR view ---
                "total_leads": leads,
                "weighted_ctr_pct": round(100.0 * clicks / imps, 4) if imps else None,
                "weighted_link_ctr_pct": round(100.0 * link_clicks / imps, 4)
                if imps
                else None,
                "weighted_cpc_aud": round(spend / clicks, 4) if clicks else None,
                "weighted_cpm_aud": round(1000.0 * spend / imps, 2) if imps else None,
                # --- the LEAD view: scoped to lead-optimised delivery only, so a
                #     TRAFFIC ad's spend never dilutes a cost-per-lead figure ---
                "n_lead_optimised_ads": len(lead_group),
                "lead_optimised_spend_aud": lead_spend,
                "lead_optimised_impressions": lead_imps,
                "lead_optimised_ctr_pct": (
                    round(100.0 * lead_clicks / lead_imps, 4) if lead_imps else None
                ),
                "total_qualified_leads": qualified,
                "total_unqualified_intent_leads": unq_intent,
                "total_unqualified_contact_leads": unq_contact,
                "total_ungraded_leads": ungraded,
                "cost_per_lead_aud": round(lead_spend / leads, 2) if leads else None,
                "cost_per_qualified_lead_aud": (
                    round(lead_spend / qualified, 2) if qualified else None
                ),
                "qualified_rate_pct": (
                    round(100.0 * qualified / (qualified + unq_intent + unq_contact), 1)
                    if (qualified + unq_intent + unq_contact) else None
                ),
                "n_high_ctr_zero_qualified_ads": len(zero_qual),
                "high_ctr_zero_qualified_ads": [
                    {"ad_id": r["ad_id"], "ad_name": r["ad_name"],
                     "ctr_pct": r["ctr_pct"], "impressions": r["impressions"],
                     "spend_aud": r["spend_aud"]}
                    for r in sorted(zero_qual, key=lambda r: -(r["ctr_pct"] or 0))[:5]
                ],
                "lead_insufficient_evidence": (
                    qualified < MIN_QUALIFIED_LEADS or leads < MIN_LEADS
                ),
                "lead_evidence_note": (
                    f"n_lead_ads={len(lead_group)}, n_leads={leads}, "
                    f"n_qualified={qualified} — below the lead gate "
                    f"({MIN_LEADS} leads / {MIN_QUALIFIED_LEADS} qualified). "
                    "NOT RANKABLE. " + LEAD_EVIDENCE_NOTE
                ) if (qualified < MIN_QUALIFIED_LEADS or leads < MIN_LEADS) else (
                    f"n_leads={leads}, n_qualified={qualified}."
                ),
                "lead_rankable": not (qualified < MIN_QUALIFIED_LEADS
                                      or leads < MIN_LEADS),
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

    finding = zero_qualified_finding(rows)
    if finding and not dry_run:
        _upsert(db[FINDINGS], [finding])

    if not dry_run:
        # UPSERT, never drop-then-write. Another agent reads content_hook_corpus
        # concurrently; a delete_many leaves it empty for the length of the
        # rebuild and it cannot tell "empty" from "not built yet".
        _upsert(db[CORPUS], rows)
        _upsert(db[AGGS], aggregates)

    return rows, aggregates, unmatched, n_profiles, n_annotations


def _upsert(coll, docs):
    from pymongo import ReplaceOne

    if not docs:
        return
    ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
    for i in range(0, len(ops), 100):  # keep batches inside Cosmos RU budget
        coll.bulk_write(ops[i:i + 100], ordered=False)
    # retire rows for ads that have since disappeared, without a blind window
    keep = {d["_id"] for d in docs}
    stale = [d["_id"] for d in coll.find({}, {"_id": 1}) if d["_id"] not in keep]
    if stale:
        coll.delete_many({"_id": {"$in": stale}})


def zero_qualified_finding(rows):
    """The single most important thing this corpus can say.

    Clicks did not predict conversion in the homeowner funnel run: 'Archetype B'
    bought clicks at $4.27 with 0% qualified intent before decaying to ~$28 CPL.
    Any system that learns from CTR alone will reproduce exactly that ad. So the
    high-CTR / zero-qualified ads are surfaced as a named finding rather than
    left to be inferred from an absent column.
    """
    # Only ads whose leads were ACTUALLY GRADED for seller intent can be said to
    # have zero qualified leads. The Buyer Brief / carousel forms never asked the
    # question, so their leads are ungraded — unmeasured is not zero, and calling
    # it zero would be the same error as inferring absence from a field that was
    # never populated.
    lead_rows = [r for r in rows if r["is_lead_optimised"]
                 and r["spend_aud"] >= MIN_LEAD_SPEND
                 and r["ungraded_leads"] == 0]
    excluded_ungraded = [r for r in rows if r["is_lead_optimised"]
                         and r["spend_aud"] >= MIN_LEAD_SPEND
                         and r["ungraded_leads"] > 0]
    if not lead_rows:
        return None
    med_ctr = sorted(r["ctr_pct"] or 0 for r in lead_rows)[len(lead_rows) // 2]
    offenders = sorted(
        (r for r in lead_rows
         if (r["ctr_pct"] or 0) >= med_ctr and r["qualified_leads"] == 0),
        key=lambda r: -(r["ctr_pct"] or 0),
    )
    return {
        "_id": "finding:high_ctr_zero_qualified",
        "finding": "high_CTR_does_not_predict_qualified_seller_leads",
        "headline": (
            f"{len(offenders)} lead-optimised ads delivered at or above the median "
            f"CTR ({med_ctr:.2f}%) of the graded lead cohort and produced ZERO qualified "
            f"seller leads, on ${round(sum(r['spend_aud'] for r in offenders), 2):,.2f} "
            "of spend."
        ),
        "why_it_matters": (
            "A content system trained on CTR alone will learn to write these. The "
            "homeowner funnel already ran this experiment: the 'Identity Threat' "
            "archetype (AN3, AN28) bought the cheapest clicks in the account "
            "($4.27 CPL) at 0% qualified intent, then decayed to ~$28 CPL. "
            "Interesting is not the same as useful."
        ),
        "n_lead_optimised_ads_above_floor": len(lead_rows),
        "n_zero_qualified": len(offenders),
        "scope": (
            f"lead-optimised ads that spent >= ${MIN_LEAD_SPEND:.0f} and whose "
            "leads carried a selling-intent question. Gated on SPEND, not "
            "impressions: 'we paid and got no qualified seller' is a cost fact at "
            "any volume. Ads on buyer forms are excluded — their seller quality is "
            "UNMEASURED, not zero. Per-ad CTR below the "
            f"{MIN_IMPRESSIONS}-impression floor is flagged ctr_unreliable and "
            "must not be compared."
        ),
        "n_excluded_ungraded_ads": len(excluded_ungraded),
        "excluded_ungraded_ads": [
            {"ad_id": r["ad_id"], "ad_name": r["ad_name"],
             "ctr_pct": r["ctr_pct"], "leads": r["leads"],
             "ungraded_leads": r["ungraded_leads"]}
            for r in excluded_ungraded[:10]
        ],
        "median_ctr_pct": round(med_ctr, 4),
        "total_spend_on_zero_qualified_aud": round(
            sum(r["spend_aud"] for r in offenders), 2),
        "ads": [
            {"ad_id": r["ad_id"], "ad_name": r["ad_name"],
             "hook_type": r["hook_type"],
             "primary_emotional_lever": r["primary_emotional_lever"],
             "ctr_pct": r["ctr_pct"], "impressions": r["impressions"],
             "spend_aud": r["spend_aud"], "leads": r["leads"],
             "qualified_leads": r["qualified_leads"],
             "unqualified_intent_leads": r["unqualified_intent_leads"],
             "ctr_unreliable": r["impressions"] < MIN_IMPRESSIONS}
            for r in offenders[:25]
        ],
        "caveat": LEAD_EVIDENCE_NOTE,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


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
    _print_lead_view(rows, aggregates)


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


def _print_lead_view(rows, aggregates):
    """The conversion view. Deliberately printed BESIDE the CTR view, never
    instead of it, so the divergence between the two is the visible object."""
    lead_rows = [r for r in rows if r["is_lead_optimised"]]
    print("=" * 78)
    print("LEAD VIEW — what actually earned SELLERS (not clicks)")
    print("=" * 78)
    print(f"lead-optimised ads in corpus   : {len(lead_rows)}")
    print(f"  with any delivery            : "
          f"{sum(1 for r in lead_rows if r['impressions'] > 0)}")
    print(f"  spend                        : "
          f"${sum(r['spend_aud'] for r in lead_rows):,.2f}")
    print(f"  raw leads                    : {sum(r['leads'] for r in lead_rows)}")
    print(f"  QUALIFIED (intent + contactable): "
          f"{sum(r['qualified_leads'] for r in lead_rows)}")
    print(f"  unqualified (said no)        : "
          f"{sum(r['unqualified_intent_leads'] for r in lead_rows)}")
    print(f"  unqualified (fake/foreign phone): "
          f"{sum(r['unqualified_contact_leads'] for r in lead_rows)}")
    print(f"  ungraded (buyer forms, no intent question): "
          f"{sum(r['ungraded_leads'] for r in lead_rows)}")
    print(f"  excluded (internal test)     : "
          f"{sum(r['excluded_test_leads'] for r in rows)}")
    print()

    for dim in ("hook_type", "primary_emotional_lever"):
        block = [a for a in aggregates if a["dimension"] == dim
                 and not a.get("controlled_for_objective")
                 and a["n_lead_optimised_ads"]]
        if not block:
            continue
        print("-" * 78)
        print(f"BY {dim.upper()} — COST PER QUALIFIED LEAD  "
              f"(! = not rankable, which is everything)")
        print("-" * 78)
        print(f"{'':1}{'value':<24}{'ads':>4}{'impr':>9}{'CTR%':>7}"
              f"{'spend':>9}{'lds':>5}{'qual':>5}{'$/lead':>9}{'$/QUAL':>9}")
        for a in sorted(block, key=lambda a: -a["lead_optimised_spend_aud"]):
            flag = "!" if a["lead_insufficient_evidence"] else " "
            ctr = (f"{a['lead_optimised_ctr_pct']:.2f}"
                   if a["lead_optimised_ctr_pct"] is not None else "n/a")
            cpl = (f"{a['cost_per_lead_aud']:.2f}"
                   if a["cost_per_lead_aud"] is not None else "—")
            cpq = (f"{a['cost_per_qualified_lead_aud']:.2f}"
                   if a["cost_per_qualified_lead_aud"] is not None else "NONE")
            print(f"{flag}{str(a['value'])[:23]:<24}{a['n_lead_optimised_ads']:>4}"
                  f"{a['lead_optimised_impressions']:>9,}{ctr:>7}"
                  f"{a['lead_optimised_spend_aud']:>9.2f}{a['total_leads']:>5}"
                  f"{a['total_qualified_leads']:>5}{cpl:>9}{cpq:>9}")
        print()
        print("  '$/QUAL = NONE' means the hook produced NO qualified seller at any")
        print("  price — not that it was cheap. Read it as an infinite cost.")
        print()

    finding = zero_qualified_finding(rows)
    if finding:
        print("=" * 78)
        print("NAMED FINDING — " + finding["finding"])
        print("=" * 78)
        print("  " + finding["headline"])
        print(f"  ${finding['total_spend_on_zero_qualified_aud']:,.2f} spent on "
              f"{finding['n_zero_qualified']} of "
              f"{finding['n_lead_optimised_ads_above_floor']} graded ads over "
              f"the ${MIN_LEAD_SPEND:.0f} spend floor.")
        print(f"  ({finding['n_excluded_ungraded_ads']} further ads excluded — "
              "buyer forms, seller quality UNMEASURED not zero.)")
        print()
        for ad in finding["ads"][:15]:
            print(f"    {ad['ctr_pct']:>6.2f}%{'~' if ad['ctr_unreliable'] else ' '}"
                  f"CTR {ad['impressions']:>7,} impr  "
                  f"${ad['spend_aud']:>7.2f}  {ad['leads']} leads / "
                  f"{ad['qualified_leads']} qualified  "
                  f"{(ad['hook_type'] or '-'):<18}{(ad['ad_name'] or '')[:34]}")
        print("    (~ = below the impression floor: the CTR is noise, "
              "the SPEND and the zero are not)")
        print()
        print("  " + finding["why_it_matters"])
        print()
    print("!! " + LEAD_EVIDENCE_NOTE)
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
    _print_lead_view(rows, aggregates)

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
