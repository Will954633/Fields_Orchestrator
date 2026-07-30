#!/usr/bin/env python3
"""
compute_reward.py — the composite reward view over the funnel ledger (§5 of
04_EXPANDED_MANDATE_SCOPING.md).

Reads system_monitor.funnel_events (ad_stats + funnel_event rows) and produces,
PER VARIANT:
  - engagement:     funnel progression depth (lp_view -> step -> field -> micro -> terminal)
  - micro_value:    business-value-weighted count of sub-goals reached (address>phone>email>name)
  - junk_signal:    bounces (lp_view, no step) + No-intent + invalid-contact patterns
  - reward:         w1*engagement + w2*micro_value - w3*junk   (quality-adjusted, NOT raw clicks)
  - cost + quality-adjusted cost per goal (spend / micro-conversions[goal])
And ACROSS the lab:
  - PII-resistance ranking (Q1): per field, abandon-rate = 1 - complete/focus.

This is what every wake-up cycle reads INSTEAD of the FB-only checkpoint. Raw
engagement is reported alongside the quality-adjusted number so a variant that
wins on clicks but fills with tyre-kickers (the AN3 lesson) reads as a LOSS.

Usage: python3 compute_reward.py [--json]
"""
from __future__ import annotations
import sys, json, argparse
from collections import defaultdict

sys.path.insert(0, "/home/fields/Fields_Orchestrator/03_Facebook/Home_Owner_Lead_Funnel_Search/ledger")
from funnel_ledger import (Ledger, EVENT_SPINE, CALL_CTA_EVENT, PII_FIELDS,
                           GOAL_WEIGHTS)

# composite reward weights (tunable as data accrues — start heuristic)
W_ENGAGEMENT = 1.0
W_MICRO = 3.0
W_JUNK = 1.5

# progression credit per depth reached (index in EVENT_SPINE)
DEPTH_CREDIT = {0: 0.1, 1: 0.25, 2: 0.4, 3: 0.7, 4: 1.0, 5: 1.0}

DISPOSABLE_EMAIL_DOMAINS = {"mailinator.com", "guerrillamail.com", "10minutemail.com",
                            "trashmail.com", "tempmail.com", "yopmail.com"}


def _depth_of(event: str) -> int:
    return EVENT_SPINE.index(event) if event in EVENT_SPINE else -1


