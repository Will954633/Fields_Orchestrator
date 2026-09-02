#!/usr/bin/env python3
"""Assemble the built teaser PDFs into a Pronto lay-up batch dir: pick the top-N
by engagement rank, rename to the manifest filename format build_pronto_print_pdf
expects (Fields_<flow>_<NN>_<slug>.pdf), and write manifest.csv (row = mailing
order). Then run build_pronto_print_pdf.py --verify/--write on it.
"""
import csv, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = sys.argv[1]                       # dir with <slug>.teaser.pdf + _built_slugs.json
N = int(sys.argv[2]) if len(sys.argv) > 2 else 50
FLOW = os.environ.get("TEASER_FLOW", "OT.1")  # e.g. OTN.1 = Owner Teaser No-note (no underscore: slug_of splits on _)
LAYUP = os.path.join(BATCH, "layup")
os.makedirs(LAYUP, exist_ok=True)

import re
built = json.load(open(os.path.join(BATCH, "_built_slugs.json")))   # rank order, successes only
addr_by_slug = {e["slug"]: e["address"] for e in json.load(open(os.environ.get("TEASER_BUILD_LIST", "/tmp/teaser_build_list_all98.json")))}

def resolve_pdf(slug):
    """The built filename can drop a trailing duplicate-doc suffix (-NNNN)."""
    p = os.path.join(BATCH, f"{slug}.teaser.pdf")
    if os.path.exists(p):
        return p, slug
    alt = re.sub(r"-\d+$", "", slug)
    p2 = os.path.join(BATCH, f"{alt}.teaser.pdf")
    return (p2, alt) if os.path.exists(p2) else (None, slug)

rows = []
for slug in built:                                  # rank order
    src, real = resolve_pdf(slug)
    if not src:
        print(f"  skip (no file): {slug}"); continue
    i = len(rows) + 1
    art = f"Fields_{FLOW}_{i:02d}_{real}.pdf"
    shutil.copyfile(src, os.path.join(LAYUP, art))
    rows.append({"artwork_file": art, "pages": 2, "flow_code": f"Fields_{FLOW}",
                 "slug": real, "address": addr_by_slug.get(slug, "")})
    if len(rows) >= N:
        break
if len(rows) < N:
    print(f"WARNING: only {len(rows)} assembled, wanted {N}")

with open(os.path.join(LAYUP, "manifest.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["artwork_file", "pages", "flow_code", "slug", "address"])
    w.writeheader(); w.writerows(rows)

print(f"assembled {len(rows)} pieces -> {LAYUP}")
print("running bleed-native lay-up --verify ...")
r = subprocess.run([sys.executable, os.path.join(HERE, "build_teaser_print_pdf.py"),
                    "--batch", LAYUP, "--verify"], text=True)
sys.exit(r.returncode)
