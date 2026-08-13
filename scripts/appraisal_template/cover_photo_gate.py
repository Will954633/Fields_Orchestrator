"""Is this photo fit to be a report cover?

WHY THIS EXISTS
---------------
The cover hero prefers scraped Domain listing photos. An audit of 43 pre-warmed
covers on 2026-08-13 found two problems with that:

1. **A competing agency's watermark on a Fields-branded cover.**
   `1 Highgate Lane` carried "PRD nationwide Robina" across the photo, directly
   under our own logo. These photos were commissioned by the listing agency, so
   this is both a brand problem and a copyright one — and it would have been
   published on ~7,700 report covers.

2. **Roughly a third of covers were not the house.** Listing photo #1 is
   frequently a kitchen, a living room, a pool or a deck. Not the wrong
   property, but a kitchen bench under a street address is a poor cover.

The gate does not try to repair a photo. `floor_plan_debrand.py` inpaints,
because a floor plan is a line drawing with margins; content-aware removal on
photography is far riskier and a visibly smudged patch is worse than no photo.
So this is a REJECT, and the caller falls through to the boundary aerial —
which is always the subject property, never watermarked, and shows the lot.

One Vision call per photo, three features. Verdicts are cached by the caller,
so a re-render costs nothing.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
_AGENCIES = _REPO_ROOT / "scripts" / "property_reports" / "floor_plan_agencies.txt"

# Labels that say "this is the outside of a building". Vision returns these with
# confidence scores; we compare the weight of exterior evidence against interior.
EXTERIOR = {
    "house", "home", "property", "real estate", "residential area", "building",
    "roof", "driveway", "yard", "facade", "cottage", "siding", "land lot",
    "estate", "suburb", "garage", "front yard", "lawn", "neighbourhood",
    "neighborhood", "villa", "mansion", "farmhouse", "door", "window",
    "aerial photography", "bird's-eye view", "residential",
}
INTERIOR = {
    "kitchen", "countertop", "cabinetry", "room", "interior design", "furniture",
    "floor", "ceiling", "living room", "couch", "tile", "bathroom", "bedroom",
    "dining room", "flooring", "hardwood", "kitchen appliance", "sink",
    "cupboard", "shelf", "table", "chair", "lighting", "curtain", "bathtub",
    "wall", "carpet", "sofa bed", "coffee table", "kitchen stove",
}
# A pool shot is outdoors but still not the home. Counted separately so the
# threshold can differ — a pool visible BESIDE a house is fine; a frame that is
# mostly water is not.
POOL = {"swimming pool", "pool", "water", "leisure", "jacuzzi", "reflecting pool"}

# Agent-marketing text that means the frame carries someone's branding even when
# no logo is detected — a "for sale" board, an agent's phone number, a URL.
MARKETING_RE = re.compile(
    r"\b(for sale|auction|open home|inspect|sold by|contact agent|realestate\.com|domain\.com\.au)\b",
    re.I,
)
PHONE_RE = re.compile(r"\b0[45]\d{2}[\s-]?\d{3}[\s-]?\d{3}\b")


def _agency_tokens() -> list[str]:
    try:
        return [
            ln.strip().lower()
            for ln in _AGENCIES.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    except Exception:
        return []


def _call_vision(image_bytes: bytes) -> dict:
    from scripts.property_reports.floor_plan_debrand import _vision_token  # reuse SA auth

    body = {"requests": [{
        "image": {"content": base64.b64encode(image_bytes).decode()},
        "features": [
            {"type": "LOGO_DETECTION", "maxResults": 10},
            {"type": "TEXT_DETECTION"},
            {"type": "LABEL_DETECTION", "maxResults": 20},
        ],
    }]}
    req = urllib.request.Request(
        VISION_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_vision_token()}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    r0 = (payload.get("responses") or [{}])[0]
    if "error" in r0:
        raise RuntimeError(f"vision api error: {r0['error']}")
    return r0


def assess(image_bytes: bytes) -> dict:
    """Return {publishable: bool, reason: str|None, detail: {...}}.

    ⚠ Fails OPEN. If Vision is unreachable the photo is accepted, because the
    alternative — silently demoting every cover to an aerial the moment an API
    key expires — would be a large invisible change to ~7,700 covers. The caller
    records `reason` so a spike in `vision_unavailable` is visible rather than
    mistaken for a clean run.
    """
    try:
        r = _call_vision(image_bytes)
    except Exception as exc:
        return {"publishable": True, "reason": "vision_unavailable",
                "detail": {"error": str(exc)[:200]}}

    logos = [l.get("description", "") for l in (r.get("logoAnnotations") or [])]
    text = ((r.get("textAnnotations") or [{}])[0].get("description") or "").lower()
    labels = {(l.get("description") or "").lower(): l.get("score", 0)
              for l in (r.get("labelAnnotations") or [])}

    detail = {"logos": logos, "top_labels": sorted(labels, key=labels.get, reverse=True)[:6]}

    # 1. Any recognised logo at all. On a house photo a detected brand mark is
    #    an agency watermark essentially by definition.
    if logos:
        return {"publishable": False, "reason": f"logo:{logos[0][:40]}", "detail": detail}

    # 2. A known agency name in the OCR.
    for token in _agency_tokens():
        if token and token in text:
            return {"publishable": False, "reason": f"agency_text:{token}", "detail": detail}

    # 3. Agent-marketing furniture — signboards, phone numbers, portal URLs.
    if MARKETING_RE.search(text):
        return {"publishable": False, "reason": "marketing_text", "detail": detail}
    if PHONE_RE.search(text):
        return {"publishable": False, "reason": "phone_number", "detail": detail}

    # 4. Is it actually the outside of the home? Compare weighted evidence rather
    #    than testing for any single label — a facade photo legitimately contains
    #    "window" and "door", and an interior legitimately contains "building".
    ext = sum(s for k, s in labels.items() if k in EXTERIOR)
    inte = sum(s for k, s in labels.items() if k in INTERIOR)
    pool = sum(s for k, s in labels.items() if k in POOL)
    detail |= {"exterior": round(ext, 2), "interior": round(inte, 2), "pool": round(pool, 2)}

    if inte > ext:
        return {"publishable": False, "reason": "interior", "detail": detail}
    if pool > ext:
        return {"publishable": False, "reason": "pool_dominant", "detail": detail}
    if ext == 0:
        return {"publishable": False, "reason": "no_exterior_signal", "detail": detail}

    return {"publishable": True, "reason": None, "detail": detail}


def assess_path(path) -> dict:
    return assess(Path(path).read_bytes())
