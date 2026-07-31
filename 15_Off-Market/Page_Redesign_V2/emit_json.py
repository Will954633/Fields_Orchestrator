#!/usr/bin/env python3
"""
emit_json.py — render a cached fact bundle into the render-ready JSON the React
Discovery deck consumes (schema: SCOPE_React_Port.md §1).

Reuses ALL of assemble.py's logic (discovery engine, angle copy, insights,
personas, tiered valuation) — this is the SAME content as the markdown, just
emitted as typed card dicts instead of formatted strings. Copy stays in
copy.yaml (the single source); React is presentation-only.

  python3 emit_json.py --slug 8-corina-close-robina --print
"""
import re
import json
import argparse
from pathlib import Path

import assemble as A

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "json"
OUT_DIR.mkdir(exist_ok=True)


def _fill(s, ctx):
    try:
        return s.format(**ctx)
    except Exception:
        return s


def _doorstep(lines):
    out = []
    for ln in lines:
        m = re.match(r"^(\d+m)\s+from\s+(.+)$", ln)
        if m:
            out.append({"dist": m.group(1), "name": m.group(2)})
        else:
            out.append({"dist": "", "name": ln})
    return out


# ---- card emitters (mirror assemble.card_0X gates, return dicts) ----

def _recognition(b, c):
    k = c["card_01_recognition"]
    cred = b.get("credibility") or {}
    ctx = {"characteristics": A.num(cred.get("characteristics") or A._characteristics_count(b)),
           "sales_reviewed": A.num(cred.get("sales_reviewed")),
           "homes_compared": A.floor_k(cred.get("homes_compared"))}
    cred_lines = []
    for ln in k["credibility_lines"]:
        toks = A._tokens(ln)
        if all(ctx.get(t) is not None for t in toks):
            # split "{fig} rest" → fig + text
            fig_tok = toks[0] if toks else None
            fig = ctx.get(fig_tok, "")
            plus = "+" in ln.split("}", 1)[1][:1] if "}" in ln else False
            text = ln.split("}", 1)[1].lstrip("+ ").strip() if "}" in ln else ln
            cred_lines.append({"fig": fig + ("+" if plus else ""), "text": text})
    return {"type": "recognition", "n": 1,
            "headline": k["headline"],
            "address": f"{b['address_short']}, {b['suburb_display']}",
            "lede": k["body"].strip(),
            "credibility": cred_lines,
            "next": k["opens"]}


def _hook(b, c):
    k = c["card_02_hook"]
    disc = b.get("_discovery") or {}
    angle = disc.get("angle") or "market_context"
    hooks = k.get("hooks") or {}
    hook = hooks.get(angle) or hooks["market_context"]
    if "{a}" in hook:
        score = (disc.get("scores") or {}).get(angle, 0)
        lvl = "strong" if score >= A._HOOK_STRONG_BAR.get(angle, 999) else "moderate"
        adj = ((k.get("intensity") or {}).get(angle) or {}).get(lvl, "")
        hook = hook.format(a=adj)
    return {"type": "hook", "n": 2, "answer": k["answer"], "headline": hook,
            "body": k["body"].strip(), "cta_label": k["cta"], "next": k["opens"]}


