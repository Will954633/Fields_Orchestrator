#!/usr/bin/env python3
"""
Engagement Analyst — a weekly Claude-on-Max reasoning pass over the entire
engagement dataset that finds causal relationships and ranks the best
opportunities for building parasocial relationships that convert homeowners.

WHAT IT IS
----------
The attribution tabs (Attr · *) make cause/effect VISIBLE. This closes the loop:
a reasoning layer that reads all of it — the weekly funnel grid, the per-metric
attribution (channel/campaign/content/new-vs-returning), the return + conversion
CHAINS, the "what we did" timeline, and the state of prior findings/experiments —
and produces, every week:

  1. RANKED CAUSAL FINDINGS, each tagged with an EVIDENCE TIER + its confounds.
  2. ICE-ranked OPPORTUNITIES tied to a parasocial mechanism.
  3. EXPERIMENT DESIGNS that would convert the best hypotheses to proof.
  4. A living CAUSAL MAP of the funnel with edge strengths + confidence.

THE DISCIPLINE (why this is trustworthy, not a confabulation engine)
--------------------------------------------------------------------
Claude is very good at spinning a plausible causal story out of noise — which is
exactly the failure mode to guard against. So the prompt FORCES:
  * an evidence tier on every causal claim (proven=A/B > strong=quasi-experiment
    on the what-we-did timeline > suggestive=matched/lead-lag/sequence > hypothesis);
  * a confound list on every claim;
  * a strong preference for PROPOSING AN EXPERIMENT over asserting a cause;
  * explicit low-N flagging (our converter counts are small — prefer continuous
    proxies and Bayesian priors from the literature).

Output is PROPOSE-ONLY: it never launches an ad, ships a deploy, or starts an
experiment. It writes the "Analyst" tab on the Live Leads Tracker + a Telegram
digest; Will decides what to run.

Run:
  python3 scripts/engagement_analyst.py --dry-run     # print, don't write/send
  python3 scripts/engagement_analyst.py
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "backend_enrichment"))

from shared.db import get_client
from job_status import job_run
import telegram_notify
from claude_max_client import make_client
from engagement_funnel_to_sheet import (
    fetch_events, week_list, week_label, build_metrics, build_attribution,
    crm_attribution, what_we_did, build_return_journeys, build_conversion_journeys,
    chain_string, set_env_from_file, LIVE_SPREADSHEET_ID, get_sheets, tab_id,
    ensure_plain_tab, a1, AEST,
)

TAB = "Analyst"
RUNS_COLL = "engagement_analyst_runs"      # history + loop state
EXPERIMENTS_COLL = "engagement_experiments"  # experiment results feed back here
MODEL = "claude-opus-4-8"

# Curated headline metrics to summarise for the analyst (key -> label).
SUMMARY_METRICS = {
    "reach_unique": "unique visitors", "reach_returning": "returning visitors",
    "att_engaged": "engaged sessions 30s+", "vid_plays": "video shown",
    "vid_deep": "video reached 75%", "vid_complete": "video completed",
    "ret_2": "2nd-week returners", "ret_3_4": "3rd-4th week", "ret_5p": "5th+ week regulars",
    "depth_content_read": "market/editorial reads", "depth_multipage": "multi-page sessions",
    "id_new_contacts": "new CRM contacts", "id_home_reco": "home recognised",
    "intent_address_search": "address searches", "intent_ayh_submit": "AYH submissions",
    "intent_offmarket_open": "off-market opens",
}
ATTR_METRICS = ["reach_unique", "att_engaged", "depth_content_read", "vid_plays",
                "intent_ayh_submit", "id_new_contacts"]

# Parasocial priors distilled from Will's "Parasocial Relationships – Science & Playbook"
# doc — the analyst reasons WITH these (as hypotheses and as an interpretive lens).
PARASOCIAL_PRIORS = """
PARASOCIAL PRIORS (Fields' strategy is to build one-sided trust bonds with future sellers):
- RETURN, not raw exposure, predicts the bond (Rubin & McHugh 1987): length of exposure did NOT
  predict PSR strength; social/task attraction and coming back did. So returning-visitor depth and
  content-recurrence matter more than pageview volume.
- Mere-exposure is an inverted-U (Montoya 2017): liking rises then DECLINES past ~36 exposures.
  Rising exposures-per-person is an over-posting WARNING, not a goal.
- Direct address ("you", eye contact) lifts source credibility (Atad & Cohen 2024) — a testable
  on-site/video copy lever.
- Persuasion-knowledge (Friestad & Wright): overt CTAs trigger scepticism and discount prior
  goodwill. Education-to-pitch ratio matters; test CTA weight.
- Warmth THEN competence (Fiske): warmth is judged first and gates trust.
- Self-disclosure DEPTH (not volume) builds PSR; consistency/predictability (appointment content)
  reduces uncertainty and deepens the bond.
- Seller decision is rare, high-trust, single-agent (NAR: 81% contact only ONE agent; reputation
  + honesty dominate; ~11yr median tenure). This is a multi-year top-of-mind farm: the goal is to
  be the one trusted name when the decision finally comes.
- Short-form (reels) drives reach/PSI; long-form + on-site content drives depth/PSR.
"""

SYSTEM_PROMPT = (
    "You are Fields Estate's Engagement Analyst. Fields is a Gold Coast property-intelligence "
    "business (sole operator Will Simpson) building PARASOCIAL relationships with future home "
    "sellers: earn trust with free data/analysis/video so that when a homeowner decides to sell, "
    "Fields is the one name they already trust. You analyse weekly engagement data to find causal "
    "relationships and rank the best opportunities.\n\n"
    "You are RIGOROUS and HONEST. You are also good at inventing plausible causal stories from "
    "noise — you must resist that. Rules:\n"
    "1. Every causal claim carries an EVIDENCE TIER: 'proven' (randomised A/B only), 'strong' "
    "(quasi-experiment — interrupted time series around a dated action in 'what we did', or "
    "difference-in-differences across suburbs, with the confound named), 'suggestive' (matched "
    "cohorts / lead-lag / sequence uplift), or 'hypothesis' (theory + pattern only, untested here).\n"
    "2. Every causal claim lists its CONFOUNDS (what else changed that week; seasonality; selection).\n"
    "3. PREFER proposing an experiment to asserting a cause. If you can't defend a tier above "
    "'hypothesis', say so and design the test.\n"
    "4. Flag LOW-N explicitly (our weekly converters are tens, not thousands). Prefer continuous "
    "proxies (engaged seconds, watch %, return rate) over the rare binary conversion, and use the "
    "parasocial priors as informative Bayesian priors.\n"
    "5. Ground opportunities in a named parasocial mechanism AND leverage broad marketing / "
    "behavioural-science knowledge to spot moves the raw numbers won't name.\n"
    "6. Do NOT recommend anything that runs unattended (no auto ad spend / deploys). Recommendations "
    "are for Will to action.\n\n"
    "Output ONLY valid JSON (no prose, no code fences) matching the requested schema exactly."
)

OUTPUT_SCHEMA = """
Return ONLY this JSON object:
{
  "summary": "2-4 sentence executive read of the week: what moved, what it likely means, the single best opportunity.",
  "findings": [
    {"claim": "one sentence", "evidence_tier": "proven|strong|suggestive|hypothesis",
     "mechanism": "parasocial/behavioural mechanism", "confounds": ["..."],
     "data_ref": "which metric/tab/chain supports it"}
  ],
  "opportunities": [
    {"title": "short", "mechanism": "why it should work (parasocial/domain)",
     "impact": 1-5, "confidence": 1-5, "ease": 1-5,
     "action": "the concrete next move for Will", "evidence_tier": "proven|strong|suggestive|hypothesis"}
  ],
  "experiments": [
    {"hypothesis": "if X then Y because Z", "design": "randomisation unit + arms + what changes",
     "primary_metric": "prefer a continuous proxy", "min_detectable_note": "given low N, what's realistic",
     "est_weeks": 1-12}
  ],
  "causal_map": [
    {"from": "node", "to": "node", "strength": "strong|moderate|weak|unknown",
     "evidence_tier": "proven|strong|suggestive|hypothesis", "note": "short"}
  ],
  "kill_list": [
    {"prior_hypothesis": "...", "reason": "why it's dropped / refuted / stale"}
  ]
}
Rank findings most-important first; opportunities are ranked by ICE afterwards. Keep it tight:
up to ~8 findings, ~8 opportunities, ~6 experiments, ~10 causal edges.
"""


# ---- compact data summary ----------------------------------------------------
def by_label(d, weeks):
    return {week_label(w): (round(d.get(w), 1) if isinstance(d.get(w), float) else d.get(w, 0))
            for w in weeks}


def top_counts(counter, n=8):
    return dict(counter.most_common(n)) if counter else {}


def attr_summary(attr, key, weeks):
    a = attr.get(key, {}) or {}
    out = {}
    ch = a.get("channel", {})
    if ch:
        out["by_channel"] = {v: by_label(bw, weeks) for v, bw in
                             sorted(ch.items(), key=lambda kv: -sum(kv[1].values()))[:6]}
    for dim in ("campaign", "content", "newret"):
        d = a.get(dim, {})
        if d:
            ranked = sorted(d.items(), key=lambda kv: -sum(kv[1].values()))[:6]
            out[f"by_{dim}"] = {v: sum(bw.values()) for v, bw in ranked}
    return out


def build_summary(sm):
    weeks = week_list()
    hours = (datetime.now(timezone.utc).date() - weeks[0]).days * 24 + 48
    events = fetch_events(hours)
    if not events:
        raise RuntimeError("PostHog returned 0 events — cannot analyse (query/creds broken).")
    metrics, sessions, person_weeks = build_metrics(events, weeks)
    for k, d in crm_metrics_safe(sm, weeks).items():
        metrics[k] = d
    attr, pfc = build_attribution(events, weeks, sessions, person_weeks)
    for k, dims in crm_attribution(sm, weeks, pfc).items():
        attr[k] = dims
    whatwedid = what_we_did(sm, weeks)
    returners = [p for p, ws in person_weeks.items() if len(ws) >= 2]
    ret_agg, ret_journeys = build_return_journeys(sm, returners)
    conv_agg, conv_journeys = build_conversion_journeys(sm)

    wlabels = [week_label(w) for w in weeks]
    summary = {
        "weeks_oldest_to_newest": wlabels,
        "metrics": {SUMMARY_METRICS[k]: by_label(metrics.get(k, {}), weeks) for k in SUMMARY_METRICS},
        "attribution": {SUMMARY_METRICS[k]: attr_summary(attr, k, weeks) for k in ATTR_METRICS},
        "what_we_did": {week_label(w): {
            "ad_spend_aud": round(v.get("spend", 0)), "ads_launched": v.get("launched", 0),
            "ads_paused": v.get("paused", 0), "ads_changed": v.get("changed", 0),
            "articles_published": v.get("articles", [])[:6], "fb_posts": v.get("posts", 0),
            "site_changes": v.get("deploys", [])[:6],
        } for w, v in whatwedid.items()},
        "return_cohort": {
            "first_touch_channel": top_counts(ret_agg.get("first_channel")),
            "first_touch_content": top_counts(ret_agg.get("first_content")),
            "return_trigger_content": top_counts(ret_agg.get("trigger")),
            "sample_journeys": [
                {"who": j["who"], "first": j["first"], "weeks": j["wks"], "visits": j["visits"],
                 "chain": chain_string(j["vlist"])[:220]}
                for j in ret_journeys[:15]],
        },
        "conversion_cohort": {
            "by_type": top_counts(conv_agg.get("by_type")),
            "first_touch_channel": top_counts(conv_agg.get("first_channel")),
            "first_touch_content": top_counts(conv_agg.get("first_content")),
            "closing_content": top_counts(conv_agg.get("closing")),
            "median_days_to_convert": _median(conv_agg.get("days", [])),
            "median_touches_to_convert": _median(conv_agg.get("touches", [])),
            "sample_journeys": [
                {"who": j["who"], "conv": j["conv"], "first": j["first"], "days": j["days"],
                 "chain": chain_string(j["vlist"])[:220]}
                for j in conv_journeys[:15]],
        },
    }
    return summary


def crm_metrics_safe(sm, weeks):
    from engagement_funnel_to_sheet import crm_metrics
    return crm_metrics(sm, weeks)


def _median(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


def prior_state(sm):
    last = sm[RUNS_COLL].find_one(sort=[("created_at", -1)])
    state = {"prior_findings": [], "prior_opportunities": [], "prior_experiments": [],
             "experiment_results": []}
    if last and isinstance(last.get("output"), dict):
        o = last["output"]
        state["prior_findings"] = [{"claim": f.get("claim"), "tier": f.get("evidence_tier")}
                                   for f in (o.get("findings") or [])][:12]
        state["prior_opportunities"] = [{"title": op.get("title"), "tier": op.get("evidence_tier")}
                                        for op in (o.get("opportunities") or [])][:12]
        state["prior_experiments"] = [e.get("hypothesis") for e in (o.get("experiments") or [])][:8]
    # experiment results recorded (by Will / an experiment-tracking step) feed the loop
    for e in sm[EXPERIMENTS_COLL].find({}, sort=[("_id", -1)]).limit(20):
        state["experiment_results"].append({
            "hypothesis": e.get("hypothesis"), "status": e.get("status"),
            "result": e.get("result"), "metric": e.get("metric")})
    return state


# ---- the analyst call --------------------------------------------------------
def run_analyst(summary, state):
    prompt = (
        PARASOCIAL_PRIORS
        + "\n\nCAUSAL METHODS AVAILABLE ON THIS DATA (use them to justify a tier):\n"
        "- interrupted time series around a dated action in 'what we did' (STRONG if the confound is named);\n"
        "- difference-in-differences across suburbs (STRONG);\n"
        "- sequence/uplift on the return & conversion chains, matched cohorts, lead-lag (SUGGESTIVE);\n"
        "- a randomised A/B via PostHog feature flags (PROVEN — propose these for the best hypotheses).\n\n"
        "ENGAGEMENT DATA (weeks run oldest→newest in each series):\n"
        + json.dumps(summary, ensure_ascii=False, default=str)
        + "\n\nPRIOR STATE (update/kill these; don't just repeat them — has an experiment resolved?):\n"
        + json.dumps(state, ensure_ascii=False, default=str)
        + "\n\n" + OUTPUT_SCHEMA
    )
    os.environ.pop("ANTHROPIC_BACKEND", None)   # ensure Max, not Vertex/OpenRouter
    os.environ["USE_CLAUDE_MAX"] = "1"
    client = make_client(api_key=os.environ.get("ANTHROPIC_API_KEY", ""), use_max=True)
    for attempt in range(2):
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt if attempt == 0 else
                       prompt + "\n\nYour last reply was not valid JSON. Return ONLY the JSON object."}])
        text = (resp.content[0].text if resp.content else "").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].lstrip("json").strip() if "```" in text[3:] else text.strip("`")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Analyst did not return valid JSON after 2 attempts.")


# ---- rendering ---------------------------------------------------------------
TIER_MARK = {"proven": "✅ PROVEN", "strong": "◆ STRONG", "suggestive": "◇ suggestive",
             "hypothesis": "○ hypothesis"}


def ice(op):
    try:
        return int(op.get("impact", 3)) * int(op.get("confidence", 3)) * int(op.get("ease", 3))
    except (TypeError, ValueError):
        return 0


def render_rows(out, generated):
    opps = sorted(out.get("opportunities", []), key=ice, reverse=True)
    rows = [
        ["▸ ENGAGEMENT ANALYST — causal findings & opportunities"],
        [f"generated {generated} · Claude Opus (Max) · PROPOSE-ONLY — Will actions these"],
        [out.get("summary", "")],
        ["Evidence: ✅ proven=A/B · ◆ strong=quasi-experiment · ◇ suggestive · ○ hypothesis. "
         "Segments/patterns EXPLAIN; only ✅ PROVES. Confounds are listed — read them."],
        [],
        ["▸ TOP OPPORTUNITIES (ranked by ICE = impact × confidence × ease)"],
        ["#", "Opportunity", "ICE", "I", "C", "E", "Mechanism", "Recommended action", "Evidence"],
    ]
    for i, op in enumerate(opps, 1):
        rows.append([i, op.get("title", ""), ice(op), op.get("impact"), op.get("confidence"),
                     op.get("ease"), op.get("mechanism", ""), op.get("action", ""),
                     TIER_MARK.get(op.get("evidence_tier"), op.get("evidence_tier", ""))])
    rows += [[], ["▸ CAUSAL FINDINGS (most important first)"],
             ["Finding", "Evidence", "Mechanism", "Confounds to rule out", "Support"]]
    for f in out.get("findings", []):
        rows.append([f.get("claim", ""), TIER_MARK.get(f.get("evidence_tier"), f.get("evidence_tier", "")),
                     f.get("mechanism", ""), "; ".join(f.get("confounds", []) or []), f.get("data_ref", "")])
    rows += [[], ["▸ EXPERIMENTS TO RUN (turn the best hypotheses into proof)"],
             ["Hypothesis", "Design", "Primary metric", "Note (low-N)", "Est. weeks"]]
    for e in out.get("experiments", []):
        rows.append([e.get("hypothesis", ""), e.get("design", ""), e.get("primary_metric", ""),
                     e.get("min_detectable_note", ""), e.get("est_weeks", "")])
    rows += [[], ["▸ CAUSAL MAP (funnel edges + current confidence)"],
             ["From", "→ To", "Strength", "Evidence", "Note"]]
    for e in out.get("causal_map", []):
        rows.append([e.get("from", ""), e.get("to", ""), e.get("strength", ""),
                     TIER_MARK.get(e.get("evidence_tier"), e.get("evidence_tier", "")), e.get("note", "")])
    kl = out.get("kill_list", [])
    if kl:
        rows += [[], ["▸ KILLED / DROPPED (prior hypotheses no longer supported)"], ["Hypothesis", "Reason"]]
        for k in kl:
            rows.append([k.get("prior_hypothesis", ""), k.get("reason", "")])
    return rows


def write_tab(svc, ssid, rows):
    sid = ensure_plain_tab(svc, ssid, TAB)
    # move Analyst tab to front-right of the attribution block: just after Engagements (index 1)
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "index": 1}, "fields": "index"}}]}).execute()
    svc.spreadsheets().values().clear(spreadsheetId=ssid, range=f"'{TAB}'", body={}).execute()
    svc.spreadsheets().values().update(spreadsheetId=ssid, range=f"'{TAB}'!A1",
                                       valueInputOption="RAW", body={"values": rows}).execute()
    reqs = [{"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
             "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 260}, "fields": "pixelSize"}}]
    for col in (1, 6, 7):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
                     "startIndex": col, "endIndex": col + 1}, "properties": {"pixelSize": 340},
                     "fields": "pixelSize"}})
    reqs.append({"repeatCell": {"range": {"sheetId": sid, "startColumnIndex": 1, "endColumnIndex": 9},
                 "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                 "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}})
    for i, r in enumerate(rows):
        head = r[0] if r else ""
        if isinstance(head, str) and (head.startswith("▸") or head in
                                      ("#", "Finding", "Hypothesis", "From")):
            shade = isinstance(head, str) and head.startswith("▸")
            cell = {"textFormat": {"bold": True}}
            if shade:
                cell["backgroundColor"] = {"red": 0.90, "green": 0.93, "blue": 0.98}
            reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1},
                         "cell": {"userEnteredFormat": cell},
                         "fields": "userEnteredFormat.textFormat.bold" + (
                             ",userEnteredFormat.backgroundColor" if shade else "")}})
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
    return sid


def telegram_digest(out, tab_url):
    opps = sorted(out.get("opportunities", []), key=ice, reverse=True)[:3]
    lines = ["*Engagement Analyst — weekly*", "", out.get("summary", ""), "", "*Top opportunities:*"]
    for i, op in enumerate(opps, 1):
        lines.append(f"{i}. {op.get('title','')} (ICE {ice(op)}, {op.get('evidence_tier','')})")
    exps = out.get("experiments", [])
    if exps:
        lines += ["", f"*Test next:* {exps[0].get('hypothesis','')}"]
    lines += ["", f"Full analysis → {tab_url}"]
    try:
        telegram_notify.send_message("\n".join(lines), parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        print(f"(telegram digest skipped: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()

    set_env_from_file()
    client = get_client()
    sm = client["system_monitor"]
    try:
        with job_run("engagement_analyst", cadence_hours=168,
                     title="Weekly Engagement Analyst (causal findings + opportunities)") as beat:
            summary = build_summary(sm)
            state = prior_state(sm)
            out = run_analyst(summary, state)

            # 7b: an analyst run that produced no findings AND no opportunities is a
            # broken model call, not a quiet week — fail rather than write an empty tab.
            if not out.get("findings") and not out.get("opportunities"):
                raise RuntimeError("Analyst returned no findings or opportunities — treating as failure.")

            generated = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
            beat.detail = (f"{len(out.get('findings', []))} findings, "
                           f"{len(out.get('opportunities', []))} opportunities, "
                           f"{len(out.get('experiments', []))} experiments")
            beat.metrics = {"findings": len(out.get("findings", [])),
                            "opportunities": len(out.get("opportunities", [])),
                            "experiments": len(out.get("experiments", []))}

            if args.dry_run:
                print(json.dumps(out, indent=2, ensure_ascii=False)[:6000])
                return

            # Persist + deliver via Telegram FIRST — these don't depend on the sheet, so a
            # tracker-permission problem can never swallow the week's analysis. The sheet
            # render is a secondary surface; if it fails we still raise (so the heartbeat
            # flags it) but the findings are already saved and sent.
            sm[RUNS_COLL].insert_one({"created_at": datetime.now(timezone.utc).isoformat(),
                                      "generated": generated, "output": out})
            tab_url = f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit"
            if not args.no_telegram:
                telegram_digest(out, tab_url)
            try:
                svc = get_sheets()
                write_tab(svc, args.spreadsheet_id, render_rows(out, generated))
                print(f"Done. '{TAB}' tab written; {beat.detail}.")
            except Exception as e:  # noqa: BLE001
                beat.metrics = dict(beat.metrics or {}, sheet_error=str(e)[:200])
                print(f"WARN: analysis saved to Mongo + sent to Telegram, but the '{TAB}' tab "
                      f"render FAILED: {e}")
                raise RuntimeError(
                    "analysis delivered (Mongo + Telegram) but the tracker sheet write failed — "
                    "likely the floor-plan-processor SA lost Editor access to the Live Leads "
                    f"Tracker: {e}") from e
    finally:
        client.close()


if __name__ == "__main__":
    main()
