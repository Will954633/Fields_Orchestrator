#!/usr/bin/env python3
"""
Log KNOWN-CONTACT site activity to the "Activity" tab of the Live Leads Tracker.

The gap this closes
-------------------
crm_sync.py already reconstructs a per-visitor journey from PostHog every hour and
stores it on system_monitor.crm_contacts (journey.page_sequence, probable_address,
offmarket_home, ...). live_leads_to_sheet.py already writes the "All Leads" roster.
But nothing ever noticed "a person we can actually REACH came back and read X" —
`returning` was only ever a static tag (crm_sync.py:318), and the All Leads tab is
insert-once-per-lead, so a repeat visit produced no row and changed nothing.

This script is that missing middle. Every run it:
  1. builds the set of contacts we have a communication pathway to (email / phone /
     a postal address — confirmed, submitted, or inferred) AND a PostHog id;
  2. pulls their raw events from PostHog for the lookback window;
  3. splits each person's events into visits (>30 min gap = a new visit);
  4. keeps visits where the contact was ALREADY KNOWN to us before the visit began
     (that is the business definition of "returning" — it also catches an FB lead-ad
     contact browsing the site for the first time, which matters just as much);
  5. writes one verbose row per visit to the "Activity" tab.

It deliberately does NOT message anyone. There is no newsletter/mailer/SMS system
yet (system_monitor.subscribers has never been sent anything). The point is a
durable, legible activity ledger that a later trigger can be built on top of.

Honesty rules this script follows (they matter — Will acts on these rows)
------------------------------------------------------------------------
  * Engaged time comes from max(time_on_page.duration), NOT last-event-minus-first.
    The time_on_page milestones fire at 10/30/60/120/300s of ACTIVE time and stop at
    300, so a tab left open for 40 minutes must never be reported as 40 minutes of
    reading. Wall-clock span is reported separately and labelled as such.
  * Every postal address says where it came from. "owner-confirmed" and "inferred
    from an off-market lookup" are very different things to act on, so the Reach Via
    column always carries the provenance rather than implying we were given it.
  * "Already sent" is read from real send records (crm_contacts.communications +
    system_monitor.email_sends), so "nothing sent yet" is a fact, not an assumption.
  * The Opportunity column is deterministic rules over what they actually read — no
    LLM call (agents are off, and it must stay cheap + reproducible).

Dedupe: system_monitor.engagement_activity_ledger, keyed by "<contact_id>:<visit
start>". Rows are inserted at the TOP (newest first) exactly like live_leads_to_sheet
so manual edits and formatting shift down intact. A row deleted by hand is never
resurrected.

Usage:
  python3 scripts/engagement_activity_to_sheet.py --dry-run
  python3 scripts/engagement_activity_to_sheet.py
  python3 scripts/engagement_activity_to_sheet.py --hours 168   # backfill a week
  python3 scripts/engagement_activity_to_sheet.py --include-first-visit
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "propradar"))

from shared.db import get_client
from crm_sync import posthog_query, INTERNAL_IDS, BOT_CITIES
from job_status import job_run
import market_status as ms
from live_leads_to_sheet import (
    LIVE_SPREADSHEET_ID, get_sheets, tab_id, set_env_from_file, AEST,
)

TAB = "Activity"
LEDGER_DB = "system_monitor"
LEDGER_COLL = "engagement_activity_ledger"

# A gap this long between two events means they left and came back.
VISIT_GAP_MIN = 30
# time_on_page milestones stop at 300s, so this is the ceiling of what we can honestly
# claim as engaged reading time on a single page.
ENGAGED_CAP_S = 300

HEADERS = ["Date", "Time (AEST)", "Who", "Safe to mail?", "Best address / contact",
           "Evidence", "All addresses on file", "Visit", "Channel", "Location",
           "Engaged", "What They Did", "Already Sent", "Opportunity", "Activity ID"]
ACTIVITY_ID_COL = 14  # 0-indexed -> column O (hidden, dedupe key only)
WRAP_COLS = (3, 15)   # "Safe to mail?" through "Opportunity" are all prose

CATEGORY_LABELS = {
    "crash-risk": "crash risk",
    "sell-now": "should I sell now",
    "buy": "is it a good time to buy",
    "overview": "market overview",
    "direction": "where the market is heading",
    "suburb-compare": "suburb comparison",
    "houses-vs-units": "houses vs units",
}

# What each thing they read implies, and what we could send. Deterministic — first
# match in this order wins, so the strongest seller signal beats a general read.
OPPORTUNITY_RULES = [
    ("own_minisite", "They re-opened their OWN home report. Strongest signal here — "
                     "offer the printed appraisal / a call about their place."),
    ("sell-now", "Actively weighing whether to sell. Highest-value follow-up: an "
                 "appraisal for their address and current buyer-demand data."),
    ("crash-risk", "Reading crash-risk data. Send the crash-risk explainer/video for "
                   "this suburb — answers the question they came with."),
    ("direction", "Reading where the market is heading. Send the market-direction "
                  "breakdown / latest Market Pulse for this suburb."),
    ("offmarket", "Looking up a specific address off-market. Send that property's "
                  "off-market report, or ask if it's their own home."),
    ("other_minisite", "Looking at OTHER homes' reports, not their own — researching "
                       "neighbours/comparables. Send comparable-sales data for the area."),
    ("valuation", "Looking at valuation/comparables. Send the comparable-sales range "
                  "for their address."),
    ("buy", "Buyer-side reading. Send the Five Property Friday shortlist."),
    ("suburb-compare", "Comparing suburbs. Send the suburb-comparison data."),
    ("houses-vs-units", "Comparing houses vs units. Send that breakdown."),
    ("overview", "General market reading for this suburb. Send the latest Market "
                 "Pulse summary."),
    ("for_sale", "Browsing live listings. Worth asking what they're looking for."),
    ("article", "Reading our articles. Newsletter candidate once we have a mailer."),
]


# ---- pathway resolution ------------------------------------------------------
# Which address is actually THEIRS is the whole ballgame — a wrong answer posts mail
# to a stranger's letterbox. These tiers exist because the underlying fields are NOT
# equally trustworthy, and the first version of this script wrongly flattened them:
#
#   T1 CONFIRMED  home_confirmed.source == "user_confirmed" — they clicked "yes, this
#                 is my home" in the recognition modal. The only direct evidence we
#                 ever get. Mailable.
#   T2 SUBMITTED  property_address — they typed it into Analyse Your Home and we built
#                 them a report. Strong, but people also run AYH on homes they're
#                 researching, so it is not proof of ownership. Mailable, flagged.
#   T3 LOOKUP     offmarket_home, AND they only ever looked at that ONE address. This
#                 is the documented owner-lookup pattern (see memory
#                 organic_offmarket_pivot: 94% of off-market visitors view exactly one
#                 address). The single-address condition is what makes it credible.
#   T4 AMBIGUOUS  everything else — most importantly `probable_address`, which is just
#                 the LAST mini-site they happened to open. `probable_address_slugs`
#                 is every address they viewed, not addresses they own. NOT mailable.
#
# A currently-listed address is never mailable regardless of tier: either they're a
# buyer researching a listing, or they're a seller already on the market with another
# agent — and "we noticed you looking at your home report" is wrong in both cases.
T_CONFIRMED, T_SUBMITTED, T_LOOKUP, T_AMBIGUOUS = 1, 2, 3, 4


def address_candidates(c: dict, seen_now: set[str] | None = None) -> list[dict]:
    """Every address we associate with this contact, each with its evidence tier.

    Returns them all — the row shows the ambiguity rather than hiding it behind one
    confidently-wrong pick.
    """
    out, added = [], set()

    def add(addr, slug, tier, basis):
        key = (slug or addr or "").lower()
        if not key or key in added:
            return
        added.add(key)
        out.append({"address": addr, "slug": slug, "tier": tier, "basis": basis})

    hc = c.get("home_confirmed") or {}
    if isinstance(hc, dict) and hc.get("address") and hc.get("source") == "user_confirmed":
        add(hc["address"], hc.get("slug"), T_CONFIRMED,
            "they clicked “yes, this is my home”")

    pa = (c.get("property_address") or "").strip()
    if pa:
        add(pa, None, T_SUBMITTED, "they submitted it to Analyse Your Home")

    om = c.get("offmarket_home") or {}
    if isinstance(om, dict) and (om.get("slug") or om.get("address")):
        slugs = [s for s in (om.get("slugs") or []) if s] or ([om["slug"]] if om.get("slug") else [])
        # Stored fields lag: `/building/<slug>` views never write to crm_contacts at
        # all. Fold in the addresses observed during THIS visit so a person looking at
        # two units in the same block can't be called the owner of one of them.
        viewed = {v for v in (c.get("probable_address_slugs") or []) if v} | (seen_now or set())
        # Only one address in their whole footprint -> the owner-lookup read holds.
        single = len(set(slugs) | viewed) == 1
        for s in slugs:
            # offmarket_home.address is stored unpunctuated ("13 4 Yodelay Street
            # Varsity Lakes") and is not postable — rebuild it from the slug.
            add(slug_to_address(s), s,
                T_LOOKUP if single else T_AMBIGUOUS,
                "arrived from Google straight to this address's off-market page"
                + ("" if single else " — but they viewed other addresses too, so this "
                                    "is just one of several"))

    prob = (c.get("probable_address") or "").strip()
    if prob:
        add(prob, c.get("probable_address_slug"), T_AMBIGUOUS,
            "the most recent mini-site they opened — NOT evidence of ownership")
    for s in (c.get("probable_address_slugs") or []):
        add(slug_to_address(s), s, T_AMBIGUOUS, "a report they opened")

    out.sort(key=lambda x: x["tier"])
    return out


def reach_for(c: dict, status: dict | None = None,
              seen_now: set[str] | None = None) -> dict | None:
    """Best available way to reach this contact, with an explicit mailability verdict.

    `status` maps address -> PropRadar market status (see propradar/market_status).
    """
    status = status or {}
    email = (c.get("email") or "").strip()
    if email:
        return {"via": "Email", "detail": email, "mail_ok": "Yes — email",
                "candidates": address_candidates(c, seen_now)}
    phone = (c.get("phone") or "").strip()
    if phone:
        return {"via": "Phone", "detail": phone, "mail_ok": "Yes — phone",
                "candidates": address_candidates(c, seen_now)}

    cands = address_candidates(c, seen_now)
    if not cands:
        return None
    best = cands[0]
    tier_label = {T_CONFIRMED: "owner-CONFIRMED", T_SUBMITTED: "self-submitted",
                  T_LOOKUP: "inferred (single-address lookup)",
                  T_AMBIGUOUS: "AMBIGUOUS"}[best["tier"]]

    # Sellability first: it doesn't matter how strong the ownership evidence is if we
    # can't sell the place. PropRadar covers FOR SALE (incl. the Form 6 window via
    # days_on_market); it has NO lease data, so lease is reported as unknown, never
    # assumed clear.
    best_addr = (status.get(best["address"], {}) or {}).get("canonical_address") \
        or best["address"]
    # A postcode disagreement is a CORRECTION, not a disqualification — we hold the
    # right answer (QLD cadastral), so use it and say so. Only an address we cannot
    # verify at all blocks: there is nothing to put on the envelope.
    addr_problem = (status.get(best["address"], {}) or {}).get("address_conflict")
    addr_note = ""
    if addr_problem and "UNVERIFIED" in addr_problem:
        return {"via": f"Postal address ({tier_label}) — {best['basis']}",
                "detail": best_addr, "mail_ok": f"NO — {addr_problem}",
                "candidates": cands, "tier": best["tier"]}
    if addr_problem:
        addr_note = f" [address corrected: {addr_problem}]"
    st = status.get(best["address"])
    sell_note = ""
    if st is not None:
        sellable, why = ms.verdict(st)
        sell_note = why
        if not sellable:
            return {"via": f"Postal address ({tier_label}) — {best['basis']}",
                    "detail": st.get("canonical_address") or best["address"],
                    "mail_ok": why, "candidates": cands, "tier": best["tier"]}

    if best["tier"] == T_AMBIGUOUS:
        others = len([x for x in cands if x["tier"] == T_AMBIGUOUS])
        ok = (f"NO — we do not know which of {others} addresses is theirs" if others > 1
              else "NO — no evidence this address is theirs")
    elif best["tier"] == T_CONFIRMED:
        ok = "Yes — they confirmed this is their home"
    elif best["tier"] == T_SUBMITTED:
        ok = "Probably — they submitted it, but that isn't proof of ownership"
    else:
        ok = "Maybe — inferred only, no confirmation"
    # Carry the real sellability finding rather than a hardcoded caveat — whether the
    # lease side was actually checked depends on rental_listings being populated.
    if not ok.startswith("NO") and sell_note:
        ok += f". {sell_note}{addr_note}"

    return {"via": f"Postal address ({tier_label}) — {best['basis']}",
            "detail": (status.get(best["address"], {}) or {}).get("canonical_address")
                      or best["address"],
            "mail_ok": ok, "candidates": cands, "tier": best["tier"]}


def cadastral_address(gc_db, slug: str) -> tuple[str | None, str | None]:
    """(postable address, caveat) rebuilt from the QLD cadastral fields.

    Far more reliable than reconstructing from the slug — and it exposes a trap: the
    leading number in a slug like `13-4-yodelay-street-varsity-lakes` is the LOT
    (LOT 13, PLAN GTP4152, STREET_NO_1 4), NOT necessarily the unit number. Writing
    "13/4 Yodelay Street" on an envelope is a guess. We surface that caveat rather
    than printing a confident address we can't stand behind.
    """
    for sub in ("robina", "varsity_lakes", "burleigh_waters"):
        d = gc_db[sub].find_one({"url_slug": slug})
        if not d:
            continue
        if d.get("address"):
            return d["address"], None
        no1, name = d.get("STREET_NO_1"), d.get("STREET_NAME")
        if not (no1 and name):
            return None, None
        street = " ".join(str(x).title() for x in
                          [no1, name, d.get("STREET_TYPE")] if x)
        loc = str(d.get("LOCALITY") or "").title()
        addr = f"{street}, {loc} QLD {d.get('POSTCODE') or ''}".strip()
        caveat = None
        if d.get("UNIT_TYPE") and d.get("LOT"):
            caveat = (f"unit number UNCONFIRMED — cadastral has LOT {d['LOT']} of plan "
                      f"{d.get('PLAN')} at {street}; the slug's leading number is the "
                      f"LOT, not necessarily the unit")
        return addr, caveat
    return None, None


def market_status_for(addresses: list[str], db, gc_db, max_calls: int,
                      resolved: dict | None = None) -> dict[str, dict]:
    """address -> market status, from PropRadar PLUS our own listings as a 2nd source.

    Two sources because neither is complete: PropRadar indexes listings statewide but
    we've seen it miss addresses, and our Gold_Coast scrape is authoritative only for
    the three core suburbs. A hit in EITHER blocks the mail.
    """
    import rental_listings_sync as rls
    import onthehouse_listings_sync as ohl
    resolved = resolved or {}
    lease_ok = db[rls.COLL].count_documents({"active": True}) > 0
    # Same empty-collection guard as the lease side: an unpopulated collection must read
    # as "not checked", never as "nothing is for sale".
    oth_ok = db[ohl.COLL].count_documents({"active": True}) > 0

    gc_listed = set()
    for sub in ("robina", "varsity_lakes", "burleigh_waters"):
        for d in gc_db[sub].find({"listing_status": "for_sale"}, {"address": 1}):
            if d.get("address"):
                gc_listed.add(ms._key(d["address"]))

    spend, out = {"calls": 0}, {}
    for a in addresses:
        if spend["calls"] >= max_calls:
            out[a] = {"error": "PropRadar call budget reached",
                      "lease_status": ms.LEASE_UNKNOWN}
        else:
            out[a] = ms.check(a, db=db, spend=spend)
        # Lease side — a home the owner is leasing is not one we can sell.
        lease = rls.is_for_lease(db, a) if lease_ok else None
        # Sale side, third opinion. Domain and onthehouse overlap only 72% on live
        # houses; 31 addresses in offmarket_discovery were actively for sale and
        # invisible to us until this source was added.
        oth = ohl.is_listed(db, a) if oth_ok else None
        r = resolved.get(rls.address_key(a) or "") or {}
        bad = [c for c in (r.get("conflicts") or []) if "misroute" in c or "UNVERIFIED" in c]
        out[a] = dict(out[a], gc_for_sale=ms._key(a) in gc_listed,
                      for_lease=lease, lease_checked=lease_ok,
                      oth_for_sale=oth, oth_checked=oth_ok,
                      address_conflict=(bad[0] if bad else None))
    sale_blocked = sum(1 for v in out.values()
                       if v.get("on_market") or v.get("gc_for_sale") or v.get("oth_for_sale"))
    oth_only = sum(1 for v in out.values()
                   if v.get("oth_for_sale") and not (v.get("on_market") or v.get("gc_for_sale")))
    lease_blocked = sum(1 for v in out.values() if v.get("for_lease"))
    print(f"  Sellability: {spend['calls']} PropRadar call(s), {len(out)} address(es) — "
          f"{sale_blocked} for sale ({oth_only} seen ONLY by onthehouse), "
          f"{lease_blocked} for lease"
          + ("" if lease_ok else " (LEASE DATA EMPTY — run rental_listings_sync.py)")
          + ("" if oth_ok else " (OTH SALE DATA EMPTY — run onthehouse_listings_sync.py)"))
    return out


def who_for(c: dict, reach_detail: str) -> str:
    name = (c.get("name") or "").strip()
    if name:
        return name
    email = (c.get("email") or "").strip()
    if email:
        return email
    return f"Anonymous — known by address: {reach_detail}"


def already_sent(c: dict, db) -> str:
    """What we have actually sent this person, from real send records."""
    out = []
    for comm in (c.get("communications") or []):
        d = str(comm.get("date") or "")[:10]
        subj = (comm.get("subject") or comm.get("type") or "").strip()
        if subj:
            out.append(f"{d} {subj}")
    email = (c.get("email") or "").strip().lower()
    if email:
        for s in db.email_sends.find({"to": {"$regex": f"^{email}$", "$options": "i"}}):
            d = str(s.get("sent_at") or "")[:10]
            out.append(f"{d} {s.get('subject') or s.get('type') or 'email'}")
    if not out:
        return "Nothing sent to them yet."
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return f"{len(uniq)} sent — " + "; ".join(uniq[-4:])


# ---- page labelling ----------------------------------------------------------
KNOWN_SUBURBS = ["burleigh-waters", "varsity-lakes", "robina", "burleigh-heads",
                 "mermaid-waters", "merrimac", "worongary", "clear-island-waters"]


def slug_to_address(slug: str) -> str:
    """'44-28-castello-circuit-varsity-lakes' -> '44/28 Castello Circuit, Varsity Lakes'.

    Splits the suburb off the tail and restores the unit separator, so a row reads as
    a real address rather than a slug with the punctuation stripped out.
    """
    s = (slug or "").strip("-")
    if not s:
        return "—"
    suburb = ""
    for k in KNOWN_SUBURBS:
        if s.endswith("-" + k):
            suburb = k.replace("-", " ").title()
            s = s[: -len(k) - 1]
            break
    parts = s.split("-")
    # leading "<unit>-<street no>" pair -> "unit/number"
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
        parts = [f"{parts[0]}/{parts[1]}"] + parts[2:]
    street = " ".join(w.capitalize() for w in parts)
    return f"{street}, {suburb}" if suburb else street


def own_slugs_for(c: dict) -> set[str]:
    """Slugs we have ACTUAL EVIDENCE belong to this contact — tier 1/2 only.

    The first version of this pooled `probable_address_slugs` (which is simply every
    report they ever opened) into "own", so a contact who browsed four mini-sites had
    all four called "their OWN home report" — while the Reach Via column named a
    different address. One row contradicted itself. Only confirmed/submitted counts.
    """
    return {x["slug"] for x in address_candidates(c)
            if x["tier"] <= T_SUBMITTED and x["slug"]}


def describe_path(path: str, category: str | None, suburb: str | None,
                  own: set[str] | None = None) -> tuple[str, str]:
    """(human label, rule tag) for one page path. `own` = this contact's own slugs."""
    own = own or set()
    p = (path or "").rstrip("/") or "/"
    parts = [x for x in p.split("/") if x]

    def minisite(slug: str, verb: str) -> tuple[str, str]:
        addr = slug_to_address(slug)
        if slug in own:
            return f"{verb} their OWN home report ({addr})", "own_minisite"
        return f"{verb} a home report for {addr} (not their own)", "other_minisite"

    if p == "/" or (parts and parts[0] == "news"):
        return "News & Research home", "article"
    if parts and parts[0] in ("market-intelligence", "market-metrics"):
        sub = (suburb or (parts[1].replace("-", " ") if len(parts) > 1 else "")).title()
        cat = category or (parts[2] if len(parts) > 2 else "overview")
        return f"{sub} market data — {CATEGORY_LABELS.get(cat, cat)}", cat
    if parts and parts[0] == "your-home":
        if len(parts) > 2 and parts[1] == "building":
            return minisite(parts[2], "waiting on")
        if len(parts) > 1:
            return minisite(parts[1], "opened")
        return "a home report", "other_minisite"
    if parts and parts[0] == "building":
        # interim "we're building it" page (see memory listed_vs_offmarket_guard)
        return minisite(parts[1], "waiting on") if len(parts) > 1 else ("a report being built", "other_minisite")
    if parts and parts[0] == "analyse-your-home":
        if len(parts) > 2 and parts[1] == "building":
            return minisite(parts[2], "waiting on")
        return "Analyse Your Home", "valuation"
    if parts and parts[0] == "off-market":
        if len(parts) > 1:
            addr = slug_to_address(parts[1])
            own_note = " — their OWN address" if parts[1] in own else ""
            return f"off-market report for {addr}{own_note}", "offmarket"
        return "off-market report", "offmarket"
    if parts and parts[0] == "property":
        # /property/<slug> — name the actual listing; "a for-sale listing" twice in a
        # row tells Will nothing he can act on.
        return (f"for-sale listing: {slug_to_address(parts[1])}" if len(parts) > 1
                else "a for-sale listing"), "for_sale"
    if parts and parts[0].startswith("for-sale"):
        return "for-sale listings", "for_sale"
    if parts and parts[0] == "articles":
        return f"article: {slug_to_address(parts[1]) if len(parts) > 1 else '—'}", "article"
    if parts and parts[0] == "discover":
        return "Discover feed", "for_sale"
    return p, ""


