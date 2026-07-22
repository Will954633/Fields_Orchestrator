#!/usr/bin/env python3
"""
lead_intelligence.py — unify + enrich + flag EVERY lead so nothing is missed.

Runs before Samantha's nightly review (cron 02:00 AEST). For every lead across all
sources (Analyse Your Home, launch form, price alerts, FB lead-gen ads, mini-site
reports, CRM contacts) it:

  1. COLLECT   — pull leads from all lead-bearing collections, normalise to one record.
  2. DEDUPE    — merge by person (email) and by property address.
  3. ENRICH     — for any lead with an address: resolve the Gold_Coast property, read
                 listing_status (for_sale / withdrawn / sold), last sold date/price,
                 years held, and classify OWNER-OCCUPIER vs INVESTOR (occupancy_classifier).
                 Free path = stored Gold_Coast timeline (zero cost). Paid Bright Data
                 fresh pull is used ONLY for high-priority + stale leads, capped per run.
  4. ATTRIBUTE — attach source/channel/campaign + CRM engagement_score + PostHog id.
  5. SCORE      — transparent rule-based priority (high/med/low) + human-readable reason.
  6. WRITE      — upsert system_monitor.lead_worklist (one enriched record per lead) and
                 flag the matching crm_contacts record. Samantha reads this and recommends.

Honest scope note: the two currently-running FB ads capture BUYER briefs (suburb + beds/
baths + timeframe), NOT an address — so those leads have nothing to timeline-enrich; they
are scored on buyer-intent instead. Address enrichment applies to AYH / launch / price-alert
/ FB-AYH / report leads.

Usage:
  python3 scripts/samantha/lead_intelligence.py                 # full run (writes)
  python3 scripts/samantha/lead_intelligence.py --dry-run       # compute, print, no writes
  python3 scripts/samantha/lead_intelligence.py --no-fresh      # never hit Bright Data
  python3 scripts/samantha/lead_intelligence.py --max-fresh 3   # cap paid fresh pulls (default 5)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields")

from src.mongo_client_factory import get_mongo_client, cosmos_retry  # noqa: E402
from scripts.property_reports import occupancy_classifier as occ  # noqa: E402

NOW = datetime.now(timezone.utc)
FRESH_STALE_DAYS = 45  # re-pull fresh only if stored timeline older than this / missing

# Internal / test markers — never surface these as real leads.
TEST_EMAIL_BITS = ("will@fieldsestate", "@blueoceans", "test@", "example.com")
TEST_NAME_BITS = ("test", "william simpson", "will simpson")
TEST_SOURCE_BITS = ("_test", "test_", "smoke")


# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #
def _s(v) -> str:
    return (str(v) if v is not None else "").strip()


def _email(v) -> str:
    return _s(v).lower()


def _is_test(email: str, name: str, source: str, raw_is_test=None) -> bool:
    if raw_is_test in (True, "true", "True", 1, "1"):
        return True
    e, n, s = email.lower(), name.lower(), source.lower()
    if any(b in e for b in TEST_EMAIL_BITS):
        return True
    if n and any(b == n or b in n for b in TEST_NAME_BITS):
        return True
    if any(b in s for b in TEST_SOURCE_BITS):
        return True
    return False


def _suburb_key(lead: dict) -> str:
    sub = _s(lead.get("suburb"))
    if not sub:
        addr = _s(lead.get("address"))
        parts = [p.strip() for p in addr.split(",")]
        if len(parts) >= 2:
            sub = parts[1]
    return re.sub(r"[^a-z0-9]+", "_", sub.lower()).strip("_")


def _resolve_gc_doc(lead: dict, gc_db):
    """Resolve the Gold_Coast property doc for a lead's address (reuses occupancy_classifier)."""
    addr = _s(lead.get("address"))
    if not addr:
        return None
    report_like = {"suburb_key": _suburb_key(lead), "address": addr}
    try:
        return occ._find_gc_doc(report_like, gc_db)
    except Exception:
        return None


STALE_STATUS_DAYS = 14


def _status_age_days(gc_doc: dict) -> float | None:
    """Days since the Gold_Coast doc was last updated (proxy for listing_status freshness)."""
    lu = gc_doc.get("last_updated")
    if not isinstance(lu, datetime):
        return None
    lu = lu.replace(tzinfo=None)
    return round((NOW.replace(tzinfo=None) - lu).days + 0.0, 1)


