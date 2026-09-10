#!/usr/bin/env python3
"""Reusable house-style chart renderer for the market-update articles.

Renders PNGs into /data/blobs/article-charts/ (nginx serves them at
https://blobs.fieldsestate.com.au/article-charts/<name>.png), so article bodies
reference them by URL — no base64 (see memory: article_inline_images).

House palette drawn from the Fields brand (deep green base, copper accent, slate).
Categorical triad copper/green/slate is an orange-green-blue family — CVD-safe by
construction. Text wears ink tokens, never the series colour. Grid recessive.

Data all comes from Gold_Coast collections computed 2026-08-01; DOM uses the
days_on_market field (NOT days_on_domain — contaminated; see memory).

Run:  python3 scripts/market_article_charts.py --median   (or --all)
"""
import argparse
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from shared.db import get_client

OUT = "/data/blobs/article-charts"
PUBLIC = "https://blobs.fieldsestate.com.au/article-charts"

# ---- house palette ----
INK = "#1a120e"          # primary text
MUTED = "#6b5d52"        # secondary text
GRID = "#e4dccf"         # recessive grid
SURFACE = "#ffffff"
COPPER = "#b87333"       # accent / the "headline" series
GREEN = "#2e6b4c"        # brand green
SLATE = "#40607f"        # slate blue
GOLD = "#c1913c"
CAT = [COPPER, GREEN, SLATE, GOLD]   # fixed categorical order, never cycled

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12,
    "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "axes.linewidth": 1.0,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "svg.fonttype": "none",
})


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=1.0, zorder=0)
    ax.tick_params(length=0)


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE, pad_inches=0.25)
    plt.close(fig)
    print(f"{PUBLIC}/{name}")
    return f"{PUBLIC}/{name}"


def _qkey(p):
    """Accept 'Q1 2025' or '2025-Q1' -> sortable int."""
    p = p.strip()
    if "-Q" in p:
        y, q = p.split("-Q")
    elif p.startswith("Q"):
        q, y = p[1:].split()
    else:
        raise ValueError(f"bad period {p!r}")
    return int(y) * 4 + int(q)


def _qlabel(p):
    """Normalise to 'Q2 2026' for display."""
    p = p.strip()
    if "-Q" in p:
        y, q = p.split("-Q"); return f"Q{int(q)} {y}"
    return p


def _q_range(series, start, end):
    lo, hi = _qkey(start), _qkey(end)
    return sorted([r for r in series if lo <= _qkey(r["period"]) <= hi], key=lambda r: _qkey(r["period"]))


# ---------- MEDIAN ARTICLE ----------

