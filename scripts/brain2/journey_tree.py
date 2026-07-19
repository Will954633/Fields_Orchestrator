#!/usr/bin/env python3
"""
journey_tree.py — Brain 2: render the user-journey tree as a self-contained HTML page.

Reads the journey collections written by organic_journey_build.py and draws a
Channel -> Intent-category flow (Sankey), a summary stat row, and a cross-tab with
outcomes. "Intent category" = searched_address_category: whether the address the
visitor searched/valued is a current listing, recently sold, withdrawn, or a home
that hasn't transacted (likely the owner). Regenerate any time — always live data.

Usage:
  python3 scripts/brain2/journey_tree.py            # -> writes journey_tree.html
  python3 scripts/brain2/journey_tree.py --out /path/to/file.html
"""
import os, sys, html, argparse
from collections import defaultdict, Counter
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

CATS = ["current_listing", "recent_listing", "withdrawn_listing",
        "likely_home_owner", "out_of_coverage"]
CAT_LABEL = {"current_listing": "Current listing", "recent_listing": "Recent listing",
             "withdrawn_listing": "Withdrawn listing", "likely_home_owner": "Home owner",
             "out_of_coverage": "Out of coverage"}
CAT_NOTE = {"current_listing": "on the market now",
            "recent_listing": "sold <12mo · may be buyers, not owner",
            "withdrawn_listing": "listed & pulled <12mo",
            "likely_home_owner": "no sale <12mo · likely the owner",
            "out_of_coverage": "no address / outside our suburbs"}
CAT_HUE = {"current_listing": "#3b82c4", "recent_listing": "#c98a2b",
           "withdrawn_listing": "#c0556a", "likely_home_owner": "#2f9e8f",
           "out_of_coverage": "#8a93a3"}


def aggregate(db):
    rows = list(db.organic_journeys.find({}, {
        "searched_address_category": 1, "channel": 1, "converted": 1,
        "pageviews": 1, "duration_s": 1}))
    links = defaultdict(int)                       # (channel, cat) -> sessions
    cat_out = defaultdict(lambda: {"n": 0, "conv": 0, "eng": 0, "bounce": 0})
    chan_tot = Counter()
    for d in rows:
        cat = d.get("searched_address_category") or "out_of_coverage"
        ch = d.get("channel") or "Unknown"
        links[(ch, cat)] += 1
        chan_tot[ch] += 1
        c = cat_out[cat]
        c["n"] += 1
        engaged = (d.get("pageviews") or 0) >= 2 or (d.get("duration_s") or 0) > 60
        if d.get("converted"):
            c["conv"] += 1
        elif engaged:
            c["eng"] += 1
        else:
            c["bounce"] += 1
    # conversions register (all channels incl. paid) for the headline stat
    conv_by_cat = Counter(d.get("searched_address_category") or "out_of_coverage"
                          for d in db.all_conversions.find({}, {"searched_address_category": 1}))
    return rows, links, cat_out, chan_tot, conv_by_cat


