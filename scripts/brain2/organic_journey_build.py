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
import os, sys, re, json, argparse, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

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


def hog(sql):
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    r = urllib.request.Request(f"https://us.posthog.com/api/projects/{PID}/query/",
                               data=body, headers={"Authorization": f"Bearer {KEY}",
                                                   "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=120).read())["results"]


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
                             "first_referrer": None, "t_first": None, "t_last": None})
    for sid, ts, event, path, prop_id, suburb, address, referrer, person in ev:
        j = J[sid]
        if person and not j["person"]:
            j["person"] = person
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
        doc = {
            "session_id": sid, "distinct_id": j.get("person"),
            "channel": m.get("channel"), "entry_path": m.get("entry_path"),
            "referring_domain": m.get("referring_domain"),
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
            "t_first": j.get("t_first"), "t_last": j.get("t_last"),
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
        conv_docs.append({
            "session_id": sid, "distinct_id": j.get("person"),
            "submitted_address": addr, "all_addresses": j.get("submits", []),
            "channel": channel, "entry_path": entry,
            "referring_domain": (m.get("referring_domain") if m else None) or j.get("first_referrer"),
            "pages": j.get("pages", [])[:30],
            "properties_viewed": [{"property_id": k, "suburb": v} for k, v in j.get("properties", {}).items()],
            "pattern": flag, "pattern_address": flag_addr,
            "contact_captured": contact_captured(addr),
            "submitted_at": j.get("t_first"),
            "computed_at": now,
        })
    conv_docs.sort(key=lambda d: d.get("submitted_at") or "", reverse=True)
    if conv_docs:
        ac.insert_many(conv_docs)

    # summary
    print(f"wrote organic_journeys={len(docs)} landing_affinity={len(affinity)} all_conversions={len(conv_docs)}")
    triggers = [d for d in docs if d["pattern"]]
    print(f"neighbour/listing-trigger sessions: {len(triggers)}")
    print("\nALL CONVERSIONS (every channel, newest first):")
    for d in conv_docs[:15]:
        reach = "REACHABLE" if d["contact_captured"] else "no-contact"
        pat = f" [{d['pattern']}]" if d["pattern"] else ""
        print(f"  {str(d['submitted_at'])[:16]} | {str(d['channel'] or '?'):16} | "
              f"{str(d['submitted_address'] or '?')[:32]:32} | {reach}{pat}")


if __name__ == "__main__":
    main()