def chart_robina_bedroom_index(gc):
    """Trap 1: Robina attached — all-attached vs 2-bed vs 3-bed, indexed 2024-Q2=100."""
    d = gc["unit_market_series"].find_one({"_id": "robina"})
    allser = {r["period"]: r["rolling_median"] for r in d["rolling_12m"]}
    bb = d["rolling_12m_by_bedrooms"]
    two = {r["period"]: r["rolling_median"] for r in bb["2"]}
    three = {r["period"]: r["rolling_median"] for r in bb["3"]}
    periods = [f"{y}-Q{q}" for y in (2024, 2025, 2026) for q in range(1, 5)]
    periods = [p for p in periods if p >= "2024-Q2" and p <= "2026-Q2"]

    def idx(m):
        base = m.get("2024-Q2")
        return [(m[p] / base * 100 if p in m and base else None) for p in periods]

    series = [("All attached dwellings", idx(allser), COPPER, 3.0),
              ("3-bedroom", idx(three), SLATE, 2.0),
              ("2-bedroom", idx(two), GREEN, 2.0)]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(periods)))
    for label, ys, col, lw in series:
        ax.plot(x, ys, color=col, linewidth=lw, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        # direct end label
        yend = next((v for v in reversed(ys) if v is not None), None)
        ax.annotate(f"{label}  {yend:.0f}", (x[-1], yend), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=11, fontweight="bold")
    ax.axhline(100, color=MUTED, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(p) for p in periods], rotation=30, ha="right", fontsize=9.5)
    ax.set_ylabel("Indexed to June 2024 = 100")
    ax.set_xlim(-0.3, len(periods) - 0.3 + 3.2)
    ax.set_title("Robina attached dwellings: the all-attached median rose faster than any size",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    end = {lab: next(v for v in reversed(ys) if v is not None) for lab, ys, _, _ in series}
    return _save(fig, "median_robina_bedroom_index.png"), end


def chart_robina_rolling_ci(gc):
    """Trap 3: Robina house rolling 12m median + CI band, quarterly medians as dots."""
    d = gc["precomputed_indexed_prices"].find_one({"_id": "robina"})
    roll = _q_range(d["rolling_12m_median_series"], "2025-Q1", "2026-Q2")
    quart = [q for q in _q_range(d["indexed_series"], "2025-Q1", "2026-Q2")]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    xr = list(range(len(roll)))
    labels = [r["period"] for r in roll]
    med = [r["rolling_median"] for r in roll]
    lo = [r.get("ci_low") or r["rolling_median"] for r in roll]
    hi = [r.get("ci_high") or r["rolling_median"] for r in roll]
    ax.fill_between(xr, lo, hi, color=GREEN, alpha=0.14, zorder=1, label="90% confidence range")
    ax.plot(xr, med, color=GREEN, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="12-month rolling median")
    # quarterly dots positioned at matching period
    idxmap = {p: i for i, p in enumerate(labels)}
    qx, qy = [], []
    for q in quart:
        if q["period"] in idxmap:
            qx.append(idxmap[q["period"]]); qy.append(q["median_price"])
    ax.scatter(qx, qy, s=70, color=COPPER, edgecolor=SURFACE, linewidth=1.2, zorder=4,
               label="single-quarter median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(xr)
    ax.set_xticklabels([p.replace("-Q", " Q") for p in labels], fontsize=10)
    ax.set_title("Robina house median: the smooth line is the trend, the dots are the noise",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower right", labelcolor=INK)
    return _save(fig, "median_robina_rolling_ci.png")


def chart_bw_asking_sqm(gc):
    """Trap 4: Burleigh Waters houses — asking vs sold over time. Copper: SQM Research
    weekly asking-price series for postcode 4220 (BW, Burleigh Heads, Miami). Green:
    the 12-month rolling median of recorded house sales in Burleigh Waters, with CI band."""
    import datetime as _dt
    import matplotlib.dates as mdates
    START = _dt.date(2009, 1, 1)

    # asking — SQM houses, postcode 4220, weekly
    d = gc["sqm_asking_prices"].find_one({"_id": "burleigh_waters"})
    ask = [(_dt.date.fromisoformat(r["date"]), r.get("houses_all")) for r in d["series"]]
    ax_x = [x for x, y in ask if y is not None]
    ax_y = [y for x, y in ask if y is not None]

    # sold — rolling 12m median, BW houses, quarterly
    sd = gc["precomputed_indexed_prices"].find_one({"_id": "burleigh_waters"})

    def qend(p):
        qt, yt = p.split()
        return _dt.date(int(yt), int(qt[1:]) * 3, 28)
    sold = [(qend(r["period"]), r["rolling_median"], r.get("ci_low"), r.get("ci_high"))
            for r in sd["rolling_12m_median_series"] if qend(r["period"]) >= START]
    sx = [s[0] for s in sold]
    sm = [s[1] for s in sold]
    slo = [s[2] or s[1] for s in sold]
    shi = [s[3] or s[1] for s in sold]

    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    ax.fill_between(sx, slo, shi, color=GREEN, alpha=0.13, zorder=1)
    ax.plot(ax_x, ax_y, color=COPPER, linewidth=2.6, zorder=3,
            label="Asking price — SQM, postcode 4220")
    ax.plot(sx, sm, color=GREEN, linewidth=2.6, marker="o", markersize=4,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.0, zorder=4,
            label="Sold median — Burleigh Waters, 12-month rolling")

    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.1f}M"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(START, ax_x[-1])
    ax.legend(frameon=False, fontsize=10, loc="upper left", labelcolor=INK)
    ax.set_title("Burleigh Waters houses: what sellers ask vs what homes sell for",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    print("asking latest:", ask[-1], "| sold latest:", sold[-1])
    return _save(fig, "median_bw_asking_sqm.png")


_CHART_CSS = r"""
  :root{--ink:#1a120e;--muted:#6b5d52;--grid:#e4dccf;--surface:#fff;--copper:#b87333;--green:#2e6b4c;--slate:#40607f;--gold:#c1913c;}
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;background:var(--surface);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);}
  .wrap{position:relative;width:100%;}
  svg{display:block;width:100%;height:auto;touch-action:none;cursor:crosshair;}
  .pill{cursor:pointer;}
  .tip{position:absolute;pointer-events:none;background:var(--ink);color:#fff;
    padding:8px 10px;border-radius:6px;font-size:12.5px;line-height:1.45;opacity:0;
    transition:opacity .08s;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,.22);z-index:5;}
  .tip .d{color:#cbb8a6;font-size:11px;margin-bottom:3px;}
  .tip .n{color:#cbb8a6;font-size:11.5px;}
"""

# Shared pill + tooltip JS. Expects: svg, NS, el(). buildPills(defs, y) lays the pills
# out left-to-right, sizing each from its measured text; defs = [{key,label,color,on,g}].
_CHART_JS_HELPERS = r"""
function buildPills(defs, y, onToggle){
  let px=6;
  defs.forEach(s=>{
    const g=el('g',{'class':'pill',role:'button',tabindex:0,'aria-pressed':s.on});
    const txt=el('text',{x:0,y:y+19,'font-size':13,fill:'#1a120e'});
    txt.textContent=s.label;
    const rect=el('rect',{y:y,height:28,rx:14});
    const dot=el('circle',{cy:y+14,r:5});
    g.appendChild(rect);g.appendChild(dot);g.appendChild(txt);svg.appendChild(g);
    const tw=txt.getComputedTextLength();
    rect.setAttribute('x',px);rect.setAttribute('width',tw+40);
    dot.setAttribute('cx',px+16);
    txt.setAttribute('x',px+28);
    s.pill={g,rect,dot,txt};
    px+=tw+40+10;
    const flip=()=>{s.on=!s.on;paintPill(s);g.setAttribute('aria-pressed',s.on);onToggle(s);};
    g.addEventListener('click',flip);
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();flip();}});
    paintPill(s);
  });
}
function paintPill(s){
  const on=s.on;
  s.pill.rect.setAttribute('fill',on?s.color:'none');
  s.pill.rect.setAttribute('fill-opacity',on?0.12:1);
  s.pill.rect.setAttribute('stroke',on?s.color:'#c9beb0');
  s.pill.rect.setAttribute('stroke-width',1.2);
  s.pill.dot.setAttribute('fill',on?s.color:'#c9beb0');
  s.pill.txt.setAttribute('fill',on?'#1a120e':'#8a7d70');
  if(s.g) s.g.style.display=on?'':'none';
}
function fmt$(v){return '$'+Math.round(v).toLocaleString('en-AU');}
function placeTip(pxView,pyView){
  const rect=svg.getBoundingClientRect(), wr=wrap.getBoundingClientRect();
  const px=pxView/VBW*rect.width+(rect.left-wr.left);
  tip.style.opacity=1;
  const tw=tip.offsetWidth;
  let left=px+14; if(left+tw>wr.width) left=px-tw-14; if(left<2) left=2;
  tip.style.left=left+'px';
  tip.style.top=Math.max(0,pyView/VBH*rect.height+(rect.top-wr.top)-tip.offsetHeight-12)+'px';
}
"""

_ASKING_SOLD_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Burleigh Waters houses: asking vs sold</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap" id="wrap">
  <svg id="chart" viewBox="0 0 820 500" preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="Interactive line chart of Burleigh Waters house asking prices versus sold medians, 2009 to 2026. Use the pill buttons to choose series; hover or tap any point for the figures and sample sizes."></svg>
  <div class="tip" id="tip"></div>
</div>
<script>
const ASK = __ASK__, SOLD = __SOLD__, M3 = __M3__, QTR = __QTR__;
const VBW=820, VBH=500, M={l:60,r:16,t:96,b:36};
const PW=VBW-M.l-M.r, PH=VBH-M.t-M.b;
const svg=document.getElementById('chart'), tip=document.getElementById('tip'), wrap=document.getElementById('wrap');
const NS='http://www.w3.org/2000/svg';
function el(n,a){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}
const askT=ASK.map(d=>Date.parse(d[0]));
const t0=askT[0], t1=askT[askT.length-1];
const yMin=__YMIN__, yMax=__YMAX__;
const xOf=t=>M.l+(t-t0)/(t1-t0)*PW;
const yOf=v=>M.t+(1-(v-yMin)/(yMax-yMin))*PH;
const ttl=el('text',{x:6,y:24,'font-size':16,'font-weight':700,fill:'#1a120e'});
ttl.textContent='Burleigh Waters houses: what sellers ask vs what homes sell for';svg.appendChild(ttl);
for(let v=Math.ceil(yMin/500000)*500000; v<=yMax; v+=500000){
  const y=yOf(v);
  svg.appendChild(el('line',{x1:M.l,y1:y,x2:VBW-M.r,y2:y,stroke:'#e4dccf','stroke-width':1}));
  const tx=el('text',{x:M.l-8,y:y+4,'text-anchor':'end','font-size':12,fill:'#6b5d52'});
  tx.textContent='$'+(v/1e6).toFixed(1)+'M'; svg.appendChild(tx);
}
const yy0=new Date(t0).getFullYear(), yy1=new Date(t1).getFullYear();
for(let yr=Math.ceil(yy0/2)*2; yr<=yy1; yr+=2){
  const x=xOf(Date.parse(yr+'-01-01'));
  const tx=el('text',{x:x,y:VBH-12,'text-anchor':'middle','font-size':12,fill:'#6b5d52'});
  tx.textContent=yr; svg.appendChild(tx);
}
// series groups (order = draw order)
const gRoll=el('g',{}), gAsk=el('g',{}), gM3=el('g',{}), gQtr=el('g',{});
let up='', dn='';
SOLD.forEach(d=>{const x=xOf(Date.parse(d[0])); up+=(up?' L':'M')+x+' '+yOf(d[2]);});
for(let i=SOLD.length-1;i>=0;i--){const d=SOLD[i],x=xOf(Date.parse(d[0])); dn+=' L'+x+' '+yOf(d[3]);}
gRoll.appendChild(el('path',{d:up+dn+' Z',fill:'#2e6b4c','fill-opacity':0.13}));
let sp=''; SOLD.forEach((d,i)=>{sp+=(i?' L':'M')+xOf(Date.parse(d[0]))+' '+yOf(d[1]);});
gRoll.appendChild(el('path',{d:sp,fill:'none',stroke:'#2e6b4c','stroke-width':2.4,'stroke-linejoin':'round'}));
SOLD.forEach(d=>{gRoll.appendChild(el('circle',{cx:xOf(Date.parse(d[0])),cy:yOf(d[1]),r:3,fill:'#2e6b4c',stroke:'#fff','stroke-width':1}));});
let ap=''; ASK.forEach((d,i)=>{ap+=(i?' L':'M')+xOf(askT[i])+' '+yOf(d[1]);});
gAsk.appendChild(el('path',{d:ap,fill:'none',stroke:'#b87333','stroke-width':2.4,'stroke-linejoin':'round'}));
let mp='', prev=0;
M3.forEach(d=>{const t=Date.parse(d[0]);
  mp+=((prev&&t-prev<45*86400000)?' L':'M')+xOf(t)+' '+yOf(d[2]); prev=t;});
gM3.appendChild(el('path',{d:mp,fill:'none',stroke:'#40607f','stroke-width':1.8,'stroke-linejoin':'round'}));
M3.forEach(d=>{gM3.appendChild(el('circle',{cx:xOf(Date.parse(d[0])),cy:yOf(d[2]),r:2.6,fill:'#40607f',stroke:'#fff','stroke-width':0.8}));});
QTR.forEach(d=>{gQtr.appendChild(el('circle',{cx:xOf(Date.parse(d[0])),cy:yOf(d[2]),r:3.6,fill:'#c1913c',stroke:'#fff','stroke-width':1}));});
svg.appendChild(gRoll);svg.appendChild(gM3);svg.appendChild(gQtr);svg.appendChild(gAsk);
__HELPERS__
const DEFS=[
  {key:'ask', label:'Asking price', color:'#b87333', on:true,  g:gAsk},
  {key:'roll',label:'12-month sold median', color:'#2e6b4c', on:true, g:gRoll},
  {key:'m3',  label:'3-month sold median', color:'#40607f', on:false, g:gM3},
  {key:'qtr', label:'Quarterly sold median', color:'#c1913c', on:false, g:gQtr},
];
const cross=el('line',{y1:M.t,y2:M.t+PH,stroke:'#1a120e','stroke-width':1,'stroke-dasharray':'3 3',opacity:0});
svg.appendChild(cross);
const hdots={};
DEFS.forEach(s=>{hdots[s.key]=el('circle',{r:4.5,fill:s.color,stroke:'#fff','stroke-width':1.5,opacity:0});svg.appendChild(hdots[s.key]);});
function hideHover(){tip.style.opacity=0;cross.setAttribute('opacity',0);DEFS.forEach(s=>hdots[s.key].setAttribute('opacity',0));}
buildPills(DEFS, 40, hideHover);
const MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function nearest(arr,t){let lo=0,hi=arr.length-1;
  while(lo<hi){const m=(lo+hi)>>1;if(Date.parse(arr[m][0])<t)lo=m+1;else hi=m;}
  if(lo>0&&Math.abs(Date.parse(arr[lo-1][0])-t)<Math.abs(Date.parse(arr[lo][0])-t))lo--;return arr[lo];}
function move(clientX){
  const on=k=>DEFS.find(s=>s.key===k).on;
  if(!DEFS.some(s=>s.on)){hideHover();return;}
  const rect=svg.getBoundingClientRect();
  let vx=(clientX-rect.left)/rect.width*VBW;
  vx=Math.max(M.l,Math.min(VBW-M.r,vx));
  const t=t0+(vx-M.l)/PW*(t1-t0);
  cross.setAttribute('x1',vx);cross.setAttribute('x2',vx);cross.setAttribute('opacity',1);
  const dt=new Date(t);
  let html='<div class="d">'+MO[dt.getMonth()]+' '+dt.getFullYear()+'</div>', topY=M.t+PH;
  DEFS.forEach(s=>hdots[s.key].setAttribute('opacity',0));
  if(on('ask')){const a=nearest(ASK,t);
    hdots.ask.setAttribute('cx',xOf(Date.parse(a[0])));hdots.ask.setAttribute('cy',yOf(a[1]));hdots.ask.setAttribute('opacity',1);
    topY=Math.min(topY,yOf(a[1]));
    html+='<b style="color:#e6a45f">'+fmt$(a[1])+'</b> asking <span class="n">(SQM weekly)</span><br>';}
  if(on('roll')){const s=nearest(SOLD,t);
    hdots.roll.setAttribute('cx',xOf(Date.parse(s[0])));hdots.roll.setAttribute('cy',yOf(s[1]));hdots.roll.setAttribute('opacity',1);
    topY=Math.min(topY,yOf(s[1]));
    html+='<b style="color:#8fc7a8">'+fmt$(s[1])+'</b> sold, 12-month median <span class="n">('+s[4]+(s[5]?' · '+s[5]+' sales':'')+')</span><br>';}
  if(on('m3')){const m=nearest(M3,t);
    hdots.m3.setAttribute('cx',xOf(Date.parse(m[0])));hdots.m3.setAttribute('cy',yOf(m[2]));hdots.m3.setAttribute('opacity',1);
    topY=Math.min(topY,yOf(m[2]));
    html+='<b style="color:#9db8d4">'+fmt$(m[2])+'</b> sold, 3-month median <span class="n">(to '+m[1]+(m[3]?' · '+m[3]+' sales':'')+')</span><br>';}
  if(on('qtr')){const q=nearest(QTR,t);
    hdots.qtr.setAttribute('cx',xOf(Date.parse(q[0])));hdots.qtr.setAttribute('cy',yOf(q[2]));hdots.qtr.setAttribute('opacity',1);
    topY=Math.min(topY,yOf(q[2]));
    html+='<b style="color:#e0c084">'+fmt$(q[2])+'</b> sold, quarterly median <span class="n">('+q[1]+(q[3]?' · '+q[3]+' sales':'')+')</span><br>';}
  tip.innerHTML=html;
  placeTip(vx,topY);
}
svg.addEventListener('mousemove',e=>move(e.clientX));
svg.addEventListener('mouseleave',hideHover);
svg.addEventListener('touchmove',e=>{if(e.touches[0])move(e.touches[0].clientX);},{passive:true});
svg.addEventListener('touchstart',e=>{if(e.touches[0])move(e.touches[0].clientX);},{passive:true});
</script>
</body>
</html>"""


_ROBINA_ROLLING_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robina house median: trend vs noise</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap" id="wrap">
  <svg id="chart" viewBox="0 0 820 500" preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="Interactive chart of the Robina house median, 2025 to 2026. Use the pill buttons to choose between the 12-month rolling median, single-quarter medians and the 3-month rolling median; hover or tap any point for the figure and its sample size."></svg>
  <div class="tip" id="tip"></div>
</div>
<script>
const ROLL = __ROLL__, QTR = __QTR__, M3 = __M3__;
const VBW=820, VBH=500, M={l:64,r:20,t:96,b:40};
const PW=VBW-M.l-M.r, PH=VBH-M.t-M.b;
const svg=document.getElementById('chart'), tip=document.getElementById('tip'), wrap=document.getElementById('wrap');
const NS='http://www.w3.org/2000/svg';
function el(n,a){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}
const allT=ROLL.map(d=>Date.parse(d[0]));
const m3T=M3.map(d=>Date.parse(d[0]));
const t0=Math.min(allT[0],m3T.length?m3T[0]:allT[0])-25*86400000;
const t1=Math.max(allT[allT.length-1],m3T.length?m3T[m3T.length-1]:0)+25*86400000;
const yMin=__YMIN__, yMax=__YMAX__;
const xOf=t=>M.l+(t-t0)/(t1-t0)*PW;
const yOf=v=>M.t+(1-(v-yMin)/(yMax-yMin))*PH;
const ttl=el('text',{x:6,y:24,'font-size':16,'font-weight':700,fill:'#1a120e'});
ttl.textContent='Robina house median: the smooth line is the trend, the dots are the noise';svg.appendChild(ttl);
for(let v=Math.ceil(yMin/100000)*100000; v<=yMax; v+=100000){
  const y=yOf(v);
  svg.appendChild(el('line',{x1:M.l,y1:y,x2:VBW-M.r,y2:y,stroke:'#e4dccf','stroke-width':1}));
  const tx=el('text',{x:M.l-8,y:y+4,'text-anchor':'end','font-size':12,fill:'#6b5d52'});
  tx.textContent='$'+(v/1e6).toFixed(1)+'M'; svg.appendChild(tx);
}
ROLL.forEach(d=>{
  const tx=el('text',{x:xOf(Date.parse(d[0])),y:VBH-14,'text-anchor':'middle','font-size':11.5,fill:'#6b5d52'});
  tx.textContent=d[1]; svg.appendChild(tx);
});
const gRoll=el('g',{}), gQtr=el('g',{}), gM3=el('g',{});
let up='', dn='';
ROLL.forEach(d=>{up+=(up?' L':'M')+xOf(Date.parse(d[0]))+' '+yOf(d[3]);});
for(let i=ROLL.length-1;i>=0;i--){dn+=' L'+xOf(Date.parse(ROLL[i][0]))+' '+yOf(ROLL[i][4]);}
gRoll.appendChild(el('path',{d:up+dn+' Z',fill:'#2e6b4c','fill-opacity':0.14}));
let rp=''; ROLL.forEach((d,i)=>{rp+=(i?' L':'M')+xOf(Date.parse(d[0]))+' '+yOf(d[2]);});
gRoll.appendChild(el('path',{d:rp,fill:'none',stroke:'#2e6b4c','stroke-width':3,'stroke-linejoin':'round'}));
ROLL.forEach(d=>{gRoll.appendChild(el('circle',{cx:xOf(Date.parse(d[0])),cy:yOf(d[2]),r:5,fill:'#2e6b4c',stroke:'#fff','stroke-width':1.4}));});
let mp=''; M3.forEach((d,i)=>{mp+=(i?' L':'M')+xOf(Date.parse(d[0]))+' '+yOf(d[2]);});
gM3.appendChild(el('path',{d:mp,fill:'none',stroke:'#40607f','stroke-width':2,'stroke-dasharray':'5 4','stroke-linejoin':'round'}));
QTR.forEach(d=>{gQtr.appendChild(el('circle',{cx:xOf(Date.parse(d[0])),cy:yOf(d[2]),r:6,fill:'#b87333',stroke:'#fff','stroke-width':1.4}));});
svg.appendChild(gRoll);svg.appendChild(gM3);svg.appendChild(gQtr);
__HELPERS__
const DEFS=[
  {key:'roll',label:'12-month median', color:'#2e6b4c', on:true, g:gRoll},
  {key:'qtr', label:'Single-quarter median', color:'#b87333', on:true, g:gQtr},
  {key:'m3',  label:'3-month rolling (90-day)', color:'#40607f', on:true, g:gM3},
];
const hl=el('circle',{r:7.5,fill:'none','stroke-width':2.5,opacity:0});
svg.appendChild(hl);
function hideHover(){tip.style.opacity=0;hl.setAttribute('opacity',0);}
buildPills(DEFS, 40, hideHover);
// hoverable points across visible series
const TIPCOL={roll:'#8fc7a8',qtr:'#e6a45f',m3:'#9db8d4'};
function points(){
  const out=[];
  const on=k=>DEFS.find(s=>s.key===k).on;
  if(on('roll'))ROLL.forEach(d=>out.push({k:'roll',x:xOf(Date.parse(d[0])),y:yOf(d[2]),
    h:'<div class="d">'+d[1]+'</div><b style="color:'+TIPCOL.roll+'">'+fmt$(d[2])+'</b> 12-month rolling median'+(d[5]?'<br><span class="n">'+d[5]+' sales in the 12-month window</span>':'')}));
  if(on('qtr'))QTR.forEach(d=>out.push({k:'qtr',x:xOf(Date.parse(d[0])),y:yOf(d[2]),
    h:'<div class="d">'+d[1]+'</div><b style="color:'+TIPCOL.qtr+'">'+fmt$(d[2])+'</b> single-quarter median'+(d[3]?'<br><span class="n">'+d[3]+' sales in the quarter</span>':'')}));
  if(on('m3'))M3.forEach(d=>out.push({k:'m3',x:xOf(Date.parse(d[0])),y:yOf(d[2]),
    h:'<div class="d">3 months to '+d[1]+'</div><b style="color:'+TIPCOL.m3+'">'+fmt$(d[2])+'</b> 3-month rolling median'+(d[3]?'<br><span class="n">'+d[3]+' sales in the window</span>':'')}));
  return out;
}
function move(clientX,clientY){
  const rect=svg.getBoundingClientRect();
  const vx=(clientX-rect.left)/rect.width*VBW;
  const vy=(clientY-rect.top)/rect.height*VBH;
  let best=null,bd=1e9;
  points().forEach(p=>{const dx=p.x-vx,dy=p.y-vy,d2=dx*dx+dy*dy;if(d2<bd){bd=d2;best=p;}});
  if(!best||bd>38*38){hideHover();return;}
  const col=DEFS.find(s=>s.key===best.k).color;
  hl.setAttribute('cx',best.x);hl.setAttribute('cy',best.y);hl.setAttribute('stroke',col);hl.setAttribute('opacity',1);
  tip.innerHTML=best.h;
  placeTip(best.x,best.y);
}
svg.addEventListener('mousemove',e=>move(e.clientX,e.clientY));
svg.addEventListener('mouseleave',hideHover);
svg.addEventListener('touchmove',e=>{if(e.touches[0])move(e.touches[0].clientX,e.touches[0].clientY);},{passive:true});
svg.addEventListener('touchstart',e=>{if(e.touches[0])move(e.touches[0].clientX,e.touches[0].clientY);},{passive:true});
</script>
</body>
</html>"""


def _qend(p):
    """'Q2 2026' or '2026-Q2' -> approximate quarter-end date (day 28 of last month)."""
    import datetime as _dt
    p = _qlabel(p)
    qt, yt = p.split()
    return _dt.date(int(yt), int(qt[1:]) * 3, 28)


def _mend(ym):
    """'2026-06' -> approximate month-end date (day 28)."""
    import datetime as _dt
    y, m = ym.split("-")
    return _dt.date(int(y), int(m), 28)


def _write_html(name, html):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{PUBLIC}/{name}  ({len(html)} bytes)")
    return f"{PUBLIC}/{name}"


def chart_bw_asking_sqm_html(gc):
    """Interactive version of the Trap 4 asking-vs-sold chart — a self-contained HTML
    file (inline SVG + vanilla JS, no external libs). Pills toggle asking / 12-month /
    3-month / quarterly sold medians; the hover tooltip carries value + sample size."""
    import datetime as _dt
    import json
    START = _dt.date(2009, 1, 1)
    END_3M = "2026-06"   # match the last complete quarter; later months are under-captured

    d = gc["sqm_asking_prices"].find_one({"_id": "burleigh_waters"})
    ask = [[r["date"], round(r["houses_all"])] for r in d["series"] if r.get("houses_all")]

    sd = gc["precomputed_indexed_prices"].find_one({"_id": "burleigh_waters"})
    sold = [[_qend(r["period"]).isoformat(), r["rolling_median"],
             r.get("ci_low") or r["rolling_median"], r.get("ci_high") or r["rolling_median"],
             _qlabel(r["period"]), r.get("transaction_count") or 0]
            for r in sd["rolling_12m_median_series"] if _qend(r["period"]) >= START]

    qtr = [[_qend(r["period"]).isoformat(), _qlabel(r["period"]), r["median_price"],
            r.get("median_sample_n") or r.get("transaction_count") or r.get("raw_transaction_count") or 0]
           for r in sd["indexed_series"]
           if r.get("median_price") and _qend(r["period"]) >= START and not r.get("is_in_progress")]

    m3 = [[_mend(ym).isoformat(), _mend(ym).strftime("%b %Y"), med, n]
          for ym, med, lo, hi, n in _rolling_3m_median(gc, "burleigh_waters", n_anchors=240)
          if ym <= END_3M and _mend(ym) >= START]

    ys = ([v for _, v in ask] + [r[3] for r in sold] + [r[2] for r in qtr] + [r[2] for r in m3])
    ymin = max(0, (min(ys) - 60000) // 100000 * 100000)
    ymax = -((-(max(ys) + 60000)) // 100000) * 100000

    html = (_ASKING_SOLD_HTML_TEMPLATE
            .replace("__CSS__", _CHART_CSS).replace("__HELPERS__", _CHART_JS_HELPERS)
            .replace("__ASK__", json.dumps(ask)).replace("__SOLD__", json.dumps(sold))
            .replace("__M3__", json.dumps(m3)).replace("__QTR__", json.dumps(qtr))
            .replace("__YMIN__", str(ymin)).replace("__YMAX__", str(ymax)))
    print(f"  bw: {len(ask)} ask, {len(sold)} sold-12m, {len(m3)} sold-3m, {len(qtr)} qtr pts, y {ymin}-{ymax}")
    return _write_html("median_bw_asking_sqm.html", html)


def chart_robina_rolling_ci_html(gc):
    """Interactive version of the Trap 3 chart. Pills toggle the 12-month rolling
    median (with its 90% confidence band), single-quarter medians and a 3-month
    rolling median; every point's tooltip carries value + sample size."""
    import json
    d = gc["precomputed_indexed_prices"].find_one({"_id": "robina"})
    roll_rows = _q_range(d["rolling_12m_median_series"], "2025-Q1", "2026-Q2")
    qtr_rows = _q_range(d["indexed_series"], "2025-Q1", "2026-Q2")

    roll = [[_qend(r["period"]).isoformat(), _qlabel(r["period"]), r["rolling_median"],
             r.get("ci_low") or r["rolling_median"], r.get("ci_high") or r["rolling_median"],
             r.get("transaction_count") or 0]
            for r in roll_rows]
    qtr = [[_qend(r["period"]).isoformat(), _qlabel(r["period"]), r["median_price"],
            r.get("median_sample_n") or r.get("transaction_count") or r.get("raw_transaction_count") or 0]
           for r in qtr_rows if r.get("median_price")]
    # Continuously-recomputed trailing-90-day median (daily), not month-stepped quarters.
    m3 = [[iso, lbl, med, n]
          for iso, lbl, med, n in _rolling_90d_median(gc, "robina", "2025-03", "2026-06")]

    ys = ([r[3] for r in roll] + [r[4] for r in roll] + [r[2] for r in qtr] + [r[2] for r in m3])
    ymin = (min(ys) - 40000) // 50000 * 50000
    ymax = -((-(max(ys) + 40000)) // 50000) * 50000

    html = (_ROBINA_ROLLING_HTML_TEMPLATE
            .replace("__CSS__", _CHART_CSS).replace("__HELPERS__", _CHART_JS_HELPERS)
            .replace("__ROLL__", json.dumps(roll)).replace("__QTR__", json.dumps(qtr))
            .replace("__M3__", json.dumps(m3))
            .replace("__YMIN__", str(ymin)).replace("__YMAX__", str(ymax)))
    print(f"  robina: {len(roll)} roll, {len(qtr)} qtr, {len(m3)} m3 pts, y {ymin}-{ymax}")
    return _write_html("median_robina_rolling_ci.html", html)


def build_median(gc):
    p1, end = chart_robina_bedroom_index(gc)
    p2 = chart_robina_rolling_ci(gc)
    p2h = chart_robina_rolling_ci_html(gc)
    p3 = chart_bw_asking_sqm(gc)
    p3h = chart_bw_asking_sqm_html(gc)
    print("\nINDEX ENDPOINTS (2026-Q2):", {k: round(v) for k, v in end.items()})


# ---------- shared computations ----------

def _rolling_3m_median(gc, suburb, n_anchors=9):
    """Month-stepped trailing 3-month house median via the live median pipeline funcs.
    Returns [(YYYY-MM, median, lo, hi, n)] for the last n_anchors, dropping thin windows."""
    import importlib.util
    import random
    from datetime import datetime
    spec = importlib.util.spec_from_file_location(
        "upx", "/home/fields/Fields_Orchestrator/scripts/precompute_union_prices.py")
    upx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upx)
    from shared.db import get_client
    random.seed(42)
    client = get_client()
    counters = {}
    from collections import defaultdict
    counters = defaultdict(int)
    sales = upx.dedupe_sales(
        upx.load_domain_history(client["Gold_Coast"], suburb, counters)
        + upx.load_onthehouse(client["system_monitor"], suburb, counters))
    pts = [(datetime.strptime(d, "%Y-%m-%d"), p) for (_, d), p in sales.items()]
    end = max(d for d, _ in pts)
    y, m = end.year, end.month
    anchors = []
    for _ in range(n_anchors):
        anchors.append((y, m))
        m -= 1
        if m == 0:
            y -= 1; m = 12
    out = []
    for yy, mm in anchors[::-1]:
        sy, smo = yy, mm - 2
        while smo <= 0:
            smo += 12; sy -= 1
        start = datetime(sy, smo, 1)
        ny, nmm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        wend = datetime(ny, nmm, 1)
        w = [p for d, p in pts if start <= d < wend]
        if len(w) < upx.MIN_N_QUARTER:
            continue
        med = int(statistics.median(w))
        lo, hi = upx.bootstrap_ci(w)
        out.append((f"{yy}-{mm:02d}", med, lo, hi, len(w)))
    return out


def _rolling_90d_median(gc, suburb, start_ym, end_ym, window_days=90, step_days=1):
    """Continuously-recomputed trailing-N-day house median from the live union sale set.
    For every step date (default daily) from the 1st of start_ym to the end of end_ym,
    the median of union sales in the trailing window (date - window_days, date].
    Returns [(date_iso, 'D Mon YYYY', median, n)], dropping windows thinner than
    MIN_N_QUARTER. Unlike _rolling_3m_median (monthly-stepped, 3 calendar months) this
    slides continuously over an exact 90-day window."""
    import importlib.util
    import random
    from collections import defaultdict
    from datetime import datetime, timedelta
    spec = importlib.util.spec_from_file_location(
        "upx", "/home/fields/Fields_Orchestrator/scripts/precompute_union_prices.py")
    upx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upx)
    from shared.db import get_client
    random.seed(42)
    client = get_client()
    counters = defaultdict(int)
    sales = upx.dedupe_sales(
        upx.load_domain_history(client["Gold_Coast"], suburb, counters)
        + upx.load_onthehouse(client["system_monitor"], suburb, counters))
    pts = sorted((datetime.strptime(d, "%Y-%m-%d"), p) for (_, d), p in sales.items())
    cur = datetime(int(start_ym[:4]), int(start_ym[5:7]), 1)
    _e = _mend(end_ym)
    end = datetime(_e.year, _e.month, _e.day)
    win = timedelta(days=window_days)
    out = []
    while cur <= end:
        ws = cur - win
        w = [p for d, p in pts if ws < d <= cur]
        if len(w) >= upx.MIN_N_QUARTER:
            out.append((cur.date().isoformat(), cur.strftime("%-d %b %Y"),
                        int(statistics.median(w)), len(w)))
        cur += timedelta(days=step_days)
    return out


def _rolling_3m_dom(gc, suburb):
    """Month-stepped trailing 3-month median DOM from days_on_market (the site's field)."""
    from datetime import datetime
    rows = list(gc[suburb].find(
        {"listing_status": "sold", "classified_property_type": "House",
         "days_on_market": {"$ne": None}, "sold_date": {"$ne": None}},
        {"days_on_market": 1, "sold_date": 1}))
    pts = []
    for r in rows:
        try:
            pts.append((datetime.strptime(r["sold_date"][:10], "%Y-%m-%d"), r["days_on_market"]))
        except Exception:
            pass
    end = max(d for d, _ in pts)
    y, m = end.year, end.month
    anchors = []
    for _ in range(9):
        anchors.append((y, m)); m -= 1
        if m == 0: y -= 1; m = 12
    out = []
    for yy, mm in anchors[::-1]:
        sy, smo = yy, mm - 2
        while smo <= 0: smo += 12; sy -= 1
        start = datetime(sy, smo, 1)
        ny, nmm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        wend = datetime(ny, nmm, 1)
        w = [v for d, v in pts if start <= d < wend]
        if len(w) < 5:
            continue
        out.append((f"{yy}-{mm:02d}", statistics.median(w), len(w)))
    return out


def _mlabel(ym):
    mm = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
          "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}
    y, m = ym.split("-")
    return f"{mm[m]} {y[2:]}"


# ---------- ROBINA ----------

def chart_robina_dom(gc):
    d = gc["precomputed_market_charts"].find_one({"_id": "robina_days_on_market"})
    tl = [t for t in d["timeline"] if _qkey(t["period"]) >= _qkey("2025-Q1")]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(tl)))
    med = [t["median_days_on_market"] for t in tl]
    inc = [bool(t.get("incomplete")) for t in tl]
    # last completed quarter is the honest headline; the in-progress quarter is
    # drawn dotted with a hollow marker so a small, still-filling sample can never
    # read as a settled jump (2026-Q3 was 22 sales when this was built).
    comp = [i for i in x if not inc[i]]
    last_comp = comp[-1] if comp else x[-1]
    ax.plot(x[:last_comp + 1], med[:last_comp + 1], color=COPPER, linewidth=3.0,
            marker="o", markersize=6, markerfacecolor=COPPER, markeredgecolor=SURFACE,
            markeredgewidth=1.4, zorder=3)
    if last_comp < x[-1]:
        ax.plot(x[last_comp:], med[last_comp:], color=COPPER, linewidth=2.2,
                linestyle=(0, (2, 2)), marker="o", markersize=7, markerfacecolor=SURFACE,
                markeredgecolor=COPPER, markeredgewidth=2.0, zorder=3)
    for xi, yi in zip(x, med):
        ax.annotate(f"{yi:.0f}", (xi, yi), xytext=(0, 9), textcoords="offset points",
                    ha="center", color=INK, fontsize=10, fontweight="bold")
    # typical (10-year) reference line
    hist = d.get("historical_median")
    if hist:
        ax.axhline(hist, color=MUTED, linewidth=1.4, linestyle=(0, (4, 3)), zorder=1)
        ax.annotate(f"typical {hist:.0f} days", (x[0], hist), xytext=(2, 5),
                    textcoords="offset points", ha="left", color=MUTED, fontsize=9)
    if last_comp < x[-1]:
        ax.annotate("current quarter\nstill in progress", (x[-1], med[-1]),
                    xytext=(0, -34), textcoords="offset points", ha="center",
                    color=MUTED, fontsize=8.5)
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(t["period"]) for t in tl], fontsize=10)
    ax.set_ylabel("Median days on market")
    ax.set_ylim(0, max(med) * 1.28)
    ax.set_title("Robina: median days for a house to sell, by quarter",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, "robina_dom.png")


