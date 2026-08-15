#!/usr/bin/env python3
"""
id4me_append_runner.py — append ID4ME contact data to a SMALL daily batch of ranked
call candidates, so build_call_list.py has phone numbers to work with.

  Gold_Coast.<suburb>  ──┐
  lead_worklist        ──┼─→ build_call_list.py --needs-id4me  (RANKING lives there)
                          │            │  ranked addresses with no ID4ME data
                          │            ▼
                          │   ┌──────────────────────────────┐
                          └───┤   THIS SCRIPT                │
                              │  40-60 addresses/day, wkdys  │
                              │  1 req/sec, sequential       │
                              └───────────┬──────────────────┘
                                          │ id4me_to_mongo.shape_for_mongo (REUSED)
                                          ▼
                              Gold_Coast.<suburb>.ID4ME_Contact_Data
                              system_monitor.id4me_append_log  (per-address ledger)

Usage
-----
  python3 id4me_append_runner.py --run --dry-run          # list what WOULD be appended
  python3 id4me_append_runner.py --run                    # the real daily batch
  python3 id4me_append_runner.py --run --limit 5          # explicit small batch
  python3 id4me_append_runner.py --run --force            # override the weekend guard
  python3 id4me_append_runner.py --backlog                # counts only, no ID4ME calls
  python3 id4me_append_runner.py --status                 # subscription health, no quota

Intended schedule — NOT INSTALLED. Will decides when this starts (the ToS/consent
question in 00_SCOPING.md §9.5 is open). Weekdays only is enforced IN CODE, so the
cron line fires every morning and the guard decides — that way a weekend still
records a heartbeat and the health board never shows a false STALE:

    # Direct calls — ID4ME daily contact append (40-60 addresses; weekdays only,
    # enforced by the script's own guard, which heartbeats "weekend" on Sat/Sun)
    # 30 9 * * * cd /home/fields/Fields_Orchestrator && /home/fields/venv/bin/python3 20_Direct_Phone_Calls/scripts/id4me_append_runner.py --run >> logs/id4me_append.log 2>&1

    # If you would rather cron itself skip the weekend, use `30 9 * * 1-5` instead —
    # STALE_HOURS below is already wide enough to cover the Fri→Mon gap either way.

⚠ ToS / consent gate (00_SCOPING.md §9.5)
-----------------------------------------
`can_use_api` is FALSE on our subscription and the ID4ME terms forbid "automated
programs or other data extraction systems"; the cap is 800 searches/day. This
script exists, is verified, and is deliberately NOT scheduled. Will is resolving
the licensing question with ID4ME (the licensed API product is ~$155/mo) — running
it before that is a terms breach at any pace.

What this script deliberately does NOT do
-----------------------------------------
* It does NOT rank. `build_call_list.do_needs_id4me` owns the ranking and every
  legal exclusion (POA Reg s21(3) listing-expiry, currently-listed, investor,
  outside-core-suburb, test). Duplicating it here would let the two drift.
* It does NOT dial, wash DNC, or write the Sheet.
* It does NOT reimplement the Mongo write. `id4me_to_mongo.shape_for_mongo` /
  `.ROOT_FIELD` are imported, so the document shape has exactly one definition.

PRIVACY (CLAUDE.md §9 of the brief, Privacy Act APPs)
-----------------------------------------------------
The payload holds names, dates of birth, phone numbers and email addresses of real
people, and this script's stdout is redirected to a log file on disk. Nothing here
ever prints a name, number, DOB or email — only counts. `--dry-run` prints
ADDRESSES (that is its whole purpose) and nothing else.

Rule 7 / 7b — which zero is which
---------------------------------
  weekend                      -> SUCCESS, detail "weekend"  (no run scheduled)
  backlog drained / nothing eligible
                               -> SUCCESS  (the queue is empty, not broken)
  attempted N, appended 0      -> RAISE    (upstream broken)
  resolve rate collapses well below the measured ~97% baseline
                               -> RAISE    (kicked session, or a changed endpoint)
  SessionError / control-address failure / expired subscription
                               -> RAISE before or during, immediately

⚠ There is no watermark and no cursor. The per-address ledger in
`system_monitor.id4me_append_log` is written ONLY after that address was actually
attempted, so a failed run can never mark work as done (Rule 7b.2).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from argparse import Namespace
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_ID4ME = os.path.join(_REPO, "12_Marketing", "00_ID4ME")
for _p in (_REPO, os.path.join(_REPO, "scripts"), _HERE, _ID4ME):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AEST = ZoneInfo("Australia/Brisbane")

JOB_NAME = "id4me_append"
JOB_TITLE = "ID4ME daily contact append"
LOG_DB = "system_monitor"
LOG_COLL = "id4me_append_log"

# Cadence is daily, but the job legitimately does not RUN on Sat/Sun. If cron is set
# to `1-5`, the gap from Friday 09:30 to Monday 09:30 is 72h — past the default
# staleness threshold (cadence x 1.5 = 36h), which would paint a correctly-behaving
# job red twice every weekend and train us to ignore the board. 80h covers the gap
# with slack and still catches a genuinely dead job by Tuesday.
STALE_HOURS = 80

# Will's instruction: 40-60 addresses per day, weekdays only.
DEFAULT_BATCH = 50
BATCH_MIN, BATCH_MAX = 40, 60

# README, "Account status and legal position": "Be a good citizen. Batches pace at
# 1s per address (--delay). Do not remove it." A FIXED, respectful rate — no jitter,
# no simulated breaks. We are not disguising the automation; we are rate-limiting it.
DELAY_FLOOR = 1.0

# The one address confirmed to resolve (12 people, 47 raw records). Probed FIRST so a
# dead session is caught before it burns quota — see fix-history 2026-08-13
# [ID4ME-KICKED-SESSION-SILENT-ZERO] and id4me_coverage_sample.py, which does the same.
CONTROL_ADDRESS = "20 Chantilly Place, Robina, QLD 4226"

# An address ID4ME has never heard of is a PERMANENT miss, not a transient one.
# Without a backoff the daily batch silently refills with the same failures until
# nothing new is ever appended — the batch would look busy and achieve nothing.
NOT_FOUND_BACKOFF_DAYS = 90
NO_RESULTS_BACKOFF_DAYS = 90
ERROR_BACKOFF_DAYS = 1          # transient: retry tomorrow, but not twice today

# Measured baseline: 97% of addresses resolve (00_SCOPING.md §1 funnel math).
# Anything under this floor over a meaningful batch is a broken session or a changed
# endpoint being reported as a finding. Deliberately generous — it is a tripwire for
# collapse, not a quality bar.
RESOLVE_RATE_FLOOR = 0.60
RESOLVE_RATE_MIN_N = 10
# ...and the same tripwire at the FRONT of the run, so we abort after 10 wasted
# lookups rather than 60.
EARLY_ABORT_AFTER = 10


class SessionKicked(RuntimeError):
    """ID4ME invalidated our session mid-run. The whole run must stop."""


class SubscriptionProblem(RuntimeError):
    """The account cannot legitimately serve lookups right now."""


# ─────────────────────────────────────────────────────────────────────────────
# env / small helpers
# ─────────────────────────────────────────────────────────────────────────────
def set_env_from_file():
    """Load our own environment (Rule 7 checklist item 3). Never trust the cron line
    to have exported anything — a missing `set -a` leaves shared.db connecting via
    config/settings.yaml while every credential-dependent call fails."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"), override=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_aest_str() -> str:
    return datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")


