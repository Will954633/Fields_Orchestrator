#!/usr/bin/env python3
"""
seller_intent.py — a CRM enrichment layer "over the top" of lead_worklist.

For each person in the worklist it cross-references two things the base
lead_intelligence pipeline does NOT connect:

  1. Their OWN property's live listing status, and — crucially — HOW LONG it has
     been for sale (the base pipeline's `status_age_days` measures how fresh OUR
     data is, not time-on-market; this computes real days-on-market).
  2. Every OTHER current listing they viewed in their PostHog journey
     (organic_journeys.pages -> /property/, /your-home/, /off-market/, /sold/
     slugs -> resolved to the live listing + its status/price/days-on-market).

It then draws a seller-intent conclusion (Will 2026-07-28):
  - Own home FOR SALE and long on market   -> likely frustrated vendor /
    second-opinion candidate (e.g. 41 Quambone St Worongary: 364 days at
    $5.15-5.65M with Harcourts).
  - Own home NOT listed but viewing live listings -> probable seller weighing a
    move / researching the market -> pre-market approach candidate.

Non-invasive: writes ONLY `lead_worklist.seller_intent`. It never touches the
base pipeline's priority/reason/signals (owned by lead_intelligence.py) or the
human-dismissal fields.

Usage:
  python3 scripts/samantha/seller_intent.py --address quambone --dry-run
  python3 scripts/samantha/seller_intent.py --lead-key "addr:41quambone..."
  python3 scripts/samantha/seller_intent.py --all
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from shared.db import get_client  # noqa: E402

try:
    from src.mongo_client_factory import cosmos_retry  # noqa: E402
except Exception:  # pragma: no cover
    def cosmos_retry(fn):
        return fn()

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None

NOW = datetime.now(timezone.utc)
STALE_DOM_DAYS = 90  # a listing on market longer than this reads as "stale / frustrated vendor"
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]  # expiry-monitor scan scope

# Paths that point at a specific property (the slug is the last segment).
LISTING_PATH_RE = re.compile(
    r"^/(?:property|sold|off-market|your-home|analyse-your-home/building)/([a-z0-9][a-z0-9\-]+?)/?$"
)


# ------------------------------------------------------------------ helpers ---
def _dom_from_listing(d: dict):
    """Days the property has been on market. Prefer first_listed_timestamp (accurate
    to today); fall back to the scraped days_on_domain."""
    ts = d.get("first_listed_timestamp")
    if ts:
        try:
            dt = datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")
            return (NOW.replace(tzinfo=None) - dt).days
        except Exception:
            pass
    try:
        return int(d.get("days_on_domain"))
    except Exception:
        return None


def _price_display(d: dict):
    return d.get("price") or d.get("listing_price") or None


def build_suburb_index(gc_db):
    """[(hyphenated-suburb, collection_name)] sorted longest-first, for slug suffix match."""
    skip = ("precomputed", "address_", "system", "fci", "indexed", "_")
    colls = [x for x in gc_db.list_collection_names() if not x.startswith(skip)]
    pairs = [(c.replace("_", "-"), c) for c in colls]
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def resolve_slug(gc_db, slug: str, suburb_index):
    """Resolve a url_slug to its live Gold_Coast listing doc (any GC suburb)."""
    if not slug:
        return None
    for hy, coll in suburb_index:
        if slug == hy or slug.endswith("-" + hy):
            d = gc_db[coll].find_one({"url_slug": slug})
            if d:
                return d
            break  # suburb matched but slug not found — don't scan every collection
    return None


def listing_brief(d: dict):
    if not d:
        return None
    status = d.get("listing_status")
    return {
        "url_slug": d.get("url_slug"),
        "address": d.get("address"),
        "suburb": d.get("suburb") or d.get("LOCALITY"),
        "listing_status": status,
        "price": _price_display(d),
        "days_on_market": _dom_from_listing(d) if status == "for_sale" else None,
        "bedrooms": d.get("bedrooms") or d.get("BEDROOMS"),
        "agency": d.get("agency"),
    }


def extract_listing_slugs(pages):
    seen, out = set(), []
    for p in pages or []:
        if not isinstance(p, str):
            continue
        m = LISTING_PATH_RE.match(p.split("?")[0])
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def lead_distinct_ids(lead: dict, sm) -> set:
    """Every PostHog distinct_id we can tie to this lead (report owner, extra, offmarket)."""
    ids = set()
    ex = lead.get("extra") or {}
    if ex.get("posthog_distinct_id"):
        ids.add(ex["posthog_distinct_id"])
    for o in lead.get("origins") or []:
        if o.get("collection") == "property_reports" and ObjectId:
            try:
                rep = sm["property_reports"].find_one(
                    {"_id": ObjectId(o["id"])}, {"owner.posthog_distinct_id": 1})
                did = ((rep or {}).get("owner") or {}).get("posthog_distinct_id")
                if did:
                    ids.add(did)
            except Exception:
                pass
    for o in lead.get("origins") or []:
        if o.get("collection") == "posthog_behavior" and o.get("id"):
            ids.add(o["id"])
    lk = str(lead.get("lead_key", ""))
    if lk.startswith("offmarket_view:") or lk.startswith("behavior:"):
        ids.add(lk.split(":", 1)[1])
    return ids


def journeys_for(sm, distinct_ids):
    pages, sessions = [], 0
    if not distinct_ids:
        return pages, sessions
    for j in sm["organic_journeys"].find({"distinct_id": {"$in": list(distinct_ids)}}):
        sessions += 1
        pages.extend(j.get("pages") or [])
    return pages, sessions


def own_property_brief(lead: dict, gc_db, suburb_index):
    """Resolve the lead's OWN home -> (brief, own_slug).

    1st choice: the report_slug they generated (full gc_doc -> real days-on-market).
    Fallback:   the base pipeline's already-resolved `property` sub-doc (gives the
                listing STATUS + price for address-only leads, but no days-on-market).
    """
    slug = (lead.get("extra") or {}).get("report_slug")
    d = resolve_slug(gc_db, slug, suburb_index) if slug else None
    if d:
        return listing_brief(d), slug
    p = lead.get("property") or {}
    if p.get("resolved_property_id"):
        return {
            "url_slug": None,
            "address": lead.get("address"),
            "suburb": p.get("suburb"),
            "listing_status": p.get("listing_status"),
            "price": p.get("price"),
            "days_on_market": None,  # unavailable without the report slug -> full doc
            "bedrooms": p.get("bedrooms"),
            "resolved_via": "base_pipeline",
        }, None
    return None, None


# ============================ behavioral signals =============================
# PostHog event signals that reveal intent, beyond raw pageviews. Loaded once per
# run into BEHAV (keyed by distinct_id) and merged across a lead's distinct_ids.
BEHAV: dict = {}
BEHAV_DAYS = 45


def load_behavioral(days=BEHAV_DAYS):
    """One HogQL sweep of intent-bearing events -> {distinct_id: signals}."""
    global BEHAV
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from crm_sync import posthog_query
    except Exception as e:  # noqa: BLE001
        print(f"[behavioral] PostHog unavailable ({e}); behavioral signals skipped")
        BEHAV = {}
        return BEHAV
    try:
        rows = posthog_query(f"""
