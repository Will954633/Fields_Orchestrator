#!/usr/bin/env python3
"""
assemble.py — turn a cached fact bundle + copy.yaml into the 10-card
Discovery Experience as a markdown document.

This is the CHEAP, deterministic half. No DB, no LLM, no network. Re-run it as
many times as you like while tuning copy.yaml — it only reads bundles/<slug>.json.

  python3 assemble.py --slug 38-beaconsfield-drive-burleigh-waters
  python3 assemble.py --slug X --out output/X.md

Design rules (from the marketing directive):
  * Every card = answer(previous) -> reveal -> opens(next). The curiosity loop
    is the product; the data is the delivery mechanism.
  * A card with no honest data is OMITTED, never faked. Omissions are recorded
    in the trailing build-notes block so we can see what a thin home loses.
  * The valuation number appears at card 9, never earlier.
"""
import os
import re
import sys
import json
import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BUNDLE_DIR = HERE / "bundles"
OUT_DIR = HERE / "output"
OUT_DIR.mkdir(exist_ok=True)


def load_copy():
    return yaml.safe_load((HERE / "copy.yaml").read_text())


def money(v):
    try:
        return "${:,}".format(int(round(float(v))))
    except Exception:
        return None


def num(v):
    try:
        return "{:,}".format(int(v))
    except Exception:
        return None