def is_weekend(when: datetime | None = None) -> bool:
    """Saturday or Sunday in Australia/Brisbane. AEST has no DST, but zoneinfo is
    used rather than a fixed offset so the answer stays right if that ever changes."""
    return (when or datetime.now(AEST)).weekday() >= 5


def days_since(dt) -> float | None:
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now_utc() - dt).total_seconds() / 86400.0


# ─────────────────────────────────────────────────────────────────────────────
# the ledger — system_monitor.id4me_append_log
# ─────────────────────────────────────────────────────────────────────────────
def load_ledger(sm_db, slugs: list[str]) -> dict[str, dict]:
    if not slugs:
        return {}
    cur = sm_db[LOG_COLL].find({"_id": {"$in": slugs}})
    return {d["_id"]: d for d in cur}


def record_attempt(sm_db, slug: str, address: str, suburb: str, result: dict,
                   payload: dict | None, written: bool) -> None:
    """One ledger row per address, written ONLY after a real attempt.

    Holds no personal data — address, suburb, status and counts. `people_count` and
    `has_callable_phone` are the two numbers that make "we looked and there is
    nobody" distinguishable from "we never looked" without reopening the payload.
    """
    doc = {
        "address": address,
        "suburb": suburb,
        "attempted_at": now_utc(),
        "status": result.get("status"),
        "people_count": len(result.get("people") or []),
        "has_callable_phone": bool((payload or {}).get("ID4ME_Has_Callable_Phone")),
        "error": (result.get("error") or "")[:300] or None,
        "written_to_property": bool(written),
    }
    sm_db[LOG_COLL].update_one(
        {"_id": slug},
        {"$set": doc,
         "$inc": {"attempts": 1},
         "$setOnInsert": {"first_attempted_at": now_utc()}},
        upsert=True)