def _reveal(b, c):
    k = c["card_03_rarity"]
    sc = b.get("scarcity") or {}
    matching, total = sc.get("active_matching"), sc.get("active_total")
    if matching is None or not total:
        return None
    angle = (b.get("_discovery") or {}).get("angle") or "market_context"
    ang = (c.get("angles") or {}).get(angle) or c["angles"]["market_context"]
    ctx = A._angle_ctx(b)
    try:
        lead = ang["c03_lead"].format(**ctx)
    except Exception:
        ang = c["angles"]["market_context"]
        lead = ang["c03_lead"].format(**ctx)
    card = {"type": "reveal", "n": 3, "answer": ang["c03_answer"],
            "lead": lead, "lead_bold": bool(ang.get("c03_lead_bold")),
            "lead_accent": ctx.get("green_name") if angle in ("parkland", "water_adjacent") else None,
            "next": k["opens"]}
    # supporting boundary line (non-lead greenspace)
    gsp = (b.get("green_space") or {}).get("premium") or {}
    if angle not in ("parkland", "water_adjacent") and gsp.get("relation") in ("backs onto", "adjoins"):
        card["boundary_line"] = f"Its boundary {gsp['relation']} {gsp.get('name') or ('a ' + gsp['kind'])}."
    # features
    feat_lines = [nf.get("phrase") for nf in (sc.get("notable") or []) if nf.get("phrase")]
    if feat_lines:
        card["features_intro"] = ang.get("c03_reveal_intro") or k["reveal_intro_default"]
        card["features"] = feat_lines
    # POI-aware rarity
    pr = b.get("poi_rarity") or {}
    cl = pr.get("cluster") or {}
    phys = pr.get("physical_matching")
    if (cl.get("features") and len(cl["features"]) >= 2 and phys and phys >= 3
            and 1 <= cl.get("matching", 0) < phys and (cl.get("share_pct") or 100) <= 60):
        card["rarity"] = k["poi_rarity_line"].format(
            physical_matching=phys, matching=cl["matching"], phrase=cl["phrase"],
            verb="is" if cl["matching"] == 1 else "are")
    # doorstep
    poi = []
    if gsp.get("relation") == "steps from":
        poi.append(f"{gsp['edge_m']:.0f}m from {gsp.get('name') or gsp['kind']}")
    poi += A._poi_lines(b, angle)
    seen, ded = set(), []
    for line in poi:
        m = re.search(r"(?:from|to) (.+?)(?: \(|$)", line)
        nm = (m.group(1) if m else line).strip().lower()
        if nm in seen:
            continue
        seen.add(nm)
        ded.append(line)
    if ded:
        card["doorstep_intro"] = k["location_intro"]
        card["doorstep"] = _doorstep(ded)
    _attach_insight(card, b, "card_03")
    return card


def _explanation(b, c):
    k = c["card_04_explanation"]
    angle = (b.get("_discovery") or {}).get("angle") or "market_context"
    ang = (c.get("angles") or {}).get(angle) or c["angles"]["market_context"]
    ctx = A._angle_ctx(b)

    def fmt(s):
        try:
            return s.format(**ctx)
        except Exception:
            return s

    card = {"type": "explanation", "n": 4, "answer": ang["c04_answer"],
            "headline": fmt(ang["c04_headline"]).strip(), "next": k["opens"]}
    if ang.get("c04_mode") == "filters":
        checklist = list(b.get("filter_checklist") or [])
        if not checklist:
            return None
        if b.get("suburb_display") in A.FAMILY_SUBURBS and "family suburb" not in checklist:
            checklist.append("family suburb")
        card["filters"] = {"body": ang["c04_body"].strip(), "intro": ang["c04_filter_intro"],
                           "items": checklist, "close": ang["c04_close"]}
    else:
        card["close"] = fmt(ang["c04_close"])
    wt = b.get("wait_time") or {}
    if wt.get("combo_phrase") and wt.get("interval_phrase"):
        card["wait"] = {"intro": k["wait_intro"],
                        "line": k["wait_line"].format(combo_phrase=wt["combo_phrase"],
                                                      interval_phrase=wt["interval_phrase"]),
                        "disclaimer": k["wait_disclaimer"]}
    return card


def _competition(b, c):
    k = c["card_05_competition"]
    comp = b.get("competition") or {}
    total, n_compete = comp.get("n_total"), comp.get("n_compete")
    homes = (b.get("credibility") or {}).get("homes_compared")
    if total is None:
        return None
    labels = list(k["funnel_labels"])
    labels[0] = labels[0].format(suburb=b["suburb_display"])
    tiers = [{"label": labels[0], "value": A.floor_k(homes)},
             {"label": labels[1], "value": A.num(total)}]
    if n_compete is not None:
        tiers.append({"label": labels[2], "value": A.num(n_compete), "final": True})
    tiers = [t for t in tiers if t["value"] is not None]
    card = {"type": "competition", "n": 5, "answer": k["answer"],
            "headline": k["headline"].strip(), "funnel": tiers, "next": k["opens"]}
    if n_compete == 0:
        card["none_note"] = k["none_note"]
    return card


def _comparable(b, c):
    k = c["card_06_comparable"]
    oc = b.get("obvious_comp")
    if not oc or not oc.get("price"):
        return None
    card = {"type": "comparable", "n": 6, "answer": k["answer"],
            "comp": {"address": oc["address"], "price": A.money(oc["price"]),
                     "distance_m": oc.get("distance_m"), "deltas": oc.get("deltas") or []},
            "looks": k["looks"], "reveal_intro": k["reveal_intro"],
            "close": k["close"], "next": k["opens"]}
    _attach_insight(card, b, "card_06")
    return card