def floor_k(v):
    """Round an int down to the nearest 1,000, comma-formatted (e.g. 7063 -> '7,000')."""
    try:
        return "{:,}".format((int(v) // 1000) * 1000)
    except Exception:
        return None


# Core suburbs we can honestly call family suburbs (card 04 filter).
FAMILY_SUBURBS = {"Robina", "Varsity Lakes", "Burleigh Waters"}


def _characteristics_count(b):
    """A real, defensible count of signals analysed for THIS home."""
    subj = b.get("subject") or {}
    n = sum(1 for v in subj.values() if v not in (None, "", False))
    n += len(b.get("proximity") or {})
    n += len(b.get("scarcity", {}).get("notable") or [])
    return n


# ---- discovery engine (v1: label the lead story; reordering comes later) ----

# A lead story must clear this to beat a plain market-context opening.
MIN_LEAD_SCORE = 3


def detect_discovery(b):
    """Score the candidate lead stories and return the strongest with a reason.
    Deterministic — this is what makes two homes read differently.

    Rules that fixed the old "everything leads scarcity" bug:
      * an angle is only ADDED to the scores when its evidence is genuinely
        present (no score-0 keys polluting the max), and
      * scarcity must clear a real rarity bar before it can register at all.
    """
    subj = b.get("subject") or {}
    sc = b.get("scarcity") or {}
    comp = b.get("competition") or {}
    val = b.get("valuation") or {}
    prox = b.get("proximity") or {}
    land = subj.get("land_sqm") or 0
    floor = subj.get("floor_sqm") or 0
    rl = subj.get("renovation_level")
    matching, total = sc.get("active_matching"), sc.get("active_total")
    n_compete = comp.get("n_compete")

    scores, reasons = {}, {}

    def add(key, score, reason):
        if score >= 1:
            scores[key] = score
            reasons[key] = reason

    # Rebalanced 2026-07-31 (Will): VIVID physical standouts (things a buyer can
    # SEE — backing onto a park/lake, water views, big land, the beach) score 8-9
    # and beat generic scarcity, which is capped at ~6. Scarcity still leads when
    # a home has NO vivid feature; moderate features (score ~5) lose to it.

    # --- SCARCITY (capped so a vivid feature can outrank it) ---
    if matching is not None and total:
        share = matching / total
        s = 0
        if n_compete == 0:
            s += 3
        if share <= 0.03:
            s += 3
        elif share <= 0.07:
            s += 2
        elif share <= 0.12:
            s += 1
        if s >= 3:  # below this it simply isn't a scarcity story
            tail = " and nothing on the market competes" if n_compete == 0 else ""
            add("scarcity", s, f"only {matching} of {total} homes share the combination{tail}")

    # --- WATER VIEWS (vivid) ---
    if subj.get("water_views"):
        add("water_views", 8, "carries water views — scarce and high-demand")

    # --- BEACHSIDE proximity (vivid when close) ---
    beach_m = (prox.get("beach") or {}).get("distance_m")
    if beach_m and beach_m <= 1500:
        add("beachside", 8 if beach_m <= 900 else 5,
            f"~{beach_m}m to {(prox.get('beach') or {}).get('name')}")

    # --- LAND / PRESTIGE (vivid at 900m²+, moderate below) ---
    if land >= 900:
        add("land_prestige", 8, f"{land}m² block — top-tier land")
    elif land >= 750:
        add("land_prestige", 5, f"{land}m² block — generous land")

    # --- RENOVATION UPSIDE (moderate) ---
    if isinstance(rl, (int, float)) and rl <= 2 and land >= 600:
        add("renovation_upside", 5, f"dated (level {rl}) on {land}m² — clear value-add")

    # --- PRESTIGE VALUE BRACKET (moderate) ---
    if val.get("low") and val["low"] >= 2_000_000:
        add("prestige_value", 5, f"range opens above {money(val['low'])}")

    # --- SCALE (moderate) ---
    if floor >= 300:
        add("scale", 5, f"{floor}m² of floor area — an unusually large home")

    # --- SCHOOL-WALK FAMILY (moderate) ---
    school_m = (prox.get("primary_school") or {}).get("distance_m")
    if school_m and school_m <= 600:
        add("school_walk", 5, f"~{school_m}m walk to {(prox.get('primary_school') or {}).get('name')}")
    elif school_m and school_m <= 900:
        add("school_walk", 4, f"~{school_m}m to {(prox.get('primary_school') or {}).get('name')}")

    # --- THIN COMPETITION (few, but not zero, genuine rivals) ---
    if isinstance(n_compete, int) and 1 <= n_compete <= 3:
        add("thin_competition", 4, f"only {n_compete} genuine competitor(s) on the market right now")

    # --- BOUNDARY ADJACENCY (vivid; OSM polygon edge-adjacency) ---
    # backs onto = 9, adjoins = 8 — a park routes to `parkland`, a lake/river to
    # `water_adjacent`. Both beat capped scarcity.
    gsp = (b.get("green_space") or {}).get("premium") or {}
    rel = gsp.get("relation")
    if rel in ("backs onto", "adjoins"):
        base = 9 if rel == "backs onto" else 8
        nm = gsp.get("name") or gsp.get("kind")
        if gsp.get("kind") in GREEN_LEAD_KINDS:
            add("parkland", base, f"{rel} {nm} ({gsp['edge_m']}m to the boundary)")
        elif gsp.get("kind") in WATER_LEAD_KINDS:
            add("water_adjacent", base, f"{rel} {nm} ({gsp['edge_m']}m to the boundary)")

    if not scores:
        return {"angle": "market_context",
                "reason": "no single standout — a general market-context opening",
                "scores": {}}
    angle, top = max(scores.items(), key=lambda kv: kv[1])
    if top < MIN_LEAD_SCORE:
        return {"angle": "market_context",
                "reason": "no angle strong enough to lead — market-context opening",
                "scores": scores}
    return {"angle": angle, "reason": reasons.get(angle, ""), "scores": scores}


# ---- card renderers -------------------------------------------------------
# Each returns a markdown string, or None to OMIT the card.

def _bullets(items, mark="-"):
    return "\n".join(f"{mark} {x}" for x in items if x)


def _select_insights(b, c):
    """Pick ≤2 research-backed 'did you know' delights genuinely relevant to this
    home. Returns {card_key: text}. Data, not advice; fired sparingly."""
    cfg = c.get("insights") or {}
    subj = b.get("subject") or {}
    suburb = b.get("suburb_display")
    gp = (b.get("green_space") or {}).get("premium") or {}

    def eligible(trig):
        if trig == "water":
            # confirmed water views OR a genuine water frontage (backs onto /
            # adjoins) — NOT merely "steps from" a lake, where the water-views
            # premium wouldn't honestly apply.
            frontage = (gp.get("kind") in ("water", "river", "canal", "creek")
                        and gp.get("relation") in ("backs onto", "adjoins"))
            return bool(subj.get("water_views")) or frontage
        if trig == "pool":
            return bool(subj.get("pool"))
        if trig == "beds4plus":
            return (subj.get("bedrooms") or 0) >= 4
        if trig == "has_floor":
            return bool(subj.get("floor_sqm"))
        return False

    cands = []
    for spec in cfg.values():
        if not eligible(spec.get("trigger")):
            continue
        text = spec["text"]
        sv = (spec.get("suburb_value") or {}).get(suburb)
        if "{value}" in text and not sv:
            continue  # no suburb-specific figure → skip rather than show a blank
        text = text.replace("{value}", sv or "").replace("{suburb}", suburb or "your suburb")
        cands.append((spec.get("priority", 0), spec["card"], text))

    cands.sort(key=lambda x: -x[0])
    out, used = {}, set()
    for _pri, card, text in cands:
        if card in used or len(out) >= 2:   # ≤1 per card, ≤2 per deck
            continue
        out[card] = text
        used.add(card)
    return out


def _insight_parts(b, card_key):
    """Parts-list fragment for a card's delight callout (empty if none here)."""
    txt = (b.get("_insights") or {}).get(card_key)
    return ["", f"> 💡 *{txt}*"] if txt else []


def card_01(b, c):
    k = c["card_01_recognition"]
    cred = b.get("credibility") or {}
    ctx = {
        "characteristics": num(cred.get("characteristics") or _characteristics_count(b)),
        "sales_reviewed": num(cred.get("sales_reviewed")),
        "homes_compared": floor_k(cred.get("homes_compared")),
    }
    lines = [ln.format(**ctx) for ln in k["credibility_lines"]
             if all(ctx.get(t) is not None for t in _tokens(ln))]
    parts = [
        f"**{b['address_short']}**",
        f"{b['suburb_display']}",
        "",
        k["headline"],
        "",
        k["body"].strip(),
    ]
    if lines:
        if k.get("credibility_intro"):
            parts += ["", k["credibility_intro"]]
        parts += ["", _bullets(lines)]
    parts += ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


# Score at/above which a size-angle hook uses the STRONG intensity word.
_HOOK_STRONG_BAR = {"land_prestige": 8, "scale": 5}


def card_02(b, c):
    k = c["card_02_hook"]
    disc = b.get("_discovery") or {}
    angle = disc.get("angle") or "market_context"
    hooks = k.get("hooks") or {}
    hook = hooks.get(angle) or hooks["market_context"]
    if "{a}" in hook:
        score = (disc.get("scores") or {}).get(angle, 0)
        level = "strong" if score >= _HOOK_STRONG_BAR.get(angle, 999) else "moderate"
        adj = ((k.get("intensity") or {}).get(angle) or {}).get(level, "")
        hook = hook.format(a=adj)
    return "\n".join([
        f"*{k['answer']}*", "",
        f"**{hook}**", "",
        k["body"].strip(), "",
        f"[ {k['cta']} ]", "",
        f"→ *{k['opens']}*",
    ])


def _angle_ctx(b):
    """Placeholder values available to the angle-specific opening-act copy."""
    subj = b.get("subject") or {}
    sc = b.get("scarcity") or {}
    comp = b.get("competition") or {}
    val = b.get("valuation") or {}
    prox = b.get("proximity") or {}
    gsp = (b.get("green_space") or {}).get("premium") or {}
    return {
        "active_matching": sc.get("active_matching"),
        "active_total": sc.get("active_total"),
        "land": subj.get("land_sqm"),
        "floor": subj.get("floor_sqm"),
        "beach_m": (prox.get("beach") or {}).get("distance_m"),
        "beach_name": (prox.get("beach") or {}).get("name"),
        "school_m": (prox.get("primary_school") or {}).get("distance_m"),
        "school_name": (prox.get("primary_school") or {}).get("name"),
        "n_compete": comp.get("n_compete"),
        "val_low": money(val.get("low")),
        "green_name": gsp.get("name") or gsp.get("kind"),
        "green_relation": gsp.get("relation"),
        "green_kind": gsp.get("kind"),
    }


# Boundary kinds that can lead. Green routes to the `parkland` angle; water to
# `water_adjacent`. (These homes are never is_waterfront — that's excluded from
# the off-market surface upstream — so surfacing a lake boundary is in-scope.)
GREEN_LEAD_KINDS = {"park", "reserve", "nature reserve", "bushland", "gardens",
                    "golf course", "open space", "wetland"}
WATER_LEAD_KINDS = {"water", "river", "canal", "creek"}


# POI lifestyle lines for Card 03. Straight-line distances (haversine) — so they
# say "from", never "a walk to" (only routed distances earn "walk"; see
# fix-history OFFMARKET-RARITY-POI-SOURCE). Groceries framed as a short drive.
POI_WALK = [("park", None), ("primary_school", "school"), ("childcare", None),
            ("beach", None), ("cafe", None)]


def _poi_lines(b, lead_angle, max_items=3):
    prox = b.get("proximity") or {}
    used_beach = lead_angle == "beachside"
    used_school = lead_angle == "school_walk"
    out = []
    for key, _ in POI_WALK:
        if key == "beach" and used_beach:
            continue           # already the headline — don't repeat it here
        if key == "primary_school" and used_school:
            continue
        p = prox.get(key)
        d = (p or {}).get("distance_m")
        if p and d and d <= 1200:
            out.append(f"{d}m from {p['name']}")
    lines = out[:max_items]
    # Supermarket as a short drive (a genuine convenience, rarely walkable).
    sm = prox.get("supermarket")
    if sm and sm.get("distance_km"):
        lines.append(f"a short drive to {sm['name']} ({sm['distance_km']}km)")
    return lines


def card_03(b, c):
    k = c["card_03_rarity"]
    sc = b.get("scarcity") or {}
    matching, total = sc.get("active_matching"), sc.get("active_total")
    if matching is None or not total:
        return None
    angle = (b.get("_discovery") or {}).get("angle") or "market_context"
    A = (c.get("angles") or {}).get(angle) or c["angles"]["market_context"]
    ctx = _angle_ctx(b)
    try:
        lead = A["c03_lead"].format(**ctx)
    except Exception:
        A = c["angles"]["market_context"]
        lead = A["c03_lead"].format(**ctx)

    parts = [f"*{A['c03_answer']}*", ""]
    parts += [f"**{lead}**" if A.get("c03_lead_bold") else lead]

    # Boundary adjacency (OSM) — a prominent supporting line when it's not
    # already the lead angle. "backs onto" / "adjoins" only (steps-from goes in
    # the doorstep layer below).
    gsp = (b.get("green_space") or {}).get("premium") or {}
    if angle not in ("parkland", "water_adjacent") and gsp.get("relation") in ("backs onto", "adjoins"):
        nm = gsp.get("name") or f"a {gsp['kind']}"
        parts += ["", f"Its boundary {gsp['relation']} **{nm}**."]

    # The scarcity "premium finish throughout" phrase is already gated on a real
    # GPT-vision quality score (>=9) upstream, so it only appears where we have
    # vision data to back it — keep it.
    feat_lines = [nf.get("phrase") for nf in (sc.get("notable") or []) if nf.get("phrase")]
    if feat_lines:
        parts += ["", A.get("c03_reveal_intro") or k["reveal_intro_default"],
                  _bullets(feat_lines, mark="✓")]

    # POI-AWARE RARITY — the walkable lifestyle cluster as part of the
    # combination. Shown only when a 2+ spot cluster genuinely narrows the
    # physical pool (a real rarity sub-story, not a stat true of everyone).
    pr = b.get("poi_rarity") or {}
    cl = pr.get("cluster") or {}
    phys = pr.get("physical_matching")
    if (cl.get("features") and len(cl["features"]) >= 2 and phys and phys >= 3
            and 1 <= cl.get("matching", 0) < phys and (cl.get("share_pct") or 100) <= 60):
        parts += ["", k["poi_rarity_line"].format(
            physical_matching=phys, matching=cl["matching"], phrase=cl["phrase"],
            verb="is" if cl["matching"] == 1 else "are")]

    # POI lifestyle layer — kept SEPARATE from the physical combination so it
    # never implies the scarcity count included proximity. Lead with a
    # "steps from <green space>" line when applicable.
    poi = []
    if gsp.get("relation") == "steps from":
        poi.append(f"{gsp['edge_m']:.0f}m from {gsp.get('name') or gsp['kind']}")
    poi += _poi_lines(b, angle)
    # Dedupe by place NAME — the OSM boundary line and the Google-Places POI line
    # can name the same park at two different distances (edge vs centroid). Keep
    # the first (the OSM edge distance is the more accurate "how close").
    seen, deduped = set(), []
    for line in poi:
        m = re.search(r"(?:from|to) (.+?)(?: \(|$)", line)
        nm = (m.group(1) if m else line).strip().lower()
        if nm in seen:
            continue
        seen.add(nm)
        deduped.append(line)
    poi = deduped
    if poi:
        parts += ["", k["location_intro"], _bullets(poi, mark="•")]
    parts += _insight_parts(b, "card_03")
    parts += ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def card_04(b, c):
    k = c["card_04_explanation"]
    angle = (b.get("_discovery") or {}).get("angle") or "market_context"
    A = (c.get("angles") or {}).get(angle) or c["angles"]["market_context"]
    ctx = _angle_ctx(b)

    def fmt(s):
        try:
            return s.format(**ctx)
        except Exception:
            return s

    parts = [f"*{A['c04_answer']}*", "", f"**{fmt(A['c04_headline']).strip()}**"]

    if A.get("c04_mode") == "filters":
        # Scarcity spine: the buyer-filter checklist.
        checklist = list(b.get("filter_checklist") or [])
        if not checklist:
            return None
        if b.get("suburb_display") in FAMILY_SUBURBS and "family suburb" not in checklist:
            checklist.append("family suburb")
        parts += ["", A["c04_body"].strip(), "", A["c04_filter_intro"],
                  _bullets(checklist, mark="✓"), "", A["c04_close"]]
    else:
        # Every other angle: the angle's buyer psychology, tied back.
        parts += ["", fmt(A["c04_close"])]

    # WAIT-TIME — supply scarcity over time, on genuinely rare homes only.
    wt = b.get("wait_time") or {}
    if wt.get("combo_phrase") and wt.get("interval_phrase"):
        parts += ["", k["wait_intro"],
                  k["wait_line"].format(combo_phrase=wt["combo_phrase"],
                                        interval_phrase=wt["interval_phrase"]),
                  "", f"<sub>{k['wait_disclaimer']}</sub>"]

    parts += ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def card_05(b, c):
    k = c["card_05_competition"]
    comp = b.get("competition") or {}
    total, n_compete = comp.get("n_total"), comp.get("n_compete")
    homes = (b.get("credibility") or {}).get("homes_compared")
    if total is None:
        return None
    labels = list(k["funnel_labels"])
    labels[0] = labels[0].format(suburb=b["suburb_display"])
    # (label, value) tiers — drop any tier whose value we don't honestly have.
    tiers = [(labels[0], floor_k(homes)), (labels[1], num(total))]
    if n_compete is not None:
        tiers.append((labels[2], num(n_compete)))
    funnel_lines = []
    for i, (label, value) in enumerate(tiers):
        if value is None:
            continue
        if i > 0:
            funnel_lines.append("↓")
        funnel_lines += [f"**{label}**", value]
    parts = [f"*{k['answer']}*", "", f"**{k['headline'].strip()}**", "",
             "\n".join(funnel_lines)]
    if n_compete == 0:
        parts += ["", k["none_note"]]
    parts += ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def card_06(b, c):
    k = c["card_06_comparable"]
    oc = b.get("obvious_comp")
    if not oc or not oc.get("price"):
        return None
    deltas = oc.get("deltas") or []
    parts = [
        f"*{k['answer']}*", "",
        f"**{k['headline'].format(comp_address=oc['address'], comp_price=money(oc['price']), comp_distance_m=oc.get('distance_m'))}**", "",
        k["looks"],
    ]
    if deltas:
        parts += ["", k["reveal_intro"], _bullets(deltas, mark="•")]
    parts += ["", k["close"]] + _insight_parts(b, "card_06") + ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def card_07(b, c):
    k = c["card_07_value_drivers"]
    vd = b.get("value_drivers") or {}
    carries = vd.get("carries_price") or []
    if not carries:
        return None
    parts = [f"*{k['answer']}*", "", k["strengthens_intro"], _bullets(carries, mark="✓")]
    # "where a buyer may focus" — genuine feature gaps + any boundary detractor.
    levers = list(b.get("negotiation_levers") or [])
    det = (b.get("green_space") or {}).get("detractor") or {}
    if det.get("relation"):
        levers.append(f"{det['relation']} {det.get('name') or det['kind']}")
    if levers:
        parts += ["", k["negotiate_intro"], _bullets(levers, mark="~")]
    parts += ["", k["close"]] + _insight_parts(b, "card_07") + ["", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def _join_plain(items):
    items = [x for x in items if x]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _clean_driver(s):
    import re
    s = re.sub(r"^a \d+[- ]metre walk to ", "the walk to ", s)
    s = re.sub(r"^a \d+[- ]min(ute)? walk to ", "the walk to ", s)
    s = re.sub(r"^the ", "", s)
    return s.strip()


def _buyer_portrait(b):
    """A believable human buyer with a motivation — built from the positioning
    archetype + this home's suburb / nearest school. Data -> human -> motivation."""
    suburb = b.get("suburb_display") or "the area"
    prox = b.get("proximity") or {}
    sch = prox.get("primary_school") or {}
    school_name = sch.get("name") if (sch.get("distance_m") or 9e9) <= 1000 else None
    frame = (b.get("buyer") or {}).get("primary_frame")
    if not frame:
        return None
    fam_school = (f"A family who'd rather walk the kids to {school_name} than drive — "
                  f"and settle into {suburb} for good." if school_name else
                  f"A family who wants to raise the kids in {suburb} and stay close to the local schools.")
    T = {
        "school_walk_family": fam_school,
        "land_lifestyle_family": (f"A family who has outgrown their current home but wants the space "
                                  f"and backyard to stay in {suburb} for the long haul."),
        "beachside_lifestyle": (f"A buyer chasing the {suburb} lifestyle who still wants a proper home, "
                                f"not just somewhere near the water."),
        "turnkey_downsizer": (f"A downsizer ready to leave stairs and a big garden behind, after an easy "
                              f"single-level home in {suburb}."),
        "renovator_valueadd": (f"A buyer after a solid home on real land in {suburb} they can make their "
                               f"own over time."),
        "prestige_privacy": (f"A buyer at the top of the {suburb} market who wants space, privacy and room "
                             f"between them and the neighbours."),
        "scarcity_play": (f"A buyer who's been watching {suburb} for exactly this combination — and won't "
                          f"settle for close enough."),
    }
    return T.get(frame) or f"A buyer who has been waiting for a home like this in {suburb}."


def _finish_signal(feat):
    """Returns 'premium' / 'renovated' / None from the GPT-4 vision reads.
    None when the property was never vision-analysed — in which case we make no
    finish claim at all. Thresholds mirror the scarcity engine (quality >= 9)."""
    qs = feat.get("renovation_quality_score")
    rl = feat.get("renovation_level")
    if qs is None and rl is None:
        return None                      # no vision data → no claim
    if qs is not None and qs >= 9:
        return "premium"
    if rl is not None and rl >= 4:       # "fully_renovated"
        return "renovated"
    return None                          # vision data exists but doesn't support a finish claim


# Kinds of boundary feature that count as a genuine buyer draw at the fence.
_ADJ_KINDS = {"park", "reserve", "nature reserve", "bushland", "gardens",
              "golf course", "open space", "wetland", "water", "river",
              "canal", "creek", "beach"}


def _home_signals(b):
    """What this home actually offers a buyer — the raw material a persona's
    needs get matched against."""
    feat = b.get("subject") or {}
    prox = b.get("proximity") or {}
    gsp = (b.get("green_space") or {}).get("premium") or {}
    notable = " ".join((nf.get("phrase") or "") for nf in
                       (b.get("scarcity", {}).get("notable") or [])).lower()

    def near(cat, thr):
        p = prox.get(cat) or {}
        d = p.get("distance_m")
        return (p.get("name"), int(d)) if (d and d <= thr) else (None, None)

    adj = None
    if gsp.get("relation") in ("backs onto", "adjoins") and gsp.get("kind") in _ADJ_KINDS:
        adj = (gsp.get("name"), gsp.get("kind"), gsp.get("relation"))
    return {
        "suburb": b.get("suburb_display"),
        "adj": adj,
        "pool": bool(feat.get("pool")),
        "single_level": bool(feat.get("single_level")),
        # FINISH — only when the property has a genuine GPT-4 vision read
        # (renovation_quality_score / renovation_level present). No vision data
        # => finish is None and we make no finish/presentation claim (Will's rule).
        "finish": _finish_signal(feat),
        "land": feat.get("land_sqm"),
        "big_land": (feat.get("land_sqm") or 0) >= 750,
        "floor": feat.get("floor_sqm"),
        "school": near("primary_school", 1100),
        "childcare": near("childcare", 900),
        "park": near("park", 700),
        "cafe": near("cafe", 650),
        "shops": near("supermarket", 1300),
        "beach": near("beach", 1600),
    }


def _adj_phrase(sig, mode):
    """The boundary feature, phrased for what THIS persona cares about."""
    if not sig["adj"]:
        return None
    name, kind, rel = sig["adj"]
    nm = name or ("the " + (kind or "reserve"))
    watery = kind in ("water", "river", "canal", "creek", "beach")
    verb = "backing onto" if rel == "backs onto" else "right beside"
    if mode == "family":
        # ⚠ NOT "a backyard the kids share with no one". That is listing-brochure
        # voice, and on the V4 report it arrives after twenty sections of
        # measured evidence — the tonal break costs more than the phrase adds.
        # State the boundary fact; the reader supplies the feeling.
        return f"{verb} {nm} — no neighbour behind" if not watery else f"{verb} {nm}"
    if mode == "stroll":
        return f"{nm} to wander at the door"
    if mode == "outlook":
        return f"{verb} {nm}, so the outlook stays open and can't be built out"
    if mode == "valueadd":
        return f"{verb} {nm} — protected open space behind them"
    return f"{verb} {nm}"


def _persona_fit(frame, s):
    """Ordered reasons THIS persona would pay for, drawn only from what the home
    has. Encodes what each buyer type actually needs — e.g. a downsizer reads a
    pool as upkeep (omitted); a renovator wants land, not finish."""
    out = []
    def add(x):
        if x and x not in out:
            out.append(x)
    school = f"the morning walk to {s['school'][0]}" if s["school"][0] else None
    childcare = f"{s['childcare'][0]} a pram-push away" if s["childcare"][0] else None
    cafe = f"coffee at {s['cafe'][0]} around the corner" if s["cafe"][0] else None
    shops = f"{s['shops'][0]} within walking distance" if s["shops"][0] else None
    park = f"{s['park'][0]} a short walk away" if s["park"][0] else None
    beach = f"the beach barely {s['beach'][1]}m away" if s["beach"][0] else None

    # Finish — ONLY when a GPT-vision read supports it (s["finish"] is not None).
    def finish(premium, renovated):
        if s.get("finish") == "premium":
            return premium
        if s.get("finish") == "renovated":
            return renovated
        return None

    if frame == "school_walk_family":
        add(school); add(_adj_phrase(s, "family"))
        if s["single_level"]: add("a single level while the kids are small")
        add(childcare)
        if s["pool"]: add("a pool")
        add(park)
    elif frame == "land_lifestyle_family":
        if s["big_land"]: add(f"the {s['land']}m² block to grow into")
        add(_adj_phrase(s, "family"))
        # ⚠ Plain noun. "a pool for the family" is brochure voice — the persona
        # is already stated, so the qualifier only adds warmth we have not earned
        # on a page built on measured evidence.
        if s["pool"]: add("a pool")
        add(school or park)
        if s["single_level"]: add("single-level family living")
    elif frame == "beachside_lifestyle":
        add(beach)
        if s["pool"]: add("a pool")
        add(cafe)
        add(finish("a high-end, holiday-ready finish", "a fully renovated, holiday-ready home"))
        add(_adj_phrase(s, "stroll"))
    elif frame == "turnkey_downsizer":
        if s["single_level"]: add("a single level, no stairs to manage")
        add(_adj_phrase(s, "stroll"))   # a reserve/park at the door beats a café for a stroll-minded downsizer
        add(finish("a home already done to a high standard", "a fully renovated home"))
        add(cafe); add(shops)
        # pool deliberately omitted — upkeep, not a draw, for a downsizer
    elif frame == "renovator_valueadd":
        if s["land"]: add(f"a {s['land']}m² block to work with")
        add(_adj_phrase(s, "valueadd"))
        add(f"a tightly-held {s['suburb']} street")
        # finish deliberately omitted — they're here to add it
    elif frame == "prestige_privacy":
        if s["big_land"]: add("the land and separation from the neighbours")
        add(_adj_phrase(s, "outlook"))
        add(finish("a finish to match the address", "a fully renovated home"))
        if s["floor"]: add(f"{s['floor']}m² of living")
    elif frame == "scarcity_play":
        add(_adj_phrase(s, "valueadd"))
        if s["pool"]: add("the pool")
        if s["big_land"]: add(f"the {s['land']}m² block")
        add("a combination the market almost never offers")

    if not out:  # fallback for any home with thin signals
        if s["pool"]: add("a pool")
        if s["single_level"]: add("single-level living")
        add(_adj_phrase(s, "family")); add(cafe)
    return out[:3]


def card_08(b, c):
    k = c["card_08_buyer"]
    portrait = _buyer_portrait(b)
    if not portrait:
        return None
    parts = [f"*{k['answer']}*", "", f"**{portrait}**"]
    # why THIS home fits them — matched to what this persona actually needs.
    frame = (b.get("buyer") or {}).get("primary_frame")
    fit = _persona_fit(frame, _home_signals(b))
    if fit:
        parts += ["", k["fit_template"].format(drivers=_join_plain(fit))]
    parts += ["", k["reframe"], "", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def _anchor(low, high, point=None):
    """A rounded central 'likely position' figure (nearest $50k), spelled in
    millions — a deliberately approximate anchor. Uses the engine's point
    estimate when we have one, else the midpoint of the range."""
    base = point if point else (low + high) / 2
    r = round(base / 50000) * 50000
    m = f"{r / 1_000_000:.2f}".rstrip("0").rstrip(".")
    return f"${m} million"


def card_09(b, c):
    k = c["card_09_valuation"]
    val = b.get("valuation")
    if not val or not val.get("low") or not val.get("high"):
        return None
    ctx = {"val_low": money(val["low"]), "val_high": money(val["high"]),
           "n_comps": val.get("n_comps"),
           "anchor": _anchor(val["low"], val["high"], val.get("point"))}
    parts = [
        f"*{k['answer']}*", "",
        k["likely_intro"],
        f"# {k['likely_value'].format(**ctx)}",
        "",
        k["range_intro"],
        f"**{k['range_value'].format(**ctx)}**",
        "",
        k["range_note"],
    ]
    # Honest tier caveat — engine ranges read clean; exterior-evidence / thin
    # tiers carry their confidence note so the reader knows we couldn't see inside.
    if val.get("method") and val["method"] != "engine":
        caveat = val.get("confidence_reason") or val.get("confidence")
        if caveat:
            parts += ["", f"*{caveat}*"]
    basis = [ln.format(**ctx) for ln in k["basis_lines"]
             if all(ctx.get(t) is not None for t in _tokens(ln))]
    if basis:
        parts += ["", k["basis_intro"], _bullets(basis, mark="✓")]
    parts += ["", k["closing"], "", f"→ *{k['opens']}*"]
    return "\n".join(parts)


def card_10(b, c):
    k = c["card_10_strategy"]
    pos = b.get("positioning") or {}
    if not pos.get("frame_line"):
        return None
    parts = [f"*{k['answer']}*", "", f"**{pos['frame_line']}**"]
    if pos.get("lead_line"):
        parts += ["", pos["lead_line"]]
    avoid = [(a.get("noun") if isinstance(a, dict) else a) for a in (pos.get("avoid") or [])]
    if avoid:
        parts += ["", k["avoid_intro"], _bullets(avoid, mark="✗")]
    parts += ["", f"**[ {k['cta']} ]**"]
    return "\n".join(parts)


CARDS = [
    ("01 — Recognition", card_01),
    ("02 — The Curiosity Hook", card_02),
    ("03 — The Rarity Reveal", card_03),
    ("04 — The Explanation", card_04),
    ("05 — The Competition Reveal", card_05),
    ("06 — The Comparable Surprise", card_06),
    ("07 — The Value Drivers", card_07),
    ("08 — The Buyer Reveal", card_08),
    ("09 — Your Home's Market Position", card_09),
    ("10 — The Strategic Future", card_10),
]


def _tokens(s):
    import re
    return re.findall(r"\{(\w+)\}", s)


def assemble(slug):
    bundle_path = BUNDLE_DIR / f"{slug}.json"
    if not bundle_path.exists():
        raise SystemExit(f"no bundle for {slug} — run fact_bundle.py first")
    b = json.loads(bundle_path.read_text())
    c = load_copy()
    disc = detect_discovery(b)
    b["_discovery"] = disc   # cards (e.g. Card 03) read the lead angle
    b["_insights"] = _select_insights(b, c)   # small research-backed delights

    out = []
    out.append(f"# {b['address_short']}, {b['suburb_display']}")
    out.append(f"*Discovery Experience — 10 reveals · lead story: **{disc['angle']}***  ")
    out.append(f"<sub>{disc['reason']}</sub>\n")
    out.append("---\n")

    omitted = []
    for title, fn in CARDS:
        md = fn(b, c)
        if md is None:
            omitted.append(title)
            continue
        out.append(f"### CARD {title}\n")
        out.append(md)
        out.append("\n---\n")

    # build notes (not part of the experience — for our review)
    out.append("<details><summary>build notes</summary>\n")
    out.append(f"- discovery scores: `{disc['scores']}`")
    if omitted:
        out.append(f"- **cards omitted (no honest data):** {', '.join(omitted)}")
    if b.get("gaps"):
        out.append(f"- data gaps: {', '.join(b['gaps'])}")
    out.append("\n</details>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    md = assemble(args.slug)
    out = Path(args.out) if args.out else (OUT_DIR / f"{args.slug}.md")
    out.write_text(md)
    if args.print:
        print(md)
    print(f"→ {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