ADDRESS_ROUTES = {"your-home", "off-market", "building", "property"}


def path_address_slug(path: str) -> str | None:
    """The address slug a page is about, if any — used to catch a visitor looking at
    several different addresses in one sitting, which invalidates the owner-lookup
    read no matter what the stored CRM fields say."""
    parts = [x for x in (path or "").split("/") if x]
    if not parts:
        return None
    if parts[0] in ADDRESS_ROUTES and len(parts) > 1:
        return parts[2] if (parts[1] == "building" and len(parts) > 2) else parts[1]
    if parts[0] == "analyse-your-home" and len(parts) > 2 and parts[1] == "building":
        return parts[2]
    return None


def channel_for(ref_domain: str | None, utm_source: str | None) -> str:
    if utm_source:
        return f"utm_source={utm_source}"
    rd = (ref_domain or "").lower()
    if not rd or rd == "$direct":
        return "Direct / no referrer"
    if "google" in rd:
        return "Google organic"
    if "facebook" in rd or "fb" == rd:
        return "Facebook"
    if "bing" in rd:
        return "Bing organic"
    if "fieldsestate" in rd:
        return "Internal"
    return rd


def fmt_engaged(engaged_s: int, span_s: int) -> str:
    """Engaged reading time, with the wall-clock span alongside and clearly labelled.

    Never conflate the two: time_on_page milestones cap at 300s of ACTIVE time, so a
    tab left open for 40 minutes is 5 min of reading, not 40.
    """
    if engaged_s <= 0:
        return f"<10s measured (page span {span_s // 60}m)" if span_s >= 60 else "<10s measured"
    cap = "+" if engaged_s >= ENGAGED_CAP_S else ""
    eng = f"{engaged_s // 60}m{cap}" if engaged_s >= 60 else f"{engaged_s}s{cap}"
    if span_s >= engaged_s + 120:
        return f"{eng} engaged (tab open {span_s // 60}m)"
    return f"{eng} engaged"


