#!/usr/bin/env python3
"""generate_conjunction_landing.py — turn a conjunction property into a buyer-
acquisition landing page from CONFIG, not hand-coded HTML.

Background
----------
93 Burleigh Street was the first conjunction property (a home listed by ANOTHER
agency for which Fields runs a buyer-acquisition conjunction — see
`scripts/conjunction_register.py`). Its landing page
(`public/93-burleigh-street/index.html`) was hand-built. This generator
templatises that page so the *next* conjunction is a config file, not a fresh
copy-paste of 300 lines of HTML.

Design
------
* SECTION-DRIVEN. A config lists sections in order; each has a `type` and its
  data. A section whose essential content is missing renders NOTHING (no empty
  shell). Section numbers (01, 02, …) are assigned by render order, so omitting
  a section renumbers the rest cleanly.
* FACTS come from our shared libs where we have them, so a config author does
  not re-key numbers we already computed:
    - shared.floor_area.resolve_internal_floor_area  (internal area, never total)
    - shared.block_geometry.compute_block_geometry    (frontage/depth/shape)
    - shared.planning_signals via zoning_data.cityplan (redevelopment signals)
    - scripts.conjunction_register.get(slug)          (agent, agency, price,
                                                        landing_url, inspection)
  A config value always overrides an auto-pulled fact (author knows best), and a
  `{{token}}` placeholder in config text is filled from the fact bag.
* RULE 5 (editorial) is enforced in code, not left to the author:
    - The "this is NOT a Fields valuation" methodology + disclaimer block and the
      footer disclaimer are MANDATORY and NON-REMOVABLE. Config cannot blank them.
    - Any `$` / range claim anywhere in the body FORCES the methodology/disclaimer
      block to render (the pre-flight): if it somehow didn't, we inject it.
* LISTING-AGENT ATTRIBUTION is MANDATORY. If the register has no listing agent
  for this slug, the generator FAILS LOUDLY rather than shipping a page that
  looks like Fields is the selling agent.
* The lead form POSTs to `/.netlify/functions/campaign-lead` with the property
  slug and a per-property `source` tag.
* `noindex` by default (a conjunction page must be cleared by the listing agent
  before it goes live — see the register's approval_status).
* NO external template engine — plain Python string building only, so the output
  is a single self-contained file (matches the static-page / artifact constraint).

Usage
-----
    python3 scripts/generate_conjunction_landing.py --slug 93-burleigh-street-burleigh-waters
    python3 scripts/generate_conjunction_landing.py --slug SLUG --config path/to.json --out /tmp/x.html
    python3 scripts/generate_conjunction_landing.py --slug SLUG --print-facts   # show the fact bag only

By default the page is written to a SCRATCH path and the website working-tree
path is only printed, never overwritten, unless --write-tree is passed AND the
page has been reviewed. This tool generates artefacts for review; it never
deploys, never pushes to the website repo, and never removes noindex.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime

# Make `shared` / `scripts` importable whether run from repo root or scripts/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
WEBSITE_PUBLIC = "/home/fields/Feilds_Website/01_Website/public"
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "conjunction_landing_configs")

# --------------------------------------------------------------------------- #
# Brand CSS — copied verbatim from the hand-built 93 page so every generated
# page is byte-for-byte the same look. Do NOT edit casually; it is the brand.
# --------------------------------------------------------------------------- #
BRAND_CSS = """  :root{
    --green:#22382C; --green-2:#2d4a3a; --cream:#fdf9f0; --panel:#f5f2ee;
    --line:#E6DDD2; --ink:#2d4a3a; --muted:#7a8a80; --accent:#B76749; --accent-soft:#c9836a;
    --gold:#FEC66F; --mint:#A0D1C9;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Poppins','Helvetica Neue',Helvetica,Arial,sans-serif;background:var(--cream);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
  img{max-width:100%;display:block}
  .wrap{max-width:860px;margin:0 auto;padding:0 22px}
  a{color:var(--accent)}
  /* header */
  header.site{background:var(--green);color:#fff;padding:14px 0}
  header.site .wrap{display:flex;align-items:center;gap:10px}
  header.site .logo{font-weight:800;font-size:1.15rem;letter-spacing:.5px}
  header.site .tag{font-size:.78rem;color:var(--mint);font-weight:300}
  /* hero */
  .hero{background:var(--green);color:#fff;padding:6px 0 40px}
  .hero img{border-radius:12px;margin:0 0 22px;box-shadow:0 12px 40px rgba(0,0,0,.25)}
  .eyebrow{font-size:.72rem;letter-spacing:2.5px;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:10px}
  .hero h1{font-size:2.1rem;font-weight:700;line-height:1.15;margin-bottom:10px}
  .hero .sub{font-size:1.12rem;color:#dfeae4;font-weight:300;max-width:640px}
  .hero .price{display:inline-flex;align-items:baseline;gap:12px;margin-top:22px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);border-radius:10px;padding:12px 18px}
  .hero .price b{font-size:1.5rem;font-weight:700;color:#fff}
  .hero .price span{font-size:.8rem;color:var(--mint);text-transform:uppercase;letter-spacing:1.5px}
  .cta-row{margin-top:20px;display:flex;gap:12px;flex-wrap:wrap}
  .btn{display:inline-block;background:var(--gold);color:var(--green);font-weight:600;padding:13px 22px;border-radius:8px;text-decoration:none;font-size:.95rem;border:none;cursor:pointer}
  .btn.ghost{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.35)}
  .btn:hover{opacity:.92}
  /* sections */
  section{padding:34px 0;border-bottom:1px solid var(--line)}
  h2{font-size:1.45rem;color:var(--green);font-weight:700;margin-bottom:8px}
  h2 .n{color:var(--accent-soft);font-weight:600;margin-right:10px}
  .lead-p{font-size:1.08rem;margin-bottom:14px}
  p{margin-bottom:12px}
  ul{margin:0 0 14px 20px}
  li{margin-bottom:7px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:640px){.grid2{grid-template-columns:1fr}.hero h1{font-size:1.7rem}}
  .card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:18px}
  .card h3{font-size:1rem;color:var(--green);margin-bottom:8px}
  .card.for h3::before{content:"✓ ";color:#3f7d5f}
  .card.against h3::before{content:"— ";color:var(--accent)}
  /* table */
  .tbl-scroll{overflow-x:auto;margin:6px 0 10px;border:1px solid var(--line);border-radius:10px}
  table{border-collapse:collapse;width:100%;font-size:.86rem;background:#fff;min-width:520px}
  th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line)}
  th{background:var(--panel);color:var(--green);font-weight:600;font-size:.76rem;text-transform:uppercase;letter-spacing:.5px}
  tr:last-child td{border-bottom:none}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .subject-row td{background:#fbf4ec;font-weight:600}
  .stat-row{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0}
  .stat{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 18px;flex:1;min-width:150px}
  .stat b{display:block;font-size:1.5rem;color:var(--green);font-weight:700}
  .stat span{font-size:.8rem;color:var(--muted)}
  .note{font-size:.82rem;color:var(--muted);font-style:italic;margin-top:8px}
  .flood{background:#f2f7f5;border:1px solid var(--mint);border-radius:10px;padding:18px}
  .callout{background:var(--green-2);color:#fff;border-radius:10px;padding:20px;margin:8px 0}
  .callout h3{color:var(--gold);margin-bottom:8px}
  /* form */
  .form-wrap{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px}
  .form-wrap label{display:block;font-size:.82rem;color:var(--green);font-weight:600;margin:12px 0 5px}
  .form-wrap input,.form-wrap select,.form-wrap textarea{width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:8px;font-family:inherit;font-size:.95rem;background:var(--cream)}
  .form-wrap textarea{min-height:70px;resize:vertical}
  .consent{display:flex;gap:9px;align-items:flex-start;margin:14px 0;font-size:.8rem;color:var(--muted)}
  .consent input{width:auto;margin-top:3px}
  #formMsg{margin-top:12px;font-size:.9rem;font-weight:600}
  /* agent / disclaimer */
  .agent-bar{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;font-size:.9rem}
  .agent-bar b{color:var(--green)}
  footer{background:var(--green);color:#cfe0d7;padding:28px 0;font-size:.8rem}
  footer .wrap{display:flex;flex-direction:column;gap:8px}
  .disc{font-size:.75rem;color:var(--muted);line-height:1.5}
  .methodology{background:var(--panel);border-radius:10px;padding:16px 18px;font-size:.82rem;color:#4a5e52}
  .methodology summary{cursor:pointer;font-weight:600;color:var(--green);font-size:.9rem}
  .methodology[open] summary{margin-bottom:10px}"""

# The one paragraph Rule 5 requires on any page carrying a $ claim, and which
# config CANNOT edit or remove. `{agency}` and `{price}` are filled in.
MANDATORY_VALUATION_DISCLAIMER = (
    "<p><b>This page does not state a Fields valuation of {short}.</b> "
    "{price} is the seller's guide, not our estimate of the home's worth. Our "
    "comparable-sales model does not produce a single-figure valuation for a "
    "property of this size and type. The comparable sales above are facts about "
    "other properties; what this home is worth is for a buyer to judge. Our sold "
    "records are not a complete census of every sale — a sale we did not "
    "capture would not appear here.</p>"
)

# Footer disclaimer — mandatory, non-removable, built from register facts.
FOOTER_DISCLAIMER = (
    "This page is prepared by Fields Real Estate to assist buyers. {address} is "
    "listed for sale by {agency}; the seller's guide is {price}. Figures on this "
    "page are drawn from Fields' property data, Domain and onthehouse listing "
    "records, Queensland cadastral data and Gold Coast City Council mapping, and "
    "are provided in good faith without warranty of accuracy — prospective "
    "purchasers should make their own enquiries. Nothing on this page is a "
    "valuation of the property, financial advice, or a recommendation to buy. "
    "Comparable sales describe other properties and do not establish this "
    "property's value."
)

# Agent attribution bar — mandatory, non-removable, built from the register.
AGENT_BAR = (
    "<b>Listing agent:</b> {agent}, {agency}. {short} is listed and sold by "
    "{agency}. Fields Real Estate is helping find a buyer for it and will "
    "introduce genuine enquiries to the listing agent — the sale, price, "
    "inspections and negotiation are handled by {agency}."
)

_MONEY_RE = re.compile(r"\$\s?\d")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def esc_text(s) -> str:
    """Escape for element text (not attributes): apostrophes stay literal, so
    heading/label copy reads as the author wrote it. <>& are still escaped."""
    return html.escape("" if s is None else str(s), quote=False)


def fill(text: str, facts: dict) -> str:
    """Fill `{{token}}` placeholders in author text from the fact bag. A missing
    token is left visibly as `{{token}}` so it is caught in review, never blanked."""
    if not isinstance(text, str):
        return text

    def repl(m):
        key = m.group(1).strip()
        val = facts.get(key)
        return str(val) if val is not None else m.group(0)

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", repl, text)


def _truthy(x) -> bool:
    if x is None:
        return False
    if isinstance(x, (list, dict, str)):
        return len(x) > 0
    return bool(x)


# --------------------------------------------------------------------------- #
# Fact gathering — pull what we can from shared libs + the property doc so the
# config author doesn't re-key computed numbers.
# --------------------------------------------------------------------------- #
def _load_property_doc(slug=None, pid=None, address=None):
    """Best-effort load of the Gold_Coast property document. Returns dict|None.
    Never raises on a miss — a config can supply everything itself."""
    try:
        from shared.db import get_client
    except Exception:
        return None
    try:
        client = get_client()
    except Exception:
        return None
    db = client["Gold_Coast"]
    # Try by _id first (fast), else scan suburb collections by slug/address.
    if pid:
        try:
            from bson import ObjectId
            for coll in db.list_collection_names():
                d = db[coll].find_one({"_id": ObjectId(pid)}) if len(pid) == 24 else None
                if d:
                    return d
        except Exception:
            pass
    query = None
    if slug:
        query = {"url_slug": slug}
    elif address:
        query = {"address": address}
    if query:
        for coll in db.list_collection_names():
            try:
                d = db[coll].find_one(query)
            except Exception:
                continue
            if d:
                return d
    return None


def gather_facts(slug, register, doc, config) -> dict:
    """Assemble the fact bag from register + property doc + shared libs. Config
    always wins on collision (author knows best)."""
    facts = {}

    # --- from the register (source of truth for agent / price / inspection) ---
    facts["listing_agent"] = register.get("listing_agent")
    facts["listing_agency"] = register.get("listing_agency")
    facts["landing_url"] = register.get("landing_url")
    facts["lead_source_tag"] = register.get("lead_source_tag") or f"campaign_landing_{re.sub(r'[^a-z0-9]+', '_', slug.lower()).strip('_')}"
    facts["property_slug"] = register.get("property_slug") or slug
    facts["property_id"] = register.get("property_id")
    facts["inspection_at"] = register.get("inspection_at")
    facts["price"] = register.get("price") or config.get("price")

    # --- address ---
    facts["address"] = (config.get("address") or register.get("address")
                        or (doc.get("address") if doc else None))
    facts["short_address"] = (config.get("short_address")
                              or _short_address(facts["address"]))

    # --- from the property doc via shared libs ---
    if doc:
        try:
            from shared.floor_area import resolve_internal_floor_area
            val, src, conflict = resolve_internal_floor_area(doc)
            if val is not None and not conflict:
                facts["internal_area_sqm"] = int(round(val))
                facts["internal_area_source"] = src
        except Exception:
            pass
        try:
            from shared.block_geometry import compute_block_geometry
            bg = compute_block_geometry(doc.get("cadastral_polygon"))
            if bg:
                facts["block"] = bg
                facts["frontage_m"] = bg.get("frontage_m_est")
                facts["depth_m"] = bg.get("depth_m_est")
                facts["block_shape"] = bg.get("shape_label")
        except Exception:
            pass
        cp = doc.get("cadastral_polygon") or {}
        facts["land_area_sqm"] = (config.get("land_area_sqm")
                                  or cp.get("lot_area_sqm")
                                  or (doc.get("zoning_data") or {}).get("cadastral_area_sqm"))
        zd = doc.get("zoning_data") or {}
        facts["zone"] = zd.get("zone")
        facts["cityplan"] = zd.get("cityplan")   # shared.planning_signals output
        # flood facts (for the flood explainer section, if the config uses them)
        for k in ("flood_designated_level_m", "flood_ground_level_m",
                  "flood_depth_description", "in_any_ica_zone"):
            if k in zd:
                facts[k] = zd[k]
        facts["aerial_boundary_url"] = doc.get("aerial_boundary_url")

    # --- config overrides everything above ---
    for k, v in config.items():
        if k == "sections":
            continue
        if _truthy(v):
            facts[k] = v

    return facts


def _short_address(address):
    """'93 Burleigh Street, Burleigh Waters, QLD 4220' -> '93 Burleigh Street'."""
    if not address:
        return None
    return str(address).split(",")[0].strip()


# --------------------------------------------------------------------------- #
# Section renderers — each returns HTML (already numbered) or "" to be omitted.
# Signature: fn(data: dict, facts: dict) -> str
# A section renders "" when its ESSENTIAL content is missing (no empty shells).
# --------------------------------------------------------------------------- #
def _heading(n, title):
    return f'    <h2><span class="n">{n:02d}</span>{esc_text(title)}</h2>\n'


def _sec_intro(d, f):
    lead = d.get("lead_p")
    stats = d.get("stats") or []
    body = d.get("body_html")
    if not (lead or stats or body):
        return ""
    out = []
    if lead:
        out.append(f'    <p class="lead-p">{fill(lead, f)}</p>\n')
    if stats:
        out.append('    <div class="stat-row">\n')
        for s in stats:
            out.append(f'      <div class="stat"><b>{esc(fill(s.get("value",""),f))}</b>'
                       f'<span>{esc(fill(s.get("label",""),f))}</span></div>\n')
        out.append('    </div>\n')
    if body:
        out.append(f'    <p>{fill(body, f)}</p>\n')
    return "".join(out)


def _sec_comps(d, f):
    rows = d.get("rows") or []
    if not rows:
        return ""   # a comps table with no comps is an empty shell -> omit
    cols = d.get("columns") or ["Sold", "Address", "Land", "Price", "Condition"]
    num_cols = set(d.get("num_columns", [2, 3]))   # indices right-aligned
    out = []
    if d.get("intro"):
        out.append(f'    <p>{fill(d["intro"], f)}</p>\n')
    out.append('    <div class="tbl-scroll">\n      <table>\n        <thead><tr>')
    for i, c in enumerate(cols):
        cls = ' class="num"' if i in num_cols else ""
        out.append(f'<th{cls}>{esc(c)}</th>')
    out.append('</tr></thead>\n        <tbody>\n')
    subj = d.get("subject_row")
    all_rows = [(r, False) for r in rows]
    if subj:
        all_rows.append((subj, True))
    for cells, is_subj in all_rows:
        tr = '          <tr class="subject-row">' if is_subj else '          <tr>'
        out.append(tr)
        for i, cell in enumerate(cells):
            cls = ' class="num"' if i in num_cols else ""
            out.append(f'<td{cls}>{esc(fill(cell, f))}</td>')
        out.append('</tr>\n')
    out.append('        </tbody>\n      </table>\n    </div>\n')
    if d.get("footer_html"):
        out.append(f'    <p>{fill(d["footer_html"], f)}</p>\n')
    # methodology <details> — the comps-methodology text is config, the
    # valuation disclaimer paragraph is MANDATORY and appended by the generator.
    out.append(_methodology_details(d.get("methodology_intro"), f))
    return "".join(out)


def _methodology_details(intro_html, f):
    """Render the methodology <details>. `intro_html` is the how-produced blurb
    (config); the not-a-valuation disclaimer is always appended, non-removable."""
    parts = ['    <details class="methodology">\n'
             '      <summary>How these figures were produced (and what this is not)</summary>\n']
    if intro_html:
        parts.append(f'      <p style="margin-top:10px">{fill(intro_html, f)}</p>\n')
    disc = MANDATORY_VALUATION_DISCLAIMER.format(
        short=esc(f.get("short_address") or "this property"),
        price=esc(f.get("price") or "The seller's guide"),
    )
    parts.append(f'      {disc}\n    </details>\n')
    return "".join(parts)


def _sec_bullets(d, f):
    items = d.get("items") or []
    if not items:
        return ""
    out = []
    if d.get("lead_p"):
        out.append(f'    <p class="lead-p">{fill(d["lead_p"], f)}</p>\n')
    out.append('    <ul>\n')
    for it in items:
        out.append(f'      <li>{fill(it, f)}</li>\n')
    out.append('    </ul>\n')
    if d.get("note"):
        out.append(f'    <p class="note">{fill(d["note"], f)}</p>\n')
    return "".join(out)


def _sec_prose(d, f):
    paras = d.get("paragraphs") or []
    lead = d.get("lead_p")
    if not (paras or lead):
        return ""
    out = []
    if lead:
        out.append(f'    <p class="lead-p">{fill(lead, f)}</p>\n')
    for p in paras:
        out.append(f'    <p>{fill(p, f)}</p>\n')
    if d.get("callout"):
        c = d["callout"]
        out.append('    <div class="callout">\n')
        if c.get("h3"):
            out.append(f'      <h3>{esc(fill(c["h3"], f))}</h3>\n')
        out.append(f'      <p style="margin:0">{fill(c.get("body",""), f)}</p>\n')
        out.append('    </div>\n')
    if d.get("note"):
        out.append(f'    <p class="note">{fill(d["note"], f)}</p>\n')
    return "".join(out)


def _sec_flood(d, f):
    bullets = d.get("bullets") or []
    if not bullets and not d.get("intro"):
        return ""
    out = ['    <div class="flood">\n']
    if d.get("intro"):
        out.append(f'      <p style="margin-bottom:10px">{fill(d["intro"], f)}</p>\n')
    if bullets:
        out.append('      <ul style="margin-bottom:10px">\n')
        for b in bullets:
            out.append(f'        <li>{fill(b, f)}</li>\n')
        out.append('      </ul>\n')
    if d.get("summary"):
        out.append(f'      <p style="margin:0">{fill(d["summary"], f)}</p>\n')
    out.append('    </div>\n')
    if d.get("note"):
        out.append(f'    <p class="note">{fill(d["note"], f)}</p>\n')
    return "".join(out)


def _sec_fit(d, f):
    good = d.get("for") or {}
    bad = d.get("against") or {}
    if not (good.get("items") or bad.get("items")):
        return ""
    out = ['    <div class="grid2">\n']
    for cls, blk in (("for", good), ("against", bad)):
        items = blk.get("items") or []
        if not items:
            continue
        out.append(f'      <div class="card {cls}"><h3>{esc(fill(blk.get("h3",""),f))}</h3>\n')
        out.append('        <ul style="margin-bottom:0">\n')
        for it in items:
            out.append(f'          <li>{fill(it, f)}</li>\n')
        out.append('        </ul>\n      </div>\n')
    out.append('    </div>\n')
    return "".join(out)


def _sec_enquiry(d, f):
    """The enquiry form section. The form POSTs to campaign-lead with the slug +
    per-property source tag. Always renders (it is the conversion point)."""
    lead = d.get("lead_p")
    options = d.get("interest_options") or [
        "The land and location", "Just want to know more"]
    interest_label = d.get("interest_label", "What interests you most about it?")
    out = []
    if lead:
        out.append(f'    <p class="lead-p">{fill(lead, f)}</p>\n')
    out.append('''    <div class="form-wrap">
      <form id="enquiryForm">
        <label for="name">Your name</label>
        <input id="name" name="name" type="text" autocomplete="name" placeholder="First and last name">
        <div class="grid2">
          <div><label for="phone">Phone</label><input id="phone" name="phone" type="tel" autocomplete="tel" placeholder="Mobile"></div>
          <div><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" placeholder="you@email.com"></div>
        </div>
''')
    out.append(f'        <label for="interest">{esc(interest_label)}</label>\n')
    out.append('        <select id="interest" name="interest">\n')
    out.append('          <option value="">Select one…</option>\n')
    for opt in options:
        out.append(f'          <option>{esc(opt)}</option>\n')
    out.append('''        </select>
        <label for="message">Anything you'd like to ask? (optional)</label>
        <textarea id="message" name="message" placeholder="e.g. can I inspect at another time? what's the building & pest position?"></textarea>
        <div class="consent">
          <input id="consent" name="consent" type="checkbox">
          <label for="consent" style="margin:0;font-weight:400;color:var(--muted)">I'm happy for Fields to contact me about this property and other properties that might suit me.</label>
        </div>
        <button type="submit" class="btn" id="submitBtn">Send enquiry</button>
        <div id="formMsg"></div>
      </form>
    </div>
''')
    # Mandatory listing-agent attribution bar directly under the form.
    agent_bar = AGENT_BAR.format(
        agent=esc(f["listing_agent"]),
        agency=esc(f["listing_agency"]),
        short=esc(f.get("short_address") or f.get("address") or "This property"),
    )
    out.append(f'\n    <div class="agent-bar" style="margin-top:18px">\n      {agent_bar}\n    </div>\n')
    return "".join(out)


SECTION_RENDERERS = {
    "intro": _sec_intro,
    "comps": _sec_comps,
    "bullets": _sec_bullets,
    "prose": _sec_prose,
    "flood": _sec_flood,
    "fit": _sec_fit,
    "enquiry": _sec_enquiry,
}

# Sections that carry a title but only free prose (map to _sec_prose).
_PROSE_ALIASES = {"spend", "downstairs", "redevelopment"}


# --------------------------------------------------------------------------- #
# Page assembly
# --------------------------------------------------------------------------- #
def build_page(slug, register, doc, config) -> str:
    facts = gather_facts(slug, register, doc, config)

    # --- MANDATORY: listing-agent attribution. Fail loudly if absent. ---
    if not facts.get("listing_agent") or not facts.get("listing_agency"):
        raise SystemExit(
            f"REFUSING to generate: the conjunction register has no listing "
            f"agent/agency for slug {slug!r}. A conjunction landing page MUST "
            f"attribute the listing agent (Rule 5 + conjunction guard). Seed the "
            f"register first: python3 scripts/conjunction_register.py --show {slug}")

    # --- render sections in order, dropping empties, numbering survivors ---
    body_sections = []
    enquiry_html = None
    enquiry_meta = None
    n = 0
    for sec in config.get("sections", []):
        stype = sec.get("type")
        renderer = SECTION_RENDERERS.get(
            "prose" if stype in _PROSE_ALIASES else stype)
        if renderer is None:
            raise SystemExit(f"unknown section type {stype!r} (known: "
                             f"{sorted(set(SECTION_RENDERERS) | _PROSE_ALIASES)})")
        inner = renderer(sec, facts)
        if not inner.strip():
            continue  # missing data -> omit cleanly, no empty shell
        n += 1
        anchor = f' id="{esc(sec["anchor"])}"' if sec.get("anchor") else ""
        heading = _heading(n, sec.get("heading", ""))
        block = f'  <section{anchor}>\n{heading}{inner}  </section>\n'
        if stype == "enquiry":
            enquiry_html = block
            enquiry_meta = sec
        else:
            body_sections.append(block)

    # --- Rule 5 pre-flight: any $ claim forces the methodology block ---
    joined = "".join(body_sections) + (enquiry_html or "")
    has_money = bool(_MONEY_RE.search(joined))
    has_methodology = "This page does not state a Fields valuation" in joined
    if has_money and not has_methodology:
        # Inject a standalone methodology section (non-removable safeguard).
        n_meth = len(body_sections) + 1
        details = _methodology_details(
            config.get("methodology_fallback_intro"), facts)
        body_sections.append(
            f'  <section>\n{_heading(n_meth, "How these figures were produced")}'
            f'{details}  </section>\n')
        # re-number the enquiry section if present
        # (enquiry is appended last in the final layout)

    # enquiry always renders last
    if enquiry_html:
        # renumber enquiry heading to be final
        final_n = len(body_sections) + 1
        enquiry_html = re.sub(r'<span class="n">\d+</span>',
                              f'<span class="n">{final_n:02d}</span>',
                              enquiry_html, count=1)
        body_sections.append(enquiry_html)

    # --- hero ---
    hero = _build_hero(config, facts)
    # --- head ---
    head = _build_head(config, facts)
    # --- footer (mandatory disclaimer) ---
    footer = _build_footer(facts)
    # --- script (form POST) ---
    script = _build_script(facts)

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        + head
        + "</head>\n<body>\n\n"
        + '<header class="site">\n  <div class="wrap"><span class="logo">Fields</span>'
          '<span class="tag">Smarter with data</span></div>\n</header>\n\n'
        + hero
        + '\n<div class="wrap">\n\n'
        + "\n".join(body_sections)
        + "\n</div>\n\n"
        + footer
        + "\n\n"
        + script
        + "\n</body>\n</html>\n"
    )


def _build_head(config, facts):
    title = config.get("title") or f"{facts.get('short_address','')} | Fields"
    desc = config.get("description", "")
    og_title = config.get("og_title", title)
    og_desc = config.get("og_description", desc)
    noindex = (
        "<!-- noindex until the listing agent / agency has cleared the page.\n"
        "     A conjunction page must be cleared before publishing. Remove this\n"
        "     tag to go live. -->\n"
        '<meta name="robots" content="noindex, nofollow">\n'
    )
    return (
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + noindex
        + f'<title>{esc(title)}</title>\n'
        + f'<meta name="description" content="{esc(desc)}">\n'
        + f'<meta property="og:title" content="{esc(og_title)}">\n'
        + f'<meta property="og:description" content="{esc(og_desc)}">\n'
        + '<meta property="og:type" content="website">\n'
        + '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">\n'
        + '<style>\n' + BRAND_CSS + '\n</style>\n'
    )


def _build_hero(config, facts):
    img = facts.get("hero_image") or facts.get("aerial_boundary_url")
    eyebrow = fill(config.get("eyebrow", ""), facts)
    h1 = fill(config.get("h1") or facts.get("short_address") or "", facts)
    sub = fill(config.get("hero_sub", ""), facts)
    price = facts.get("price")
    price_label = config.get("price_label", "Guide")
    cta_primary = config.get("cta_primary", "Ask about the property")
    cta_secondary = config.get("cta_secondary")
    cta_secondary_anchor = config.get("cta_secondary_anchor", "#numbers")
    img_alt = esc(config.get("hero_image_alt")
                  or (f"Aerial view of {facts.get('short_address','the property')}"))
    out = ['<div class="hero">\n  <div class="wrap">\n']
    if img:
        out.append(f'    <img src="{esc(img)}" alt="{img_alt}">\n')
    if eyebrow:
        out.append(f'    <div class="eyebrow">{eyebrow}</div>\n')
    out.append(f'    <h1>{esc(h1)}</h1>\n')
    if sub:
        out.append(f'    <p class="sub">{esc(sub)}</p>\n')
    if price:
        out.append(f'    <div class="price"><b>{esc(price)}</b>'
                   f'<span>{esc(price_label)}</span></div>\n')
    out.append('    <div class="cta-row">\n')
    out.append(f'      <a class="btn" href="#enquire">{esc(cta_primary)}</a>\n')
    if cta_secondary:
        out.append(f'      <a class="btn ghost" href="{esc(cta_secondary_anchor)}">'
                   f'{esc(cta_secondary)}</a>\n')
    out.append('    </div>\n  </div>\n</div>\n')
    return "".join(out)


def _build_footer(facts):
    disc = FOOTER_DISCLAIMER.format(
        address=esc(facts.get("address") or "This property"),
        agency=esc(facts["listing_agency"]),
        price=esc(facts.get("price") or "on application"),
    )
    return (
        '<footer>\n  <div class="wrap">\n'
        '    <div><b style="color:#fff">Fields</b> &mdash; property intelligence '
        'for the southern Gold Coast.</div>\n'
        f'    <div class="disc">\n      {disc}\n    </div>\n'
        '  </div>\n</footer>'
    )


def _build_script(facts):
    slug = esc(facts["property_slug"])
    source = esc(facts["lead_source_tag"])
    # Note: the JS below is copied structurally from the 93 page; only the slug
    # and source tag are per-property.
    return (
        '<script>\n'
        '  (function(){\n'
        "    var form = document.getElementById('enquiryForm');\n"
        "    var msg = document.getElementById('formMsg');\n"
        "    var btn = document.getElementById('submitBtn');\n"
        "    function ph(){ try{ return (window.posthog && window.posthog.get_distinct_id) ? window.posthog.get_distinct_id() : null; }catch(e){ return null; } }\n"
        "    form.addEventListener('submit', function(e){\n"
        "      e.preventDefault();\n"
        "      var phone = document.getElementById('phone').value.trim();\n"
        "      var email = document.getElementById('email').value.trim();\n"
        "      if(!phone && !email){ msg.style.color='#B76749'; msg.textContent='Please leave a phone number or an email so we can reach you.'; return; }\n"
        "      btn.disabled = true; btn.textContent = 'Sending…'; msg.textContent='';\n"
        "      var payload = {\n"
        "        name: document.getElementById('name').value,\n"
        "        phone: phone, email: email,\n"
        "        interest: document.getElementById('interest').value,\n"
        "        message: document.getElementById('message').value,\n"
        "        consent: document.getElementById('consent').checked,\n"
        f"        property_slug: '{slug}',\n"
        f"        source: '{source}',\n"
        "        posthog_distinct_id: ph()\n"
        "      };\n"
        "      fetch('/.netlify/functions/campaign-lead', {\n"
        "        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)\n"
        "      }).then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })\n"
        "      .then(function(res){\n"
        "        if(res.ok){ form.reset(); msg.style.color='#3f7d5f'; msg.textContent='Thanks — we’ll be in touch shortly.'; }\n"
        "        else { msg.style.color='#B76749'; msg.textContent = (res.j && res.j.error) || 'Something went wrong — please try again.'; btn.disabled=false; btn.textContent='Send enquiry'; }\n"
        "      }).catch(function(){ msg.style.color='#B76749'; msg.textContent='Something went wrong — please try again.'; btn.disabled=false; btn.textContent='Send enquiry'; });\n"
        "    });\n"
        "  })();\n"
        '</script>'
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_config(slug, path):
    if path:
        with open(path) as fh:
            return json.load(fh)
    default = os.path.join(CONFIG_DIR, f"{slug}.json")
    if os.path.exists(default):
        with open(default) as fh:
            return json.load(fh)
    raise SystemExit(
        f"No config found. Provide --config PATH or create {default}. "
        f"A config is required — the editorial sections cannot be invented.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a conjunction landing page from config")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--slug", help="conjunction property_slug (register key)")
    who.add_argument("--id", dest="pid", help="Gold_Coast property _id")
    who.add_argument("--address", help="property address")
    ap.add_argument("--config", help="path to config JSON (default: configs/<slug>.json)")
    ap.add_argument("--out", help="output path (default: a scratch path)")
    ap.add_argument("--write-tree", action="store_true",
                    help="ALSO write to the website working tree public/<slug>/index.html "
                         "(review artefact only; still noindex; never pushed)")
    ap.add_argument("--print-facts", action="store_true",
                    help="print the assembled fact bag and exit (no HTML)")
    args = ap.parse_args()

    from scripts.conjunction_register import get as reg_get  # local import for path

    # Resolve slug from the register (id/address paths look up the doc first).
    doc = _load_property_doc(slug=args.slug, pid=args.pid, address=args.address)
    slug = args.slug or (doc.get("url_slug") if doc else None)
    if not slug:
        raise SystemExit("Could not resolve a property_slug — pass --slug explicitly.")

    register = reg_get(slug)
    if not register:
        raise SystemExit(
            f"No conjunction registered for slug {slug!r}. Register it first:\n"
            f"  python3 scripts/conjunction_register.py --add property_slug={slug} "
            f"listing_agent=... listing_agency=... ...")

    if doc is None:
        doc = _load_property_doc(slug=slug, pid=register.get("property_id"))

    config = _load_config(slug, args.config)

    if args.print_facts:
        facts = gather_facts(slug, register, doc or {}, config)
        facts.pop("cityplan", None)  # too big to print
        facts.pop("block", None)
        print(json.dumps(facts, indent=2, default=str))
        return 0

    html_out = build_page(slug, register, doc or {}, config)

    # Default output = scratch path (NEVER overwrite the live tree silently).
    out = args.out or f"/tmp/conjunction_{slug}.html"
    with open(out, "w") as fh:
        fh.write(html_out)
    print(f"wrote {len(html_out):,} bytes -> {out}")

    tree_path = os.path.join(WEBSITE_PUBLIC, slug, "index.html")
    if args.write_tree:
        os.makedirs(os.path.dirname(tree_path), exist_ok=True)
        with open(tree_path, "w") as fh:
            fh.write(html_out)
        print(f"ALSO wrote website working tree -> {tree_path} (noindex; not pushed)")
    else:
        print(f"website tree path (NOT written; pass --write-tree to also write): {tree_path}")

    # Rule-5 self-checks the caller can eyeball.
    checks = {
        "noindex": 'content="noindex, nofollow"' in html_out,
        "not-a-Fields-valuation disclaimer": "does not state a Fields valuation" in html_out,
        f"listing agency ({register.get('listing_agency')})": (register.get("listing_agency") or "\0") in html_out,
        "campaign-lead form": "/.netlify/functions/campaign-lead" in html_out,
        "per-property source tag": register.get("lead_source_tag", "") in html_out if register.get("lead_source_tag") else True,
    }
    print("\nself-checks:")
    for k, v in checks.items():
        print(f"  [{'OK' if v else 'MISSING'}] {k}")
    if not all(checks.values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