def _property_summary(gc_doc: dict) -> dict:
    if not gc_doc:
        return {}
    age = _status_age_days(gc_doc)
    return {
        "resolved_property_id": str(gc_doc.get("_id")),
        "listing_status": gc_doc.get("listing_status"),
        # Staleness guard (Dee lesson): listing_status older than STALE_STATUS_DAYS —
        # or of unknown age — must be re-verified with a FRESH pull before anyone acts.
        "status_age_days": age,
        "status_stale": age is None or age > STALE_STATUS_DAYS,
        "price": gc_doc.get("price"),
        "bedrooms": gc_doc.get("bedrooms") or gc_doc.get("BEDROOMS"),
        "bathrooms": gc_doc.get("bathrooms") or gc_doc.get("BATHROOMS"),
        "property_type": gc_doc.get("property_type") or gc_doc.get("PROPERTY_TYPE"),
        "suburb": gc_doc.get("LOCALITY") or gc_doc.get("suburb"),
    }


def _years_held(last_sale_date: str) -> float | None:
    if not last_sale_date:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = datetime.strptime(last_sale_date[:10], "%Y-%m-%d")
            return round((NOW.replace(tzinfo=None) - d).days / 365.25, 1)
        except Exception:
            continue
    return None


def _enrich_occupancy(lead: dict, gc_doc: dict, gc_db, allow_fresh: bool) -> dict:
    """Owner-occupier vs investor. Free stored path by default; fresh only when asked."""
    if not gc_doc:
        return {"type": "unknown", "confidence": "low",
                "signals": ["address not resolved to a property"],
                "timeline_source": "none", "needs_fresh_pull": False}

    # Free path — stored timeline.
    events = occ.normalise_stored_timeline(gc_doc)
    result = occ.classify_from_timeline(events)
    result["timeline_source"] = "stored"
    result["timeline_event_count"] = len(events)

    stored_age_days = None
    refreshed = gc_doc.get("occupancy_timeline_refreshed_at")
    if isinstance(refreshed, datetime):
        stored_age_days = (NOW.replace(tzinfo=None) - refreshed.replace(tzinfo=None)).days
    stale = stored_age_days is None or stored_age_days > FRESH_STALE_DAYS
    result["needs_fresh_pull"] = bool(stale)

    if allow_fresh:
        report_like = {"suburb_key": _suburb_key(lead), "address": _s(lead.get("address")),
                       "property_id": str(gc_doc.get("_id")), "slug": gc_doc.get("url_slug")}
        try:
            fresh = occ.refresh_and_classify(report_like, gc_db, fetch_fresh=True)
            if fresh and fresh.get("timeline_source") == "fresh_brightdata":
                fresh["needs_fresh_pull"] = False
                return fresh
        except Exception as e:  # noqa: BLE001
            result["signals"] = list(result.get("signals", [])) + [f"fresh pull failed: {e}"]
    return result


