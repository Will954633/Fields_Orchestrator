#!/usr/bin/env python3
"""flood_reality.py — one-page "Flood: the map vs the numbers" buyer DD sheet.

Reads the property's stored flood fields (zoning_data, from GC City ArcGIS + ICA model)
and renders a Fields-branded A4 PDF. Honest by design: leads with the caveats, never
asserts "safe from flooding". Reusable per listing.

  python3 flood_reality.py --address "93 Burleigh Street, Burleigh Waters" \
      --agent "Tyler Benson" --agency "Coomera Realty" --out <path.pdf>
"""
import os, io, base64, argparse, datetime, subprocess
from PIL import Image
from weasyprint import HTML
import sys; sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db

LOGO = "/home/fields/Fields_Orchestrator/templates/fields-logo.png"

def logo_uri():
    im = Image.open(LOGO).convert("RGBA"); bg = Image.new("RGBA", im.size, (255,255,255,255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64,"+base64.b64encode(b.getvalue()).decode()

def find_flood(address):
    db = get_gold_coast_db()
    # collection from suburb in address
    sub = address.split(",")[1].strip().lower().replace(" ", "_") if "," in address else "burleigh_waters"
    d = db[sub].find_one({"address": {"$regex": "^"+address.split(",")[0], "$options":"i"}}, {"zoning_data":1})
    z = (d or {}).get("zoning_data", {})
    # flatten the flood-ish fields wherever they live
    out = {}
    def walk(o):
        if isinstance(o, dict):
            for k,v in o.items():
                if not isinstance(v,(dict,list)): out.setdefault(k, v)
                else: walk(v)
    walk(z)
    return out

def build(address, agent, agency, out):
    f = find_flood(address)
    dfl   = f.get("flood_designated_level_m")
    grd   = f.get("flood_ground_level_m")
    fb    = f.get("flood_freeboard_m")
    depth = f.get("flood_depth_description") or f.get("flood_depth_class")
    overlay = f.get("flood_description") or ("Flood Assessment Required" if f.get("flood_overlay") else "—")
    ica_clear = (f.get("in_any_ica_zone") is False)
    ica_note = f.get("ica_note","")
    street, suburb = address.split(",")[0].strip(), (address.split(",")[1].strip() if "," in address else "")
    today = datetime.date.today().strftime("%B %Y")
    # level diagram geometry (map 3.6–4.6 m AHD to 0–100%)
    def pct(v): return max(0, min(100, (v-3.6)/(4.6-3.6)*100))
    dfl_y, grd_y = 100-pct(dfl), 100-pct(grd)

    html = f"""<!doctype html><html><head><meta charset=utf-8><style>
@page {{ size:A4; margin:0; }} *{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Helvetica Neue',Arial,sans-serif;color:#20291f;font-size:10.5pt;line-height:1.5}}
.page{{width:210mm;min-height:297mm;padding:15mm 15mm 12mm;position:relative}}
.top{{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #2b3a30;padding-bottom:9px;margin-bottom:12px}}
.top img{{height:28px}} .tag{{color:#5c6b5a;font-size:9pt;letter-spacing:.14em;text-transform:uppercase}}
.kick{{color:#d9645b;font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:8.5pt}}
h1{{font-size:19pt;letter-spacing:-.02em;margin:2px 0}} .sub{{color:#5c6b5a;margin-bottom:12px}}
.lead{{background:#f4f6f2;border-left:3px solid #d9645b;padding:11px 14px;border-radius:0 6px 6px 0;margin-bottom:14px}}
h2{{font-size:11.5pt;color:#2b3a30;margin:15px 0 7px;padding-bottom:4px;border-bottom:1px solid #e3e8e1}}
.row{{display:flex;gap:16px}} .row>div{{flex:1}}
.diagram{{position:relative;height:150px;border:1px solid #dfe4dc;border-radius:8px;background:linear-gradient(to bottom,#eef3f7 0%,#eef3f7 var(--dfl),#dbeaf5 var(--dfl),#cfe3f2 100%);margin:6px 0}}
.line{{position:absolute;left:0;right:0;border-top:2px dashed #7aa7c7;font-size:8pt;color:#33627f;padding-left:6px}}
.line.dfl{{border-top:2px solid #d9645b;color:#b64236;font-weight:700}}
.line.grd{{border-top:2px solid #4a6b4f;color:#31502f;font-weight:700}}
.up{{position:absolute;top:8px;left:8px;font-size:8pt;color:#5c6b5a}}
ul{{margin:2px 0 4px 16px}} li{{margin-bottom:3px}}
.stat{{display:inline-block;background:#2b3a30;color:#fff;border-radius:6px;padding:5px 10px;margin:2px 3px 2px 0;font-size:9.5pt}}
.stat b{{font-size:11pt}}
.ica{{background:#eef4ee;border:1px solid #cfe0cf;border-radius:8px;padding:11px 14px;margin-top:6px}}
.do{{background:#fff;border:1px dashed #c7b98a;border-radius:8px;padding:11px 14px;margin-top:8px}}
.pending{{color:#8a7a3a;font-size:9.5pt;background:#fbf7e8;border-radius:6px;padding:8px 12px;margin-top:6px}}
.disc{{font-size:7.8pt;color:#8a9387;margin-top:14px;line-height:1.45}}
.foot{{position:absolute;bottom:8mm;left:15mm;right:15mm;font-size:7.8pt;color:#9aa397;border-top:1px solid #e3e8e1;padding-top:6px;display:flex;justify-content:space-between}}
</style></head><body><div class="page">
<div class="top"><img src="{logo_uri()}"><span class="tag">Smarter with data</span></div>
<div class="kick">Buyer due diligence &middot; Flood</div>
<h1>Flood: the map vs the numbers</h1>
<div class="sub">{street}, {suburb}</div>

<div class="lead">The council map flags this property (and most of {suburb}) for flood assessment &mdash;
that overlay is deliberately conservative and area-wide. The parcel-level numbers below tell a more
specific story. This sheet shows you the data and the sources so you can judge it, and points you to
the official searches that settle it.</div>

<div class="row">
<div>
<h2>1 &middot; The planning overlay</h2>
<p><b>{overlay}.</b> An area-wide City Plan overlay covering most of {suburb}. It triggers a flood
assessment for building work; it is <b>not</b> a statement that a property floods.</p>
<h2>2 &middot; The modelled flood level</h2>
<span class="stat">Designated level <b>{dfl} m AHD</b></span>
<span class="stat">Ground <b>{grd} m AHD</b></span>
<span class="stat">Modelled depth <b>{depth}</b></span>
<p style="margin-top:6px">In the defined (rare) flood event the ground sits about <b>{abs(fb):.2f} m
{'below' if fb and fb<0 else 'above'}</b> the designated level, with modelled depth <b>{depth}</b> &mdash;
so the <b>yard and any ground-level rooms</b> are the exposed part, not the whole home.</p>
</div>
<div>
<div class="diagram" style="--dfl:{dfl_y:.0f}%">
  <div class="up">Upstairs living &amp; 4 bedrooms &mdash; well above</div>
  <div class="line dfl" style="top:{dfl_y:.0f}%">Designated flood level {dfl} m AHD</div>
  <div class="line grd" style="top:{grd_y:.0f}%">Ground level {grd} m AHD</div>
</div>
<p style="font-size:8.5pt;color:#5c6b5a">Levels in metres AHD (Australian Height Datum). Ground level
is council's parcel-centre figure; the finished floor level is typically higher and is best confirmed
by a surveyor. This home is two-storey &mdash; the main living and bedrooms are upstairs.</p>
</div>
</div>

<h2>3 &middot; What the insurance industry's own model says</h2>
<div class="ica">{'<b>This parcel falls within NONE of the five ICA insurance flood-probability bands</b> (1-in-5-year through 1-in-2000-year).' if ica_clear else 'See ICA model result below.'}
<br><span style="font-size:9pt;color:#3a5a3c">{ica_note}</span></div>

<div class="pending"><b>Being added:</b> historical actual-inundation (did the 2017 and 2022 events reach
this block) &mdash; sourced from Queensland state flood studies; this sheet will be updated when confirmed.</div>

<h2>4 &middot; The searches that settle it (we recommend all three)</h2>
<div class="do"><ul>
<li><b>Council Flood Search certificate</b> &mdash; the official, letterhead version of the numbers above (City of Gold Coast, small fee).</li>
<li><b>An insurance quote for the address</b> &mdash; the real annual cost is the market pricing the risk in dollars; the most practical test there is.</li>
<li><b>A floor-level survey</b> &mdash; confirms the finished floor height against the designated level, especially for the downstairs zone.</li>
</ul></div>

<p class="disc">Sources: City of Gold Coast public planning &amp; flood data (City Plan flood overlay,
designated flood level, modelled flood depth, ICA Insurance Flood Event model) and Queensland elevation
data. Figures are modelled and indicative; ground level is a parcel-centre value, not a floor-level
survey. This is general information compiled to assist your enquiries &mdash; it is not a flood
certificate, a valuation, or financial, legal or insurance advice, and it does not state that the
property will or will not flood. Confirm with the City of Gold Coast, a licensed surveyor and your
insurer before you rely on it. Marketed in conjunction with {agent}, {agency}. Prepared {today}.</p>
<div class="foot"><span>Fields Real Estate &mdash; Smarter with data &middot; fieldsestate.com.au</span><span>{street} &middot; Flood DD</span></div>
</div></body></html>"""
    HTML(string=html).write_pdf(out)
    print("PDF ->", out, os.path.getsize(out), "bytes")
    print("data used:", {k:f.get(k) for k in ("flood_designated_level_m","flood_ground_level_m","flood_freeboard_m","flood_depth_description","in_any_ica_zone")})

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True); ap.add_argument("--agent", default="the listing agent")
    ap.add_argument("--agency", default=""); ap.add_argument("--out", required=True)
    a = ap.parse_args(); build(a.address, a.agent, a.agency, a.out)