# ---- Sankey geometry (2 columns: channels left, categories right) --------------
# LGUT/RGUT reserve horizontal room for the node labels so text never clips the
# viewBox edge; nodes live in the band between them.
def sankey_svg(links, chan_tot, cat_out, W=900, H=460, pad=10, nodew=13, gap=10,
               LGUT=104, RGUT=168):
    channels = [c for c, _ in chan_tot.most_common()]
    cats = [c for c in CATS if cat_out.get(c, {}).get("n")]
    total = sum(links.values()) or 1
    usable = H - 2 * pad
    # scale so all node bands + gaps fit the height, per column
    def layout(names, totals):
        s = sum(totals.values()) or 1
        gaps = gap * max(0, len(names) - 1)
        scale = (usable - gaps) / s
        y = pad
        pos = {}
        for n in names:
            h = max(3.0, totals[n] * scale)
            pos[n] = [y, h, y, y]  # top, height, cursorL, cursorR
            y += h + gap
        return pos, scale
    lpos, _ = layout(channels, chan_tot)
    cat_tot = {c: cat_out[c]["n"] for c in cats}
    rpos, _ = layout(cats, Counter(cat_tot))
    lx = pad + LGUT
    rx = W - pad - RGUT - nodew
    ribbons, lnodes, rnodes = [], [], []
    # ribbons ordered biggest first for nicer stacking
    for (ch, cat), v in sorted(links.items(), key=lambda kv: -kv[1]):
        if cat not in rpos or ch not in lpos:
            continue
        scale_l = lpos[ch][1] / max(1, chan_tot[ch])
        scale_r = rpos[cat][1] / max(1, cat_tot[cat])
        th_l = max(1.0, v * scale_l)
        th_r = max(1.0, v * scale_r)
        y0 = lpos[ch][3]; lpos[ch][3] += th_l
        y1 = rpos[cat][3]; rpos[cat][3] += th_r
        x0 = lx + nodew; x1 = rx
        mx = (x0 + x1) / 2
        # ribbon as filled path between two edges
        p = (f"M{x0:.1f},{y0:.1f} C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
             f"L{x1:.1f},{y1+th_r:.1f} C{mx:.1f},{y1+th_r:.1f} {mx:.1f},{y0+th_l:.1f} {x0:.1f},{y0+th_l:.1f} Z")
        ribbons.append(f'<path d="{p}" fill="{CAT_HUE[cat]}" fill-opacity="0.28"/>')
    for ch in channels:
        t, h, *_ = lpos[ch]
        lnodes.append(f'<rect x="{lx:.1f}" y="{t:.1f}" width="{nodew}" height="{h:.1f}" rx="2" fill="var(--ink-soft)"/>')
        lnodes.append(f'<text x="{lx-6:.1f}" y="{t+h/2+3:.1f}" text-anchor="end" class="nlabel">{html.escape(ch)}</text>')
        lnodes.append(f'<text x="{lx-6:.1f}" y="{t+h/2+15:.1f}" text-anchor="end" class="nsub">{chan_tot[ch]}</text>')
    for cat in cats:
        t, h, *_ = rpos[cat]
        rnodes.append(f'<rect x="{rx:.1f}" y="{t:.1f}" width="{nodew}" height="{h:.1f}" rx="2" fill="{CAT_HUE[cat]}"/>')
        rnodes.append(f'<text x="{rx+nodew+6:.1f}" y="{t+h/2+1:.1f}" class="nlabel">{html.escape(CAT_LABEL[cat])}</text>')
        rnodes.append(f'<text x="{rx+nodew+6:.1f}" y="{t+h/2+13:.1f}" class="nsub">{cat_out[cat]["n"]} sessions</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'preserveAspectRatio="xMinYMin meet" role="img" '
            f'style="width:100%;min-width:{W}px;height:auto;display:block" '
            f'aria-label="Channel to intent-category flow">'
            + "".join(ribbons) + "".join(lnodes) + "".join(rnodes) + "</svg>")


def refresh_badge(db):
    """'Last refreshed' badge from the builder's completion marker (fresh <26h)."""
    from datetime import datetime, timezone, timedelta
    st = db.brain2_run_status.find_one({"_id": "organic_journey_build"})
    if not st or not st.get("run_completed_at"):
        return ('<div class="refresh unknown"><span class="r-lab">Last refreshed</span>'
                '<b class="r-date">never recorded</b>'
                '<span class="r-ago">builder has not reported a run</span></div>')
    s = str(st["run_completed_at"]).replace("Z", "+00:00")
    done = datetime.fromisoformat(s)
    if not done.tzinfo:
        done = done.replace(tzinfo=timezone.utc)
    hrs = (datetime.now(timezone.utc) - done).total_seconds() / 3600
    state = "fresh" if hrs <= 26 else "stale"
    aest = done + timedelta(hours=10)
    date_str = aest.strftime("%-d %b, %-I:%M %p")
    if hrs < 1:
        ago = f"{max(1, round(hrs*60))} min ago"
    elif hrs < 48:
        ago = f"{round(hrs)}h ago"
    else:
        ago = f"{round(hrs/24)}d ago"
    warn = " · nightly run may have failed" if state == "stale" else ""
    return (f'<div class="refresh {state}"><span class="r-lab">Last refreshed</span>'
            f'<b class="r-date">{html.escape(date_str)} AEST</b>'
            f'<span class="r-ago">{html.escape(ago + warn)}</span></div>')