# ---------------------------------------------------------------------------- #
# Collect
# ---------------------------------------------------------------------------- #
def collect_leads(sm) -> dict:
    """Return {lead_key: normalised_lead} merged across all lead sources."""
    leads: dict = {}

    def add(email, name, phone, address, source, origin, ts, extra=None):
        email = _email(email)
        name, phone, address, source = _s(name), _s(phone), _s(address), _s(source)
        key = email or ("addr:" + re.sub(r"[^a-z0-9]+", "", address.lower())) or f"{origin[0]}:{origin[1]}"
        rec = leads.get(key)
        if not rec:
            rec = {"lead_key": key, "email": email, "name": name, "phone": phone,
                   "address": address, "sources": [], "origins": [],
                   "first_seen": ts, "last_seen": ts, "extra": {}}
            leads[key] = rec
        # merge: prefer to fill blanks + keep an address if any source had one
        rec["name"] = rec["name"] or name
        rec["phone"] = rec["phone"] or phone
        rec["address"] = rec["address"] or address
        if source and source not in rec["sources"]:
            rec["sources"].append(source)
        rec["origins"].append({"collection": origin[0], "id": str(origin[1])})
        if ts:
            rec["first_seen"] = min(x for x in [rec["first_seen"], ts] if x)
            rec["last_seen"] = max(x for x in [rec["last_seen"], ts] if x)
        if extra:
            rec["extra"].update({k: v for k, v in extra.items() if v not in (None, "")})
        return rec

    for d in sm["analyse_leads"].find():
        add(d.get("email"), d.get("name"), d.get("phone"), d.get("address"),
            d.get("source") or "analyse_your_home", ("analyse_leads", d["_id"]),
            _s(d.get("submitted_at")),
            {"buy_timeline": d.get("buy_timeline"), "sell_timeline": d.get("sell_timeline"),
             "referring_property": d.get("referring_property"),
             "posthog_distinct_id": d.get("posthog_distinct_id"), "status": d.get("status")})

    for d in sm["launch_leads"].find():
        add(d.get("email"), d.get("name"), d.get("phone"), d.get("address"),
            "launch_form", ("launch_leads", d["_id"]), _s(d.get("submitted_at")),
            {"value_range": d.get("value_range"), "timeline": d.get("timeline"),
             "appraised": d.get("appraised"), "status": d.get("status")})

    for d in sm["leads"].find():
        add(d.get("email"), (d.get("owner") or {}).get("name") if isinstance(d.get("owner"), dict) else None,
            None, d.get("address"), d.get("source") or "lead", ("leads", d["_id"]),
            _s(d.get("created_at")),
            {"property_id": d.get("property_id"), "lead_quality": d.get("lead_quality"),
             "status": d.get("status")})

    for d in sm["fb_leads"].find():
        f = d.get("fields") or {}
        add(f.get("email"), f.get("full_name") or f.get("name"), f.get("phone"),
            f.get("address") or f.get("street_address"),  # buyer-brief forms usually have none
            f"fb_ad:{_s(d.get('campaign_name')) or 'ad'}", ("fb_leads", d["_id"]),
            _s(d.get("created_time")),
            {"campaign_name": d.get("campaign_name"), "ad_name": d.get("ad_name"),
             "is_organic": d.get("is_organic"), "is_test": d.get("is_test"),
             "buyer_area": f.get("area"), "buyer_beds": f.get("bedrooms"),
             "buyer_baths": f.get("bathrooms"), "timeframe": f.get("timeframe"),
             "owns_gc_home": f.get("owns_gc_home")})

    for d in sm["property_reports"].find():
        owner = d.get("owner") or {}
        add(owner.get("email"), owner.get("name"), owner.get("phone"), d.get("address"),
            d.get("source") or "property_report", ("property_reports", d["_id"]),
            _s(d.get("created_at")),
            {"report_slug": d.get("slug"), "report_state": d.get("state"),
             "report_occupancy": d.get("occupancy")})

    return leads


def merge_crm(leads: dict, sm) -> None:
    """Attach CRM engagement + attribution to matching people (by email)."""
    by_email = {r["email"]: r for r in leads.values() if r["email"]}
    for c in sm["crm_contacts"].find():
        e = _email(c.get("email"))
        if not e:
            continue
        rec = by_email.get(e)
        if not rec:  # CRM contact with no lead-form row — still a lead spine
            rec = {"lead_key": e, "email": e, "name": "", "phone": _s(c.get("phone")),
                   "address": "", "sources": [], "origins": [],
                   "first_seen": _s(c.get("first_seen")), "last_seen": _s(c.get("last_seen")),
                   "extra": {}}
            leads[e] = rec
        rec["origins"].append({"collection": "crm_contacts", "id": str(c["_id"])})
        if _s(c.get("source")) and _s(c.get("source")) not in rec["sources"]:
            rec["sources"].append(_s(c.get("source")))
        rec["crm"] = {
            "engagement_score": c.get("engagement_score"),
            "status": c.get("status"), "tags": c.get("tags"),
            "lead_attribution": c.get("lead_attribution"),
            "qualification_reason": c.get("qualification_reason"),
        }


