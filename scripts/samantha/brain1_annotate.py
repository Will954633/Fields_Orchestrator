#!/usr/bin/env python3
"""
brain1_annotate.py — DURABLE, resumable Haiku annotation of the coaching corpus (Brain 1).

Why this exists: the earlier workflow-based run kept dying on session limits and lost
its thread because it wrote to session scratchpad with no checkpoint. This version is
built to survive interruption:
  • Corpus lives in a durable dir (/home/fields/brain1_build/batches, 309 files x 10 units).
  • Each batch's annotations are appended to annotations.jsonl the instant they're parsed,
    and the batch is marked done. A kill mid-run loses at most one batch.
  • A lockfile lets a cron relaunch it safely — if it's already running, the new run exits.
  • On restart it skips done batches and resumes exactly where it stopped.
  • 100% on the Anthropic Max subscription via `claude -p` (Haiku). No paid API, no ollama.

Run: env -u CLAUDECODE python3 scripts/samantha/brain1_annotate.py
Cron relaunch (auto-resume): */10 * * * * /home/fields/brain1_build/run.sh
"""
import os, re, sys, json, glob, time, fcntl, subprocess
from datetime import datetime, timezone

BASE = "/home/fields/brain1_build"
BATCH_DIR = f"{BASE}/batches"
OUT = f"{BASE}/annotations.jsonl"
DONE = f"{BASE}/done_batches.txt"
FAIL = f"{BASE}/failures.txt"
LOG = f"{BASE}/brain1_annotate.log"
LOCK = f"{BASE}/.lock"
COMPLETE = f"{BASE}/COMPLETE"
MODEL = "claude-haiku-4-5-20251001"
MAX_WORDS_PER_UNIT = 1500  # cap runaway transcripts; keeps a 10-unit batch well within Haiku

PROMPT_HEADER = """You are annotating transcript UNITS from real-estate coaching programs to build a knowledge graph of client-acquisition methods that are claimed to work.

For EACH unit below, output one JSON object with EXACTLY these keys:
- "unit_id": the given id (e.g. "u0231")
- "provenance": {"library": <given lib>, "course": <from header or "">, "module": <from header or "">}
- "topic_tags": array of short lowercase tags (what the unit is actually about)
- "channels": array of {"channel": <client-acquisition channel e.g. "cold_calling","database_reactivation","referrals","social_media","door_knocking","open_homes","past_clients","farming","video","seo","paid_ads","auctions","free_value_content">, "emphasis": one of "PRIMARY"|"USED"|"AVOIDED"}. AVOIDED = the speaker deliberately does NOT use it (contrarian — capture these). Empty array if the unit teaches no acquisition channel.
- "concepts": array of concise concept phrases taught (mindset, tactic, principle)
- "entities": array of named people/companies/tools/places mentioned
- "claims": array of specific claims of what works or what result it produced
- "outcomes": array of concrete outcomes/numbers cited (e.g. "listed 60 homes/yr")
- "relationships": array of {"from": concept, "type": one of "enables"|"requires"|"supports"|"contradicts"|"example_of", "to": concept}
- "answers_questions": array of natural-language questions THIS unit would answer for an agent (be specific to the unit, not generic)
- "key_quotes": array of the most useful VERBATIM quotes (copy exact words from the text; do NOT paraphrase). 1-4 quotes.

If a unit is off-topic (not about real estate / acquisition), still fill it out honestly with whatever concepts it holds and channels=[].

Output ONLY a valid JSON array of these objects, in the same order as the units. No prose, no markdown fences.

UNITS:
"""


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def parse_batch(path):
    content = open(path, encoding="utf-8", errors="ignore").read()
    parts = re.split(r"===== UNIT (u\d+) \| LIB: (.*?) =====", content)
    units = []
    for i in range(1, len(parts), 3):
        uid = parts[i].strip()
        lib = parts[i + 1].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        hm = re.search(r"HEADER:\s*(.*)", body)
        tm = re.search(r"TEXT:\s*(.*)", body, re.S)
        header = hm.group(1).strip() if hm else ""
        text = (tm.group(1).strip() if tm else "").split()
        text = " ".join(text[:MAX_WORDS_PER_UNIT])
        units.append({"unit_id": uid, "lib": lib, "header": header, "text": text})
    return units


def build_prompt(units):
    blocks = []
    for u in units:
        blocks.append(
            f'--- unit_id: {u["unit_id"]} | lib: {u["lib"]}\nHEADER: {u["header"]}\nTEXT: {u["text"]}'
        )
    return PROMPT_HEADER + "\n\n".join(blocks)


def call_haiku(prompt, timeout=300):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(
        ["claude", "-p", "--model", MODEL],
        input=prompt, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:200]}")
    return r.stdout.strip()


def extract_json_array(s):
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON array in output")
    return json.loads(s[a:b + 1])


def main():
    os.makedirs(BATCH_DIR, exist_ok=True)
    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("already running — exiting")
        return
    lockf.write(str(os.getpid()))
    lockf.flush()

    batches = sorted(glob.glob(f"{BATCH_DIR}/b_*.txt"))
    done = set()
    if os.path.exists(DONE):
        done = set(l.strip() for l in open(DONE) if l.strip())
    todo = [b for b in batches if os.path.basename(b) not in done]
    log(f"START — {len(done)}/{len(batches)} batches already done, {len(todo)} to do")

    for path in todo:
        name = os.path.basename(path)
        units = parse_batch(path)
        prompt = build_prompt(units)
        recs = None
        for attempt in (1, 2):
            try:
                out = call_haiku(prompt)
                recs = extract_json_array(out)
                if not isinstance(recs, list) or not recs:
                    raise ValueError("empty/invalid array")
                break
            except Exception as e:
                log(f"  {name} attempt {attempt} failed: {str(e)[:160]}")
                time.sleep(5)
        if recs is None:
            with open(FAIL, "a") as f:
                f.write(name + "\n")
            log(f"  {name} SKIPPED after retries")
            continue
        with open(OUT, "a") as f:
            for rec in recs:
                rec["_batch"] = name
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(DONE, "a") as f:
            f.write(name + "\n")
        done.add(name)
        log(f"  {name} OK — {len(recs)} units ({len(done)}/{len(batches)} done)")

    remaining = [b for b in batches if os.path.basename(b) not in done]
    if not remaining:
        open(COMPLETE, "w").write(datetime.now(timezone.utc).isoformat())
        log(f"COMPLETE — all {len(batches)} batches annotated -> {OUT}")
    else:
        log(f"PAUSED — {len(remaining)} batches remain (will resume next run)")


if __name__ == "__main__":
    main()
