#!/usr/bin/env python3
"""
Samantha ad-lifecycle workflow — fast-iteration cull + winner→organic promotion.

Two coded behaviours, run each Samantha session (and by a daily cron guardrail so a
skipped session never silently drops them). See charter.md "Standing workflow — Ad
lifecycle" and CLAUDE.md Rule 3 (ad_decisions) / Rule 7 (self-monitoring).

  1. CULL  (`cull-scan`)  — pause ads that are clear underperformers on their
     objective's *results* metric after >=2 days, using a fair-shot exposure floor
     and a relative test vs the best sibling in the SAME campaign. Before pausing it
     verifies every layer of the ad's Brain-2 record, best-effort backfills the
     missing ones, and ARCHIVES the full raw dossier to `ad_lifecycle_archive` so
     nothing is ever lost (we PAUSE, never delete — a paused ad still enriches
     nightly). Then it logs an `ad_decisions` type=pruning entry and drops a
     structured replacement brief into Will's running doc for Samantha to turn into
     a rigorous proposal.

  2. PROMOTE (`organic-promote`) — at most ONCE per ~month, take a genuinely-winning
     ad and re-run its creative as an ORGANIC page post (single image; carousels post
     their hero card). Editorial-compliance gated. Picks a winner not organically
     reposted in the last 30 days; if none qualifies, posts nothing that week.

  `run`     — do both (what the cron calls, with a job_run heartbeat when --execute).
  `status`  — print cadence state (has this period's promote been done? last cull?).

"results" is objective-dependent — resolved per campaign (leads / link clicks /
post engagements / content views / reach). Detection reads the Brain-2 `ad_profiles`
cache (refreshed 12:00 + 23:00 AEST) + `fb_leads`; only the pause POST and the
organic post hit the live Graph API.

Usage:
  python3 scripts/samantha/ad_lifecycle.py cull-scan            # dry-run report
  python3 scripts/samantha/ad_lifecycle.py cull-scan --execute  # pause + log + archive + brief
  python3 scripts/samantha/ad_lifecycle.py organic-promote --execute
  python3 scripts/samantha/ad_lifecycle.py run --execute        # both (cron entrypoint)
  python3 scripts/samantha/ad_lifecycle.py status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import requests
from dateutil import parser as dateparser

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from src.mongo_client_factory import get_mongo_client, cosmos_retry  # noqa: E402
sys.path.insert(0, os.path.join("/home/fields/Fields_Orchestrator", "scripts"))
from job_status import job_run  # noqa: E402

# ─────────────────────────── tuning constants ───────────────────────────
# CULL — the "significantly underperforming" bar (relative + exposure floor).
CULL_MIN_AGE_HOURS      = 48      # "running for 2 days" — never touch anything younger
CULL_MIN_IMPRESSIONS    = 500     # fair-shot floor: an under-delivered ad is spared
CULL_MIN_SPEND_AUD      = 10.0    # fair-shot floor (a $25/day arm clears this in <1 day)
CULL_LAGGARD_MULT       = 3.0     # cost/result >= 3x the best sibling => laggard
CULL_MIN_SIBLING_RESULTS = 3      # a zero-result ad is only culled if a sibling proved it can convert
CACHE_MAX_STALE_HOURS   = 36      # refuse to auto-pause on ad_profiles data older than this

# PROMOTE — what counts as a genuine winner worth reposting organically.
PROMOTE_COOLDOWN_DAYS   = 30      # max ~1 organic repost per month; per-ad 30d cooldown too
PROMOTE_MAX_AGE_DAYS    = 120     # don't repost an ancient ad
PROMOTE_MIN_RESULTS = {           # minimum lifetime results by result-metric to qualify as a winner
    "leads": 3, "content views": 10, "link clicks": 15,
    "post engagements": 25, "reach": 2500,
}
# Amplify the most business-valuable proven creative first. cost-per-result is only
# comparable WITHIN a tier (a post-engagement ad's cost-per-engagement will always
# undercut a leads ad's cost-per-lead), so we pick the best of the highest tier present.
PROMOTE_TIER = {"leads": 0, "content views": 1, "link clicks": 2, "post engagements": 3, "reach": 4}

# The running doc Samantha shares with Will (Will Notes). Overridable via env.
RUNNING_DOC_ID = os.environ.get(
    "AD_LIFECYCLE_DOC_ID", "14U5UkXBikGRcEkNePk8WLHRtpQzJIDsl6RPHfRho84A")

REPO = "/home/fields/Fields_Orchestrator"
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
FB_BASE = f"https://graph.facebook.com/{API_VERSION}"
TOKEN = os.environ.get("FACEBOOK_ADS_TOKEN", "")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
TAGLINE = "Fields Real Estate: Smarter with data."

# Established learnings — never re-test these (from fb_ads_experimentation_playbook.md).
DO_NOT_RETEST = ("sell-focused copy is dead; lifestyle/aspirational photos are dead; "
                 "OFFSITE_CONVERSIONS (pixel CONTENT_VIEW) is the #1 lever; "
                 "broad targeting + Advantage Audience beats custom audiences")

FORBIDDEN_WORDS = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]
ADVICE_PATTERNS = [
    r"\byou should\b", r"\bnow('?s| is)\s+(a|the)?\s*(good|great|right|perfect)?\s*time\b",
    r"\bconsider (buying|selling)\b", r"\b(prices|values|the market)\s+will\b",
    r"\bwill (rise|fall|increase|drop|climb|crash|soar|plummet)\b",
    r"\bguaranteed\b", r"\bmust (buy|sell|act)\b", r"\bdon'?t (wait|miss)\b",
]

NOW = datetime.now(timezone.utc)


# ─────────────────────────── small helpers ───────────────────────────
def _db():
    return get_mongo_client()["system_monitor"]


def _state(sm):
    return sm["samantha_state"]


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = dateparser.parse(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _metric_block(prof):
    """Prefer lifetime, fall back to last_30d/last_7d for the metric block."""
    for k in ("lifetime", "last_30d", "last_7d"):
        b = prof.get(k)
        if isinstance(b, dict) and b:
            return b
    return {}


def _objective_result(objective, campaign_name, block, leads_count):
    """Return (results:int, result_label:str) for this ad given its objective."""
    obj = (objective or "").upper()
    cname = (campaign_name or "")
    is_leads = ("LEAD" in obj) or cname.strip().lower().startswith("leads:")
    if is_leads:
        return int(leads_count), "leads"
    if "TRAFFIC" in obj or "LINK_CLICK" in obj:
        r = block.get("link_clicks")
        if r is None:
            r = block.get("clicks")
        return int(_f(r)), "link clicks"
    if "ENGAGEMENT" in obj or "POST_ENGAGEMENT" in obj:
        r = block.get("post_engagement", block.get("page_engagement"))
        return int(_f(r)), "post engagements"
    if "SALES" in obj or "CONVERSION" in obj:
        return int(_f(block.get("view_content"))), "content views"
    if "AWARENESS" in obj or "REACH" in obj:
        return int(_f(block.get("reach"))), "reach"
    # default: treat link clicks as the result
    return int(_f(block.get("link_clicks", block.get("clicks")))), "link clicks"


def _lead_counts(sm):
    counts = {}
    for L in sm["fb_leads"].find({}, {"ad_id": 1}):
        aid = L.get("ad_id")
        if aid:
            counts[aid] = counts.get(aid, 0) + 1
    return counts


def _load_ads(sm):
    """Return list of enriched ad dicts from the ad_profiles cache + lead join."""
    leads = _lead_counts(sm)
    ads = []
    newest_collected = None
    for p in sm["ad_profiles"].find({}):
        block = _metric_block(p)
        lc = leads.get(p["_id"], 0)
        results, label = _objective_result(
            p.get("campaign_objective"), p.get("campaign_name"), block, lc)
        spend = _f(block.get("spend_aud", block.get("spend")))
        impr = int(_f(block.get("impressions")))
        created = _parse_dt(p.get("created_time"))
        collected = _parse_dt(p.get("last_collected") or p.get("updated_time"))
        if collected and (newest_collected is None or collected > newest_collected):
            newest_collected = collected
        cr = p.get("creative") or {}
        ads.append({
            "ad_id": p["_id"],
            "name": p.get("name") or p.get("ad_name") or "(unnamed)",
            "status": p.get("effective_status"),
            "campaign_id": p.get("campaign_id"),
            "campaign": p.get("campaign_name"),
            "objective": p.get("campaign_objective"),
            "created": created,
            "age_hours": ((NOW - created).total_seconds() / 3600) if created else None,
            "spend": spend,
            "impressions": impr,
            "leads": lc,
            "results": results,
            "result_label": label,
            "cpr": (spend / results) if results > 0 else None,
            "image_url": cr.get("image_url") or cr.get("thumbnail_url"),
            "body": cr.get("body") or "",
            "format": cr.get("format"),
            "content_type": cr.get("content_type"),
            "is_video": "video" in (str(cr.get("format")) + str(cr.get("content_type"))).lower(),
        })
    return ads, newest_collected


# ─────────────────────────── Brain-2 preservation ───────────────────────────
def _brain2_completeness(sm, ad_id):
    """Which Brain-2 layers hold a record for this ad? (present -> True)."""
    def has(coll, q):
        try:
            return sm[coll].count_documents(q, limit=1) > 0
        except Exception:
            return False
    return {
        "ad_profiles":            has("ad_profiles", {"_id": ad_id}),
        "creative_structured":    has("ad_profiles", {"_id": ad_id, "creative_structured": {"$exists": True}}),
        "semantic_annotation":    has("ad_semantic_annotations", {"ad_id": ad_id}),
        "downstream_attribution": has("ad_downstream", {"ad_id": ad_id}) or has("lead_attribution", {"ad_id": ad_id}),
        "daily_metrics":          has("ad_daily_metrics", {"ad_id": ad_id}),
        "session_behaviour":      has("ad_session_behaviour", {"ad_id": ad_id}) or has("ad_content_affinity", {"ad_id": ad_id}),
        "launch_decision":        has("ad_decisions", {"$or": [
                                      {"ads_affected": ad_id}, {"treatment_ads": ad_id},
                                      {"ads_created": ad_id}, {"ad_id": ad_id}]}),
    }


def _backfill_brain2(execute):
    """Best-effort: run the cheap enrich + a bounded semantic annotate so newly-paused
    ads carry a full record. Heavy attribution/behaviour builders run nightly and a
    paused ad still enriches, so we don't force them inline. Never fatal."""
    if not execute:
        return ["(dry-run: would run ad_creative_enrich.py + ad_annotate.py --limit 8)"]
    out = []
    for cmd, tmo in ((["python3", f"{REPO}/scripts/brain2/ad_creative_enrich.py"], 240),
                     (["python3", f"{REPO}/scripts/brain2/ad_annotate.py", "--limit", "8"], 600)):
        try:
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=tmo)
            out.append(f"{os.path.basename(cmd[1])}: rc={r.returncode} {(r.stdout or r.stderr).strip()[-160:]}")
        except Exception as e:
            out.append(f"{os.path.basename(cmd[1])}: FAILED {e}")
    return out