def _value_drivers(b, c):
    k = c["card_07_value_drivers"]
    vd = b.get("value_drivers") or {}
    carries = vd.get("carries_price") or []
    if not carries:
        return None
    card = {"type": "value_drivers", "n": 7, "answer": k["answer"],
            "strengthens": {"intro": k["strengthens_intro"], "items": carries},
            "close": k["close"], "next": k["opens"]}
    levers = list(b.get("negotiation_levers") or [])
    det = (b.get("green_space") or {}).get("detractor") or {}
    if det.get("relation"):
        levers.append(f"{det['relation']} {det.get('name') or det['kind']}")
    if levers:
        card["negotiate"] = {"intro": k["negotiate_intro"], "items": levers}
    _attach_insight(card, b, "card_07")
    return card


def _buyer(b, c):
    k = c["card_08_buyer"]
    portrait = A._buyer_portrait(b)
    if not portrait:
        return None
    card = {"type": "buyer", "n": 8, "answer": k["answer"], "portrait": portrait,
            "reframe": k["reframe"], "next": k["opens"]}
    frame = (b.get("buyer") or {}).get("primary_frame")
    fit = A._persona_fit(frame, A._home_signals(b))
    if fit:
        card["fit"] = k["fit_template"].format(drivers=A._join_plain(fit))
    return card


def _valuation(b, c):
    k = c["card_09_valuation"]
    val = b.get("valuation")
    if not val or not val.get("low") or not val.get("high"):
        return None
    ctx = {"val_low": A.money(val["low"]), "val_high": A.money(val["high"]),
           "n_comps": val.get("n_comps"), "anchor": A._anchor(val["low"], val["high"], val.get("point"))}
    basis = [ln.format(**ctx) for ln in k["basis_lines"]
             if all(ctx.get(t) is not None for t in A._tokens(ln))]
    card = {"type": "valuation", "n": 9, "answer": k["answer"],
            "likely_intro": k["likely_intro"], "anchor": k["likely_value"].format(**ctx),
            "range_intro": k["range_intro"], "range": k["range_value"].format(**ctx),
            "range_note": k["range_note"], "basis": basis,
            "closing": k["closing"], "next": k["opens"]}
    if val.get("method") and val["method"] != "engine":
        card["tier_caveat"] = val.get("confidence_reason") or val.get("confidence")
    return card


def _strategy(b, c):
    k = c["card_10_strategy"]
    pos = b.get("positioning") or {}
    if not pos.get("frame_line"):
        return None
    avoid = [(a.get("noun") if isinstance(a, dict) else a) for a in (pos.get("avoid") or [])]
    return {"type": "strategy", "n": 10, "answer": k["answer"],
            "frame_line": pos["frame_line"], "lead_line": pos.get("lead_line"),
            "avoid": avoid, "cta_label": k["cta"]}


def _attach_insight(card, b, card_key):
    txt = (b.get("_insights") or {}).get(card_key)
    if txt:
        card["insight"] = txt


_EMITTERS = [_recognition, _hook, _reveal, _explanation, _competition,
             _comparable, _value_drivers, _buyer, _valuation, _strategy]


def _strip_md(v):
    """Remove markdown bold (**…**) from every string in the tree — React styles
    its own emphasis, so the JSON carries clean text."""
    if isinstance(v, str):
        return v.replace("**", "")
    if isinstance(v, list):
        return [_strip_md(x) for x in v]
    if isinstance(v, dict):
        return {k: _strip_md(x) for k, x in v.items()}
    return v


def emit_json(slug):
    b = json.loads((A.BUNDLE_DIR / f"{slug}.json").read_text())
    c = A.load_copy()
    disc = A.detect_discovery(b)
    b["_discovery"] = disc
    b["_insights"] = A._select_insights(b, c)
    cards = [_strip_md(f(b, c)) for f in _EMITTERS]
    cards = [c_ for c_ in cards if c_]
    return {
        "slug": b["slug"],
        "suburb_key": b.get("suburb_key"),
        "address": b.get("address"),
        "address_short": b.get("address_short"),
        "suburb_display": b.get("suburb_display"),
        "lead_angle": disc.get("angle"),
        "hero_image": None,
        "engine_version": "disc-v1",
        "cards": cards,
        "build_notes": {"discovery_scores": disc.get("scores"), "gaps": b.get("gaps")},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    doc = emit_json(args.slug)
    out = OUT_DIR / f"{args.slug}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    if args.print:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    import sys
    print(f"→ {out}  ({len(doc['cards'])} cards, lead={doc['lead_angle']})", file=sys.stderr)


if __name__ == "__main__":
    main()
