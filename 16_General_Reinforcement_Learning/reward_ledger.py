#!/usr/bin/env python3
"""
reward_ledger.py — General RL Phase 0: the shared reward ledger + milestone map.

This is the FOUNDATION of the General Reinforcement Learning system (see 00_SCOPING.md).
It is a READ-ONLY analytics layer over data we already have — it touches no website code
and writes only one new collection (`system_monitor.rl_reward_ledger`).

What it computes, each run:
  1. MILESTONE MAP — for every session/user, which milestones on the seller journey they
     reached, and each milestone's PREDICTIVE POWER toward the true reward
     P(true_reward | reached milestone), Bayesian-shrunk to the base rate so tiny-N weights
     aren't wild. This is the self-reweighting reward signal the loop learns from (potential-
     based shaping — weight = measured predictiveness, the built-in Goodhart defence).
  2. CHANNEL / REFERRER / AI-SOURCE ATTRIBUTION of conversion — so the ACQUIRE arm knows
     what traffic converts (the GEO signal lives here: ai_source conversion rates).
  3. COST ATTRIBUTION — FB/Google ad spend (ad_daily_metrics) + organic marginal cost
     (cost_tracking: ai_compute + infra) → cost-per-conversion per pathway. Optimise
     cost-per-identified-seller, not raw conversions (00_SCOPING §5.1).

TRUE REWARD (v1 proxy): `converted` in organic_journeys == an address submit / contact-capture
== an identified-seller *candidate*. The real reward is a contactable seller in lead_worklist
(name+email+phone+intent); the identity-join fix (Phase 0, Gap A) will strengthen this join.
Until then the ledger is honest about coverage: it learns on the joinable population.

Usage:
  python3 reward_ledger.py                 # build + write snapshot + print summary
  python3 reward_ledger.py --dry-run       # compute + print, do NOT write
  python3 reward_ledger.py --window-days 30
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
LEDGER_COLL = "rl_reward_ledger"

# --- milestone map (cold-start ordering; the loop refines weights over time) --------------
# Each: (name, predicate over a rolled-up per-USER record). Ordered roughly by journey depth.
def _user_milestones(u):
    """Given a rolled-up user record, return the set of milestones reached."""
    ms = set()
    ms.add("reached_site")
    if u["sessions"] > 1:
        ms.add("return_visit")
    if u["properties_viewed"] > 0:
        ms.add("viewed_property")
    if u["properties_viewed"] >= 2:
        ms.add("viewed_multiple_properties")
    if u["searches"] > 0:
        ms.add("searched_address")
    if u["search_in_coverage"]:
        ms.add("search_in_coverage")
    # off-market owner-lookup deck trajectory (micro → macro); each auto-earns a
    # predictiveness weight toward the true reward, same as every other milestone.
    ome = u.get("offmarket_events") or set()
    if u.get("offmarket_view"):
        ms.add("offmarket_page_view")
    if u.get("offmarket_cards", 0) >= 2 or "deck_exit" in ome:
        ms.add("offmarket_deck_engaged")      # swiped past the hero/intent-menu
    if "offmarket_menu_sell" in ome:
        ms.add("offmarket_intent_sell")       # chose "see how this home might sell"
    if "offmarket_qualify" in ome:
        ms.add("offmarket_qualified")         # answered the ownership/intent question
    if u["converted"]:
        ms.add("submitted_address")  # == true-reward proxy (contact capture)
    return ms


TRUE_REWARD_MILESTONE = "submitted_address"

# --- HISTORICAL PRIORS (informed cold-start from PostHog full-year history) ----------------
# Each milestone's weight shrinks toward its YEAR-LONG measured conversion rate (not a flat base
# rate), weighted by how much history backs it (`strength` = pseudo-observations). Measured
# 2026-07-29 via PostHog funnels [milestone_event -> analyse_home_address_submit], 365d window.
# This is what "use historical data to inform the weights" means concretely — the thin current
# window updates a sturdy prior instead of starting from scratch. Refresh via refresh_priors().
HISTORICAL_PRIORS = {
    #                  prior_rate  strength  provenance
    "viewed_property":       (0.0095, 40, "posthog_365d n=524"),   # passive browse barely predicts
    "searched_address":      (0.3226, 12, "posthog_365d n=31"),    # THE dominant pre-reward milestone
    "forward_cta_clicked":   (0.02,    6, "posthog_365d n=6 (weak)"),
    # milestones with no direct PostHog event fall back to the base rate (strength 5) below.
}


def _posterior(conv, reached, prior_rate, strength):
    """Beta-binomial posterior: blend the current-window rate with an informed prior.
    strength = pseudo-observations of the prior (bigger = the prior pulls harder)."""
    if reached <= 0 and strength <= 0:
        return prior_rate
    return (conv + strength * prior_rate) / (reached + strength)


def _shrink(conv, reached, base, strength=5.0):
    """Shrink a rate toward the scalar base rate (used for channel attribution)."""
    return _posterior(conv, reached, base, strength) if (reached or strength) else base


def _seller_reward_dids(sm):
    """Distinct_ids that reached the TRUE reward — an identified seller outcome linked back to
    a website journey via posthog_distinct_id. Richer than the organic_journeys `converted`
    proxy: it catches AYH homeowners (property_reports) + off-market qualifiers whose journey
    conversion event wasn't captured. Grows as the identity-join fix (Gap A) accrues data."""
    dids, by_src = set(), {}
    # AYH homeowner analysis → seller intent (owner.posthog_distinct_id)
    for d in sm["property_reports"].find(
            {"owner.posthog_distinct_id": {"$exists": True, "$nin": [None, ""]}},
            {"owner.posthog_distinct_id": 1}):
        v = (d.get("owner") or {}).get("posthog_distinct_id")
        if v:
            dids.add(v); by_src["property_reports"] = by_src.get("property_reports", 0) + 1
    # off-market in-deck seller qualification
    for coll in ("offmarket_qualification",):
        for d in sm[coll].find({"$or": [{"posthog_distinct_id": {"$nin": [None, ""]}},
                                        {"distinct_id": {"$nin": [None, ""]}}]},
                               {"posthog_distinct_id": 1, "distinct_id": 1}):
            v = d.get("posthog_distinct_id") or d.get("distinct_id")
            if v:
                dids.add(v); by_src[coll] = by_src.get(coll, 0) + 1
    return dids, by_src


