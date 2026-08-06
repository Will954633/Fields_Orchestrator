#!/usr/bin/env python3
"""
emit_v4.py — build the V4 card sequence from a cached fact bundle.

Sits alongside emit_json.py. **Nothing here touches the 26,297 live decks** —
this writes `engine_version: "disc-v4"` and, when --write is passed, upserts to a
SEPARATE collection (`offmarket_discovery_v4`) so the live arm is untouched.

    python3 emit_v4.py --slug 28-wedgebill-parade-burleigh-waters --print
    python3 emit_v4.py --slug X --write

Reuses assemble.py's helpers and the cached bundles (26,298 already built), so
assembly is instant — the expensive harvest never re-runs.

WHAT CHANGES vs the live deck
  * the range moves from card 09 to card 01. V3 held the number to the 7th of 9
    cards; measured, ~1 session in 7 gets that far. The curiosity gap moves onto
    the FEATURE, which is what the hook was always about.
  * five new card types — evidence, method, dispersion, gain, control — which
    DeckV3 does not yet render. Flagged in `build_notes.new_types` so the React
    work is scoped rather than discovered.
  * data the bundle does not carry (adjusted comparables, market snapshot,
    competitor change log) is fetched here, matching the markdown prototype.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/fields/Fields_Orchestrator")

import yaml                                     # noqa: E402
import assemble as A                            # noqa: E402
from emit_json import _strip_md                 # noqa: E402
from src.mongo_client_factory import get_mongo_client  # noqa: E402

OUT_DIR = HERE / "json_v4"
OUT_DIR.mkdir(exist_ok=True)

# Card types DeckV3 already renders. Anything else needs front-end work.
KNOWN_TYPES = {"recognition", "hook", "reveal", "explanation", "competition",
               "comparable", "buyer", "valuation", "strategy", "value_drivers"}


def load_copy_v4():
    return yaml.safe_load((HERE / "copy_v4.yaml").read_text())


def money_m(v):
    """Millions to 2dp. A range precise to the dollar reads as algorithmic and
    contradicts 'the width is the honest part'."""
    try:
        f = float(v)
    except Exception:
        return None
    if f >= 1_000_000:
        return "$" + f"{f/1_000_000:.2f}".rstrip("0").rstrip(".") + " million"
    return f"${int(round(f)):,}"


def _month(d):
    try:
        return datetime.fromisoformat(str(d)[:10]).strftime("%B %Y")
    except Exception:
        return str(d)[:7]


# ── extra data the bundle does not carry ───────────────────────────────────

def _extras(b):
    gc = get_mongo_client()["Gold_Coast"]
    sm = get_mongo_client()["system_monitor"]
    doc = gc[b["suburb_key"]].find_one({"address": b["address"]}) or {}
    vd = doc.get("valuation_data") or {}
    tl = [e for e in ((doc.get("scraped_data") or {}).get("property_timeline") or [])
          if str(e.get("category", "")).lower() == "sale" and e.get("price")]
    tl.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
    # Prefer the doc's own sale over the timeline, which lags a recent transaction.
    last = None
    if doc.get("listing_status") == "sold" and doc.get("sale_price") and doc.get("sold_date"):
        import re
        digits = re.sub(r"[^\d]", "", str(doc["sale_price"]))
        if digits:
            last = {"date": doc["sold_date"], "price": int(digits)}
    if last is None and tl:
        last = tl[0]
    return {
        "adjusted": [c for c in (vd.get("adjusted_comparables") or []) if c.get("adjusted_price")],
        "last_sale": last,
        "market": (sm["market_pulse"].find_one({"suburb": b["suburb_key"]}) or {}).get("data_snapshot") or {},
        "report": sm["property_reports"].find_one({"slug": b["slug"]}) or {},
        # Why a range is absent, when it is. `above_design_ceiling` /
        # `below_design_floor` mean the method declined, not that the data is
        # thin — those need different copy and the wrong one would be a lie.
        "directional": ((vd.get("confidence") or {}).get("directional_reason")),
    }


# ── cards ──────────────────────────────────────────────────────────────────

def c00_arrival(b, c, x):
    k = c["card_00_arrival"]
    card = {"type": "recognition", "questions_intro": k["questions_intro"],
            "questions": k["questions"], "frame": k["frame"], "next": k["opens"]}
    ls = x.get("last_sale")
    if ls:
        card["last_sale"] = k["last_sale"].format(price=A.money(ls["price"]),
                                                  month=_month(ls.get("date")))
        card["last_sale_note"] = k["last_sale_note"]
    return card


def c01_range(b, c, x):
    k = c["card_01_range"]
    v = b.get("valuation") or {}
    if not (v.get("low") and v.get("high")):
        if x.get("directional") in ("above_design_ceiling", "below_design_floor"):
            return {"type": "valuation", "answer": k["answer"],
                    "no_range": k["no_range_envelope_intro"],
                    "no_range_reason": k["no_range_envelope_reason"],
                    "no_range_why": k["no_range_envelope_why"],
                    "no_range_close": k["no_range_envelope_close"],
                    "next": k["opens"]}
        return {"type": "valuation", "answer": k["answer"],
                "no_range": k["no_range_intro"], "no_range_reason": k["no_range_reason"],
                "next": k["opens"]}
    card = {"type": "valuation", "answer": k["answer"],
            "range": k["range"].format(val_low=money_m(v["low"]), val_high=money_m(v["high"])),
            "anchor_intro": k["anchor_intro"],
            "anchor": A._anchor(v["low"], v["high"], v.get("point")),
            "anchor_note": k["anchor_note"], "next": k["opens"]}
    if v.get("n_comps") and x["adjusted"]:
        card["basis"] = k["basis"].format(n_comps=v["n_comps"], n_shown=len(x["adjusted"]))
    if v.get("method") and v["method"] != "engine":
        # ⚠ `confidence_reason` ONLY — never fall back to the bare tier
        # (2026-08-06). The one-word level is not calibrated: measured on 333
        # sold homes, within-10% ran high 55%, medium 46%, low 56%, very_low
        # 61%. It is not monotonic in either direction, and `very_low` beat
        # `high`. A reader shown "high confidence" infers the range is more
        # trustworthy, and we cannot demonstrate that it is.
        #
        # `confidence_reason` states WHY (how many comparables, how close) —
        # that is a fact and survives. The tier is an unearned confidence
        # signal, which is the exact thing this page argues against; shipping
        # it would be self-refuting. Product/09_ACCURACY_AND_CALIBRATION.md.
        reason = v.get("confidence_reason")
        if reason:
            card["tier_caveat"] = reason
    return card


def c02_evidence(b, c, x):
    """NEW TYPE. The adjusted comparables — the traceability spine."""
    k = c["card_02_evidence"]
    if not x["adjusted"]:
        return None
    cred = b.get("credibility") or {}
    v = b.get("valuation") or {}
    funnel = [f"{cred['sales_reviewed']:,} recent sales searched" if cred.get("sales_reviewed") else None,
              f"{v['n_comps']} relevant sales retained" if v.get("n_comps") else None,
              f"{len(x['adjusted'])} strongest comparisons shown"]
    rows = [{"address": a.get("address"),
             "sold": money_m(a.get("sale_price")),
             "adjusted": "about " + (money_m(a.get("adjusted_price")) or ""),
             "when": str(a.get("sale_date"))[:7] if a.get("sale_date") else None}
            for a in sorted(x["adjusted"], key=lambda z: z.get("adjusted_price") or 0)]
    card = {"type": "evidence", "answer": k["answer"],
            "funnel_intro": k["funnel_intro"], "funnel": [f for f in funnel if f],
            "table_note": k["table_note"], "rows": rows,
            "means": k["means"], "next": k["opens"]}
    if cred.get("characteristics"):
        card["considered"] = k["considered"].format(n=cred["characteristics"])
    return card


def c03_comparable(b, c, x):
    k = c["card_03_comparable"]
    oc = b.get("obvious_comp")
    if not oc or not oc.get("price"):
        return None
    return {"type": "comparable", "answer": k["answer"],
            "headline": k["headline"].format(comp_address=oc["address"],
                                             comp_price=A.money(oc["price"]),
                                             comp_distance_m=oc.get("distance_m")),
            "looks": k["looks"], "reveal_intro": k["reveal_intro"],
            "deltas": oc.get("deltas") or [], "close": k["close"], "next": k["opens"]}


def c04_rarity(b, c, x):
    k = c["card_04_rarity"]
    sc = b.get("scarcity") or {}
    n_match, n_tot = sc.get("active_matching"), sc.get("active_total")
    anchors = [a for a in str(sc.get("query") or "").split("·") if a.strip()]
    share = (n_match / n_tot) if (n_match and n_tot) else None
    card = {"type": "reveal", "answer": k["answer"], "next": k["opens"]}
    # Never assert rarity the numbers don't support — a majority is not scarcity.
    if n_match is not None and share is not None and share <= 0.25 and len(anchors) >= 2:
        card["line"] = k["line"].format(matching=n_match, total=n_tot,
                                        query=_humanise(sc.get("query")))
        pr = b.get("poi_rarity") or {}
        feats = pr.get("features") or []
        if feats and pr.get("physical_matching"):
            best = min(feats, key=lambda f: f.get("matching", 9e9))
            shorts = [f.get("short") for f in feats if f.get("short")]
            phrase = (", ".join(shorts[:-1]) + " and " + shorts[-1]) if len(shorts) > 1 else (shorts[0] if shorts else "")
            card["poi_line"] = k["poi_line"].format(
                physical_matching=pr["physical_matching"], matching=best["matching"],
                verb="is" if best["matching"] == 1 else "are", phrase=phrase)
        card["means"] = k["means"]
    vd = b.get("value_drivers") or {}
    carries, levers = vd.get("carries_price") or [], b.get("negotiation_levers") or []
    if carries:
        card["drivers_intro"], card["drivers"] = k["drivers_intro"], carries
    if levers:
        card["levers_intro"], card["levers"] = k["levers_intro"], levers
    if carries and levers:
        card["drivers_close"] = k["drivers_close"]
    return card if (card.get("line") or carries or levers) else None


def _humanise(q):
    if not q:
        return "its core combination"
    out, seen_m2 = [], 0
    for p in [p.strip() for p in str(q).split("·")]:
        if p.lower() in ("yes", "true"):
            out.append("a pool")
        elif p.lower() in ("no", "false"):
            continue
        elif p.endswith("m²"):
            out.append(f"{p} of {'floor area' if seen_m2 else 'land'}"); seen_m2 += 1
        else:
            out.append(p)
    return ", ".join(out[:-1]) + " and " + out[-1] if len(out) > 1 else (out[0] if out else "its core combination")


def c05_method(b, c, x):
    """NEW TYPE."""
    k = c["card_05_method"]
    card = {"type": "method", "answer": k["answer"], "is_not": k["is_not"],
            "we_do": k["we_do"], "next": k["opens"]}
    if k.get("error_rate"):
        card["error_rate"] = k["error_rate"]
    else:
        card["blocked"] = ("error rate unpinned — one figure, one sample, one date, "
                           "and a definition")
    return card


def c06_dispersion(b, c, x):
    """NEW TYPE. Universal — needs nothing about this home."""
    k = c["card_06_dispersion"]
    return {"type": "dispersion", "answer": k["answer"], "setup": k["setup"],
            "test": k["test"], "finding": k["finding"], "means": k["means"],
            "reveal": {"label": k["reveal_label"], "body": k["reveal_body"]},
            "next": k["opens"]}


def c07_gain(b, c, x):
    """NEW TYPE."""
    k = c["card_07_gain"]
    ls, ms = x.get("last_sale"), x.get("market") or {}
    if not ls:
        return None
    hist = ms.get("median_price_history") or []
    card = {"type": "gain", "answer": k["answer"],
            "bought": k["bought"].format(price=A.money(ls["price"]), month=_month(ls.get("date"))),
            "means": k["means"], "next": k["opens"]}
    if not hist:
        return card
    first, last = hist[0], hist[-1]
    try:
        buy_year = int(str(ls["date"])[:4])
        idx_year = int(str(first.get("period")).split()[-1])
    except Exception:
        buy_year = idx_year = None
    sub = b.get("suburb_display")
    if buy_year and idx_year and buy_year < idx_year:
        card["cannot_reach"] = k["cannot_reach"].format(suburb=sub, start_period=first.get("period"))
        if ms.get("ten_year_growth_pct"):
            card["ten_year"] = k["ten_year"].format(
                then=money_m(ms.get("ten_year_start_price")),
                now=money_m(ms.get("ten_year_end_price")),
                pct=round(ms["ten_year_growth_pct"]))
    else:
        card["since"] = k["since"].format(suburb=sub, then=money_m(first.get("median_price")),
                                          then_period=first.get("period"),
                                          now=money_m(last.get("median_price")),
                                          now_period=last.get("period"))
    return card


def c08_competition(b, c, x):
    k = c["card_08_competition"]
    rep = x.get("report") or {}
    comps = rep.get("comparables") or {}
    active = comps.get("closest_active") or []
    ms = x.get("market") or {}
    card = {"type": "competition", "answer": k["answer"], "next": k["opens"]}
    if comps.get("generated_at"):
        card["live_bar"] = k["live_bar"].format(checked=str(comps["generated_at"])[:10])
    if active:
        card["substitutes"] = k["substitutes"].format(n=len(active))
        card["homes"] = [{"address": a.get("address"), "price": a.get("price"),
                          "bedrooms": a.get("bedrooms"),
                          "difference": a.get("differenceVsSubject")} for a in active]
        if comps.get("aperture_label"):
            card["aperture"] = k["aperture"].format(label=comps["aperture_label"])
    ev = rep.get("comparable_events") or []
    if ev:
        card["changed_intro"] = k["changed_intro"]
        card["changed"] = [{"date": str(e.get("date"))[:10],
                            "headline": e.get("headline") or e.get("kind")} for e in ev[:5]]
    if ms.get("dom_median") and ms.get("dom_yoy_prev"):
        now, prev = int(round(ms["dom_median"])), int(round(ms["dom_yoy_prev"]))
        card["two_true_intro"] = k["two_true_intro"]
        card["two_true"] = k["two_true"].format(
            direction="faster" if now < prev else "more slowly", dom=now, dom_prev=prev,
            active=ms.get("active_listings"), active_delta=abs(ms.get("active_listings_mom_pct", 0)),
            fewer_more="fewer" if ms.get("active_listings_mom_pct", 0) < 0 else "more")
        card["two_true_close"] = k["two_true_close"]
        if ms.get("qoq_suppressed_reason"):
            import re
            ns = re.findall(r"n=(\d+)", str(ms["qoq_suppressed_reason"]))
            # Strip the internal directive ("Do not state a QoQ change") — it is
            # instruction to us, not copy for a homeowner.
            if len(ns) >= 2:
                card["suppression"] = (f"We're not showing a quarter-on-quarter price change. "
                                       f"Only {ns[0]} and {ns[1]} sales sit behind the two "
                                       f"quarters — too few to separate a real movement from "
                                       f"ordinary variation.")
    return card if (active or card.get("two_true")) else None


def c09_buyer(b, c, x):
    k = c["card_09_buyer"]
    portrait = A._buyer_portrait(b) if hasattr(A, "_buyer_portrait") else None
    if not portrait:
        return None
    card = {"type": "buyer", "answer": k["answer"], "portrait": portrait,
            "reframe": k["reframe"], "next": k["opens"]}
    frame = (b.get("buyer") or {}).get("primary_frame")
    if hasattr(A, "_persona_fit") and hasattr(A, "_home_signals"):
        fit = A._persona_fit(frame, A._home_signals(b))
        if fit:
            card["fit"] = k["fit"].format(drivers=A._join_plain(fit))
    return card


def c10_control(b, c, x):
    """NEW TYPE."""
    k = c["card_10_control"]
    card = {"type": "control", "answer": k["answer"], "body": k["body"],
            "see_record": k["see_record"], "correct": k["correct"],
            "not_sold_on": k["not_sold_on"]}
    gaps = b.get("gaps") or []
    for g in gaps:
        if "bathroom" in g or "bedroom" in g:
            card["gap_ask"] = k["gap_ask"].format(gap=g.replace(" unknown", ""))
            break
    return card


_EMITTERS = [c00_arrival, c01_range, c02_evidence, c03_comparable, c04_rarity,
             c05_method, c06_dispersion, c07_gain, c08_competition, c09_buyer,
             c10_control]

# Canonical copy block per position — the question that INTRODUCES card i is the
# `opens` of block i-1. Needed because emitters return None when data is missing
# and those gaps are common; without re-chaining, a card closes with a question
# the next rendered card does not answer.
_CANON = ["card_00_arrival", "card_01_range", "card_02_evidence",
          "card_03_comparable", "card_04_rarity", "card_05_method",
          "card_06_dispersion", "card_07_gain", "card_08_competition",
          "card_09_buyer", "card_10_control"]


def emit_v4(slug):
    b = json.loads((A.BUNDLE_DIR / f"{slug}.json").read_text())
    c = load_copy_v4()
    b["_discovery"] = A.detect_discovery(b)
    x = _extras(b)
    cards = []
    for i, f in enumerate(_EMITTERS):
        try:
            card = f(b, c, x)
        except Exception as e:
            print(f"  ! {f.__name__}: {type(e).__name__}: {e}", file=sys.stderr)
            card = None
        if card:
            card["_canon"] = i
            cards.append({k_: (_strip_md(v_) if isinstance(v_, str) else v_)
                          for k_, v_ in card.items()})
    # Re-chain: card i closes with the question that introduces the card that
    # ACTUALLY follows — the `opens` of the copy block immediately before it.
    for i, card in enumerate(cards):
        card["n"] = i
        if i + 1 < len(cards):
            intro_block = _CANON[max(0, cards[i + 1]["_canon"] - 1)]
            card["next"] = (c.get(intro_block) or {}).get("opens") or card.get("next")
        else:
            card.pop("next", None)
        card.pop("_canon", None)
    new_types = sorted({c_["type"] for c_ in cards} - KNOWN_TYPES)
    return {"slug": b["slug"], "suburb_key": b.get("suburb_key"),
            "address": b.get("address"), "address_short": b.get("address_short"),
            "suburb_display": b.get("suburb_display"),
            "lead_angle": b["_discovery"].get("angle"),
            "engine_version": "disc-v4", "cards": cards,
            "build_notes": {"gaps": b.get("gaps"), "new_types": new_types,
                            "n_cards": len(cards)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="upsert to system_monitor.offmarket_discovery_v4 (NOT the live arm)")
    args = ap.parse_args()
    doc = emit_v4(args.slug)
    (OUT_DIR / f"{args.slug}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    if args.write:
        get_mongo_client()["system_monitor"]["offmarket_discovery_v4"].update_one(
            {"slug": doc["slug"]}, {"$set": doc}, upsert=True)
        print(f"→ offmarket_discovery_v4/{doc['slug']}")
    if args.print:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    print(f"{len(doc['cards'])} cards · new types needing React: "
          f"{', '.join(doc['build_notes']['new_types']) or 'none'}", file=sys.stderr)


if __name__ == "__main__":
    main()