# ---------------------------------------------------------------------------- #
# Score
# ---------------------------------------------------------------------------- #
def score(rec: dict) -> tuple[str, str, list]:
    """Transparent priority. Returns (priority, reason, signals)."""
    sig = []
    ex = rec.get("extra", {})
    occ_type = (rec.get("occupancy") or {}).get("type")
    listing = (rec.get("property") or {}).get("listing_status")
    yrs = rec.get("years_held")
    has_addr = bool(rec.get("address"))
    resolved = bool((rec.get("property") or {}).get("resolved_property_id"))

    if rec.get("is_test"):
        return "test", "internal/test lead — excluded from action", ["test marker matched"]

    # Seller-intent signals on a real address
    if has_addr and resolved:
        if occ_type == "owner_occupier":
            sig.append("owner-occupier (lives there)")
        elif occ_type == "investor":
            sig.append("investor/rented")
        if listing in ("for_sale", "withdrawn"):
            sig.append(f"currently {listing} — active move")
        if yrs is not None and yrs >= 7:
            sig.append(f"held ~{yrs}y (typical sell window)")
        if _s(ex.get("sell_timeline")) and _s(ex.get("sell_timeline")).lower() not in ("", "none", "just_watching"):
            sig.append(f"stated sell timeline: {ex.get('sell_timeline')}")

    # Buyer-intent (no address; e.g. FB buyer-brief ads)
    if not has_addr:
        tf = _s(ex.get("timeframe")).lower()
        if tf in ("now", "0-3", "asap"):
            sig.append("buyer timeframe: now")
        if _s(ex.get("owns_gc_home")).lower() == "yes":
            sig.append("buyer already owns a GC home (potential seller too)")

    eng = (rec.get("crm") or {}).get("engagement_score")
    try:
        if eng is not None and float(eng) >= 5:
            sig.append(f"engagement score {eng}")
    except Exception:
        pass

    # Priority rules (2026-07-17: tenure alone is a prior, not an active signal —
    # HIGH now requires a genuine pre-market signal; already-listed owners drop to
    # MEDIUM with a changed angle; long tenure alone is MEDIUM.)
    stated_timeline = _s(ex.get("sell_timeline")).lower() not in ("", "none", "just_watching")
    already_listed = listing in ("for_sale", "sold")
    pre_market = (listing == "withdrawn") or (stated_timeline and not already_listed)
    high = has_addr and resolved and occ_type == "owner_occupier" and pre_market
    med = (has_addr and resolved) or _s(ex.get("timeframe")).lower() in ("now", "asap") \
        or _s(ex.get("owns_gc_home")).lower() == "yes"

    if high:
        pr = "high"
        reason = "Owner-occupier with a genuine pre-market signal (withdrawn / stated timeline) — likely seller. Review + draft outreach."
    elif med:
        pr = "medium"
        if has_addr and resolved and occ_type == "owner_occupier" and listing == "for_sale":
            reason = "Owner-occupier but ALREADY LISTED — not pre-market. Track their listing / buyer-side angle only."
        elif has_addr and resolved and occ_type == "owner_occupier" and yrs is not None and yrs >= 7:
            reason = "Owner-occupier, long-held (tenure prior only — no active-move signal yet)."
        else:
            reason = "Real lead with a property or near-term intent — worth a look."
    else:
        pr = "low"
        reason = "Lead captured; low active-intent signal for now."
    if not sig:
        sig = ["no strong intent signal yet"]
    return pr, reason, sig


