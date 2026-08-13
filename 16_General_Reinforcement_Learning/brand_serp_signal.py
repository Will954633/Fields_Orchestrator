#!/usr/bin/env python3
"""
brand_serp_signal.py — measures how well we own the search results for OUR OWN NAME.

WHY THIS EXISTS (Will, 2026-08-13). He googled "Fields Real Estate" and the results were
buyer-facing, inconsistently named, and third place went to an unrelated PRD agent called
Ben Fields. That page is the first thing a seller sees after a flyer, a posted report or a
referral — the highest-intent audience we have — and nobody was managing it.

A prompt instruction alone would only make the agent LOOK each week. Will asked for
something that CHECKS WE ARE PROGRESSING. So this measures the things we control, gives
each a number, and stores a history so week-over-week movement is visible.

WHAT IT MEASURES — and, importantly, what it does not:

  It does NOT scrape Google. No SERP API, no rank tracking. Everything here is a property
  of OUR OWN pages plus (when available) Search Console's own report of how our brand
  queries perform. Rank is an output we cannot read directly and should not fake.

  1. ENTITY CONSISTENCY. Google can only form a confident entity if every signal agrees.
     On 2026-08-13 we gave it four different names for one business — schema said "Fields
     Estate", the Facebook page said "Fields Real Estate", and title suffixes were split
     between "| Fields" and "| Fields Estate". Will has since ruled: the canonical name is
     "Fields Real Estate". Anything else is now drift, and drift is the likeliest reason a
     competitor outranks us on our own name.

  2. sameAs COVERAGE. Corroborating links are how an entity gets confirmed. We had exactly
     one, and it was a raw facebook.com/profile.php?id= URL.

  3. SELLER-vs-BUYER LANGUAGE. Sellers are the customer. Measured 2026-08-13 the homepage
     said "buy" 82 times and "seller" 7 — roughly 12:1 against the audience that pays us.

  4. META OVERRIDE RISK. Our meta descriptions were fine; Google ignored them and built
     snippets from body copy instead. So a bad snippet is usually a BODY problem. This
     flags pages whose visible body text contains something we would not want surfaced —
     most importantly a single-property valuation figure, which CLAUDE.md Rule 5 forbids in
     a headline and which was live in the SERP for /for-sale-v3.

  5. GSC BRAND QUERIES, when the collector is working. Impressions/clicks/position for
     queries containing our name is the only real outcome measure here. As of 2026-08-13
     the collector is broken (scope 'webmasters.readonly' was never granted), so this
     degrades gracefully and says so rather than reporting a silent zero — a zero here
     would otherwise be indistinguishable from "nobody searches for us".

Writes system_monitor.rl_brand_serp (_id="latest" + dated history).
Read by the seo domain cycle. Run standalone: python3 brand_serp_signal.py [--verbose]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

CANONICAL_NAME = "Fields Real Estate"      # Will's ruling, 2026-08-13
SITE = "https://fieldsestate.com.au"

# The pages a person researching the business actually lands on.
BRAND_PAGES = ["/", "/why-fields", "/for-sale-v3", "/analyse-your-home"]

# Brand queries we care about. Used against Search Console, not scraped.
BRAND_TERMS = ["fields real estate", "fields estate", "fieldsestate", "fields gold coast",
               "fields robina", "fields burleigh", "fields varsity"]

UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

# Name variants that are NOT the canonical one. Order matters: longest first, so that
# "Fields Real Estate" is consumed before the bare "Fields" can match inside it.
NAME_VARIANTS = ["Fields Real Estate", "Fields Estate", "Fields"]


def _now():
    return datetime.now(timezone.utc)


def _fetch(path):
    import requests
    try:
        r = requests.get(SITE + path, headers={"User-Agent": UA}, timeout=45)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _tag(t, pattern):
    m = re.search(pattern, t, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else None


def _visible_text(t):
    """Strip script/style/tags so we count words a reader (and Google's snippet
    generator) would actually see — not JSON payloads or class names."""
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def _title_suffix(title):
    """The brand token after the last '|'. That is the entity signal in a title."""
    if not title or "|" not in title:
        return None
    return title.rsplit("|", 1)[1].strip()


def _schema_orgs(t):
    out = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            d = json.loads(block)
        except Exception:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if not isinstance(o, dict):
                continue
            ty = o.get("@type")
            types = ty if isinstance(ty, list) else [ty]
            if any(x in ("Organization", "RealEstateAgent", "LocalBusiness") for x in types):
                out.append(o)
    return out


# Rule 5 forbids a SINGLE VALUATION figure, and explicitly PERMITS comparable ranges and
# exact transaction prices. So context decides, not the number. An earlier version of this
# function flagged every 7-figure amount and produced four false positives on copy that was
# entirely compliant ("comps $1,180,366 – $1,508,396", "sold to $1,610,000").
_VALUATION_CONTEXT = re.compile(
    r"(?:valuation of|valued at|we value it at|reconcile[sd]? to(?: about| around)?|"
    r"worth about|worth around|estimated? at|estimate of)\s*\$\s?"
    r"([0-9]{1,3}(?:,[0-9]{3}){2,})", re.I)


def _valuation_figures(text):
    """Dollar figures presented as THIS property's single value, in visible body copy.

    Verified live on /for-sale-v3 2026-08-13: 'valuation of $1,726,668' and 'reconciles to
    about $1,183,000'. Google built its brand-SERP snippet from exactly this shape of
    sentence, which is how a compliant page still produced a non-compliant search result.
    Comparable ranges and sold prices are deliberately NOT matched — they are allowed.
    """
    return sorted({m.group(1) for m in _VALUATION_CONTEXT.finditer(text)})


def collect(verbose=False):
    pages = {}
    for path in BRAND_PAGES:
        raw = _fetch(path)
        if raw is None:
            pages[path] = {"fetched": False}
            continue
        vis = _visible_text(raw)
        title = _tag(raw, r"<title[^>]*>(.*?)</title>")
        desc = (_tag(raw, r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
                or _tag(raw, r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']'))
        orgs = _schema_orgs(raw)
        # Whole-word counts; "buyer" must not be counted as "buy".
        n_buy = len(re.findall(r"\bbuy(?:s|ing|er|ers)?\b", vis, re.I))
        n_sell = len(re.findall(r"\bsell(?:s|ing|er|ers)?\b", vis, re.I))
        pages[path] = {
            "fetched": True,
            "title": title,
            "title_suffix": _title_suffix(title),
            "meta_description": desc,
            "schema_names": [o.get("name") for o in orgs if o.get("name")],
            "schema_types": [o.get("@type") for o in orgs],
            "same_as": sorted({u for o in orgs for u in (o.get("sameAs") or [])}),
            "buy_mentions": n_buy,
            "sell_mentions": n_sell,
            "seller_ratio": round(n_sell / n_buy, 3) if n_buy else None,
            "valuation_figures_in_body": _valuation_figures(vis),
        }

    fetched = {p: d for p, d in pages.items() if d.get("fetched")}

    # ── entity consistency ────────────────────────────────────────────────────────
    names = set()
    for d in fetched.values():
        names.update(n for n in d["schema_names"] if n)
        if d["title_suffix"]:
            names.add(d["title_suffix"])
    off_canon = sorted(n for n in names if n != CANONICAL_NAME)
    same_as = sorted({u for d in fetched.values() for u in d["same_as"]})
    ugly_fb = [u for u in same_as if "profile.php" in u]

    issues = []
    if off_canon:
        issues.append({
            "severity": "high", "kind": "entity_name_drift",
            "detail": f"{len(off_canon)} name variant(s) other than '{CANONICAL_NAME}': "
                      f"{', '.join(off_canon)}. Google cannot form one confident entity "
                      f"while these disagree, which is how a competitor outranks us on our "
                      f"own brand name.",
        })
    if len(same_as) < 4:
        issues.append({
            "severity": "high", "kind": "thin_same_as",
            "detail": f"only {len(same_as)} sameAs link(s). Corroborating profiles are how "
                      f"an entity gets confirmed; this is the weakest signal we control.",
        })
    if ugly_fb:
        issues.append({
            "severity": "medium", "kind": "non_canonical_social_url",
            "detail": f"sameAs uses a raw profile.php URL ({ugly_fb[0][:70]}). Use the "
                      f"vanity URL — it is a stronger, human-readable entity signal.",
        })
    for path, d in fetched.items():
        if d["seller_ratio"] is not None and d["seller_ratio"] < 0.5:
            issues.append({
                "severity": "high", "kind": "buyer_skewed_copy", "page": path,
                "detail": f"{path} mentions buying {d['buy_mentions']}x vs selling "
                          f"{d['sell_mentions']}x (ratio {d['seller_ratio']}). Sellers are "
                          f"the customer and this is what they read first.",
            })
        if d["valuation_figures_in_body"]:
            issues.append({
                "severity": "high", "kind": "rule5_valuation_in_body", "page": path,
                "detail": f"{path} shows single-property valuation figure(s) in visible body "
                          f"copy: {', '.join('$' + v for v in d['valuation_figures_in_body'][:3])}. "
                          f"Google builds snippets from body copy, so these can surface into "
                          f"the brand SERP — where CLAUDE.md Rule 5 forbids them.",
            })

    # ── Search Console brand queries (the only real outcome measure) ──────────────
    gsc = {"available": False, "reason": None, "queries": []}
    try:
        from shared.db import get_client
        coll = get_client()["system_monitor"]["search_console_queries"]
        rows = []
        for term in BRAND_TERMS:
            for doc in coll.find({"query": {"$regex": re.escape(term), "$options": "i"}}
                                 ).sort("date", -1).limit(50):
                rows.append({"query": doc.get("query"), "date": str(doc.get("date"))[:10],
                             "clicks": doc.get("clicks"), "impressions": doc.get("impressions"),
                             "position": doc.get("position")})
        seen, dedup = set(), []
        for r in rows:
            k = (r["query"], r["date"])
            if k not in seen:
                seen.add(k)
                dedup.append(r)
        if dedup:
            gsc = {"available": True, "reason": None, "queries": dedup[:40]}
        else:
            # Rule 8 / Rule 7b: an empty result is a statement about the pipeline, not
            # about demand. Say which, never let it read as "nobody searches for us".
            gsc["reason"] = ("no brand rows in search_console_queries. As of 2026-08-13 the "
                             "GSC collector fails on an invalid_scope error (REC-ops-002), so "
                             "treat this as NO DATA, not as zero brand search demand.")
    except Exception as e:
        gsc["reason"] = f"could not read search_console_queries: {e}"

    score_max = 4
    score = sum([
        1 if not off_canon else 0,
        1 if len(same_as) >= 4 else 0,
        1 if all((d["seller_ratio"] or 0) >= 0.5 for d in fetched.values()) else 0,
        1 if not any(d["valuation_figures_in_body"] for d in fetched.values()) else 0,
    ])

    doc = {
        "generated_at": _now().isoformat(),
        "canonical_name": CANONICAL_NAME,
        "pages": pages,
        "entity": {"names_found": sorted(names), "off_canonical": off_canon,
                   "same_as": same_as, "same_as_count": len(same_as)},
        "issues": sorted(issues, key=lambda i: 0 if i["severity"] == "high" else 1),
        "gsc_brand": gsc,
        "progress_score": score,
        "progress_score_max": score_max,
        "note": ("Score counts only what we CONTROL: one consistent name, >=4 sameAs links, "
                 "seller-balanced copy on every brand page, no single valuation figure in "
                 "body copy. It deliberately does not model rank — we cannot read rank and "
                 "should not invent it."),
    }
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write to Mongo")
    a = ap.parse_args()

    doc = collect(a.verbose)

    print(f"BRAND SERP — progress {doc['progress_score']}/{doc['progress_score_max']} "
          f"(canonical name: {doc['canonical_name']})")
    print(f"  names in use : {', '.join(doc['entity']['names_found']) or '(none found)'}")
    print(f"  sameAs links : {doc['entity']['same_as_count']}")
    for p, d in doc["pages"].items():
        if not d.get("fetched"):
            print(f"  {p:22s} NOT FETCHED")
            continue
        print(f"  {p:22s} buy={d['buy_mentions']:3d} sell={d['sell_mentions']:3d} "
              f"ratio={d['seller_ratio']}  suffix={d['title_suffix']!r}")
    print(f"\n  {len(doc['issues'])} issue(s):")
    for i in doc["issues"]:
        print(f"   [{i['severity'].upper():6s}] {i['kind']}: {i['detail'][:150]}")
    g = doc["gsc_brand"]
    print(f"\n  GSC brand queries: {'available, %d rows' % len(g['queries']) if g['available'] else 'UNAVAILABLE — ' + str(g['reason'])[:120]}")

    if a.dry_run:
        return
    try:
        from shared.db import get_client
        c = get_client()["system_monitor"]["rl_brand_serp"]
        c.replace_one({"_id": "latest"}, dict(doc, _id="latest"), upsert=True)
        c.insert_one(dict(doc, _id=None, kind="history") if False else
                     {**{k: v for k, v in doc.items()}, "kind": "history"})
        print("\n  written to system_monitor.rl_brand_serp")
    except Exception as e:
        print(f"\n  WRITE FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
