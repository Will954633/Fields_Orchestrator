#!/usr/bin/env python3
"""
Brain 3 (internal OPERATIONAL knowledge) — ingest + batch emitter.

REFRAME 2026-07-21 (Will): Brain 3 is a NEW brain from our internal operational data, and the
KB (/home/fields/knowledge-base/) is EXCLUDED ENTIRELY (it holds personal/financial data). This
script therefore NEVER touches the knowledge-base; it reads curated VM knowledge files, the
system_monitor NARRATIVE collections (PII collections excluded), and the fix-history logs, and
emits Brain-1-format batch files for annotation. Same pipeline as Brain 1 (annotate → graph →
deep-query → verify), but Brain 3 is its own firewalled package in /home/fields/brain3_ops/.

Connectors:
  fs      — curated knowledge roots (07_Focus, 08_Seller-Book, 001_Our_Competitive_Advantages,
            config/*.md, 00_Run_Commands/*.md), chunked ~600 words.
  fixlog  — logs/fix-history/*.md, one unit per "## [PROBLEM-ID]" block.
  mongo   — system_monitor narrative collections as text cards. PII collections
            (crm_contacts / leads / analyse_leads) HARD-EXCLUDED. Property-structured
            (appraisal_substantiation, raw Gold_Coast) excluded — that's Brain-1 territory.

Run:  env-load .env, then  python3 scripts/samantha/brain3_ops_ingest.py [--emit]
"""
import os, re, sys, json, glob, hashlib, argparse

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)  # so `from src.mongo_client_factory ...` resolves
OUT = "/home/fields/brain3_ops"
BATCH_DIR = f"{OUT}/batches_ops"
WORDS_PER_CHUNK = 600
UNITS_PER_BATCH = 10

FS_ROOTS = ["07_Focus", "08_Seller-Book", "001_Our_Competitive_Advantages",
            "00_Run_Commands", "config"]
FS_EXTS = (".md", ".txt")
# system_monitor NARRATIVE collections (business knowledge). PII + property-structured excluded.
MONGO_COLLECTIONS = ["content_articles", "ceo_proposals", "ceo_memory", "ceo_briefs",
                     "will_tasks", "ad_decisions", "website_change_log", "case_study_library",
                     "market_pulse"]
PII_FIELD = re.compile(r"email|phone|mobile|password|token|secret|_id$|embedding|distinct_id", re.I)


def words(text, n=WORDS_PER_CHUNK):
    w = text.split()
    return [" ".join(w[i:i + n]) for i in range(0, len(w), n)] or []


def clean(s):
    return " ".join(str(s).split())


def fs_units():
    out = []
    for root in FS_ROOTS:
        base = os.path.join(ORCH, root)
        if not os.path.isdir(base):
            continue
        for path in sorted(glob.glob(f"{base}/**/*", recursive=True)):
            if not path.endswith(FS_EXTS) or not os.path.isfile(path):
                continue
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            rel = os.path.relpath(path, ORCH)
            for i, ch in enumerate(words(text)):
                if len(ch.split()) < 20:
                    continue
                out.append({"lib": f"internal:{root}", "src_ref": rel,
                            "header": f"{rel} (part {i+1})", "text": clean(ch)})
    return out


def fixlog_units():
    out = []
    for path in sorted(glob.glob(f"{ORCH}/logs/fix-history/*.md")):
        date = os.path.basename(path).replace(".md", "")
        content = open(path, encoding="utf-8", errors="ignore").read()
        # split on "## [PROBLEM-ID] ..." headers, keep the header with its block
        blocks = re.split(r"(?=^##\s+\[)", content, flags=re.M)
        for b in blocks:
            b = b.strip()
            if not b.startswith("## ["):
                continue
            title = b.splitlines()[0][:120]
            if len(b.split()) < 15:
                continue
            out.append({"lib": "internal:fix-history", "src_ref": f"{path}#{title}",
                        "header": f"fix-log {date}: {title}", "text": clean(b)[:6000]})
    return out


def mongo_units():
    from src.mongo_client_factory import get_mongo_client
    db = get_mongo_client()["system_monitor"]
    out = []
    for coll in MONGO_COLLECTIONS:
        try:
            cur = db[coll].find({}, limit=5000)
        except Exception as e:
            sys.stderr.write(f"[mongo] {coll} skipped: {e}\n")
            continue
        for d in cur:
            # render a text card: non-PII string/number fields only
            parts = []
            for k, v in d.items():
                if PII_FIELD.search(k):
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, default=str)[:800]
                s = clean(v)
                if s and len(s) > 1:
                    parts.append(f"{k}: {s}")
            card = " | ".join(parts)[:6000]
            if len(card.split()) < 12:
                continue
            title = clean(d.get("title") or d.get("name") or d.get("headline")
                          or d.get("problem_id") or str(d.get("_id", "")))[:90]
            out.append({"lib": f"internal:{coll}", "src_ref": f"{coll}:{d.get('_id')}",
                        "header": f"{coll}: {title}", "text": card})
    return out


def emit(units):
    os.makedirs(BATCH_DIR, exist_ok=True)
    for old in glob.glob(f"{BATCH_DIR}/b_*.txt"):
        os.remove(old)
    manifest = {}
    for uid_i, u in enumerate(units):
        u["unit_id"] = f"i{uid_i:05d}"
        manifest[u["unit_id"]] = {"lib": u["lib"], "src_ref": u["src_ref"]}
    for i in range(0, len(units), UNITS_PER_BATCH):
        with open(f"{BATCH_DIR}/b_{i//UNITS_PER_BATCH:04d}.txt", "w", encoding="utf-8") as fh:
            for u in units[i:i + UNITS_PER_BATCH]:
                fh.write(f"===== UNIT {u['unit_id']} | LIB: {u['lib']} =====\n")
                fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")
    json.dump(manifest, open(f"{OUT}/units_manifest.json", "w"), indent=0)
    return len(units), (len(units) + UNITS_PER_BATCH - 1) // UNITS_PER_BATCH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="write batch files (default: just report counts)")
    ap.add_argument("--no-mongo", action="store_true", help="skip the mongo connector (files only)")
    args = ap.parse_args()

    fs = fs_units()
    fx = fixlog_units()
    mg = [] if args.no_mongo else mongo_units()
    units = fs + fx + mg

    from collections import Counter
    by_src = Counter(u["lib"] for u in units)
    sys.stderr.write(f"[ingest] fs={len(fs)} fixlog={len(fx)} mongo={len(mg)} | total units={len(units)}\n")
    for lib, n in sorted(by_src.items()):
        sys.stderr.write(f"   {lib:34s} {n}\n")

    if args.emit:
        n, nb = emit(units)
        sys.stderr.write(f"[emit] {n} units -> {nb} batches in {BATCH_DIR}\n")
    else:
        sys.stderr.write("[dry] --emit to write batches\n")


if __name__ == "__main__":
    main()