# ---------------------------------------------------------------------------- #
# Main
# ---------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fresh", action="store_true", help="never hit Bright Data")
    ap.add_argument("--max-fresh", type=int, default=5, help="cap paid fresh pulls per run")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    c = get_mongo_client()
    sm = c["system_monitor"]
    gc_db = c["Gold_Coast"]

    leads = collect_leads(sm)
    merge_crm(leads, sm)
    recs = list(leads.values())
    if args.limit:
        recs = recs[:args.limit]

    # Mark test + resolve property (free enrichment) for everyone first.
    for r in recs:
        r["is_test"] = _is_test(r["email"], r["name"], " ".join(r["sources"]),
                                (r.get("extra") or {}).get("is_test"))
        gc_doc = None if r["is_test"] else _resolve_gc_doc(r, gc_db)
        r["property"] = _property_summary(gc_doc)
        # Occupancy: prefer a report's already-computed occupancy if present.
        rep_occ = (r.get("extra") or {}).get("report_occupancy")
        if rep_occ:
            r["occupancy"] = {**rep_occ, "needs_fresh_pull": False}
        else:
            r["occupancy"] = _enrich_occupancy(r, gc_doc, gc_db, allow_fresh=False)
        ev = (r["occupancy"] or {}).get("evidence") or {}
        r["last_sold_date"] = ev.get("last_sale_date")
        r["last_sold_price"] = ev.get("last_sale_price")
        r["years_held"] = _years_held(ev.get("last_sale_date"))
        r["_gc_doc_found"] = gc_doc is not None

    # First-pass score to find high-priority + stale for the capped fresh pulls.
    for r in recs:
        r["priority"], r["reason"], r["signals"] = score(r)
        # Staleness guard (Dee lesson): actionable leads whose listing_status is old or of
        # unknown age get an explicit VERIFY-FIRST signal so nobody calls a "pre-market
        # seller" who has already listed.
        if r["priority"] in ("high", "medium") and (r.get("property") or {}).get("status_stale"):
            r["signals"].append("STALE_STATUS_verify_fresh_before_acting")
            r["reason"] = f"{r['reason']} [status stale >{STALE_STATUS_DAYS}d — verify fresh first]"

    if not args.no_fresh:
        fresh_budget = args.max_fresh
        for r in sorted(recs, key=lambda x: x["priority"] != "high"):
            if fresh_budget <= 0:
                break
            if r["priority"] == "high" and (r.get("occupancy") or {}).get("needs_fresh_pull") \
                    and r["_gc_doc_found"] and not args.dry_run:
                gc_doc = _resolve_gc_doc(r, gc_db)
                r["occupancy"] = _enrich_occupancy(r, gc_doc, gc_db, allow_fresh=True)
                fresh_budget -= 1
                r["priority"], r["reason"], r["signals"] = score(r)  # re-score with better data

    # Write
    # Leads a human has explicitly dismissed (e.g. "already listed, drop it") must NOT be
    # silently re-scored back to a live priority on the next run — that's exactly what happened
    # before this fix (2026-07-22): a manually-resolved lead had no durable way to stay resolved.
    dismissed_keys = {d["lead_key"] for d in sm["lead_worklist"].find(
        {"dismissed": True}, {"lead_key": 1})}

    written = 0
    for r in recs:
        doc = {
            "lead_key": r["lead_key"], "email": r["email"], "name": r["name"],
            "phone": r["phone"], "address": r["address"], "sources": r["sources"],
            "origins": r["origins"], "first_seen": r["first_seen"], "last_seen": r["last_seen"],
            "is_test": r["is_test"], "property": r.get("property"),
            "occupancy": r.get("occupancy"), "last_sold_date": r.get("last_sold_date"),
            "last_sold_price": r.get("last_sold_price"), "years_held": r.get("years_held"),
            "attribution": {"sources": r["sources"], "crm": r.get("crm")},
            "extra": r.get("extra"), "priority": r["priority"], "reason": r["reason"],
            "signals": r["signals"], "enriched_at": NOW, "updated_at": NOW,
        }
        if r["lead_key"] in dismissed_keys:
            # Keep enrichment fresh but leave priority/reason/signals + the dismissed_* fields
            # alone — a dismissal only clears when a human/Samantha explicitly un-dismisses it.
            for k in ("priority", "reason", "signals"):
                doc.pop(k, None)
        if args.dry_run:
            continue
        cosmos_retry(lambda: sm["lead_worklist"].update_one(
            {"lead_key": r["lead_key"]}, {"$set": doc}, upsert=True))
        if r["email"] and not r["is_test"]:
            cosmos_retry(lambda: sm["crm_contacts"].update_one(
                {"email": r["email"]},
                {"$set": {"worklist_priority": r["priority"], "worklist_reason": r["reason"],
                          "worklist_updated_at": NOW}}))
        written += 1

    # Summary
    from collections import Counter
    pri = Counter(r["priority"] for r in recs)
    print(f"leads: {len(recs)} | {'DRY-RUN' if args.dry_run else f'written {written}'} | "
          f"priority: {dict(pri)}")
    for r in sorted(recs, key=lambda x: {"high": 0, "medium": 1, "low": 2, "test": 3}.get(x["priority"], 4)):
        if r["priority"] in ("high", "medium"):
            occ_t = (r.get("occupancy") or {}).get("type", "?")
            print(f"  [{r['priority']:>6}] {r['email'] or r['address'] or r['lead_key']:<42} "
                  f"{'addr✓' if r['address'] else 'no-addr':<7} occ={occ_t:<13} "
                  f"held={r.get('years_held')} — {r['signals'][0] if r['signals'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
