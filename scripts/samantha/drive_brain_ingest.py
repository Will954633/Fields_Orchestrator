#!/usr/bin/env python3
"""
drive_brain_ingest.py — ingest ALL of Fields' Google Drive knowledge into the brains,
with a per-document classifier that decides intelligently WHICH brain each file belongs to
(or whether it must be excluded entirely).

Routing model (Will's established two-axis firewall, 2026-07-18/19 + 2026-07-31):
  • BRAIN 1  = EXTERNAL / public-safe published knowledge — generic real-estate / marketing /
               behavioural-science research, competitor analysis, positioning theory. Can inform
               PUBLIC content. Folds into the external pool alongside the coaching corpus + KB books.
  • BRAIN 3  = INTERNAL Fields operational / strategic material — our own data analysis, our test
               results, our case studies, our seller-book drafts, our strategy + action docs.
               Firewalled (Samantha-only).
  • EXCLUDE  = PII / financial / client-identifying / zero-knowledge junk. Never enters any brain.

Two-stage firewall (fail CLOSED):
  1. HARD-PRIVATE regex on the file name + folder path (bank/tax/invoice/statement/payslip/…, and
     the client-specific "Appraisals" folder) → EXCLUDE, no LLM, no exceptions.
  2. Otherwise a cheap Haiku-on-Max classifier reads name + folder path + a text sample and returns
     brain1 / brain3 / exclude. On any uncertainty or error it defaults to BRAIN 3 (private) — never
     brain1 — so nothing confidential can leak into the public-informing pool by mistake.

Auth: the non-expiring service account /home/fields/.gcp-floor-plan-vision.json (drive.readonly),
NOT the 7-day OAuth MCP token — this runs nightly on cron. The SA must have each root folder shared
with floor-plan-processor@fields-estate.iam.gserviceaccount.com (verified 2026-07-31).

Output namespace: /home/fields/brain_drive/ (own manifest + tombstones + two batch pools), merged
into the Brain 1 and Brain 3 packages at graph-build time by brain_drive_nightly.py — so the two
source brains' own ingest pipelines are never touched.

LLM: Haiku on the Max subscription via max_client (classification is cheap/high-volume). Annotation
of the emitted batches is done separately by brain3_annotate.py (also Haiku on Max).

Run:
  Dry classification report (no batches, no annotate): python3 drive_brain_ingest.py
  Emit delta batches (the nightly path):               python3 drive_brain_ingest.py --emit --delta
  Full re-emit (rare, wipes batch pools):              python3 drive_brain_ingest.py --emit
"""
import os, re, sys, json, glob, argparse, subprocess, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import max_client as orc
import brain3_ops_ingest as ing  # reuse: content_hash, stable_key, stable_id, words, clean

OUT = "/home/fields/brain_drive"
MANIFEST = f"{OUT}/units_manifest.json"
DOC_CACHE = f"{OUT}/doc_decisions.json"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")

WORDS_PER_CHUNK = 600
UNITS_PER_BATCH = 10
CLASSIFY_SAMPLE_WORDS = 1500

# Drive roots to walk. Coaching transcripts (1iyd…) are DELIBERATELY excluded — they are already
# annotated into Brain 1 via the dedicated brain1 pipeline (u#### ids); re-ingesting here would
# duplicate them under new ids. Add new shared folders as Will shares them with the SA.
ROOTS = {
    "Research": "1AYkf2FPojjKTTPFjx8CkkqX9nXCsM1h9",
    "Seller_Book": "1Ga_UdxLQQIAeYtKdqGH2V1w5POI5DL67",
    "Seller_Book_V2": "1pkV-EkTmq4qzVTdG8abVN-ggRiMmkOeo",
}

FOLDER_MIME = "application/vnd.google-apps.folder"

# Stage-1 firewall: name/path patterns that are ALWAYS private, no LLM asked.
HARD_PRIVATE = re.compile(
    r"invoice|statement|bank|\btax\b|receipt|payslip|payroll|superannuat|\bBAS\b|\bABN\b|"
    r"balance.?sheet|profit.?(and|&).?loss|\bP&L\b|ledger|salary|remittance|"
    r"passport|licen[cs]e|medicare|\bTFN\b|contract of sale|\bcommission statement",
    re.I)
# Client-specific files: a "draft appraisal" names a real address + a valuation = client PII.
# We DON'T blanket-exclude the whole "Appraisals" folder — it also holds generic strategy docs;
# each is judged by the content-classifier (which excludes real appraisals + financial records and
# fails closed to brain3/private, never brain1, when unsure). Filename is the hard signal here.
HARD_PRIVATE_PATH = re.compile(r"draft.{0,3}appraisal", re.I)

# mimeType -> how to pull text
GDOC = "application/vnd.google-apps.document"
GSHEET = "application/vnd.google-apps.spreadsheet"
GSLIDE = "application/vnd.google-apps.presentation"
PDF = "application/pdf"