SELECT distinct_id,
  uniq(properties.$session_id) AS sessions,
  countIf(event='$pageview') AS pv,
  toString(min(timestamp)) AS first_seen,
  toString(max(timestamp)) AS last_seen,
  countIf(event='analyse_home_build_complete') AS ayh_build,
  countIf(event='forsale_ladder_complete' AND toString(properties.opted_in) IN ('true','True','1')) AS buyer_optin,
  countIf(event='forsale_ladder_answer') AS ladder_ans,
  countIf(event='v3_seller_anchor_view') AS seller_anchor,
  countIf(event='price_alert_submit_success') AS price_alert_set,
  countIf(event='minisite_tab') AS minisite_tab,
  countIf(event='offmarket_report_view') AS offmkt,
  countIf(event='property_view') AS prop_view,
  countIf(properties.$pathname LIKE '%sell-now%') AS sellnow,
  arrayFilter(x -> x != '', groupUniqArray(toString(properties.search_query))) AS searches,
  argMax(properties.$geoip_city_name, timestamp) AS city,
  argMax(properties.$geoip_country_name, timestamp) AS country
FROM events
WHERE timestamp > now() - INTERVAL {int(days)} DAY
GROUP BY distinct_id
HAVING pv >= 1
ORDER BY sessions DESC
LIMIT 50000
""")
    except Exception as e:  # noqa: BLE001
        # Do NOT degrade to empty. Behavioral signals ARE the seller-intent story —
        # without them every lead scores "no_cross_signal" and the Situation column
        # quietly goes blank, which looks identical to "this lead has no intent".
        # posthog_query already retried transient failures before raising, so a
        # failure here is real: fail the run loudly (job_run -> ERROR) instead.
        print(f"[behavioral] PostHog query failed ({e}) — aborting rather than "
              f"writing story-less seller_intent over good data")
        raise
    BEHAV = {}
    for r in rows:
        (did, sessions, pv, first_seen, last_seen, ayh_build, buyer_optin, ladder_ans,
         seller_anchor, price_alert_set, minisite_tab, offmkt, prop_view, sellnow, searches,
         city, country) = r
        BEHAV[did] = dict(
            sessions=sessions, pageviews=pv, first_seen=first_seen, last_seen=last_seen,
            ayh_build=ayh_build, buyer_optin=buyer_optin, ladder_answered=ladder_ans,
            seller_anchor=seller_anchor, price_alert_set=price_alert_set, minisite_tab=minisite_tab,
            offmarket_views=offmkt, property_views=prop_view, sell_now_landings=sellnow,
            address_searches=[s for s in (searches or []) if s and s != "null"],
            city=city, country=country)
    print(f"[behavioral] loaded {len(BEHAV)} people from PostHog ({days}d)")
    return BEHAV


_COUNT_KEYS = ("sessions", "pageviews", "ayh_build", "buyer_optin", "ladder_answered",
               "seller_anchor", "price_alert_set", "minisite_tab", "offmarket_views",
               "property_views", "sell_now_landings")


def merge_behavioral(distinct_ids):
    agg = {k: 0 for k in _COUNT_KEYS}
    agg.update(address_searches=[], first_seen=None, last_seen=None, city=None)
    for did in distinct_ids or []:
        b = BEHAV.get(did)
        if not b:
            continue
        for k in _COUNT_KEYS:
            agg[k] += b.get(k, 0) or 0
        agg["address_searches"] += b.get("address_searches") or []
        agg["city"] = agg["city"] or b.get("city")
        fs, ls = b.get("first_seen"), b.get("last_seen")
        if fs and (agg["first_seen"] is None or fs < agg["first_seen"]):
            agg["first_seen"] = fs
        if ls and (agg["last_seen"] is None or ls > agg["last_seen"]):
            agg["last_seen"] = ls
    # Drop incremental-typing prefixes ("20 GLEN" when "20 GLEN EAG" is also present).
    uniq = list(dict.fromkeys(agg["address_searches"]))
    uniq = [s for s in uniq if not any(o != s and o.lower().startswith(s.lower()) for o in uniq)]
    agg["address_searches"] = uniq[:8]
    return agg


def behavioral_score(b):
    """Weighted intent score — strongest seller signals weighted highest."""
    return (b["ayh_build"] * 6 + b["sell_now_landings"] * 6 + b["buyer_optin"] * 5
            + b["minisite_tab"] * 4 + len(b["address_searches"]) * 3 + b["seller_anchor"] * 3
            + b["price_alert_set"] * 4 + b["ladder_answered"] * 2 + b["offmarket_views"]
            + b["property_views"] + min(b["sessions"], 10))


def _all_known_distinct_ids(sm):
    """Every distinct_id already tied to a worklist lead — so we don't double-surface."""
    known = set()
    for d in sm["lead_worklist"].find({}, {"extra": 1, "lead_key": 1, "origins": 1}):
        known |= lead_distinct_ids(d, sm)
    return known


