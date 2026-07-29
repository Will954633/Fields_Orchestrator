#!/usr/bin/env python3
"""
cycle_state.py — deterministic state snapshot for the Off-Market RL cycle.

The `checkpoint.py` analog for this initiative: gathers the DB-side facts a cycle
needs (corpus size, coverage by suburb, scraper output, page eligibility) into a
JSON + markdown summary, so each Claude cycle starts from the same measured baseline
rather than re-deriving it. PostHog behaviour (card funnel, dwell, deck_exit,
milestones) is pulled by the cycle agent itself (it has posthog access); this script
owns the cheap, deterministic DB truth.

Usage: python3 cycle_state.py [--json]
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db  # noqa: E402

# The rollout band (house-dominant southern-to-central first) + the 3 core suburbs.
CORE = ["robina", "burleigh_waters", "varsity_lakes"]
ROLLOUT = ["nerang", "mudgeeraba", "highland_park", "worongary", "reedy_creek",
           "palm_beach", "burleigh_heads", "merrimac", "carrara", "miami",
           "mermaid_waters", "elanora", "tallai", "bonogin"]

ELIGIBLE = {"url_slug": {"$exists": True, "$ne": None},
            "enriched_data.transactions.0": {"$exists": True},
            "listing_status": {"$nin": ["for_sale", "under_contract"]}}


def suburb_counts(db, name):
    c = db[name]
    try:
        total = c.estimated_document_count()
    except Exception:
        total = None
    eligible = c.count_documents(ELIGIBLE)
    minted = c.count_documents({"offmarket_coverage": {"$exists": True}})
    return {"suburb": name, "addresses": total, "offmarket_eligible": eligible,
            "minted_by_scraper": minted}


def scorecard(sys_db, corpus_total):
    """Persist a comparable metric snapshot each run + return the delta vs the previous one,
    so a cycle can answer 'did engagement move?' instead of re-deriving from prose."""
    now = datetime.now(timezone.utc).isoformat()
    # off-market milestone lifts from the shared reward ledger (nightly-computed)
    led = sys_db["rl_reward_ledger"].find_one(sort=[("computed_at", -1)]) or {}
    lifts = {m["milestone"]: m.get("lift_vs_base")
             for m in (led.get("milestones") or []) if "offmarket" in m.get("milestone", "")}
    card = {"at": now, "corpus_eligible": corpus_total, "offmarket_milestone_lifts": lifts}
    prev = sys_db["rl_offmarket_scorecard"].find_one(sort=[("at", -1)])
    sys_db["rl_offmarket_scorecard"].insert_one(dict(card))
    diff = {}
    if prev:
        for k, v in lifts.items():
            pv = (prev.get("offmarket_milestone_lifts") or {}).get(k)
            if isinstance(v, (int, float)) and isinstance(pv, (int, float)):
                diff[k] = round(v - pv, 3)
        diff["corpus_eligible"] = corpus_total - (prev.get("corpus_eligible") or 0)
    return card, diff, (prev or {}).get("at")


def main():
    db = get_gold_coast_db()
    now = datetime.now(timezone.utc).isoformat()
    core = [suburb_counts(db, s) for s in CORE]
    rollout = []
    for s in ROLLOUT:
        try:
            rollout.append(suburb_counts(db, s))
        except Exception as e:
            rollout.append({"suburb": s, "error": str(e)[:80]})
    core_elig = sum(x["offmarket_eligible"] for x in core)
    rollout_elig = sum(x.get("offmarket_eligible", 0) for x in rollout)
    rollout_minted = sum(x.get("minted_by_scraper", 0) for x in rollout)

    state = {
        "generated_at": now,
        "corpus": {
            "core_eligible": core_elig,
            "rollout_eligible": rollout_elig,
            "rollout_minted_by_scraper": rollout_minted,
            "total_eligible": core_elig + rollout_elig,
        },
        "core": core,
        "rollout": rollout,
    }

    if "--json" in sys.argv:
        print(json.dumps(state, indent=2))
        return state

    print(f"# Off-Market RL — cycle state @ {now}\n")
    print(f"CORPUS: {state['corpus']['total_eligible']:,} off-market-eligible pages "
          f"(core {core_elig:,} + rollout {rollout_elig:,}); "
          f"scraper-minted (rollout) {rollout_minted:,}\n")
    print(f"{'suburb':20}{'addresses':>11}{'off-mkt elig':>14}{'scraper-minted':>16}")
    for row in core + rollout:
        if "error" in row:
            print(f"{row['suburb']:20}{'ERR: '+row['error']:>41}")
            continue
        tag = " [core]" if row["suburb"] in CORE else ""
        print(f"{row['suburb']:20}{(row['addresses'] or 0):>11,}"
              f"{row['offmarket_eligible']:>14,}{row['minted_by_scraper']:>16,}{tag}")

    # persisted scorecard + delta vs the previous cycle (did engagement move?)
    try:
        from shared.db import get_client
        card, diff, prev_at = scorecard(get_client()["system_monitor"],
                                        state["corpus"]["total_eligible"])
        print(f"\nSCORECARD (off-market milestone lifts vs base): {card['offmarket_milestone_lifts']}")
        if prev_at:
            print(f"  Δ vs previous cycle ({prev_at}): {diff}")
        else:
            print("  (first scorecard — no prior to diff)")
        state["scorecard"] = card
        state["scorecard_delta"] = diff
    except Exception as e:
        print(f"\n(scorecard skipped: {e})")
    return state


if __name__ == "__main__":
    main()