def compute():
    lg = Ledger()
    ad_rows = lg.ad_stats()
    ev_rows = lg.funnel_events()

    # ----- cost per variant (FB side) -----
    cost = defaultdict(lambda: {"spend": 0.0, "impressions": 0, "clicks": 0, "fb_leads": 0})
    for r in ad_rows:
        c = cost[r["variant"]]
        c["spend"] += r.get("spend", 0.0); c["impressions"] += r.get("impressions", 0)
        c["clicks"] += r.get("clicks", 0); c["fb_leads"] += r.get("fb_leads", 0)

    # ----- behaviour per variant (PostHog side) -----
    # per (variant, distinct_id): deepest depth reached, goals, fields, call, junk hints
    person = defaultdict(lambda: defaultdict(lambda: {
        "max_depth": -1, "goals": set(), "focus": set(), "complete": set(),
        "call": False, "terminal": None, "invalid_contact": False, "no_intent": False}))
    field_focus = defaultdict(lambda: defaultdict(int))    # variant -> field -> n
    field_complete = defaultdict(lambda: defaultdict(int))
    for e in ev_rows:
        v = e["variant"]; d = e.get("distinct_id", "?"); ev = e["event"]
        p = person[v][d]
        depth = _depth_of(ev)
        if depth > p["max_depth"]:
            p["max_depth"] = depth
        if ev == "lab_field_focus" and e.get("field"):
            p["focus"].add(e["field"]); field_focus[v][e["field"]] += 1
        if ev == "lab_field_complete" and e.get("field"):
            p["complete"].add(e["field"]); field_complete[v][e["field"]] += 1
            # invalid-contact heuristic on completion props (domain only — no raw PII stored)
            pr = e.get("props", {}) or {}
            dom = (pr.get("email_domain") or "").lower()
            if dom and dom in DISPOSABLE_EMAIL_DOMAINS:
                p["invalid_contact"] = True
        if ev == "lab_micro_conversion" and e.get("goal"):
            p["goals"].add(e["goal"])
        if ev == CALL_CTA_EVENT:
            p["call"] = True
        if ev == "lab_terminal":
            p["terminal"] = e.get("terminal_type")
        pr = e.get("props", {}) or {}
        if str(pr.get("selling_intent", "")).lower() == "no":
            p["no_intent"] = True

    # ----- roll up per variant -----
    out = {}
    all_variants = set(cost) | set(person)
    for v in sorted(all_variants):
        ppl = person.get(v, {})
        n_lp = len(ppl)  # people who reached at least lp_view
        engagement = sum(DEPTH_CREDIT.get(p["max_depth"], 0) for p in ppl.values())
        # micro-conversion value (business-weighted, per unique person-goal)
        goal_counts = defaultdict(int)
        for p in ppl.values():
            for g in p["goals"]:
                goal_counts[g] += 1
        micro_value = sum(GOAL_WEIGHTS.get(g, 0.1) * n for g, n in goal_counts.items())
        # junk: bounced (lp only, depth 0), or explicit No-intent, or invalid contact
        junk = sum(1 for p in ppl.values()
                   if p["max_depth"] <= 0 or p["no_intent"] or p["invalid_contact"])
        reward = W_ENGAGEMENT * engagement + W_MICRO * micro_value - W_JUNK * junk
        c = cost.get(v, {"spend": 0.0, "impressions": 0, "clicks": 0, "fb_leads": 0})
        # quality-adjusted cost per goal
        cpg = {g: (round(c["spend"] / goal_counts[g], 2) if goal_counts[g] else None)
               for g in PII_FIELDS}
        out[v] = {
            "spend": round(c["spend"], 2), "impressions": c["impressions"],
            "clicks": c["clicks"], "fb_leads": c["fb_leads"],
            "people": n_lp, "engagement": round(engagement, 2),
            "goal_counts": dict(goal_counts), "micro_value": round(micro_value, 2),
            "call_intent": sum(1 for p in ppl.values() if p["call"]),
            "junk": junk, "reward": round(reward, 2),
            "cost_per_goal": cpg,
        }

    # ----- PII resistance ranking (Q1), lab-wide -----
    resist = {}
    for f in PII_FIELDS:
        foc = sum(field_focus[v][f] for v in field_focus)
        comp = sum(field_complete[v][f] for v in field_complete)
        resist[f] = {"focus": foc, "complete": comp,
                     "abandon_rate": round(1 - comp / foc, 3) if foc else None}
    ranking = sorted([f for f in PII_FIELDS if resist[f]["abandon_rate"] is not None],
                     key=lambda f: -resist[f]["abandon_rate"])

    return {"variants": out, "pii_resistance": resist,
            "resistance_ranking_most_to_least": ranking,
            "totals": lg.counts()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = compute()
    if args.json:
        print(json.dumps(res, indent=2, default=str)); return
    print("=== FUNNEL LEDGER — REWARD VIEW ===")
    print("ledger rows:", res["totals"])
    if not res["variants"]:
        print("\n(no variant data yet — expected until /lab/ landing pages emit events)")
    print(f"\n{'variant':32} {'ppl':>4} {'eng':>6} {'micro':>6} {'junk':>4} {'reward':>7} {'spend':>8}")
    for v, d in sorted(res["variants"].items(), key=lambda x: -x[1]["reward"]):
        print(f"{v[:32]:32} {d['people']:>4} {d['engagement']:>6} {d['micro_value']:>6} "
              f"{d['junk']:>4} {d['reward']:>7} {d['spend']:>8.2f}")
    print("\n=== PII RESISTANCE (Q1: most -> least resisted) ===")
    print("ranking:", " > ".join(res["resistance_ranking_most_to_least"]) or "(no field data yet)")
    for f, d in res["pii_resistance"].items():
        print(f"  {f:8} focus={d['focus']:>4} complete={d['complete']:>4} abandon_rate={d['abandon_rate']}")


if __name__ == "__main__":
    main()
