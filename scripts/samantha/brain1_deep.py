#!/usr/bin/env python3
"""
Brain 1 — COMPLETENESS-FIRST deep query tool.

Design principle (Will, 2026-07-18): surface ALL relevant data from ALL sources, even a
single mention (n=1). Never rank-out or crowd-out a smaller corpus by size — corpus size is
an accident of what footage exists, not a signal of relevance. The user applies judgement;
the system guarantees recall. See memory: brain-retrieval-completeness-principle.

Pipeline:
  1. DECOMPOSE the question into ~8 retrieval facets (Haiku on Max) — broadens vocabulary so
     recall isn't hostage to one phrasing.
  2. PER-SOURCE CANDIDATE GATHER — for EACH library independently: lexical candidates over all
     facets (reuses brain1_query.score_units) + 1-hop graph neighbours. Each source competes
     only against itself -> no crowd-out. Generous caps, not a tight top-N.
  3. RELEVANCE JUDGE (Haiku, batched, stateless) — keep every candidate judged relevant to the
     ORIGINAL question. This is a THRESHOLD, not a fixed count. Biased to INCLUDE (rarity is
     valuable); fail-OPEN on any error (keep the batch) so we never silently drop.
  4. SYNTHESISE — if the relevant set fits one context, single Opus-on-Max call (best: it can
     bridge any unit to any other). On overflow: MAP-REDUCE with citation-preserving extraction
     (Haiku map keeps ids+quotes) -> Opus reduce -> tree-reduce if the findings still overflow.
  5. VERIFY — every unit id cited is checked against the shortlist (invented ids = hallucination).
  6. COVERAGE — logs relevant-unit counts PER SOURCE so crowd-out is visible if it recurs.

100% Anthropic on Max — no embeddings, no vector DB, no paid API (Will directive).

Usage:
  env -u CLAUDECODE python3 scripts/samantha/brain1_deep.py "your question" \
      [--library "Sell It"] [--mode general|insight] [--out answer.md] [--dry] [--no-verify] \
      [--cand-per-facet 40] [--judge-batch 18] [--token-budget 500000]
"""
import os, re, sys, json, argparse
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain1_query as bq
import openrouter_client as orc

UID_RE = re.compile(r"\bu\d{4}\b")
HAIKU = orc.HAIKU  # decompose / judge / map — Haiku via OpenRouter
JUDGE_WORKERS = 6      # bounded concurrency for I/O-bound claude calls (judge + map)
MAX_SINGLE_UNITS = 150 # fidelity ceiling: above this, single-context synthesis stops citing real
                       # unit ids and confabulates (empirically ~1000 units -> 0 real citations).
                       # Force map-reduce past this REGARDLESS of token budget — fidelity breaks
                       # before the token window does.


def claude(prompt, model, timeout=900):
    return orc.call(prompt, model, timeout=timeout, max_tokens=16000)


def tok(s):
    return len(s) // 4


def decompose(question, n=8):
    p = (f"Break this research question into {n} DISTINCT search facets for retrieving passages "
         f"from a real-estate coaching corpus. Each facet = a short keyword-rich phrase covering a "
         f"different angle (methods, obstacles, objections, psychology, principles, etc.). Vary the "
         f"VOCABULARY deliberately (synonyms, related jargon) so different phrasings are covered. "
         f"Return ONLY a JSON array of {n} strings.\n\nQUESTION: {question}")
    try:
        out = claude(p, HAIKU, timeout=120)
        facets = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        facets = [f.strip() for f in facets if isinstance(f, str) and f.strip()]
        return facets or [question]
    except Exception as e:
        sys.stderr.write(f"[decompose] fell back to raw question ({e})\n")
        return [question]


def compact(u, nq=2, na=3, nc=8):
    return {"id": u["id"],
            "src": f"{u['src']['lib']} / {u['src'].get('course','')} / {u['src'].get('module','')}",
            "concepts": u["concepts"][:nc], "asks": u["asks"][:na], "quotes": u["quotes"][:nq]}


def gather_candidates(pkg, facets, libs, cand_per_facet):
    """Per-library candidate pool: lexical union over facets + 1-hop graph neighbours in-library.
    Returns {lib: [units]}. Casts a WIDE net (this is the recall layer; the judge does precision)."""
    by_id = {u["id"]: u for u in pkg["units"]}
    out = {}
    for lib in libs:
        scan = {**pkg, "units": [u for u in pkg["units"] if u["src"].get("lib") == lib]}
        picked, ids = [], set()
        for f in facets:
            for _, u in bq.score_units(scan, f)[:cand_per_facet]:
                if u["id"] not in ids:
                    ids.add(u["id"]); picked.append(u)
        # graph neighbours (vocabulary-mismatched but concept-linked), kept in-library
        neigh_ids, _ = bq.expand(pkg, picked, set(ids))
        for i in neigh_ids:
            u = by_id.get(i)
            if u and u["src"].get("lib") == lib and i not in ids:
                ids.add(i); picked.append(u)
        out[lib] = picked
    return out