def render(db, generated):
    rows, links, cat_out, chan_tot, conv_by_cat = aggregate(db)
    total = len(rows)
    matched = total - cat_out.get("out_of_coverage", {}).get("n", 0)
    owner_like = cat_out.get("likely_home_owner", {}).get("n", 0)
    listing_like = (cat_out.get("current_listing", {}).get("n", 0)
                    + cat_out.get("recent_listing", {}).get("n", 0)
                    + cat_out.get("withdrawn_listing", {}).get("n", 0))
    total_conv = sum(conv_by_cat.values())

    def stat(v, label, sub=""):
        s = f'<div class="s-sub">{html.escape(sub)}</div>' if sub else ""
        return f'<div class="stat"><div class="s-num">{v}</div><div class="s-lab">{html.escape(label)}</div>{s}</div>'

    stats = "".join([
        stat(total, "journeys analysed", "non-paid sessions"),
        stat(f"{round(100*matched/total) if total else 0}%", "address identified", f"{matched} of {total}"),
        stat(owner_like, "likely home owners", "the seller signal"),
        stat(listing_like, "listing lookers", "current · recent · withdrawn"),
        stat(total_conv, "conversions", "all channels"),
    ])

    svg = sankey_svg(links, chan_tot, cat_out)

    # cross-tab rows
    trows = ""
    for cat in CATS:
        c = cat_out.get(cat)
        if not c:
            continue
        chans = ", ".join(f"{ch} {links[(ch,cat)]}" for ch, _ in chan_tot.most_common()
                          if links.get((ch, cat)))
        trows += (f'<tr><td><span class="dot" style="background:{CAT_HUE[cat]}"></span>'
                  f'<b>{html.escape(CAT_LABEL[cat])}</b><div class="tnote">{html.escape(CAT_NOTE[cat])}</div></td>'
                  f'<td class="num">{c["n"]}</td><td class="num">{c["conv"]}</td>'
                  f'<td class="num">{c["eng"]}</td><td class="num">{c["bounce"]}</td>'
                  f'<td class="chans">{html.escape(chans)}</td></tr>')

    return TEMPLATE.format(stats=stats, svg=svg, trows=trows, badge=refresh_badge(db),
                           generated=html.escape(generated))


