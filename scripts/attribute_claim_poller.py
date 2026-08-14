#!/usr/bin/env python3
"""
attribute_claim_poller.py — run a PRIVATE what-if valuation from attributes a
reader corrected on the V4 /off-market/:slug page.

WHAT IT DOES
    1. claim a pending doc from system_monitor.attribute_claims
    2. resolve slug -> Gold_Coast.<suburb> property document
    3. inject the reader's corrected attributes into that document IN MEMORY
    4. call precompute_property_valuation on the mutated copy
    5. write the result back onto THE CLAIM DOCUMENT

⚠ STEP 5 IS THE WHOLE POINT. This script must never write `valuation_data` on a
property document. The V4 loader renders that field on every SSR request
(off-market.$slug.tsx:582), so writing there would publish an unverified,
reader-supplied figure onto a public, indexed page — about a home the submitter
has not proved is theirs. The page states a MEASURED error rate beside every
figure it shows, and that error rate was measured against our own scraped and
enriched inputs; it does not transfer to a number typed into a form. A corrected
figure becomes publishable only after a human sets `verified: true`, and
publishing it is deliberately NOT automated here.

The injection points are the TOP of each resolver's priority chain, so the
reader's figure wins without touching the resolvers themselves:
    floor area -> internal_living_area_sqm   (precompute_valuations.py:2560)
    land size  -> lot_size_sqm               (precompute_valuations.py:2621)
    room counts-> top-level bedrooms/bathrooms/car_spaces

⚠ Bounds are enforced at the EDGE (offmarket-attribute-claim.mjs) and again
here. The endpoint can be called directly, so a poller that trusted its input
would be the actual attack surface, not the form.

Run as a service: fields-attribute-claim-poller
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv

# Load our own environment rather than trusting the caller — a unit file missing
# `set -a` exports nothing, and pymongo would still connect via settings.yaml,
# so the job would look healthy while credential-dependent calls failed. Rule 7.
load_dotenv(REPO_ROOT / ".env")

from shared.db import get_client  # noqa: E402
from scripts.job_status import job_run  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ⚠ A READER IS WATCHING A SPINNER. This is not a background queue — someone is
# sitting on the page waiting for the answer, so the interval is the floor on
# how fast they can possibly get it. 15s here plus a 145s cold cache build was
# measured at ~160s end to end on 2026-08-14 and people leave long before that.
POLL_INTERVAL = 2
STALE_CLAIM_SECONDS = 600
# Comfortably inside the 24h cadence x1.5 stale threshold, so an idle poller
# reads OK on the health board rather than STALE. See the note in main().
IDLE_BEAT_SECONDS = 6 * 3600
SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# Mirrors BOUNDS in offmarket-attribute-claim.mjs. 40 is MIN_FLOOR_AREA from
# precompute_valuations.py:2544 — below it the engine discards the value and we
# would compute a "corrected" valuation that silently ignored the correction.
BOUNDS = {
    "floor_area_sqm": (40, 800),
    "land_size_sqm": (50, 5000),
    "bedrooms": (1, 10),
    "bathrooms": (1, 10),
    "car_spaces": (0, 10),
}

# Where each corrected attribute must be written so it wins its resolver.
INJECT_AT = {
    "floor_area_sqm": "internal_living_area_sqm",
    "land_size_sqm": "lot_size_sqm",
    "bedrooms": "bedrooms",
    "bathrooms": "bathrooms",
    "car_spaces": "car_spaces",
}

# The shared comparable caches cost 25-130s to build and change only when the
# nightly sold data lands. Rebuilding them per claim would make a reader wait
# two minutes for a 200ms computation.
_CACHE = {"built_at": None, "payload": None}
CACHE_TTL_SECONDS = 6 * 3600


def _caches(pv, client):
    """
    ⚠ NEVER CALL THIS ON THE CLAIM PATH. Building the comparable caches was
    measured at **145 seconds**, and lazily building them meant the first reader
    to click paid for all of it while staring at a spinner. It is now called
    once at startup and again from idle ticks (`_warm_caches`), so a claim only
    ever reads an already-built payload.

    Stale-but-present beats fresh-but-slow here: the sold set changes nightly, so
    a payload a few hours past its TTL is materially identical, while a rebuild
    on the claim path is a reader lost.
    """
    now = time.time()
    if _CACHE["payload"] and now - _CACHE["built_at"] < CACHE_TTL_SECONDS:
        return _CACHE["payload"]
    logger.info("Building shared comparable caches …")
    t0 = time.time()
    sold = pv._load_sold_comparables(client)
    keys = list(sold.keys())
    payload = (
        sold,
        pv._preload_gc_coordinates(client, keys),
        pv._preload_gc_timelines(client, keys),
    )
    mc = pv._build_suburb_median_cache(sold)
    payload = payload + (mc, pv._build_street_premium_cache(sold, mc))
    _CACHE["payload"] = payload
    _CACHE["built_at"] = now
    logger.info("  caches ready in %.0fs", time.time() - t0)
    return payload


def _notify(claim, doc, provisional, suburb):
    """
    Tell Will a real person just corrected a record.

    Best-effort and deliberately non-fatal: a Telegram outage must never fail a
    claim the reader completed successfully. Errors are logged, not raised.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        import requests
        attrs = ", ".join(f"{k.replace('_sqm','').replace('_',' ')} {v}"
                          for k, v in (claim.get("attributes") or {}).items())
        if provisional.get("method") == "engine":
            outcome = (f"${provisional['low']:,.0f} – ${provisional['high']:,.0f} "
                       f"({provisional.get('n_comps')} comps)")
        else:
            outcome = f"still declined ({provisional.get('decline_reason')})"
        kind = "typical figures" if claim.get("assumed") else "their own figures"
        lines = [
            "🏠 *Someone corrected a record*",
            f"*{doc.get('address', claim['slug'])}*",
            f"Gave us: {attrs}  _({kind})_",
            f"Result: {outcome}",
            "",
            f"Private to them — not published. Review: `{claim['_id']}`",
            f"https://fieldsestate.com.au/off-market/{claim['slug']}",
        ]
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as exc:
        logger.error("Telegram notify failed (claim still succeeded): %s", exc)