def _judge_chunk(question, chunk):
    listing = "\n".join(json.dumps(compact(u)) for u in chunk)
    p = ("You are filtering real-estate coaching units for RELEVANCE to a question. KEEP a unit "
         "if it contains ANY information, method, example, principle, objection, quote or angle "
         "that could help answer the question — even a single relevant mention counts. Do NOT "
         "filter by how common or popular an idea is; a rare or one-off relevant point is "
         "valuable and MUST be kept. Only DROP units with nothing relevant at all.\n\n"
         f"QUESTION: {question}\n\nUNITS (one JSON per line):\n{listing}\n\n"
         "Return ONLY a JSON array of the unit ids to KEEP.")
    try:
        out = claude(p, HAIKU, timeout=120)
        ids = set(json.loads(re.search(r"\[.*\]", out, re.S).group(0)))
        return [u for u in chunk if u["id"] in ids]
    except Exception as e:
        sys.stderr.write(f"[judge] FAIL-OPEN (kept all {len(chunk)}): {e}\n")
        return list(chunk)  # fail-open: never silently drop relevant data


def judge_relevant(question, units, batch):
    """Haiku relevance filter. Keep any unit with ANY info that could help answer the question —
    rarity is valuable, bias to INCLUDE. Batched, STATELESS (order-independent), run concurrently.
    Fail-OPEN on any error."""
    chunks = [units[i:i + batch] for i in range(0, len(units), batch)]
    if not chunks:
        return []
    with ThreadPoolExecutor(max_workers=JUDGE_WORKERS) as ex:
        results = list(ex.map(lambda c: _judge_chunk(question, c), chunks))
    return [u for r in results for u in r]


PROMPTS = {
    "general": ("Answer the QUESTION with a DEEP, well-structured brief. Synthesise ACROSS units into "
                "method families; surface the difficulties/obstacles; then an INSIGHT LAYER extracting "
                "core principles and extending them into new/sharpened methods (flag which are "
                "un-copyable given Fields' data platform). "),
    "insight": ("Do NOT just summarise. Bridge DISTANT concepts across different units to generate NEW, "
                "non-obvious client-acquisition plays for Fields (a Gold Coast data-first agency). Name "
                "each play, cite the unit ids it bridges, state the mechanism. "),
}
HEADER = ("You are Brain 1 — an intelligence layer over a real-estate coaching corpus (Tom Panos/"
          "RealEstate Gym, Ryan Serhant/Sell It, Mat Steinwede & Josh Tesolin/Agent School). ")
RULES = ("RULES: cite unit ids (e.g. u0452) for every substantive claim; include DIRECT VERBATIM "
         "QUOTES throughout; give EQUAL consideration to material from every source regardless of how "
         "many units it has — a point made once is as admissible as one made often; if the corpus does "
         "not cover something, say so plainly — do NOT invent. Structure with clear headings.\n\n")


def synth_prompt(question, mode, payload_json, is_findings=False):
    src = "PRE-EXTRACTED FINDINGS (already citation-tagged)" if is_findings else "CORPUS SHORTLIST (JSON)"
    return (HEADER + PROMPTS[mode] + RULES + f"=== QUESTION ===\n{question}\n\n=== {src} ===\n" + payload_json)


def map_extract(question, units):
    """MAP step: Haiku pulls citation-preserving findings from a shard (keeps ids + verbatim quotes)."""
    listing = "\n".join(json.dumps(compact(u, nq=3, na=4)) for u in units)
    p = ("Extract every point RELEVANT to the question from these coaching units. For each, write a "
         "one-line finding that PRESERVES the unit id and at least one VERBATIM quote. Keep rare/one-off "
         "points. Do not synthesise or drop anything relevant.\n\n"
         f"QUESTION: {question}\n\nUNITS:\n{listing}\n\nReturn a plain bulleted list of findings.")
    return claude(p, HAIKU, timeout=300)


