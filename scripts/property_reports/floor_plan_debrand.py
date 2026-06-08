"""floor_plan_debrand.py — Strip agent branding from a floor-plan image (Google Vision
text OCR + OpenCV inpainting + Claude stylized-logo pass), for the house mini-site build.

This is the production module behind the de-brand POC in
`Feilds_Website/10_Floor_Plans/Debrand_POC/vision_debrand_v2.py` (the experiment record).
The engine here is the v1 logic, lifted to operate on in-memory bytes and wired into the
property-report build so the mini-site only ever shows a cleaned floor plan.

Pipeline (per image):
  1. Google Vision DOCUMENT_TEXT_DETECTION + LOGO_DETECTION  -> precise text/logo boxes.
     Text classified brand-vs-keep (agency list + phone/url/copyright patterns) so room
     labels, dimensions and the address are preserved.
  2. Colour-badge detector (margin/text-corroborated only — never the plan body).
  3. Claude (Anthropic) vision pass for stylized logos OCR can't read (Digi360, COASTAL°…).
  4. Content-aware removal: margin/chrome flattened to paper, body text stroke-inpainted,
     coloured/grey ROOM fills always preserved.

Auth:
  * Google Vision: a token minted from the dedicated `floor-plan-processor` service
    account key (GOOGLE_VISION_SA_KEY, default /home/fields/.gcp-floor-plan-vision.json) —
    durable, no dependency on any personal login. Falls back to VISION_ACCESS_TOKEN env or
    `gcloud auth print-access-token` if the key is missing. Quota project is the SA's own
    project (fields-estate); X-Goog-User-Project = VISION_QUOTA_PROJECT is also sent.
  * Claude: ANTHROPIC_API_KEY env.

Public API:
  debrand_image_bytes(img_bytes)  -> cleaned PNG bytes  (raises DebrandError on hard failure)
  apply_debrand(fp, slug=, address=) -> fp with url swapped to the cleaned blob, or the
    original url left in place + a Telegram alert sent, on any failure (never blocks a build).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
HERE = Path(__file__).parent
AGENCIES_PATH = HERE / "floor_plan_agencies.txt"
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
BLOB_CONTAINER = "property-images"


class DebrandError(RuntimeError):
    """Hard failure that prevented producing a cleaned image (Vision down, bad image…)."""


# ---------------------------------------------------------------------------
# Classification vocab (room labels/dimensions kept; agency/contact text removed)
# ---------------------------------------------------------------------------
FLOORPLAN_KEEP = {
    "bedroom", "master", "bed", "bath", "bathroom", "ensuite", "en-suite", "en",
    "suite", "kitchen", "living", "dining", "lounge", "family", "rumpus", "media",
    "garage", "carport", "carpark", "car", "park", "laundry", "l'dry", "ldry",
    "study", "wir", "robe", "wc", "pantry", "p'try", "ptry", "butlers", "balcony",
    "patio", "deck", "porch", "alfresco", "verandah", "entry", "ent", "hall",
    "hallway", "store", "storage", "void", "stairs", "stair", "pwd", "powder",
    "wardrobe", "linen", "shower", "shwr", "pool", "spa", "level", "ground",
    "first", "second", "third", "lower", "upper", "floor", "plan", "internal",
    "external", "total", "area", "approx", "m2", "m²", "sqm", "sqs", "sq", "bbq",
    "bar", "island", "fr", "ov", "cof", "mc", "c'brd", "cbrd", "fp", "dn", "up",
    "n", "north", "ceiling", "height", "scale", "meters", "metres", "with",
    "ocean", "views", "view", "lin", "u/cover", "cover", "single",
    "double", "space", "amenities", "building", "apartment", "not", "in",
    "position", "of", "the", "and", "to", "is", "are", "this", "shed", "office",
    "retreat", "nook", "walk", "open", "dressing", "guest", "kids",
    "theatre", "gym", "cellar", "wine", "workshop", "mud", "room",
}

BRAND_PATTERNS = [
    re.compile(r"©|\(c\)|copyright", re.I),
    re.compile(r"www\.|\.com|\.au|http|\.net", re.I),
    re.compile(r"\b(?:\+?61|0)\s*\d[\d\s]{7,}\b"),
    re.compile(r"\b1300\s*\d{3}\s*\d{3}\b"),
    re.compile(r"\b13\s?\d{2}\s?\d{2}\b"),
    re.compile(r"™|®"),
    re.compile(r"\b(realty|realestate|real estate|property group|properties|estate agents?)\b", re.I),
]

# Branding lives in the outer frame / footer; this is the safety boundary for any removal
# not anchored to Vision-detected brand text. Coloured ROOM fills in the body are off-limits.
MARGIN_FRAC = 0.12
SMALL_REGION_FRAC = 0.03
COLOR_TOL = 52

_AGENCIES_CACHE: Optional[List[str]] = None


def _agencies() -> List[str]:
    global _AGENCIES_CACHE
    if _AGENCIES_CACHE is None:
        phrases: List[str] = []
        if AGENCIES_PATH.exists():
            for line in AGENCIES_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    phrases.append(line)
        _AGENCIES_CACHE = phrases
    return _AGENCIES_CACHE


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _boxes_overlap(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _frac_area_inside(box, rect) -> float:
    ix0, iy0 = max(box[0], rect[0]), max(box[1], rect[1])
    ix1, iy1 = min(box[2], rect[2]), min(box[3], rect[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
    return inter / area


def in_margin(box, W: int, H: int, frac: float = MARGIN_FRAC) -> bool:
    inner = (W * frac, H * frac, W * (1 - frac), H * (1 - frac))
    return _frac_area_inside(box, inner) < 0.5


def _vertices(poly):
    xs = [v.get("x", 0) for v in poly.get("vertices", [])]
    ys = [v.get("y", 0) for v in poly.get("vertices", [])]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Google Vision
# ---------------------------------------------------------------------------
_SA_CREDS = None  # cached service-account Credentials (token auto-refreshes)
_VISION_SA_KEY_DEFAULT = "/home/fields/.gcp-floor-plan-vision.json"


def _vision_token() -> str:
    """Fresh Vision access token.

    Priority: VISION_ACCESS_TOKEN env (testing) > dedicated service-account key
    (durable, no dependency on any personal login — this is the production path) >
    `gcloud auth print-access-token` (last-resort fallback).
    """
    tok = os.environ.get("VISION_ACCESS_TOKEN", "").strip()
    if tok:
        return tok

    # Preferred: the floor-plan-processor service account key.
    key_path = os.environ.get("GOOGLE_VISION_SA_KEY", _VISION_SA_KEY_DEFAULT)
    if key_path and os.path.exists(key_path):
        try:
            global _SA_CREDS
            if _SA_CREDS is None:
                from google.oauth2 import service_account
                _SA_CREDS = service_account.Credentials.from_service_account_file(
                    key_path, scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not _SA_CREDS.valid:
                from google.auth.transport.requests import Request
                _SA_CREDS.refresh(Request())
            if _SA_CREDS.token:
                return _SA_CREDS.token
        except Exception as e:
            logger.warning(f"  floor_plan debrand: SA-key auth failed ({e}); trying gcloud")

    # Last resort: a user gcloud login on the VM.
    try:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        raise DebrandError(f"vision: no usable SA key and gcloud token mint errored: {e}")
    if out.returncode != 0 or not out.stdout.strip():
        raise DebrandError(f"vision: no usable SA key and gcloud token failed: "
                           f"{(out.stderr or '').strip()[:200]}")
    return out.stdout.strip()


def _call_vision(image_bytes: bytes, token: str, quota_project: str) -> dict:
    body = {"requests": [{
        "image": {"content": base64.b64encode(image_bytes).decode()},
        "features": [
            {"type": "DOCUMENT_TEXT_DETECTION"},
            {"type": "LOGO_DETECTION", "maxResults": 10},
        ],
    }]}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if quota_project:
        headers["X-Goog-User-Project"] = quota_project
    req = urllib.request.Request(VISION_URL, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        raise DebrandError(f"vision: HTTP {e.code} {detail}")
    except Exception as e:
        raise DebrandError(f"vision: request failed: {e}")
    resp0 = (payload.get("responses") or [{}])[0]
    if "error" in resp0:
        raise DebrandError(f"vision: api error {resp0['error']}")
    return resp0


def _classify(text: str, agencies: List[str]) -> str:
    t = text.strip().lower()
    if not t:
        return "keep"
    for pat in BRAND_PATTERNS:
        if pat.search(text):
            return "brand"
    for phrase in agencies:
        if " " in phrase:
            if phrase in t:
                return "brand"
        elif re.search(rf"\b{re.escape(phrase)}\b", t):
            return "brand"
    return "keep"


def _detect_color_badges(bgr: np.ndarray, brand_text_boxes=None):
    brand_text_boxes = brand_text_boxes or []
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    mask = ((sat > 90) & (val > 60)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = bgr.shape[:2]
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < (W * H) * 0.0008 or area > (W * H) * 0.25:
            continue
        box = (x, y, x + w, y + h)
        if in_margin(box, W, H) or any(_boxes_overlap(box, t) for t in brand_text_boxes):
            boxes.append(box)
    return boxes


# ---------------------------------------------------------------------------
# Claude stylized-logo pass
# ---------------------------------------------------------------------------
_LLM_PROMPT = (
    "This is a real-estate floor plan. Find every region containing AGENT or AGENCY "
    "BRANDING and return a tight pixel-coordinate bounding box for each. Branding includes: "
    "agency/company logos and stylized wordmarks drawn as graphics (e.g. 'Digi360', 'TMG', "
    "'JMO', 'BANGO STERA'), agency names, agent names, photographer or floor-plan-provider "
    "credits, website URLs, email addresses, phone numbers, and copyright notices. "
    "Do NOT box any of these (they must be preserved): room names/labels (Bedroom, Kitchen, "
    "Garage, Living, etc.), measurements/dimensions, total area figures, the property's "
    "street address, level titles (Floor 1, Ground, Level 1), the bed/bath/car summary icons, "
    "north arrows, and scale bars. Return an empty list if there is no branding."
)


def _encode_for_llm(pil: Image.Image, max_edge: int = 1568):
    im = pil.convert("RGB")
    w, h = im.size
    if max(w, h) > max_edge:
        s = max_edge / max(w, h)
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), im.size[0], im.size[1]


def _detect_branding_regions_claude(png_bytes: bytes, model: str, W: int, H: int,
                                    timeout_s: int = 60) -> List[tuple]:
    """Stylized-logo boxes from Claude. Degrades to [] on any error (non-fatal)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("  floor_plan debrand: ANTHROPIC_API_KEY unset; skipping logo pass")
        return []
    b64 = base64.b64encode(png_bytes).decode()
    tool = {
        "name": "report_branding",
        "description": "Report bounding boxes of agent/agency branding found in the floor plan.",
        "input_schema": {
            "type": "object",
            "properties": {"regions": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "x_min": {"type": "integer"}, "y_min": {"type": "integer"},
                    "x_max": {"type": "integer"}, "y_max": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["x_min", "y_min", "x_max", "y_max", "label"],
            }}},
            "required": ["regions"],
        },
    }
    prompt = (f"The image is {W}px wide by {H}px tall. " + _LLM_PROMPT +
              " Give coordinates in full-image pixels (origin top-left). Call report_branding "
              "with one region per branding element; pass an empty list if there is none.")
    body = {
        "model": model, "max_tokens": 1500, "tools": [tool],
        "tool_choice": {"type": "tool", "name": "report_branding"},
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": prompt},
        ]}],
    }
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    payload = json.dumps(body).encode()
    data = None
    for attempt in range(6):
        req = urllib.request.Request(ANTHROPIC_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                ra = e.headers.get("retry-after")
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else 2.0 * (2 ** attempt)
                time.sleep(min(wait, 30.0))
                continue
            logger.warning(f"  floor_plan debrand: Claude HTTP {e.code}; skipping logo pass")
            return []
        except Exception as e:
            logger.warning(f"  floor_plan debrand: Claude pass failed ({e}); skipping")
            return []
    if data is None:
        return []
    regions = []
    for blk in data.get("content", []):
        if blk.get("type") == "tool_use" and blk.get("name") == "report_branding":
            regions = blk.get("input", {}).get("regions", [])
            break
    out = []
    for r in regions:
        try:
            box = (int(r["x_min"]), int(r["y_min"]), int(r["x_max"]), int(r["y_max"]))
        except (KeyError, TypeError, ValueError):
            continue
        if box[2] > box[0] and box[3] > box[1]:
            out.append((str(r.get("label", "logo"))[:40], box))
    return out


def _accept_llm_box(box, W: int, H: int) -> bool:
    area = (box[2] - box[0]) * (box[3] - box[1])
    if area > (W * H) * 0.25:
        return False
    if area < (W * H) * SMALL_REGION_FRAC:
        return True
    return in_margin(box, W, H)


# ---------------------------------------------------------------------------
# Removal (content-aware)
# ---------------------------------------------------------------------------
def _sample_paper(bgr: np.ndarray, box, pad=6):
    H, W = bgr.shape[:2]
    x0 = max(0, min(box[0], W - 1)); y0 = max(0, min(box[1], H - 1))
    x1 = max(0, min(box[2], W - 1)); y1 = max(0, min(box[3], H - 1))
    ring = []
    for x in range(max(0, x0 - pad), min(W, x1 + pad + 1)):
        for y in (max(0, min(y0 - pad, H - 1)), max(0, min(y1 + pad, H - 1))):
            ring.append(tuple(int(v) for v in bgr[y, x]))
    for y in range(max(0, y0 - pad), min(H, y1 + pad + 1)):
        for x in (max(0, min(x0 - pad, W - 1)), max(0, min(x1 + pad, W - 1))):
            ring.append(tuple(int(v) for v in bgr[y, x]))
    if not ring:
        return (255, 255, 255)
    return Counter(ring).most_common(1)[0][0]


def _page_paper(bgr: np.ndarray):
    H, W = bgr.shape[:2]
    ys = np.linspace(0, H - 1, min(H, 120)).astype(int)
    xs = np.linspace(0, W - 1, min(W, 120)).astype(int)
    pts = bgr[np.ix_(ys, xs)].reshape(-1, 3)
    q = (pts // 8 * 8)
    vals, counts = np.unique(q, axis=0, return_counts=True)
    return vals[counts.argmax()].astype(int)


def _nonpaper_mask(bgr: np.ndarray, paper, sat_thr=55, lum_thr=45):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(int)
    diff = np.abs(bgr.astype(int) - paper).sum(2)
    return (((sat > sat_thr) | (diff > lum_thr)) * 255).astype(np.uint8)


def _dominant_color(bgr: np.ndarray, box, nonpaper):
    x0, y0, x1, y1 = box
    roi = bgr[y0:y1, x0:x1].reshape(-1, 3)
    m = nonpaper[y0:y1, x0:x1].reshape(-1) > 0
    if not m.any():
        return None
    q = (roi[m] // 24 * 24)
    vals, counts = np.unique(q, axis=0, return_counts=True)
    return vals[counts.argmax()].astype(int) + 12


def _expand_color_region(bgr: np.ndarray, C, box, W: int, H: int):
    cmask = (np.abs(bgr.astype(int) - C).sum(2) < COLOR_TOL).astype(np.uint8)
    cmask = cv2.morphologyEx(cmask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(cmask, 8)
    ux0, uy0, ux1, uy1 = W, H, 0, 0
    found = False
    for i in range(1, n):
        cx, cy, cw, ch, _area = stats[i]
        comp = (cx, cy, cx + cw, cy + ch)
        if _boxes_overlap(comp, box):
            ux0, uy0 = min(ux0, cx), min(uy0, cy)
            ux1, uy1 = max(ux1, cx + cw), max(uy1, cy + ch)
            found = True
    if not found:
        return None
    union = (ux0, uy0, ux1, uy1)
    uw, uh, uarea = ux1 - ux0, uy1 - uy0, (ux1 - ux0) * (uy1 - uy0)
    is_strip = uw > 0.5 * W and uh < 0.22 * H
    is_small = uarea < 0.03 * W * H
    if (is_strip or is_small or in_margin(box, W, H)) and uarea < 0.45 * W * H:
        return union
    return None


def _grow_flatten_box(nonpaper: np.ndarray, box, W: int, H: int):
    x0, y0, x1, y1 = box
    gx = int((x1 - x0) * 0.6) + int(0.05 * W)
    gy = int((y1 - y0) * 0.6) + int(0.05 * H)
    wx0, wy0 = max(0, x0 - gx), max(0, y0 - gy)
    wx1, wy1 = min(W, x1 + gx), min(H, y1 + gy)
    sub = cv2.dilate(nonpaper[wy0:wy1, wx0:wx1], np.ones((7, 7), np.uint8), iterations=1)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(sub, 8)
    bx0, by0, bx1, by1 = x0 - wx0, y0 - wy0, x1 - wx0, y1 - wy0
    labels = set(np.unique(lbl[by0:by1, bx0:bx1].astype(np.int64))) - {0}
    ux0, uy0, ux1, uy1 = x0, y0, x1, y1
    for i in labels:
        cx, cy, cw, ch, _a = stats[i]
        ux0, uy0 = min(ux0, wx0 + cx), min(uy0, wy0 + cy)
        ux1, uy1 = max(ux1, wx0 + cx + cw), max(uy1, wy0 + cy + ch)
    if (ux1 - ux0) * (uy1 - uy0) > 0.15 * W * H:
        return box
    return (ux0, uy0, ux1, uy1)


def _remove_branding(bgr: np.ndarray, brand_boxes):
    H, W = bgr.shape[:2]
    out = bgr.copy()
    paper = _page_paper(bgr)
    nonpaper = _nonpaper_mask(bgr, paper)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    ink = np.zeros((H, W), np.uint8)

    for box in brand_boxes:
        x0, y0 = max(0, box[0]), max(0, box[1])
        x1, y1 = min(W, box[2]), min(H, box[3])
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        b = (x0, y0, x1, y1)

        flatten_region = None
        C = _dominant_color(bgr, b, nonpaper)
        if C is not None and int(C.max()) >= 70:
            flatten_region = _expand_color_region(bgr, C, b, W, H)
        if flatten_region is None and in_margin(b, W, H):
            flatten_region = _grow_flatten_box(nonpaper, b, W, H)

        if flatten_region is not None:
            rx0, ry0, rx1, ry1 = flatten_region
            fill = _sample_paper(bgr, flatten_region)
            cv2.rectangle(out, (max(0, rx0), max(0, ry0)),
                          (min(W - 1, rx1), min(H - 1, ry1)), fill, -1)
            continue

        # Body box: protect filled rooms (uniform/coloured fill); inpaint dense wordmarks.
        if C is not None and (x1 - x0) * (y1 - y0) > 0.01 * W * H:
            roi = bgr[y0:y1, x0:x1].astype(int)
            fill_frac = (np.abs(roi - C).sum(2) < COLOR_TOL).mean()
            coloured = int(C.max()) - int(C.min()) > 40
            if fill_frac >= 0.6 or (coloured and fill_frac >= 0.30):
                continue
        thr = cv2.adaptiveThreshold(gray[y0:y1, x0:x1], 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                    cv2.THRESH_BINARY_INV, 31, 10)
        ink[y0:y1, x0:x1] = np.maximum(ink[y0:y1, x0:x1], thr)

    ink = cv2.dilate(ink, np.ones((3, 3), np.uint8), iterations=2)
    if ink.any():
        out = cv2.inpaint(out, ink, 4, cv2.INPAINT_TELEA)
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def debrand_image_bytes(img_bytes: bytes, *, llm_model: str = DEFAULT_LLM_MODEL) -> bytes:
    """De-brand one floor-plan image. Returns cleaned PNG bytes.

    Raises DebrandError if a cleaned image cannot be produced (decode/Vision failure).
    The Claude logo pass degrades gracefully (logged + skipped) so Vision-only cleaning
    still ships if Anthropic is unavailable.
    """
    try:
        pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        raise DebrandError(f"decode: not a readable image ({e})")
    bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    H, W = bgr.shape[:2]
    agencies = _agencies()

    token = _vision_token()
    quota = os.environ.get("VISION_QUOTA_PROJECT", "fields-estate").strip()
    resp = _call_vision(img_bytes, token, quota)

    brand_text_boxes = []
    full = resp.get("fullTextAnnotation", {})
    for page in full.get("pages", []):
        for blk in page.get("blocks", []):
            for para in blk.get("paragraphs", []):
                words = ["".join(s.get("text", "") for s in w.get("symbols", []))
                         for w in para.get("words", [])]
                box = _vertices(para.get("boundingBox", {}))
                if box and _classify(" ".join(words), agencies) == "brand":
                    brand_text_boxes.append(box)
    for lg in resp.get("logoAnnotations", []):
        box = _vertices(lg.get("boundingPoly", {}))
        if box:
            brand_text_boxes.append(box)

    badge_boxes = _detect_color_badges(bgr, brand_text_boxes)

    # Stylized-logo pass (non-fatal).
    png, sw, sh = _encode_for_llm(pil)
    sx, sy = W / sw, H / sh
    for _label, box in _detect_branding_regions_claude(png, llm_model, sw, sh):
        box = (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))
        box = (max(0, min(box[0], W - 1)), max(0, min(box[1], H - 1)),
               max(0, min(box[2], W)), max(0, min(box[3], H)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        if _accept_llm_box(box, W, H):
            brand_text_boxes.append(box)

    clean_bgr = _remove_branding(bgr, brand_text_boxes + badge_boxes)
    clean_pil = Image.fromarray(cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    clean_pil.save(buf, format="PNG")
    return buf.getvalue()


def _fetch_image(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fields-debrand/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise DebrandError(f"fetch: HTTP {e.code} for {url}")
    except Exception as e:
        raise DebrandError(f"fetch: {e} for {url}")
    if not data:
        raise DebrandError(f"fetch: empty body for {url}")
    return data


def _telegram_alert(text: str) -> None:
    """Best-effort Telegram alert (never raises). Reads token/chat from env at call time."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        logger.warning("  floor_plan debrand: TELEGRAM_BOT_TOKEN/CHAT_ID unset; alert not sent")
        return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "Markdown",
                             "disable_web_page_preview": True}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        logger.warning(f"  floor_plan debrand: telegram alert failed: {e}")


def apply_debrand(fp: Dict[str, Any], *, slug: str, address: str = "",
                  llm_model: str = DEFAULT_LLM_MODEL) -> Dict[str, Any]:
    """Replace fp['url'] with a cleaned (de-branded) blob URL, in place.

    On any failure the original url is kept (so the mini-site always shows *a* plan) and a
    Telegram alert with stage + error is sent for fault-finding. Adds:
        fp['original_url'] — the source image
        fp['debranded']    — True if a cleaned image is now being served
    """
    orig = fp.get("url")
    if not orig:
        return fp
    stage = "fetch"
    try:
        img = _fetch_image(orig)
        stage = "debrand"
        cleaned = debrand_image_bytes(img, llm_model=llm_model)
        stage = "blob_upload"
        from shared import blob_storage
        blob_name = f"reports/{slug}/floor_plan_debranded.png"
        public = blob_storage.upload(BLOB_CONTAINER, blob_name, cleaned, "image/png")
        if not public:
            raise DebrandError("blob_upload: blob_storage.upload returned None")
        fp["original_url"] = orig
        fp["url"] = public
        fp["debranded"] = True
        logger.info(f"  floor_plan debranded ({len(cleaned)//1024} KB) -> {public}")
    except Exception as e:
        fp["debranded"] = False
        msg = (
            "🛑 *Floor-plan de-brand FAILED* — serving the ORIGINAL (un-cleaned) plan\n"
            f"*Report:* `{slug or '?'}`\n"
            f"*Address:* {address or '?'}\n"
            f"*Stage:* `{stage}`\n"
            f"*Error:* `{type(e).__name__}: {str(e)[:300]}`\n"
            f"*Image:* {orig}"
        )
        _telegram_alert(msg)
        logger.warning(f"  floor_plan debrand FAILED at {stage}: {type(e).__name__}: {e}")
    return fp


if __name__ == "__main__":
    # Manual smoke test: python3 -m scripts.property_reports.floor_plan_debrand <url-or-path> [out.png]
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/debrand_out.png"
    raw = _fetch_image(src) if src.startswith("http") else Path(src).read_bytes()
    Path(out).write_bytes(debrand_image_bytes(raw))
    print(f"wrote {out}")