def ledger_skip_reason(entry: dict | None, refresh_older_than: int | None) -> str | None:
    """Why this address should NOT be attempted today. None = attempt it.

    Idempotence lives here: a successful append is never repeated unless
    --refresh-older-than asks for it, and a permanent miss backs off instead of
    being retried every single day forever.
    """
    if not entry:
        return None
    age = days_since(entry.get("attempted_at"))
    status = entry.get("status")

    if status == "ok":
        if refresh_older_than is None:
            return "already appended (ok)"
        if age is not None and age < refresh_older_than:
            return f"appended {age:.0f}d ago (< --refresh-older-than {refresh_older_than})"
        return None

    if age is None:
        return None
    if status == "address_not_found" and age < NOT_FOUND_BACKOFF_DAYS:
        return f"address_not_found {age:.0f}d ago (backoff {NOT_FOUND_BACKOFF_DAYS}d)"
    if status == "no_results" and age < NO_RESULTS_BACKOFF_DAYS:
        return f"no_results {age:.0f}d ago (backoff {NO_RESULTS_BACKOFF_DAYS}d)"
    if status in ("error", "auth_error") and age < ERROR_BACKOFF_DAYS:
        return f"{status} {age:.1f}d ago (backoff {ERROR_BACKOFF_DAYS}d)"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# candidate selection — ranking is IMPORTED, never duplicated
# ─────────────────────────────────────────────────────────────────────────────
def ranked_candidates(gc_db, sm_db, suburb: str | None, quiet: bool = False) -> list[dict]:
    """The full ranked backlog, straight out of build_call_list.

    `do_needs_id4me` is the ranking. Importing it (rather than shelling out and
    parsing) means a change to the score, or to any of the legal exclusions it
    applies, reaches this job automatically.
    """
    import build_call_list as bcl
    args = Namespace(suburb=suburb, limit=0, out=None)
    if quiet:
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            return bcl.do_needs_id4me(gc_db, sm_db, args)
    return bcl.do_needs_id4me(gc_db, sm_db, args)


def already_appended(cand: dict) -> bool:
    """The property document itself already carries a good pull.

    Belt and braces: `do_needs_id4me` should not emit these, but the ledger and the
    document can disagree (a hand-run of id4me_to_mongo.py writes one and not the
    other), and re-spending quota on data we already hold is the failure mode that
    costs money silently.
    """
    doc = cand.get("_gc_doc") or {}
    return (doc.get("ID4ME_Contact_Data") or {}).get("ID4ME_Status") == "ok"


def select_batch(gc_db, sm_db, suburb: str | None, batch: int,
                 refresh_older_than: int | None, quiet: bool = False):
    """-> (batch, eligible_total, backlog_total, skip_counts)"""
    import build_call_list as bcl
    pending = ranked_candidates(gc_db, sm_db, suburb, quiet=quiet)
    backlog_total = len(pending)

    slugs = [bcl.address_slug(c["address"]) for c in pending]
    ledger = load_ledger(sm_db, slugs)

    skips = Counter()
    eligible = []
    for cand, slug in zip(pending, slugs):
        if already_appended(cand):
            skips["property doc already has ID4ME_Status=ok"] += 1
            continue
        reason = ledger_skip_reason(ledger.get(slug), refresh_older_than)
        if reason:
            skips[reason.split(" (")[0]] += 1
            continue
        cand["_slug"] = slug
        eligible.append(cand)

    return eligible[:batch], len(eligible), backlog_total, skips