def _anon_qualifies(b):
    """Threshold gate — a GENUINE intent bar so random browsers are never surfaced."""
    return (b["ayh_build"] >= 1                       # generated a valuation for an address
            or b["sell_now_landings"] >= 1            # landed on a 'sell now' page
            or b["buyer_optin"] >= 1                  # gave email to the weekly buyer brief
            or b["price_alert_set"] >= 1              # set a real price alert
            or b["seller_anchor"] >= 3                # heavy seller-content engagement
            or (b["sessions"] >= 4 and (b["property_views"] + b["offmarket_views"]) >= 3))


def surface_behavioral_leads(sm, dry_run=False):
    """Create worklist entries for anonymous HIGH-signal visitors not tied to any lead —
    so genuine intent with no contact/address is never missed. Threshold-gated (see
    _anon_qualifies) so noise stays out. Keyed 'behavior:<distinct_id>'; the normal
    enrichment pass then gives them a behavioral story."""
    if not BEHAV:
        load_behavioral()
    try:
        from crm_sync import INTERNAL_IDS, BOT_CITIES
    except Exception:
        INTERNAL_IDS, BOT_CITIES = set(), set()
    known = _all_known_distinct_ids(sm)
    n = 0
    for did, b in BEHAV.items():
        if did in known or did in INTERNAL_IDS:
            continue
        if (b.get("country") or "Australia") != "Australia" or (b.get("city") in BOT_CITIES):
            continue
        if not _anon_qualifies(b):
            continue
        key = f"behavior:{did}"
        n += 1
        if dry_run:
            continue
        cosmos_retry(lambda: sm["lead_worklist"].update_one(
            {"lead_key": key},
            {"$setOnInsert": {
                "lead_key": key, "email": "", "name": "", "phone": "", "address": "",
                "sources": ["site_behavior"], "is_test": False,
                "first_seen": b.get("first_seen"), "behavioral_surface": True},
             "$set": {"origins": [{"collection": "posthog_behavior", "id": did}],
                      "extra": {"posthog_distinct_id": did},
                      "last_seen": b.get("last_seen"), "updated_at": NOW}},
            upsert=True))
    print(f"[behavioral-surface] {n} anonymous high-signal lead(s) "
          f"{'(dry-run)' if dry_run else 'upserted'}")
    return n


def _dom_from_our_listing(d):
    """Days-on-market from our own scraped listing (first_listed_timestamp preferred)."""
    ts = d.get("first_listed_timestamp")
    if ts:
        try:
            dt = datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")
            return (NOW.replace(tzinfo=None) - dt).days
        except Exception:
            pass
    try:
        return int(d.get("days_on_domain"))
    except Exception:
        return None


