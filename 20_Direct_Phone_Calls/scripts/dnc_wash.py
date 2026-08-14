#!/usr/bin/env python3
"""
dnc_wash.py — Australian Do Not Call Register washing for the direct-call module.

THIS IS THE ONLY THING PERMITTED TO MARK A NUMBER DIALABLE.

Legal contract it enforces (see 20_Direct_Phone_Calls/00_SCOPING.md §2):

  DNCR Act 2006 s11(3)(a) gives a defence only where the number was on a list
  submitted BY US under s19(1), and only for the 30-day period ending at the end
  of the day the call is made. Therefore:

    * every number carries its OWN wash timestamp (dnc.washed_at),
    * the wash HARD-EXPIRES 30 days later (dnc.expires_at),
    * an expired wash is NOT dialable — it is exactly as unprotected as an
      unwashed number, and this module refuses to say otherwise,
    * ID4ME's own DNC flag is NEVER a wash. It is recorded as
      dnc.id4me_advisory and is advisory only: it can BLOCK (we honour a
      third-party "registered" as a reason not to call) but it can never
      CLEAR anything. Only our own submitted-list result clears.

  ACMA IS 157: "this defence is only available to the person who washed the
  list… where a real estate agent obtains an externally provided list and does
  not carry out their own list wash, they cannot rely on the 30-day defence."

Subscription tier is Type B ($126/yr, 20,000 credits) — manual CSV upload at
donotcall.gov.au. THERE IS NO API AT THAT TIER. So the cycle is:

    --export   →  (Will uploads the CSV by hand, downloads the result)  →  --import

⚠ ACMA charges a wash credit for INVALID numbers silently: no warning, no
  abort, no refund. Every number is AU-format-validated and de-duplicated in
  OUR code before it is allowed anywhere near the export CSV. Rejects go to a
  separate file and the count is reported loudly.

Commands
    --export [--out FILE] [--limit N]     build the upload CSV
    --import FILE --submission-id ID      ingest ACMA's returned result
    --status                              counts + earliest expiry
    --assert-dialable PHONE               exit 0 iff clean AND unexpired

Importable gate for other scripts (call-list builder, sheet writer):
    from dnc_wash import is_dialable
    ok, reason = is_dialable(queue_doc)

Collections
    system_monitor.call_queue        the queue (may not exist yet — handled)
    system_monitor.dnc_submissions   one doc per export; the record of WHAT WE
                                     SUBMITTED, which is the evidence s11(6)
                                     puts the burden on us to produce.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Brisbane")
UTC = timezone.utc

WASH_VALID_DAYS = 30          # DNCR Act 2006 s11(3)(a). Not negotiable.
REWASH_LEAD_DAYS = 7          # re-export numbers expiring within this window

DB_NAME = "system_monitor"
QUEUE_COLL = "call_queue"
SUBMISSION_COLL = "dnc_submissions"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dnc")


# ---------------------------------------------------------------------------
# environment / db
# ---------------------------------------------------------------------------

def set_env_from_file():
    """Load our own environment (CLAUDE.md Rule 7 step 3) — never trust the caller."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(_REPO_ROOT, ".env"), override=False)


def _db():
    sys.path.insert(0, _REPO_ROOT)
    from shared.db import get_client
    return get_client()[DB_NAME]


def _job_status():
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
    from job_status import record_job_result
    return record_job_result