# ---- visit assembly ----------------------------------------------------------
def build_visits(events: list[dict]) -> list[dict]:
    """Split one person's ordered events into visits (>VISIT_GAP_MIN gap = new visit)."""
    visits, cur = [], None
    for e in events:
        if cur is None or (e["ts"] - cur["end"]) > timedelta(minutes=VISIT_GAP_MIN):
            cur = {"start": e["ts"], "end": e["ts"], "events": []}
            visits.append(cur)
        cur["end"] = e["ts"]
        cur["events"].append(e)
    return visits


def summarise_visit(v: dict, own: set[str]) -> dict:
    """Collapse a visit's events into ordered pages with engaged time + rule tags."""
    pages, order = {}, []
    for e in v["events"]:
        path = e["path"] or "/"
        if path not in pages:
            label, tag = describe_path(path, e.get("category"), e.get("suburb"), own)
            pages[path] = {"label": label, "tag": tag, "engaged": 0,
                           "first": e["ts"], "last": e["ts"]}
            order.append(path)
        p = pages[path]
        p["last"] = e["ts"]
        if e["event"] == "time_on_page" and e.get("duration"):
            p["engaged"] = max(p["engaged"], int(e["duration"]))
    ref = next((e.get("ref_domain") for e in v["events"] if e.get("ref_domain")), None)
    utm = next((e.get("utm_source") for e in v["events"] if e.get("utm_source")), None)
    city = next((e.get("city") for e in v["events"] if e.get("city")), "")
    country = next((e.get("country") for e in v["events"] if e.get("country")), "")
    return {
        "seen_slugs": {x for x in (path_address_slug(p) for p in order) if x},
        "pages": [dict(pages[p], path=p) for p in order],
        "channel": channel_for(ref, utm),
        "location": ", ".join(x for x in (city, country) if x) or "Unknown",
        "start": v["start"], "end": v["end"],
    }


