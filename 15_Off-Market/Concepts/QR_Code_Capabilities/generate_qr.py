#!/usr/bin/env python3
"""
generate_qr.py — build and round-trip verify every QR payload type that can put
a link (or a channel) onto a stranger's phone from a screen we control.

This is the measurement rig for the concept in README.md. The point is not that
it draws QR codes — anything does that. The point is that it reports, per
payload, the two numbers that actually decide whether a QR works when it is
shown on a screen rather than printed:

  · modules   — the QR grid size. A long payload forces a higher QR "version",
                more modules, finer detail, and a code that a phone camera
                cannot resolve off a glossy screen at arm's length.
  · min_mm    — the smallest physical width the code may be rendered at and
                still scan at ~30cm, derived from a 0.5mm minimum module size.

Every code is decoded again after generation (pyzbar, with an OpenCV fallback)
and the decoded string is compared byte-for-byte against the input. A QR that
does not round-trip is a QR that will not scan.

Usage:
    python3 generate_qr.py [--slug 5-chantilly-place-robina] [--out ./samples]
"""

import argparse
import os
import sys

import segno

SITE = "https://fieldsestate.com.au"
PHONE = "+61416529481"          # same number as the deck's SMS/WhatsApp save row
PAGE_ID = "889412530933297"     # Fields Facebook Page — messenger-webhook.mjs
EMAIL = "will@fieldsestate.com.au"

# Minimum module edge for reliable camera capture off a *screen* at ~30cm.
# Print can go finer; screen cannot — glare and subpixel rendering eat the
# margin. 0.5mm is the conservative floor used across scanner vendor guidance.
MIN_MODULE_MM = 0.5


def payloads(slug: str) -> dict:
    """Every payload variant, keyed by the name used in README.md."""
    deck_url = f"{SITE}/off-market/{slug}"
    address = slug.replace("-", " ").title()
    save_msg = (
        f"Hi Will - keeping my off-market plan for {address} handy. "
        f"My link: {deck_url}"
    )

    return {
        # --- Tier 1: opens a browser tab. Nothing is saved. ----------------
        "url": deck_url,

        # --- Tier 2: the phone's camera offers a native save action -------
        # vCard 3.0. iOS Camera and Android Lens both surface "Add to
        # Contacts". URL lands in the contact's website field and survives
        # forever with no backend at all.
        "vcard": (
            "BEGIN:VCARD\r\n"
            "VERSION:3.0\r\n"
            "N:Simpson;Will;;;\r\n"
            "FN:Will Simpson\r\n"
            "ORG:Fields Real Estate\r\n"
            "TITLE:Property Intelligence\r\n"
            f"TEL;TYPE=CELL:{PHONE}\r\n"
            f"EMAIL;TYPE=WORK:{EMAIL}\r\n"
            f"URL:{deck_url}\r\n"
            "END:VCARD\r\n"
        ),
        # MECARD — the compact alternative. Same "Add to Contacts" behaviour,
        # roughly half the bytes, so a materially coarser (more scannable) code.
        "mecard": (
            f"MECARD:N:Simpson,Will;TEL:{PHONE};EMAIL:{EMAIL};"
            f"URL:{deck_url};ORG:Fields Real Estate;;"
        ),

        # --- Tier 3: opens a two-way channel we own -----------------------
        # SMSTO is the widely-supported form; `sms:` with a body is honoured
        # inconsistently across Android launchers.
        "sms": f"SMSTO:{PHONE}:{save_msg}",
        "whatsapp": f"https://wa.me/{PHONE.lstrip('+')}?text={save_msg}",
        # The only one with a server behind it: messenger-webhook.mjs reads the
        # ref, auto-replies with the deck link, and pings Will on Telegram.
        "messenger": f"https://m.me/{PAGE_ID}?ref={slug}",
        "mailto": (
            f"mailto:{EMAIL}?subject=My off-market plan&body={save_msg}"
        ),
    }


def decode(path: str) -> str | None:
    """Decode a rendered PNG back to its payload. pyzbar first, OpenCV fallback."""
    try:
        from PIL import Image
        from pyzbar import pyzbar

        found = pyzbar.decode(Image.open(path))
        if found:
            return found[0].data.decode("utf-8")
    except Exception:
        pass
    try:
        import cv2

        got, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(path))
        return got or None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="5-chantilly-place-robina")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "samples"))
    ap.add_argument("--scale", type=int, default=10, help="pixels per module")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows, failures = [], 0

    for name, data in payloads(args.slug).items():
        # error='m' (15% recovery) is the right level for a screen: 'l' has no
        # margin for glare, 'h' inflates the module count for no real gain when
        # the surface cannot be physically damaged.
        qr = segno.make(data, error="m")
        path = os.path.join(args.out, f"{name}.png")
        # quiet_zone is not optional — a QR rendered flush against dark deck
        # chrome will not acquire. 4 modules is the spec minimum.
        qr.save(path, scale=args.scale, border=4, dark="#000000", light="#ffffff")

        modules = qr.symbol_size(scale=1, border=0)[0]
        min_mm = modules * MIN_MODULE_MM
        ok = decode(path) == data
        failures += 0 if ok else 1

        rows.append((name, len(data), f"{qr.version}", modules, f"{min_mm:.0f}", "PASS" if ok else "FAIL"))

    w = [max(len(str(r[i])) for r in rows + [("payload", "bytes", "ver", "modules", "min_mm", "rt")]) for i in range(6)]
    hdr = ("payload", "bytes", "ver", "modules", "min_mm", "round-trip")
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(hdr)))
    print("  ".join("-" * w[i] for i in range(6)))
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))

    print(f"\nWrote {len(rows)} PNGs to {args.out}")
    if failures:
        print(f"{failures} payload(s) failed round-trip decode", file=sys.stderr)
        return 1
    print("All payloads decoded back to their exact input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
