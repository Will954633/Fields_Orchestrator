#!/usr/bin/env python3
"""
Brain 1 — Phase 2b: concept normalization (Sonnet on Max).

Maps the ~30k near-unique raw concept strings to a smaller canonical vocabulary so the
knowledge graph's typed + co-occurrence edges actually connect (endpoints match).

WHY SONNET (not Haiku): empirically compared on a 90-concept batch (2026-07-16) —
Sonnet found more true merges (20 vs 13 clusters), higher compression (0.378 vs 0.311),
made finer semantically-correct distinctions, and AVOIDED the over-merges Haiku made
(over-merge = false graph edges = the dangerous failure mode). It was also faster here.
This is a one-time build, judgment-heavy → quality > speed. See norm_compare_out.json.

Durable/resumable (mirrors brain1_annotate.py): lockfile, done_batches, append-per-batch,
cron-safe. 100% Anthropic on Max — no embeddings, no paid API.

Pass 1 (this script default): normalize each batch of raw concepts -> canonical_label.
Pass 2 (--consolidate): dedup the canonical VOCABULARY itself (fixes cross-batch drift),
   producing the final concept->canonical map at concept_canonical.json.

Run:  env -u CLAUDECODE python3 scripts/samantha/brain1_normalize.py [--batch 120] [--consolidate]
"""
import os, re, sys, json, time, fcntl, argparse, subprocess
from pathlib import Path

BUILD = Path("/home/fields/brain1_build")
PACKAGE = BUILD / "package.json"
MAP = BUILD / "concept_norm_map.jsonl"       # raw_concept -> canonical (pass 1, appended)
DONE = BUILD / "norm_done_batches.txt"
LOCK = BUILD / ".norm_lock"
FINAL = BUILD / "concept_canonical.json"      # final raw -> canonical (after consolidate)
MODEL = "sonnet"
BATCH = 120

PROMPT_HEAD = (
    "You are normalizing a real-estate coaching CONCEPT vocabulary so a knowledge graph can "
    "merge synonymous ideas. For EACH concept below, output a short canonical_label: a lowercase "
    "noun phrase (2-5 words) capturing the underlying idea. Concepts meaning the SAME underlying "
    "idea MUST get the IDENTICAL canonical_label. Keep genuinely DISTINCT ideas separate — do NOT "
    "over-merge (merging distinct ideas corrupts the graph). Return ONLY a JSON object mapping each "
    "EXACT original string to its canonical_label. No prose, no code fences.\n\nCONCEPTS:\n"
)


def call(prompt, timeout=420):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(["claude", "-p", "--model", MODEL],
                       input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:200]}")
    out = r.stdout.strip()
    if out.startswith("```"):
        out = out.split("```")[1]
        out = out[4:].strip() if out.lower().startswith("json") else out.strip()
    return json.loads(out)


def log(msg):
    ts = subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True).stdout.strip()
    line = f"{ts}  {msg}"
    print(line, file=sys.stderr)
    with open(BUILD / "brain1_normalize.log", "a") as fh:
        fh.write(line + "\n")


def load_concepts():
    pkg = json.load(open(PACKAGE, encoding="utf-8"))
    return sorted(pkg["concept_index"].keys())


def pass1(batch_size):
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("already running — exiting"); return
    concepts = load_concepts()
    batches = [concepts[i:i + batch_size] for i in range(0, len(concepts), batch_size)]
    done = set()
    if DONE.exists():
        done = set(l.strip() for l in open(DONE) if l.strip())
    log(f"START — {len(concepts)} concepts, {len(batches)} batches ({len(done)} already done)")
    for idx, b in enumerate(batches):
        bid = f"nb_{idx:04d}"
        if bid in done:
            continue
        prompt = PROMPT_HEAD + json.dumps(b, ensure_ascii=False, indent=1)
        for attempt in (1, 2):
            try:
                mapping = call(prompt)
                with open(MAP, "a", encoding="utf-8") as fh:
                    for orig, lab in mapping.items():
                        fh.write(json.dumps({"c": orig, "k": str(lab).strip().lower()}, ensure_ascii=False) + "\n")
                with open(DONE, "a") as fh:
                    fh.write(bid + "\n")
                log(f"  {bid} OK — {len(mapping)} concepts ({idx + 1}/{len(batches)})")
                break
            except Exception as e:
                log(f"  {bid} attempt {attempt} failed: {e}")
                if attempt == 2:
                    log(f"  {bid} SKIPPED")
    if len(set(l.strip() for l in open(DONE) if l.strip())) >= len(batches):
        (BUILD / "NORM_PASS1_COMPLETE").write_text("done\n")
        log(f"PASS1 COMPLETE — {MAP}")


def consolidate():
    """Pass 2: merge canonical labels that are themselves near-duplicates, then emit final map."""
    raw2k = {}
    for line in open(MAP, encoding="utf-8"):
        d = json.loads(line)
        raw2k[d["c"]] = d["k"]
    labels = sorted(set(raw2k.values()))
    log(f"CONSOLIDATE — {len(raw2k)} concepts -> {len(labels)} canonical labels; deduping labels")
    # dedup the label vocabulary in Sonnet batches
    label_map = {}
    for i in range(0, len(labels), 200):
        chunk = labels[i:i + 200]
        prompt = (
            "These are canonical concept labels from a real-estate coaching graph. Some are duplicates "
            "phrased differently. Map each to a single MASTER label (lowercase noun phrase); identical "
            "ideas -> identical master. Do NOT over-merge distinct ideas. Return ONLY a JSON object "
            "{label: master}. No prose.\n\nLABELS:\n" + json.dumps(chunk, ensure_ascii=False, indent=1)
        )
        try:
            m = call(prompt)
            label_map.update({k.strip().lower(): str(v).strip().lower() for k, v in m.items()})
            log(f"  labels {i}-{i+len(chunk)} consolidated")
        except Exception as e:
            log(f"  label chunk {i} failed ({e}) — keeping originals")
            for l in chunk:
                label_map.setdefault(l, l)
    final = {raw: label_map.get(k, k) for raw, k in raw2k.items()}
    json.dump(final, open(FINAL, "w", encoding="utf-8"), ensure_ascii=False)
    n_master = len(set(final.values()))
    log(f"DONE — {len(final)} concepts -> {n_master} master concepts (from {len(labels)} labels) -> {FINAL}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--consolidate", action="store_true")
    args = ap.parse_args()
    if args.consolidate:
        consolidate()
    else:
        pass1(args.batch)


if __name__ == "__main__":
    main()
