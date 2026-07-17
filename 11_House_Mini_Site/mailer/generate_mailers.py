#!/usr/bin/env python3
"""
generate_mailers.py — bespoke, data-driven homeowner mailer, one per address.

Every mailer is generated from that property's OWN report doc
(system_monitor.property_reports): its real competitor count, comparable sales,
buyer profile, school-walk distance, hero photo and aerial parcel — plus a QR
pointing at that home's /your-home/<slug>. Postal address, data and QR all come
from the same record, so nothing can drift.

The QR opens a report that MUST already exist (build_state=complete) with an
approved competition/scarcity slot — otherwise the headline numbers would be
missing. The generator refuses addresses that aren't ready.

USAGE:
  python3 generate_mailers.py --slug 25-huntingdale-crescent-robina
  python3 generate_mailers.py --all-complete --combine
  python3 generate_mailers.py --slug <s> --dry-run     # print the extracted copy, no PDF
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

import requests
import qrcode
from weasyprint import HTML

from shared.db import get_client  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "mailer_template.html")
ASSETS = os.path.join(HERE, "assets")
GEN = os.path.join(ASSETS, "gen")
OUT = os.path.join(HERE, "output")
BASE_URL = "https://fieldsestate.com.au"
UTM = "utm_source=mailer&utm_medium=print&utm_campaign=home_report"
GREEN = (34, 56, 44)
PAPER = (253, 243, 236)


# ---------- helpers ----------
def parse_address(address):
    parts = [p.strip() for p in address.split(",") if p.strip()]
    street = parts[0]
    locality = " ".join(parts[1:]).upper()
    return street, locality


def download(url, dest):
    r = requests.get(url, timeout=45, allow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Fields mailer)"})
    r.raise_for_status()
    if len(r.content) < 800:
        raise ValueError(f"tiny image {len(r.content)}B")
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def make_qr(slug):
    url = f"{BASE_URL}/your-home/{slug}?{UTM}"
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=20, border=4)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color=GREEN, back_color=PAPER)
    os.makedirs(os.path.join(GEN, slug), exist_ok=True)
    path = os.path.join(GEN, slug, "qr.png")
    img.save(path)
    return url, f"assets/gen/{slug}/qr.png"


def fmt_date(dt):
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt[:10]
    if isinstance(dt, datetime):
        return dt.strftime("%-d %b %Y")
    return ""


# ---------- extraction ----------
def extract(doc):
    """Pull every dynamic value the mailer needs. Raises if a headline field is missing."""
    slug = doc["slug"]
    street, locality = parse_address(doc["address"])
    suburb = (doc.get("suburb") or "").replace("_", " ").title()

    sf = doc.get("scarcity_features") or {}
    comps_block = doc.get("comparables") or {}
    val = doc.get("valuation") or {}
    mr = val.get("model_range") or {}
    pois = doc.get("pois") or []
    pos = doc.get("positioning") or {}
    slot = doc.get("slot_status") or {}

    total_active = sf.get("active_listings_total")
    true_comp = len(comps_block.get("closest_active") or [])
    full_stack = sf.get("active_matching_full_stack")
    comps_reviewed = mr.get("comp_count") or len(val.get("comps") or [])

    # nearest school
    school = next((p for p in pois if p.get("category") == "school"), None)
    school_name = school.get("name") if school else None
    school_m = school.get("walkMetres") if school else None

    # buyer persona (first labelled)
    personas = pos.get("personas") or []
    persona = next((p.get("label") for p in personas if isinstance(p, dict) and p.get("label")), None)

    # imagery
    photos = (doc.get("property") or {}).get("photos") or []
    hero = photos[0]["url"] if photos else None
    aerial = ((doc.get("property") or {}).get("satellite") or {}).get("satellite_image_url")

    updated = fmt_date(comps_block.get("generated_at") or doc.get("activity_refreshed_at")
                       or doc.get("build_completed_at"))

    # ---- readiness gate ----
    missing = [n for n, v in [
        ("total_active", total_active), ("true_competitors", true_comp or None),
        ("comps_reviewed", comps_reviewed), ("school", school_name),
        ("persona", persona), ("hero_photo", hero), ("aerial", aerial),
    ] if not v]
    if slot.get("scarcity") != "approved" or slot.get("competitor_matches") != "approved":
        missing.append("scarcity/competitor slot not approved")
    if missing:
        raise ValueError("not ready — missing: " + ", ".join(missing))

    return {
        "slug": slug, "street": street, "locality": locality, "suburb": suburb,
        "total_active": total_active, "true_comp": true_comp, "full_stack": full_stack,
        "comps_reviewed": comps_reviewed, "school": school_name, "school_m": school_m,
        "persona": persona, "hero": hero, "aerial": aerial, "updated": updated,
    }


def render(ctx, dry=False):
    slug = ctx["slug"]
    url, qr_rel = make_qr(slug)
    gdir = os.path.join(GEN, slug)
    hero_rel = f"assets/gen/{slug}/hero.jpg"
    aer_rel = f"assets/gen/{slug}/aerial.png"
    if not dry:
        download(ctx["hero"], os.path.join(gdir, "hero.jpg"))
        download(ctx["aerial"], os.path.join(gdir, "aerial.png"))

    repl = {
        "{{STREET}}": ctx["street"], "{{LOCALITY}}": ctx["locality"], "{{SUBURB}}": ctx["suburb"],
        "{{TRUE_COMP}}": str(ctx["true_comp"]), "{{TOTAL_ACTIVE}}": str(ctx["total_active"]),
        "{{FULL_STACK}}": str(ctx["full_stack"]), "{{COMPS_REVIEWED}}": str(ctx["comps_reviewed"]),
        "{{SCHOOL}}": ctx["school"], "{{SCHOOL_M}}": str(ctx["school_m"]),
        "{{PERSONA}}": ctx["persona"], "{{HERO_IMG}}": hero_rel, "{{AERIAL_IMG}}": aer_rel,
        "{{QR_IMG}}": qr_rel,
    }
    html = open(TEMPLATE, encoding="utf-8").read()
    for k, v in repl.items():
        html = html.replace(k, v)

    print(f"  ✓ {ctx['street']}, {ctx['locality']}")
    print(f"      hook: Only {ctx['true_comp']} of {ctx['total_active']} homes compete · "
          f"{ctx['comps_reviewed']} comps · {ctx['school_m']}m to {ctx['school']} · buyer: {ctx['persona']}")
    print(f"      QR → {url}")
    if dry:
        return None
    os.makedirs(OUT, exist_ok=True)
    out_pdf = os.path.join(OUT, f"{slug}.pdf")
    HTML(string=html, base_url=HERE).write_pdf(out_pdf)
    return out_pdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", nargs="+")
    ap.add_argument("--all-complete", action="store_true")
    ap.add_argument("--combine", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.slug and not args.all_complete:
        ap.error("pass --slug <slug...> or --all-complete")

    col = get_client()["system_monitor"]["property_reports"]
    q = {"slug": {"$in": args.slug}} if args.slug else {"build_state": "complete"}
    docs = list(col.find(q))
    if not docs:
        print("No matching reports.")
        return

    print(f"{'DRY RUN — ' if args.dry_run else ''}generating {len(docs)} mailer(s):")
    pdfs = []
    for d in docs:
        try:
            ctx = extract(d)
            p = render(ctx, dry=args.dry_run)
            if p:
                pdfs.append(p)
        except Exception as e:
            print(f"  ✗ {d.get('slug')}: {e}")

    if args.combine and pdfs:
        from pypdf import PdfWriter
        w = PdfWriter()
        for p in pdfs:
            w.append(p)
        combined = os.path.join(OUT, "all_mailers.pdf")
        with open(combined, "wb") as f:
            w.write(f)
        print(f"\nCombined → {combined} ({len(pdfs)} recipients)")
    print(f"\nDone. {len(pdfs)} PDF(s).")


if __name__ == "__main__":
    main()