# ─────────────────────────────────────────────────────────────────────────────
# guards
# ─────────────────────────────────────────────────────────────────────────────
def check_subscription(client) -> dict:
    """Fail LOUDLY on an expired or blocked account rather than burning a batch of
    identical failures. Costs no search quota — /account/profile is free.

    The subscription expires 2026-08-16 and auto-renews; a renewal that silently
    does not happen must be an error, not a day of zeros."""
    profile = client.profile()
    meta = profile.get("user_metadata") or {}
    status = meta.get("subscription_status")
    expiry_raw = str(meta.get("financial_expiry") or "")

    if profile.get("blocked") is True:
        raise SubscriptionProblem("ID4ME account is BLOCKED — no lookups attempted.")
    if status and status != "subscribed":
        raise SubscriptionProblem(
            f"ID4ME subscription_status is {status!r}, not 'subscribed' — no lookups attempted.")

    days_left = None
    if expiry_raw:
        try:
            exp = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
            days_left = (exp - now_utc()).total_seconds() / 86400.0
        except ValueError:
            days_left = None
        if days_left is not None and days_left <= 0:
            raise SubscriptionProblem(
                f"ID4ME subscription EXPIRED at {expiry_raw} — it should have auto-renewed. "
                f"Raising rather than recording a batch of silent zeros.")

    return {"subscription_status": status, "expiry": expiry_raw,
            "days_left": None if days_left is None else round(days_left, 2),
            "blocked": profile.get("blocked")}


def _session_error(result: dict) -> str | None:
    """Detect a kicked session inside a lookup() result.

    ⚠ `api.Id4meClient._request` raises SessionError, but `lookup.lookup` catches
    bare `Exception` and folds it into `result["status"]="error"` with the class name
    in the text — so the exception NEVER reaches this caller. Catching SessionError
    around the call is therefore necessary but NOT sufficient; this string check is
    what actually fires. Both are wired below.

    A session kick is also possible during the compliance sub-call, where lookup()
    keeps status "ok" and stores the message in `error`. That result's contact data
    is genuine and is kept — but the run still stops, because every subsequent
    address would return address_not_found and look like real absence.
    """
    text = str(result.get("error") or "")
    return text if "SessionError" in text else None


def probe_control(id4me_lookup, client) -> dict:
    """Prove the lookup path works on a known-good address BEFORE spending quota.

    A dead session makes EVERY address return `address_not_found`, which is
    indistinguishable from genuinely absent data — an unguarded batch reports 0%
    coverage as though it were a finding. Same guard as id4me_coverage_sample.py.
    """
    result = id4me_lookup.lookup(client, CONTROL_ADDRESS, compliance=False)
    if kicked := _session_error(result):
        raise SessionKicked(f"control probe: {kicked}")
    if result["status"] != "ok":
        raise RuntimeError(
            f"ABORT: control address returned {result['status']} ({result.get('error')}). "
            f"The lookup path is broken — every address in this batch would report "
            f"'not found' and the run would look like a finding. Nothing appended.")
    return {"people": len(result["people"])}


# ─────────────────────────────────────────────────────────────────────────────
# the run
# ─────────────────────────────────────────────────────────────────────────────
def append_one(gc_db, sm_db, id4me_lookup, id4me_to_mongo, client, cand) -> dict:
    """One address: look it up, write it if good, ledger it either way."""
    address = cand["address"]
    suburb = cand.get("suburb")
    slug = cand["_slug"]

    try:
        result = id4me_lookup.lookup(client, address, compliance=True)
    except Exception as exc:                       # includes api.SessionError
        if type(exc).__name__ == "SessionError":
            raise SessionKicked(str(exc)) from exc
        raise

    if kicked := _session_error(result):
        # Do not ledger a kicked-session result as an address outcome: it is a fact
        # about OUR session, not about this address, and writing it would poison the
        # backoff with a false permanent miss.
        if result["status"] != "ok":
            raise SessionKicked(kicked)
        # status ok: the data IS real. Write it, ledger it, then stop the run.

    payload, written = None, False
    if result["status"] == "ok":
        payload = id4me_to_mongo.shape_for_mongo(result)
        doc = cand.get("_gc_doc")
        coll_name = suburb
        if not doc:
            coll_name, doc = id4me_to_mongo.find_property(gc_db, address, suburb)
        if doc:
            gc_db[coll_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {id4me_to_mongo.ROOT_FIELD: payload}})
            written = True
        else:
            # A miss must not overwrite a good earlier pull with an empty one, and a
            # result we cannot attach to a property is not an append.
            result = {**result, "status": "error",
                      "error": "no Gold_Coast document to attach the payload to"}

    record_attempt(sm_db, slug, address, suburb, result, payload, written)

    if kicked and result["status"] == "ok":
        raise SessionKicked(f"session died during compliance lookup: {kicked}")

    return {"status": result["status"],
            "people": len(result.get("people") or []),
            "callable": bool((payload or {}).get("ID4ME_Has_Callable_Phone")),
            "written": written}