def listing_expiry_monitor(sm, gc_db, suburbs=None, dry_run=False):
    """Scan current for-sale listings in target suburbs and CAPTURE the ones whose ~90-day
    Form 6 exclusive agency is nearing expiry as leads — the moment a vendor can switch or
    re-list (an already-listed home is only a lead as its agreement expires). Cheap: uses
    our own DOM; the enrichment pass PropRadar-verifies each captured lead afterwards.
    Alerts Will with the expiring set."""
    suburbs = suburbs or CORE_SUBURBS
    captured, alerts = 0, []
    for suburb in suburbs:
        for d in gc_db[suburb].find(
                {"listing_status": "for_sale"},
                {"address": 1, "url_slug": 1, "price": 1, "agency": 1, "agent_name": 1,
                 "first_listed_timestamp": 1, "days_on_domain": 1, "bedrooms": 1}):
            dom = _dom_from_our_listing(d)
            if dom is None:
                continue
            label, _reason, dte = listing_stage(dom)
            if label != "on_market_expiring":
                continue
            addr = d.get("address")
            if not addr:
                continue
            slug = d.get("url_slug")
            key = f"listing:{slug or re.sub(r'[^a-z0-9]+', '', addr.lower())}"
            alerts.append((addr, dom, dte, d.get("price"), d.get("agency")))
            captured += 1
            if dry_run:
                continue
            cosmos_retry(lambda: sm["lead_worklist"].update_one(
                {"lead_key": key},
                {"$setOnInsert": {"lead_key": key, "email": "", "name": "", "phone": "",
                                  "sources": ["listing_expiry"], "is_test": False, "first_seen": NOW},
                 "$set": {"address": addr,
                          "origins": [{"collection": "gc_listing", "id": str(d.get("_id"))}],
                          "extra": {"report_slug": slug, "agency": d.get("agency"),
                                    "agent_name": d.get("agent_name")},
                          "listing_expiry": {"days_on_market": dom, "days_to_expiry": dte,
                                             "agency": d.get("agency"), "price": d.get("price")},
                          "updated_at": NOW}},
                upsert=True))
    if alerts and not dry_run:
        _notify_expiring(alerts)
    print(f"[listing-expiry] {captured} near-expiry listing(s) captured as leads "
          f"{'(dry-run)' if dry_run else ''}")
    return captured


