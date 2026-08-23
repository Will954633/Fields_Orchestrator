#!/usr/bin/env python3
"""Generate the Fields-branded 93 Burleigh Street buyer info pack (2-page A4 PDF)."""
import os, io, base64
from PIL import Image
from weasyprint import HTML

HERE = os.path.dirname(os.path.abspath(__file__))
RAW  = os.path.join(HERE, "raw")
LOGO = "/home/fields/Fields_Orchestrator/templates/fields-logo.png"
OUT  = os.path.join(HERE, "93_Burleigh_St_Information_Pack.pdf")

def datauri(path, w=None, crop=None):
    im = Image.open(path).convert("RGB")
    if crop == "sq":
        s = min(im.size); im = im.crop(((im.width-s)//2, 0, (im.width-s)//2+s, s))
    if w:
        im = im.resize((w, int(im.height*w/im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=88);
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

def logo_uri():
    im = Image.open(LOGO).convert("RGBA"); bg = Image.new("RGBA", im.size, (255,255,255,255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    b = io.BytesIO(); im.save(b, "PNG");
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

HERO = datauri(f"{RAW}/01_Hero.jpg", w=1100)
T_WORK = datauri(f"{RAW}/25.jpg", w=380, crop="sq")
T_REAR = datauri(f"{RAW}/26.jpg", w=380, crop="sq")
T_KIT  = datauri(f"{RAW}/09t.jpg", w=380, crop="sq")
LOGOU = logo_uri()

COMPS = [
 ("47 Wedgebill Parade", "4 bed / 3 bath", "Oct 2025", "$2,350,000"),
 ("23 Kestrel Drive",    "4 bed / 2 bath", "May 2026", "$2,210,000"),
 ("46 Auk Avenue",       "4 bed / 2 bath", "Oct 2025", "$2,190,000"),
 ("8 Beaconsfield Drive","4 bed / 2 bath", "Mar 2026", "$2,100,000"),
 ("6 Boston Place",      "4 bed / 2 bath", "Apr 2025", "$1,840,000"),
 ("66 Wedgebill Parade", "4 bed / 2 bath", "Jan 2025", "$1,710,000"),
]
comp_rows = "".join(
 f"<tr><td>{a}</td><td>{s}</td><td>{d}</td><td class='p'>{pr}</td></tr>" for a,s,d,pr in COMPS)

HTMLDOC = f"""<!doctype html><html><head><meta charset=utf-8><style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin:0; padding:0; }}
body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color:#20291f; font-size:11pt; line-height:1.5; }}
.page {{ width:210mm; min-height:297mm; padding:16mm 15mm 14mm; position:relative; }}
.top {{ display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #2b3a30; padding-bottom:10px; margin-bottom:16px; }}
.top img {{ height:30px; }}
.tag {{ color:#5c6b5a; font-size:9.5pt; letter-spacing:.14em; text-transform:uppercase; }}
.kicker {{ color:#d9645b; font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:9pt; }}
.hero {{ width:100%; height:74mm; object-fit:cover; border-radius:8px; display:block; margin:6px 0 14px; }}
h1 {{ font-size:20pt; letter-spacing:-.02em; color:#20291f; margin-bottom:2px; }}
.suburb {{ color:#5c6b5a; font-size:11pt; margin-bottom:10px; }}
.price {{ font-size:22pt; font-weight:800; color:#2b3a30; }}
.price small {{ font-size:10pt; font-weight:600; color:#5c6b5a; }}
.stats {{ display:flex; gap:0; margin:14px 0 6px; border:1px solid #dfe4dc; border-radius:8px; overflow:hidden; }}
.stat {{ flex:1; padding:11px 8px; text-align:center; border-right:1px solid #dfe4dc; }}
.stat:last-child {{ border-right:0; }}
.stat b {{ display:block; font-size:14pt; color:#2b3a30; }}
.stat span {{ font-size:8.5pt; color:#6b776a; text-transform:uppercase; letter-spacing:.06em; }}
.lead {{ margin:14px 0; }}
.thumbs {{ display:flex; gap:8px; margin:12px 0; }}
.thumbs > div {{ flex:1; }}
.thumbs img {{ width:100%; height:38mm; object-fit:cover; border-radius:6px; display:block; }}
.thumbs .cap {{ font-size:8pt; color:#6b776a; }}
h2 {{ font-size:12.5pt; color:#2b3a30; margin:18px 0 8px; padding-bottom:5px; border-bottom:1px solid #e3e8e1; }}
ul {{ margin:0 0 4px 18px; }} li {{ margin-bottom:3px; }}
table {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:10pt; }}
th {{ text-align:left; color:#6b776a; font-size:8.5pt; text-transform:uppercase; letter-spacing:.06em; border-bottom:2px solid #2b3a30; padding:6px 4px; }}
td {{ padding:7px 4px; border-bottom:1px solid #ecefe9; }}
td.p, th.p {{ text-align:right; font-weight:700; color:#2b3a30; }}
.range {{ background:#f4f6f2; border-left:3px solid #d9645b; padding:10px 14px; margin:12px 0; border-radius:0 6px 6px 0; }}
.range b {{ color:#2b3a30; }}
.two {{ display:flex; gap:18px; }} .two > div {{ flex:1; }}
.contact {{ background:#2b3a30; color:#eef1ea; border-radius:8px; padding:16px 18px; margin-top:16px; display:flex; justify-content:space-between; align-items:center; }}
.contact b {{ color:#fff; font-size:12.5pt; }}
.contact .r {{ text-align:right; font-size:10.5pt; line-height:1.7; }}
.disc {{ font-size:8pt; color:#8a938700; }}
.disc {{ font-size:8pt; color:#8a9387; margin-top:14px; line-height:1.45; }}
.foot {{ position:absolute; bottom:8mm; left:15mm; right:15mm; font-size:8pt; color:#9aa397; border-top:1px solid #e3e8e1; padding-top:6px; display:flex; justify-content:space-between; }}
</style></head><body>

<div class="page">
  <div class="top"><img src="{LOGOU}"><span class="tag">Smarter with data</span></div>
  <div class="kicker">Buyer Information Pack</div>
  <img class="hero" src="{HERO}">
  <h1>93 Burleigh Street</h1>
  <div class="suburb">Burleigh Waters, QLD 4220</div>
  <div class="price">$1,915,000 <small>&nbsp;price guide</small></div>
  <div class="stats">
    <div class="stat"><b>822 m&sup2;</b><span>Land</span></div>
    <div class="stat"><b>220 m&sup2;</b><span>Home</span></div>
    <div class="stat"><b>4</b><span>Bed</span></div>
    <div class="stat"><b>3</b><span>Bath</span></div>
    <div class="stat"><b>44 m&sup2;</b><span>Workshop</span></div>
    <div class="stat"><b>1 km</b><span>To beach</span></div>
  </div>
  <p class="lead">A solid 822&nbsp;m&sup2; landholding a 1&nbsp;km walk from Burleigh Beach. The home is
  original and unrenovated &mdash; and priced accordingly. What you're buying is the land, the
  ~19.9&nbsp;m frontage and the location, none of which can be changed later; the house is yours to
  update in your own time. A separate downstairs zone with its own kitchenette and bathroom, plus a
  powered 7&nbsp;&times;&nbsp;6.2&nbsp;m workshop, make it unusually flexible for a family, a
  work-from-home setup or multi-generational living.</p>
  <div class="thumbs">
    <div><img src="{T_REAR}"><div class="cap">Rear elevation &amp; yard</div></div>
    <div><img src="{T_WORK}"><div class="cap">7 &times; 6.2 m powered workshop</div></div>
    <div><img src="{T_KIT}"><div class="cap">Original kitchen (unrenovated)</div></div>
  </div>
  <h2>What's here</h2>
  <div class="two">
    <div><ul>
      <li>822&nbsp;m&sup2; block, ~19.9&nbsp;m frontage</li>
      <li>220&nbsp;m&sup2; two-level home, built c.1975</li>
      <li>4 bedrooms upstairs, 3 bathrooms</li>
    </ul></div>
    <div><ul>
      <li>Downstairs zone: MPR 6.3 &times; 5.1 m + kitchenette + bathroom</li>
      <li>Powered 7 &times; 6.2 m (44&nbsp;m&sup2;) workshop</li>
      <li>Large fenced backyard, ample parking</li>
    </ul></div>
  </div>
  <div class="foot"><span>Fields Real Estate &mdash; Smarter with data</span><span>93 Burleigh Street, Burleigh Waters &middot; Page 1</span></div>
</div>

<div class="page">
  <div class="top"><img src="{LOGOU}"><span class="tag">Smarter with data</span></div>
  <h2>Recent comparable sales &mdash; Burleigh Waters</h2>
  <p style="font-size:10pt;color:#5c6b5a;margin-bottom:2px;">Recent 4-bedroom house sales in the same suburb, compiled from public sale records.</p>
  <table>
    <tr><th>Address</th><th>Beds/Baths</th><th>Sold</th><th class="p">Price</th></tr>
    {comp_rows}
  </table>
  <div class="range">Recent 4-bedroom house sales in Burleigh Waters range <b>$1,710,000&nbsp;&ndash;&nbsp;$2,350,000</b>,
  clustering around $2,100,000 for renovated homes. At <b>$1,915,000</b>, 93 Burleigh Street sits below that
  cluster &mdash; the difference reflects its original, unrenovated condition rather than its land or location.</div>

  <h2>Location</h2>
  <ul>
    <li>1&nbsp;km walk to Burleigh Beach; close to Burleigh Waters parks, lake and Stephens Street shops</li>
    <li>Easy access to Burleigh Heads, Miami and the M1</li>
  </ul>

  <h2>Planning snapshot</h2>
  <p style="font-size:10pt;">Zoned <b>Low density residential</b> (Gold Coast City Plan). The 822&nbsp;m&sup2; block
  offers redevelopment possibilities <b>subject to Council approval</b>; a flood assessment applies and a
  dwelling house overlay is mapped. Any development potential should be confirmed with independent town-planning
  advice &mdash; we're happy to share the Council planning report on request.</p>

  <h2>About Fields</h2>
  <p style="font-size:10pt;">Fields is a Gold Coast property-intelligence business &mdash; we help buyers make
  informed decisions with original data and local research. 93 Burleigh Street is marketed in conjunction with
  <b>Tyler Benson, Coomera Realty</b>; we work alongside the listing agent, on behalf of buyers. We're glad to talk
  you through the numbers, arrange an inspection, or keep an eye out for other homes that fit what you're after.</p>

  <div class="contact">
    <div><b>Arrange an inspection</b><br><span style="color:#bcc7b8;font-size:10pt;">Ask us for the floor plan, or a private viewing this weekend.</span></div>
    <div class="r">Will Simpson<br>0416&nbsp;529&nbsp;481<br>will@fieldsestate.com.au</div>
  </div>

  <p class="disc">Comparable sales are recent transactions of broadly similar homes selected to give context;
  every property differs and past sales are not a prediction of value. All figures compiled from public sale
  records. The price guide is the current asking price, not a valuation. This document is general information only
  and is not financial, legal or town-planning advice. Buyers should make their own enquiries and obtain
  independent advice. Marketed in conjunction with Tyler Benson, Coomera Realty.
  Prepared {os.popen('date +"%B %Y"').read().strip()}.</p>
  <div class="foot"><span>Fields Real Estate &mdash; Smarter with data &middot; fieldsestate.com.au</span><span>Page 2</span></div>
</div>
</body></html>"""

HTML(string=HTMLDOC).write_pdf(OUT)
# also render page-1 preview PNG for on-screen check
from weasyprint import HTML as H2
print("PDF ->", OUT, os.path.getsize(OUT), "bytes")
