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
import os, re, sys, json, hashlib, argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain1_query as bq
import max_client as orc
import brain_json as bj

UID_RE = re.compile(r"\b[uki]\d{4,10}\b")  # u#### coaching + k##### KB units
FACET_CACHE = os.path.expanduser("~/.cache/brain1/facets")
HAIKU = orc.HAIKU  # decompose / judge / map -> Haiku on Max (Will 2026-07-31)
JUDGE_WORKERS = 6      # bounded concurrency for I/O-bound claude calls (judge + map)
MAX_SINGLE_UNITS = 150 # fidelity ceiling: above this, single-context synthesis stops citing real
                       # unit ids and confabulates (empirically ~1000 units -> 0 real citations).
                       # Force map-reduce past this REGARDLESS of token budget — fidelity breaks
                       # before the token window does.


def claude(prompt, model, timeout=900):
    return orc.call(prompt, model, timeout=timeout, max_tokens=16000)


def tok(s):
    return len(s) // 4


def _facet_cache_path(question, n, package):
    key = hashlib.sha256(f"{package}|{n}|{question.strip()}".encode()).hexdigest()[:20]
    return os.path.join(FACET_CACHE, f"{key}.json")


def decompose(question, n=8, package="", refresh=False):
    """Decompose the question into retrieval facets.

    CACHED per (package, n, question). Haiku is non-deterministic, so an uncached re-run of the
    SAME question produced different facets -> different candidate pools -> a different answer.
    For a tool used to make business decisions that is a reproducibility failure: we could not
    re-run a query to check an answer. Caching is cheaper and more reliable than trying to make
    the model deterministic. Use --refresh-facets to deliberately re-decompose.
    """
    path = _facet_cache_path(question, n, package)
    if not refresh and os.path.exists(path):
        try:
            facets = json.load(open(path, encoding="utf-8"))["facets"]
            if facets:
                sys.stderr.write(f"[facets] reused cached decomposition ({len(facets)}) — "
                                 f"reproducible re-run. --refresh-facets to regenerate.\n")
                return facets
        except Exception:
            pass  # corrupt cache entry -> just regenerate

    p = (f"Break this research question into {n} DISTINCT search facets for retrieving passages "
         f"from a real-estate coaching corpus. Each facet = a short keyword-rich phrase covering a "
         f"different angle (methods, obstacles, objections, psychology, principles, etc.). Vary the "
         f"VOCABULARY deliberately (synonyms, related jargon) so different phrasings are covered. "
         f"Return ONLY a JSON array of {n} strings.\n\nQUESTION: {question}")
    try:
        raw = bj.parse_with_retry(
            p, lambda pr: claude(pr, HAIKU, timeout=120), want="array",
            on_retry=lambda e: sys.stderr.write(f"[decompose] unparseable, retrying once ({e})\n"))
        facets = [f.strip() for f in raw if isinstance(f, str) and f.strip()]
    except Exception as e:
        sys.stderr.write(f"[decompose] fell back to raw question ({e})\n")
        return [question]
    if not facets:
        return [question]
    try:
        os.makedirs(FACET_CACHE, exist_ok=True)
        json.dump({"question": question, "n": n, "package": package, "facets": facets},
                  open(path, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        sys.stderr.write(f"[facets] cache write failed ({e}) — continuing uncached\n")
    return facets


def compact(u, nq=2, na=3, nc=8):
    d = {"id": u["id"],
         "src": f"{u['src']['lib']} / {u['src'].get('course','')} / {u['src'].get('module','')}",
         "concepts": u["concepts"][:nc], "asks": u["asks"][:na], "quotes": u["quotes"][:nq]}
    if u.get("date"):
        d["date"] = u["date"]  # structured, recency-aware synthesis reasons over this
    if u.get("entities"):
        # who/what the unit names — lets the synthesis attribute a method to the practitioner
        # who described it instead of to a library, and answers name-anchored questions.
        d["entities"] = u["entities"][:8]
    return d


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
        # Robust parse + ONE retry before giving up. The old greedy re.search(r"\[.*\]") spanned
        # from the first "[" to the LAST "]" in the reply, so any trailing prose or second array
        # made the captured span invalid JSON -> "Extra data: line 7 column 1" -> a whole batch
        # lost its filtering. See brain_json.py.
        raw = bj.parse_with_retry(
            p, lambda pr: claude(pr, HAIKU, timeout=120), want="array",
            on_retry=lambda e: sys.stderr.write(f"[judge] unparseable, retrying once ({e})\n"))
        ids = {i for i in raw if isinstance(i, str)}
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
DEFAULT_HEADER = ("You are Brain 1 — an intelligence layer over a real-estate coaching corpus (Tom Panos/"
                  "RealEstate Gym, Ryan Serhant/Sell It, Mat Steinwede & Josh Tesolin/Agent School). ")


def header_for(pkg):
    """Generic header for non-default packages (e.g. Brain 3 ops) — the coaching-specific framing
    above is wrong when the loaded package is a different brain entirely."""
    libs = sorted({u["src"].get("lib", "") for u in pkg.get("units", [])})
    coaching_libs = {"RealEstate_Gym", "Sell It", "Agent School"}
    if any(l in coaching_libs or l.startswith("KB:") for l in libs):
        return DEFAULT_HEADER
    return (f"You are an intelligence layer over a knowledge graph. The corpus's sources are: "
            f"{', '.join(l.replace('internal:', '') for l in libs)}. ")


def rules_for(pkg):
    example_id = pkg["units"][0]["id"] if pkg.get("units") else "u0452"
    return ("RULES: cite unit ids EXACTLY as given in the shortlist's \"id\" field (e.g. "
            f"{example_id}) for every substantive claim — copy the id character-for-character, "
            "never invent or alter its prefix letter or digits; include DIRECT VERBATIM QUOTES "
            "throughout; give EQUAL consideration to material from every source regardless of how "
            "many units it has — a point made once is as admissible as one made often; if the corpus "
            "does not cover something, say so plainly — do NOT invent. Structure with clear headings.\n"
            "QUOTATION RULE — this is a hard constraint, not a style note. Quotation marks mean ONE "
            "thing: the enclosed words are copied character-for-character from a unit's \"quotes\" "
            "field. Never put quotation marks around your own wording — not around section labels, "
            "not around coined shorthand, not around a paraphrase or compression of what a unit "
            "said, not around scare-quoted terms. For your own phrasing use plain text or "
            "**bold**. If you remember the gist of a passage but not its exact words, write it as "
            "plain prose and cite the unit id — that is correct and expected. A paraphrase inside "
            "quote marks beside a unit id is a FALSE ATTRIBUTION: the reader will believe that "
            "person said those exact words. Every quoted span you write is machine-checked against "
            "the corpus after generation, and any that is not found verbatim blocks the brief from "
            "publication — so quote less and quote exactly, rather than quoting often.\n"
            "TEMPORAL RULE: some units carry a 'date' field. Do not treat retrieval score as recency — a "
            "unit can rank highly and still be OLD. When units on the same topic carry different dates, "
            "or a topic could plausibly have changed since a unit's date, state the chronology explicitly: "
            "cite the date, say what was true then, and — if a later unit shows it changed — say what is "
            "CURRENT now and flag the earlier claim as SUPERSEDED. Never present dated information as "
            "current without checking whether a more recent unit contradicts it.\n\n")


def concentration_rule(concentration):
    """When one library supplies most of the evidence, the brief MUST say so. Otherwise one
    training organisation's doctrine reads as settled industry consensus — a citation-integrity
    problem for a business whose positioning is methodology transparency."""
    lib, share = concentration or (None, 0.0)
    if not lib or share <= 0.5:
        return ""
    return ("SOURCE-CONCENTRATION RULE: {pct:.0f}% of the evidence below comes from a single "
            "source ({lib}). You MUST state this plainly near the top of the brief and note that "
            "conclusions therefore reflect that source's doctrine rather than demonstrated "
            "industry consensus. Where a claim rests only on {lib}, say so at the claim. Where "
            "another source corroborates or contradicts it, name that source explicitly.\n\n"
            ).format(pct=100 * share, lib=lib)


def synth_prompt(question, mode, payload_json, pkg, is_findings=False, concentration=None):
    src = "PRE-EXTRACTED FINDINGS (already citation-tagged)" if is_findings else "CORPUS SHORTLIST (JSON)"
    today = datetime.now().strftime("%Y-%m-%d")
    return (header_for(pkg) + PROMPTS[mode] + rules_for(pkg) + concentration_rule(concentration)
            + f"TODAY'S DATE: {today}\n\n"
            f"=== QUESTION ===\n{question}\n\n=== {src} ===\n" + payload_json)


def map_extract(question, units):
    """MAP step: Haiku pulls citation-preserving findings from a shard (keeps ids + verbatim quotes)."""
    listing = "\n".join(json.dumps(compact(u, nq=3, na=4)) for u in units)
    p = ("Extract every point RELEVANT to the question from these knowledge-graph units. For each, "
         "write a one-line finding that copies the unit's \"id\" field EXACTLY as given (character "
         "for character — never alter its prefix letter or digits), its 'date' if present, and at "
         "least one VERBATIM quote. Keep rare/one-off points. Do not synthesise or drop anything "
         "relevant.\n\nQUESTION: {question}\n\nUNITS:\n{listing}\n\nReturn a plain bulleted list of "
         "findings.").format(question=question, listing=listing)
    return claude(p, HAIKU, timeout=300)


def synthesise(question, mode, relevant, budget, pkg, shard_n=60, force_path=None,
               concentration=None):
    """force_path: None = automatic (production). "single"/"mapreduce" force one path, holding the
    evidence constant so the two can be compared directly — used to test whether citation
    fidelity is lost at the map-reduce shard boundary. Not for production use."""
    # Sort most-recent-first (missing dates last) so recency is salient in reading order — this
    # does NOT drop or deprioritise anything (completeness principle intact), it only orders what
    # the LLM sees so a later, possibly-superseding unit isn't buried behind an older one.
    relevant = sorted(relevant, key=lambda u: u.get("date") or "0000-00-00", reverse=True)
    ctx = {"units": [compact(u, nq=4, na=5, nc=10) for u in relevant]}
    payload = json.dumps(ctx, ensure_ascii=False)
    # Single-context ONLY when small enough to cite faithfully AND under token budget.
    fits = len(relevant) <= MAX_SINGLE_UNITS and tok(payload) <= budget
    if force_path == "single" or (force_path is None and fits):
        if force_path == "single" and not fits:
            sys.stderr.write(f"[synth] ⚠ FORCED single-context past the fidelity ceiling "
                             f"({len(relevant)} units > MAX_SINGLE_UNITS={MAX_SINGLE_UNITS}) — "
                             f"experiment only, expect confabulated ids\n")
        sys.stderr.write(f"[synth] single-context ({tok(payload):,} tok, {len(relevant)} units)\n")
        return claude(synth_prompt(question, mode, payload, pkg, concentration=concentration),
                      bq.MODEL, timeout=900), {u["id"] for u in relevant}
    # OVERFLOW (unit-count fidelity limit OR token budget) -> map-reduce, citation-preserving extraction
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
    return claude(synth_prompt(question, mode, blob, pkg, is_findings=True,
                               concentration=concentration),
                  bq.MODEL, timeout=900), {u["id"] for u in relevant}


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
    ap.add_argument("--package", help="graph package to query (default Brain 1; e.g. brain3_ops/package.json)")
    ap.add_argument("--dry", action="store_true", help="stop after the relevance judge; print coverage")
    ap.add_argument("--no-judge", action="store_true", help="skip Haiku judge (keep all candidates)")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--refresh-facets", action="store_true",
                    help="re-decompose instead of reusing the cached facets for this question")
    ap.add_argument("--no-repair", action="store_true",
                    help="report misattributed citations without auto-correcting them")
    ap.add_argument("--save-relevant", metavar="FILE",
                    help="write the judged relevant set to FILE (retrieval is the slow part; "
                         "this lets a later run re-synthesise the SAME evidence)")
    ap.add_argument("--load-relevant", metavar="FILE",
                    help="skip retrieval+judging and synthesise from a saved relevant set")
    ap.add_argument("--limit-relevant", type=int,
                    help="truncate the relevant set to N units (experiments only)")
    ap.add_argument("--shard-n", type=int, default=60, help="units per map-reduce shard")
    ap.add_argument("--force-path", choices=["single", "mapreduce"],
                    help="force the synthesis path instead of auto-selecting (experiments only)")
    args = ap.parse_args()

    if args.package:
        bq.PACKAGE = args.package
    pkg = bq.load()
    all_libs = sorted({u["src"].get("lib") for u in pkg["units"]})
    libs = [args.library] if args.library else all_libs
    by_id = {u["id"]: u for u in pkg["units"]}

    if args.load_relevant:
        cached = json.load(open(args.load_relevant, encoding="utf-8"))
        facets = cached.get("facets", [])
        coverage = {l: tuple(v) for l, v in cached.get("coverage", {}).items()}
        relevant = [by_id[i] for i in cached["relevant_ids"] if i in by_id]
        missing = len(cached["relevant_ids"]) - len(relevant)
        sys.stderr.write(f"[load] {len(relevant)} relevant units from {args.load_relevant}"
                         + (f" ({missing} no longer in package)" if missing else "") + "\n")
    else:
        facets = decompose(args.question, args.facets, package=bq.PACKAGE,
                           refresh=args.refresh_facets)
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

    # SOURCE CONCENTRATION — a brief drawn 67% from one training organisation reads as industry
    # consensus when it is one school's doctrine. Surface it to the caller, and (below) tell the
    # synthesis to say so in the brief itself.
    dom_lib, dom_share = None, 0.0
    if relevant:
        counts = {}
        for u in relevant:
            counts[u["src"].get("lib", "?")] = counts.get(u["src"].get("lib", "?"), 0) + 1
        dom_lib, dom_n = max(counts.items(), key=lambda kv: kv[1])
        dom_share = dom_n / len(relevant)
        sys.stderr.write(f"[concentration] top source {dom_lib} = {dom_n}/{len(relevant)} "
                         f"({100*dom_share:.0f}%) of carried evidence"
                         + ("  ⚠ >50% — single-source dominance\n" if dom_share > 0.5 else "\n"))

    if args.save_relevant:
        json.dump({"question": args.question, "package": bq.PACKAGE, "facets": facets,
                   "coverage": {l: list(v) for l, v in coverage.items()},
                   "relevant_ids": [u["id"] for u in relevant]},
                  open(args.save_relevant, "w", encoding="utf-8"), indent=2)
        sys.stderr.write(f"[saved] relevant set -> {args.save_relevant}\n")

    if args.dry:
        print(json.dumps({"facets": facets,
                          "coverage": {l: {"candidates": c, "relevant": r} for l, (c, r) in coverage.items()},
                          "total_relevant": len(relevant),
                          "top_source": dom_lib, "top_source_share": round(dom_share, 3)}, indent=2))
        return

    if args.limit_relevant:
        relevant = relevant[:args.limit_relevant]
        sys.stderr.write(f"[limit] truncated to {len(relevant)} relevant units (experiment)\n")

    sys.stderr.write("[opus] deep synthesis…\n")
    answer, shortlist_ids = synthesise(args.question, args.mode, relevant, args.token_budget, pkg,
                                       shard_n=args.shard_n, force_path=args.force_path,
                                       concentration=(dom_lib, dom_share))
    # VERIFY (+ REPAIR) BEFORE OUTPUT — the verifier already knows each misattributed quote's true
    # source, so the correct id is substituted back into the brief and the result re-verified.
    # Detection alone left the caller to hand-fix; repair means the printed/saved brief is the
    # corrected one. Fabricated quotes are never auto-repaired and still fail the publish gate.
    if not args.no_verify:
        # scope the true-source search to THIS package's units — otherwise a paraphrased quote
        # gets falsely attributed to a verbatim match in another brain not in context.
        import brain1_verify as bv
        answer, _stats = bv.audit(answer, by_id, shortlist_ids=shortlist_ids,
                                  repair=not args.no_repair, question=args.question)
    print(answer)

    if args.out:
        open(args.out, "w", encoding="utf-8").write(answer)
        sys.stderr.write(f"[saved] {args.out}\n")


if __name__ == "__main__":
    main()