def narrative(c: dict, s: dict, prior_days: int, first_seen: str, reach: dict) -> str:
    """The verbose, plain-English line Will actually reads."""
    bits = []
    # Counted in DAYS, not visits — PostHog gives us visit_dates, and two sessions on
    # one day must not be reported as two separate "visits".
    if first_seen:
        d = f"active on {prior_days} earlier day(s), first seen {first_seen}" if prior_days \
            else f"known to us since {first_seen}"
        bits.append(f"Returning visitor — {d}. Arrived via {s['channel']}, from {s['location']}.")
    else:
        bits.append(f"First recorded visit. Arrived via {s['channel']}, from {s['location']}.")

    n = len(s["pages"])
    bits.append(f"Viewed {n} page{'s' if n != 1 else ''}:")
    for p in s["pages"]:
        span = int((p["last"] - p["first"]).total_seconds())
        bits.append(f"  • {p['label']} — {fmt_engaged(p['engaged'], span)}")

    deep = [p for p in s["pages"] if p["engaged"] >= 120]
    if deep:
        bits.append("Read " + " and ".join(f"“{p['label']}”" for p in deep[:2]) +
                    " properly, not a bounce.")
    bits.append(f"Best contact — {reach['via']}: {reach['detail']}")
    bits.append(f"Safe to contact? {reach['mail_ok']}")
    return "\n".join(bits)