def _median_ci_chart(gc, suburb, title, fname, start="2025-Q1"):
    d = gc["precomputed_indexed_prices"].find_one({"_id": suburb})
    roll = _q_range(d["rolling_12m_median_series"], start, "2026-Q2")
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(roll)))
    med = [r["rolling_median"] for r in roll]
    lo = [r.get("ci_low") or r["rolling_median"] for r in roll]
    hi = [r.get("ci_high") or r["rolling_median"] for r in roll]
    ax.fill_between(x, lo, hi, color=GREEN, alpha=0.14, zorder=1, label="90% confidence range")
    ax.plot(x, med, color=GREEN, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="12-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(r["period"]) for r in roll], fontsize=10)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower right", labelcolor=INK)
    return _save(fig, fname)


def chart_bedroom_levels(gc, suburb, fname, title):
    d = gc["unit_market_series"].find_one({"_id": suburb})
    bb = d["rolling_12m_by_bedrooms"]
    periods = [f"{y}-Q{q}" for y in (2024, 2025, 2026) for q in range(1, 5)]
    periods = [p for p in periods if "2025-Q2" <= p <= "2026-Q2"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(periods)))
    order = [("2", GREEN, "2-bedroom"), ("3", SLATE, "3-bedroom"), ("4", COPPER, "4-bedroom")]
    for bed, col, label in order:
        if bed not in bb:
            continue
        m = {r["period"]: r["rolling_median"] for r in bb[bed]}
        ys = [m.get(p) for p in periods]
        if not any(ys):
            continue
        ax.plot(x, ys, color=col, linewidth=2.4, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        yend = next((v for v in reversed(ys) if v is not None), None)
        ax.annotate(f"{label}  ${yend/1e3:.0f}k", (x[-1], yend), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=10.5, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:.0f}k"))
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(p) for p in periods], rotation=30, ha="right", fontsize=9.5)
    ax.set_xlim(-0.3, len(periods) - 0.3 + 3.4)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