def _archive_ad(sm, ad, completeness, execute):
    """Permanently archive the full raw dossier so nothing is lost even if the ad is
    later deleted. This is the hard preservation guarantee (raw creative/targeting/
    metrics/leads are irreplaceable; derived layers can be rebuilt from them)."""
    prof = sm["ad_profiles"].find_one({"_id": ad["ad_id"]}) or {}
    ann = sm["ad_semantic_annotations"].find_one({"ad_id": ad["ad_id"]})
    down = sm["ad_downstream"].find_one({"ad_id": ad["ad_id"]})
    lead_attr = sm["lead_attribution"].find_one({"ad_id": ad["ad_id"]})
    leads = list(sm["fb_leads"].find({"ad_id": ad["ad_id"]}))
    daily = list(sm["ad_daily_metrics"].find({"ad_id": ad["ad_id"]}))
    doc = {
        "_id": ad["ad_id"],
        "archived_at": NOW,
        "reason": "cull",
        "completeness_at_cull": completeness,
        "missing_layers": [k for k, v in completeness.items() if not v],
        "ad_profile": prof,
        "semantic_annotation": ann,
        "downstream": down,
        "lead_attribution": lead_attr,
        "fb_leads": leads,
        "ad_daily_metrics": daily,
    }
    if execute:
        cosmos_retry(lambda: sm["ad_lifecycle_archive"].replace_one(
            {"_id": ad["ad_id"]}, doc, upsert=True))
    return doc["missing_layers"]