def do_run(gc_db, sm_db, args, beat) -> None:
    import build_call_list as bcl  # noqa: F401  (path setup + shared helpers)

    # ── weekend guard ────────────────────────────────────────────────────────
    # Will: weekdays only, never Saturday or Sunday. A weekend is a SUCCESSFUL
    # non-run — the job did exactly what it is meant to do — so it records a
    # heartbeat and exits 0. Treating it as staleness would make the health board
    # cry wolf twice a week and train us to ignore it.
    if is_weekend() and not args.force:
        beat.detail = "weekend — no run scheduled"
        beat.metrics = {"attempted": 0, "ok": 0, "not_found": 0, "errors": 0,
                        "people_total": 0, "with_callable_phone": 0,
                        "backlog_remaining": None, "skipped_weekend": True}
        print(f"\nID4ME append — {now_aest_str()}")
        print("  weekend — no run scheduled (weekdays only; --force to override).")
        return

    batch_size = args.limit if args.limit is not None else max(
        BATCH_MIN, min(BATCH_MAX, DEFAULT_BATCH))
    if args.limit is None and not (BATCH_MIN <= batch_size <= BATCH_MAX):
        raise RuntimeError(f"batch size {batch_size} outside the agreed {BATCH_MIN}-{BATCH_MAX}")
    delay = max(DELAY_FLOOR, args.delay)          # floor is not overridable downward

    batch, eligible_total, backlog_total, skips = select_batch(
        gc_db, sm_db, args.suburb, batch_size, args.refresh_older_than,
        quiet=not args.verbose)

    print(f"\nID4ME append — {now_aest_str()}{'  [DRY RUN]' if args.dry_run else ''}")
    print(f"  backlog (ranked, unappended) : {backlog_total}")
    print(f"  eligible today               : {eligible_total}")
    print(f"  batch size                   : {len(batch)} (requested {batch_size}, "
          f"{'explicit --limit' if args.limit is not None else f'default, clamped {BATCH_MIN}-{BATCH_MAX}'})")
    print(f"  pacing                       : {delay:.1f}s/address, sequential, fixed")
    if skips:
        print("  not attempted today (idempotence + backoff):")
        for reason, n in skips.most_common():
            print(f"    {n:>6}  {reason}")

    # ── the backlog is drained ───────────────────────────────────────────────
    # An empty queue is SUCCESS (Rule 7b.1). It is distinguishable from "could not
    # do the work" because backlog_total and eligible_total are both reported.
    if not batch:
        beat.detail = (f"nothing eligible to append "
                       f"(backlog {backlog_total}, all skipped or drained)")
        beat.metrics = {"attempted": 0, "ok": 0, "not_found": 0, "errors": 0,
                        "people_total": 0, "with_callable_phone": 0,
                        "backlog_remaining": backlog_total, "eligible": 0}
        print("\n  Nothing eligible to append today. This is an empty queue, not a failure.")
        return

    if args.dry_run:
        print(f"\n  Would append, in rank order (no ID4ME call made):")
        for i, c in enumerate(batch, 1):
            print(f"    {i:>3}. {c['address']}  [{bcl.SUBURB_LABEL.get(c['suburb'], c['suburb'])}]")
        print(f"\n  DRY RUN — no ID4ME call, no Mongo write, NO HEARTBEAT recorded.")
        print(f"  (a dry run must never make the health board look like the job ran)")
        return

    # ── live guards, cheapest first ──────────────────────────────────────────
    import id4me_to_mongo                       # noqa: E402  (also puts tool/ on sys.path)
    import lookup as id4me_lookup               # noqa: E402
    from api import AuthError, Id4meClient      # noqa: E402

    try:
        client = Id4meClient()
    except AuthError as exc:
        raise RuntimeError(f"ID4ME authentication failed: {exc}") from exc

    sub = check_subscription(client)            # free: no search quota
    print(f"\n  subscription : {sub['subscription_status']}, expires {sub['expiry']} "
          f"({sub['days_left']} days)")
    if sub["days_left"] is not None and sub["days_left"] <= 14:
        print(f"  ⚠ subscription expires in {sub['days_left']:.1f} day(s) — it is set to "
              f"auto-renew; if it does not, this job will RAISE rather than record zeros.")

    ctrl = probe_control(id4me_lookup, client)  # costs 1 search
    print(f"  control      : OK, {ctrl['people']} people at the known-good address")

    # ── the batch ────────────────────────────────────────────────────────────
    counts = Counter()
    people_total = 0
    callable_total = 0
    attempted = 0
    try:
        for i, cand in enumerate(batch, 1):
            time.sleep(delay)                   # before, not after: the control probe counts too
            out = append_one(gc_db, sm_db, id4me_lookup, id4me_to_mongo, client, cand)
            attempted += 1
            counts[out["status"]] += 1
            people_total += out["people"]
            callable_total += int(out["callable"])

            if i % 10 == 0 or i == len(batch):
                print(f"    [{i}/{len(batch)}] ok {counts['ok']} | "
                      f"not_found {counts['address_not_found']} | "
                      f"with phone {callable_total}", flush=True)

            # Front-of-run tripwire: 10 consecutive misses is a broken session or a
            # changed endpoint, not ten unlucky addresses. Stop at 10 wasted lookups
            # rather than 60 — and RAISE, so it is never filed as "0% coverage".
            if attempted >= EARLY_ABORT_AFTER and counts["ok"] == 0:
                raise RuntimeError(
                    f"ABORT: {attempted}/{attempted} addresses unresolved after the control "
                    f"address passed. That is a session or endpoint failure, not absent data.")
    finally:
        # Whatever we managed is recorded even on the abort path — job_run persists
        # metrics on the error branch too.
        beat.metrics = {
            "attempted": attempted,
            "ok": counts["ok"],
            "not_found": counts["address_not_found"],
            "errors": attempted - counts["ok"] - counts["address_not_found"],
            "people_total": people_total,
            "with_callable_phone": callable_total,
            "backlog_remaining": max(0, backlog_total - counts["ok"]),
            "eligible": eligible_total,
            "batch_size": len(batch),
            "delay_s": delay,
        }

    ok = counts["ok"]
    not_found = counts["address_not_found"]
    errors = attempted - ok - not_found
    remaining = max(0, backlog_total - ok)
    rate = ok / attempted if attempted else 0.0

    # ── Rule 7b: assert an outcome ───────────────────────────────────────────
    if attempted > 0 and ok == 0:
        raise RuntimeError(
            f"attempted {attempted} addresses and appended 0 — the control address "
            f"resolved, so this is not an empty upstream. Nothing was appended.")
    if attempted >= RESOLVE_RATE_MIN_N and rate < RESOLVE_RATE_FLOOR:
        raise RuntimeError(
            f"resolve rate {rate:.0%} over {attempted} addresses, far below the measured "
            f"~97% baseline (floor {RESOLVE_RATE_FLOOR:.0%}). Likeliest causes: our session "
            f"was kicked mid-run, or the endpoint changed. Treating this as a finding would "
            f"publish a fake coverage number. {ok} address(es) WERE appended and are kept.")

    # weekdays only, so calendar days ≈ weekdays × 7/5
    weekdays_to_drain = math.ceil(remaining / len(batch)) if remaining and batch else 0
    calendar_days = math.ceil(weekdays_to_drain * 7 / 5)

    beat.detail = (f"{ok}/{attempted} appended, {callable_total} with a callable phone; "
                   f"{remaining} left (~{weekdays_to_drain} weekdays)")

    print(f"\n  attempted            : {attempted}")
    print(f"  appended (ok)        : {ok}  ({rate:.0%}; measured baseline ~97%)")
    print(f"  address_not_found    : {not_found}  (backed off {NOT_FOUND_BACKOFF_DAYS}d — "
          f"a permanent miss must not refill tomorrow's batch)")
    print(f"  errors               : {errors}")
    print(f"  people found         : {people_total}")
    print(f"  with callable phone  : {callable_total}  "
          f"(⚠ ID4ME's DNC flag is advisory only — dnc_wash.py decides, ACMA IS 157)")
    print(f"  backlog remaining    : {remaining}")
    if remaining:
        print(f"  projected drain      : ~{weekdays_to_drain} weekday run(s) at {len(batch)}/day "
              f"≈ {calendar_days} calendar days")
    else:
        print(f"  projected drain      : backlog drained")


