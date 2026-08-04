#!/usr/bin/env python3
"""
build_examples_index.py — the review gallery for the ten example decks.

Reads examples/index.json (what was built) and shots/index.json (what was shot)
and writes examples.html: every property, every card, desktop and mobile side by
side, with a link to the live deck.

Run after:
  python3 build_deck_preview.py --all
  node shoot_examples.js
"""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "examples.html"
E = lambda s: html.escape(str(s or ""), quote=True)

CARD_NAMES = {
    "card-00": "The hand-off", "card-01": "Recognition", "card-02": "The hook",
    "card-03": "The reveal", "card-04": "Why it matters", "card-05": "Competition",
    "card-06": "The comparable", "card-07": "Value drivers", "card-08": "The buyer",
    "card-09": "Valuation", "card-10": "The strategy",
}


def card_label(fname: str) -> str:
    # desktop-03-card-03.png -> "card-03"
    stem = fname.rsplit(".", 1)[0]
    cid = stem.split("-", 2)[2]
    return CARD_NAMES.get(cid, cid.replace("-", " "))


def main() -> None:
    built = {r["slug"]: r for r in json.loads((HERE / "examples" / "index.json").read_text())}
    shots = json.loads((HERE / "shots" / "index.json").read_text())

    sections = []
    for slug, devices in sorted(shots.items(),
                                key=lambda kv: built.get(kv[0], {}).get("suburb", "")):
        b = built.get(slug, {})
        desktop = devices.get("desktop", [])
        mobile = devices.get("mobile", [])
        rows = ""
        for i, d in enumerate(desktop):
            m = mobile[i] if i < len(mobile) else None
            rows += (
                f'      <div class="row">\n'
                f'        <div class="rowLabel"><span class="n">{i:02d}</span>'
                f'{E(card_label(d))}</div>\n'
                f'        <a class="shot d" href="shots/{E(slug)}/{E(d)}" target="_blank" rel="noopener">'
                f'<img loading="lazy" src="shots/{E(slug)}/{E(d)}" alt="desktop"></a>\n'
                + (f'        <a class="shot m" href="shots/{E(slug)}/{E(m)}" target="_blank" rel="noopener">'
                   f'<img loading="lazy" src="shots/{E(slug)}/{E(m)}" alt="mobile"></a>\n' if m else "")
                + f'      </div>\n')
        emblem = b.get("emblem")
        chip = (f'<span class="chip">{E(emblem)}</span>' if emblem
                else '<span class="chip none">no emblem · text-only angle</span>')
        sections.append(
            f'  <section class="prop" id="{E(slug)}">\n'
            f'    <header>\n'
            f'      <h2>{E(b.get("address") or slug)}<small>{E(b.get("suburb"))}</small></h2>\n'
            f'      <div class="meta"><span class="chip angle">{E(b.get("angle"))}</span>{chip}'
            f'<span class="chip">{b.get("cards", "?")} cards</span>'
            f'<a class="chip live" href="examples/{E(slug)}.html" target="_blank" rel="noopener">'
            f'open the deck →</a></div>\n'
            f'    </header>\n'
            f'    <div class="grid">\n'
            f'      <div class="head"><span></span><span>Desktop · 1440×900</span>'
            f'<span>Mobile · 390×844</span></div>\n{rows}'
            f'    </div>\n  </section>\n')

    nav = "".join(
        f'<a href="#{E(s)}">{E(built.get(s, {}).get("address") or s)}</a>'
        for s in sorted(shots, key=lambda s: built.get(s, {}).get("suburb", "")))

    OUT.write_text(PAGE.replace("{{NAV}}", nav)
                       .replace("{{SECTIONS}}", "".join(sections))
                       .replace("{{COUNT}}", str(len(sections))))
    print(f"wrote {OUT.relative_to(HERE.parent)}  ({OUT.stat().st_size / 1024:.0f} KB, "
          f"{len(sections)} properties)")


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>V3 deck — ten worked examples</title>
<style>
  :root {
    --ground:#000; --ink:#E6DDD2; --ink-soft:#CABEB0; --muted:#8C8177;
    --line:rgba(230,221,210,.13); --accent:#C0704A; --gold:#D28C5E;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
       line-height:1.55;padding:3rem clamp(1rem,4vw,3rem) 6rem}
  h1{font-family:var(--serif);font-weight:500;font-size:clamp(1.8rem,4.5vw,2.6rem);margin:0 0 .4rem}
  .sub{color:var(--muted);max-width:70ch;margin:0 0 2rem}
  nav{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:3rem;
      padding-bottom:1.5rem;border-bottom:1px solid var(--line)}
  nav a{color:var(--ink-soft);text-decoration:none;font-size:.85rem;
        border:1px solid var(--line);border-radius:999px;padding:.35rem .8rem}
  nav a:hover{border-color:var(--accent);color:var(--accent)}
  .prop{margin:0 0 4.5rem;scroll-margin-top:1rem}
  .prop header{margin-bottom:1.1rem}
  h2{font-family:var(--serif);font-weight:500;font-size:1.6rem;margin:0;
     display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap}
  h2 small{font-family:var(--sans);font-size:.85rem;color:var(--muted);
           letter-spacing:.12em;text-transform:uppercase}
  .meta{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.6rem}
  .chip{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
        border:1px solid var(--line);border-radius:999px;padding:.28rem .7rem}
  .chip.angle{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,transparent)}
  .chip.none{color:#8C8177;font-style:italic;text-transform:none;letter-spacing:.04em}
  .chip.live{color:var(--gold);border-color:color-mix(in srgb,var(--gold) 45%,transparent);
             text-decoration:none}
  .chip.live:hover{background:color-mix(in srgb,var(--gold) 12%,transparent)}
  .grid{border:1px solid var(--line);border-radius:10px;overflow:hidden}
  .head,.row{display:grid;grid-template-columns:11rem 1fr 22rem;gap:1rem;align-items:start}
  .head{padding:.7rem 1rem;background:rgba(230,221,210,.04);color:var(--muted);
        font-size:.7rem;letter-spacing:.14em;text-transform:uppercase}
  .row{padding:1rem;border-top:1px solid var(--line)}
  .rowLabel{color:var(--ink-soft);font-size:.9rem;display:flex;gap:.6rem;align-items:baseline}
  .rowLabel .n{color:var(--accent);font-variant-numeric:tabular-nums;font-size:.78rem}
  .shot{display:block;line-height:0}
  .shot img{width:100%;height:auto;border:1px solid var(--line);border-radius:6px;
            background:#000}
  .shot.m img{max-width:20rem}
  @media (max-width:900px){
    .head{display:none}
    .row{grid-template-columns:1fr;gap:.6rem}
  }
  footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--line);
         color:var(--muted);font-size:.85rem;max-width:76ch}
  code{color:var(--ink-soft);font-size:.86em}
</style>
</head>
<body>

<h1>V3 deck — {{COUNT}} worked examples</h1>
<p class="sub">Every card of every example, desktop and mobile. These are the real decks:
copy comes from each home's <code>offmarket_discovery</code> document and the drawing is
chosen by its <code>lead_angle</code>, so this is what the reader gets. Shots are clipped to
the whole card, not the viewport — several cards run taller than one phone screen, and a
viewport crop would hide the bottom of them. Click any shot for full size, or open the
live deck to see the intro and the reveals move.</p>

<nav>{{NAV}}</nav>

{{SECTIONS}}

<footer>
Built by <code>build_deck_preview.py --all</code>, shot by <code>shoot_examples.js</code>,
indexed by <code>build_examples_index.py</code>. Angle→drawing mapping is
<code>angle_media.yaml</code>; the emblem set is at <a href="reveals.html">reveals.html</a>.
</footer>

</body>
</html>
"""

if __name__ == "__main__":
    main()
