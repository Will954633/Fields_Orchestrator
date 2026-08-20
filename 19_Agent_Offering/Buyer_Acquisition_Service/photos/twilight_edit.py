#!/usr/bin/env python3
"""
twilight_edit.py — turn a daytime real-estate exterior into a dusk/twilight shot
using Google's Gemini 2.5 Flash Image model (codename "nano-banana"), billed on
our own GOOGLE_GEMINI_API_KEY (GCP fields-estate), not a third-party reseller.

Usage:
    python3 twilight_edit.py 03 25 31            # edit these image numbers, default style
    python3 twilight_edit.py 03 --style subtle
    python3 twilight_edit.py 03 --style dramatic

Reads originals from ./original/NN.jpg, writes ./twilight/NN_twilight_<style>.jpg.

⚠ These are LIGHTING/SKY edits only. The prompt forbids adding, removing or moving
any structure, plant or object. Always eyeball the output against the original —
the model can quietly beautify (greener grass, tidier foliage). Anything beyond a
lighting change is a misrepresentation risk and must not ship.
"""
import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

from google import genai
from PIL import Image

HERE = Path(__file__).resolve().parent
ORIG = HERE / "original"
OUT = HERE / "twilight"
MODEL = "gemini-2.5-flash-image"

_KEEP = (
    "Keep the house, garden, driveway, fences, trees, plants and every object "
    "EXACTLY as they are — do not add, remove, move, clean up or beautify anything. "
    "Do not make the grass greener or the plants fuller. Same camera angle and framing. "
    "Photorealistic, natural, professional estate-agent quality."
)

STYLES = {
    # balanced, the safe default
    "default": (
        "Convert this real-estate photograph into a professional twilight (dusk) shot. "
        "Change ONLY the lighting and sky: a deep blue dusk sky with soft warm cloud near "
        "the horizon, warm golden light glowing from the windows, subtle warm landscape "
        "lighting, gentle ambient dusk on the facade. " + _KEEP
    ),
    # restrained — clear graduated blue sky, minimal cloud drama, gentle glow
    "subtle": (
        "Convert this real-estate photograph into a restrained twilight (blue-hour) shot. "
        "Change ONLY the lighting and sky: a clean graduated deep-blue evening sky with only "
        "faint cloud, a soft warm glow from the windows, and gentle dusk light on the facade. "
        "Understated and realistic — not dramatic. " + _KEEP
    ),
    # richer sunset colour for hero use
    "dramatic": (
        "Convert this real-estate photograph into a striking twilight (dusk) hero shot. "
        "Change ONLY the lighting and sky: a rich sunset sky with warm orange-to-deep-blue "
        "gradient and soft glowing clouds, strong warm light pouring from the windows, and "
        "warm landscape/uplighting on the facade and trees. Cinematic but still photorealistic. "
        + _KEEP
    ),
    # INTERIOR photographic enhancement — NOT a renovation. Exposure/WB/window-pull only.
    "interior": (
        "Professionally enhance this real-estate INTERIOR photograph as a skilled property "
        "photographer would in post-production. Allowed changes ONLY: balance the exposure so "
        "the room is bright, clean and evenly lit; correct the white balance to neutral; recover "
        "the blown-out windows so the view/greenery outside is visible instead of pure white; add "
        "a natural, inviting warmth to the existing light; sharpen and clean up haze. "
        "STRICTLY FORBIDDEN: do NOT renovate or modernise. Do NOT change, replace, resurface or "
        "re-colour any benchtop, cabinet, tile, splashback, floor, appliance, fixture, tap, wall, "
        "ceiling or window frame. Do NOT add, remove, move or tidy any furniture, appliance, "
        "personal item or clutter. Keep the exact same room, the exact same dated or original "
        "finishes, and every object precisely where it is. Same camera angle and framing. "
        "Photorealistic. This is a lighting/exposure edit, not a redecoration."
    ),
    # INTERIOR TWILIGHT — the visible dusk look to pair with the exterior twilight shots.
    "interior_twilight": (
        "Relight this real-estate INTERIOR photograph as a professional TWILIGHT / dusk shot, "
        "matching evening exterior twilight photography. Make the change clearly visible: "
        "- Through every window and glass door, show a DUSK sky outside — deep blue evening or a "
        "warm sunset glow on the horizon, not bright daytime. "
        "- Turn ON the room's existing lights: warm golden glow from the ceiling fixtures, lamps "
        "and any fittings already in the shot, casting a cosy warm pool of light. "
        "- Shift the overall mood to a warm, inviting evening ambience — warmer white balance, "
        "gentle contrast, soft shadows — clearly an evening interior, not a midday one. "
        "STRICTLY FORBIDDEN: do NOT renovate or modernise. Do NOT change, replace, resurface or "
        "re-colour any benchtop, cabinet, tile, splashback, floor, appliance, fixture, wall, "
        "ceiling, window frame or furniture. Do NOT add, remove, move or tidy any object or "
        "clutter. Keep the exact same room, the exact same dated/original finishes and every "
        "object where it is — only the light and the view through the windows change. "
        "Same camera angle and framing. Photorealistic estate-agent quality."
    ),
}


def edit(num: str, style: str, client: genai.Client) -> str:
    src = ORIG / f"{num}.jpg"
    if not src.exists():
        return f"[skip] {src} not found"
    img = Image.open(src)
    if max(img.size) > 1600:
        img.thumbnail((1600, 1600))
    resp = client.models.generate_content(model=MODEL, contents=[STYLES[style], img])
    for part in resp.candidates[0].content.parts:
        data = getattr(getattr(part, "inline_data", None), "data", None)
        if data:
            OUT.mkdir(exist_ok=True)
            dst = OUT / f"{num}_twilight_{style}.jpg"
            Image.open(BytesIO(data)).convert("RGB").save(dst, quality=92)
            return f"[ok]   {dst.name}"
    return f"[fail] {num}: no image returned"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nums", nargs="+", help="image numbers, e.g. 03 25 31")
    ap.add_argument("--style", default="default", choices=list(STYLES))
    args = ap.parse_args()
    key = os.environ.get("GOOGLE_GEMINI_API_KEY")
    if not key:
        sys.exit("GOOGLE_GEMINI_API_KEY not set (source the .env)")
    client = genai.Client(api_key=key)
    for num in args.nums:
        print(edit(num.zfill(2), args.style, client))


if __name__ == "__main__":
    main()