def synthesise(question, mode, relevant, budget):
    ctx = {"units": [compact(u, nq=4, na=5, nc=10) for u in relevant]}
    payload = json.dumps(ctx, ensure_ascii=False)
    # Single-context ONLY when small enough to cite faithfully AND under token budget.
    if len(relevant) <= MAX_SINGLE_UNITS and tok(payload) <= budget:
        sys.stderr.write(f"[synth] single-context ({tok(payload):,} tok, {len(relevant)} units)\n")
        return claude(synth_prompt(question, mode, payload), bq.MODEL, timeout=900), {u["id"] for u in relevant}
    # OVERFLOW (unit-count fidelity limit OR token budget) -> map-reduce, citation-preserving extraction
    shard_n = 60
    shards = [relevant[i:i + shard_n] for i in range(0, len(relevant), shard_n)]
    sys.stderr.write(f"[synth] overflow ({tok(payload):,} tok) -> map-reduce over {len(shards)} shards\n")
    with ThreadPoolExecutor(max_workers=JUDGE_WORKERS) as ex:
        findings = list(ex.map(lambda s: map_extract(question, s), shards))
    blob = "\n".join(findings)
    # tree-reduce if the concatenated findings still overflow
    while tok(blob) > budget:
        groups = [findings[i:i + 4] for i in range(0, len(findings), 4)]
        sys.stderr.write(f"[synth] findings still {tok(blob):,} tok -> tree-reduce {len(groups)} groups\n")
        findings = [claude("Merge these findings, preserving every unit id and verbatim quote, dropping "
                           "nothing relevant:\n\n" + "\n".join(g), HAIKU, timeout=300) for g in groups]
        blob = "\n".join(findings)
    return claude(synth_prompt(question, mode, blob, is_findings=True), bq.MODEL, timeout=900), {u["id"] for u in relevant}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--library", help="restrict to ONE library (default: all, per-source)")
    ap.add_argument("--mode", choices=list(PROMPTS), default="general")
    ap.add_argument("--facets", type=int, default=8)
    ap.add_argument("--cand-per-facet", type=int, default=40)
    ap.add_argument("--judge-batch", type=int, default=18)
    ap.add_argument("--token-budget", type=int, default=500000)
    ap.add_argument("--out")
    ap.add_argument("--dry", action="store_true", help="stop after the relevance judge; print coverage")
    ap.add_argument("--no-judge", action="store_true", help="skip Haiku judge (keep all candidates)")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    pkg = bq.load()
    all_libs = sorted({u["src"].get("lib") for u in pkg["units"]})
    libs = [args.library] if args.library else all_libs
    by_id = {u["id"]: u for u in pkg["units"]}

    facets = decompose(args.question, args.facets)
    sys.stderr.write(f"[facets] {len(facets)}:\n" + "".join(f"   - {f}\n" for f in facets))

    cand = gather_candidates(pkg, facets, libs, args.cand_per_facet)
    sys.stderr.write("[candidates] per source: " +
                     " | ".join(f"{l}={len(cand[l])}" for l in libs) + "\n")

    # relevance judge per source (keeps sources independent end-to-end)
    relevant, coverage = [], {}
    for l in libs:
        rel = cand[l] if args.no_judge else judge_relevant(args.question, cand[l], args.judge_batch)
        coverage[l] = (len(cand[l]), len(rel))
        relevant.extend(rel)
    sys.stderr.write("[COVERAGE] relevant / candidates per source:\n" +
                     "".join(f"   {l:15s}: {r:3d} relevant / {c:3d} judged\n"
                             for l, (c, r) in coverage.items()) +
                     f"   {'TOTAL':15s}: {sum(r for _, r in coverage.values())} relevant units carried\n")

    if args.dry:
        print(json.dumps({"facets": facets,
                          "coverage": {l: {"candidates": c, "relevant": r} for l, (c, r) in coverage.items()},
                          "total_relevant": len(relevant)}, indent=2))
        return

    sys.stderr.write("[opus] deep synthesis…\n")
    answer, shortlist_ids = synthesise(args.question, args.mode, relevant, args.token_budget)
    print(answer)

    if not args.no_verify:
        # (1) id-level: invented / out-of-shortlist ids
        cited = sorted(set(UID_RE.findall(answer)))
        in_short = [c for c in cited if c in shortlist_ids]
        invented = [c for c in cited if c not in by_id]
        oos = [c for c in cited if c in by_id and c not in shortlist_ids]
        sys.stderr.write(f"\n[verify] {len(cited)} cited | {len(in_short)} in shortlist ✓ | "
                         f"{len(oos)} exist-not-in-shortlist | {len(invented)} INVENTED\n")
        if invented:
            sys.stderr.write(f"[verify] ⚠ INVENTED ids: {invented}\n")
        # (2) quote-level: misattribution (real quote -> wrong unit) + fabrication
        try:
            import brain1_verify as bv
            total, ok, misattr, notfound = bv.verify_text(answer)
            if total:
                sys.stderr.write(f"[quote-verify] {total} quotes | {ok} verified | {len(misattr)} "
                                 f"MISATTRIBUTED | {len(notfound)} NOT_FOUND | {100*ok/total:.1f}% fidelity\n")
                for r in misattr:
                    sys.stderr.write(f"   ✗ MISATTR cited {','.join(r['cited'])} -> actually "
                                     f"{r['actual']} (cov {r['cov']}): \"{r['quote'][:60]}\"\n")
                for r in notfound:
                    sys.stderr.write(f"   ✗ FABRICATED (best {r['actual']} {r['cov']}): "
                                     f"\"{r['quote'][:60]}\"\n")
                if misattr or notfound:
                    sys.stderr.write("[quote-verify] ⚠ NOT publication-ready — fix flagged quotes before public use.\n")
        except Exception as e:
            sys.stderr.write(f"[quote-verify] skipped ({e})\n")

    if args.out:
        open(args.out, "w", encoding="utf-8").write(answer)
        sys.stderr.write(f"[saved] {args.out}\n")


if __name__ == "__main__":
    main()
