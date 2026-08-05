#!/usr/bin/env python3
"""
fridge_home_shot_check.py — is the fridge's secret-door reveal still the homepage?

Behind the secret door at /fridge is a STILL of the Fields homepage, not a live
iframe (an iframe fires the homepage's own analytics on every press and can
reveal a blank box if it hasn't painted). The cost of that choice is that the
still goes stale silently: the homepage gets redesigned and the fridge keeps
revealing last month's version, and nothing anywhere says so.

This job re-captures the homepage, compares it with the still that is actually
deployed, and reports the drift as a heartbeat on the Fields Systems Health
sheet (Process Registry page). It does NOT auto-deploy: pushing to the website
repo costs a Netlify build and is not something a cron should do unattended.
When it reports STALE, run:

    cd 15_Off-Market/Concepts/Fridge_Magnet_Concept
    node assets/build_home_shot.mjs && python3 deploy.py
    # then push public/fridge/assets/home.webp with scripts/push_website_files.py

Comparison is a coarse perceptual one — a 32x64 grid of mean luminance, compared
as mean absolute difference. Deliberately blunt: a byte hash would fire on every
listing-price change and a strict pixel diff would fire on any photo rotating in
the "New this week" rail. We only want to know when the PAGE changed, not when
its contents did.

Cadence: weekly. Rule 7 (CLAUDE.md) — cadence_hours self-registers it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_status import job_run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONCEPT = os.path.join(HERE, "..", "15_Off-Market", "Concepts", "Fridge_Magnet_Concept")
DEPLOYED = "https://fieldsestate.com.au/fridge/assets/home.webp"
HOMEPAGE = "https://fieldsestate.com.au/?fields_internal=1"

# Mean-absolute-difference over a 32x64 luminance grid, 0-255. Tuned so a
# normal week of listing churn stays well under it and a redesign clears it.
DRIFT_STALE = 12.0

GRID_W, GRID_H = 32, 64


def _fingerprint(path):
    """Coarse luminance grid — blunt on purpose. See module docstring."""
    from PIL import Image
    im = Image.open(path).convert("L").resize((GRID_W, GRID_H), Image.LANCZOS)
    return list(im.getdata())  # noqa: Pillow deprecation is harmless here


def _capture(out_png):
    """Re-shoot the homepage with the SAME script the still is built from, so a
    difference can never be an artefact of two different capture paths."""
    script = os.path.join(CONCEPT, "assets", "build_home_shot.mjs")
    subprocess.run(["node", script], cwd=CONCEPT, check=True,
                   capture_output=True, text=True, timeout=180)
    raw = os.path.join(CONCEPT, "assets", "home_raw.png")
    if not os.path.exists(raw):
        # Deliberately NO fallback to assets/home.webp. An earlier version had
        # one, and since this function MOVES the file it found, that fallback
        # would have quietly destroyed the deployed source asset the first time
        # build_home_shot.mjs changed its output name. Fail loudly instead.
        raise RuntimeError(f"build_home_shot.mjs produced no {raw}")
    os.replace(raw, out_png)          # move, so no stray capture is left behind
    return out_png


def main():
    with job_run("fridge_home_shot", cadence_hours=168,
                 title="Fridge secret-door homepage still") as beat:
        import urllib.request

        tmp = tempfile.mkdtemp(prefix="fridgeshot_")
        live_path = os.path.join(tmp, "deployed.webp")
        with urllib.request.urlopen(DEPLOYED, timeout=60) as r:
            if r.status != 200:
                raise RuntimeError(f"deployed still returned HTTP {r.status}")
            open(live_path, "wb").write(r.read())

        fresh_path = _capture(os.path.join(tmp, "fresh.png"))

        a, b = _fingerprint(live_path), _fingerprint(fresh_path)
        drift = sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))
        stale = drift >= DRIFT_STALE

        beat.metrics = {
            "drift": round(drift, 2),
            "threshold": DRIFT_STALE,
            "stale": stale,
            "deployed_bytes": os.path.getsize(live_path),
        }
        beat.detail = (
            f"STALE — homepage drift {drift:.1f} (>= {DRIFT_STALE}); "
            f"re-run build_home_shot.mjs + deploy.py"
            if stale else
            f"in sync — drift {drift:.1f} of {DRIFT_STALE}"
        )
        print(beat.detail)

        # Surface it as a failure so the health board shows ERROR rather than a
        # green row with bad news buried in the detail column. A stale reveal is
        # a real defect: the fridge shows a homepage that no longer exists.
        if stale:
            raise RuntimeError(beat.detail)


if __name__ == "__main__":
    main()
