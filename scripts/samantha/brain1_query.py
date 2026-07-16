#!/usr/bin/env python3
"""
Brain 1 — Phase 2 retrieval + reasoning harness.

The full graph package (~2.2M tokens) does not fit Opus's 1M window, so retrieval is:
  1. Deterministic lexical pre-filter — score every unit by query-term overlap against
     its concepts / topics / answers_questions / quotes / module title. Free, no model.
  2. Graph expansion — pull in 1-hop neighbours via typed_edges whose endpoints appear
     in the top units. This is what surfaces INDIRECT links keyword search misses.
  3. Feed the shortlist (units + the typed edges among them) to an Opus agent on Max
     (claude -p) which does the graph-walk reasoning / synthesis / insight natively.

100% Anthropic on Max — no embeddings, no vector DB, no paid API (Will directive).

Usage:
  env -u CLAUDECODE python3 scripts/samantha/brain1_query.py "your question" [--k 50] [--mode general|insight]
  --dry   : print the shortlist + prompt size, skip the Opus call (for tuning / cost check)
"""
import os, re, sys, json, argparse, subprocess
from collections import defaultdict

PACKAGE = "/home/fields/brain1_build/package.json"
MODEL = "opus"  # CLI alias -> Opus on Max
_ws = re.compile(r"\s+")
STOP = set("the a an and or of to in for on with your you it is are be as at by from this that "
           "how why what when who do does can will if into over out up not no more most your their "
           "them they we our us i me my he she his her its about which than then them being".split())


def toks(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 2]


def load():
    with open(PACKAGE, encoding="utf-8") as fh:
        return json.load(fh)


def score_units(pkg, query):
    qt = set(toks(query))
    scored = []
    for u in pkg["units"]:
        blob = " ".join(
            u["concepts"] + u["topics"] + u["asks"] + u["quotes"]
            + [u["src"].get("module", ""), u["src"].get("course", "")]
        )
        ut = toks(blob)
        utset = set(ut)
        overlap = qt & utset
        if not overlap:
            continue
        # weight: distinct-term overlap (recall) + a small freq bonus (density)
        s = len(overlap) + 0.1 * sum(ut.count(w) for w in overlap)
        # asks/quotes hits are high-signal for narrative content -> bonus
        ask_hit = sum(1 for a in u["asks"] if qt & set(toks(a)))
        scored.append((s + 0.5 * ask_hit, u))
    scored.sort(key=lambda x: -x[0])
    return scored


def expand(pkg, top_units, top_ids):
    """1-hop typed-edge neighbours: edges whose endpoints touch the top set."""
    concept_to_units = pkg["concept_index"]
    top_concepts = set()
    for u in top_units:
        top_concepts.update(u["concepts"])
    neigh_ids = set()
    bridging = []
    for e in pkg["typed_edges"]:
        if e["from"] in top_concepts or e["to"] in top_concepts:
            other = e["to"] if e["from"] in top_concepts else e["from"]
            for uid in concept_to_units.get(other, []):
                if uid not in top_ids:
                    neigh_ids.add(uid)
            bridging.append(e)
    return neigh_ids, bridging[:120]


def build_context(top_units, neigh_units, bridging):
    def fmt(u):
        return {
            "id": u["id"],
            "src": f"{u['src']['lib']} / {u['src']['course']} / {u['src']['module']}",
            "concepts": u["concepts"][:10],
            "channels": u["channels"],
            "asks": u["asks"][:5],
            "quotes": u["quotes"][:4],
        }
    return {
        "primary_units": [fmt(u) for u in top_units],
        "neighbour_units": [fmt(u) for u in neigh_units],
        "typed_edges": [{"from": e["from"], "type": e["type"], "to": e["to"], "count": e["count"]} for e in bridging],
    }


PROMPTS = {
    "general": (
        "You are Brain 1 — an intelligence layer over a real-estate coaching corpus (Tom Panos, "
        "Ryan Serhant, Mat Steinwede). Below is a shortlist of annotated coaching units plus the "
        "typed relationship edges among their concepts. Answer the QUESTION by synthesising ACROSS "
        "units. Group findings into method families. Cite unit ids. Quote verbatim where it matters. "
        "If the corpus genuinely does not cover something, say so plainly — do NOT invent. "
        "This is for Fields (a Gold Coast data-first agency), so flag what is directly applicable."
    ),
    "insight": (
        "You are Brain 1 — an insight engine over a real-estate coaching corpus. Below is a shortlist "
        "of annotated units + typed concept edges. Do NOT just summarise. Bridge DISTANT concepts across "
        "different courses to generate NEW, non-obvious client-acquisition plays Fields (a Gold Coast "
        "data-first agency) could run. For each idea: name it, cite the source unit ids it bridges, and "
        "state the mechanism. Ground every idea in the corpus — cite ids; no hallucination."
    ),
}


def call_opus(prompt, timeout=600):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(["claude", "-p", "--model", MODEL],
                       input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:300]}")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=45, help="primary units to keep")
    ap.add_argument("--neigh", type=int, default=25, help="max graph-neighbour units")
    ap.add_argument("--mode", choices=list(PROMPTS), default="general")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    pkg = load()
    scored = score_units(pkg, args.query)
    top = [u for _, u in scored[:args.k]]
    top_ids = {u["id"] for u in top}
    print(f"[retrieval] {len(scored)} units matched; keeping top {len(top)}", file=sys.stderr)

    neigh_ids, bridging = expand(pkg, top, top_ids)
    by_id = {u["id"]: u for u in pkg["units"]}
    neigh = [by_id[i] for i in list(neigh_ids)[:args.neigh] if i in by_id]
    print(f"[graph] {len(neigh_ids)} neighbour units found via {len(bridging)} typed edges; "
          f"keeping {len(neigh)}", file=sys.stderr)

    ctx = build_context(top, neigh, bridging)
    prompt = (PROMPTS[args.mode] + "\n\n=== QUESTION ===\n" + args.query
              + "\n\n=== CORPUS SHORTLIST (JSON) ===\n" + json.dumps(ctx, ensure_ascii=False))
    approx = len(prompt) // 4
    print(f"[prompt] ~{approx:,} tokens ({len(ctx['primary_units'])} primary + "
          f"{len(ctx['neighbour_units'])} neighbour units, {len(ctx['typed_edges'])} edges)", file=sys.stderr)

    if args.dry:
        print(json.dumps(ctx, ensure_ascii=False, indent=2)[:4000])
        return
    print("[opus] reasoning…", file=sys.stderr)
    print(call_opus(prompt))


if __name__ == "__main__":
    main()
