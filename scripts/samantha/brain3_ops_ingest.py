#!/usr/bin/env python3
"""
Brain 3 (internal OPERATIONAL knowledge) — ingest + batch emitter.

REFRAME 2026-07-21 (Will): Brain 3 is a NEW brain from our internal operational data, and the
KB (/home/fields/knowledge-base/) is EXCLUDED ENTIRELY (it holds personal/financial data). This
script therefore NEVER touches the knowledge-base; it reads curated VM knowledge files, the
system_monitor NARRATIVE collections (PII collections excluded), and the fix-history logs, and
emits Brain-1-format batch files for annotation.

DATES + STABLE IDS + DELTA (2026-07-22): every unit now carries a structured `date` (not just
buried in header text) so retrieval/synthesis can reason about recency and resolve conflicts
instead of silently treating whichever unit scored highest lexically as "current". Unit identity
is a STABLE KEY (lib + src_ref) independent of run order, so nightly re-ingestion is idempotent:
unchanged content keeps its existing id forever; only genuinely NEW or CHANGED (content_hash
differs) items get emitted for annotation. This is what makes "add new data" cheap — no whole-
graph rebuild-from-scratch of the LLM step, ever again.

Connectors:
  fs      — curated knowledge roots (07_Focus, 08_Seller-Book, 001_Our_Competitive_Advantages,
            config/*.md, 00_Run_Commands/*.md), chunked ~600 words. Date: filename date if
            present, else file mtime.
  fixlog  — logs/fix-history/*.md, one unit per "## [PROBLEM-ID]" block. Date: the log filename.
  mongo   — system_monitor narrative collections as text cards. Date: first date-shaped field
            found (date/created_at/timestamp/published_at/generated_at), else ObjectId
            generation_time. PII collections (crm_contacts/leads/analyse_leads) HARD-EXCLUDED.
            Property-structured (appraisal_substantiation, raw Gold_Coast) excluded — Brain-1
            territory.

Run:
  Full (first build / rare full rebuild): python3 brain3_ops_ingest.py --emit
  Nightly incremental (the normal path):   python3 brain3_ops_ingest.py --emit --delta
"""
import os, re, sys, json, glob, hashlib, argparse
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)  # so `from src.mongo_client_factory ...` resolves
OUT = "/home/fields/brain3_ops"
BATCH_DIR = f"{OUT}/batches_ops"
MANIFEST = f"{OUT}/units_manifest.json"
TOMBSTONES = f"{OUT}/tombstones.json"
WORDS_PER_CHUNK = 600
UNITS_PER_BATCH = 10

FS_ROOTS = ["07_Focus", "08_Seller-Book", "001_Our_Competitive_Advantages",
            "00_Run_Commands", "config"]
FS_EXTS = (".md", ".txt")
MONGO_COLLECTIONS = ["content_articles", "ceo_proposals", "ceo_memory", "ceo_briefs",
                     "will_tasks", "ad_decisions", "website_change_log", "case_study_library",
                     "market_pulse"]
PII_FIELD = re.compile(r"email|phone|mobile|password|token|secret|_id$|embedding|distinct_id", re.I)
DATE_IN_NAME = re.compile(r"(20\d{2}-\d{2}-\d{2})")
MONGO_DATE_FIELDS = ["date", "created_at", "createdAt", "timestamp", "published_at", "generated_at"]


def words(text, n=WORDS_PER_CHUNK):
    w = text.split()
    return [" ".join(w[i:i + n]) for i in range(0, len(w), n)] or []


def clean(s):
    return " ".join(str(s).split())


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24]


def stable_key(lib, src_ref):
    return f"{lib}||{src_ref}"


def stable_id(key, used_ids):
    """Deterministic 10-digit numeric id from the stable key, purely numeric so it matches the
    existing [uki]\\d{4,10} id regex. Collision-safe: perturbs with a salt if (very unlikely) the
    hash bucket is already taken by a different key."""
    salt = 0
    while True:
        basis = key if salt == 0 else f"{key}#{salt}"
        h = int(hashlib.sha1(basis.encode("utf-8")).hexdigest(), 16) % (10 ** 10)
        cand = f"i{h:010d}"
        if cand not in used_ids:
            return cand
        salt += 1


def fs_date(path):
    m = DATE_IN_NAME.search(os.path.basename(path))
    if m:
        return m.group(1)
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


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
            date = fs_date(path)
            for i, ch in enumerate(words(text)):
                if len(ch.split()) < 20:
                    continue
                out.append({"lib": f"internal:{root}", "src_ref": f"{rel}#p{i+1}",
                            "header": f"{rel} (part {i+1})", "text": clean(ch), "date": date})
    return out


def fixlog_units():
    out = []
    for path in sorted(glob.glob(f"{ORCH}/logs/fix-history/*.md")):
        date = os.path.basename(path).replace(".md", "")
        content = open(path, encoding="utf-8", errors="ignore").read()
        blocks = re.split(r"(?=^##\s+\[)", content, flags=re.M)
        for b in blocks:
            b = b.strip()
            if not b.startswith("## ["):
                continue
            title = b.splitlines()[0][:120]
            if len(b.split()) < 15:
                continue
            out.append({"lib": "internal:fix-history", "src_ref": f"{path}#{title}",
                        "header": f"fix-log {date}: {title}", "text": clean(b)[:6000], "date": date})
    return out