def candidates_cell(cands: list[dict], status: dict, caveats: dict) -> str:
    """Every address on file with its evidence, so ambiguity is visible not hidden."""
    tier_name = {T_CONFIRMED: "CONFIRMED", T_SUBMITTED: "submitted",
                 T_LOOKUP: "inferred", T_AMBIGUOUS: "no evidence"}
    lines = []
    for x in cands:
        st = status.get(x["address"]) or {}
        if st.get("on_market"):
            dom = st.get("days_on_market")
            mark = f" [FOR SALE{f' — {dom}d on market' if dom is not None else ''}]"
        elif st.get("on_market") is None:
            mark = " [sale status UNVERIFIED]"
        else:
            mark = ""
        if (status.get(x["address"]) or {}).get("for_lease"):
            mark += " [FOR LEASE]"
        cav = caveats.get(x["address"])
        lines.append(f"[{tier_name[x['tier']]}] "
                     f"{st.get('canonical_address') or x['address']}{mark} — {x['basis']}"
                     + (f" ⚠ {cav}" if cav else ""))
    return "\n".join(lines) or "—"


def opportunity(s: dict, c: dict) -> str:
    tags = {p["tag"] for p in s["pages"]}
    for tag, text in OPPORTUNITY_RULES:
        if tag in tags:
            return text
    return "General site activity — no specific content match."


