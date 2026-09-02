#!/usr/bin/env python3
"""
Stage 2 — Topic Ranking & Selection (deterministic; no LLM, fully auditable).

Collapses the raw headlines (Stage 1) into candidate TOPICS, maps them onto our standing
evergreen dossiers where they fit, scores every candidate against demand + reach + novelty +
answerability + suburb-relevance, and emits this cycle's ranked slate. The slate is:
    standing topics (always kept current)  +  top-N promoted candidates.

Score (weights in WEIGHTS): reach + novelty + audience_demand + editorial_answerability
+ suburb_relevance  −  staleness_penalty.

Output artifact: data/<cycle>/topic_slate.json
Zero-output assertion (Rule 7b): an empty slate RAISES — standing topics guarantee it is
never legitimately empty, so empty means Stage 1 fed nothing or the scorer is misconfigured.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import mce_common as mc

WEIGHTS = {
    "reach": 1.0,          # tier coverage (GC>Bris>national) + loudness + outlets
    "novelty": 1.2,        # new theme vs an existing dossier
    "demand": 1.6,         # matches rising audience search-intent
    "answerability": 1.0,  # can we answer with DATA under Rule 5?
    "suburb": 1.3,         # plausibly touches the core three
}
TIER_WEIGHT = {"gold_coast": 3.0, "queensland": 2.0, "national": 1.0}
DEFAULT_N_PROMOTED = 4

# theme keyword -> standing dossier slug. First match wins.
THEME_TO_SLUG = [
    (r"negative gearing|capital gains|\bcgt\b|tax reform", "cgt-negative-gearing-2026"),
    (r"\brate|\brba\b|cash rate|interest|inflation|borrow", "interest-rates"),
    (r"migrat|interstate|overseas|population", "migration"),
    (r"supply|approvals|construction|listings|stock|building", "supply-and-approvals"),
    (r"afford|deposit|serviceab|price.to.income", "affordability"),
    (r"sentiment|confidence|crash|bubble|fear|expectation", "sentiment"),
    (r"indicator|wage|spending|clearance|days on market", "leading-indicators"),
    (r"turn|recovery|boom|growth|price rise|price fall|market", "national-market-turn-2026"),
]

# Topics we do NOT answer (agent selection, non-property) — downweight answerability.
NON_ANSWERABLE = re.compile(r"best (real estate )?agent|commission|which agent|agent review",
                            re.I)
# Pure advice framing we CAN answer, but only by reframing to data (Rule 5).
ADVICE_FRAMING = re.compile(r"should i (sell|buy)|is now a good time|sell now or wait", re.I)


def _norm_theme(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def _slugify(theme: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")[:60] or "topic"


def _map_slug(theme: str) -> str | None:
    for pat, slug in THEME_TO_SLUG:
        if re.search(pat, theme, re.I):
            return slug
    return None


def _demand_corpus(intent: dict) -> list[tuple[str, float]]:
    """Weighted (text, weight) demand terms from the search-intent digest."""
    corpus = []
    for c in intent.get("clusters") or []:
        corpus.append((c.get("phrase", ""), float(c.get("query_count") or 0)))
    for q in intent.get("top_questions") or []:
        corpus.append((q.get("q", ""), float(q.get("freq") or 0)))
    for i in intent.get("importance_top") or []:
        corpus.append((i.get("q", ""), float(i.get("score") or 0)))
    for ftype, fv in (intent.get("fears") or {}).items():
        corpus.append((ftype, float(fv.get("count") or 0)))
        for s in fv.get("top") or []:
            corpus.append((s, float(fv.get("count") or 0) / 3.0))
    for t in intent.get("trends") or []:
        # rising trends weight more
        corpus.append((t.get("kw", ""), max(0.0, float(t.get("direction") or 0)) * 2))
    return [(txt.lower(), w) for txt, w in corpus if txt]


def _demand_score(theme: str, headlines: list, corpus: list[tuple[str, float]]) -> float:
    """How much live audience search demand this theme matches (0..1 normalized later)."""
    terms = set(re.findall(r"[a-z]{4,}", theme.lower()))
    for h in headlines:
        terms |= set(re.findall(r"[a-z]{4,}", (h.get("gist", "") + " " +
                                               h.get("headline", "")).lower()))
    terms -= {"that", "this", "with", "from", "have", "will", "into", "your", "market",
              "property", "house", "housing", "australia", "australian"}
    score = 0.0
    for txt, w in corpus:
        if any(t in txt for t in terms):
            score += w
    return score


def _suburb_relevance(theme: str, headlines: list, intent: dict) -> float:
    s = 0.0
    blob = (theme + " " + " ".join(h.get("headline", "") + h.get("gist", "")
                                   for h in headlines)).lower()
    for name in ("gold coast", "robina", "varsity lakes", "burleigh", "queensland", "brisbane"):
        if name in blob:
            s += 2.0 if name != "queensland" and name != "brisbane" else 1.0
    # any GC-tier headline in the group counts
    if any(h.get("tier") == "gold_coast" for h in headlines):
        s += 2.0
    # per-suburb search interest for the theme
    for sub, sd in (intent.get("suburbs") or {}).items():
        s += 0.001 * float(sd.get("total_queries") or 0)
    return s


def _answerability(theme: str, headlines: list) -> float:
    blob = theme + " " + " ".join(h.get("headline", "") for h in headlines)
    if NON_ANSWERABLE.search(blob):
        return 0.2
    if ADVICE_FRAMING.search(blob):
        return 0.6   # answerable only by reframing to data/context
    return 1.0


def build_slate(cycle: str, *, n_promoted: int = DEFAULT_N_PROMOTED) -> dict:
    raw = mc.load_artifact(cycle, "headlines_raw.json")
    pack = mc.load_artifact(cycle, "internal_pack.json")
    if not raw:
        raise RuntimeError("Stage 2: headlines_raw.json missing — run Stage 1 first")
    intent = (pack or {}).get("search_intent") or {}
    headlines = raw.get("headlines") or []

    # standing topics from topics.json (load-bearing evergreen dossiers)
    with open(mc.CONFIG) as fh:
        cfg = json.load(fh)
    standing = {t["slug"]: t for t in cfg.get("active", [])}

    # group headlines into candidate topics by mapped-slug (else by theme)
    groups: dict[str, dict] = {}
    for h in headlines:
        theme = _norm_theme(h.get("theme"))
        slug = _map_slug(theme) or _slugify(theme)
        g = groups.setdefault(slug, {"slug": slug, "themes": set(), "headlines": [],
                                     "loudness": 0.0, "tiers": set(), "outlets": set()})
        g["themes"].add(theme)
        g["headlines"].append(h)
        g["loudness"] += float(h.get("loudness") or 1)
        g["tiers"].add(h.get("tier"))
        g["outlets"].add(h.get("outlet"))

    corpus = _demand_corpus(intent)
    existing_dossiers = {os.path.splitext(f)[0] for f in os.listdir(mc.TOPICS_DIR)
                         if f.endswith(".md")}

    cands = []
    for slug, g in groups.items():
        theme_str = " / ".join(sorted(g["themes"]))
        reach = (sum(TIER_WEIGHT.get(t, 1.0) for t in g["tiers"])
                 + g["loudness"] + 0.5 * len(g["outlets"]))
        novelty = 0.5 if slug in existing_dossiers else 2.5   # new theme scores higher
        demand = _demand_score(theme_str, g["headlines"], corpus)
        answer = _answerability(theme_str, g["headlines"])
        suburb = _suburb_relevance(theme_str, g["headlines"], intent)
        cands.append({
            "slug": slug, "theme": theme_str,
            "is_standing": slug in standing,
            "has_dossier": slug in existing_dossiers,
            "n_headlines": len(g["headlines"]),
            "tiers": sorted(t for t in g["tiers"] if t),
            "outlets": sorted(o for o in g["outlets"] if o),
            "raw": {"reach": round(reach, 2), "novelty": novelty,
                    "demand": round(demand, 2), "answerability": answer,
                    "suburb": round(suburb, 2)},
            "driving_headlines": [{"headline": h.get("headline"), "url": h.get("url"),
                                   "outlet": h.get("outlet"), "tier": h.get("tier")}
                                  for h in g["headlines"][:4]],
        })

    # normalize each raw dimension to 0..1 across candidates, then weight
    def _norm(key):
        vals = [c["raw"][key] for c in cands] or [0]
        hi = max(vals) or 1.0
        return {c["slug"]: c["raw"][key] / hi for c in cands}
    norms = {k: _norm(k) for k in ("reach", "novelty", "demand", "answerability", "suburb")}
    for c in cands:
        c["score"] = round(sum(WEIGHTS[k] * norms[k][c["slug"]]
                               for k in WEIGHTS), 3)
    cands.sort(key=lambda c: c["score"], reverse=True)

    # selection: every standing topic (kept current) + top-N promoted non-standing
    promoted = [c for c in cands if not c["is_standing"]][:n_promoted]
    promoted_slugs = {c["slug"] for c in promoted}
    slate = []
    for slug, t in standing.items():
        match = next((c for c in cands if c["slug"] == slug), None)
        slate.append({"slug": slug, "title": t.get("title"), "focus": t.get("focus"),
                      "kind": "standing", "has_dossier": slug in existing_dossiers,
                      "score": match["score"] if match else None,
                      "in_headlines": bool(match)})
    for c in promoted:
        slate.append({"slug": c["slug"], "title": c["theme"].title(),
                      "focus": (f"Emerging topic surfaced from the {'/'.join(c['tiers'])} "
                                f"headline scan ({c['n_headlines']} stories). Research the "
                                f"underlying drivers behind: {c['theme']}. Test the premise; "
                                f"ground in Queensland/Gold Coast data where possible."),
                      "kind": "promoted", "has_dossier": c["has_dossier"],
                      "score": c["score"], "in_headlines": True})

    out = {"cycle": cycle, "n_candidates": len(cands), "n_promoted": len(promoted),
           "n_standing": len(standing), "weights": WEIGHTS,
           "slate": slate, "candidates_ranked": cands}
    mc.save_artifact(cycle, "topic_slate.json", out)

    if not slate:
        raise RuntimeError("Stage 2: empty slate — Stage 1 fed no headlines or scorer misconfigured")
    print(f"    ✓ Stage 2: {len(cands)} candidates -> slate of {len(slate)} "
          f"({len(standing)} standing + {len(promoted)} promoted: "
          f"{', '.join(c['slug'] for c in promoted) or 'none'})", file=sys.stderr)

    # persist to DB for auditability over time
    try:
        mc.get_sm()["mce_topic_slate"].update_one(
            {"cycle": cycle}, {"$set": out}, upsert=True)
    except Exception as e:
        print(f"    ! Stage 2: slate DB write failed: {e}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 2 — topic ranking")
    ap.add_argument("--cycle", default=mc.cycle_id())
    ap.add_argument("--n-promoted", type=int, default=DEFAULT_N_PROMOTED)
    a = ap.parse_args()
    out = build_slate(a.cycle, n_promoted=a.n_promoted)
    print(json.dumps([{"slug": s["slug"], "kind": s["kind"], "score": s["score"]}
                      for s in out["slate"]], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
