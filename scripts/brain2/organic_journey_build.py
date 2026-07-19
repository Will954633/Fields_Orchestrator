#!/usr/bin/env python3
"""
organic_journey_build.py — Brain 2 Layer 5: full-attribution, all-channel journeys.

Fixes the ads-only blind spot: ad_behaviour_build.py keeps ONLY sessions that map
to a known Facebook ad, so every organic / direct / referral lead is structurally
invisible (this is how the Bing → 16 Collingwood Ave → self-valuation lead was
missed). This builder keys on PostHog's native channel + entry page instead of ad
ids, so it sees ALL traffic.

Writes three collections in system_monitor:
  organic_journeys        — per-session docs for NON-PAID notable sessions
                            (converted, or hit /property or /analyse, or engaged)
  organic_landing_affinity — per entry-URL rollup (sessions -> engaged -> converters)
  all_conversions         — EVERY address submit across EVERY channel, with channel,
                            entry page, referrer, journey, reachability, and the
                            neighbour-sale-trigger flag. THIS is the collection any
                            "who engaged / converted this week" review must query.

Derived signal (auto-computed): neighbour_sale_trigger — the visitor landed on a
/property/<addr> page then ran Analyse-Your-Home on a DIFFERENT house on the SAME
street (or on the listing itself). The strongest seller-intent flag we have.

Usage: python3 scripts/brain2/organic_journey_build.py [--days 60]
Env: POSTHOG_ALL_ACCESS_KEY (or POSTHOG_PERSONAL_API_KEY), POSTHOG_PROJECT_ID
"""
import os, sys, re, json, argparse, urllib.request, urllib.error
from collections import defaultdict, Counter
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts/brain2")
from shared.db import get_client  # noqa: E402
from address_category import AddressClassifier, LABELS as ADDR_LABELS  # noqa: E402
from brain2_util import hog_retry, alert_failure  # noqa: E402

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ["POSTHOG_PERSONAL_API_KEY"]

PAID = ("Paid Social", "Paid Search", "Paid Other", "Paid Unknown")
CONV_EVENTS = ["analyse_home_submit_start", "analyse_home_submit_success",
               "analyse_home_address_submit", "analyse_v3_address_selected",
               "analyse_v2_address_selected", "analyse_v3_jobs_queued"]
SUBMIT_EVENT = "analyse_home_address_submit"  # carries properties.address
CONTENT_EVENTS = ["article_view", "v3_section_marker_view", "property_view",
                  "address_search", "v3_card_click", "time_on_page", "scroll_depth"]
STATE_TOKENS = {"qld", "nsw", "vic", "act", "sa", "wa", "nt", "tas", "australia"}

# --- Funnel-regime labelling (Will, 2026-07-16) ---------------------------------
# The /analyse-your-home funnel changed product on 1 July 2026 (AEST). Address-entry
# behaviour BEFORE this date is not comparable to behaviour after it, and drop-off
# before the cutover must NOT be read as friction in the current product.
#   contact_required_pdf   (< 2026-07-01 AEST): user had to enter phone and/or email
#       to receive a PDF report. High friction by design -> drop-off expected.
#   address_only_minisite  (>= 2026-07-01 AEST): friction removed; address-only entry
#       generates the automated house mini-site. This is the CURRENT product; drop-off
#       here is a real conversion signal.
FUNNEL_REGIME_CUTOVER = datetime(2026, 6, 30, 14, 0, 0, tzinfo=timezone.utc)  # 2026-07-01 00:00 AEST