# ---- gather ------------------------------------------------------------------
def identity_key(c: dict) -> str:
    """Collapse duplicate crm_contacts docs describing the same human.

    crm_sync keys contacts on a distinct_id hash, so one person browsing on two
    devices (or re-identified mid-journey) gets two documents with identical
    addresses — which would produce two Activity rows for the same visit and, worse,
    two mail-outs to the same letterbox. Prefer a confirmed/submitted address as the
    identity; fall back to the contact id.
    """
    email = (c.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    for x in address_candidates(c):
        if x["tier"] <= T_SUBMITTED:
            return f"addr:{(x['slug'] or x['address']).lower()}"
    return f"id:{c.get('_id')}"


def reachable_contacts(db) -> dict[str, dict]:
    """distinct_id -> contact doc, for every contact we can actually reach."""
    out = {}
    for c in db.crm_contacts.find({}):
        if not reach_for(c):
            continue
        ids = list(c.get("posthog_ids") or [])
        if c.get("primary_posthog_id"):
            ids.append(c["primary_posthog_id"])
        for i in ids:
            if i and i not in INTERNAL_IDS:
                out[i] = c
    return out


def fetch_events(dids: list[str], hours: int) -> dict[str, list[dict]]:
    """Raw PostHog events per distinct_id for the lookback window, oldest first."""
    by_person: dict[str, list[dict]] = {}
    CHUNK = 150  # keep the IN(...) clause a sane size
    for i in range(0, len(dids), CHUNK):
        chunk = dids[i:i + CHUNK]
        id_list = ", ".join("'" + d.replace("'", "") + "'" for d in chunk)
        bots = ", ".join("'" + b + "'" for b in BOT_CITIES)
        rows = posthog_query(f"""
SELECT distinct_id, timestamp, event, properties.$pathname, properties.duration,
       properties.category, properties.suburb, properties.$referring_domain,
       properties.utm_source, properties.$geoip_city_name, properties.$geoip_country_name
FROM events
WHERE distinct_id IN ({id_list})
  AND timestamp > now() - INTERVAL {int(hours)} HOUR
  AND (properties.$geoip_city_name IS NULL OR properties.$geoip_city_name NOT IN ({bots}))
ORDER BY distinct_id, timestamp ASC
LIMIT 50000
""")
        for r in rows:
            ts = r[1]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            by_person.setdefault(r[0], []).append({
                "ts": ts, "event": r[2], "path": r[3], "duration": r[4],
                "category": r[5], "suburb": r[6], "ref_domain": r[7],
                "utm_source": r[8], "city": r[9], "country": r[10],
            })
    return by_person


def known_before(c: dict, when: datetime) -> str | None:
    """Was this contact already known to us before this visit? Returns the date we
    first knew them, or None. Covers both a repeat site visitor and an FB lead-ad
    contact browsing the site for the first time — both are 'returning' to us."""
    cands = []
    for k in ("first_seen", "created_at"):
        v = c.get(k)
        if v:
            cands.append(str(v)[:10])
    for d in ((c.get("journey") or {}).get("visit_dates") or []):
        cands.append(str(d)[:10])
    cands = [d for d in cands if d and d < when.astimezone(AEST).strftime("%Y-%m-%d")]
    return min(cands) if cands else None


def build_rows(db, gc_db, hours: int, include_first: bool, max_pr: int = 150) -> list[dict]:
    contacts = reachable_contacts(db)
    if not contacts:
        return []
    events = fetch_events(sorted(contacts), hours)

    # Resolve every address we might name to a POSTABLE form (cadastral beats a
    # slug reconstruction) and then ask PropRadar whether it's sellable at all.
    # normalize_addresses.py has already resolved every stored address to the QLD
    # cadastral `complete_address` (correct unit number, street type and postcode) and
    # recorded any conflict. Prefer that over reconstructing from a slug.
    import rental_listings_sync as _rls
    resolved = {d["_id"]: d for d in db["address_resolution"].find({})}
    addr_fix, caveats = {}, {}
    for c in contacts.values():
        for x in address_candidates(c):
            if x["address"] in addr_fix or x["address"] in caveats:
                continue
            r = resolved.get(_rls.address_key(x["address"]) or "")
            if r:
                if r.get("canonical") and r["canonical"] != x["address"]:
                    addr_fix[x["address"]] = r["canonical"]
                if r.get("conflicts"):
                    caveats[x["address"]] = "; ".join(r["conflicts"])
                continue
            a, cav = cadastral_address(gc_db, x["slug"]) if x["slug"] else (None, None)
            if a:
                addr_fix[x["address"]] = a
            if cav:
                caveats[x["address"]] = cav
    # Only resolve addresses that could plausibly be mailed: each contact's BEST
    # candidate, plus anything with real ownership evidence. The long tail of
    # "a report they opened" is already disqualified on evidence, so spending a
    # PropRadar call on it buys nothing.
    wanted = set()
    for c in contacts.values():
        cands = address_candidates(c)
        if not cands:
            continue
        wanted.add(addr_fix.get(cands[0]["address"], cands[0]["address"]))
        for x in cands:
            if x["tier"] <= T_SUBMITTED:
                wanted.add(addr_fix.get(x["address"], x["address"]))
    wanted = sorted(wanted)
    status = market_status_for(wanted, db, gc_db, max_pr, resolved)
    # index by the pre-fix address too, so lookups by either form hit
    for orig, fixed in addr_fix.items():
        if fixed in status:
            status[orig] = status[fixed]

    rows = []
    for did, evs in events.items():
        c = contacts[did]
        cid = identity_key(c)
        own = own_slugs_for(c)
        for v in build_visits(sorted(evs, key=lambda e: e["ts"])):
            first_seen = known_before(c, v["start"])
            if not first_seen and not include_first:
                continue
            # Earlier days only — a same-day earlier session isn't an "earlier day".
            vday = v["start"].astimezone(AEST).strftime("%Y-%m-%d")
            prior_dates = len({str(d)[:10] for d in
                               ((c.get("journey") or {}).get("visit_dates") or [])
                               if str(d)[:10] < vday})
            s = summarise_visit(v, own)
            local = v["start"].astimezone(AEST)
            reach = reach_for(c, status, s["seen_slugs"])
            rows.append({
                "activity_id": f"{cid}:{v['start'].isoformat()}",
                "date": local.strftime("%Y-%m-%d"),
                "time": local.strftime("%H:%M"),
                "who": who_for(c, reach["detail"]),
                "mail_ok": reach["mail_ok"],
                "contact_detail": reach["detail"],
                "evidence": reach["via"],
                "all_addresses": candidates_cell(reach["candidates"], status, caveats),
                "visit": f"{prior_dates} earlier day(s)" if first_seen else "first visit",
                "channel": s["channel"],
                "location": s["location"],
                "engaged": fmt_engaged(max((p["engaged"] for p in s["pages"]), default=0),
                                       int((v["end"] - v["start"]).total_seconds())),
                "what": narrative(c, s, prior_dates, first_seen, reach),
                "already_sent": already_sent(c, db),
                "opportunity": opportunity(s, c),
                "_sort": v["start"],
            })
    rows.sort(key=lambda r: r["_sort"])
    # Same human, same visit, two contact docs -> one row (see identity_key).
    dedup = {}
    for r in rows:
        dedup[r["activity_id"]] = r
    return sorted(dedup.values(), key=lambda r: r["_sort"])


def row_values(r: dict) -> list[str]:
    return [r["date"], r["time"], r["who"], r["mail_ok"], r["contact_detail"],
            r["evidence"], r["all_addresses"], r["visit"], r["channel"],
            r["location"], r["engaged"], r["what"], r["already_sent"],
            r["opportunity"], r["activity_id"]]


# ---- sheet -------------------------------------------------------------------
def ensure_tab(svc, ssid):
    sid = tab_id(svc, ssid, TAB)
    if sid is not None:
        return sid
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "addSheet": {"properties": {"title": TAB, "gridProperties": {
            "rowCount": 2000, "columnCount": len(HEADERS), "frozenRowCount": 1}}}}]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{TAB}'!A1", valueInputOption="RAW",
        body={"values": [HEADERS]}).execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": ACTIVITY_ID_COL, "endIndex": ACTIVITY_ID_COL + 1},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        # "What They Did" is a multi-line narrative — it must wrap, or the row is unreadable.
        {"repeatCell": {
            "range": {"sheetId": sid, "startColumnIndex": WRAP_COLS[0],
                      "endColumnIndex": WRAP_COLS[1]},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                           "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"updateDimensionProperties": {  # "All addresses on file"
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 6, "endIndex": 7},
            "properties": {"pixelSize": 420}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {  # "What They Did"
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 11, "endIndex": 12},
            "properties": {"pixelSize": 520}, "fields": "pixelSize"}},
    ]}).execute()
    print(f"Created '{TAB}' tab.")
    return sid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--hours", type=int, default=26,
                    help="PostHog lookback (default 26 — nightly with overlap)")
    ap.add_argument("--include-first-visit", action="store_true",
                    help="also log visits by contacts we only met during this visit")
    ap.add_argument("--max-pr", type=int, default=150,
                    help="cap PropRadar API calls per run (Hobby tier = 20k/month)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="drop the tab and the ledger and rewrite from scratch — for "
                         "column-schema changes; discards any manual edits on the tab")
    args = ap.parse_args()

    set_env_from_file()
    client = get_client()
    db = client["system_monitor"]

    try:
      with job_run("engagement_activity_to_sheet", cadence_hours=24,
                   title="Known-Contact Activity → Live Leads Tracker") as beat:
          rows = build_rows(db, client["Gold_Coast"], args.hours,
                            args.include_first_visit, args.max_pr)

          if args.rebuild and not args.dry_run:
              svc0 = get_sheets()
              old = tab_id(svc0, args.spreadsheet_id, TAB)
              if old is not None:
                  svc0.spreadsheets().batchUpdate(
                      spreadsheetId=args.spreadsheet_id,
                      body={"requests": [{"deleteSheet": {"sheetId": old}}]}).execute()
              db[LEDGER_COLL].delete_many({})
              print(f"[rebuild] dropped '{TAB}' + ledger.")

          seen = {d["_id"] for d in db[LEDGER_COLL].find({}, {"_id": 1})}
          new = [r for r in rows if r["activity_id"] not in seen]

          print(f"{len(rows)} visit(s) by reachable contacts in the last {args.hours}h; "
                f"{len(new)} not yet logged.")
          for r in new:
              print(f"\n--- {r['date']} {r['time']}  {r['who']}")
              print(f"    MAIL? {r['mail_ok']}")
              print(f"    best: {r['contact_detail']}  ({r['evidence']})")
              print("    addresses on file:\n      " + r['all_addresses'].replace("\n","\n      "))
              print("    " + r["what"].replace("\n", "\n    "))
              print(f"    opportunity: {r['opportunity']}")

          beat.detail = f"{len(new)} new activity row(s)"
          beat.metrics = {"visits_seen": len(rows), "rows_added": 0 if args.dry_run else len(new)}

          if args.dry_run or not new:
              return

          svc = get_sheets()
          sid = ensure_tab(svc, args.spreadsheet_id)
          # Newest FIRST: the whole batch is written downward from row 2 in one update,
          # so the first element of the list is the row that ends up directly under the
          # header. (Sorting ascending here would bury today's activity at the bottom.)
          new.sort(key=lambda r: r["_sort"], reverse=True)
          svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
              "insertDimension": {
                  "range": {"sheetId": sid, "dimension": "ROWS",
                            "startIndex": 1, "endIndex": 1 + len(new)},
                  "inheritFromBefore": False}}]}).execute()
          svc.spreadsheets().values().update(
              spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A2",
              valueInputOption="RAW", body={"values": [row_values(r) for r in new]}).execute()

          ts = datetime.now(AEST).isoformat()
          for r in new:
              db[LEDGER_COLL].update_one({"_id": r["activity_id"]},
                                         {"$setOnInsert": {"logged_at": ts,
                                                           "date": r["date"],
                                                           "who": r["who"]}}, upsert=True)
          beat.metrics = {"visits_seen": len(rows), "rows_added": len(new)}
          print(f"\nDone. {len(new)} row(s) added to '{TAB}'.")


    finally:
        client.close()

if __name__ == "__main__":
    main()
