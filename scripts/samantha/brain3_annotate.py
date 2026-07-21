#!/usr/bin/env python3
"""
brain3_annotate.py — DURABLE, resumable Haiku annotation of the curated KB (Brain 3).

Clone of brain1_annotate.py (same durable/resumable/lockfile/cron-safe machinery), with:
  • a KB-specific prompt (no coaching "channels"; adds decisions/initiatives/metrics facets);
  • a --pool {public|private} selector so the PUBLIC-SAFE pool is annotated + validated first,
    fully isolated from the firewalled PRIVATE pool (separate batches/out/lock/done/complete).

Batches produced by kb_ingest.py (--emit-only) in /home/fields/brain3_build/batches_<pool>/.
100% on the Anthropic Max subscription via `claude -p` (Haiku). No paid API, no ollama.

Run:  env -u CLAUDECODE python3 scripts/samantha/brain3_annotate.py --pool public
Cron auto-resume: */10 * * * * /home/fields/brain3_build/run_<pool>.sh
"""
import os, re, sys, json, glob, time, fcntl, argparse
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openrouter_client as orc

BASE = "/home/fields/brain3_build"
MODEL = orc.HAIKU  # annotation stays Haiku, now via OpenRouter (off Max budget)
MAX_WORDS_PER_UNIT = 1200

PROMPT_HEADER = """You are annotating UNITS from a real-estate company's internal knowledge base (books, papers, articles, strategy docs, meeting notes) to build a queryable knowledge graph.

For EACH unit below, output one JSON object with EXACTLY these keys:
- "unit_id": the given id (e.g. "k00231")
- "provenance": {"source": "KB", "pool": <from LIB before the colon: "public" or "private">, "category": <from LIB after the colon>, "doc": <the document name from HEADER>}
- "topic_tags": array of short lowercase tags (what the unit is actually about)
- "concepts": array of concise concept/idea phrases the unit contains
- "entities": array of named people/companies/tools/places/sources mentioned
- "claims": array of specific claims, findings, or assertions made (what is argued to be true)
- "decisions": array of decisions or recommendations stated (empty if none)
- "initiatives": array of projects/actions proposed or underway (empty if none)
- "metrics": array of concrete numbers/KPIs/targets/results cited (empty if none)
- "relationships": array of {"from": concept, "type": one of "enables"|"requires"|"supports"|"contradicts"|"example_of", "to": concept}
- "answers_questions": array of natural-language questions THIS unit would answer (specific to the unit, not generic)
- "key_quotes": array of the most useful VERBATIM quotes (copy exact words; do NOT paraphrase). 1-4 quotes.

If a unit is thin or administrative, still fill it out honestly with whatever it holds (empty arrays where nothing applies).

Output ONLY a valid JSON array of these objects, in the same order as the units. No prose, no markdown fences.

UNITS:
"""


def log(logpath, msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with open(logpath, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def parse_batch(path):
    content = open(path, encoding="utf-8", errors="ignore").read()
    parts = re.split(r"===== UNIT (k\d+) \| LIB: (.*?) =====", content)
    units = []
    for i in range(1, len(parts), 3):
        uid = parts[i].strip()
        lib = parts[i + 1].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        hm = re.search(r"HEADER:\s*(.*)", body)
        tm = re.search(r"TEXT:\s*(.*)", body, re.S)
        header = hm.group(1).strip() if hm else ""
        text = " ".join((tm.group(1).strip() if tm else "").split()[:MAX_WORDS_PER_UNIT])
        units.append({"unit_id": uid, "lib": lib, "header": header, "text": text})
    return units


def build_prompt(units):
    blocks = [f'--- unit_id: {u["unit_id"]} | lib: {u["lib"]}\nHEADER: {u["header"]}\nTEXT: {u["text"]}'
              for u in units]
    return PROMPT_HEADER + "\n\n".join(blocks)


def call_haiku(prompt, timeout=300):
    return orc.call(prompt, MODEL, timeout=timeout, max_tokens=16000)


def extract_json_array(s):
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON array in output")
    return json.loads(s[a:b + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=["public", "private"], required=True)
    args = ap.parse_args()
    pool = args.pool

    batch_dir = f"{BASE}/batches_{pool}"
    OUT = f"{BASE}/annotations_{pool}.jsonl"
    DONE = f"{BASE}/done_batches_{pool}.txt"
    FAIL = f"{BASE}/failures_{pool}.txt"
    LOG = f"{BASE}/brain3_annotate_{pool}.log"
    LOCK = f"{BASE}/.lock_{pool}"
    COMPLETE = f"{BASE}/COMPLETE_{pool}"

    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"already running ({pool}) — exiting")
        return
    lockf.write(str(os.getpid())); lockf.flush()

    batches = sorted(glob.glob(f"{batch_dir}/b_*.txt"))
    done = set(l.strip() for l in open(DONE)) if os.path.exists(DONE) else set()
    todo = [b for b in batches if os.path.basename(b) not in done]
    log(LOG, f"START [{pool}] — {len(done)}/{len(batches)} done, {len(todo)} to do")

    for path in todo:
        name = os.path.basename(path)
        units = parse_batch(path)
        recs = None
        for attempt in (1, 2):
            try:
                recs = extract_json_array(call_haiku(build_prompt(units)))
                if not isinstance(recs, list) or not recs:
                    raise ValueError("empty/invalid array")
                break
            except Exception as e:
                log(LOG, f"  {name} attempt {attempt} failed: {str(e)[:160]}")
                time.sleep(5)
        if recs is None:
            open(FAIL, "a").write(name + "\n")
            log(LOG, f"  {name} SKIPPED after retries")
            continue
        with open(OUT, "a") as f:
            for rec in recs:
                rec["_batch"] = name
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        open(DONE, "a").write(name + "\n")
        done.add(name)
        log(LOG, f"  {name} OK — {len(recs)} units ({len(done)}/{len(batches)} done)")

    remaining = [b for b in batches if os.path.basename(b) not in done]
    if not remaining:
        open(COMPLETE, "w").write(datetime.now(timezone.utc).isoformat())
        log(LOG, f"COMPLETE [{pool}] — all {len(batches)} batches -> {OUT}")
    else:
        log(LOG, f"PAUSED [{pool}] — {len(remaining)} remain (resume next run)")


if __name__ == "__main__":
    main()