# ---------- 3-month rolling median (Varsity, BW) ----------

def chart_rolling_3m_median(gc, suburb, fname, title, drop_last=True):
    data = _rolling_3m_median(gc, suburb)
    if drop_last:
        data = data[:-1]  # exclude partial current month
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(data)))
    med = [r[1] for r in data]
    lo = [r[2] or r[1] for r in data]
    hi = [r[3] or r[1] for r in data]
    ax.fill_between(x, lo, hi, color=COPPER, alpha=0.13, zorder=1, label="90% confidence range")
    ax.plot(x, med, color=COPPER, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=COPPER, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="3-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x)
    ax.set_xticklabels([_mlabel(r[0]) for r in data], rotation=30, ha="right", fontsize=9.5)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="best", labelcolor=INK)
    return _save(fig, fname)


# ---------- 3-month DOM, three suburbs ----------

def chart_dom_3suburb(gc, fname):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    series = [("Robina", "robina", COPPER), ("Burleigh Waters", "burleigh_waters", SLATE),
              ("Varsity Lakes", "varsity_lakes", GREEN)]
    # align on a common set of month anchors present in all
    allmonths = None
    data = {}
    for label, sub, col in series:
        rows = _rolling_3m_dom(gc, sub)[:-1]  # drop partial
        data[sub] = rows
        ms = [r[0] for r in rows]
        allmonths = ms if allmonths is None else [m for m in allmonths if m in ms]
    for label, sub, col in series:
        rows = {r[0]: r[1] for r in data[sub]}
        ys = [rows[m] for m in allmonths]
        ax.plot(range(len(allmonths)), ys, color=col, linewidth=2.6, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        ax.annotate(f"{label}  {ys[-1]:.0f}", (len(allmonths) - 1, ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=10.5, fontweight="bold")
    ax.set_xticks(range(len(allmonths)))
    ax.set_xticklabels([_mlabel(m) for m in allmonths], rotation=30, ha="right", fontsize=9.5)
    ax.set_ylabel("Median days on market")
    ax.set_xlim(-0.3, len(allmonths) - 0.3 + 4.2)
    ax.set_title("Three suburbs, three directions: median days on market",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


# ---------- Varsity value bars ----------

def chart_value_bars(gc, fname):
    subs = [("Varsity Lakes", 1400000, 398000, GREEN),
            ("Robina", 1490000, 426000, COPPER),
            ("Burleigh Waters", 1925000, 525000, SLATE)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.4))
    for ax in (a1, a2):
        _style(ax)
    labels = [s[0] for s in subs]
    x = list(range(len(subs)))
    cols = [s[3] for s in subs]
    a1.bar(x, [s[1] for s in subs], color=cols, width=0.62, zorder=3)
    for xi, s in zip(x, subs):
        a1.annotate(f"${s[1]/1e6:.2f}M", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=10.5, fontweight="bold")
    a1.set_title("Median house price", color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=10)
    a1.set_ylim(0, 2.2e6)
    a2.bar(x, [s[2] for s in subs], color=cols, width=0.62, zorder=3)
    for xi, s in zip(x, subs):
        a2.annotate(f"${s[2]/1e3:.0f}k", (xi, s[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=10.5, fontweight="bold")
    a2.set_title("Price per bedroom", color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=10)
    a2.set_ylim(0, 6.1e5)
    for ax in (a1, a2):
        ax.set_xticks(x)
        ax.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=9.5)
        ax.set_yticks([])
        ax.grid(False)
    fig.suptitle("Varsity Lakes offers the most house for the money of the three",
                 color=INK, fontsize=13, fontweight="bold", x=0.02, ha="left", y=1.02)
    return _save(fig, fname)


# ---------- BW waterfront ----------

def chart_waterfront(gc, fname):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.4))
    for ax in (a1, a2):
        _style(ax)
    # share of house listings fronting water
    subs = [("Burleigh\nWaters", 31, SLATE), ("Robina", 13, COPPER)]
    x = [0, 1]
    a1.bar(x, [s[1] for s in subs], color=[s[2] for s in subs], width=0.6, zorder=3)
    for xi, s in zip(x, subs):
        a1.annotate(f"{s[1]}%", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=11, fontweight="bold")
    a1.set_xticks(x); a1.set_xticklabels([s[0] for s in subs], fontsize=10)
    a1.set_yticks([]); a1.grid(False); a1.set_ylim(0, 38)
    a1.set_title("Share of house listings on water", color=INK, fontsize=12, fontweight="bold", loc="left", pad=10)
    # asking spread: waterfront vs non-waterfront median asking
    groups = [("Waterfront", 2972500, 1625000), ("Non-waterfront", 1949000, 1495000)]
    xg = [0, 1]
    w = 0.36
    a2.bar([g - w/2 for g in xg], [groups[0][1], groups[1][1]], width=w, color=SLATE, zorder=3, label="Burleigh Waters")
    a2.bar([g + w/2 for g in xg], [groups[0][2], groups[1][2]], width=w, color=COPPER, zorder=3, label="Robina")
    a2.set_xticks(xg); a2.set_xticklabels([g[0] for g in groups], fontsize=10)
    a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.1f}M"))
    a2.set_title("Median asking price", color=INK, fontsize=12, fontweight="bold", loc="left", pad=10)
    a2.legend(frameon=False, fontsize=9.5, labelcolor=INK, loc="upper right")
    fig.suptitle("Burleigh Waters carries far more waterfront — and a bigger premium on it",
                 color=INK, fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=1.02)
    return _save(fig, fname)