# ---------------------------------------------------------------------------
# time helpers — AEST for anything a human reads, UTC for anything stored
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(dt):
    """Cosmos hands back naive datetimes (they are UTC). Make them comparable."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def aest_str(dt, fmt="%Y-%m-%d %H:%M AEST") -> str:
    dt = as_utc(dt)
    return dt.astimezone(AEST).strftime(fmt) if dt else "—"


# ---------------------------------------------------------------------------
# AU phone validation — runs BEFORE anything is written to the export CSV
# ---------------------------------------------------------------------------

_LANDLINE_AREA = ("2", "3", "7", "8")


def normalise_au_phone(raw) -> tuple[str | None, str]:
    """Return (10-digit national number, "") or (None, reason).

    Accepts: 04xxxxxxxx, 0[2378]xxxxxxxx, +61 4xxxxxxxx, 614xxxxxxxx,
             0011 61 ... and any of the above with spaces/brackets/dashes.
    Rejects: everything else — 13/1300/1800 (not consumer numbers and a
             wasted credit), short numbers, extensions, letters.
    """
    if raw is None:
        return None, "empty"
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None, "no digits"

    # international prefixes: 0011 61 …, 61 …, +61 … (the + is already stripped)
    if digits.startswith("001161"):
        digits = digits[6:]
    elif digits.startswith("61") and len(digits) in (11, 12):
        digits = digits[2:]
    if len(digits) == 9 and digits[0] in ("4",) + _LANDLINE_AREA:
        digits = "0" + digits  # missing leading zero

    if len(digits) != 10:
        return None, f"not 10 digits (got {len(digits)})"
    if not digits.startswith("0"):
        return None, "does not start with 0"
    if digits[1] == "4":
        return digits, ""
    if digits[1] in _LANDLINE_AREA:
        return digits, ""
    return None, f"invalid AU prefix 0{digits[1]}"


def mask(phone: str) -> str:
    """04xx xxx 123 — never print a full number to stdout."""
    d = re.sub(r"\D", "", str(phone or ""))
    if len(d) != 10:
        return "xxxx xxx xxx"
    return f"{d[:2]}xx xxx {d[-3:]}"


# ---------------------------------------------------------------------------
# THE GATE
# ---------------------------------------------------------------------------

def is_dialable(doc: dict, now: datetime | None = None) -> tuple[bool, str]:
    """(dialable, reason). The single source of truth for 'may we ring this'.

    Deliberately fails CLOSED: any shape it does not understand is not dialable.
    Note it answers only the DNC question — calling hours (ACL s73), consent and
    the s215 CMA trap are enforced elsewhere.
    """
    now = as_utc(now) or now_utc()
    if not isinstance(doc, dict):
        return False, "no queue document"

    qstatus = doc.get("status")
    if qstatus == "do_not_contact":
        return False, "queue status=do_not_contact"

    phone, why = normalise_au_phone(doc.get("phone"))
    if not phone:
        return False, f"invalid phone ({why})"

    dnc = doc.get("dnc") or {}
    status = dnc.get("status", "unwashed")

    if status == "blocked":
        return False, "on the Do Not Call Register"
    if status != "clean":
        return False, f"not washed (dnc.status={status!r})"

    # A "clean" with no evidence behind it is not a wash.
    washed_at = as_utc(dnc.get("washed_at"))
    if not washed_at:
        return False, "clean but no washed_at — no evidence of a wash"
    if not dnc.get("submission_id"):
        return False, "clean but no submission_id — not OUR list (s11(3)(a))"

    expires_at = as_utc(dnc.get("expires_at")) or (washed_at + timedelta(days=WASH_VALID_DAYS))
    if now >= expires_at:
        age = (now - washed_at).days
        return False, f"wash EXPIRED {aest_str(expires_at, '%Y-%m-%d')} ({age}d old) — re-wash required"

    # ID4ME's flag can block, never clear.
    if (dnc.get("id4me_advisory") or "unknown") == "blocked":
        return False, "ID4ME advisory says registered (advisory, but we honour it)"

    days_left = (expires_at - now).days
    return True, f"clean, {days_left}d of safe harbour left (expires {aest_str(expires_at, '%Y-%m-%d')})"


# ---------------------------------------------------------------------------
# helpers over the queue
# ---------------------------------------------------------------------------

def _queue(db):
    return db[QUEUE_COLL]


def _all_queue_docs(db, extra_query: dict | None = None) -> list[dict]:
    """Cosmos: no fancy $or on nested optional fields — read and filter in Python.
    The queue is a few thousand docs at most (00_SCOPING §1: ~22k dwellings max)."""
    q = dict(extra_query or {})
    try:
        return list(_queue(db).find(q))
    except Exception as e:
        if "not found" in str(e).lower() or "NamespaceNotFound" in str(e):
            return []
        raise


def needs_wash(doc: dict, now: datetime) -> bool:
    """Unwashed, or a clean wash expiring within REWASH_LEAD_DAYS."""
    if doc.get("status") == "do_not_contact":
        return False
    dnc = doc.get("dnc") or {}
    status = dnc.get("status", "unwashed")
    if status == "blocked":
        return False          # registered; we are not going to dial it anyway
    if status != "clean":
        return True           # unwashed / unknown / anything we don't recognise
    expires_at = as_utc(dnc.get("expires_at"))
    if not expires_at:
        return True
    return expires_at <= now + timedelta(days=REWASH_LEAD_DAYS)


# ---------------------------------------------------------------------------
# --export
# ---------------------------------------------------------------------------

def make_submission_id(now: datetime | None = None) -> str:
    """Deterministic: derived from the AEST minute, NOT from randomness.
    Re-running the export inside the same minute reproduces the same id, so a
    crash-and-retry does not orphan a submission record."""
    now = as_utc(now) or now_utc()
    return "SUB-" + now.astimezone(AEST).strftime("%Y%m%d-%H%M")


def cmd_export(db, args) -> dict:
    now = now_utc()
    sub_id = args.submission_id or make_submission_id(now)

    docs = _all_queue_docs(db)
    candidates = [d for d in docs if needs_wash(d, now)]

    seen: dict[str, str] = {}          # phone -> first _id seen
    rows: list[tuple[str, dict]] = []
    rejects: list[tuple[str, str, str]] = []   # raw, reason, doc id
    dupes = 0

    for d in candidates:
        phone, why = normalise_au_phone(d.get("phone"))
        if not phone:
            rejects.append((str(d.get("phone", "")), why, str(d.get("_id"))))
            continue
        if phone in seen:
            dupes += 1
            continue
        seen[phone] = str(d.get("_id"))
        rows.append((phone, d))
        if args.limit and len(rows) >= args.limit:
            break

    out_path = args.out or os.path.join(args.out_dir, f"{sub_id}_submit.csv")
    rej_path = os.path.splitext(out_path)[0].replace("_submit", "") + "_rejects.csv"

    # ---- Rule 7b: name the zero-output path and RAISE on it -----------------
    if not docs:
        print(f"call_queue is empty ({DB_NAME}.{QUEUE_COLL} has no documents) — "
              "nothing to wash. This is 'no work to do', not a failure.")
        return {"submitted": 0, "rejected": 0, "candidates": 0, "empty_queue": True}
    if candidates and not rows:
        raise RuntimeError(
            f"{len(candidates)} numbers needed washing but ZERO survived validation "
            f"({len(rejects)} rejected, {dupes} duplicates). Refusing to write an empty "
            "submission — the upstream phone append is broken, not empty.")
    if not candidates:
        print(f"All {len(docs)} queued numbers already carry a current wash "
              f"(none expiring within {REWASH_LEAD_DAYS} days) — nothing to submit.")
        return {"submitted": 0, "rejected": 0, "candidates": 0, "empty_queue": False}

    # ---- write the files ----------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        for phone, _ in rows:
            w.writerow([phone])          # one number per line, no header
    if rejects:
        with open(rej_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["raw_value", "reason", "queue_id"])
            w.writerows(rejects)

    # ---- record the submission (this IS the s11(6) evidence) ----------------
    db[SUBMISSION_COLL].replace_one(
        {"_id": sub_id},
        {"_id": sub_id,
         "created_at": now,
         "created_at_aest": aest_str(now),
         "phones": [p for p, _ in rows],
         "queue_ids": [str(d.get("_id")) for _, d in rows],
         "count": len(rows),
         "rejected": len(rejects),
         "duplicates_skipped": dupes,
         "out_file": out_path,
         "state": "exported"},
        upsert=True)

    # mark the queue docs as submitted — NOT as washed. Nothing becomes dialable
    # here; only --import can do that.
    for phone, d in rows:
        try:
            _queue(db).update_one(
                {"_id": d["_id"]},
                {"$set": {"dnc.last_submitted_at": now,
                          "dnc.last_submission_id": sub_id,
                          "phone_normalised": phone}})
        except Exception as e:
            print(f"  ! could not tag queue doc {d.get('_id')}: {e}")

    # ---- what Will actually has to do --------------------------------------
    print()
    print("=" * 72)
    print(f"  DNC WASH EXPORT — submission {sub_id}")
    print("=" * 72)
    print(f"  numbers to submit : {len(rows)}")
    print(f"  duplicates removed: {dupes}   (each one would have cost a credit)")
    if rejects:
        print(f"  ⚠ REJECTED (invalid AU format, NOT submitted): {len(rejects)}")
        print(f"    → {rej_path}")
        print("    ACMA charges for invalid numbers silently. These were stopped here.")
        for raw, why, _id in rejects[:5]:
            print(f"      {mask(raw)}  {why}")
        if len(rejects) > 5:
            print(f"      … and {len(rejects) - 5} more")
    else:
        print("  rejected          : 0")
    print()
    print(f"  FILE TO UPLOAD    : {out_path}")
    print()
    print("  DO THIS AT donotcall.gov.au:")
    print("   1. Log in to the Do Not Call Register (Fields' OWN Type B subscription —")
    print("      a wash done by anyone else gives us NO s11(3) defence).")
    print("   2. Washing → Submit a list → upload the file above.")
    print(f"   3. It will consume {len(rows)} of the 20,000 annual wash credits.")
    print("   4. Wait for the result file, download it, then run:")
    print(f"        python3 {os.path.abspath(__file__)} \\")
    print(f"          --import /path/to/acma_result.csv --submission-id {sub_id}")
    print()
    print(f"  ⚠ The 30-day clock starts when ACMA processes the list, and this")
    print(f"    module dates it from the --import run. Import the result the same")
    print(f"    day you get it, or you are silently shortening the safe harbour.")
    print("=" * 72)
    return {"submitted": len(rows), "rejected": len(rejects), "duplicates": dupes,
            "submission_id": sub_id, "candidates": len(candidates)}


# ---------------------------------------------------------------------------
# --import
# ---------------------------------------------------------------------------

_REGISTERED_TOKENS = {"registered", "listed", "on list", "on-list", "onlist",
                      "y", "yes", "true", "1", "blocked", "dnc", "washed out",
                      "do not call", "match", "matched", "found"}
_CLEAN_TOKENS = {"not registered", "notregistered", "unregistered", "unlisted",
                 "not listed", "clean", "n", "no", "false", "0", "ok",
                 "no match", "nomatch", "not found", "unmatched"}

_STATUS_HEADER_HINTS = ("status", "result", "registered", "dnc", "outcome",
                        "washresult", "wash_result", "listed")
_PHONE_HEADER_HINTS = ("phone", "number", "msisdn", "telephone", "mobile", "contact")


def parse_acma_result(path: str) -> tuple[dict[str, bool], str, list[str]]:
    """Return ({phone: is_registered}, shape_description, warnings).

    ⚠ ACMA's Type B result file format is NOT verified — we have never run a
    wash. Two plausible shapes are supported and auto-detected:
      A) "bare list"   — one column, the numbers that ARE registered.
      B) "status rows" — a phone column plus a status/result column.
    Detection is reported out loud so a wrong guess is visible, not silent.
    """
    warnings: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw_rows = [r for r in csv.reader(f) if any((c or "").strip() for c in r)]
    if not raw_rows:
        raise RuntimeError(f"{path} is empty — nothing to import.")

    header = [(c or "").strip().lower() for c in raw_rows[0]]
    header_is_labels = any(
        any(h in cell for h in _STATUS_HEADER_HINTS + _PHONE_HEADER_HINTS)
        for cell in header) and normalise_au_phone(raw_rows[0][0])[0] is None

    body = raw_rows[1:] if header_is_labels else raw_rows
    ncols = max(len(r) for r in body)

    phone_col, status_col = 0, None
    if header_is_labels:
        for i, cell in enumerate(header):
            if status_col is None and any(h in cell for h in _STATUS_HEADER_HINTS):
                status_col = i
            if any(h in cell for h in _PHONE_HEADER_HINTS):
                phone_col = i
    if status_col is None and ncols > 1:
        # no labelled header: find a column whose values look like status tokens
        for i in range(ncols):
            vals = [(r[i].strip().lower() if i < len(r) else "") for r in body]
            vals = [v for v in vals if v]
            if vals and all(v in _REGISTERED_TOKENS or v in _CLEAN_TOKENS for v in vals):
                status_col = i
                break
    if status_col == phone_col:
        status_col = None

    result: dict[str, bool] = {}
    bad = 0
    for r in body:
        raw = r[phone_col] if phone_col < len(r) else ""
        phone, why = normalise_au_phone(raw)
        if not phone:
            bad += 1
            continue
        if status_col is not None:
            tok = (r[status_col].strip().lower() if status_col < len(r) else "")
            if tok in _REGISTERED_TOKENS:
                registered = True
            elif tok in _CLEAN_TOKENS:
                registered = False
            else:
                warnings.append(f"unrecognised status {tok!r} for {mask(phone)} "
                                "— treated as REGISTERED (fail closed)")
                registered = True
        else:
            registered = True      # bare list = the numbers that ARE registered
        result[phone] = registered

    if bad:
        warnings.append(f"{bad} row(s) in the result file did not contain a valid "
                        "AU number and were ignored")

    shape = ("status-column CSV (phone col %d, status col %d%s)"
             % (phone_col, status_col, ", labelled header" if header_is_labels else "")
             ) if status_col is not None else \
            ("bare list of REGISTERED numbers (single column%s)"
             % (", labelled header" if header_is_labels else ""))
    return result, shape, warnings


def cmd_import(db, args) -> dict:
    sub_id = args.submission_id
    sub = db[SUBMISSION_COLL].find_one({"_id": sub_id})
    if not sub:
        raise RuntimeError(
            f"No submission {sub_id!r} in {DB_NAME}.{SUBMISSION_COLL}. Import must be "
            "matched to the list WE submitted — s11(3)(a) protects only our own list. "
            "Run --export first, or pass the id printed by it.")

    submitted = set(sub.get("phones") or [])
    if not submitted:
        raise RuntimeError(f"Submission {sub_id} recorded ZERO phones — cannot import "
                           "against it (nothing to clear, nothing to block).")

    parsed, shape, warnings = parse_acma_result(args.import_file)
    print(f"Detected result-file shape: {shape}")
    print(f"  rows parsed: {len(parsed)}   submitted in {sub_id}: {len(submitted)}")
    for w in warnings:
        print(f"  ⚠ {w}")

    registered = {p for p, reg in parsed.items() if reg}
    matched = set(parsed) & submitted
    unknown = set(parsed) - submitted

    # ---- Rule 7b: the silent-zero shape. Raise; write NOTHING. -------------
    if not matched:
        raise RuntimeError(
            f"ZERO of the {len(parsed)} numbers in {args.import_file} match the "
            f"{len(submitted)} numbers submitted as {sub_id}. This is a mismatched "
            "file or a format we parsed wrongly — NOT a clean result. No wash "
            "timestamp has been written; nothing has become dialable.")

    coverage = len(matched) / len(submitted)
    if coverage < 0.5 and shape.startswith("status"):
        raise RuntimeError(
            f"Only {len(matched)}/{len(submitted)} ({coverage:.0%}) of the submitted "
            "numbers appear in a per-row status file. A status file should cover the "
            "whole list; refusing to mark the missing majority 'clean' on that basis.")

    now = now_utc()
    expires = now + timedelta(days=WASH_VALID_DAYS)

    blocked_set = registered & submitted
    if shape.startswith("bare"):
        # bare list => every submitted number NOT returned is clean
        clean_set = submitted - registered
    else:
        # status file => only rows we actually saw a clean status for
        clean_set = {p for p in matched if not parsed[p]}

    docs = _all_queue_docs(db)
    by_phone: dict[str, list[dict]] = {}
    for d in docs:
        p, _ = normalise_au_phone(d.get("phone"))
        if p:
            by_phone.setdefault(p, []).append(d)

    n_blocked = n_clean = n_orphan = 0
    for phone in sorted(blocked_set | clean_set):
        targets = by_phone.get(phone)
        if not targets:
            n_orphan += 1
            continue
        is_blocked = phone in blocked_set
        for d in targets:
            update = {
                "dnc.status": "blocked" if is_blocked else "clean",
                "dnc.washed_at": now,
                "dnc.expires_at": expires,
                "dnc.submission_id": sub_id,
                "dnc.result_file": os.path.abspath(args.import_file),
                "phone_normalised": phone,
            }
            if is_blocked:
                # Registered on the DNCR: never dialable, take it out of the queue.
                update["status"] = "do_not_contact"
                update["dnc.blocked_reason"] = "on Do Not Call Register (our wash)"
            _queue(db).update_one({"_id": d["_id"]}, {"$set": update})
            if is_blocked:
                n_blocked += 1
            else:
                n_clean += 1

    db[SUBMISSION_COLL].update_one(
        {"_id": sub_id},
        {"$set": {"state": "imported", "imported_at": now,
                  "result_file": os.path.abspath(args.import_file),
                  "result_shape": shape,
                  "registered_count": len(blocked_set),
                  "clean_count": len(clean_set),
                  "unmatched_in_result": len(unknown),
                  "expires_at": expires,
                  "warnings": warnings[:50]}})

    attrition = len(blocked_set) / max(1, len(blocked_set) + len(clean_set))
    print()
    print("=" * 72)
    print(f"  IMPORTED {sub_id}")
    print("=" * 72)
    print(f"  BLOCKED (on the register) : {n_blocked} docs / {len(blocked_set)} numbers")
    print(f"  CLEAN   (dialable)        : {n_clean} docs / {len(clean_set)} numbers")
    print(f"  DNC attrition             : {attrition:.1%}  "
          "← the number 00_SCOPING §9.4 says decides the round size")
    if unknown:
        print(f"  ⚠ {len(unknown)} number(s) in the result file were NOT in our "
              "submission — ignored (they carry no defence for us).")
    if n_orphan:
        print(f"  ⚠ {n_orphan} submitted number(s) no longer in call_queue — skipped.")
    print(f"  Safe harbour expires      : {aest_str(expires)}  (hard 30 days)")
    print("=" * 72)
    return {"blocked": len(blocked_set), "clean": len(clean_set),
            "attrition_pct": round(attrition * 100, 1), "shape": shape}


# ---------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------

def cmd_status(db, args) -> dict:
    now = now_utc()
    docs = _all_queue_docs(db)

    buckets = {"unwashed": [], "clean_current": [], "clean_expired": [],
               "blocked": [], "invalid_phone": [], "do_not_contact": []}
    expiries: list[datetime] = []

    for d in docs:
        dnc = d.get("dnc") or {}
        st = dnc.get("status", "unwashed")
        if d.get("status") == "do_not_contact" and st != "blocked":
            buckets["do_not_contact"].append(d)
            continue
        if normalise_au_phone(d.get("phone"))[0] is None:
            buckets["invalid_phone"].append(d)
            continue
        if st == "blocked":
            buckets["blocked"].append(d)
        elif st == "clean":
            washed = as_utc(dnc.get("washed_at"))
            exp = as_utc(dnc.get("expires_at")) or (
                washed + timedelta(days=WASH_VALID_DAYS) if washed else None)
            if exp and now < exp:
                buckets["clean_current"].append(d)
                expiries.append(exp)
            else:
                buckets["clean_expired"].append(d)
        else:
            buckets["unwashed"].append(d)

    earliest = min(expiries) if expiries else None

    print()
    print("=" * 72)
    print(f"  DNC WASH STATUS — {aest_str(now)}")
    print(f"  {DB_NAME}.{QUEUE_COLL}: {len(docs)} document(s)")
    print("=" * 72)
    print(f"  unwashed              {len(buckets['unwashed']):>6}   no s11(3) defence — not dialable")
    truly_dialable = sum(1 for d in buckets["clean_current"] if is_dialable(d, now)[0])
    print(f"  clean & CURRENT       {len(buckets['clean_current']):>6}   "
          f"of which DIALABLE: {truly_dialable}")
    if truly_dialable != len(buckets["clean_current"]):
        print(f"    ⚠ {len(buckets['clean_current']) - truly_dialable} carry a current wash "
              "but fail the gate (ID4ME advisory 'blocked', or no submission_id)")
    print(f"  clean but EXPIRED     {len(buckets['clean_expired']):>6}   NOT dialable — re-wash")
    print(f"  blocked (registered)  {len(buckets['blocked']):>6}   never dialable")
    print(f"  invalid phone format  {len(buckets['invalid_phone']):>6}   would waste a wash credit")
    print(f"  do_not_contact        {len(buckets['do_not_contact']):>6}   opted out / excluded")
    print("-" * 72)
    if earliest:
        days = (earliest - now).days
        print(f"  EARLIEST WASH EXPIRY  {aest_str(earliest, '%Y-%m-%d')}  (in {days} day(s))")
        print(f"  → re-export at latest  {aest_str(earliest - timedelta(days=REWASH_LEAD_DAYS), '%Y-%m-%d')}")
    else:
        print("  EARLIEST WASH EXPIRY  — (nothing currently washed)")
    due = sum(1 for d in docs if needs_wash(d, now))
    print(f"  due for export now    {due:>6}   (unwashed or expiring within {REWASH_LEAD_DAYS}d)")

    sample = (buckets["clean_expired"] or buckets["unwashed"])[:3]
    if sample:
        print("-" * 72)
        print("  examples (masked):")
        for d in sample:
            ok, why = is_dialable(d, now)
            print(f"    {mask(d.get('phone')):<14} {d.get('suburb','?'):<16} {why}")
    print("=" * 72)

    metrics = {k: len(v) for k, v in buckets.items()}
    metrics["dialable"] = truly_dialable
    metrics["due_for_export"] = due
    metrics["earliest_expiry"] = aest_str(earliest, "%Y-%m-%d") if earliest else None
    return metrics


# ---------------------------------------------------------------------------
# --assert-dialable
# ---------------------------------------------------------------------------

def cmd_assert_dialable(db, phone_raw: str) -> int:
    phone, why = normalise_au_phone(phone_raw)
    if not phone:
        print(f"NOT DIALABLE: {mask(phone_raw)} — invalid AU number ({why})")
        return 1
    docs = [d for d in _all_queue_docs(db)
            if normalise_au_phone(d.get("phone"))[0] == phone]
    if not docs:
        print(f"NOT DIALABLE: {mask(phone)} — not in {DB_NAME}.{QUEUE_COLL}. "
              "A number we have never washed carries no defence.")
        return 1
    # fail closed: every doc for this number must be dialable
    reasons = []
    for d in docs:
        ok, why = is_dialable(d)
        if not ok:
            reasons.append(why)
    if reasons:
        print(f"NOT DIALABLE: {mask(phone)} — {reasons[0]}")
        return 1
    _, why = is_dialable(docs[0])
    print(f"DIALABLE: {mask(phone)} — {why}")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Australian Do Not Call Register washing (DNCR Act 2006 s11(3)).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true",
                   help="build the CSV to upload manually at donotcall.gov.au")
    g.add_argument("--import", dest="import_file", metavar="FILE",
                   help="ingest ACMA's returned result file")
    g.add_argument("--status", action="store_true", help="counts + earliest expiry")
    g.add_argument("--assert-dialable", metavar="PHONE",
                   help="exit 0 only if that number is clean AND unexpired")
    ap.add_argument("--out", help="export: output CSV path")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="export: default output dir")
    ap.add_argument("--limit", type=int, help="export: cap the number of numbers")
    ap.add_argument("--submission-id", help="import: required; export: override the id")
    ap.add_argument("--heartbeat", action="store_true",
                    help="record the run to system_monitor.job_runs (use when run from cron)")
    args = ap.parse_args()

    set_env_from_file()
    db = _db()

    if args.assert_dialable:
        return cmd_assert_dialable(db, args.assert_dialable)

    if args.import_file and not args.submission_id:
        ap.error("--import requires --submission-id (the id printed by --export)")

    job = "dnc_wash_export" if args.export else (
        "dnc_wash_import" if args.import_file else "dnc_wash_status")
    # Heartbeat only when explicitly asked. Export and import are MANUAL (there is
    # no API at Type B), so self-registering them on the health board would create a
    # job that is permanently STALE and trains us to ignore the board. When --status
    # is put on cron, run it with --heartbeat and it self-registers weekly.
    record = None
    if args.heartbeat:
        try:
            record = _job_status()
        except Exception as e:
            print(f"(heartbeat unavailable: {e})")

    try:
        if args.export:
            metrics = cmd_export(db, args)
            detail = (f"{metrics.get('submitted', 0)} submitted, "
                      f"{metrics.get('rejected', 0)} rejected")
        elif args.import_file:
            metrics = cmd_import(db, args)
            detail = f"{metrics['clean']} clean / {metrics['blocked']} blocked"
        else:
            metrics = cmd_status(db, args)
            detail = (f"{metrics['clean_current']} dialable, "
                      f"{metrics['clean_expired']} expired, "
                      f"{metrics['unwashed']} unwashed")
    except Exception as e:
        if record:
            # Manual commands: heartbeat only when asked. NOTE no wash timestamp is
            # ever written on this path — cmd_import raises BEFORE any $set.
            record(job, "error", detail=f"{type(e).__name__}: {e}"[:500],
                   **({"cadence_hours": 24 * 7,
                       "title": "DNC Wash (Do Not Call Register)"} if args.status else {}))
        print(f"\nFAILED: {e}", file=sys.stderr)
        return 2

    if record:
        record(job, "success", detail=detail, metrics=metrics,
               **({"cadence_hours": 24 * 7,
                   "title": "DNC Wash (Do Not Call Register)"} if args.status else {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
