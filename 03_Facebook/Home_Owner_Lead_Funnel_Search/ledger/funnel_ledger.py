#!/usr/bin/env python3
"""
funnel_ledger.py — cross-boundary reward ledger for the Home Owner Funnel-Discovery lab.

Build 6A of 04_EXPANDED_MANDATE_SCOPING.md. This is the PREREQUISITE that makes
optimisation possible across the FB-ad -> landing-page seam: one unified event
stream per person, joined on the PostHog `distinct_id`, so a funnel VARIANT can be
scored on engagement + micro-conversions (behaviour) against cost (FB spend).

Storage: system_monitor.funnel_events (Cosmos). Two ROW KINDS in one collection:
  kind="ad_stats"     _id = adstats:<variant>:<date>   (FB Graph API, per variant/day)
      fields: variant, date, spend, impressions, clicks, fb_leads, updated_at
  kind="funnel_event" _id = evt:<posthog_uuid>          (PostHog, per person/step)
      fields: distinct_id, variant, lab_cid, event, step, field, goal,
              terminal_type, ts, props, ingested_at

Both writers are IDEMPOTENT (deterministic _id + upsert) so the hourly sync can
re-run over an overlapping window without double-counting.

CANONICAL EVENT SPINE — the CONTRACT the landing pages MUST emit to PostHog. All
lab events are prefixed `lab_` so they never collide with the main site's events.
Every event carries `variant` (= the ad_name / template variant) and `lab_cid`
(the per-click id threaded from the ad URL). See EVENT_SPINE below.

Usage (library):
    from funnel_ledger import Ledger, EVENT_SPINE, GOAL_WEIGHTS
    lg = Ledger()
    lg.ensure_indexes()
    lg.record_ad_stats(variant="AN2_missmillion_light", date="2026-07-30",
                       spend=32.19, impressions=628, clicks=43, fb_leads=2)
    lg.record_funnel_event(uuid="...", distinct_id="d1", variant="AN2...",
                       event="lab_field_complete", field="address", ts="...ISO...")
"""
from __future__ import annotations
import os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

# ---------------------------------------------------------------------------
# The event spine — canonical lab event names + their required properties.
# This is the contract the /lab/ landing-page templates emit to PostHog.
# ORDER matters: index = funnel depth, used for the engagement/progression score.
# ---------------------------------------------------------------------------
EVENT_SPINE = [
    "lab_lp_view",         # 0  landing page loaded            props: variant, lab_cid
    "lab_step_view",       # 1  a funnel step was shown        props: variant, lab_cid, step
    "lab_field_focus",     # 2  user focused a PII field       props: variant, field
    "lab_field_complete",  # 3  user entered a valid value     props: variant, field
    "lab_micro_conversion",# 4  a sub-goal was reached         props: variant, goal
    "lab_terminal",        # 5  funnel end reached             props: variant, terminal_type
]
# call-intent is a side event (measured, not a step): a click on a "call us" CTA.
CALL_CTA_EVENT = "lab_call_cta_click"

# The four micro-conversion sub-goals (G1..G4) and their BUSINESS-VALUE weights.
# Address is the crown jewel (address -> direct mail -> inbound call). Tunable.
PII_FIELDS = ["address", "phone", "email", "name"]
GOAL_WEIGHTS = {"address": 1.0, "phone": 0.8, "email": 0.5, "name": 0.2}

# PII fields that are "terminal_type" values on the honest end-state.
TERMINAL_TYPES = ["waitlist_optin", "deadend"]

_UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(_UTC).isoformat()


def _cosmos_retry(fn, *a, **k):
    """Minimal retry for Cosmos 16500 (RU exhaustion). Reuses the project pattern."""
    delay = 1.0
    for attempt in range(6):
        try:
            return fn(*a, **k)
        except Exception as e:  # pymongo OperationFailure carries code 16500
            code = getattr(e, "code", None)
            msg = str(e)
            if code == 16500 or "16500" in msg or "TooManyRequests" in msg or "RetryAfterMs" in msg:
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            raise
    return fn(*a, **k)


class Ledger:
    def __init__(self, client=None):
        self.client = client or get_client()
        self.coll = self.client["system_monitor"]["funnel_events"]

    # -- schema / indexes ---------------------------------------------------
    def ensure_indexes(self):
        # create_index is idempotent; safe to call every run.
        self.coll.create_index("kind")
        self.coll.create_index("variant")
        self.coll.create_index("distinct_id")
        self.coll.create_index("event")
        self.coll.create_index("ts")
        self.coll.create_index([("kind", 1), ("variant", 1)])

    # -- writers (idempotent) ----------------------------------------------
    def record_ad_stats(self, *, variant: str, date: str, spend: float,
                        impressions: int, clicks: int, fb_leads: int = 0) -> None:
        doc = {"kind": "ad_stats", "variant": variant, "date": date,
               "spend": float(spend), "impressions": int(impressions),
               "clicks": int(clicks), "fb_leads": int(fb_leads),
               "updated_at": _now_iso()}
        _id = f"adstats:{variant}:{date}"
        _cosmos_retry(self.coll.update_one, {"_id": _id}, {"$set": doc}, upsert=True)

    def record_funnel_event(self, *, uuid: str, distinct_id: str, variant: str,
                            event: str, ts: str, lab_cid: str = "", step=None,
                            field: str = "", goal: str = "", terminal_type: str = "",
                            props: dict | None = None) -> None:
        doc = {"kind": "funnel_event", "distinct_id": distinct_id, "variant": variant,
               "lab_cid": lab_cid, "event": event, "ts": ts,
               "ingested_at": _now_iso()}
        if step is not None:
            doc["step"] = step
        if field:
            doc["field"] = field
        if goal:
            doc["goal"] = goal
        if terminal_type:
            doc["terminal_type"] = terminal_type
        if props:
            doc["props"] = props
        _id = f"evt:{uuid}"
        _cosmos_retry(self.coll.update_one, {"_id": _id}, {"$set": doc}, upsert=True)

    # -- readers ------------------------------------------------------------
    def ad_stats(self) -> list[dict]:
        return list(self.coll.find({"kind": "ad_stats"}))

    def funnel_events(self, variant: str | None = None) -> list[dict]:
        q = {"kind": "funnel_event"}
        if variant:
            q["variant"] = variant
        return list(self.coll.find(q))

    def variants(self) -> list[str]:
        return sorted(set(self.coll.distinct("variant")))

    def counts(self) -> dict:
        return {"ad_stats": self.coll.count_documents({"kind": "ad_stats"}),
                "funnel_event": self.coll.count_documents({"kind": "funnel_event"})}


if __name__ == "__main__":
    lg = Ledger()
    lg.ensure_indexes()
    print("funnel_events indexes ensured. current counts:", lg.counts())
    print("known variants:", lg.variants()[:10], "...")