def _parse_ts(ts):
    """Best-effort parse of an ISO-8601 timestamp (with trailing Z) to aware UTC datetime."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def funnel_regime(ts):
    """Label an address-entry timestamp by the product regime in force at that time."""
    d = _parse_ts(ts)
    if d is None:
        return "unknown"
    return "contact_required_pdf" if d < FUNNEL_REGIME_CUTOVER else "address_only_minisite"

# AI-assistant / generative-engine referrers. They tag outbound links with
# utm_source (ChatGPT) or send a referrer (Copilot) — NOT captured as a normal
# channel, so PostHog labels them "Direct". This is a first-class signal:
# which of our pages LLMs cite as authoritative sources ("GEO"/AI-SEO).
AI_SOURCES = {
    "chatgpt.com": "ChatGPT", "openai.com": "ChatGPT", "chat.openai.com": "ChatGPT",
    "copilot.com": "Copilot", "copilot.microsoft.com": "Copilot", "bing.com/chat": "Copilot",
    "perplexity.ai": "Perplexity", "www.perplexity.ai": "Perplexity",
    "gemini.google.com": "Gemini", "claude.ai": "Claude",
}


def detect_ai(utm_source, referring_domain):
    for key, name in AI_SOURCES.items():
        if (utm_source and key in utm_source) or (referring_domain and key in referring_domain):
            return name
    return None


def hog(sql):
    return hog_retry(PID, KEY, sql)


def parse_addr(text):
    """(house_number, street+suburb key) from an address string or property slug."""
    if not text:
        return None, None
    t = text.lower().replace("/property/", "").replace("-", " ")
    t = re.sub(r"[.,]", " ", t)
    toks = [x for x in t.split() if x]
    num = None
    if toks and re.match(r"^\d+[a-z]?$", toks[0]):
        num = toks[0]
        toks = toks[1:]
    # drop trailing state + postcode tokens
    toks = [x for x in toks if x not in STATE_TOKENS and not re.match(r"^\d{4}$", x)]
    return num, " ".join(toks).strip()


def property_slug(path):
    m = re.match(r"^/property/([^/?#]+)", path or "")
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    args = ap.parse_args()
    since = f"now() - INTERVAL {args.days} DAY"
    db = get_client()["system_monitor"]

    # searched-address classifier (Will 2026-07-19): tag each journey by the listing
    # state of the address they searched/valued -> owner-vs-buyer intent.
    addr_clf = AddressClassifier()

    def classify_searched(submits, entry_path):
        """Pick the most intent-bearing address (valued home > listing landed on)
        and classify it. Returns (category, label, detail)."""
        target = None
        if submits:
            target = submits[0]
        elif entry_path and str(entry_path).startswith("/property/"):
            target = entry_path
        if not target:
            return "out_of_coverage", ADDR_LABELS["out_of_coverage"], {"matched": False}
        cat, detail = addr_clf.classify(target)
        detail["classified_address"] = target
        return cat, ADDR_LABELS[cat], detail

    # internal identities (Will + anyone who ever hit /ops) — excluded from leads.
    # Seeded list + auto-detect over a wide window (an /ops visit = internal).
    internal = set(db.internal_identities.distinct("distinct_id"))
    stamp = datetime.now(timezone.utc).isoformat()
    for r in hog("""SELECT DISTINCT properties.distinct_id FROM events
        WHERE properties.$pathname = '/ops' AND timestamp > now() - INTERVAL 365 DAY
          AND properties.distinct_id IS NOT NULL LIMIT 100000"""):
        did = r[0]
        if did and did not in internal:
            internal.add(did)
            db.internal_identities.update_one({"distinct_id": did},
                {"$setOnInsert": {"distinct_id": did, "who": "unknown",
                                  "source": "auto_ops_visit", "added_at": stamp}}, upsert=True)
    print(f"internal identities excluded: {len(internal)}")

    # 1) all NON-PAID sessions (native sessions table — channel + entry + referrer)
    paid_list = ",".join("'" + p + "'" for p in PAID)
    srows = hog(f"""SELECT session_id, $channel_type, $entry_pathname,
        $entry_referring_domain, $session_duration, $is_bounce, $pageview_count,
        $entry_utm_source, $entry_utm_medium
        FROM sessions
        WHERE $start_timestamp > {since} AND $channel_type NOT IN ({paid_list})
        LIMIT 1000000""")
    sess_meta = {}
    for r in srows:
        sess_meta[r[0]] = {"channel": r[1], "entry_path": r[2], "referring_domain": r[3],
                           "duration_s": r[4], "is_bounce": bool(r[5]), "pageviews": r[6],
                           "utm_source": r[7], "utm_medium": r[8]}

    # 2) every session (ANY channel) that has an address-submit conversion
    conv_in = ",".join("'" + e + "'" for e in CONV_EVENTS)
    crows = hog(f"""SELECT DISTINCT properties.$session_id FROM events
        WHERE event IN ({conv_in}) AND timestamp > {since}
          AND properties.$session_id IS NOT NULL LIMIT 1000000""")
    conv_sids = {r[0] for r in crows if r[0]}

    # 3) which non-paid sessions are "notable" enough to reconstruct fully
    def notable(sid, m):
        if sid in conv_sids:
            return True
        ep = m.get("entry_path") or ""
        if ep.startswith("/property") or ep.startswith("/analyse"):
            return True
        if (m.get("pageviews") or 0) >= 3 or (m.get("duration_s") or 0) > 90:
            return True
        return False

    target = {s for s, m in sess_meta.items() if notable(s, m)} | conv_sids
    print(f"non-paid sessions: {len(sess_meta)} | conversions(any channel): {len(conv_sids)} "
          f"| reconstructing: {len(target)}")
    if not target:
        return

    # 4) full event stream for target sessions
    sid_list = ",".join("'" + s.replace("'", "") + "'" for s in target)
    ev_in = ",".join("'" + e + "'" for e in (CONTENT_EVENTS + CONV_EVENTS + ["$pageview"]))
    ev = hog(f"""SELECT properties.$session_id, timestamp, event, properties.$pathname,
        properties.property_id, properties.suburb, properties.address,
        properties.$referrer, properties.distinct_id
        FROM events WHERE properties.$session_id IN ({sid_list})
          AND event IN ({ev_in}) AND timestamp > {since}
        ORDER BY properties.$session_id, timestamp LIMIT 5000000""")

    J = defaultdict(lambda: {"pages": [], "properties": {}, "submits": [], "searches": 0,
                             "converted": False, "conv_events": set(), "person": None,
                             "first_referrer": None, "t_first": None, "t_last": None,
                             "timeline": []})
    for sid, ts, event, path, prop_id, suburb, address, referrer, person in ev:
        j = J[sid]
        if person and not j["person"]:
            j["person"] = person
        # permanent timestamped timeline (survives PostHog retention)
        te = {"t": ts, "e": event}
        for k, v in (("path", path), ("property_id", prop_id), ("suburb", suburb),
                     ("address", address), ("referrer", referrer)):
            if v is not None and v != "":
                te[k] = v
        j["timeline"].append(te)
        if referrer and not j["first_referrer"]:
            j["first_referrer"] = referrer
        j["t_first"] = j["t_first"] or ts
        j["t_last"] = ts
        if event == "$pageview":
            j["pages"].append(path or "?")
        elif event == "property_view" and prop_id:
            j["properties"][prop_id] = suburb
        elif event == "address_search":
            j["searches"] += 1
        elif event in CONV_EVENTS:
            j["converted"] = True
            j["conv_events"].add(event)
            if event == SUBMIT_EVENT and address:
                j["submits"].append(address)

    # neighbour-sale trigger: entry /property/<addr> then valued a house on same street
    def neighbour_flag(entry_path, submits):
        slug = property_slug(entry_path)
        if not slug or not submits:
            return None, None
        pn, pkey = parse_addr(slug)
        for a in submits:
            an, akey = parse_addr(a)
            if akey and pkey and akey == pkey:
                if an and pn and an != pn:
                    return "neighbour_sale_trigger", a       # different house, same street
                return "valued_the_listing_itself", a        # same house they landed on
        return None, None

    now = datetime.now(timezone.utc).isoformat()

    # helper: has this address ever produced reachable contact info?
    def contact_captured(address):
        if not address:
            return False
        num, key = parse_addr(address)
        for coll in ("analyse_leads", "valuation_requests", "leads", "report_review_bookings"):
            try:
                for d in db[coll].find({}, {"email": 1, "phone": 1, "address": 1}).limit(500):
                    an, ak = parse_addr(d.get("address", ""))
                    if ak and ak == key and (d.get("email") or d.get("phone")):
                        return True
            except Exception:
                pass
        return False

    # 5) write organic_journeys (non-paid notable) + accumulate landing affinity
    oj = db.organic_journeys
    oj.delete_many({})
    oj.create_index("channel"); oj.create_index("converted")
    affinity = defaultdict(lambda: {"sessions": 0, "converters": 0, "engaged": 0,
                                    "channels": Counter(), "referrers": Counter()})
    docs = []
    for sid in target:
        m = sess_meta.get(sid, {})
        j = J.get(sid, {})
        # organic_journeys = non-paid only (paid conversions already in ad store)
        if sid not in sess_meta:
            continue
        if j.get("person") in internal:
            continue
        flag, flag_addr = neighbour_flag(m.get("entry_path"), j.get("submits", []))
        engaged = (m.get("pageviews") or 0) >= 2 or (m.get("duration_s") or 0) > 60
        sa_cat, sa_label, sa_detail = classify_searched(j.get("submits", []), m.get("entry_path"))
        doc = {
            "session_id": sid, "distinct_id": j.get("person"),
            "channel": m.get("channel"), "entry_path": m.get("entry_path"),
            "referring_domain": m.get("referring_domain"),
            "utm_source": m.get("utm_source"),
            "ai_source": detect_ai(m.get("utm_source"), m.get("referring_domain")),
            "first_referrer": j.get("first_referrer"),
            "duration_s": m.get("duration_s"), "is_bounce": m.get("is_bounce"),
            "pageviews": m.get("pageviews"),
            "pages": j.get("pages", [])[:30],
            "properties_viewed": [{"property_id": k, "suburb": v} for k, v in j.get("properties", {}).items()],
            "n_searches": j.get("searches", 0),
            "converted": j.get("converted", False),
            "conversion_events": sorted(j.get("conv_events", [])),
            "addresses_submitted": j.get("submits", []),
            "pattern": flag, "pattern_address": flag_addr,
            "searched_address_category": sa_cat,
            "searched_address_label": sa_label,
            "searched_address_detail": sa_detail,
            "funnel_regime": funnel_regime(j.get("t_first")),
            "t_first": j.get("t_first"), "t_last": j.get("t_last"),
            "timeline": j.get("timeline", [])[:3000],  # full timestamped event sequence
            "computed_at": now,
        }
        docs.append(doc)
        af = affinity[m.get("entry_path") or "?"]
        af["sessions"] += 1
        af["converters"] += 1 if doc["converted"] else 0
        af["engaged"] += 1 if engaged else 0
        af["channels"][m.get("channel")] += 1
        if m.get("referring_domain"):
            af["referrers"][m["referring_domain"]] += 1
    if docs:
        oj.insert_many(docs)

    la = db.organic_landing_affinity
    la.delete_many({})
    for path, af in affinity.items():
        la.insert_one({"_id": path, "entry_path": path, "sessions": af["sessions"],
                       "engaged": af["engaged"], "converters": af["converters"],
                       "channels": dict(af["channels"]),
                       "top_referrers": dict(af["referrers"].most_common(5)),
                       "computed_at": now})

    # full cross-session person timeline (all sessions, not just the converting one)
    # — the entry point is often in an earlier session, and it's the key signal.
    def person_timeline(did):
        if not did:
            return []
        rows = hog(f"""SELECT timestamp, event, properties.$pathname,
            properties.property_id, properties.suburb, properties.address, properties.$referrer
            FROM events WHERE properties.distinct_id = '{did}'
              AND (event = '$pageview' OR event LIKE 'analyse_home_%' OR event LIKE 'analyse_v%'
                   OR event IN ('property_view','address_search','article_view',
                                'v3_section_marker_view','scroll_depth','time_on_page'))
            ORDER BY timestamp LIMIT 5000""")
        tl = []
        for ts, event, path, pid, suburb, address, ref in rows:
            te = {"t": ts, "e": event}
            for k, v in (("path", path), ("property_id", pid), ("suburb", suburb),
                         ("address", address), ("referrer", ref)):
                if v is not None and v != "":
                    te[k] = v
            tl.append(te)
        return tl

    # 6) all_conversions — EVERY address submit, EVERY channel (the review register)
    ac = db.all_conversions
    ac.delete_many({})
    ac.create_index("submitted_at")
    conv_docs = []
    for sid in conv_sids:
        j = J.get(sid, {})
        if j.get("person") in internal:  # drop Will / internal from the leads register
            continue
        m = sess_meta.get(sid)  # None => paid (not in non-paid pull)
        channel = m.get("channel") if m else "Paid (see ad store)"
        entry = m.get("entry_path") if m else (j.get("pages", ["?"])[0] if j.get("pages") else "?")
        flag, flag_addr = neighbour_flag(entry, j.get("submits", []))
        addr = j["submits"][0] if j.get("submits") else None
        sa_cat, sa_label, sa_detail = classify_searched(j.get("submits", []), entry)
        conv_docs.append({
            "session_id": sid, "distinct_id": j.get("person"),
            "submitted_address": addr, "all_addresses": j.get("submits", []),
            "channel": channel, "entry_path": entry,
            "referring_domain": (m.get("referring_domain") if m else None) or j.get("first_referrer"),
            "ai_source": detect_ai(m.get("utm_source") if m else None,
                                   (m.get("referring_domain") if m else None) or j.get("first_referrer")),
            "pages": j.get("pages", [])[:30],
            "properties_viewed": [{"property_id": k, "suburb": v} for k, v in j.get("properties", {}).items()],
            "pattern": flag, "pattern_address": flag_addr,
            "searched_address_category": sa_cat,
            "searched_address_label": sa_label,
            "searched_address_detail": sa_detail,
            "contact_captured": contact_captured(addr),
            "funnel_regime": funnel_regime(j.get("t_first")),
            "submitted_at": j.get("t_first"),
            "timeline": person_timeline(j.get("person")),  # FULL cross-session person journey
            "computed_at": now,
        })
    conv_docs.sort(key=lambda d: d.get("submitted_at") or "", reverse=True)
    if conv_docs:
        ac.insert_many(conv_docs)
    ac.create_index("searched_address_category")
    oj.create_index("searched_address_category")
    cat_counts = Counter(d["searched_address_category"] for d in conv_docs)
    print("searched_address_category (all_conversions): " +
          ", ".join(f"{k}={v}" for k, v in cat_counts.most_common()))

    # 7) AI-REFERRAL SIGNAL — which of our pages LLM assistants cite (all-time,
    # since this traffic predates the organic window + is otherwise mislabelled Direct)
    ai_rows = hog("""SELECT properties.utm_source, properties.$referring_domain,
        properties.$pathname, properties.$session_id, properties.distinct_id, timestamp
        FROM events
        WHERE event = '$pageview' AND timestamp > now() - INTERVAL 400 DAY
          AND (properties.utm_source IN ('chatgpt.com','openai.com','copilot.com')
               OR properties.$referring_domain LIKE '%copilot%'
               OR properties.$referring_domain LIKE '%chatgpt%'
               OR properties.$referring_domain LIKE '%perplexity%'
               OR properties.$referring_domain LIKE '%gemini%'
               OR properties.$referring_domain LIKE '%claude.ai%')
        LIMIT 100000""")
    ai_page = defaultdict(lambda: {"sessions": set(), "people": set(), "first": None, "last": None})
    ai_sess = set()
    for utm, ref, path, sid, did, ts in ai_rows:
        name = detect_ai(utm, ref) or "AI"
        key = (name, path)
        a = ai_page[key]
        if sid:
            a["sessions"].add(sid); ai_sess.add(sid)
        if did:
            a["people"].add(did)
        a["first"] = min(a["first"], ts) if a["first"] else ts
        a["last"] = max(a["last"], ts) if a["last"] else ts
    # conversions among AI sessions
    ai_conv = 0
    if ai_sess:
        sl = ",".join("'" + s + "'" for s in ai_sess if s)
        cr = hog(f"""SELECT count(DISTINCT properties.$session_id) FROM events
            WHERE event IN ({conv_in}) AND properties.$session_id IN ({sl})""")
        ai_conv = cr[0][0] if cr else 0
    ars = db.ai_referral_signal
    ars.delete_many({})
    for (name, path), a in ai_page.items():
        ars.insert_one({"ai_source": name, "page": path,
                        "sessions": len(a["sessions"]), "people": len(a["people"]),
                        "first_seen": a["first"], "last_seen": a["last"], "computed_at": now})
    ars.create_index("ai_source")
    print(f"AI-referral signal: {len(ai_sess)} sessions, {ai_conv} conversions, "
          f"{len(ai_page)} (source,page) rows -> ai_referral_signal")

    # summary
    print(f"wrote organic_journeys={len(docs)} landing_affinity={len(affinity)} all_conversions={len(conv_docs)}")
    triggers = [d for d in docs if d["pattern"]]
    print(f"neighbour/listing-trigger sessions: {len(triggers)}")

    # run-completion marker — written ONLY after all collection writes above
    # succeeded, so its timestamp confirms a clean refresh (the ops journey-tree
    # page reads this to show "last refreshed" + a fresh/stale badge).
    db.brain2_run_status.update_one(
        {"_id": "organic_journey_build"},
        {"$set": {"_id": "organic_journey_build", "run_completed_at": now,
                  "window_days": args.days, "status": "ok",
                  "counts": {"organic_journeys": len(docs),
                             "all_conversions": len(conv_docs),
                             "categories": dict(cat_counts)}}},
        upsert=True)
    print(f"run status recorded: run_completed_at={now}")
    print("\nALL CONVERSIONS (every channel, newest first):")
    for d in conv_docs[:15]:
        reach = "REACHABLE" if d["contact_captured"] else "no-contact"
        pat = f" [{d['pattern']}]" if d["pattern"] else ""
        print(f"  {str(d['submitted_at'])[:16]} | {str(d['channel'] or '?'):16} | "
              f"{str(d['submitted_address'] or '?')[:32]:32} | {reach}{pat}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        alert_failure("organic_journey_build", e)
        raise