def _find_property(gc, slug):
    """slug -> (suburb, doc). Mirrors db.server.ts findPropertyById."""
    for suburb in SUBURBS:
        doc = gc[suburb].find_one({"url_slug": slug})
        if doc:
            return suburb, doc
    return None, None


def _validate(attributes):
    """Re-check at the poller. The endpoint is reachable without the form."""
    clean = {}
    for field, value in (attributes or {}).items():
        if field not in BOUNDS:
            continue
        try:
            n = float(value)
        except (TypeError, ValueError):
            return None, f"{field} is not a number"
        lo, hi = BOUNDS[field]
        if not (lo <= n <= hi):
            return None, f"{field}={n:g} is outside {lo}-{hi}"
        clean[field] = int(round(n))
    if not clean:
        return None, "no usable attributes"
    return clean, None


def process_one(client, pv, claim):
    gc = client["Gold_Coast"]
    claims = client["system_monitor"]["attribute_claims"]

    def fail(reason):
        logger.warning("Claim %s failed: %s", claim["_id"], reason)
        claims.update_one(
            {"_id": claim["_id"]},
            {"$set": {"status": "error", "error": reason,
                      "finished_at": datetime.now(timezone.utc)}},
        )
        return False

    attributes, err = _validate(claim.get("attributes"))
    if err:
        return fail(f"rejected: {err}")

    suburb, doc = _find_property(gc, claim["slug"])
    if not doc:
        return fail(f"no property for slug {claim['slug']}")

    # ⚠ The engine resolves its comparable pool from `_collection` or `suburb`,
    # and `suburb` is NULL on every off-market doc. Without this the pool is
    # empty and every valuation returns insufficient_data.
    doc["_collection"] = suburb
    for field, value in attributes.items():
        doc[INJECT_AT[field]] = value

    # Warmed at startup and on idle ticks. Falls back to a build only if the
    # warm-up itself failed, which would otherwise mean returning an error to a
    # reader who did nothing wrong.
    sold, coords, timelines, mc, sc = _CACHE["payload"] or _caches(pv, client)
    try:
        vd = pv.precompute_property_valuation(
            gc, doc, gc[suburb], sold, coords, timelines, mc, sc)
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc}")

    if not vd:
        return fail("engine returned nothing")

    conf = (vd.get("confidence") or {}) if isinstance(vd, dict) else {}
    rng = conf.get("range") or {}
    point = conf.get("reconciled_valuation")
    exclusion = (vd.get("summary") or {}).get("exclusion_reason")

    provisional = {
        "low": rng.get("low"),
        "high": rng.get("high"),
        "point": point,
        "n_comps": conf.get("n_total"),
        "method": "engine" if (rng.get("low") and rng.get("high") and point) else "declined",
        "decline_reason": None if point else (exclusion or "no_engine_figure"),
        "computed_at": datetime.now(timezone.utc),
        # The claim is what produced this. Recorded so a reviewer never has to
        # guess which correction the figure was built on.
        "inputs": attributes,
    }

    claims.update_one(
        {"_id": claim["_id"]},
        {"$set": {"status": "computed", "provisional": provisional,
                  "suburb": suburb, "property_id": doc["_id"], "error": None,
                  "finished_at": datetime.now(timezone.utc)}},
    )
    logger.info("Claim %s computed: %s %s", claim["_id"], provisional["method"],
                point or provisional["decline_reason"])
    _notify(claim, doc, provisional, suburb)
    # A declined what-if is a legitimate outcome, not a failure: the reader's
    # correction can be perfectly valid and the home still fall outside the
    # design envelope. It is recorded, and the caller counts it as succeeded.
    return True


