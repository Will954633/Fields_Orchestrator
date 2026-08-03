#!/usr/bin/env python3
"""
Turn the four Break Glass stills into the layers the prototype animates.

The four renders were generated independently, so they do not share a camera or
a consistent handle. Two facts drive everything below:

  * handle_down is the only internally consistent frame - its pivot bolts sit
    exactly midway between the raised and lowered bar positions (arm length
    221px). handle_up drew the arms ~120px too long, so it is used for
    reference and as a donor for clean plate, never as the motion source.
  * The bail is a rigid U hinged on the horizontal axis through the two pivot
    bolts (y=643), so the swing is a single rotateX in CSS. That is why the
    sprite is cut from handle_down and simply rotated 180deg -> 0deg.

Outputs (WebP) into assets/:
  01_intact  02_broken  03_handle_up  05_handle_down  06_plate_clean  07_handle_sprite

Run:  python3 build_assets.py
"""
import os
import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.dirname(HERE) + "/"
OUT  = os.path.join(HERE, "assets") + "/"
os.makedirs(OUT, exist_ok=True)

REF = "break_glass_handle_down.png"          # registration + motion reference

# Measured off the source render (see module docstring).
PIVOT_Y   = 643                              # hinge axis, full-image px
SIGN_BOX  = (496, 550, 744, 816)             # PULL DOWN plate in handle_down
KNUCKLES  = [(442, 865, 36), (838, 857, 36),  # bar end caps (too dark to diff)
             (458, 648, 30), (758, 638, 30)]  # pivot bolts


def _reg_band(h, w):
    """Only the metal box frame: outside the glass, so cracks and the handle
    cannot pull the registration around."""
    b = np.zeros((h, w), np.uint8)
    for r in [(170, 60, 1030, 205), (150, 205, 245, 1290),
              (940, 150, 1030, 1270), (200, 1160, 1040, 1330)]:
        cv2.rectangle(b, r[:2], r[2:], 255, -1)
    return b


def register(ref, fn, band, scale=4):
    """Affine ECC, estimated at 1/scale for speed, applied at full res."""
    h, w = ref.shape[:2]
    sh, sw = h // scale, w // scale
    g_ref = cv2.cvtColor(cv2.resize(ref, (sw, sh), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2GRAY).astype(np.float32)
    band_s = (cv2.resize(band, (sw, sh), interpolation=cv2.INTER_AREA) > 60).astype(np.uint8) * 255

    im = cv2.resize(cv2.imread(SRC + fn), (w, h), interpolation=cv2.INTER_LANCZOS4)
    g = cv2.cvtColor(cv2.resize(im, (sw, sh), interpolation=cv2.INTER_AREA),
                     cv2.COLOR_BGR2GRAY).astype(np.float32)

    best = (None, None)
    for s in (1.00, 1.05, 1.10, 0.95):       # v1 was rendered ~11% larger
        wm = np.float32([[s, 0, (1 - s) * sw / 2], [0, s, (1 - s) * sh / 2]])
        try:
            cc, wm = cv2.findTransformECC(
                g_ref, g, wm, cv2.MOTION_AFFINE,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 220, 1e-6), band_s, 5)
        except cv2.error:
            continue
        if best[0] is None or cc > best[0]:
            best = (cc, wm.copy())
    cc, wm = best
    if wm is None:
        print(f"  {fn}: ECC failed, using unregistered frame")
        return im
    wm[0, 2] *= scale
    wm[1, 2] *= scale
    print(f"  {fn:32s} ECC={cc:.4f} scale~{np.hypot(wm[0,0],wm[1,0]):.4f}")
    return cv2.warpAffine(im, wm, (w, h),
                          flags=cv2.INTER_LANCZOS4 + cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def handle_mask(down, up):
    """The bail is whatever got brighter when it swung down. Thresholding
    brightness alone fails here - it grabs the plate and the sign."""
    h, w = down.shape[:2]
    gd = cv2.cvtColor(down, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gu = cv2.cvtColor(up,   cv2.COLOR_BGR2GRAY).astype(np.float32)
    d = cv2.GaussianBlur(gd - gu, (0, 0), 2.0)

    m = ((d > 16).astype(np.uint8) * 255)
    roi = np.zeros_like(m); roi[600:940, 380:920] = 255
    m = cv2.bitwise_and(m, roi)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  np.ones((7, 7), np.uint8))

    cv2.rectangle(m, (498, 530), (740, 812), 0, -1)   # sign shifted between renders
    cv2.rectangle(m, (0, 0), (w, 612), 0, -1)         # above the pivots
    cv2.rectangle(m, (0, 930), (w, h), 0, -1)         # below the bar
    cv2.rectangle(m, (866, 0), (w, 800), 0, -1)       # handle_up right-arm ghost
    cv2.rectangle(m, (0, 560), (436, 800), 0, -1)     # handle_up left-arm ghost
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] > 3000:
            keep[lab == i] = 255
    for cx, cy, r in KNUCKLES:
        cv2.circle(keep, (cx, cy), r, 255, -1)
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    ff = keep.copy()
    cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
    return keep | cv2.bitwise_not(ff)


