#!/usr/bin/env python3
"""
Brain 1 — Phase 2: deterministic concept-graph package builder.

Reads the Haiku annotations (annotations.jsonl, one JSON object per module unit)
and produces a compact, self-contained `package.json` that an Opus agent can read
whole to do graph-walk retrieval + insight generation. NO embeddings, NO vector DB
(Will directive: 100% Anthropic on Max).

Outputs (to --outdir, default the annotations' directory):
  package.json     — units + typed_edges + cooccur_edges + indexes (the feedable layer)
  graph_stats.json — human-readable summary (counts, top concepts, channel tally)

Design notes:
  - Concept/entity normalization is intentionally light (lowercase, ws-collapse,
    trailing-punct strip) — deterministic, no model calls.
  - Co-occurrence edges are pruned to weight >= MIN_COOCCUR to kill singleton noise;
    typed relationship edges are always kept (they are the high-signal ones).
  - answers_questions -> question index is the recall fix for narrative content that
    keyword search misses (doc->question generation).
"""
import json
import re
import sys
import argparse
from collections import defaultdict, Counter
from itertools import combinations
from pathlib import Path

MIN_COOCCUR = 2          # drop co-occurrence edges seen in only one unit
TOP_CONCEPTS_IN_STATS = 60

_ws = re.compile(r"\s+")
_trail = re.compile(r"^[\s\"'.,;:!?()\-]+|[\s\"'.,;:!?()\-]+$")


def norm(s):
    if not isinstance(s, str):
        return ""
    s = _ws.sub(" ", s).strip().lower()
    s = _trail.sub("", s)
    return s


def load(path):
    units = []
    bad = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                units.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return units, bad


def load_canonical(outdir):
    """Optional concept->canonical map from brain1_normalize.py --consolidate.

    When present, raw concept strings are collapsed to their canonical form BEFORE the
    graph is built, so typed + co-occurrence edge endpoints actually connect. Returns a
    dict keyed by normalized raw concept (norm()) -> canonical label, or {} if absent.
    """
    p = Path(outdir) / "concept_canonical.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {norm(k): norm(v) for k, v in raw.items()}


def build(units, canon=None):
    canon = canon or {}
    cn = lambda c: canon.get(c, c)  # collapse a normalized concept to its canonical form
    out_units = []
    concept_index = defaultdict(list)      # norm concept -> [unit_id]
    question_index = defaultdict(list)     # norm question -> [unit_id]
    channel_index = defaultdict(list)      # channel -> [{unit, emphasis}]
    typed = defaultdict(lambda: {"units": [], "count": 0})   # (from,type,to) -> agg
    cooccur = Counter()                     # frozenset({a,b}) -> weight

    for u in units:
        uid = u.get("unit_id") or f"u{len(out_units):04d}"
        prov = u.get("provenance", {}) or {}
        src = {
            "lib": prov.get("library", ""),
            "course": prov.get("course", ""),
            "module": prov.get("module", ""),
        }
        concepts = [cn(c) for c in (norm(x) for x in u.get("concepts", []) or []) if c]
        topics = [t for t in (norm(x) for x in u.get("topic_tags", []) or []) if t]
        asks = [q.strip() for q in (u.get("answers_questions", []) or []) if isinstance(q, str) and q.strip()]
        quotes = [q.strip() for q in (u.get("key_quotes", []) or []) if isinstance(q, str) and q.strip()]

        out_units.append({
            "id": uid,
            "src": src,
            "topics": topics,
            "channels": u.get("channels", []) or [],
            "concepts": concepts,
            "asks": asks,
            "quotes": quotes,
        })

        for c in set(concepts):
            concept_index[c].append(uid)
        for q in asks:
            question_index[norm(q)].append(uid)
        for ch in u.get("channels", []) or []:
            if isinstance(ch, dict) and ch.get("channel"):
                channel_index[norm(ch["channel"])].append(
                    {"unit": uid, "emphasis": ch.get("emphasis", "")}
                )

        # typed edges from relationships[]
        for r in u.get("relationships", []) or []:
            if not isinstance(r, dict):
                continue
            f = cn(norm(r.get("from", "")))
            t = cn(norm(r.get("to", "")))
            ty = (r.get("type") or "").strip().lower()
            if not f or not t or not ty:
                continue
            key = (f, ty, t)
            typed[key]["count"] += 1
            if uid not in typed[key]["units"]:
                typed[key]["units"].append(uid)

        # co-occurrence within the unit (concept pairs)
        for a, b in combinations(sorted(set(concepts)), 2):
            cooccur[frozenset((a, b))] += 1

    typed_edges = [
        {"from": k[0], "type": k[1], "to": k[2], "count": v["count"], "units": v["units"]}
        for k, v in sorted(typed.items(), key=lambda kv: -kv[1]["count"])
    ]
    cooccur_edges = [
        {"a": sorted(pair)[0], "b": sorted(pair)[1], "w": w}
        for pair, w in cooccur.items() if w >= MIN_COOCCUR
    ]
    cooccur_edges.sort(key=lambda e: -e["w"])

    package = {
        "meta": {
            "brain": 1,
            "source": "coaching-corpus annotations (Haiku on Max)",
            "n_units": len(out_units),
            "min_cooccur": MIN_COOCCUR,
        },
        "units": out_units,
        "typed_edges": typed_edges,
        "cooccur_edges": cooccur_edges,
        "concept_index": {k: v for k, v in concept_index.items()},
        "question_index": {k: v for k, v in question_index.items()},
        "channel_index": {k: v for k, v in channel_index.items()},
    }
    return package