def _ultimate_reward(sm):
    """The ULTIMATE reward (North Star) — an INBOUND ENQUIRY: a seller who asked to talk to us.
    This is DISTINCT from the near-term reward below. Strategy (Will, 2026-07-29): the public won't
    give phone/email to agents, so we capture the ADDRESS (near-term reward) → direct-mail rapport →
    the seller CALLS us. This ultimate tier measures whether that actually happens, so the system
    validates address-capture against real enquiries instead of declaring victory at the address.
    Expect it sparse for now — that's the point, it's the thing the whole loop is trying to grow.
    Sources: report_review_bookings (booked a call about their report) + genuinely contactable
    seller-intent leads in lead_worklist (real phone AND a seller_intent signal)."""
    names = set(sm.list_collection_names())
    booked = sm["report_review_bookings"].count_documents({}) if "report_review_bookings" in names else 0
    contactable = 0
    for d in sm["lead_worklist"].find({"is_test": {"$ne": True}}, {"phone": 1, "seller_intent": 1}):
        ph = (d.get("phone") or "").strip().replace(" ", "")
        if len(ph) >= 8 and ph not in ("0400000000",) and d.get("seller_intent"):
            contactable += 1
    return {
        "definition": "inbound enquiry — a seller who asked to talk to us (booked call OR contactable seller-intent lead)",
        "booked_calls": booked,
        "contactable_seller_leads": contactable,
        "note": ("Distinct from the near-term address reward. Sparse by design — the address→mail→"
                 "rapport→call strategy is what grows this. booked_calls and contactable may overlap; "
                 "treat as the North-Star validation + weekly sanity-check, not a dense learning signal."),
    }