# ---------- BW 3m vs 12m ----------

def chart_bw_3v12(gc, fname):
    d = gc["precomputed_indexed_prices"].find_one({"_id": "burleigh_waters"})
    roll12 = _q_range(d["rolling_12m_median_series"], "2025-Q1", "2026-Q2")
    three = _rolling_3m_median(gc, "burleigh_waters")[:-1]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    # x by month index; place 12m quarterly points at their quarter-end month
    qmonth = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}
    months = [r[0] for r in three]
    mi = {m: i for i, m in enumerate(months)}
    x3 = list(range(len(three)))
    ax.plot(x3, [r[1] for r in three], color=COPPER, linewidth=2.8, marker="o", markersize=5,
            markerfacecolor=COPPER, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3,
            label="3-month rolling median")
    # map 12m rolling to month axis
    x12, y12 = [], []
    for r in roll12:
        q, y = r["period"].split()[0] if " " in r["period"] else ("Q" + r["period"].split("-Q")[1], "")
        if "-Q" in r["period"]:
            yy, qq = r["period"].split("-Q"); key = f"{yy}-{qmonth['Q'+qq]}"
        else:
            qq, yy = r["period"][1:].split(); key = f"{yy}-{qmonth['Q'+qq]}"
        if key in mi:
            x12.append(mi[key]); y12.append(r["rolling_median"])
    ax.plot(x12, y12, color=GREEN, linewidth=3.0, marker="s", markersize=7,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=4,
            label="12-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x3)
    ax.set_xticklabels([_mlabel(m) for m in months], rotation=30, ha="right", fontsize=9.5)
    ax.set_title("Burleigh Waters: the annual figure still rising, the recent months softening",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower left", labelcolor=INK)
    return _save(fig, fname)


def chart_supply(gc, fname):
    """Months of supply, three suburbs, with the 4-month balance line."""
    subs = [("Varsity Lakes", 1.77, GREEN), ("Robina", 2.18, COPPER), ("Burleigh Waters", 3.57, SLATE)]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    _style(ax)
    x = list(range(len(subs)))
    ax.bar(x, [s[1] for s in subs], color=[s[2] for s in subs], width=0.6, zorder=3)
    for xi, s in zip(x, subs):
        ax.annotate(f"{s[1]:.2f}", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=11, fontweight="bold")
    ax.axhline(4, color=MUTED, linewidth=1.2, linestyle=(0, (5, 4)), zorder=2)
    ax.annotate("4 months = balanced market", (len(subs) - 0.5, 4), xytext=(0, 5),
                textcoords="offset points", ha="right", color=MUTED, fontsize=10.5)
    ax.set_xticks(x)
    ax.set_xticklabels([s[0].replace(" ", "\n") for s in subs], fontsize=10.5)
    ax.set_ylabel("Months of supply")
    ax.set_ylim(0, 4.6)
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_title("Unsold stock is not piling up: all three suburbs sit below balanced",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_capital_quarterly(fname):
    """Ranked capital-city quarterly dwelling-value change to July 2026 (Cotality)."""
    data = [("Sydney", -4.0), ("Melbourne", -3.4), ("Combined capitals", -2.5),
            ("Canberra", -1.3), ("Brisbane", -0.6), ("Perth", -0.3),
            ("Adelaide", 0.1), ("Hobart", 1.4), ("Darwin", 2.4)]
    data = sorted(data, key=lambda d: d[1])
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    ax.grid(False); ax.grid(axis="x", color=GRID, linewidth=1.0, zorder=0)
    y = list(range(len(data)))
    cols = [COPPER if v < 0 else GREEN for _, v in data]
    ax.barh(y, [v for _, v in data], color=cols, height=0.62, zorder=3)
    for yi, (lab, v) in zip(y, data):
        ha = "right" if v < 0 else "left"
        off = -6 if v < 0 else 6
        emph = lab == "Brisbane"
        ax.annotate(f"{v:+.1f}%", (v, yi), xytext=(off, 0), textcoords="offset points",
                    va="center", ha=ha, color=INK, fontsize=10.5,
                    fontweight="bold" if emph else "normal")
    ax.axvline(0, color=MUTED, linewidth=1.0, zorder=2)
    ax.set_xlim(-5.4, 3.2)
    ax.set_yticks(y)
    labels = [f"{lab}" for lab, _ in data]
    ax.set_yticklabels(labels, fontsize=10.5)
    # emphasise Brisbane tick
    for t in ax.get_yticklabels():
        if t.get_text() == "Brisbane":
            t.set_fontweight("bold"); t.set_color(INK)
    ax.set_xlabel("Change over the quarter to July 2026")
    ax.set_title("Brisbane is turning — but gently, next to Sydney and Melbourne",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_two_clocks(fname):
    """Annual vs quarterly change, Sydney/Melbourne/Brisbane — the two clocks."""
    data = [("Sydney", -2.0, -4.0), ("Melbourne", -2.8, -3.4), ("Brisbane", 14.8, -0.6)]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(data)))
    w = 0.38
    ax.bar([i - w/2 for i in x], [d[1] for d in data], width=w, color=GREEN, zorder=3, label="Past year")
    ax.bar([i + w/2 for i in x], [d[2] for d in data], width=w, color=COPPER, zorder=3, label="Past quarter")
    for i, d in enumerate(data):
        ax.annotate(f"{d[1]:+.1f}%", (i - w/2, d[1]), xytext=(0, 6 if d[1] >= 0 else -14),
                    textcoords="offset points", ha="center", color=INK, fontsize=10, fontweight="bold")
        ax.annotate(f"{d[2]:+.1f}%", (i + w/2, d[2]), xytext=(0, 6 if d[2] >= 0 else -14),
                    textcoords="offset points", ha="center", color=INK, fontsize=10, fontweight="bold")
    ax.axhline(0, color=MUTED, linewidth=1.0, zorder=2)
    ax.set_xticks(x); ax.set_xticklabels([d[0] for d in data], fontsize=11)
    ax.set_ylabel("Dwelling-value change")
    ax.set_ylim(-6, 17)
    ax.set_yticks([])
    ax.grid(False)
    ax.legend(frameon=False, fontsize=10.5, loc="upper left", labelcolor=INK)
    ax.set_title("Two clocks: Brisbane is up 14.8% over the year, down over the quarter",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_the_gap(fname):
    """The gap that matters when you move: own-home vs target-home, a year ago vs now.
    Year-ago = Q2-2025 rolling-12m median (consistent with the published YoY), NOT
    the rolling_12m_prev_median_price field, which disagrees with yoy_pct."""
    groups = [("A year ago", 1270000, 1800000), ("Now", 1400000, 1925000)]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    x = [0, 1]
    w = 0.34
    ax.bar([i - w/2 for i in x], [g[1] for g in groups], width=w, color=GREEN, zorder=3, label="A home like yours (Varsity Lakes median)")
    ax.bar([i + w/2 for i in x], [g[2] for g in groups], width=w, color=SLATE, zorder=3, label="The home you want (Burleigh Waters median)")
    for i, g in enumerate(groups):
        ax.annotate(f"${g[1]/1e6:.2f}M", (i - w/2, g[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        ax.annotate(f"${g[2]/1e6:.3f}M", (i + w/2, g[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        gap = g[2] - g[1]
        ax.annotate(f"the gap:\n${gap/1e3:.0f}k", (i, max(g[1], g[2]) * 0.52), ha="center",
                    color=COPPER, fontsize=12, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([g[0] for g in groups], fontsize=12)
    ax.set_ylim(0, 2.25e6); ax.set_yticks([]); ax.grid(False)
    ax.legend(frameon=False, fontsize=10, loc="upper left", labelcolor=INK)
    ax.set_title("Both homes rose about $130,000 — but the gap between them barely moved",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_suburb_gaps(fname):
    """The gaps BETWEEN suburbs, a year ago vs now — proof they moved differently.
    Year-ago = Q2-2025 rolling-12m median; now = Q2-2026 (consistent with published YoY)."""
    pairs = [("Varsity Lakes\n→ Robina", 138500, 90000),
             ("Robina →\nBurleigh Waters", 391500, 435000),
             ("Varsity Lakes →\nBurleigh Waters", 530000, 525000)]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    x = list(range(len(pairs)))
    w = 0.34
    ax.bar([i - w/2 for i in x], [p[1] for p in pairs], width=w, color=SLATE, zorder=3, label="Gap a year ago")
    ax.bar([i + w/2 for i in x], [p[2] for p in pairs], width=w, color=COPPER, zorder=3, label="Gap now")
    for i, p in enumerate(pairs):
        ax.annotate(f"${p[1]/1e3:.0f}k", (i - w/2, p[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        ax.annotate(f"${p[2]/1e3:.0f}k", (i + w/2, p[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:.0f}k"))
    ax.set_xticks(x); ax.set_xticklabels([p[0] for p in pairs], fontsize=10)
    ax.set_ylim(0, 560000)
    ax.legend(frameon=False, fontsize=10, loc="upper left", labelcolor=INK)
    ax.set_title("The same year lifted every suburb — but moved the gaps between them differently",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_gc_industry(fname):
    """Gold Coast employment by industry — the diversified, health-led economy.
    Source: economy.id (City of Gold Coast / NIEIR), 2024/25."""
    data = [("Health care & social assistance", 16.6, True),
            ("Construction", 15.7, False),
            ("Retail trade", 9.9, False),
            ("Education & training", 8.7, False),
            ("Accommodation & food (tourism)", 8.5, "tourism"),
            ("Professional & technical", 6.4, False),
            ("Manufacturing", 6.1, False),
            ("Administrative & support", 3.7, False),
            ("Public administration & safety", 3.5, False)]
    data = data[::-1]  # largest at top
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    _style(ax)
    ax.grid(False); ax.grid(axis="x", color=GRID, linewidth=1.0, zorder=0)
    y = list(range(len(data)))
    cols = [COPPER if flag is True else (SLATE if flag == "tourism" else GREEN) for _, _, flag in data]
    ax.barh(y, [v for _, v, _ in data], color=cols, height=0.66, zorder=3)
    for yi, (lab, v, flag) in zip(y, data):
        ax.annotate(f"{v:.1f}%", (v, yi), xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=10,
                    fontweight="bold" if flag else "normal")
    ax.set_yticks(y); ax.set_yticklabels([d[0] for d in data], fontsize=10)
    ax.set_xlim(0, 19)
    ax.set_xlabel("Share of Gold Coast jobs")
    ax.set_title("A health-led economy, not a tourism town: Gold Coast jobs by industry",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def build_all(gc):
    build_median(gc)
    print("\n-- Robina --")
    chart_robina_dom(gc)
    _median_ci_chart(gc, "robina", "Robina house median: price held while the clock stretched", "robina_median_ci.png")
    chart_bedroom_levels(gc, "robina", "robina_bedroom_levels.png", "Robina units: what each size actually did")
    print("\n-- Varsity --")
    chart_value_bars(gc, "varsity_value_bars.png")
    chart_rolling_3m_median(gc, "varsity_lakes", "varsity_median_3m.png", "Varsity Lakes: a dip over summer, then a recovery")
    chart_dom_3suburb(gc, "dom_3suburb.png")
    chart_bedroom_levels(gc, "varsity_lakes", "varsity_bedroom_levels.png", "Varsity Lakes units: what each size actually did")
    print("\n-- Burleigh Waters --")
    chart_waterfront(gc, "bw_waterfront.png")
    _median_ci_chart(gc, "burleigh_waters", "Burleigh Waters house median: a steady climb that has levelled", "bw_median_12m.png", start="2024-Q3")
    chart_bw_3v12(gc, "bw_median_3v12.png")
    chart_bedroom_levels(gc, "burleigh_waters", "bw_bedroom_levels.png", "Burleigh Waters units: 2- and 3-bedroom, what each did")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--median", action="store_true")
    ap.add_argument("--bw-asking", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    gc = get_client()["Gold_Coast"]
    if args.all:
        build_all(gc)
    elif args.bw_asking:
        chart_bw_asking_sqm(gc)
        chart_bw_asking_sqm_html(gc)
    elif args.median:
        build_median(gc)


if __name__ == "__main__":
    main()


# ── Renovation premium chart (renovation article, 2026-09) ─────────────────────
# Data baked from 16_Valuation/Renovation_Premium/results_24m.json (hedonic leg2 +
# matched-twins leg3). Single-hue interval chart: bar = 95% interval, dot = best
# estimate; Varsity Lakes drawn muted/dashed (26 treated sales — inconclusive).

_RENO_ROWS = [
    {"suburb": "Burleigh Waters", "est": 16.1, "lo": 4.2, "hi": 29.5,
     "twins": "+22.9%", "n": "70 renovated sales",
     "dollars": "≈ $297,000–$423,000 on the typical $1,845,000 house", "solid": True},
    {"suburb": "Robina", "est": 11.7, "lo": 5.7, "hi": 18.0,
     "twins": "+10.5%", "n": "71 renovated sales",
     "dollars": "≈ $175,000 on the typical $1,491,944 house", "solid": True},
    {"suburb": "Varsity Lakes", "est": 6.9, "lo": -0.4, "hi": 14.8,
     "twins": "+8.3%", "n": "26 sales — too few to be sure",
     "dollars": "≈ $93,000 on the typical $1,351,000 house", "solid": False},
]

_RENO_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What a full renovation adds to the sale price</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap" id="wrap">
  <svg id="chart" viewBox="0 0 820 470" preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="Interval chart of the estimated sale-price premium for fully renovated houses: Burleigh Waters best estimate 16.1 percent, range 4.2 to 29.5; Robina 11.7 percent, range 5.7 to 18; Varsity Lakes 6.9 percent, range minus 0.4 to 14.8, based on too few sales to be sure. Hover or tap a row for details."></svg>
  <div class="tip" id="tip"></div>
</div>
<script>
const ROWS=__ROWS__;
const VBW=820, VBH=470, M={l:170,r:34,t:96,b:46};
const PW=VBW-M.l-M.r, PH=VBH-M.t-M.b;
const svg=document.getElementById('chart'), tip=document.getElementById('tip'), wrap=document.getElementById('wrap');
const NS='http://www.w3.org/2000/svg';
function el(n,a){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}
const GREEN='#2e6b4c', INK='#1a120e', MUTED='#6b5d52', GRID='#e4dccf';
const x0=-5, x1=30;
const xOf=v=>M.l+(v-x0)/(x1-x0)*PW;
const rowH=PH/ROWS.length;
const ttl=el('text',{x:6,y:24,'font-size':16,'font-weight':700,fill:INK});
ttl.textContent='What a full renovation adds to the sale price';svg.appendChild(ttl);
const sub=el('text',{x:6,y:44,'font-size':12.5,fill:MUTED});
sub.textContent='Fully renovated vs comparable unrenovated houses · 578 sales, 24 months to September 2026';
svg.appendChild(sub);
const key=el('text',{x:6,y:64,'font-size':12,fill:MUTED});
key.textContent='Bar = the range the true premium very likely sits in · dot = best estimate · hover or tap a row';
svg.appendChild(key);
for(let v=x0;v<=x1;v+=5){
  const x=xOf(v), zero=v===0;
  svg.appendChild(el('line',{x1:x,y1:M.t,x2:x,y2:M.t+PH,stroke:zero?INK:GRID,'stroke-width':zero?1.6:1}));
  const tx=el('text',{x:x,y:VBH-16,'text-anchor':'middle','font-size':12,fill:zero?INK:MUTED,'font-weight':zero?700:400});
  tx.textContent=(v>0?'+':'')+v+'%'; svg.appendChild(tx);
}
ROWS.forEach((r,i)=>{
  const cy=M.t+rowH*i+rowH/2;
  const name=el('text',{x:M.l-14,y:cy-4,'text-anchor':'end','font-size':14,'font-weight':700,fill:INK});
  name.textContent=r.suburb; svg.appendChild(name);
  const nn=el('text',{x:M.l-14,y:cy+14,'text-anchor':'end','font-size':11,fill:MUTED});
  nn.textContent=r.n; svg.appendChild(nn);
  const bx=xOf(r.lo), bw=xOf(r.hi)-xOf(r.lo);
  const bar=el('rect',{x:bx,y:cy-7,width:bw,height:14,rx:7,
    fill:GREEN,'fill-opacity':r.solid?0.16:0.07,stroke:GREEN,
    'stroke-width':1.2,'stroke-opacity':r.solid?1:0.65});
  if(!r.solid) bar.setAttribute('stroke-dasharray','5 4');
  svg.appendChild(bar);
  const dot=el('circle',{cx:xOf(r.est),cy:cy,r:7,fill:GREEN,'fill-opacity':r.solid?1:0.55,stroke:'#fff','stroke-width':2});
  svg.appendChild(dot);
  const lab=el('text',{x:xOf(r.est),y:cy-16,'text-anchor':'middle','font-size':13.5,'font-weight':700,fill:r.solid?INK:MUTED});
  lab.textContent='+'+r.est+'%'; svg.appendChild(lab);
  const hit=el('rect',{x:0,y:M.t+rowH*i,width:VBW,height:rowH,fill:'transparent'});
  svg.appendChild(hit);
  const show=()=>{
    tip.innerHTML='<div class="d">'+r.suburb+'</div>'
      +'Best estimate: <b>+'+r.est+'%</b><br>'
      +'Very likely between '+(r.lo>0?'+':'')+r.lo+'% and +'+r.hi+'%<br>'
      +'Second method (matched twins): '+r.twins+'<br>'
      +'<span class="n">'+r.dollars+'</span>';
    placeTip(xOf(r.est), cy-10);
  };
  hit.addEventListener('mousemove',show);
  hit.addEventListener('touchstart',e=>{show();e.preventDefault();},{passive:false});
  hit.addEventListener('mouseleave',()=>{tip.style.opacity=0;});
});
__HELPERS__
</script>
</body>
</html>
"""


def chart_renovation_premium_html():
    import json as _json
    html = (_RENO_HTML_TEMPLATE
            .replace("__CSS__", _CHART_CSS)
            .replace("__HELPERS__", _CHART_JS_HELPERS)
            .replace("__ROWS__", _json.dumps(_RENO_ROWS)))
    return _write_html("renovation-premium.html", html)


def chart_renovation_premium_png():
    """Static noscript fallback for the interactive chart."""
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ax.set_xlim(-5, 30)
    ax.set_ylim(-0.6, len(_RENO_ROWS) - 0.4)
    ax.invert_yaxis()
    ax.axvline(0, color=INK, linewidth=1.4, zorder=2)
    for v in range(-5, 31, 5):
        if v:
            ax.axvline(v, color=GRID, linewidth=1, zorder=0)
    for i, r in enumerate(_RENO_ROWS):
        a = 1.0 if r["solid"] else 0.55
        ax.barh(i, r["hi"] - r["lo"], left=r["lo"], height=0.28,
                color=GREEN, alpha=0.16 if r["solid"] else 0.07, zorder=2)
        ax.plot([r["lo"], r["hi"]], [i, i], color=GREEN, alpha=a, linewidth=1.4,
                linestyle="-" if r["solid"] else (0, (5, 4)), zorder=3)
        ax.plot(r["est"], i, "o", markersize=11, color=GREEN, alpha=a,
                markeredgecolor="white", markeredgewidth=2, zorder=4)
        ax.annotate(f'+{r["est"]}%', (r["est"], i - 0.22), ha="center",
                    fontsize=11, fontweight="bold", color=INK if r["solid"] else MUTED)
        ax.annotate(r["suburb"], (-5.6, i - 0.08), ha="right", fontsize=11.5,
                    fontweight="bold", color=INK, annotation_clip=False)
        ax.annotate(r["n"], (-5.6, i + 0.22), ha="right", fontsize=8.5,
                    color=MUTED, annotation_clip=False)
    ax.set_yticks([])
    ax.set_xticks(range(-5, 31, 5))
    ax.set_xticklabels([f'{"+" if v > 0 else ""}{v}%' for v in range(-5, 31, 5)])
    _style(ax)
    ax.grid(False)
    ax.set_title("What a full renovation adds to the sale price\n"
                 "Fully renovated vs comparable unrenovated houses · 578 sales, 24 months to September 2026",
                 loc="left", fontsize=12, pad=14)
    return _save(fig, "renovation-premium.png")
