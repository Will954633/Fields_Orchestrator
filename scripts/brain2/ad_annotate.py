#!/usr/bin/env python3
"""
ad_annotate.py — Brain 2 Layer 2: deep semantic annotation of every ad's creative.

Runs Claude OPUS (high effort) on the Anthropic Max subscription via `claude -p`
(no paid API, no ollama) over each ad's structured creative + copy, producing one
richly-categorised annotation record so we can find patterns across the whole
account — tone, emotional lever (fear vs curiosity vs aspiration...), hook type,
claim types, persona, CTA hardness, editorial-compliance flags, verbatim copy.

Design: annotation covers CREATIVE CONTENT ONLY. Performance metrics are joined
deterministically in Layer 3 — we never let the model see outcomes and rationalise
backwards.

Durable + resumable:
  • Reads ads from ad_profiles.creative_structured (Layer 1 output).
  • Writes each annotation to system_monitor.ad_semantic_annotations the instant it
    parses; keyed by ad_id, stamped with content_hash of the annotated input.
  • Skips ads whose content_hash is unchanged (re-run only re-does changed/failed).
  • Lockfile so a cron relaunch is safe.

Usage:
  python3 scripts/brain2/ad_annotate.py                 # annotate all pending
  python3 scripts/brain2/ad_annotate.py --id <AD_ID>    # single ad (prints result)
  python3 scripts/brain2/ad_annotate.py --limit 3       # first N pending
  python3 scripts/brain2/ad_annotate.py --force         # re-annotate all
"""
import os, sys, json, glob, time, fcntl, hashlib, argparse, subprocess
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

MODEL = "claude-opus-4-8"
LOG = "/home/fields/Fields_Orchestrator/logs/brain2-ad-annotate.log"
LOCK = "/tmp/brain2_ad_annotate.lock"

SCHEMA_PROMPT = """You are a senior direct-response advertising analyst building a structured knowledge base of every Facebook ad a property-intelligence company has run, so patterns can be mined across the whole account (e.g. "does fear-based copy out-engage curiosity-based copy?", "how do video ads differ from single-image ads?").

You will receive ONE ad's factual creative details (format, CTA, and verbatim copy). Analyse ONLY the creative content given. Do NOT speculate about performance — you are not shown any metrics. Be precise and evidence-based; quote the copy.

Output ONE JSON object with EXACTLY these keys:

- "headline_present": boolean — is there a distinct headline/title separate from body?
- "headline_text": string — the headline, or "".
- "copy_line_count": integer — number of non-empty lines in the body copy.
- "copy_word_count": integer — words in the body copy.
- "copy_sentence_count": integer.
- "reading_complexity": one of "simple","moderate","complex".
- "primary_emotional_lever": the SINGLE dominant emotional driver, one of:
    "fear_anxiety","curiosity","aspiration","urgency_scarcity","trust_credibility",
    "relief_simplification","pride_status","fomo","frustration","none".
- "emotional_registers": array of {"emotion": <same vocabulary as above>, "intensity": "low"|"medium"|"high", "evidence": <short verbatim phrase from the copy>}.
- "tone": array of applicable tones from:
    "analytical","conversational","authoritative","urgent","empathetic",
    "provocative","educational","storytelling","confident","understated".
- "hook_type": the opening device, one of:
    "question","statistic_number","contrarian_claim","story_narrative","direct_offer",
    "provocation","curiosity_gap","social_proof","problem_statement","how_to".
- "hook_text": string — the verbatim opening hook.
- "message_theme": short lowercase phrase for what the ad is fundamentally about
    (e.g. "market timing","specific property story","data you can't get elsewhere",
     "curation over overwhelm","valuation accuracy","buyer education").
- "value_proposition": one sentence — what the ad promises the reader.
- "target_persona": one of "buyer","seller","both","investor","unclear".
- "specificity": {"cites_numbers": boolean, "cites_address_or_property": boolean, "cites_suburb": boolean, "examples": [<verbatim specifics: prices, %s, addresses, suburbs>]}.
- "claim_types": array from "data_claim","capability_claim","social_proof","scarcity","authority","comparison","none".
- "claims": array of specific claims made (verbatim or close paraphrase).
- "cta_semantic": {"action": <what the reader is asked to do>, "hardness": "soft"|"medium"|"hard", "friction": "low"|"medium"|"high"}.
- "editorial_compliance": {"gives_advice": boolean, "makes_prediction": boolean, "single_valuation_in_headline": boolean, "forbidden_words": [<any of: stunning,nestled,boasting,rare opportunity,robust market>], "notes": <short>}.
- "distinctive_features": array of short strings — what makes THIS ad's creative distinctive vs a generic version.
- "one_line_summary": string — the ad in one sentence.

Output ONLY the JSON object. No prose, no markdown fences."""


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def ad_input_block(prof):
    """Build the factual creative block fed to Opus (content only, no metrics)."""
    cs = prof.get("creative_structured", {}) or {}
    bodies = cs.get("bodies") or []
    titles = cs.get("titles") or []
    lines = {
        "ad_name": prof.get("name", ""),
        "format": cs.get("format", ""),
        "cta_button": cs.get("primary_cta", ""),
        "n_body_variants": cs.get("n_body_variants", 0),
        "n_title_variants": cs.get("n_title_variants", 0),
    }
    block = "\n".join(f"{k}: {v}" for k, v in lines.items())
    block += "\n\nTITLE(S):\n" + ("\n---\n".join(titles) if titles else "(none)")
    block += "\n\nBODY COPY:\n" + ("\n===VARIANT===\n".join(bodies) if bodies else "(none)")
    return block