def _form_lead_rewards(sm):
    """Facebook Instant-Form SELLER leads as a first-class reward tier. A completed seller form
    carrying name/email/phone/intent IS an identified seller — but these live in fb_leads (filled
    on FB, no website session, no posthog_distinct_id), so they never touch organic_journeys and
    were invisible to this ledger. Surfaced here so the ads cycle + conductor credit the ads that
    drove them; kept SEPARATE from the milestone/base-rate math (different population — folding
    them in would distort predictiveness). Split GC-served (real) vs out-of-market copy-test."""
    import ast
    # Seller-intent SIGNAL fields — the reliable discriminator. A seller-ish form NAME alone is
    # not enough (e.g. the "Independent Listing Analysis" carousel routes to a Buyer Brief form),
    # so we require the submission itself to carry a selling-intent / property-address field.
    SELLER_SIGNAL_FIELDS = ("selling_intent", "selling_timeframe", "property_address",
                            "sell_timeframe", "thinking_of_selling")

    def parse_fields(l):
        f = l.get("fields")
        if isinstance(f, str):
            try:
                f = ast.literal_eval(f)
            except Exception:
                f = {}
        return f or {}

    real_seller, test_seller = [], []
    for l in sm["fb_leads"].find({}):
        f = parse_fields(l)
        if not any(k in f for k in SELLER_SIGNAL_FIELDS):
            continue
        is_test = bool(l.get("test_market")) or str(l.get("is_test")).lower() in ("true", "1")
        rec = {"ad_id": l.get("ad_id"), "ad_name": l.get("ad_name"),
               "campaign": l.get("campaign_name"), "created_time": l.get("created_time"),
               "name": f.get("full_name"), "email": f.get("email"),
               "phone": f.get("phone_number"),
               "intent": f.get("selling_intent") or f.get("selling_timeframe"),
               "address": f.get("property_address")}
        (test_seller if is_test else real_seller).append(rec)

    def _yes(recs):
        return sum(1 for r in recs if str(r.get("intent") or "").lower() in
                   ("yes", "y", "true", "now", "soon", "1_3_months", "3_6_months"))
    return {
        "definition": ("FB Instant-Form seller leads = identified sellers (name/email/phone/intent). "
                       "Separate reward tier, NOT in milestone math."),
        "gc_served": {"count": len(real_seller), "intent_yes": _yes(real_seller),
                      "leads": real_seller[:20]},
        "out_of_market_test": {"count": len(test_seller), "intent_yes": _yes(test_seller)},
        "note": ("gc_served = the true paid seller reward from Instant-Form ads; out_of_market_test = "
                 "contactable but outside GC (copy discovery), excluded from GC CPL. No distinct_id on "
                 "these (form filled on FB) — bind future site visits via a lead token on the emailed "
                 "link (website change, not implemented here)."),
    }


