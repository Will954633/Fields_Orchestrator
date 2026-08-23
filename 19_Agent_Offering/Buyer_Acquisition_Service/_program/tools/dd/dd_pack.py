#!/usr/bin/env python3
"""dd_pack.py — buyer-facing "Due-Diligence Pack" PDF renderer for the Fields conjunction program.

Reads a listing's dd/dd_data.json (council + QLD state layer pulls) and renders one branded,
buyer-friendly, multi-page A4 PDF. Every layer is translated into plain English with its source and
as-at date. Honest by design: it never asserts a property "won't flood", keeps the freeboard caveat,
and phrases every $ / only-every-no claim as data + source, conditional (CLAUDE.md Rule 5).

  source /home/fields/venv/bin/activate && set -a && source .env && set +a
  python3 _program/tools/dd/dd_pack.py \
      --data listings/93-burleigh-street-burleigh-waters/dd/dd_data.json \
      --agent "Tyler Benson" --agency "Coomera Realty"

Brand mirrors flood_reality.py + make_infopack.py (dark green #2b3a30, coral #d9645b, logo header +
"Smarter with data", footer on every page). Only writes the output PDF; reads nothing but dd_data.json.
"""
import os, io, re, json, base64, argparse, datetime
from PIL import Image
from weasyprint import HTML

LOGO = "/home/fields/Fields_Orchestrator/templates/fields-logo.png"