def content_hash(prof):
    cs = prof.get("creative_structured", {}) or {}
    payload = json.dumps({
        "bodies": cs.get("bodies"), "titles": cs.get("titles"),
        "format": cs.get("format"), "cta": cs.get("primary_cta"),
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def call_opus(block, timeout=300):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    prompt = SCHEMA_PROMPT + "\n\n===== AD =====\n" + block
    # --effort high = Opus adaptive high reasoning; the --settings override clears
    # the global alwaysThinkingEnabled, which injects the legacy thinking.type.enabled
    # param that Opus 4.8 rejects (400).
    r = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--effort", "high",
         "--settings", '{"alwaysThinkingEnabled":false}'],
        input=prompt, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:200]}")
    return r.stdout.strip()


def extract_json_object(s):
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON object in output")
    return json.loads(s[a:b + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    db = get_client()["system_monitor"]
    ann = db["ad_semantic_annotations"]
    ann.create_index("ad_id", unique=True)

    q = {"creative_structured": {"$exists": True}}
    if args.id:
        q = {"_id": args.id}
    profs = list(db.ad_profiles.find(q))

    if args.id:  # single, verbose, no lock
        prof = profs[0]
        out = call_opus(ad_input_block(prof))
        rec = extract_json_object(out)
        print(json.dumps(rec, indent=2))
        return

    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("already running — exiting"); return

    done = {d["ad_id"]: d.get("content_hash") for d in ann.find({}, {"ad_id": 1, "content_hash": 1})}
    pending = []
    for p in profs:
        h = content_hash(p)
        if args.force or done.get(p["_id"]) != h:
            pending.append((p, h))
    if args.limit:
        pending = pending[:args.limit]
    log(f"START — {len(profs)} ads, {len(pending)} to annotate")

    ok = err = 0
    for i, (prof, h) in enumerate(pending, 1):
        aid = prof["_id"]
        block = ad_input_block(prof)
        rec = None
        for attempt in (1, 2):
            try:
                rec = extract_json_object(call_opus(block))
                break
            except Exception as e:
                log(f"  [{i}/{len(pending)}] {aid} attempt {attempt} failed: {str(e)[:140]}")
                time.sleep(4)
        if rec is None:
            err += 1
            continue
        cs = prof.get("creative_structured", {})
        ann.replace_one({"ad_id": aid}, {
            "ad_id": aid,
            "ad_name": prof.get("name", ""),
            "campaign_name": prof.get("campaign_name", ""),
            "campaign_objective": prof.get("campaign_objective", ""),
            "format": cs.get("format", ""),
            "content_hash": h,
            "model": MODEL,
            "annotation": rec,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
        }, upsert=True)
        ok += 1
        log(f"  [{i}/{len(pending)}] {aid} OK — lever={rec.get('primary_emotional_lever')} "
            f"hook={rec.get('hook_type')} theme={rec.get('message_theme')}")

    log(f"DONE — {ok} annotated, {err} failed")


if __name__ == "__main__":
    main()
