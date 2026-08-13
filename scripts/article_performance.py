#!/usr/bin/env python3
"""
article_performance.py — writes measured outcomes back onto every article.

WHY (Will, 2026-08-13). `content_articles` is write-once editorial metadata: title, slug,
tags, target_keyword — and **not one performance field**. No views, no scroll, no clicks, no
conversions. So the article generator has never seen an outcome for anything it wrote, and
`articles_signal.py` reads only 2 of the ~10 collections that hold one. The loop is closed
at 0%. This is the missing spine: one nightly rollup that lands every available outcome on
the article it belongs to, so both the sensor and the generator can finally read back.

It invents no data. Everything here already existed and was simply never joined.

WHAT IT PULLS, and the honest state of each source:

  organic_landing_affinity   sessions / engaged / converters for /articles/<slug>.
                             ~6 article rows, 12 sessions total. Real but tiny.
  seo_landing_performance    GSC clicks / impressions / position per page.
                             62 article rows — but a SINGLE snapshot (2026-08-12), not a
                             series, so trend is unavailable and must not be implied.
  ad_session_behaviour       ⭐ the most valuable and least used: articles_read[] carries
                             max_scroll_pct and dwell per session. PAID traffic only.
                             The $3.465M flagship reads 37 sessions at 10.1% avg scroll —
                             the hook won the click and the body lost the reader. Nothing
                             has ever read this.
  organic_journeys           article_view + scroll_depth fire and land in timeline[] for
                             ORGANIC sessions but are never rolled up — paid gets read-depth
                             and organic does not, for no reason other than nobody built it.
                             Rolled up here so the two are comparable.
  ad_profiles                ~200 ads whose NAME is an article title, with lifetime CTR from
                             0% to 9.97%. Matched back to articles by title.
  fb_page_posts              organic post reach/clicks, once the insights collector lands.

⚠ SAMPLE SIZES ARE TINY AND THE OUTPUT SAYS SO. Every block carries its own n. A verdict of
"dead" on 0 sessions means "never distributed", not "bad article", and `evidence_grade`
records which. The previous articles cycle already made this exact mistake — it declared 25
articles dead when they had never actually been live.

Usage:
  article_performance.py                # roll up all articles, write back
  article_performance.py --dry-run      # print, write nothing
  article_performance.py --slug <slug>  # one article, verbose
  article_performance.py --top 15       # show the leaderboard after running
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client  # noqa: E402

ARTICLES = "content_articles"
OUT = "article_performance"

# Below this, a number is a hint and not a measurement. Used to set evidence_grade, never to
# hide data — the numbers are always reported, the grade just says how much to trust them.
MIN_SESSIONS_FOR_READ_DEPTH = 5
MIN_IMPRESSIONS_FOR_CTR = 50


def _now():
    return datetime.now(timezone.utc).isoformat()


def _slug_from_path(path):
    """/articles/<slug> or /article/<id> -> the identifying segment."""
    if not path:
        return None
    m = re.match(r"^/articles?/([^/?#]+)", str(path))
    return m.group(1) if m else None


def _norm_title(t):
    """Ad names are article titles with drift — case, punctuation, a trailing '?'. Normalise
    hard so the match is on words, not formatting."""
    return re.sub(r"[^a-z0-9 ]+", "", str(t or "").lower()).strip()


def build(dry_run=False, only_slug=None, verbose=False):
    sm = get_client()["system_monitor"]
    arts = list(sm[ARTICLES].find({}, {"html": 0, "content": 0}))
    if only_slug:
        arts = [a for a in arts if a.get("slug") == only_slug]
        if not arts:
            sys.exit(f"no article with slug {only_slug!r}")

    # Resolver: an article is referenced by slug, ghost_id or raw _id across the sources.
    by_key = {}
    for a in arts:
        for k in (a.get("slug"), a.get("ghost_id"), str(a.get("_id"))):
            if k:
                by_key[str(k)] = a["_id"]
    by_title = {_norm_title(a.get("title")): a["_id"] for a in arts if a.get("title")}

    perf = defaultdict(lambda: {
        "organic": {"sessions": 0, "engaged": 0, "converters": 0},
        "search": {"clicks": 0, "impressions": 0, "position_weighted": 0.0, "top_query": None},
        "read_depth_paid": {"sessions": 0, "scroll_sum": 0.0, "dwell_sum": 0.0},
        "read_depth_organic": {"sessions": 0, "scroll_sum": 0.0},
        "paid_headline": {"ads": 0, "impressions": 0, "clicks": 0, "spend_aud": 0.0},
        "fb_organic": {"posts": 0, "clicks": 0, "fan_reach": 0, "reactions": 0},
    })

    # ── organic landing affinity ────────────────────────────────────────────────
    for d in sm["organic_landing_affinity"].find({"entry_path": {"$regex": r"^/articles?/"}}):
        aid = by_key.get(_slug_from_path(d.get("entry_path")) or "")
        if not aid:
            continue
        p = perf[aid]["organic"]
        p["sessions"] += d.get("sessions", 0) or 0
        p["engaged"] += d.get("engaged", 0) or 0
        p["converters"] += d.get("converters", 0) or 0

    # ── Google Search Console ───────────────────────────────────────────────────
    best_q = {}
    for d in sm["seo_landing_performance"].find({"page": {"$regex": r"/articles?/"}}):
        aid = by_key.get(_slug_from_path(re.sub(r"^https?://[^/]+", "", str(d.get("page", "")))) or "")
        if not aid:
            continue
        s = perf[aid]["search"]
        imp = d.get("impressions", 0) or 0
        s["clicks"] += d.get("clicks", 0) or 0
        s["impressions"] += imp
        s["position_weighted"] += (d.get("position") or 0) * imp
        if imp > best_q.get(aid, (0, None))[0]:
            best_q[aid] = (imp, d.get("query"))
    for aid, (_, q) in best_q.items():
        perf[aid]["search"]["top_query"] = q

    # ── PAID read depth (the unused crown jewel) ────────────────────────────────
    for d in sm["ad_session_behaviour"].find({"articles_read": {"$exists": True, "$ne": []}}):
        dwell = d.get("dwell_seconds") or 0
        for r in d.get("articles_read") or []:
            aid = by_key.get(str(r.get("key") or "")) or by_title.get(_norm_title(r.get("title")))
            if not aid:
                continue
            p = perf[aid]["read_depth_paid"]
            p["sessions"] += 1
            p["scroll_sum"] += r.get("max_scroll_pct") or 0
            p["dwell_sum"] += dwell

    # ── ORGANIC read depth — same measure, never previously rolled up ───────────
    for j in sm["organic_journeys"].find({"timeline": {"$exists": True}}):
        cur, best = None, {}
        for ev in j.get("timeline") or []:
            path = ev.get("path") or ev.get("pathname") or ev.get("url")
            s = _slug_from_path(path)
            if s and s in by_key:
                cur = by_key[s]
            if cur and (ev.get("event") or ev.get("name")) == "scroll_depth":
                props = ev.get("properties") or ev
                for k in ("depth", "percent", "scroll_depth", "value"):
                    if isinstance(props.get(k), (int, float)):
                        best[cur] = max(best.get(cur, 0), float(props[k]))
                        break
        for aid, depth in best.items():
            p = perf[aid]["read_depth_organic"]
            p["sessions"] += 1
            p["scroll_sum"] += depth

    # ── the ~200 article-titled ads ─────────────────────────────────────────────
    # Two joins are needed and they catch different things:
    #   (a) ad NAME == article title. Covers the many ads that reuse the headline verbatim,
    #       and is what makes this a headline A/B corpus.
    #   (b) ad -> landing page via ad_downstream.entry_pages. Covers ads whose hook DIFFERS
    #       from the article title — e.g. the $68.34 ad "Who buys a home for $1,550,000 and
    #       sells it eighteen months later for $3,465,000?" drove
    #       /articles/someone-paid-1550000-... , which (a) alone misses entirely, leaving the
    #       best-performing article in the business showing 0 impressions.
    seen_ad_ids = set()
    for d in sm["ad_profiles"].find({}):
        aid = by_title.get(_norm_title(d.get("name")))
        if not aid:
            continue
        lt = d.get("lifetime") or {}
        p = perf[aid]["paid_headline"]
        p["ads"] += 1
        p["impressions"] += lt.get("impressions", 0) or 0
        p["clicks"] += lt.get("clicks", 0) or 0
        p["spend_aud"] += float(lt.get("spend_aud", 0) or 0)
        if d.get("ad_id"):
            seen_ad_ids.add(str(d["ad_id"]))

    for d in sm["ad_downstream"].find({}):
        ad_id = str(d.get("ad_id") or "")
        if ad_id in seen_ad_ids:
            continue  # already counted by title; don't double-count the same spend
        pages = d.get("entry_pages") or {}
        paths = pages.keys() if isinstance(pages, dict) else [
            (x.get("path") if isinstance(x, dict) else x) for x in (pages or [])]
        matched = {by_key[s] for s in (_slug_from_path(p) for p in paths) if s and s in by_key}
        if not matched:
            continue
        lt = d.get("ad_lifetime") or {}
        # Split evenly when one ad drove several articles — crude, but it is honest about
        # not knowing the split, and never inflates total spend.
        n = len(matched)
        for aid in matched:
            p = perf[aid]["paid_headline"]
            p["ads"] += 1
            p["impressions"] += int((lt.get("impressions", 0) or 0) / n)
            p["clicks"] += int((lt.get("clicks", 0) or 0) / n)
            p["spend_aud"] += float(lt.get("spend_aud", 0) or 0) / n
            if ad_id:
                seen_ad_ids.add(ad_id)

    # ── organic FB posts (populated once the insights collector lands) ──────────
    for d in sm["fb_page_posts"].find({}):
        aid = None
        if d.get("article_id"):
            aid = by_key.get(str(d["article_id"])) or (
                d["article_id"] if d["article_id"] in {a["_id"] for a in arts} else None)
        if not aid and d.get("link"):
            aid = by_key.get(_slug_from_path(re.sub(r"^https?://[^/]+", "", d["link"])) or "")
        if not aid:
            continue
        # ⚠ Meta has DEPRECATED post-level impressions and reach. `post_impressions`,
        # `post_impressions_unique` and friends now return "(#100) The value must be a valid
        # insights metric" on both v18 and v23, with read_insights granted — it is not a
        # permission problem and no token change brings them back. So organic posts cannot
        # have a CTR computed, and articles must be ranked on ABSOLUTE CLICKS.
        # `post_fan_reach` (reach among page fans only) is the sole reach-like survivor and
        # is recorded for completeness, not for rate maths.
        ins = (d.get("insights") or {}).get("metrics") or {}
        eng = d.get("engagement") or {}
        p = perf[aid]["fb_organic"]
        p["posts"] += 1
        p["clicks"] += ins.get("post_clicks", 0) or 0
        p["fan_reach"] = p.get("fan_reach", 0) + (ins.get("post_fan_reach", 0) or 0)
        reacts = ins.get("post_reactions_by_type_total") or {}
        p["reactions"] += (sum(reacts.values()) if isinstance(reacts, dict) else 0) \
            or ((eng.get("likes", 0) or 0) + (eng.get("comments", 0) or 0))

    # ── derive, grade, write ────────────────────────────────────────────────────
    rows, written = [], 0
    for a in arts:
        aid = a["_id"]
        p = perf.get(aid) or perf[aid]
        o, s = p["organic"], p["search"]
        rdp, rdo, ph, fo = (p["read_depth_paid"], p["read_depth_organic"],
                            p["paid_headline"], p["fb_organic"])

        block = {
            "computed_at": _now(),
            "organic": dict(o),
            "search": {**{k: v for k, v in s.items() if k != "position_weighted"},
                       "avg_position": round(s["position_weighted"] / s["impressions"], 1)
                       if s["impressions"] else None,
                       "ctr": round(s["clicks"] / s["impressions"], 4) if s["impressions"] else None},
            "read_depth": {
                "paid_sessions": rdp["sessions"],
                "paid_avg_scroll_pct": round(rdp["scroll_sum"] / rdp["sessions"], 1) if rdp["sessions"] else None,
                "paid_avg_dwell_s": round(rdp["dwell_sum"] / rdp["sessions"], 1) if rdp["sessions"] else None,
                "organic_sessions": rdo["sessions"],
                "organic_avg_scroll_pct": round(rdo["scroll_sum"] / rdo["sessions"], 1) if rdo["sessions"] else None,
            },
            "paid_headline": {**ph,
                              "ctr": round(ph["clicks"] / ph["impressions"], 4) if ph["impressions"] else None},
            "fb_organic": dict(fo),
        }

        total_sessions = o["sessions"] + rdp["sessions"] + rdo["sessions"]
        # fb_organic contributes no impressions — Meta deprecated post-level reach (see above).
        total_impr = s["impressions"] + ph["impressions"]

        # The distinction the last articles cycle got wrong: never distributed is NOT the
        # same as distributed-and-ignored, and only the second is the article's fault.
        if total_impr == 0 and total_sessions == 0:
            block["evidence_grade"] = "never_distributed"
            block["verdict_note"] = ("No impressions and no sessions from any channel. This "
                                     "says nothing about the article's quality — it was never "
                                     "put in front of anyone.")
        elif total_sessions < MIN_SESSIONS_FOR_READ_DEPTH and total_impr < MIN_IMPRESSIONS_FOR_CTR:
            block["evidence_grade"] = "insufficient"
            block["verdict_note"] = (f"{total_sessions} session(s), {total_impr} impression(s) — "
                                     f"directional at best. Do not rank on this.")
        else:
            block["evidence_grade"] = "measurable"
            hints = []
            if block["read_depth"]["paid_avg_scroll_pct"] is not None and rdp["sessions"] >= MIN_SESSIONS_FOR_READ_DEPTH:
                if block["read_depth"]["paid_avg_scroll_pct"] < 25:
                    hints.append(f"readers stop at {block['read_depth']['paid_avg_scroll_pct']}% "
                                 f"of the page (n={rdp['sessions']}) — the body is losing them, "
                                 f"not the headline")
            if ph["impressions"] >= MIN_IMPRESSIONS_FOR_CTR and block["paid_headline"]["ctr"]:
                hints.append(f"headline earned {block['paid_headline']['ctr']*100:.2f}% CTR paid "
                             f"(n={ph['impressions']} impr)")
            block["verdict_note"] = "; ".join(hints) or "measurable but unremarkable"

        rows.append((a, block, total_sessions, total_impr))
        if not dry_run:
            sm[ARTICLES].update_one({"_id": aid}, {"$set": {"performance": block}})
            sm[OUT].replace_one({"_id": aid},
                                {"_id": aid, "slug": a.get("slug"), "title": a.get("title"),
                                 "status": a.get("status"), **block}, upsert=True)
            written += 1

    return rows, written


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slug")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    rows, written = build(a.dry_run, a.slug, verbose=bool(a.slug))

    grades = defaultdict(int)
    for _, b, _, _ in rows:
        grades[b["evidence_grade"]] += 1
    print(f"{len(rows)} articles | written: {written}{'  (dry-run)' if a.dry_run else ''}")
    print("evidence grade: " + ", ".join(f"{k}={v}" for k, v in sorted(grades.items())))
    print()

    rank = sorted(rows, key=lambda r: (r[3], r[2]), reverse=True)[:a.top]
    print(f"{'article':52s} {'impr':>7s} {'sess':>5s} {'scroll':>7s} {'grade':>16s}")
    for art, b, sess, impr in rank:
        rd = b["read_depth"]
        scroll = rd["paid_avg_scroll_pct"] if rd["paid_avg_scroll_pct"] is not None else rd["organic_avg_scroll_pct"]
        print(f"{str(art.get('title'))[:52]:52s} {impr:>7d} {sess:>5d} "
              f"{(str(scroll)+'%') if scroll is not None else '—':>7s} {b['evidence_grade']:>16s}")
    print()
    for art, b, _, _ in rank[:5]:
        if b["verdict_note"] and b["evidence_grade"] == "measurable":
            print(f"• {str(art.get('title'))[:60]}\n    {b['verdict_note']}")


if __name__ == "__main__":
    main()
