#!/usr/bin/env python3
"""
make_index.py -- build output/index.html, a comparison board for the variants.

Scans whatever is in output/ rather than hardcoding a list, so it stays true after
a rebuild. Reads each article's H1 so the board shows the actual opening line --
which is the thing being compared.

    python3 make_index.py
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")

try:
    from variants import VARIANTS
    DESCRIPTIONS = {k: v[1] for k, v in VARIANTS.items()}
except Exception:
    DESCRIPTIONS = {}
DESCRIPTIONS["report"] = "Original composition — states the finding, then evidences it"

ORDER = ["report", "anomaly", "anchor", "features", "timing", "contradiction"]

CSS = """
:root{--ink:#15171a;--muted:#5b6470;--rule:#e2e5ea;--bg:#fff;--accent:#0b6b4f;--band:#fafbfc}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
h1{font-size:1.7rem;margin:0 0 .4rem}
.sub{color:var(--muted);margin:0 0 2rem}
h2{font-size:1.15rem;margin:2.5rem 0 .3rem;padding-top:1.2rem;border-top:1px solid var(--rule)}
.desc{color:var(--muted);font-size:.92rem;margin:0 0 1rem}
.row{display:flex;gap:.6rem;flex-wrap:wrap;margin:0 0 .5rem}
a.card{flex:1 1 17rem;display:block;padding:.75rem .9rem;border:1px solid var(--rule);
 border-radius:8px;text-decoration:none;color:inherit;background:var(--band)}
a.card:hover{border-color:var(--accent)}
.addr{font-size:.78rem;letter-spacing:.05em;text-transform:uppercase;color:var(--accent);
 font-weight:600;margin-bottom:.25rem}
.h1line{font-size:.95rem;line-height:1.4}
.note{color:var(--muted);font-size:.88rem;margin:2.5rem 0 0;padding-top:1.2rem;
 border-top:1px solid var(--rule)}
@media (prefers-color-scheme:dark){
 :root{--ink:#e9ecf0;--muted:#9aa4b2;--rule:#2a2f36;--bg:#0f1114;--accent:#4fd1a5;--band:#151920}}
"""


def h1_of(path):
    try:
        with open(path.replace(".html", ".md")) as fh:
            for line in fh:
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return ""


def main():
    by_variant = defaultdict(list)
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".html") or f == "index.html":
            continue
        stem = f[:-5]
        variant = stem.split("--")[1] if "--" in stem else "report"
        addr = stem.split("--")[0].replace("-", " ").title()
        by_variant[variant].append((f, addr))

    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta name="robots" content="noindex">',
             "<title>Owner-subject article — variants</title>",
             f"<style>{CSS}</style></head><body><div class='wrap'>",
             "<h1>Owner-subject article — copy variants</h1>",
             "<p class='sub'>Same data, same gates, different opening move. "
             "Each variant opens an information gap and closes it in the same piece.</p>"]

    for v in ORDER + [k for k in by_variant if k not in ORDER]:
        if v not in by_variant:
            continue
        parts.append(f"<h2>{v}</h2>")
        parts.append(f"<p class='desc'>{DESCRIPTIONS.get(v, '')}</p>")
        parts.append("<div class='row'>")
        for f, addr in by_variant[v]:
            parts.append(f"<a class='card' href='{f}'><div class='addr'>{addr}</div>"
                         f"<div class='h1line'>{h1_of(os.path.join(OUT, f))}</div></a>")
        parts.append("</div>")

    parts.append("<p class='note'>Prototypes. Nothing here has been posted. "
                 "Every figure is minted from the data and every draft passes the "
                 "editorial guardrails, including the anti-tease rules added for these "
                 "variants.</p>")
    parts.append("</div></body></html>")

    dest = os.path.join(OUT, "index.html")
    with open(dest, "w") as fh:
        fh.write("\n".join(parts))
    total = sum(len(v) for v in by_variant.values())
    print(f"index written: {dest}  ({total} articles across {len(by_variant)} variants)")


if __name__ == "__main__":
    main()