def mongo_doc_date(d):
    for f in MONGO_DATE_FIELDS:
        v = d.get(f)
        if v:
            s = str(v)[:10]
            if DATE_IN_NAME.match(s) or re.match(r"^\d{4}-\d{2}-\d{2}", s):
                return s[:10]
    oid = d.get("_id")
    gt = getattr(oid, "generation_time", None)
    if gt:
        try:
            return gt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


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
                        "header": f"{coll}: {title}", "text": card, "date": mongo_doc_date(d)})
    return out


def load_prior():
    """Load the prior manifest, keyed by stable key -> LIST of {id, content_hash, date} (a key
    CAN have had multiple old ids historically — e.g. the original fs chunking stored the same
    bare file path as src_ref for every chunk, so several ids collided on one key). Keeping the
    full list (not last-write-wins) means every one of those old ids gets correctly tombstoned
    if the key no longer matches, instead of silently orphaning all-but-one as duplicates.
    Transparently migrates the original id-keyed shape ({id: {lib, src_ref}}, no hash/date)."""
    if not os.path.exists(MANIFEST):
        return {}
    raw = json.load(open(MANIFEST))
    out = {}
    for uid, meta in raw.items():
        key = stable_key(meta["lib"], meta.get("src_ref", ""))
        out.setdefault(key, []).append(
            {"id": uid, "content_hash": meta.get("content_hash"), "date": meta.get("date")})
    return out


def assemble(units, prior):
    """Assign each unit its STABLE id (reused from prior if the key existed, else freshly
    derived), and classify new_or_changed vs unchanged. Returns (all_units, new_or_changed,
    removed_ids, new_manifest). removed_ids tombstones ALL old ids for any key not seen this
    run — not just one — so a src_ref-format change (like the fs chunk-index fix below) can't
    leave orphaned duplicates sitting in the graph."""
    used_ids = {e["id"] for lst in prior.values() for e in lst}
    new_manifest, new_or_changed, seen_keys = {}, [], set()
    for u in units:
        key = stable_key(u["lib"], u["src_ref"])
        seen_keys.add(key)
        h = content_hash(u["text"])
        prev_list = prior.get(key)
        prev = prev_list[-1] if prev_list else None  # most-recently-written entry for this key
        if prev:
            uid = prev["id"]
            if prev.get("content_hash") is None:
                # migrated from the original hash-less manifest: no baseline to diff against.
                # Assume unchanged (the data is already correctly annotated) — this run backfills
                # a REAL hash so genuinely future edits are detected correctly from here on.
                changed = False
            else:
                changed = prev.get("content_hash") != h
        else:
            uid = stable_id(key, used_ids)
            used_ids.add(uid)
            changed = True
        u["unit_id"] = uid
        new_manifest[uid] = {"lib": u["lib"], "src_ref": u["src_ref"], "date": u.get("date", ""),
                             "content_hash": h}
        if changed:
            new_or_changed.append(u)
    removed_ids = [e["id"] for k, lst in prior.items() if k not in seen_keys for e in lst]
    return units, new_or_changed, removed_ids, new_manifest


def next_batch_index():
    existing = glob.glob(f"{BATCH_DIR}/b_*.txt")
    if not existing:
        return 0
    return max(int(re.search(r"b_(\d+)\.txt", f).group(1)) for f in existing) + 1


def emit_batches(units_to_write, full_rebuild):
    os.makedirs(BATCH_DIR, exist_ok=True)
    if full_rebuild:
        for old in glob.glob(f"{BATCH_DIR}/b_*.txt"):
            os.remove(old)
        start = 0
    else:
        start = next_batch_index()
    n = 0
    for i in range(0, len(units_to_write), UNITS_PER_BATCH):
        chunk = units_to_write[i:i + UNITS_PER_BATCH]
        with open(f"{BATCH_DIR}/b_{start + i // UNITS_PER_BATCH:04d}.txt", "w", encoding="utf-8") as fh:
            for u in chunk:
                fh.write(f"===== UNIT {u['unit_id']} | LIB: {u['lib']} =====\n")
                fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")
        n += len(chunk)
    return n, (len(units_to_write) + UNITS_PER_BATCH - 1) // UNITS_PER_BATCH if units_to_write else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="write batch files (default: just report counts)")
    ap.add_argument("--delta", action="store_true",
                    help="incremental mode (the nightly path): only emit NEW/CHANGED units, "
                         "reuse existing ids for unchanged content, append (never wipe) batches")
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

    prior = load_prior() if args.delta else {}
    all_units, new_or_changed, removed_ids, manifest = assemble(units, prior)

    if args.delta:
        sys.stderr.write(f"[delta] {len(new_or_changed)} new/changed | {len(removed_ids)} removed "
                         f"| {len(all_units) - len(new_or_changed)} unchanged (skipped)\n")

    if args.emit:
        to_write = new_or_changed if args.delta else all_units
        n, nb = emit_batches(to_write, full_rebuild=not args.delta)
        json.dump(manifest, open(MANIFEST, "w"), indent=0)
        if removed_ids:
            prev_tomb = json.load(open(TOMBSTONES)) if os.path.exists(TOMBSTONES) else []
            json.dump(sorted(set(prev_tomb) | set(removed_ids)), open(TOMBSTONES, "w"), indent=0)
        sys.stderr.write(f"[emit] {n} units -> {nb} batch file(s) in {BATCH_DIR} "
                         f"({'delta' if args.delta else 'full'} mode)\n")
    else:
        sys.stderr.write("[dry] --emit to write batches\n")


if __name__ == "__main__":
    main()