CLASSIFY_PROMPT = """You are the data-router for a real-estate company's (Fields) internal AI "brains". Decide which brain ONE document belongs to, or whether it must be excluded.

BRAIN 1 = EXTERNAL, public-safe PUBLISHED knowledge: generic real-estate / marketing / behavioural-science research, competitor analysis, industry best-practice, positioning theory. Not Fields-confidential; could legitimately inform PUBLIC content.
BRAIN 3 = INTERNAL Fields operational/strategic material: our OWN data analysis, our test results, our case studies, our seller-book drafts, our strategy docs, knowledge gaps, internal action items. Confidential.
EXCLUDE = personal/financial/PII (bank, tax, invoice, payslip, a named client's appraisal, contracts), raw data dumps with no reusable knowledge, or empty/administrative junk.

Rules:
- If it identifies a specific private individual's finances/property/contract -> exclude.
- If unsure between brain1 and brain3, choose brain3 (safer: private). Only choose brain1 when it is clearly generic, publishable knowledge.
- Judge by CONTENT, not just the title.

Return ONLY compact JSON: {"decision":"brain1|brain3|exclude","reason":"<=15 words"}

DOCUMENT NAME: %(name)s
FOLDER PATH: %(path)s
TEXT SAMPLE:
%(sample)s
"""


def log(msg):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def drive():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def walk(svc, folder_id, path_prefix, acc):
    """Recursively collect non-folder files under folder_id. acc gets dicts with a `path`."""
    page = None
    while True:
        r = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType,modifiedTime)",
            pageSize=100, pageToken=page,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in r.get("files", []):
            if f["mimeType"] == FOLDER_MIME:
                walk(svc, f["id"], f"{path_prefix}/{f['name']}", acc)
            else:
                f["path"] = f"{path_prefix}/{f['name']}"
                acc.append(f)
        page = r.get("nextPageToken")
        if not page:
            break


def extract_text(svc, f):
    mt = f.get("mimeType", "")
    fid = f["id"]
    try:
        if mt == GDOC or mt == GSLIDE:
            return svc.files().export(fileId=fid, mimeType="text/plain").execute().decode("utf-8", "replace")
        if mt == GSHEET:
            return svc.files().export(fileId=fid, mimeType="text/csv").execute().decode("utf-8", "replace")
        if mt.startswith("text/") or mt in ("application/json", "application/rtf"):
            return svc.files().get_media(fileId=fid).execute().decode("utf-8", "replace")
        if mt == PDF:
            data = svc.files().get_media(fileId=fid).execute()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(data); tmp = tf.name
            try:
                out = subprocess.run(["pdftotext", "-q", tmp, "-"], capture_output=True, timeout=120)
                return out.stdout.decode("utf-8", "replace")
            finally:
                os.unlink(tmp)
    except Exception as e:
        log(f"  [extract] {f['name'][:50]}: {str(e)[:100]}")
    return ""  # images/video/binary/unsupported -> no text


def classify(name, path, text):
    """Return (decision, reason). Fail CLOSED to brain3 (private) on any error/uncertainty."""
    sample = " ".join(text.split()[:CLASSIFY_SAMPLE_WORDS])
    prompt = CLASSIFY_PROMPT % {"name": name, "path": path, "sample": sample}
    try:
        out = orc.call(prompt, orc.HAIKU, timeout=120, max_tokens=200)
        a, b = out.find("{"), out.rfind("}")
        d = json.loads(out[a:b + 1])
        dec = d.get("decision", "").strip().lower()
        if dec not in ("brain1", "brain3", "exclude"):
            return "brain3", "classifier returned unknown decision -> default private"
        return dec, d.get("reason", "")[:120]
    except orc.MaxQuotaExhausted:
        raise
    except Exception as e:
        return "brain3", f"classifier error -> default private: {str(e)[:60]}"


def lib_for(decision, top_folder):
    prefix = "external" if decision == "brain1" else "internal"
    return f"{prefix}:drive/{top_folder}"