# ─────────────────────────────────────────────────────────────────────────────
def do_backlog(gc_db, sm_db, args) -> None:
    """Counts only — never calls ID4ME."""
    batch, eligible_total, backlog_total, skips = select_batch(
        gc_db, sm_db, args.suburb, DEFAULT_BATCH, args.refresh_older_than,
        quiet=not args.verbose)
    ledger = sm_db[LOG_COLL]
    print(f"\nID4ME append backlog — {now_aest_str()}")
    print(f"  ranked, unappended   : {backlog_total}")
    print(f"  eligible today       : {eligible_total}")
    for reason, n in skips.most_common():
        print(f"    {n:>6}  {reason}")
    print(f"\n  ledger ({LOG_DB}.{LOG_COLL}):")
    total = ledger.count_documents({})
    if not total:
        print("       0  no attempt has ever been recorded")
    for row in ledger.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}},
                                 {"$sort": {"n": -1}}]):
        print(f"    {row['n']:>6}  {row['_id']}")
    if eligible_total:
        wd = math.ceil(eligible_total / DEFAULT_BATCH)
        print(f"\n  projected drain      : ~{wd} weekday run(s) at {DEFAULT_BATCH}/day "
              f"≈ {math.ceil(wd * 7 / 5)} calendar days")


def do_status() -> int:
    """Subscription health. Costs no search quota."""
    import id4me_to_mongo   # noqa: F401  (puts tool/ on sys.path)
    from api import AuthError, Id4meClient
    try:
        sub = check_subscription(Id4meClient())
    except AuthError as exc:
        print(f"ID4ME authentication failed: {exc}")
        return 2
    for k, v in sub.items():
        print(f"  {k:<20}: {v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="append today's batch")
    ap.add_argument("--backlog", action="store_true",
                    help="counts and ledger composition only — never calls ID4ME")
    ap.add_argument("--status", action="store_true",
                    help="ID4ME subscription health (no search quota), then exit")
    ap.add_argument("--limit", type=int, default=None,
                    help=f"explicit batch size. Omit for the default {DEFAULT_BATCH} "
                         f"(clamped to {BATCH_MIN}-{BATCH_MAX}, Will's instruction)")
    ap.add_argument("--delay", type=float, default=DELAY_FLOOR,
                    help=f"seconds between addresses. Floor {DELAY_FLOOR} and it cannot be "
                         f"set lower — the delivered tool documents 1s/address as the "
                         f"good-citizen rate. Fixed, never randomised.")
    ap.add_argument("--suburb", choices=["robina", "varsity_lakes", "burleigh_waters"])
    ap.add_argument("--force", action="store_true",
                    help="run on a Saturday or Sunday (manual/testing only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list exactly which addresses WOULD be appended, in order. "
                         "No ID4ME call, no write, no heartbeat.")
    ap.add_argument("--refresh-older-than", type=int, metavar="DAYS", default=None,
                    help="re-append addresses whose successful pull is older than DAYS. "
                         "Omit and a successful append is NEVER repeated.")
    ap.add_argument("--verbose", action="store_true",
                    help="show build_call_list's own exclusion report")
    args = ap.parse_args()

    if not (args.run or args.backlog or args.status):
        ap.error("one of --run / --backlog / --status is required")
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be at least 1")

    set_env_from_file()
    from shared.db import get_client, get_gold_coast_db
    from job_status import job_run

    if args.status:
        return do_status()

    mongo = get_client()
    gc_db = get_gold_coast_db()
    sm_db = mongo[LOG_DB]

    if args.backlog:
        do_backlog(gc_db, sm_db, args)
        return 0

    if args.dry_run:
        # No heartbeat on a dry run: recording success would make the health board
        # show a job that appended nothing as a healthy daily run.
        class _NullBeat:
            detail = ""
            metrics: dict = {}
        do_run(gc_db, sm_db, args, _NullBeat())
        return 0

    with job_run(JOB_NAME, cadence_hours=24, title=JOB_TITLE,
                 stale_hours=STALE_HOURS) as beat:
        do_run(gc_db, sm_db, args, beat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