# ─────────────────────────── live Graph API actions ───────────────────────────
def _confirm_active(ad_id):
    try:
        r = requests.get(f"{FB_BASE}/{ad_id}",
                         params={"fields": "effective_status", "access_token": TOKEN}, timeout=15)
        r.raise_for_status()
        return r.json().get("effective_status") == "ACTIVE"
    except Exception:
        return None  # unknown — caller decides


def _pause_ad(ad_id):
    r = requests.post(f"{FB_BASE}/{ad_id}",
                      data={"access_token": TOKEN, "status": "PAUSED"}, timeout=20)
    r.raise_for_status()
    return True


def _page_token():
    r = requests.get(f"{FB_BASE}/{PAGE_ID}",
                     params={"fields": "access_token", "access_token": TOKEN}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def _post_photo_url(image_url, message):
    tok = _page_token()
    r = requests.post(f"{FB_BASE}/{PAGE_ID}/photos",
                      data={"message": message, "url": image_url, "access_token": tok}, timeout=40)
    r.raise_for_status()
    d = r.json()
    return d.get("post_id") or d.get("id")


# ─────────────────────────── logging / doc / state ───────────────────────────
def _log_ad_decision(sm, decision):
    date_str = NOW.strftime("%Y-%m-%d")
    seq = sm["ad_decisions"].count_documents({"date": date_str}) + 1
    decision.setdefault("_id", f"{date_str}_{seq:03d}")
    decision.setdefault("date", date_str)
    decision.setdefault("created_at", NOW.isoformat())
    cosmos_retry(lambda: sm["ad_decisions"].insert_one(decision))
    return decision["_id"]


def _doc_add(text):
    """Append a paragraph to the top of Will's running doc (best-effort)."""
    try:
        r = subprocess.run(
            ["python3", f"{REPO}/scripts/samantha/running_doc.py", "add",
             "--doc", RUNNING_DOC_ID, "--text", text],
            cwd=REPO, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout or r.stderr).strip()[-200:]
    except Exception as e:
        return False, str(e)


def _replacement_brief(culled, siblings):
    lines = [
        f"⚑ AD REPLACEMENT BRIEF — {NOW.strftime('%Y-%m-%d')} — Samantha to write the proposal",
        f"Campaign: {culled['campaign']}  (objective {culled['objective']})",
        f"CULLED: \"{culled['name']}\" (ad_id {culled['ad_id']}) — {culled['_cull_reason']}",
        (f"  stats: ${culled['spend']:.2f} spend · {culled['results']} {culled['result_label']} · "
         f"cost/result {('$%.2f' % culled['cpr']) if culled['cpr'] else 'n/a (0 results)'} · "
         f"{culled['impressions']} impressions · {(culled['age_hours'] or 0)/24:.1f}d live"),
        "Surviving siblings (what is working in this campaign):",
    ]
    for s in siblings:
        cpr = ("$%.2f" % s["cpr"]) if s["cpr"] else "n/a"
        lines.append(f"  - \"{s['name']}\": {s['results']} {s['result_label']} @ {cpr}/result (${s['spend']:.2f} spend)")
    lines += [
        f"Established learnings — do NOT re-test: {DO_NOT_RETEST}.",
        (f"ACTION (Samantha): write a rigorous, evidence-backed proposal for a NEW test ad to take "
         f"the culled ad's place. It MAY differ substantially from the existing ads so long as it "
         f"serves the same objective ({culled['objective']}). Specify: the one variable being tested, "
         f"the hypothesis, creative direction + copy angle, targeting, daily budget, the results metric, "
         f"and the measurement date. Ground it in the sibling data above + Brain-2 learnings."),
    ]
    return "\n".join(lines)


# ─────────────────────────── CULL ───────────────────────────
def cull_scan(sm, execute):
    ads, newest = _load_ads(sm)
    cache_age_h = ((NOW - newest).total_seconds() / 3600) if newest else None
    active = [a for a in ads if a["status"] == "ACTIVE"]

    print(f"\n=== CULL SCAN {'(EXECUTE)' if execute else '(dry-run)'} — "
          f"{len(active)} active ads · cache age {cache_age_h:.1f}h ===" if cache_age_h is not None
          else f"\n=== CULL SCAN — {len(active)} active ads ===")

    stale_block = execute and cache_age_h is not None and cache_age_h > CACHE_MAX_STALE_HOURS
    if stale_block:
        print(f"  ⚠ ad_profiles cache is {cache_age_h:.1f}h old (> {CACHE_MAX_STALE_HOURS}h) — "
              f"refusing to auto-pause on stale data. Run fb-metrics-collector.py first. Reporting only.")

    # group active ads by campaign
    by_campaign = {}
    for a in active:
        by_campaign.setdefault(a["campaign_id"], []).append(a)

    culled = []
    for cid, sibs in by_campaign.items():
        if len(sibs) < 2:
            continue  # need a comparison + always keep >=1 alive
        with_results = [s for s in sibs if s["results"] > 0 and s["cpr"] is not None]
        best_cpr = min((s["cpr"] for s in with_results), default=None)
        best_results = max((s["results"] for s in sibs), default=0)

        candidates = []
        for a in sibs:
            # gates: age + fair-shot exposure floor
            if (a["age_hours"] or 0) < CULL_MIN_AGE_HOURS:
                continue
            if a["impressions"] < CULL_MIN_IMPRESSIONS or a["spend"] < CULL_MIN_SPEND_AUD:
                continue
            reason = None
            if a["results"] == 0:
                # 0 results while a sibling proved the concept on <= comparable budget
                proved = [s for s in sibs if s is not a and s["results"] >= CULL_MIN_SIBLING_RESULTS
                          and s["spend"] <= a["spend"] * 1.25]
                if proved:
                    top = max(proved, key=lambda s: s["results"])
                    reason = (f"0 {a['result_label']} on ${a['spend']:.2f}/{a['impressions']} impr while "
                              f"sibling \"{top['name']}\" got {top['results']} on ${top['spend']:.2f}")
            elif best_cpr is not None and a["cpr"] is not None and a["cpr"] >= CULL_LAGGARD_MULT * best_cpr:
                reason = (f"cost/result ${a['cpr']:.2f} is {a['cpr']/best_cpr:.1f}x the campaign best "
                          f"(${best_cpr:.2f}) after {(a['age_hours'] or 0)/24:.1f}d")
            if reason:
                a = dict(a); a["_cull_reason"] = reason
                candidates.append(a)

        if not candidates:
            continue
        # keep-alive guard: never pause the last ad; sort worst-first, cap at n_active-1
        candidates.sort(key=lambda a: (a["results"], -(a["cpr"] or 1e9)))
        max_pausable = len(sibs) - 1
        for a in candidates[:max_pausable]:
            culled.append((a, [s for s in sibs if s["ad_id"] != a["ad_id"]]))

    if not culled:
        print("  No ads meet the cull bar (age + exposure floor + clear-laggard vs sibling). Nothing to pause.")
        _record_scan(sm, "ad_cull_scan", execute, {"active": len(active), "candidates": 0})
        return {"culled": [], "active": len(active)}

    done = []
    for a, sibs in culled:
        print(f"\n  ▸ CULL CANDIDATE: \"{a['name']}\" [{a['ad_id']}]  campaign={a['campaign']}")
        print(f"      {a['_cull_reason']}")
        comp = _brain2_completeness(sm, a["ad_id"])
        missing = [k for k, v in comp.items() if not v]
        print(f"      brain2: {'COMPLETE' if not missing else 'missing ' + ', '.join(missing)}")
        if missing:
            for line in _backfill_brain2(execute):
                print(f"        backfill: {line}")
            comp = _brain2_completeness(sm, a["ad_id"])
            missing = [k for k, v in comp.items() if not v]
        archived_missing = _archive_ad(sm, a, comp, execute)
        print(f"      archived raw dossier -> ad_lifecycle_archive "
              f"({'all layers present' if not archived_missing else 'still-pending (nightly rebuild): ' + ', '.join(archived_missing)})")

        if not execute:
            print("      (dry-run) would: pause ad, log ad_decisions[pruning], write replacement brief to doc")
            done.append({"ad_id": a["ad_id"], "name": a["name"], "paused": False, "brain2_pending": archived_missing})
            continue
        if stale_block:
            print("      SKIP pause (stale cache guard). Archived only.")
            done.append({"ad_id": a["ad_id"], "name": a["name"], "paused": False, "reason": "stale_cache"})
            continue

        still = _confirm_active(a["ad_id"])
        if still is False:
            print("      already not ACTIVE live — skipping pause, decision still logged.")
        try:
            if still is not False:
                _pause_ad(a["ad_id"])
                print("      ✔ PAUSED live")
        except Exception as e:
            print(f"      x pause FAILED: {e} — logging decision, leaving live.")

        dec_id = _log_ad_decision(sm, {
            "type": "pruning", "action": "ad_pause",
            "title": f"Cull underperformer: {a['name']}",
            "ads_affected": [a["ad_id"]], "treatment_ads": [a["ad_id"]],
            "campaign": a["campaign"], "objective": a["objective"],
            "hypothesis": "Fast-iteration: clear early laggards free budget for proven siblings.",
            "reasoning": a["_cull_reason"],
            "findings": [
                f"{a['results']} {a['result_label']} · ${a['spend']:.2f} spend · {a['impressions']} impr · "
                f"cost/result {('$%.2f' % a['cpr']) if a['cpr'] else 'n/a'}",
            ],
            "data_snapshot": {
                "ad": {k: a[k] for k in ("ad_id", "name", "results", "result_label", "spend", "impressions", "cpr", "age_hours")},
                "siblings": [{k: s[k] for k in ("name", "results", "cpr", "spend")} for s in sibs],
            },
            "brain2_completeness": _brain2_completeness(sm, a["ad_id"]),
            "brain2_pending_nightly": archived_missing,
            "learning": "Judged on >=2 days with exposure floor; winners show early in this account.",
            "tags": ["facebook", "cull", "fast_iteration", "samantha_ad_lifecycle"],
            "time_aest": (NOW + timedelta(hours=10)).strftime("%H:%M"),
        })
        ok, msg = _doc_add(_replacement_brief(a, sibs))
        print(f"      logged ad_decisions[{dec_id}] · replacement brief -> doc: {'ok' if ok else 'FAILED ' + msg}")
        done.append({"ad_id": a["ad_id"], "name": a["name"], "paused": still is not False,
                     "decision": dec_id, "brief_written": ok, "brain2_pending": archived_missing})

    _record_scan(sm, "ad_cull_scan", execute,
                 {"active": len(active), "candidates": len(culled), "paused": sum(1 for d in done if d.get("paused"))})
    return {"culled": done, "active": len(active)}


# ─────────────────────────── PROMOTE ───────────────────────────
def _compliant(body):
    low = (body or "").lower()
    for w in FORBIDDEN_WORDS:
        if w in low:
            return False, f"forbidden word '{w}'"
    for pat in ADVICE_PATTERNS:
        if re.search(pat, low):
            return False, f"advice/prediction pattern /{pat}/"
    if len(body.strip()) < 30:
        return False, "copy too short for a standalone post"
    return True, ""


def organic_promote(sm, execute):
    print(f"\n=== ORGANIC PROMOTE {'(EXECUTE)' if execute else '(dry-run)'} ===")
    st = _state(sm).find_one({"_id": "ad_organic_promote"}) or {}
    last_promote = _parse_dt(st.get("last_promote_at"))
    if last_promote and (NOW - last_promote).days < PROMOTE_COOLDOWN_DAYS:
        nxt = (last_promote + timedelta(days=PROMOTE_COOLDOWN_DAYS)).date()
        print(f"  Already promoted this period ({last_promote.date()}, period {st.get('last_period')}). "
              f"Next eligible {nxt}. Nothing to do.")
        _record_scan(sm, "ad_organic_promote", execute, {"skipped": "cooldown"}, promote=False)
        return {"promoted": None, "reason": "cooldown"}

    ads, _ = _load_ads(sm)
    # ads reposted organically in the last 30 days are ineligible (per-ad cooldown)
    since = NOW - timedelta(days=PROMOTE_COOLDOWN_DAYS)
    recent = {r["ad_id"] for r in sm["ad_organic_reposts"].find(
        {"posted_at": {"$gte": since.isoformat()}}, {"ad_id": 1})}

    eligible, blocked = [], []
    for a in ads:
        if a["ad_id"] in recent:
            continue
        if not a["image_url"] or not a["body"]:
            continue
        if a["created"] and (NOW - a["created"]).days > PROMOTE_MAX_AGE_DAYS:
            continue
        floor = PROMOTE_MIN_RESULTS.get(a["result_label"], 999999)
        if a["results"] < floor:
            continue
        if a["is_video"]:
            a = dict(a); a["_skip"] = "video creative — organic video repost not supported in v1 (won't post a static thumbnail)"
            blocked.append(a); continue
        ok, why = _compliant(a["body"])
        if not ok:
            a = dict(a); a["_skip"] = f"copy not organic-compliant ({why})"
            blocked.append(a); continue
        eligible.append(dict(a))

    if not eligible:
        print(f"  No eligible winner to repost this week ({len(ads)} ads scanned, "
              f"{len(blocked)} strong-but-ineligible). Posting nothing — as designed.")
        for a in blocked[:6]:
            print(f"    · strong but ineligible: \"{a['name']}\" ({a['results']} {a['result_label']}) — {a['_skip']}")
        _record_scan(sm, "ad_organic_promote", execute, {"eligible": 0, "blocked": len(blocked)}, promote=False)
        return {"promoted": None, "reason": "no_eligible"}

    # Pick the best of the HIGHEST business-value tier present (leads > conversions >
    # traffic > engagement > reach); cost-per-result compared only within that tier.
    eligible.sort(key=lambda a: (PROMOTE_TIER.get(a["result_label"], 9),
                                 a["cpr"] if a["cpr"] else 1e9, -a["results"]))
    winner = eligible[0]
    caption = f"{winner['body'].strip()}\n\n{TAGLINE}"
    print(f"  WINNER: \"{winner['name']}\" [{winner['ad_id']}] — {winner['results']} {winner['result_label']} "
          f"@ {('$%.2f' % winner['cpr']) if winner['cpr'] else 'n/a'}/result")
    print(f"  caption ({len(caption)} chars): {caption[:160]}...")

    if not execute:
        print("  (dry-run) would post winner's hero image + caption to the page as an organic post.")
        _record_scan(sm, "ad_organic_promote", execute, {"eligible": len(eligible), "winner": winner["ad_id"]}, promote=False)
        return {"promoted": None, "reason": "dry_run", "winner": winner["ad_id"]}

    try:
        post_id = _post_photo_url(winner["image_url"], caption)
        print(f"  ✔ PUBLISHED organic post {post_id}")
    except Exception as e:
        print(f"  ✗ publish FAILED: {e}")
        _record_scan(sm, "ad_organic_promote", execute, {"error": str(e)[:200]}, promote=False)
        return {"promoted": None, "reason": "publish_failed", "error": str(e)}

    period = NOW.strftime("%Y-%m")
    cosmos_retry(lambda: sm["ad_organic_reposts"].insert_one({
        "ad_id": winner["ad_id"], "ad_name": winner["name"], "campaign": winner["campaign"],
        "post_id": post_id, "image_url": winner["image_url"], "caption": caption,
        "results_at_repost": winner["results"], "result_label": winner["result_label"],
        "cpr_at_repost": winner["cpr"], "posted_at": NOW.isoformat(), "period": period,
        "source": "ad_lifecycle.py",
    }))
    cosmos_retry(lambda: sm["fb_page_posts"].insert_one({
        "post_id": post_id, "message": caption[:200], "link": None,
        "template_type": "ad_winner_repost", "content_type": "photo",
        "posted_at": NOW.isoformat(), "source": "ad_lifecycle.py", "finalized": True,
        "origin_ad_id": winner["ad_id"],
    }))
    # ad decision (structural/creative reuse)
    _log_ad_decision(sm, {
        "type": "creative_change", "action": "organic_repost",
        "title": f"Promote winner to organic post: {winner['name']}",
        "ads_affected": [winner["ad_id"]],
        "hypothesis": "A paid winner's creative earns organic reach at zero incremental cost (max 1/month).",
        "reasoning": f"Best cost/result qualifier: {winner['results']} {winner['result_label']}.",
        "findings": [f"organic post_id {post_id}"],
        "tags": ["facebook", "organic", "winner_repost", "samantha_ad_lifecycle"],
        "time_aest": (NOW + timedelta(hours=10)).strftime("%H:%M"),
    })
    _record_scan(sm, "ad_organic_promote", execute,
                 {"promoted": winner["ad_id"], "post_id": post_id}, promote=True, post_id=post_id, ad_id=winner["ad_id"])
    return {"promoted": winner["ad_id"], "post_id": post_id}


# ─────────────────────────── state / status ───────────────────────────
def _record_scan(sm, key, execute, extra, promote=None, post_id=None, ad_id=None):
    if not execute:
        return
    upd = {"last_run": NOW.isoformat(), "last_summary": extra}
    if promote is True:
        upd.update({"last_promote_at": NOW.isoformat(), "last_period": NOW.strftime("%Y-%m"),
                    "last_ad_id": ad_id, "last_post_id": post_id})
    cosmos_retry(lambda: _state(sm).update_one({"_id": key}, {"$set": upd}, upsert=True))


def status(sm):
    print("\n=== AD LIFECYCLE STATUS ===")
    for key, label in (("ad_cull_scan", "Cull scan"), ("ad_organic_promote", "Organic promote")):
        d = _state(sm).find_one({"_id": key}) or {}
        lr = _parse_dt(d.get("last_run"))
        age = f"{(NOW - lr).total_seconds()/3600:.1f}h ago" if lr else "never"
        print(f"  {label}: last run {age}  summary={d.get('last_summary')}")
        if key == "ad_organic_promote":
            lp = _parse_dt(d.get("last_promote_at"))
            if lp:
                nxt = (lp + timedelta(days=PROMOTE_COOLDOWN_DAYS)).date()
                print(f"      last publish {lp.date()} (period {d.get('last_period')}, ad {d.get('last_ad_id')}) · next eligible {nxt}")
            else:
                print("      no organic repost published yet")
    ads, newest = _load_ads(sm)
    active = [a for a in ads if a["status"] == "ACTIVE"]
    print(f"  {len(active)} active ads across "
          f"{len({a['campaign_id'] for a in active})} campaigns · "
          f"cache age {((NOW-newest).total_seconds()/3600):.1f}h" if newest else f"  {len(active)} active ads")


# ─────────────────────────── main ───────────────────────────
def _run_both(execute):
    sm = _db()
    r1 = cull_scan(sm, execute)
    r2 = organic_promote(sm, execute)
    return {"cull": r1, "promote": r2}


def main():
    ap = argparse.ArgumentParser(description="Samantha ad-lifecycle: cull + winner→organic promote")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("cull-scan", "organic-promote", "run"):
        p = sub.add_parser(name)
        p.add_argument("--execute", action="store_true", help="take live action (default: dry-run)")
        p.add_argument("--json", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()

    if args.cmd == "status":
        status(_db())
        return 0

    execute = getattr(args, "execute", False)
    if args.cmd == "cull-scan":
        out = cull_scan(_db(), execute)
    elif args.cmd == "organic-promote":
        out = organic_promote(_db(), execute)
    else:  # run — the cron entrypoint; heartbeat only when actually executing
        if execute:
            with job_run("samantha_ad_lifecycle", cadence_hours=24, stale_hours=40,
                         title="Ad lifecycle: cull + winner→organic promote") as beat:
                out = _run_both(execute)
                nc = len(out["cull"].get("culled") or [])
                beat.detail = f"culled {nc} · promote {out['promote'].get('reason') or out['promote'].get('promoted')}"
                beat.metrics = {"culled": nc, "active": out["cull"].get("active")}
        else:
            out = _run_both(execute)

    if getattr(args, "json", False):
        print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