def load_prior_manifest():
    """key -> {id, content_hash, date, lib}. Independent of the source brains' manifests."""
    if not os.path.exists(MANIFEST):
        return {}
    raw = json.load(open(MANIFEST))
    out = {}
    for uid, m in raw.items():
        out[ing.stable_key(m["lib"], m.get("src_ref", ""))] = {
            "id": uid, "content_hash": m.get("content_hash"), "date": m.get("date"), "lib": m["lib"]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="write batch files (default: dry report only)")
    ap.add_argument("--delta", action="store_true",
                    help="incremental: only re-classify/emit docs whose content changed; reuse ids")
    ap.add_argument("--limit", type=int, default=0, help="cap files processed (testing)")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    svc = drive()
    files = []
    for name, fid in ROOTS.items():
        try:
            walk(svc, fid, name, files)
        except Exception as e:
            log(f"[walk] root {name} failed: {str(e)[:120]}")
    if args.limit:
        files = files[:args.limit]
    log(f"[walk] {len(files)} file(s) across {len(ROOTS)} root(s)")

    doc_cache = json.load(open(DOC_CACHE)) if os.path.exists(DOC_CACHE) else {}
    prior = load_prior_manifest() if args.delta else {}

    units, decisions = [], {"brain1": 0, "brain3": 0, "exclude": 0, "hard_private": 0, "no_text": 0}
    used_ids = {e["id"] for e in prior.values()}
    new_manifest, seen_keys, new_or_changed = {}, set(), []

    for f in files:
        name, path = f["name"], f.get("path", f["name"])
        date = (f.get("modifiedTime") or "")[:10]
        top = path.split("/", 1)[0]

        # Stage 1 — hard firewall (no LLM, fail closed)
        if HARD_PRIVATE.search(name) or HARD_PRIVATE_PATH.search(path):
            decisions["hard_private"] += 1
            doc_cache[f["id"]] = {"content_hash": None, "decision": "exclude",
                                  "reason": "hard-private firewall", "name": name}
            continue

        text = extract_text(svc, f)
        if len(text.split()) < 25:
            decisions["no_text"] += 1
            continue
        h = ing.content_hash(text)

        # Stage 2 — classifier (cached by content hash so unchanged docs are free)
        cached = doc_cache.get(f["id"])
        if cached and cached.get("content_hash") == h:
            decision, reason = cached["decision"], cached.get("reason", "")
        else:
            decision, reason = classify(name, path, text)
            doc_cache[f["id"]] = {"content_hash": h, "decision": decision, "reason": reason, "name": name}
        decisions[decision] = decisions.get(decision, 0) + 1
        if decision == "exclude":
            continue

        lib = lib_for(decision, top)
        for i, ch in enumerate(ing.words(text, WORDS_PER_CHUNK)):
            if len(ch.split()) < 20:
                continue
            src_ref = f"drive:{f['id']}#p{i+1}"
            key = ing.stable_key(lib, src_ref)
            seen_keys.add(key)
            uh = ing.content_hash(ch)
            prev = prior.get(key)
            if prev and prev.get("content_hash") is not None:
                uid = prev["id"]; changed = prev["content_hash"] != uh
            elif prev:
                uid = prev["id"]; changed = False
            else:
                uid = ing.stable_id(key, used_ids); used_ids.add(uid); changed = True
            u = {"unit_id": uid, "lib": lib, "src_ref": src_ref,
                 "header": f"{name} (part {i+1})", "text": ing.clean(ch), "date": date,
                 "brain": decision}
            units.append(u)
            new_manifest[uid] = {"lib": lib, "src_ref": src_ref, "date": date, "content_hash": uh}
            if changed:
                new_or_changed.append(u)

    # Tombstones: any prior unit whose key wasn't seen this run (doc deleted or reclassified to a
    # different brain). Route each to its OWN brain's tombstone file by lib prefix.
    removed = [(e["id"], e.get("lib", "")) for k, e in prior.items() if k not in seen_keys]

    log(f"[classify] brain1={decisions['brain1']} brain3={decisions['brain3']} "
        f"exclude={decisions['exclude']} hard_private={decisions['hard_private']} "
        f"no_text={decisions['no_text']}")
    by_brain = {"brain1": [u for u in units if u["brain"] == "brain1"],
                "brain3": [u for u in units if u["brain"] == "brain3"]}
    log(f"[units] brain1={len(by_brain['brain1'])} brain3={len(by_brain['brain3'])} "
        f"| new/changed={len(new_or_changed)} | removed={len(removed)}")

    if not args.emit:
        log("[dry] --emit to write batches")
        return

    to_write = new_or_changed if args.delta else units
    for pool, prefix in (("b1", "external:"), ("b3", "internal:")):
        pool_units = [u for u in to_write if u["lib"].startswith(prefix)]
        emit_pool(pool, pool_units, full=not args.delta)
        log(f"[emit] pool {pool}: {len(pool_units)} unit(s)")

    json.dump(new_manifest, open(MANIFEST, "w"), indent=0)
    json.dump(doc_cache, open(DOC_CACHE, "w"), indent=0)
    # per-brain tombstones
    for pool, prefix in (("b1", "external:"), ("b3", "internal:")):
        ids = [uid for uid, lib in removed if lib.startswith(prefix)]
        if ids:
            tomb = f"{OUT}/tombstones_{pool}.json"
            prev = json.load(open(tomb)) if os.path.exists(tomb) else []
            json.dump(sorted(set(prev) | set(ids)), open(tomb, "w"), indent=0)
    log("[done] manifest + doc cache + tombstones written")


def emit_pool(pool, pool_units, full):
    batch_dir = f"{OUT}/batches_{pool}"
    os.makedirs(batch_dir, exist_ok=True)
    if full:
        for old in glob.glob(f"{batch_dir}/b_*.txt"):
            os.remove(old)
        start = 0
    else:
        existing = glob.glob(f"{batch_dir}/b_*.txt")
        start = (max(int(re.search(r"b_(\d+)\.txt", x).group(1)) for x in existing) + 1) if existing else 0
    for i in range(0, len(pool_units), UNITS_PER_BATCH):
        chunk = pool_units[i:i + UNITS_PER_BATCH]
        with open(f"{batch_dir}/b_{start + i // UNITS_PER_BATCH:04d}.txt", "w", encoding="utf-8") as fh:
            for u in chunk:
                fh.write(f"===== UNIT {u['unit_id']} | LIB: {u['lib']} =====\n")
                fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")


if __name__ == "__main__":
    main()