def _notify_expiring(alerts):
    """Telegram alert with listings whose ~90-day agency is nearing expiry (switch/re-list leads)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        alerts.sort(key=lambda a: a[2])  # soonest expiry first
        lines = [f"⏰ {len(alerts)} listing(s) nearing ~90-day agency expiry — switch/re-list leads:"]
        for addr, dom, dte, price, agency in alerts[:12]:
            lines.append(f"• {addr} — {dom}d on market, ~{dte}d to expiry, {price or '?'} via {agency or '?'}")
        send_message("\n".join(lines), parse_mode="")
    except Exception as e:  # noqa: BLE001
        print(f"(expiry Telegram alert skipped: {e})")


# ============================ PropRadar enrichment ==========================
_PR_CACHE: dict = {}


def pr_enrich(address):
    """On-demand PropRadar: listing status, real days-on-market, valuation, potential
    sell price, last sale (=> tenure + equity), attributes, price-cut count. Cached per
    address. ~2-3 calls; only call for genuinely high-intent leads (quota is 5000/mo)."""
    if not address:
        return None
    key = address.strip().lower()
    if key in _PR_CACHE:
        return _PR_CACHE[key]
    pc = re.search(r"\b(\d{4})\b", address)
    postcode = pc.group(1) if pc else None
    street = re.split(r",|\bQLD\b", address)[0].strip()
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "propradar"))
        import propradar_client as pr
        params = {"address": street}
        if postcode:
            params["postcode"] = postcode
        s, _ = pr.call("/properties/search", params)
    except Exception as e:  # noqa: BLE001
        _PR_CACHE[key] = {"error": str(e)[:80]}
        return _PR_CACHE[key]
    pid = s.get("property_id") or (s.get("matches") or [{}])[0].get("property_id")
    res = {"on_market": s.get("on_market"), "sold_record": s.get("sold_record_available"), "pid": pid}
    if pid:
        try:
            d, _ = pr.call(f"/properties/{pid}", {})
            lst = d.get("listing") or {}
            val = d.get("valuation") or {}
            ls = d.get("last_sale") or {}
            at = d.get("attributes") or {}
            res.update(dom=lst.get("days_on_market"), asking_low=lst.get("asking_price_low"),
                       asking_high=lst.get("asking_price_high"), sale_type=lst.get("sale_type"),
                       est_value=val.get("estimated_value"), est_conf=val.get("confidence"),
                       psp=d.get("potential_sell_price"), last_sale_price=ls.get("sold_price"),
                       last_sale_date=ls.get("sold_date"), bedrooms=at.get("bedrooms"),
                       land_sqm=at.get("land_size_sqm"), year_built=at.get("year_built"),
                       property_type=at.get("property_type"))
        except Exception:
            pass
        try:
            hist, _ = pr.call(f"/properties/{pid}/history", {})
            evs = hist.get("history") or []
            res["price_cuts"] = sum(1 for e in evs if e.get("event_type") == "price_change")
            listed = [e for e in evs if e.get("event_type") == "listed"]
            if listed:
                res["first_listed_date"] = listed[0].get("date")
            solds = [e for e in evs if e.get("event_type") == "sold"]
            if solds and not res.get("last_sale_price"):
                res["last_sale_price"] = solds[-1].get("price")
                res["last_sale_date"] = solds[-1].get("date")
        except Exception:
            pass
    _PR_CACHE[key] = res
    return res


def _years_since(datestr):
    if not datestr:
        return None
    try:
        d = datetime.strptime(str(datestr)[:10], "%Y-%m-%d")
        return round((NOW.replace(tzinfo=None) - d).days / 365.25, 1)
    except Exception:
        return None


def _money(v):
    try:
        return f"${int(v):,}"
    except Exception:
        return str(v) if v else "?"


# A home ALREADY listed is NOT a lead — they've just committed to a competing agent
# (Will 2026-07-28). They become a lead as the Form 6 exclusive agency agreement nears
# expiry. In QLD a sole/exclusive residential-sales appointment maxes at 90 days
# (Property Occupations Act 2014); the 90-day mark (and each renewal boundary) is the
# decision point to renew, switch agent, or withdraw.
FORM6_DAYS = 90
EXPIRY_WINDOW = 21  # days before a 90-day boundary that we treat as "nearing expiry"


def listing_stage(dom):
    """Classify an on-market listing by where it sits against the ~90-day agency term.
    Returns (label, reason, days_to_expiry)."""
    if dom is None:
        return ("on_market_active",
                "On the market (days-on-market unknown) — verify the agency stage before treating as a lead.", None)
    dte = (FORM6_DAYS - (dom % FORM6_DAYS)) % FORM6_DAYS   # days to next 90-day boundary (0 = at it)
    boundary = ((dom // FORM6_DAYS) + (0 if dom % FORM6_DAYS == 0 else 1)) * FORM6_DAYS or FORM6_DAYS
    if dom < FORM6_DAYS - EXPIRY_WINDOW:
        # Comfortably inside the first exclusive term.
        return ("on_market_fresh",
                f"Just listed with another agent (~{dom}d in) — their exclusive agency has ~{dte} days to run. "
                "NOT a lead yet: they've committed to a competitor. Watch for the ~90-day expiry, don't approach now.",
                dte)
    if dte <= EXPIRY_WINDOW:
        return ("on_market_expiring",
                f"Their exclusive agency is nearing expiry — ~{dte} days to the {boundary}-day mark, still unsold after {dom} days. "
                "The decision point to renew, switch agent, or withdraw. PRIME approach window: offer a candid read + re-list plan.",
                dte)
    return ("on_market_stale",
            f"On the market {dom} days — past the first 90-day agency term and still unsold. "
            "Renewed but struggling / likely frustrated vendor. Open to a second opinion.", dte)


def conclude(own, current_viewed, generated_minisite):
    own_status = (own or {}).get("listing_status")
    dom = (own or {}).get("days_on_market")
    n = len(current_viewed)
    addrs = ", ".join(v["address"] for v in current_viewed if v.get("address"))[:200]

    if own_status == "for_sale":
        label, reason, _ = listing_stage(dom)
        return (label, reason)
    if own_status == "withdrawn":
        return ("pre_market_withdrawn",
                "Own home recently WITHDRAWN from market — wait-and-see pre-market seller. High-intent.")

    own_resolved = own is not None  # we actually identified their home
    if own_resolved:
        # Home identified and NOT currently for sale/withdrawn (never-listed, sold, etc.)
        if n >= 1:
            return ("browsing_while_unlisted",
                    f"Own home is NOT currently listed, yet viewed {n} live listing(s) [{addrs}]. "
                    "Strong 'weighing a move / thinking of selling' signal — pre-market approach candidate."
                    + (" Also generated their own valuation mini-site." if generated_minisite else ""))
        return ("no_cross_signal", "Home identified, not listed, no active-listing cross-signal yet.")

    # We could NOT identify their home — a viewed listing is a weaker (home-unknown) signal.
    if n >= 1:
        return ("viewing_listings_home_unknown",
                f"Viewed {n} live listing(s) [{addrs}] but we have not tied a home to this person — "
                "could be a buyer, or a seller we can't yet confirm. Enrich identity before acting.")
    return ("no_cross_signal", "No active-listing cross-signal yet.")


READS = {
    "on_market_fresh": "Read: just listed with a COMPETING agent — not a lead yet (they've committed). "
                       "Approach: none now; auto-watch for the ~90-day agency expiry.",
    "on_market_expiring": "Read: their exclusive agency is at/near expiry with no sale — the single best moment to approach. "
                          "Approach: a candid 'why it hasn't sold + what I'd do differently' + concrete re-list plan.",
    "on_market_stale": "Read: past the first agency term and still unsold — frustrated vendor. "
                       "Approach: a second-opinion / re-list conversation; verify the listing is still live first.",
    "on_market_active": "Read: on the market, agency stage unclear. Approach: verify days-on-market before treating as a lead.",
    "pre_market_withdrawn": "Read: pulled the listing to wait — a warm pre-market seller. Approach: acknowledge the pause; offer a no-pressure repositioning view.",
    "browsing_while_unlisted": "Read: not listed but researching the market — probable seller weighing a move. Approach: a soft, helpful pre-market appraisal offer.",
    "engaged_owner_researching": "Read: an owner quietly testing the waters on their own home — early-stage but real seller intent. Approach: a warm, no-pressure 'here's what your home could be worth' follow-up.",
    "viewing_listings_home_unknown": "Read: engaged but unidentified — buyer or seller unclear. Approach: capture identity before pitching.",
    "no_cross_signal": "",
}


def build_story(lead, own, current_viewed, behav, pr, label):
    """A verbose, human-readable paragraph: who they likely are, what they did, what it
    means, and the best way to help — everything a person needs to tailor an approach."""
    bits = []
    addr = lead.get("address")
    city = behav.get("city")
    occ = (lead.get("occupancy") or {}).get("type")
    tenure = _years_since((pr or {}).get("last_sale_date")) or lead.get("years_held")

    # Anonymous (behaviour-surfaced) visitor with no address/contact captured yet.
    if not addr:
        loc = f"{city}-based " if city else ""
        bits.append(f"Anonymous {loc}visitor — no contact captured yet.")

    # Who
    who = []
    if city and addr and city.split(",")[0] not in addr:
        who.append(f"{city}-based")
    if occ and occ != "unknown":
        who.append(occ.replace("_", " "))
    if tenure:
        who.append(f"held ~{tenure}y")
    if who and addr:
        bits.append(f"{' '.join(who).capitalize()} owner of {addr}.")

    # Own-home situation (PropRadar-enriched where available)
    st = (own or {}).get("listing_status")
    if st == "for_sale":
        s = "Their home is on the market"
        dom = (pr or {}).get("dom") or (own or {}).get("days_on_market")
        if dom:
            s += f", ~{dom} days into the current campaign"
        if (own or {}).get("price"):
            s += f", asking {own['price']}"
        if (own or {}).get("agency"):
            s += f" via {own['agency']}"
        bits.append(s + ".")
        if pr and pr.get("est_value"):
            eq = ""
            if pr.get("last_sale_price"):
                gain = pr["est_value"] - pr["last_sale_price"]
                yr = str(pr.get("last_sale_date"))[:4] if pr.get("last_sale_date") else ""
                eq = f"; bought for {_money(pr['last_sale_price'])}{(' in ' + yr) if yr else ''} → ~{_money(gain)} unrealised gain"
            bits.append(f"PropRadar values it at {_money(pr['est_value'])} ({pr.get('est_conf')} confidence), "
                        f"potential sell price {_money(pr.get('psp'))}{eq}.")
            if pr.get("price_cuts"):
                bits.append(f"{pr['price_cuts']} price change(s) recorded — motivation/price-discovery signal.")
    elif st == "withdrawn":
        bits.append("Their home was recently withdrawn from the market — a wait-and-see vendor.")
    elif addr and label == "browsing_while_unlisted":
        note = "not currently listed"
        if pr and pr.get("est_value"):
            note += f"; PropRadar estimate {_money(pr['est_value'])}"
            if pr.get("last_sale_price"):
                note += f" vs {_money(pr['last_sale_price'])} paid"
        bits.append(f"Their home is {note}.")

    # Behaviour
    beh = []
    if behav.get("sessions"):
        beh.append(f"{behav['sessions']} session(s)/{behav['pageviews']} pageviews")
    if behav.get("ayh_build"):
        beh.append(f"generated our valuation {behav['ayh_build']}×")
    if behav.get("minisite_tab"):
        beh.append(f"opened their report's tabs {behav['minisite_tab']}× (incl. Messages)")
    if behav.get("sell_now_landings"):
        beh.append(f"visited a 'sell now' page {behav['sell_now_landings']}×")
    if behav.get("address_searches"):
        beh.append("searched " + ", ".join(behav["address_searches"][:3]))
    if behav.get("seller_anchor"):
        beh.append(f"read seller-focused content {behav['seller_anchor']}×")
    if behav.get("price_alert_set"):
        beh.append(f"set {behav['price_alert_set']} price alert(s) on a property")
    if behav.get("ladder_answered"):
        beh.append("answered the /for-sale-v3 buyer preferences quiz")
    if behav.get("buyer_optin"):
        beh.append("opted into the weekly buyer email (5 Property Friday)")
    if current_viewed:
        beh.append("also viewing live listing(s): "
                   + "; ".join(f"{v['address']} ({v.get('price')})" for v in current_viewed[:2]))
    if beh:
        bits.append("Behaviour: " + "; ".join(beh) + ".")

    if READS.get(label):
        bits.append(READS[label])
    return " ".join(bits).strip()


def analyze(lead: dict, sm, gc_db, suburb_index, pr_budget=None) -> dict:
    dids = lead.get("_dids")
    if dids is None:
        dids = lead_distinct_ids(lead, sm)
    pages, sessions = journeys_for(sm, dids)
    own, own_slug = own_property_brief(lead, gc_db, suburb_index)

    viewed = []
    for s in extract_listing_slugs(pages):
        if own_slug and s == own_slug:
            continue
        d = resolve_slug(gc_db, s, suburb_index)
        viewed.append(listing_brief(d) if d else {
            "url_slug": s, "address": s.replace("-", " ").title(),
            "listing_status": "unresolved", "price": None, "days_on_market": None})
    current_viewed = [v for v in viewed if v.get("listing_status") == "for_sale"]
    generated_minisite = any(o.get("collection") == "property_reports"
                             for o in lead.get("origins") or [])
    label, reason = conclude(own, current_viewed, generated_minisite)

    behav = merge_behavioral(dids)
    bscore = behavioral_score(behav)

    # Behavioral upgrade: an unlisted owner actively valuing their own home is a
    # pre-market seller signal the listing-status logic alone cannot see.
    if (label == "no_cross_signal"
            and (own or {}).get("listing_status") not in ("for_sale", "withdrawn")
            and (behav["ayh_build"] or behav["sell_now_landings"] or behav["minisite_tab"] >= 3)):
        label = "engaged_owner_researching"
        reason = ("Not listed, but actively researching their own home — generated a valuation / explored "
                  "their report / visited a sell-now page. Probable early-stage seller.")

    # PropRadar — rationed to genuine leads. A FRESH listing (well inside its exclusive
    # agency term) is NOT a lead (they just committed to a competitor), so skip paid enrichment.
    pr = None
    addr = lead.get("address")
    st = (own or {}).get("listing_status")
    own_dom = (own or {}).get("days_on_market")
    listing_lead = (st == "for_sale" and (own_dom is None or own_dom >= FORM6_DAYS - EXPIRY_WINDOW - 9)) \
        or st == "withdrawn"
    high_intent = (listing_lead or bscore >= 8
                   or label in ("on_market_stale", "on_market_expiring", "browsing_while_unlisted",
                                "engaged_owner_researching", "pre_market_withdrawn"))
    if addr and high_intent and (pr_budget is None or pr_budget[0] > 0):
        pr = pr_enrich(addr)
        if pr_budget is not None and pr and "error" not in pr:
            pr_budget[0] -= 1

    # Reclassify the listing with PropRadar's accurate CURRENT-campaign days-on-market
    # (our first_listed_timestamp can include earlier relists; the agency term restarts on
    # the current listing).
    if st == "for_sale":
        eff_dom = (pr or {}).get("dom")
        if eff_dom is None:
            eff_dom = own_dom
        label, reason, _dte = listing_stage(eff_dom)

    # Hotness by lead-worthiness: a fresh listing is NOT a lead -> deprioritise.
    listing_bonus = {"on_market_expiring": 22, "on_market_stale": 12, "pre_market_withdrawn": 14,
                     "on_market_fresh": -6}.get(label, 0)
    hotness = bscore + listing_bonus
    moment = None
    ls = behav.get("last_seen")
    recent = False
    if ls:
        try:
            recent = (NOW.replace(tzinfo=None) - datetime.strptime(ls[:19], "%Y-%m-%d %H:%M:%S")).days <= 3
        except Exception:
            recent = False
    if recent:
        if behav["ayh_build"]:
            moment = "Just generated a home valuation"
        elif behav["sell_now_landings"]:
            moment = "Just visited a 'sell now' page"
        elif behav["buyer_optin"]:
            moment = "Just opted into the weekly buyer email"
        elif behav["minisite_tab"] >= 3:
            moment = "Actively exploring their report (incl. Messages)"
        elif behav["seller_anchor"]:
            moment = "Just engaged seller-focused content"

    # "Just listed" inbound trigger — the strongest signal. If this home was NOT listed on
    # the previous run and is now on the market, the owner went from researching to selling.
    prev = lead.get("seller_intent") or {}
    prev_listed = ((prev.get("own_property") or {}).get("listing_status") == "for_sale"
                   or (prev.get("propradar") or {}).get("on_market") is True)
    now_listed = st == "for_sale" or (pr or {}).get("on_market") is True
    just_listed = bool(prev and now_listed and not prev_listed)
    if just_listed:
        # They've just committed to a competing agent — NOT a lead now. Flag for the
        # ~90-day expiry watch instead of treating it as hot intent.
        moment = "Just listed with another agent — NOT a lead now; flag for ~90-day expiry watch"

    story = build_story(lead, own, current_viewed, behav, pr, label)

    return {
        "label": label,
        "conclusion": reason,
        "story": story,
        "own_property": own,
        "listings_viewed": viewed,
        "current_listings_viewed": current_viewed,
        "n_current_listings_viewed": len(current_viewed),
        "behavioral": {**{k: behav[k] for k in _COUNT_KEYS},
                       "address_searches": behav["address_searches"], "last_seen": behav["last_seen"]},
        "behavioral_score": bscore,
        "hotness": hotness,
        "moment": moment,
        "just_listed": just_listed,
        "propradar": pr,
        "journey_sessions": sessions,
        "generated_own_minisite": generated_minisite,
        "computed_at": NOW,
    }


def run(query: dict, dry_run: bool = False, limit: int = 0, max_pr: int = 30) -> int:
    c = get_client()
    sm = c["system_monitor"]
    gc_db = c["Gold_Coast"]
    suburb_index = build_suburb_index(gc_db)
    load_behavioral()  # one PostHog sweep -> BEHAV

    # On a full run, first surface anonymous high-signal visitors into the worklist so
    # they're enriched + written to the sheet alongside everyone else.
    if query == {}:
        surface_behavioral_leads(sm, dry_run=dry_run)
        listing_expiry_monitor(sm, gc_db, dry_run=dry_run)

    leads = list(sm["lead_worklist"].find(query))
    if limit:
        leads = leads[:limit]

    # Resolve distinct_ids once, then process HOTTEST first so the PropRadar budget
    # (quota-limited) is spent on the highest-intent leads.
    for lead in leads:
        lead["_dids"] = lead_distinct_ids(lead, sm)
    leads.sort(key=lambda l: (
        behavioral_score(merge_behavioral(l["_dids"]))
        + (12 if (l.get("property") or {}).get("listing_status") in ("for_sale", "withdrawn") else 0)),
        reverse=True)

    pr_budget = [max_pr]
    pr_used_start = max_pr
    n = hits = 0
    alerts = []
    for lead in leads:
        si = analyze(lead, sm, gc_db, suburb_index, pr_budget)
        n += 1
        actionable = si["label"] != "no_cross_signal" or si["behavioral_score"] >= 8 or si.get("moment")
        if actionable:
            hits += 1
        if si.get("just_listed"):
            alerts.append((lead.get("address") or lead.get("lead_key"), si))
        flag = "🔥" if si.get("moment") else ("•" if actionable else " ")
        print(f"{flag} [{si['label']:>24}] hot={si['hotness']:>3} "
              f"{(lead.get('address') or lead.get('lead_key'))[:40]:<40} "
              f"{('| ' + si['moment']) if si.get('moment') else ''}")
        if not dry_run:
            cosmos_retry(lambda: sm["lead_worklist"].update_one(
                {"_id": lead["_id"]}, {"$set": {"seller_intent": si}}))
    if alerts and not dry_run:
        _notify_just_listed(alerts)
    print(f"\nseller_intent: {n} leads processed, {hits} actionable, "
          f"{len(alerts)} JUST-LISTED trigger(s), "
          f"PropRadar-enriched {pr_used_start - pr_budget[0]} lead(s), "
          f"{'DRY-RUN (nothing written)' if dry_run else 'written to lead_worklist.seller_intent'}")
    return hits


def _notify_just_listed(alerts):
    """Telegram alert when a tracked pre-market lead's home flips to on-market — the
    strongest inbound selling-intent trigger."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        lines = ["📋 A tracked pre-market lead just LISTED WITH ANOTHER AGENT "
                 "(not a lead now — flagged for the ~90-day expiry watch):"]
        for addr, si in alerts[:10]:
            lines.append(f"• {addr}")
            if si.get("story"):
                lines.append(f"  {si['story'][:180]}")
        send_message("\n".join(lines), parse_mode="")
    except Exception as e:  # noqa: BLE001
        print(f"(just-listed Telegram alert skipped: {e})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead-key")
    ap.add_argument("--address", help="regex match on lead address")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-pr", type=int, default=30,
                    help="max leads to PropRadar-enrich this run (quota guard)")
    args = ap.parse_args()

    if args.lead_key:
        q = {"lead_key": args.lead_key}
    elif args.address:
        q = {"address": {"$regex": re.escape(args.address), "$options": "i"}}
    elif args.all:
        q = {}
    else:
        ap.error("pass --lead-key, --address, or --all")

    # Scheduled full run (nightly, after lead_intelligence) self-reports so it can
    # never fail silently (Rule 7). Targeted/dry runs stay unmonitored.
    if args.all and not args.dry_run:
        from scripts.job_status import job_run
        with job_run("seller_intent", cadence_hours=24,
                     title="CRM Seller-Intent Enrichment") as beat:
            hits = run(q, dry_run=False, limit=args.limit, max_pr=args.max_pr)
            beat.detail = f"{hits} actionable seller-intent leads"
            beat.metrics = {"actionable": hits}
        return 0
    run(q, dry_run=args.dry_run, limit=args.limit, max_pr=args.max_pr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