def build(window_days=None, dry_run=False):
    c = get_client()
    sm = c["system_monitor"]
    journeys = list(sm["organic_journeys"].find({}))

    # optional window filter on computed t_last
    def _dt(s):
        try:
            return datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None

    if window_days:
        cut = NOW.timestamp() - window_days * 86400
        journeys = [j for j in journeys if (_dt(j.get("t_last")) or NOW).timestamp() >= cut]

    journeys = [j for j in journeys if not j.get("is_bot")]  # defensive
    n_sessions = len(journeys)

    # roll sessions up to users (distinct_id) ------------------------------------------------
    users = defaultdict(lambda: {"sessions": 0, "properties_viewed": 0, "searches": 0,
                                 "search_in_coverage": False, "converted": False,
                                 "channels": set(), "ai_sources": set(), "referrers": set(),
                                 "offmarket_view": False, "offmarket_events": set(),
                                 "offmarket_cards": 0})
    for j in journeys:
        u = users[j.get("distinct_id")]
        u["sessions"] += 1
        u["properties_viewed"] += len(j.get("properties_viewed") or [])
        u["searches"] += int(j.get("n_searches") or 0)
        if j.get("searched_address_category") and j["searched_address_category"] != "out_of_coverage":
            u["search_in_coverage"] = True
        if j.get("converted"):
            u["converted"] = True
        # off-market deck trajectory (from organic_journey_build)
        if j.get("is_offmarket"):
            u["offmarket_view"] = True
        u["offmarket_events"] |= set(j.get("offmarket_events") or [])
        u["offmarket_cards"] = max(u["offmarket_cards"], int(j.get("offmarket_card_views") or 0))
        if j.get("channel"):
            u["channels"].add(j["channel"])
        if j.get("ai_source"):
            u["ai_sources"].add(j["ai_source"])
        if j.get("referring_domain"):
            u["referrers"].add(j["referring_domain"])

    # TRUE-reward strengthening: union the journey `converted` proxy with real seller outcomes
    # linked by distinct_id (property_reports homeowners + off-market qualifiers). This makes the
    # reward truer (an identified seller) AND denser, without destabilising — it only ADDS rewards.
    seller_dids, seller_src = _seller_reward_dids(sm)
    n_journey_conv = sum(1 for u in users.values() if u["converted"])
    n_seller_linked = 0
    for did, u in users.items():
        if did in seller_dids:
            if not u["converted"]:
                n_seller_linked += 1
            u["converted"] = True  # journey-converted OR linked to a real seller outcome

    n_users = len(users)
    n_conv = sum(1 for u in users.values() if u["converted"])
    base_rate = (n_conv / n_users) if n_users else 0.0

    # milestone predictiveness ---------------------------------------------------------------
    reached = defaultdict(int)
    reached_and_conv = defaultdict(int)
    for u in users.values():
        ms = _user_milestones(u)
        conv = u["converted"]
        for m in ms:
            reached[m] += 1
            if conv:
                reached_and_conv[m] += 1

    milestones = []
    for m in ["reached_site", "return_visit", "viewed_property", "viewed_multiple_properties",
              "searched_address", "search_in_coverage",
              "offmarket_page_view", "offmarket_deck_engaged", "offmarket_intent_sell",
              "offmarket_qualified", "submitted_address"]:
        r = reached[m]
        cvt = reached_and_conv[m]
        # informed prior from full-year history where we have it; else shrink to base rate
        if m in HISTORICAL_PRIORS:
            prate, pstr, prov = HISTORICAL_PRIORS[m]
        else:
            prate, pstr, prov = base_rate, 5.0, "base_rate (no direct history)"
        pred = _posterior(cvt, r, prate, pstr)
        milestones.append({
            "milestone": m,
            "reached_users": r,
            "converted_users": cvt,
            "predictiveness": round(pred, 4),          # P(true_reward | reached M), prior-informed
            "prior": {"rate": round(prate, 4), "strength": pstr, "source": prov},
            "lift_vs_base": round(pred / base_rate, 2) if base_rate else None,
            "confidence_n": r,                          # current-window sample behind the update
            "is_true_reward": (m == TRUE_REWARD_MILESTONE),
        })

    # channel / ai_source attribution --------------------------------------------------------
    def _attr(keyfn):
        agg = defaultdict(lambda: {"sessions": 0, "users": set(), "conv_users": set()})
        for j in journeys:
            k = keyfn(j)
            if not k:
                continue
            a = agg[k]
            a["sessions"] += 1
            did = j.get("distinct_id")
            a["users"].add(did)
            if users[did]["converted"]:
                a["conv_users"].add(did)
        out = []
        for k, a in agg.items():
            uu, cc = len(a["users"]), len(a["conv_users"])
            out.append({"key": k, "sessions": a["sessions"], "users": uu, "conversions": cc,
                        "conv_rate": round(_shrink(cc, uu, base_rate), 4), "raw_conv_rate": round(cc / uu, 4) if uu else 0})
        return sorted(out, key=lambda x: -x["conversions"])

    channels = _attr(lambda j: j.get("channel"))
    ai_sources = _attr(lambda j: j.get("ai_source"))
    referrers = _attr(lambda j: (j.get("referring_domain") or "").lower())[:15]

    # cost attribution -----------------------------------------------------------------------
    dates = [str(j.get("t_last"))[:10] for j in journeys if j.get("t_last")]
    dmin, dmax = (min(dates), max(dates)) if dates else (None, None)
    # split FB spend into GC-served vs out-of-market (SEQ ex-GC copy discovery). OOM spend must
    # NOT be in the GC cost-per-seller numerator. Marker = 'ex-gc' token in campaign name (mirrors
    # ads_signal.is_oom). Requires an ad_id→campaign join (ad_daily_metrics alone has no campaign).
    _prof = {p.get("ad_id"): (p.get("campaign_name") or "")
             for p in sm["ad_profiles"].find({}, {"ad_id": 1, "campaign_name": 1})}
    def _oom(cn):
        cn = (cn or "").lower()
        return "ex-gc" in cn or "ex gc" in cn
    gc_spend = oom_spend = 0.0
    if dmin:
        for d in sm["ad_daily_metrics"].find({"date": {"$gte": dmin, "$lte": dmax}}):
            sp = float(d.get("spend_aud") or 0)
            cn = _prof.get(d.get("ad_id")) or d.get("campaign_name")
            if _oom(cn):
                oom_spend += sp
            else:
                gc_spend += sp
    fb_spend = gc_spend + oom_spend
    ai_compute = infra = 0.0
    if dmin:
        for d in sm["cost_tracking"].find({"date": {"$gte": dmin, "$lte": dmax}}):
            bc = d.get("by_category") or {}
            ai_compute += float(bc.get("ai_compute") or 0)
            infra += float(bc.get("infrastructure") or 0)

    # paid vs organic conversions — read from all_conversions, which captures EVERY-channel
    # address submit (organic_journeys is non-paid by design, so counting paid there was always
    # 0; that manufactured the false "∞ paid / every seller organic" result). all_conversions
    # now carries is_paid + ad_id + utm_campaign for paid sessions (organic_journey_build 1b).
    ac_docs = list(sm["all_conversions"].find({}, {"is_paid": 1, "channel": 1, "ad_id": 1,
                                                   "utm_campaign": 1, "submitted_at": 1,
                                                   "contact_captured": 1}))
    if window_days:
        cutstamp = (NOW.timestamp() - window_days * 86400)
        ac_docs = [d for d in ac_docs if (_dt(d.get("submitted_at")) or NOW).timestamp() >= cutstamp]
    def _is_paid(d):
        return bool(d.get("is_paid")) or str(d.get("channel") or "").startswith("Paid")
    paid_conv = sum(1 for d in ac_docs if _is_paid(d))
    organic_conv = sum(1 for d in ac_docs if not _is_paid(d))
    # per-ad / per-campaign paid conversion breakdown (the ads sensor joins on this)
    paid_by_ad = defaultdict(int); paid_by_campaign = defaultdict(int)
    for d in ac_docs:
        if _is_paid(d):
            if d.get("ad_id"):
                paid_by_ad[d["ad_id"]] += 1
            paid_by_campaign[d.get("utm_campaign") or "(untagged)"] += 1
    cost_summary = {
        "window": {"from": dmin, "to": dmax},
        "fb_ad_spend_aud": round(fb_spend, 2),
        "gc_ad_spend_aud": round(gc_spend, 2),        # GC-served spend (the CPL numerator)
        "oom_test_spend_aud": round(oom_spend, 2),    # out-of-market (SEQ ex-GC) copy discovery, excluded
        "ai_compute_aud": round(ai_compute, 2),
        "infra_aud": round(infra, 2),
        "paid_conversions": paid_conv,
        "organic_conversions": organic_conv,
        "paid_conversions_by_ad": dict(paid_by_ad),
        "paid_conversions_by_campaign": dict(paid_by_campaign),
        # TRUE GC cost-per-paid-conversion: GC-served spend ÷ GC paid conversions (OOM removed).
        "cost_per_paid_conversion_aud": round(gc_spend / paid_conv, 2) if paid_conv else None,
        "cost_per_paid_conversion_incl_oom_aud": round(fb_spend / paid_conv, 2) if paid_conv else None,
        "note": ("Paid vs organic read from all_conversions (every-channel address submits) — NOT "
                 "organic_journeys, which is non-paid by design. cost_per_paid_conversion uses "
                 "GC-served spend only (out-of-market SEQ ex-GC copy-test spend excluded); the "
                 "incl_oom variant is kept for reference. Organic conversions carry ~$0 marginal cost."),
    }

    snapshot = {
        "kind": "reward_ledger_snapshot",
        "computed_at": NOW.isoformat(),
        "window": {"from": dmin, "to": dmax, "window_days": window_days},
        "n_sessions": n_sessions, "n_users": n_users, "n_conversions": n_conv,
        "base_conversion_rate": round(base_rate, 4),
        # NEAR-TERM reward (dense, learnable) = ADDRESS captured / home-analysis engaged. This is the
        # achievable target Will's strategy is built on (address → direct-mail rapport → inbound call);
        # it is NOT phone/email capture (the public won't give that). The system learns on this signal.
        "true_reward": {
            "tier": "near-term (address captured → mail channel opens)",
            "definition": ("address captured = journey `converted` (address submit) UNION a real "
                           "seller outcome linked by distinct_id (property_reports homeowners + "
                           "off-market qualifiers). NOT phone/email — see ultimate_reward for the North Star."),
            "journey_converted": n_journey_conv,
            "seller_linked_extra": n_seller_linked,   # true sellers the proxy alone missed
            "total_true_rewards": n_conv,
            "linked_sources": seller_src,
            "note": ("This is the DENSE learnable reward and it's aligned with strategy — capturing an "
                     "address unlocks the mail-out channel. Validate it against `ultimate_reward` "
                     "(actual inbound enquiries): if addresses never convert to calls, that's the signal "
                     "to change the mail/rapport mechanism, not to chase phone/email head-on."),
        },
        # ULTIMATE reward (sparse, North Star) = an inbound enquiry (a seller who asked to talk to us).
        "ultimate_reward": _ultimate_reward(sm),
        # FB Instant-Form seller leads — identified sellers that live outside organic_journeys.
        "form_lead_rewards": _form_lead_rewards(sm),
        "milestones": milestones,
        "channels": channels,
        "ai_sources": ai_sources,
        "top_referrers": referrers,
        "cost_summary": cost_summary,
        "coverage_note": (
            "Predictiveness + attribution are over the joinable population in organic_journeys "
            f"(~{n_users} users). Anonymous non-journey traffic and FB-ad-only leads are not yet "
            "joined (identity-join fix pending, 00_SCOPING §10.3 Gap A)."),
    }

    if not dry_run:
        coll = sm[LEDGER_COLL]
        coll.insert_one(dict(snapshot))                       # history
        coll.replace_one({"_id": "latest"}, {**snapshot, "_id": "latest"}, upsert=True)  # fast read

    return snapshot