def stats(package):
    ci = package["concept_index"]
    top = sorted(ci.items(), key=lambda kv: -len(kv[1]))[:TOP_CONCEPTS_IN_STATS]
    channel_tally = Counter()
    avoided = []
    for ch, refs in package["channel_index"].items():
        for r in refs:
            channel_tally[ch] += 1
            if (r.get("emphasis") or "").upper() == "AVOIDED":
                avoided.append({"channel": ch, "unit": r["unit"]})
    libs = Counter(u["src"]["lib"] for u in package["units"])
    return {
        "n_units": package["meta"]["n_units"],
        "n_concepts": len(ci),
        "n_typed_edges": len(package["typed_edges"]),
        "n_cooccur_edges": len(package["cooccur_edges"]),
        "n_questions": len(package["question_index"]),
        "n_channels": len(package["channel_index"]),
        "by_library": dict(libs),
        "top_concepts": [{"concept": c, "units": len(u)} for c, u in top],
        "top_channels": [{"channel": c, "mentions": n} for c, n in channel_tally.most_common(30)],
        "avoided_channels": avoided,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="/home/fields/brain1_build/annotations.jsonl")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    inp = Path(args.inp)
    outdir = Path(args.outdir) if args.outdir else inp.parent

    units, bad = load(inp)
    print(f"Loaded {len(units)} annotation records ({bad} unparseable lines skipped)")
    canon = load_canonical(outdir)
    if canon:
        print(f"Applying canonical concept map: {len(canon)} raw -> {len(set(canon.values()))} canonical")
    else:
        print("No concept_canonical.json — building on raw concepts (run brain1_normalize.py to densify edges)")
    package = build(units, canon)
    st = stats(package)

    pkg_path = outdir / "package.json"
    stats_path = outdir / "graph_stats.json"
    pkg_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    stats_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    size_mb = pkg_path.stat().st_size / 1e6
    approx_tokens = int(pkg_path.stat().st_size / 4)  # ~4 chars/token
    print(f"\nWrote {pkg_path}  ({size_mb:.1f} MB, ~{approx_tokens:,} tokens)")
    print(f"Wrote {stats_path}")
    print(f"\n  units={st['n_units']}  concepts={st['n_concepts']}  "
          f"typed_edges={st['n_typed_edges']}  cooccur_edges={st['n_cooccur_edges']}")
    print(f"  questions={st['n_questions']}  channels={st['n_channels']}  "
          f"avoided_channels={len(st['avoided_channels'])}")
    print(f"  by_library={st['by_library']}")
    if approx_tokens > 900_000:
        print("\n  ⚠ package exceeds ~900k tokens — Opus 1M window is tight; "
              "add a Haiku shortlister pass for retrieval.")


if __name__ == "__main__":
    main()