def clean_plate(down, up, mask):
    """Erase the bail so the sprite has something to swing over."""
    h, w = down.shape[:2]
    dn, up_f = down.astype(np.float32), up.astype(np.float32)

    # The bail casts a large, very soft shadow. Repair the whole zone it lives
    # in rather than chasing the shadow's edges.
    M = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=9)
    box = np.zeros((h, w), np.uint8)
    cv2.rectangle(box, (366, 598), (906, 946), 255, -1)
    cv2.rectangle(box, (492, 546), (748, 820), 0, -1)          # keep the sign
    M = cv2.max(M, box)
    M = cv2.dilate(M, np.ones((15, 15), np.uint8))
    M = ((cv2.GaussianBlur(M, (0, 0), 4)) > 30).astype(np.uint8) * 255

    # lighting field: inpaint at 1/8 scale so it stays smooth and halo-free
    s = 8
    small = cv2.resize(down, (w // s, h // s), interpolation=cv2.INTER_AREA)
    sm = (cv2.resize(M, (w // s, h // s), interpolation=cv2.INTER_LINEAR) > 10).astype(np.uint8) * 255
    low = cv2.resize(cv2.inpaint(small, sm, 5, cv2.INPAINT_NS), (w, h),
                     interpolation=cv2.INTER_CUBIC).astype(np.float32)

    # grain: a real, text-free patch of the same plate, mirror-tiled
    d = dn[415:550, 400:870]
    d = np.vstack([d, d[::-1]]); d = np.hstack([d, d[:, ::-1]])
    tile = np.tile(d, (int(np.ceil(h / d.shape[0])), int(np.ceil(w / d.shape[1])), 1))[:h, :w]
    synth = low + (tile - cv2.GaussianBlur(tile, (0, 0), s * 4)) * 0.9

    # handle_up has genuinely clean, correctly lit plate low down - prefer real
    # pixels there, but never donor from inside its (differently placed) sign
    ramp = np.clip((np.arange(h) - 782) / 46.0, 0, 1)[:, None, None]
    ramp = np.repeat(ramp, w, axis=1)
    ok = np.ones((h, w), np.float32)
    cv2.rectangle(ok, (486, 596), (754, 884), 0.0, -1)
    ramp = ramp * cv2.GaussianBlur(ok, (0, 0), 9)[..., None]
    base = synth * (1 - ramp) + up_f * ramp

    soft = (cv2.GaussianBlur(M, (0, 0), 3) / 255.0)[..., None]
    plate = np.clip(dn * (1 - soft) + base * soft, 0, 255)

    # the bail never crosses the sign - restore it verbatim so the repair
    # cannot eat its screws or edges
    keep = np.zeros((h, w), np.float32)
    cv2.rectangle(keep, SIGN_BOX[:2], SIGN_BOX[2:], 1.0, -1)
    keep = cv2.GaussianBlur(keep, (0, 0), 3)[..., None]
    return np.clip(plate * (1 - keep) + dn * keep, 0, 255).astype(np.uint8)


def save(path, img):
    cv2.imwrite("/tmp/_bg.png", img)
    Image.open("/tmp/_bg.png").save(path, "WEBP", quality=88, method=5)
    os.remove("/tmp/_bg.png")
    print(f"  wrote {os.path.basename(path):24s} {os.path.getsize(path)//1024:4d}KB")


def main():
    down = cv2.imread(SRC + REF)
    h, w = down.shape[:2]
    band = _reg_band(h, w)

    print("registering frames to", REF)
    intact = register(down, "break_glass_v1.png", band)
    broken = register(down, "break_glass_broken.png", band)
    up     = register(down, "break_glass_handle_up.png", band)

    print("cutting the bail")
    mask = handle_mask(down, up)
    ys, xs = np.where(mask > 0)
    x0, x1, y0, y1 = xs.min() - 6, xs.max() + 7, ys.min() - 6, ys.max() + 7
    sprite = np.dstack([down, cv2.GaussianBlur(mask, (0, 0), 1.6)])[y0:y1, x0:x1]

    print("repairing the plate")
    plate = clean_plate(down, up, mask)

    print("writing assets")
    save(OUT + "01_intact.webp",       intact)
    save(OUT + "02_broken.webp",       broken)
    save(OUT + "03_handle_up.webp",    up)
    save(OUT + "05_handle_down.webp",  down)
    save(OUT + "06_plate_clean.webp",  plate)
    cv2.imwrite("/tmp/_spr.png", sprite)
    Image.open("/tmp/_spr.png").save(OUT + "07_handle_sprite.webp", "WEBP", quality=88, method=5)
    os.remove("/tmp/_spr.png")
    print(f"  wrote 07_handle_sprite.webp    {os.path.getsize(OUT+'07_handle_sprite.webp')//1024:4d}KB")

    # the numbers index.html needs, so the two never drift apart
    print("\nCSS geometry for index.html (image is %dx%d):" % (w, h))
    print(f"  --spr-l:{100*x0/w:.4f}%;  --spr-t:{100*y0/h:.4f}%;")
    print(f"  --spr-w:{100*(x1-x0)/w:.4f}%; --spr-h:{100*(y1-y0)/h:.4f}%;")
    print(f"  --pivot:{100*(PIVOT_Y-y0)/(y1-y0):.2f}%;   (hinge at y={PIVOT_Y})")


if __name__ == "__main__":
    main()
