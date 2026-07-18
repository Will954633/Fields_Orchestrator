#!/usr/bin/env python3
"""
Brain 1 — Tier-3 DEEP query tool.

Single keyword net (brain1_query.py) caps at ~45 units and is hostage to one phrasing.
This tool does the higher-quality process:
  1. DECOMPOSE the question into ~8 retrieval facets (Haiku on Max) so recall isn't
     tied to one keyword net.
  2. MULTI-RETRIEVE — score units per facet (reuses brain1_query.score_units), union+dedupe.
  3. GRAPH-EXPAND once over the whole chosen set (1-hop typed edges -> indirect neighbours).
  4. SYNTHESISE — one deep Opus-on-Max call over the merged shortlist.
  5. VERIFY — every unit id Opus cites is checked: does it exist, was it actually in the
     shortlist we sent (invented ids = hallucination flag), and is it in the requested library.

100% Anthropic on Max — no embeddings, no vector DB, no paid API (Will directive).

Usage:
  env -u CLAUDECODE python3 scripts/samantha/brain1_deep.py "your question" \
      [--library "Sell It"] [--mode general|insight] [--per-facet 22] [--neigh 30] \
      [--out /path/answer.md] [--dry] [--no-verify]
"""
import os, re, sys, json, argparse, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain1_query as bq

UID_RE = re.compile(r"\bu\d{4}\b")


def claude(prompt, model, timeout=900):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(["claude", "-p", "--model", model],
                       input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude({model}) exit {r.returncode}: {r.stderr[:300]}")
    return r.stdout.strip()


def decompose(question, n=8):
    """Ask Haiku to split the question into n distinct retrieval facets. Falls back to [question]."""
    p = (f"Break this research question into {n} DISTINCT search facets for retrieving passages "
         f"from a real-estate coaching corpus. Each facet = a short keyword-rich phrase covering a "
         f"different angle (methods, obstacles, objections, psychology, principles, etc.). "
         f"Return ONLY a JSON array of {n} strings, nothing else.\n\nQUESTION: {question}")
    try:
        out = claude(p, "claude-haiku-4-5-20251001", timeout=120)
        m = re.search(r"\[.*\]", out, re.S)
        facets = json.loads(m.group(0))
        facets = [f.strip() for f in facets if isinstance(f, str) and f.strip()]
        return facets or [question]
    except Exception as e:
        sys.stderr.write(f"[decompose] fell back to raw question ({e})\n")
        return [question]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--library", help="restrict primary + neighbour units to one library "
                                       "(e.g. 'Sell It', 'RealEstate_Gym', 'Agent School')")
    ap.add_argument("--mode", choices=["general", "insight"], default="general")
    ap.add_argument("--per-facet", type=int, default=22)
    ap.add_argument("--neigh", type=int, default=30)
    ap.add_argument("--facets", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    pkg = bq.load()
    lib = args.library

    def in_lib(u):
        return (not lib) or u["src"].get("lib") == lib

    # a scoring package whose units are restricted to the library (expand still uses full graph)
    scan_pkg = {**pkg, "units": [u for u in pkg["units"] if in_lib(u)]}
    if lib:
        sys.stderr.write(f"[library] restricted to '{lib}' -> {len(scan_pkg['units'])} units in scope\n")

    facets = decompose(args.question, args.facets)
    sys.stderr.write(f"[facets] {len(facets)}:\n" + "".join(f"   - {f}\n" for f in facets))

    seen, chosen = set(), []
    for f in facets:
        for _, u in bq.score_units(scan_pkg, f)[:args.per_facet]:
            if u["id"] not in seen:
                seen.add(u["id"]); chosen.append(u)

    by_id = {u["id"]: u for u in pkg["units"]}
    neigh_ids, bridging = bq.expand(pkg, chosen, set(seen))
    neigh = [by_id[i] for i in neigh_ids if i in by_id and in_lib(by_id[i])][:args.neigh]

    ctx = bq.build_context(chosen, neigh, bridging)
    shortlist_ids = {u["id"] for u in chosen} | {u["id"] for u in neigh}

    base = (
        "You are Brain 1 — an intelligence layer over a real-estate coaching corpus "
        "(Tom Panos/RealEstate Gym, Ryan Serhant/Sell It, Mat Steinwede & Josh Tesolin/Agent School). "
        "Below is a broad multi-facet shortlist of annotated coaching units + typed concept-edges among them.\n\n"
    )
    task = (
        "Answer the QUESTION with a DEEP, well-structured brief. Synthesise ACROSS units into method families; "
        "surface the difficulties/obstacles; then an INSIGHT LAYER that extracts the core principles and extends "
        "them into new/sharpened methods (flag which are un-copyable given Fields' data platform). "
        if args.mode == "general" else
        "Do NOT just summarise. Bridge DISTANT concepts across different units to generate NEW, non-obvious "
        "client-acquisition plays for Fields (a Gold Coast data-first agency). Name each play, cite the unit ids "
        "it bridges, state the mechanism. "
    )
    rules = (
        "RULES: cite unit ids (e.g. u0452) for every substantive claim; include DIRECT VERBATIM QUOTES throughout; "
        "if the corpus does not cover something, say so plainly — do NOT invent. Structure with clear headings.\n\n"
        f"=== QUESTION ===\n{args.question}\n\n=== CORPUS SHORTLIST (JSON) ===\n"
        + json.dumps(ctx, ensure_ascii=False)
    )
    prompt = base + task + rules
    approx = len(prompt) // 4
    sys.stderr.write(f"[shortlist] {len(chosen)} primary + {len(neigh)} neighbour units, "
                     f"{len(bridging)} edges | ~{approx:,} tokens\n")

    if args.dry:
        print(json.dumps({"facets": facets, "n_primary": len(chosen), "n_neigh": len(neigh),
                          "approx_tokens": approx}, indent=2))
        return

    sys.stderr.write("[opus] deep synthesis…\n")
    answer = claude(prompt, bq.MODEL, timeout=900)
    print(answer)

    if not args.no_verify:
        cited = sorted(set(UID_RE.findall(answer)))
        exists = [c for c in cited if c in by_id]
        in_shortlist = [c for c in cited if c in shortlist_ids]
        invented = [c for c in cited if c not in by_id]
        out_of_scope = [c for c in cited if c in by_id and c not in shortlist_ids]
        sys.stderr.write(
            f"\n[verify] {len(cited)} unit ids cited | {len(in_shortlist)} in shortlist ✓ | "
            f"{len(out_of_scope)} exist-but-not-in-shortlist | {len(invented)} INVENTED\n")
        if invented:
            sys.stderr.write(f"[verify] ⚠ INVENTED ids (hallucination): {invented}\n")
        if out_of_scope:
            sys.stderr.write(f"[verify] note out-of-shortlist ids: {out_of_scope[:20]}\n")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(answer)
        sys.stderr.write(f"[saved] {args.out}\n")


if __name__ == "__main__":
    main()