def poll_once(client, pv):
    claims = client["system_monitor"]["attribute_claims"]

    # ⚠ Compare in explicit UTC. Cosmos returns naive datetimes and the VM runs
    # AEST, so a naive comparison makes a job started seconds ago look ten hours
    # old and hands a live job to a second worker.
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_CLAIM_SECONDS)
    for stuck in claims.find({"status": "processing"}):
        started = stuck.get("started_at")
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started and started < cutoff:
            claims.update_one({"_id": stuck["_id"]}, {"$set": {"status": "pending"}})
            logger.warning("Reclaimed stale claim %s", stuck["_id"])

    claim = claims.find_one_and_update(
        {"status": "pending"},
        {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}},
        sort=[("created_at", 1)],
    )
    if not claim:
        return {"claimed": 0, "succeeded": 0, "failed": 0}

    ok = process_one(client, pv, claim)
    return {"claimed": 1, "succeeded": int(ok), "failed": int(not ok)}


def main():
    logger.info("Attribute claim poller starting (every %ss)", POLL_INTERVAL)
    import precompute_valuations as pv
    client = get_client()
    last_idle_beat = 0.0

    # Warm before serving anything. The first reader must never pay the 145s
    # build; systemd restarts this process rarely, and a restart during traffic
    # costs one slow claim rather than every claim.
    try:
        _caches(pv, client)
    except Exception as exc:
        logger.error("Cache warm-up failed, will retry on the first claim: %s", exc)

    while True:
        try:
            counters = poll_once(client, pv)
            now = time.time()

            # Refresh off the critical path, while nobody is waiting.
            if not counters["claimed"] and _CACHE["built_at"] and \
                    now - _CACHE["built_at"] > CACHE_TTL_SECONDS:
                try:
                    _caches(pv, client)
                except Exception as exc:
                    logger.error("Cache refresh failed, keeping the old payload: %s", exc)

            # ⚠ TWO heartbeat paths, deliberately.
            #
            # A poller that only beats when it does work is indistinguishable
            # from a dead one whenever the queue is quiet — and this queue will
            # be quiet for a while, because the feature is new. With a
            # work-only heartbeat the health board would show STALE on day one
            # and stay there, training us to ignore it. See
            # [[health_board_paused_vs_dead]].
            #
            # So: an idle beat every IDLE_BEAT_SECONDS proves the process is
            # alive, and a work beat carries the 7b assertion. Both use the same
            # job name so the board shows one row.
            if counters["claimed"]:
                with job_run("attribute_claim_poller", cadence_hours=24,
                             title="Off-Market Attribute Corrections") as beat:
                    beat.metrics = counters
                    # Rule 7b — claiming work and producing nothing is a
                    # failure, not an idle cycle. Without this the poller
                    # reports success while every reader's correction errors.
                    if counters["succeeded"] == 0:
                        raise RuntimeError(
                            f"claimed {counters['claimed']} correction(s) and computed none — "
                            "see attribute_claims.error")
                    beat.detail = f"{counters['succeeded']} correction(s) valued"
                last_idle_beat = now
            elif now - last_idle_beat > IDLE_BEAT_SECONDS:
                with job_run("attribute_claim_poller", cadence_hours=24,
                             title="Off-Market Attribute Corrections") as beat:
                    beat.detail = "alive, no corrections waiting"
                    beat.metrics = {"claimed": 0, "succeeded": 0, "failed": 0}
                last_idle_beat = now
        except Exception as exc:
            logger.error("Poll cycle failed: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
