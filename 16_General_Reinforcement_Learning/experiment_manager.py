#!/usr/bin/env python3
"""
experiment_manager.py — the machinery the ONSITE CYCLE (Claude) drives to run dynamic-content
experiments on real users. This REPLACES the old hand-authored personalization_policy table:
Claude hypothesizes an experiment, defines the arms, and this registers it as a PostHog
multivariate feature flag + a registry doc. The serving slot renders each visitor their assigned
variant; arm_grader.py measures which lifted the target milestone; Claude reads the grade and iterates.

Nothing renders to users until the MASTER KILL-SWITCH flag `genrl_personalization_v1` is ON
(Will's gated decision, after the perf gate). While OFF, proposing/serving experiments is safe and
inert — flags assign silently, the slot renders nothing. So the cycle may propose/serve/grade/retire
freely (Tier-1); only flipping the master switch ON is Tier-3.

Registry: system_monitor.rl_onsite_experiments. Flags: PostHog multivariate (equal rollout).

CLI (the cycle calls these):
  experiment_manager.py propose --surface /analyse-your-home --target from_market_metrics \
     --hypothesis "..." --arms '[{"variant":"control"},{"variant":"bridge","content":{"headline":"...","sub":"...","cta_label":"...","cta_href":"/analyse-your-home"}}]'
  experiment_manager.py serve   --exp <id>      # create the PostHog flag, status->serving
  experiment_manager.py list    [--serving]     # (serving endpoint + cycle read this)
  experiment_manager.py grade                   # pull arm_grader verdicts onto experiments
  experiment_manager.py retire  --exp <id>      # disable flag, status->retired
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_onsite_experiments"
MASTER_KILL_SWITCH = "genrl_personalization_v1"
# 2026-08-13: /off-market and /property added by the onsite cycle. The original two surfaces were
# both ~100% Facebook-fed and fell to ~2 users/week when ads paused 2026-07-30, so every experiment
# registered against them is unreadable. Organic traffic lands on the deck (324 of 545 google-referred
# users / 28d) and the property page (162). NOTE: registering a surface here does NOT mount it —
# PersonalizationSlot is only rendered by AnalyseYourHomePage.tsx and DecisionFeedV3Page.tsx, so an
# experiment on a new surface stays STAGED until the slot is mounted there (REC-onsite-001).
SURFACES = ("/analyse-your-home", "/for-sale-v3", "/off-market", "/property")


def _ph(method, path, body=None):
    pid = os.environ["POSTHOG_PROJECT_ID"]
    key = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ["POSTHOG_PERSONAL_API_KEY"]
    url = f"https://us.posthog.com/api/projects/{pid}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _coll():
    return get_client()["system_monitor"][COLL]


def _next_id(surface):
    slug = surface.strip("/").replace("/", "_").replace("-", "")[:16]
    n = _coll().count_documents({"surface": surface}) + 1
    return f"onsite_exp_{slug}_{n}"


def propose(surface, target, hypothesis, arms):
    assert surface in SURFACES, f"surface must be one of {SURFACES}"
    variants = [a["variant"] for a in arms]
    assert "control" in variants and len(variants) >= 2, "need a 'control' arm + >=1 test arm"
    exp_id = _next_id(surface)
    doc = {"_id": exp_id, "surface": surface, "target": target or "all",
           "hypothesis": hypothesis, "arms": arms, "flag_key": exp_id,
           "target_milestone": "searched_address", "status": "proposed",
           "created_at": NOW.isoformat(), "created_by": "onsite_cycle"}
    _coll().insert_one(doc)
    print(f"proposed {exp_id} on {surface} · {len(variants)} arms · status=proposed (not serving yet)")
    return exp_id


def serve(exp_id):
    doc = _coll().find_one({"_id": exp_id})
    assert doc, f"no experiment {exp_id}"
    variants = [a["variant"] for a in doc["arms"]]
    pct = max(1, 100 // len(variants))
    roll = [{"key": v, "rollout_percentage": (100 - pct * (len(variants) - 1)) if i == 0 else pct}
            for i, v in enumerate(variants)]
    flag = {"key": doc["flag_key"], "name": f"[GenRL onsite] {doc['hypothesis'][:60]}",
            "active": True, "filters": {"multivariate": {"variants": roll}, "groups": [{"rollout_percentage": 100}]}}
    # Create the flag. Only mark 'serving' if the flag actually exists afterward — otherwise a
    # 403 (missing feature_flag:write scope) would leave a phantom 'serving' experiment with no flag.
    created = False
    try:
        _ph("POST", "feature_flags/", flag)
        created = True
    except Exception as e:
        existing = next((f for f in _ph("GET", "feature_flags/?limit=200").get("results", [])
                         if f["key"] == doc["flag_key"]), None) if "GET" else None
        if existing:  # already exists → activate
            try:
                _ph("PATCH", f"feature_flags/{existing['id']}/", {"active": True, "filters": flag["filters"]})
                created = True
            except Exception:
                pass
        if not created:
            _coll().update_one({"_id": exp_id}, {"$set": {"status": "serve_failed",
                               "serve_error": str(e)[:140]}})
            print(f"SERVE FAILED for {exp_id}: {str(e)[:100]} — flag NOT created. "
                  f"(Likely the PostHog Personal API Key lacks feature_flag:write scope.) Left as serve_failed.")
            return False
    _coll().update_one({"_id": exp_id}, {"$set": {"status": "serving", "served_at": NOW.isoformat()}})
    print(f"serving {exp_id} — flag '{doc['flag_key']}' live. Renders to users only when "
          f"master kill-switch '{MASTER_KILL_SWITCH}' is ON.")
    return True


def grade():
    grades = get_client()["system_monitor"]["rl_arm_grades"].find_one({"_id": "latest"}) or {}
    by_flag = {e["flag"]: e for e in grades.get("experiments", [])}
    n = 0
    for doc in _coll().find({"status": "serving"}):
        g = by_flag.get(doc["flag_key"])
        if g:
            _coll().update_one({"_id": doc["_id"]}, {"$set": {"grade": g, "graded_at": NOW.isoformat()}})
            n += 1
    print(f"graded {n} serving experiments from rl_arm_grades")


def retire(exp_id):
    doc = _coll().find_one({"_id": exp_id})
    assert doc, f"no experiment {exp_id}"
    try:
        existing = _ph("GET", f"feature_flags/?limit=100")
        fid = next((f["id"] for f in existing.get("results", []) if f["key"] == doc["flag_key"]), None)
        if fid:
            _ph("PATCH", f"feature_flags/{fid}/", {"active": False})
    except Exception as e:
        print("flag disable note:", str(e)[:100])
    _coll().update_one({"_id": exp_id}, {"$set": {"status": "retired", "retired_at": NOW.isoformat()}})
    print(f"retired {exp_id}")


def _list(serving_only):
    q = {"status": "serving"} if serving_only else {}
    docs = list(_coll().find(q).sort("_id", 1))
    print(f"{len(docs)} experiment(s){' serving' if serving_only else ''}:")
    for d in docs:
        print(f"  {d['_id']:<26} {d['surface']:<20} {d['status']:<9} target={d.get('target')} "
              f"arms={[a['variant'] for a in d['arms']]}  «{d['hypothesis'][:40]}»")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose"); p.add_argument("--surface", required=True); p.add_argument("--target", default="all")
    p.add_argument("--hypothesis", required=True); p.add_argument("--arms", required=True, help="JSON list")
    s = sub.add_parser("serve"); s.add_argument("--exp", required=True)
    r = sub.add_parser("retire"); r.add_argument("--exp", required=True)
    sub.add_parser("grade")
    ll = sub.add_parser("list"); ll.add_argument("--serving", action="store_true")
    a = ap.parse_args()
    if a.cmd == "propose":
        propose(a.surface, a.target, a.hypothesis, json.loads(a.arms))
    elif a.cmd == "serve":
        serve(a.exp)
    elif a.cmd == "retire":
        retire(a.exp)
    elif a.cmd == "grade":
        grade()
    elif a.cmd == "list":
        _list(a.serving)


if __name__ == "__main__":
    main()