def _print_summary(s):
    print(f"\n=== RL REWARD LEDGER  ({s['window']['from']} → {s['window']['to']}) ===")
    print(f"users={s['n_users']}  sessions={s['n_sessions']}  conversions={s['n_conversions']}  "
          f"base_rate={s['base_conversion_rate']:.3f}")
    print("\nMILESTONE MAP (predictiveness = P(reward | reached), history-informed prior + current):")
    print(f"  {'milestone':<28}{'reached':>8}{'conv':>6}{'pred':>8}{'lift':>7}")
    for m in s["milestones"]:
        star = " ★reward" if m["is_true_reward"] else ""
        lift = f"{m['lift_vs_base']:.2f}" if m["lift_vs_base"] is not None else "-"
        print(f"  {m['milestone']:<28}{m['reached_users']:>8}{m['converted_users']:>6}"
              f"{m['predictiveness']:>8.3f}{lift:>7}{star}")
    print("\nCHANNEL attribution (conv_rate shrunk):")
    for ch in s["channels"]:
        print(f"  {ch['key']:<20} users={ch['users']:>4}  conv={ch['conversions']:>3}  "
              f"rate={ch['conv_rate']:.3f} (raw {ch['raw_conv_rate']:.3f})")
    print("\nAI-SOURCE attribution (the GEO signal):")
    for a in s["ai_sources"] or [{"key": "(none captured)", "users": 0, "conversions": 0, "conv_rate": 0, "raw_conv_rate": 0}]:
        print(f"  {a['key']:<20} users={a['users']:>4}  conv={a['conversions']:>3}  rate={a['conv_rate']:.3f}")
    cs = s["cost_summary"]
    print(f"\nCOST: FB spend ${cs['fb_ad_spend_aud']} (GC ${cs['gc_ad_spend_aud']} + OOM "
          f"${cs['oom_test_spend_aud']}) | organic conv {cs['organic_conversions']} (~$0) | "
          f"paid conv {cs['paid_conversions']} @ GC cost/conv ${cs['cost_per_paid_conversion_aud']} "
          f"(incl-OOM ${cs['cost_per_paid_conversion_incl_oom_aud']})")
    print(f"\n{s['coverage_note']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--window-days", type=int, default=None)
    args = ap.parse_args()

    try:
        from job_status import job_run
    except Exception:
        job_run = None

    if job_run and not args.dry_run:
        with job_run("rl_reward_ledger", cadence_hours=168,
                     title="General RL — reward ledger + milestone map") as beat:
            s = build(window_days=args.window_days, dry_run=False)
            _print_summary(s)
            beat.detail = (f"{s['n_users']} users, {s['n_conversions']} conv, "
                           f"{len(s['milestones'])} milestones weighted")
            beat.metrics = {"users": s["n_users"], "conversions": s["n_conversions"],
                            "base_rate": s["base_conversion_rate"]}
    else:
        s = build(window_days=args.window_days, dry_run=args.dry_run)
        _print_summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