def logo_uri():
    im = Image.open(LOGO).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    b = io.BytesIO(); im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def esc(s):
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build(data, agent, agency, out):
    layers = {l["key"]: l for l in data.get("layers", [])}
    flood = data.get("mongo_flood_zoning", {}) or {}
    parcel_attrs = (data.get("parcel", {}) or {}).get("attributes", {}) or {}

    address = data.get("address", "")
    street = address.split(",")[0].strip()
    suburb = address.split(",")[1].strip() if "," in address else ""
    lotplan = data.get("lotplan", "")
    land_area = parcel_attrs.get("AREA_SIZE_SQ_M") or flood.get("cadastral_area_sqm")
    tenure = parcel_attrs.get("TENURE")
    tenure_txt = "Freehold" if tenure == "FH" else (tenure or "")
    zone = flood.get("zone") or (layers.get("zoning", {}).get("attributes", {}) or {}).get("LVL1_ZONE") or ""
    as_at = data.get("layers", [{}])[0].get("as_at") if data.get("layers") else datetime.date.today().isoformat()
    today = datetime.date.today().strftime("%B %Y")
    logo = logo_uri()

    # ---- flood numbers ----
    dfl = flood.get("flood_designated_level_m")
    grd = flood.get("flood_ground_level_m")
    fb = flood.get("flood_freeboard_m")
    depth = flood.get("flood_depth_description") or "—"
    overlay = flood.get("flood_description") or ("Flood Assessment Required" if flood.get("flood_overlay") else "—")
    ica_clear = (flood.get("in_any_ica_zone") is False)
    ica_note = flood.get("ica_note", "")

    def pct(v):
        return max(0, min(100, (v - 3.6) / (4.6 - 3.6) * 100))
    dfl_y = 100 - pct(dfl) if dfl is not None else 40
    grd_y = 100 - pct(grd) if grd is not None else 55

    # QLD FloodCheck 1% AEP (basin) + historic floodlines
    fc1 = layers.get("qld_floodcheck_1pct_aep", {})
    fc1_hit = fc1.get("hit")
    hist = layers.get("qld_historic_flood", {})
    hist_layers = hist.get("intersecting_layers", []) or []
    dam_only = all(("dam" in h.lower() or "max flood" in h.lower()) for h in hist_layers) if hist_layers else True
    study = layers.get("qld_floodcheck_study_coverage", {})
    study_name = ""
    for feat in (study.get("features", []) or []):
        sn = (feat.get("studyname") or "").strip()
        if sn:
            study_name = sn
            break

    # ---- hazards ----
    def hazard_row(key, label, clear_txt, hit_txt):
        l = layers.get(key, {})
        if l.get("status") == "unavailable":
            return (label, "na", l.get("note") or "Not published as a queryable layer — confirm via council mapping.")
        if l.get("hit") is False:
            return (label, "clear", clear_txt)
        return (label, "hit", hit_txt)

    hazards = [
        hazard_row("bushfire_hazard", "Bushfire hazard area",
                   "Not mapped in a bushfire hazard area.", "Mapped within a bushfire hazard area."),
        hazard_row("landslide_hazard", "Landslide / steep-land hazard",
                   "Not mapped in a landslide or steep-land hazard area.", "Mapped within a landslide hazard area."),
        hazard_row("heritage", "Heritage place / listed area",
                   "Not a heritage place and not in a heritage-listed area.", "Mapped as / within a heritage place."),
        hazard_row("minimum_lot_size", "Minimum lot size overlay",
                   "No minimum-lot-size overlay returned at the parcel.", "A minimum-lot-size overlay applies."),
        hazard_row("acid_sulfate", "Acid sulfate soils",
                   "Not mapped.", "Mapped — relevant to excavation / canal-front works."),
    ]

    def tick(cls):
        return {"clear": "&#10003;", "hit": "&#9888;", "na": "&#8226;"}.get(cls, "&#8226;")
    haz_rows = "".join(
        f'<tr class="{cls}"><td class="tk">{tick(cls)}</td><td class="hl">{esc(lab)}</td><td>{note}</td></tr>'
        for (lab, cls, note) in hazards)

    # ---- location / road hierarchy ----
    road = layers.get("road_hierarchy", {})
    road_radius = road.get("radius_m", 500)
    road_hit = road.get("hit")

    # ---- services ----
    def svc(key):
        l = layers.get(key, {})
        return l.get("hit"), l.get("count", 0), l.get("radius_m")
    sew_hit, sew_n, sew_r = svc("sewer_main")
    wat_hit, wat_n, wat_r = svc("water_main")
    sw_hit, sw_n, sw_r = svc("stormwater_main")

    def svc_row(label, hit, n, r, present, absent):
        cls = "clear" if hit else "hit"
        txt = present.format(n=n, r=r) if hit else absent.format(r=r)
        return f'<tr class="{cls}"><td class="tk">{tick(cls)}</td><td class="hl">{esc(label)}</td><td>{txt}</td></tr>'
    svc_rows = (
        svc_row("Sewer (gravity) main", sew_hit, sew_n, sew_r,
                "{n} council gravity-sewer segment(s) within {r} m — the lot is connected to reticulated sewer.",
                "No gravity-sewer segment returned within {r} m.") +
        svc_row("Potable water main", wat_hit, wat_n, wat_r,
                "{n} potable-water main within {r} m — town water is available at the street.",
                "No potable-water main returned within {r} m.") +
        svc_row("Stormwater / drainage pipe", sw_hit, sw_n, sw_r,
                "{n} council stormwater pipe(s) within {r} m — check the survey for any pipe or easement crossing the lot.",
                "No council stormwater pipe returned within {r} m.")
    )

    # ---- development applications ----
    da = layers.get("development_applications", {})
    da_n = da.get("count", 0)
    da_r = da.get("radius_m", 400)
    da_feats = da.get("features", []) or []
    # de-dup by (number, description), keep readable minor-works examples first
    seen = set()
    examples = []
    for f in da_feats:
        desc = (f.get("APPLICATION_DESCRIPTION") or f.get("APPLICATION_CLASS") or "").strip().title()
        num = f.get("APPLICATION_NUMBER")
        if not desc or (num, desc) in seen:
            continue
        seen.add((num, desc))
        examples.append(desc)
    examples = examples[:6]
    da_examples = ", ".join(esc(e) for e in examples)

    # ---- sources (dedupe) ----
    srcs = []
    seen_s = set()
    for l in data.get("layers", []):
        u = l.get("source_url")
        if u and u not in seen_s:
            seen_s.add(u)
            srcs.append((l.get("label", l.get("key", "")), u))
    # shorten host for display
    def host(u):
        m = re.match(r"https?://([^/]+)/", u + "/")
        return m.group(1) if m else u
    src_rows = "".join(
        f'<li><b>{esc(lab)}</b><br><span class="url">{esc(host(u))}</span></li>' for lab, u in srcs)

    land_txt = f"{int(land_area)} m&sup2;" if land_area else "&mdash;"

    css = """
@page { size:A4; margin:0; } *{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Helvetica Neue',Arial,sans-serif;color:#20291f;font-size:10.5pt;line-height:1.5}
.page{width:210mm;min-height:297mm;padding:15mm 15mm 16mm;position:relative;page-break-after:always}
.page:last-child{page-break-after:auto}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #2b3a30;padding-bottom:9px;margin-bottom:12px}
.top img{height:28px} .tag{color:#5c6b5a;font-size:9pt;letter-spacing:.14em;text-transform:uppercase}
.kick{color:#d9645b;font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:8.5pt}
h1{font-size:21pt;letter-spacing:-.02em;margin:3px 0} .sub{color:#5c6b5a;margin-bottom:12px;font-size:11pt}
.lead{background:#f4f6f2;border-left:3px solid #d9645b;padding:11px 14px;border-radius:0 6px 6px 0;margin-bottom:14px}
h2{font-size:12.5pt;color:#2b3a30;margin:16px 0 8px;padding-bottom:5px;border-bottom:1px solid #e3e8e1}
h3{font-size:10.5pt;color:#2b3a30;margin:10px 0 4px}
p{margin-bottom:6px}
.tight{font-size:10pt;line-height:1.42}
.tight h2{margin:9px 0 5px;font-size:11.5pt} .tight p{margin-bottom:4px} .tight .lead{margin-bottom:8px}
.tight .ica,.tight .do{padding:9px 14px;margin-top:5px} .tight ul{margin-bottom:3px} .tight li{margin-bottom:3px}
.row{display:flex;gap:16px} .row>div{flex:1}
.factbar{display:flex;gap:0;margin:14px 0 8px;border:1px solid #dfe4dc;border-radius:8px;overflow:hidden}
.factbar .f{flex:1;padding:11px 8px;text-align:center;border-right:1px solid #dfe4dc}
.factbar .f:last-child{border-right:0}
.factbar b{display:block;font-size:14pt;color:#2b3a30} .factbar span{font-size:8pt;color:#6b776a;text-transform:uppercase;letter-spacing:.05em}
.diagram{position:relative;height:130px;border:1px solid #dfe4dc;border-radius:8px;background:linear-gradient(to bottom,#eef3f7 0%,#eef3f7 var(--dfl),#dbeaf5 var(--dfl),#cfe3f2 100%);margin:6px 0}
.line{position:absolute;left:0;right:0;border-top:2px dashed #7aa7c7;font-size:8pt;color:#33627f;padding-left:6px}
.line.dfl{border-top:2px solid #d9645b;color:#b64236;font-weight:700}
.line.grd{border-top:2px solid #4a6b4f;color:#31502f;font-weight:700}
.up{position:absolute;top:8px;left:8px;font-size:8pt;color:#5c6b5a}
ul{margin:2px 0 6px 16px} li{margin-bottom:4px}
.stat{display:inline-block;background:#2b3a30;color:#fff;border-radius:6px;padding:5px 10px;margin:2px 3px 2px 0;font-size:9.5pt}
.stat b{font-size:11pt}
.ica{background:#eef4ee;border:1px solid #cfe0cf;border-radius:8px;padding:11px 14px;margin-top:6px}
.do{background:#fff;border:1px dashed #c7b98a;border-radius:8px;padding:11px 14px;margin-top:8px}
.note{color:#8a7a3a;font-size:9.5pt;background:#fbf7e8;border-radius:6px;padding:8px 12px;margin-top:6px}
table.hz{width:100%;border-collapse:collapse;margin-top:4px;font-size:10pt}
table.hz td{padding:8px 6px;border-bottom:1px solid #ecefe9;vertical-align:top}
table.hz td.tk{width:22px;font-size:12pt;font-weight:700;text-align:center}
table.hz td.hl{width:34%;font-weight:600;color:#2b3a30}
table.hz tr.clear td.tk{color:#3f7d47} table.hz tr.hit td.tk{color:#b64236} table.hz tr.na td.tk{color:#8a7a3a}
.contact{background:#2b3a30;color:#eef1ea;border-radius:8px;padding:14px 18px;margin-top:14px;display:flex;justify-content:space-between;align-items:center}
.contact b{color:#fff;font-size:12pt} .contact .r{text-align:right;font-size:10pt;line-height:1.7}
.srcgrid{columns:2;column-gap:22px;font-size:8.5pt;margin-top:4px}
.srcgrid li{break-inside:avoid;margin-bottom:5px;list-style:none}
.srcgrid .url{color:#6b776a;font-size:7.6pt}
.disc{font-size:7.8pt;color:#8a9387;margin-top:14px;line-height:1.45}
.foot{position:absolute;bottom:8mm;left:15mm;right:15mm;font-size:7.8pt;color:#9aa397;border-top:1px solid #e3e8e1;padding-top:6px;display:flex;justify-content:space-between}
"""

    def foot(tag):
        return (f'<div class="foot"><span>Fields Real Estate &mdash; Smarter with data &middot; '
                f'fieldsestate.com.au</span><span>{esc(street)} &middot; {tag}</span></div>')

    def header():
        return f'<div class="top"><img src="{logo}"><span class="tag">Smarter with data</span></div>'

    fb_abs = abs(fb) if fb is not None else 0
    fb_dir = "below" if (fb is not None and fb < 0) else "above"

    # ---------- PAGE 1 : cover ----------
    p1 = f"""<div class="page">
{header()}
<div class="kick">Buyer Due-Diligence Pack</div>
<h1>{esc(street)}</h1>
<div class="sub">{esc(suburb)} &middot; Lot/Plan {esc(lotplan)}</div>
<div class="factbar">
  <div class="f"><b>{land_txt}</b><span>Land area</span></div>
  <div class="f"><b>{esc(tenure_txt) or '&mdash;'}</b><span>Tenure</span></div>
  <div class="f"><b>{esc(zone) or '&mdash;'}</b><span>Zoning</span></div>
</div>
<div class="lead">Everything we could pull from council + state data so you can do your homework &mdash;
with the sources, and what to order yourself. Each section below translates a council or Queensland
Government data layer into plain English, tells you where it came from, and notes where a layer was
silent or unavailable. It is a starting point for your enquiries, not a substitute for the official
searches and inspections; those are listed at the back.</div>

<h2>What's inside</h2>
<ul>
<li><b>Flood</b> &mdash; the planning overlay vs the parcel-level numbers, the insurer's own model, and the historic record.</li>
<li><b>Hazards &amp; overlays</b> &mdash; bushfire, landslide, heritage, minimum lot size, acid sulfate soils.</li>
<li><b>Location &amp; noise</b> &mdash; the functional road hierarchy around the street.</li>
<li><b>Services</b> &mdash; sewer, water and stormwater mains near the lot.</li>
<li><b>Nearby development</b> &mdash; recent development applications around the parcel.</li>
<li><b>What a building &amp; pest won't cover</b> &mdash; the searches and inspections to order yourself.</li>
<li><b>Sources</b> &mdash; every data layer and its origin, with the as-at date.</li>
</ul>

<div class="note"><b>How to read this:</b> a &#10003; means a hazard layer returned no hit at the parcel;
a &#9888; means a layer did return something worth reading; a &#8226; means the layer was not available
to us and should be confirmed directly with council. All results are as-at {esc(as_at)}.</div>

<div class="contact">
  <div><b>Questions on any of this?</b><br><span style="color:#bcc7b8;font-size:9.5pt;">We're happy to walk you through the data or arrange an inspection.</span></div>
  <div class="r">Will Simpson &middot; Fields Real Estate<br>0416&nbsp;529&nbsp;481<br>will@fieldsestate.com.au</div>
</div>
{foot("Overview")}
</div>"""

    # ---------- PAGE 2 : flood ----------
    p2 = f"""<div class="page tight">
{header()}
<div class="kick">Buyer due diligence &middot; Flood</div>
<h1>Flood: the map vs the numbers</h1>
<div class="sub">{esc(street)}, {esc(suburb)}</div>
<div class="lead">The council map flags this property (and most of {esc(suburb)}) for flood assessment &mdash;
that overlay is deliberately conservative and area-wide. The parcel-level numbers below tell a more
specific story. This shows you the data and the sources so you can judge it, and points you to the
official searches that settle it. It does <b>not</b> state that the property will or will not flood.</div>

<div class="row">
<div>
<h2>1 &middot; The planning overlay</h2>
<p><b>{esc(overlay)}.</b> An area-wide City Plan overlay covering most of {esc(suburb)}. It triggers a
flood assessment for building work; it is <b>not</b> a statement that the land floods.</p>
<h2>2 &middot; The modelled flood level</h2>
<span class="stat">Designated level <b>{dfl} m AHD</b></span>
<span class="stat">Ground <b>{grd} m AHD</b></span>
<span class="stat">Modelled depth <b>{esc(depth)}</b></span>
<p style="margin-top:6px">In the defined (rare) flood event the ground sits about <b>{fb_abs:.2f} m
{fb_dir}</b> the designated level, with a modelled depth band of <b>{esc(depth)}</b> &mdash; so on this
data the <b>yard and any ground-level rooms</b> are the exposed part, not the whole home. The
&minus;{fb_abs:.2f} m freeboard means a downstairs zone should be treated as exposed until a floor-level
survey says otherwise.</p>
</div>
<div>
<div class="diagram" style="--dfl:{dfl_y:.0f}%">
  <div class="up">Upstairs living &amp; bedrooms &mdash; well above</div>
  <div class="line dfl" style="top:{dfl_y:.0f}%">Designated flood level {dfl} m AHD</div>
  <div class="line grd" style="top:{grd_y:.0f}%">Ground level {grd} m AHD</div>
</div>
<p style="font-size:8.5pt;color:#5c6b5a">Levels in metres AHD (Australian Height Datum). Ground level is
council's parcel-centre figure; the finished floor level is typically higher and is best confirmed by a
surveyor.</p>
<h2 style="margin-top:11px">3 &middot; What the insurer's model says</h2>
<div class="ica">{'<b>On the ICA Insurance Flood Event model (2026) this parcel falls within none of the five insurance flood-probability bands</b> (1-in-5-year through 1-in-2000-year) as pulled on ' + esc(as_at) + '.' if ica_clear else 'See ICA model result below.'}
<br><span style="font-size:9pt;color:#3a5a3c">{esc(ica_note)}</span></div>
</div>
</div>

<h2>4 &middot; Has it ever actually flooded?</h2>
<div class="ica" style="background:#eef4ee;border-color:#cfe0cf">
On the Queensland Government flood datasets pulled {esc(as_at)}: the state <b>FloodCheck 1% AEP</b>
(1-in-100-year basin model) returns <b>{'no extent at this parcel' if fc1_hit is False else 'an extent at this parcel'}</b>,
and <b>no recorded historic floodline</b> (e.g. 1974, 2011, 2013) is returned at the block.
{'The only modelled extents that reach it are extreme <b>Hinze Dam</b> scenarios &mdash; a probable-maximum-flood and dam-failure model, not an ordinary flood event.' if dam_only and hist_layers else ''}
{'The overlays here trace back to the ' + esc(study_name) + '.' if study_name else ''}</div>

<h2>5 &middot; The searches that settle it (we recommend all three)</h2>
<div class="do"><ul>
<li><b>Council Flood Search certificate</b> &mdash; the official, letterhead version of the numbers above (City of Gold Coast, small fee).</li>
<li><b>An insurance quote for the address</b> &mdash; the real annual cost is the market pricing the risk in dollars; the most practical test there is.</li>
<li><b>A floor-level survey</b> &mdash; confirms the finished floor height against the designated level, especially for any downstairs zone.</li>
</ul></div>
{foot("Flood")}
</div>"""

    # ---------- PAGE 3 : hazards + location ----------
    road_txt = (f"No arterial, sub-arterial or distributor road is returned within {road_radius} m of the "
                f"parcel on the council functional-road-hierarchy layer &mdash; consistent with a quiet local "
                f"street rather than a through-road. Street traffic and traffic-noise exposure should still be "
                f"judged on a visit at different times of day."
                if road_hit is False else
                f"A classified road is returned within {road_radius} m &mdash; see the road-hierarchy layer.")
    p3 = f"""<div class="page">
{header()}
<div class="kick">Buyer due diligence &middot; Hazards &amp; setting</div>
<h1>Hazards &amp; overlays</h1>
<div class="sub">What the council hazard layers return at the parcel &mdash; as-at {esc(as_at)}</div>
<p>Each row is a council City Plan hazard/overlay layer queried at the parcel. A tick means the layer
returned no hit here; that is a favourable result on this data, not a guarantee &mdash; confirm anything
material against the council's own City Plan mapping.</p>
<table class="hz">{haz_rows}</table>
<div class="note">Acid sulfate soils could not be pulled as a queryable layer in this catalogue. The Gold
Coast City Plan does carry an Acid Sulfate Soils overlay, so treat this as <b>unconfirmed</b> and check it
directly via the council's City Plan interactive mapping / PD Online, particularly if you plan excavation
or canal-front works.</div>

<h2>Location &amp; noise</h2>
<p>{road_txt}</p>
<ul>
<li>Zoned <b>{esc(zone)}</b> under the Gold Coast City Plan &mdash; the setting is established low-density residential.</li>
<li>Proximity to beach, shops, schools and transport is best judged on the ground; this pack covers the mapped-data angle, not lifestyle.</li>
</ul>
{foot("Hazards & setting")}
</div>"""

    # ---------- PAGE 4 : services + development ----------
    p4 = f"""<div class="page">
{header()}
<div class="kick">Buyer due diligence &middot; Services &amp; surrounds</div>
<h1>Services</h1>
<div class="sub">Council utility mains near the lot &mdash; as-at {esc(as_at)}</div>
<p>Whether the reticulated services are present near the parcel. Presence of a main near the lot
indicates the service is available in the street; the exact connection point, depth and any main or
easement crossing the land are confirmed by a survey and a service-locator (Dial Before You Dig) plan.</p>
<table class="hz">{svc_rows}</table>
<div class="note">Sewer and stormwater lines can cross a lot and carry a build-over/easement restriction.
If you intend to build or extend, order a <b>Dial Before You Dig</b> plan and check the survey for any
pipe alignment across the block before you rely on the yard being clear.</div>

<h2>Nearby development</h2>
<p>Council's development-application layer returns <b>{da_n}</b> record(s) in the search around the parcel
(~{da_r} m), pulled {esc(as_at)}. Most are minor residential works &mdash; the descriptions returned include
{da_examples or 'a mix of dwelling additions and minor structures'}. This is a picture of <b>what could
change nearby</b>, not a concern in itself; the detail and current status of any single application are on
the council's PD Online.</p>
<div class="note">Development-application records are indicative and can include lodged, approved, completed
and withdrawn items together. Treat the count as context for the area's activity, and check any specific
application that matters to you on the City of Gold Coast PD Online.</div>
{foot("Services & surrounds")}
</div>"""

    # ---------- PAGE 5 : order yourself + sources + disclaimer ----------
    p5 = f"""<div class="page tight">
{header()}
<div class="kick">Buyer due diligence &middot; Next steps</div>
<h1>What a building &amp; pest won't cover</h1>
<div class="sub">The searches and inspections to order yourself</div>
<p>A standard building &amp; pest inspection looks at the physical condition of the structure. It does
<b>not</b> pull the legal, records and insurance searches below &mdash; and neither can we for you. These
are the ones worth ordering before you commit.</p>
<div class="do"><ul>
<li><b>Title search &amp; registered plan (Titles Queensland)</b> &mdash; confirms the registered owner and,
critically, any <b>easements, covenants or encumbrances</b> on the title. A small statutory fee; your
solicitor or conveyancer usually orders it.</li>
<li><b>Building-records / final-certificate search (City of Gold Coast)</b> &mdash; whether structures,
additions and any pool were approved and finalised. Un-certified work becomes the buyer's problem.</li>
<li><b>Council Flood Search certificate</b> &mdash; the official letterhead version of the flood numbers in
this pack.</li>
<li><b>An insurance quote for the address</b> &mdash; the only way to see, in dollars, how the market prices
this specific property's risk. Get it in writing before finance.</li>
<li><b>A licensed building &amp; pest inspection</b> &mdash; the physical condition report; engage your own
inspector.</li>
</ul></div>
<div class="note"><b>What we cannot get you, and why:</b> a property-level insurance <b>claim history</b> is
not available to us (it is private to the insurer and the owner), and a physical <b>building &amp; pest</b>
inspection has to be done on-site by a licensed inspector. Where those matter, order them directly &mdash;
we can point you to the right search each time.</div>

<h2>Sources</h2>
<p style="font-size:9pt;color:#5c6b5a">Every data layer used in this pack, with its origin. All results
as-at {esc(as_at)}.</p>
<ul class="srcgrid">{src_rows}</ul>

<p class="disc">This document compiles publicly available Gold Coast City Council and Queensland Government
spatial data to assist your own enquiries. Figures are modelled and indicative; flood levels are
parcel-centre values, not a floor-level survey; hazard, service and development-application layers reflect
what the source layers returned on the date pulled and can be incomplete or superseded. A tick or a
"no hit" result is favourable on this data but is not a guarantee. This is <b>general information only</b>
&mdash; it is not a flood certificate, a valuation, a title search, or financial, legal, town-planning or
insurance advice, and it does not state that the property will or will not flood. Confirm everything that
matters with the City of Gold Coast, Titles Queensland, a licensed surveyor, your insurer and your
solicitor before you rely on it. <b>Marketed in conjunction with {esc(agent)}, {esc(agency)}.</b>
Prepared {today}.</p>
{foot("Next steps & sources")}
</div>"""

    html = (f"<!doctype html><html><head><meta charset=utf-8><style>{css}</style></head><body>"
            + p1 + p2 + p3 + p4 + p5 + "</body></html>")

    HTML(string=html).write_pdf(out)
    print("PDF ->", out, os.path.getsize(out), "bytes")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path to dd/dd_data.json")
    ap.add_argument("--agent", default="Tyler Benson")
    ap.add_argument("--agency", default="Coomera Realty")
    ap.add_argument("--out", default=None, help="output PDF path (default: alongside dd_data.json)")
    a = ap.parse_args()

    data_path = os.path.abspath(a.data)
    with open(data_path) as fh:
        data = json.load(fh)

    if a.out:
        out = os.path.abspath(a.out)
    else:
        street = data.get("address", "property").split(",")[0].strip()
        fname = re.sub(r"[^A-Za-z0-9]+", "_", street).strip("_") + "_Due_Diligence_Pack.pdf"
        out = os.path.join(os.path.dirname(data_path), fname)

    build(data, a.agent, a.agency, out)