TEMPLATE = """<title>User Journey Tree — Fields</title>
<style>
:root{{
  --bg:#f4f6f8; --panel:#ffffff; --ink:#1a2230; --ink-soft:#6b7688;
  --line:#e2e7ee; --accent:#2f9e8f; --good:#2f9e8f; --good-bg:#e7f4f2; --warn:#c0556a;
  --warn-bg:#f9e9ec; --mut-bg:#eef1f5; --shadow:0 1px 2px rgba(20,30,45,.06),0 8px 24px rgba(20,30,45,.05);
}}
@media (prefers-color-scheme:dark){{
  :root{{ --bg:#0f141b; --panel:#171e28; --ink:#e6ebf2; --ink-soft:#8b98ab;
    --line:#242e3b; --accent:#3bb3a2; --good:#3bb3a2; --good-bg:#123029; --warn:#e08497;
    --warn-bg:#3a1f26; --mut-bg:#20272f; --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 28px rgba(0,0,0,.35); }}
}}
:root[data-theme="dark"]{{ --bg:#0f141b; --panel:#171e28; --ink:#e6ebf2; --ink-soft:#8b98ab;
  --line:#242e3b; --accent:#3bb3a2; --good:#3bb3a2; --good-bg:#123029; --warn:#e08497;
  --warn-bg:#3a1f26; --mut-bg:#20272f; --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 28px rgba(0,0,0,.35); }}
:root[data-theme="light"]{{ --bg:#f4f6f8; --panel:#ffffff; --ink:#1a2230; --ink-soft:#6b7688;
  --line:#e2e7ee; --accent:#2f9e8f; --good:#2f9e8f; --good-bg:#e7f4f2; --warn:#c0556a;
  --warn-bg:#f9e9ec; --mut-bg:#eef1f5; --shadow:0 1px 2px rgba(20,30,45,.06),0 8px 24px rgba(20,30,45,.05); }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.5;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;}}
.wrap{{max-width:920px;margin:0 auto;padding:40px 24px 64px;}}
.hd{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;margin-bottom:8px;}}
.hd>div:first-child{{flex:1 1 300px;min-width:0;}}
.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:600;color:var(--accent);margin:0 0 6px;}}
h1{{font-size:29px;line-height:1.15;margin:0 0 6px;font-weight:750;letter-spacing:-.01em;text-wrap:balance;}}
.sub{{color:var(--ink-soft);margin:0 0 28px;font-size:15px;max-width:60ch;}}
.refresh{{flex:0 0 auto;text-align:right;border:1px solid var(--line);border-radius:10px;
  padding:9px 14px;background:var(--panel);box-shadow:var(--shadow);min-width:150px;}}
.refresh .r-lab{{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-soft);font-weight:600;}}
.refresh .r-date{{display:block;font-size:14px;font-weight:700;margin-top:2px;}}
.refresh .r-ago{{display:block;font-size:11.5px;color:var(--ink-soft);margin-top:1px;}}
.refresh.fresh{{border-color:var(--good);background:var(--good-bg);}}
.refresh.fresh .r-lab{{color:var(--good);}}
.refresh.stale{{border-color:var(--warn);background:var(--warn-bg);}}
.refresh.stale .r-lab,.refresh.stale .r-ago{{color:var(--warn);}}
.refresh.unknown{{background:var(--mut-bg);}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:28px;}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);}}
.s-num{{font-size:30px;font-weight:750;letter-spacing:-.02em;line-height:1;}}
.s-lab{{font-size:13px;font-weight:600;margin-top:7px;}}
.s-sub{{font-size:12px;color:var(--ink-soft);margin-top:2px;}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 22px 12px;box-shadow:var(--shadow);margin-bottom:22px;}}
.panel h2{{font-size:15px;margin:0 0 4px;font-weight:700;}}
.phint{{font-size:13px;color:var(--ink-soft);margin:0 0 14px;}}
.svgbox{{overflow-x:auto;}}
svg .nlabel{{font:600 12px -apple-system,"Segoe UI",sans-serif;fill:var(--ink);}}
svg .nsub{{font:500 11px -apple-system,"Segoe UI",sans-serif;fill:var(--ink-soft);}}
table{{width:100%;border-collapse:collapse;font-size:14px;}}
thead th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--ink-soft);font-weight:600;padding:0 10px 9px;border-bottom:1px solid var(--line);}}
thead th.num{{text-align:right;}}
tbody td{{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top;}}
tbody tr:last-child td{{border-bottom:none;}}
td.num{{text-align:right;font-weight:600;}}
.tnote{{font-size:12px;color:var(--ink-soft);font-weight:400;margin-top:2px;}}
.chans{{color:var(--ink-soft);font-size:12.5px;}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle;}}
.foot{{color:var(--ink-soft);font-size:12.5px;margin-top:20px;}}
.foot code{{background:var(--panel);border:1px solid var(--line);padding:1px 6px;border-radius:5px;font-size:12px;}}
</style>
<div class="wrap">
  <div class="hd">
    <div>
      <p class="eyebrow">Brain 2 · Journey Intelligence</p>
      <h1>Who's searching, and whose house are they looking at?</h1>
    </div>
    {badge}
  </div>
  <p class="sub">Every non-paid visitor journey, tagged by the listing state of the address they
  searched or valued — turning a page view into an owner-vs-buyer signal.</p>
  <div class="stats">{stats}</div>
  <div class="panel">
    <h2>Channel → intent</h2>
    <p class="phint">Ribbon width = sessions. Left: where they came from. Right: the address they were looking at.</p>
    <div class="svgbox">{svg}</div>
  </div>
  <div class="panel">
    <h2>Intent categories, by outcome</h2>
    <p class="phint">Converted = ran a home valuation. Engaged = 2+ pages or 60s+. Bounced = neither.</p>
    <div class="svgbox">
    <table>
      <thead><tr><th>Intent category</th><th class="num">Sessions</th><th class="num">Conv.</th>
      <th class="num">Engaged</th><th class="num">Bounced</th><th>Top channels</th></tr></thead>
      <tbody>{trows}</tbody>
    </table>
    </div>
  </div>
  <p class="foot">Live data from <code>organic_journeys</code> + <code>all_conversions</code>.
  Regenerate with <code>python3 scripts/brain2/journey_tree.py</code>. Page built {generated}
  (data freshness shown top-right). "Home owner" is an inference (no sale in 12mo), not confirmed ownership.</p>
</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/fields/Fields_Orchestrator/scripts/brain2/journey_tree.html")
    args = ap.parse_args()
    db = get_client()["system_monitor"]
    # timestamp passed in (Date.* unavailable in some contexts, but here we're plain python)
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc) + timedelta(hours=10)  # AEST
    out = render(db, now.strftime("%Y-%m-%d %H:%M AEST"))
    with open(args.out, "w") as f:
        f.write(out)
    print("wrote", args.out, f"({len(out)} bytes)")


if __name__ == "__main__":
    main()
