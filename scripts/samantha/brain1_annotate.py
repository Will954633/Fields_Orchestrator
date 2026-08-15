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
import os, re, sys, json, glob, time, fcntl, argparse, threading, subprocess
from concurrent.futures import ThreadPoolExecutor
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
    # Ids are u#### (coaching, YouTube), k##### (KB books) or i######### (Drive).
    # This was hard-wired to `u\d+`, so a batch of k-ids parsed to ZERO units, the
    # prompt went out empty, the model answered in prose and every batch failed
    # with "no JSON array in output" — a parser bug wearing an API error's clothes.
    parts = re.split(r"===== UNIT ([uki]\d+) \| LIB: (.*?) =====", content)
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
    # ANTHROPIC_API_KEY must go too, not just the nested-session vars: when it is
    # present the CLI prefers the metered API over the Max OAuth login and exits 1
    # ("connectors are disabled because ANTHROPIC_API_KEY ... takes precedence").
    # Same strip list as max_client.py — keep them in step.
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
                        "ANTHROPIC_API_KEY")}
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


def _rebase(base):
    """Point every path constant at a different build dir (used by the YouTube feed,
    which annotates into its own annotations file and is merged at graph time)."""
    global BASE, BATCH_DIR, OUT, DONE, FAIL, LOG, LOCK, COMPLETE
    BASE = base
    BATCH_DIR = f"{BASE}/batches"
    OUT = f"{BASE}/annotations.jsonl"
    DONE = f"{BASE}/done_batches.txt"
    FAIL = f"{BASE}/failures.txt"
    LOG = f"{BASE}/brain1_annotate.log"
    LOCK = f"{BASE}/.lock"
    COMPLETE = f"{BASE}/COMPLETE"
    os.makedirs(BASE, exist_ok=True)


def main():
    ap = argparse.ArgumentParser(description="Annotate brain-1 transcript batches.")
    ap.add_argument("--base", default=BASE,
                    help=f"build directory holding batches/ (default {BASE})")
    ap.add_argument("--workers", type=int, default=1,
                    help="batches annotated concurrently (each is one `claude -p` call)")
    ap.add_argument("--sweep-missing", action="store_true",
                    help="annotate units present in batches/ but absent from annotations.jsonl, "
                         "one at a time (recovers stragglers a batch-level retry cannot reach)")
    args = ap.parse_args()
    workers = max(1, args.workers)
    if args.base != BASE:
        _rebase(args.base)
    os.makedirs(BATCH_DIR, exist_ok=True)
    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("already running — exiting")
        return
    lockf.write(str(os.getpid()))
    lockf.flush()

    # Original corpus batches are b_*.txt; the YouTube feed writes yt_*.txt and
    # the podcast feed sp_*.txt, each into its own base. Globbing only b_* made a
    # run over the YouTube base report "COMPLETE — all 0 batches annotated" — a
    # clean exit having done nothing, which is the exact failure CLAUDE.md rule
    # 7b exists to stop. Any NEW corpus prefix must be added here too.
    batches = sorted(glob.glob(f"{BATCH_DIR}/b_*.txt")
                     + glob.glob(f"{BATCH_DIR}/yt_*.txt")
                     + glob.glob(f"{BATCH_DIR}/sp_*.txt"))
    if not batches:
        raise SystemExit(f"no batch files in {BATCH_DIR} — nothing to annotate")
    if args.sweep_missing:
        # A batch that partially succeeded is marked done, so its lost units are
        # invisible to a batch-level retry — they sit inside a "finished" batch
        # forever. This compares the unit ids in batches/ against the ids actually
        # in annotations.jsonl and annotates whatever is missing, one at a time.
        have = set()
        if os.path.exists(OUT):
            for line in open(OUT, encoding="utf-8"):
                try:
                    have.add(json.loads(line).get("unit_id"))
                except json.JSONDecodeError:
                    pass
        missing = []
        for b in batches:
            for u in parse_batch(b):
                if u["unit_id"] not in have:
                    missing.append(u)
        log(f"SWEEP — {len(have)} units annotated, {len(missing)} missing from batches/")
        if not missing:
            log("SWEEP — nothing missing, corpus is complete")
            return
        recovered = lost = 0
        for u in missing:
            try:
                recs = extract_json_array(call_haiku(build_prompt([u])))
                if not isinstance(recs, list) or not recs:
                    raise ValueError("empty/invalid array")
            except Exception as e:
                lost += 1
                log(f"  {u['unit_id']} unrecoverable: {str(e)[:120]}")
                continue
            with open(OUT, "a") as f:
                for rec in recs:
                    rec["_batch"] = "sweep"
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            recovered += 1
            log(f"  {u['unit_id']} recovered ({recovered}/{len(missing)})")
        log(f"SWEEP COMPLETE — recovered {recovered}, still lost {lost}")
        if recovered == 0 and missing:
            raise SystemExit(f"swept {len(missing)} missing units and recovered none")
        return

    done = set()
    if os.path.exists(DONE):
        done = set(l.strip() for l in open(DONE) if l.strip())
    todo = [b for b in batches if os.path.basename(b) not in done]
    log(f"START — {len(done)}/{len(batches)} batches already done, {len(todo)} to do")

    def _ask(units):
        recs = extract_json_array(call_haiku(build_prompt(units)))
        if not isinstance(recs, list) or not recs:
            raise ValueError("empty/invalid array")
        return recs

    def annotate_one(path):
        """Returns (name, recs|None). Never raises — a dead batch must not kill the run."""
        name = os.path.basename(path)
        units = parse_batch(path)
        for attempt in (1, 2):
            try:
                return name, _ask(units)
            except Exception as e:
                log(f"  {name} attempt {attempt} failed: {str(e)[:160]}")
                time.sleep(5)

        # Fall back to one unit at a time. The failures are almost entirely
        # truncated / malformed JSON on a 10-unit array — the model runs out of
        # room or fumbles an escape somewhere in ~12k words of unpunctuated
        # auto-caption text. A single unit is a short, well-formed array, so it
        # nearly always succeeds. This costs 10 calls instead of 1, but only for
        # the batches that already failed twice.
        #
        # Why it matters: without this, a batch that fails is 10 units silently
        # missing from the graph. On the first YouTube backfill that was 77 of
        # 228 batches — a THIRD of the corpus gone, while the run still exited 0.
        log(f"  {name} batch failed twice — falling back to per-unit")
        recs, lost = [], 0
        for u in units:
            try:
                recs.extend(_ask([u]))
            except Exception as e:
                lost += 1
                log(f"    {name}/{u['unit_id']} unrecoverable: {str(e)[:110]}")
        if not recs:
            return name, None
        log(f"  {name} per-unit recovered {len(recs)}/{len(units)} units ({lost} lost)")
        return name, recs

    # Each call is a `claude -p` subprocess — I/O-bound on the API, so workers cost
    # almost no local CPU. Serial, a 228-batch YouTube backfill takes ~10 hours.
    write_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, recs in pool.map(annotate_one, todo):
            with write_lock:
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
