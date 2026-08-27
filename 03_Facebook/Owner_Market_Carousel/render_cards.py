#!/usr/bin/env python3
"""Render the owner-market carousel creative: 5 cards x 3 suburbs = 15 PNGs at 1080x1080.

Cards 01 and 02 are suburb-specific (aerial + suburb name); 03/04/05 are identical
across suburbs but rendered per set so each Meta ad set gets a complete 5-image set.

Source of truth for copy is the concept artifact reviewed by Will. No $ figures, no
predictions (CLAUDE.md Rule 5). Renders via system Chrome + Playwright, screenshots at
2x then downscales to a clean 1080x1080 PNG.
"""
import json, os, io
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cards")
os.makedirs(OUT, exist_ok=True)
A = json.load(open(os.path.join(HERE, "assets.json")))

SUBURBS = {
    "robina":   {"name": "Robina",         "aerial": A["AERIAL_ROBINA"]},
    "varsity":  {"name": "Varsity Lakes",  "aerial": A["AERIAL_VARSITY"]},
    "burleigh": {"name": "Burleigh Waters", "aerial": A["AERIAL_BURLEIGH"]},
}

SERIF = "Georgia, 'Liberation Serif', 'Times New Roman', serif"
SANS = "Helvetica, 'Liberation Sans', Arial, sans-serif"

BASE_CSS = f"""
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:1080px;height:1080px}}
  .card{{width:1080px;height:1080px;position:relative;overflow:hidden;
        font-family:{SANS};-webkit-font-smoothing:antialiased}}
  .pad{{position:absolute;inset:0;padding:78px;display:flex;flex-direction:column}}
  .kick{{font-size:23px;letter-spacing:.22em;text-transform:uppercase;font-weight:700}}
  .serif{{font-family:{SERIF};font-weight:700;letter-spacing:-.01em;line-height:1.06}}
  .brandbar{{display:flex;align-items:center;gap:16px;margin-top:auto;font-size:24px;letter-spacing:.01em}}
  .brandbar img{{width:44px;height:44px;object-fit:contain}}
  /* grounds */
  .c-cream{{background:#F6F1E7;color:#2B2A25}}
  .c-green{{background:linear-gradient(158deg,#2F4D3E 0%,#213A2E 100%);color:#F2EDE1}}
"""

def page(body_css, body_html):
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{BASE_CSS}\n{body_css}</style></head><body>{body_html}</body></html>"""


# ---- Card 01 : the hook (aerial) --------------------------------------------
def card01(sub):
    css = """
    .c1 .aerial{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
    .c1 .scrim{position:absolute;inset:0;background:linear-gradient(180deg,
        rgba(24,40,30,.30) 0%,rgba(22,37,28,.55) 45%,rgba(18,31,24,.93) 100%)}
    .c1 .lock{display:flex;flex-direction:column;gap:6px}
    .c1 .lock .sub{font-size:62px;color:#FEC66F;line-height:.98}
    .c1 .lock .an{font-size:46px;color:#FEC66F;line-height:.98}
    .c1 h1{font-size:74px;color:#F4EFE3;margin-top:20px}
    .c1 .body{font-size:31px;line-height:1.42;color:#DCE6D8;margin-top:30px;max-width:20ch}
    .c1 .body .sp{display:block;height:20px}
    """
    html = f"""<div class="card c1">
      <img class="aerial" src="{sub['aerial']}">
      <div class="scrim"></div>
      <div class="pad">
        <div class="lock"><span class="serif sub">{sub['name']}</span><span class="serif an">Analysis</span></div>
        <div style="margin-top:auto">
          <h1 class="serif">Prices are falling.<br>Is your home next?</h1>
          <div class="body">Sydney and Melbourne have turned. Brisbane has slipped.
            The Gold Coast is holding &mdash; for now.<span class="sp"></span>
            Property markets do not move as one.<br>Neither do individual homes.</div>
        </div>
      </div></div>"""
    return page(css, html)


# ---- Card 02 : what we did (cream + trajectory) -----------------------------
def card02(sub):
    css = """
    .c2 .kick{color:#9A5228}
    .c2 h2{font-size:52px;margin-top:22px;color:#2B2A25}
    .c2 svg{width:100%;height:150px;margin-top:40px}
    .c2 .body{font-size:31px;line-height:1.42;color:#5C574B;margin-top:34px;max-width:24ch}
    .c2 .brandbar{color:#7B7466}
    """
    html = f"""<div class="card c2 c-cream"><div class="pad">
        <div class="kick">Your home, traced</div>
        <h2 class="serif">We tracked your home&rsquo;s estimated value over 18 months
          &mdash; against {sub['name']}&rsquo;s wider market.</h2>
        <svg viewBox="0 0 520 150" preserveAspectRatio="none">
          <line x1="0" y1="128" x2="520" y2="128" stroke="#D9D1C0" stroke-width="2"/>
          <polyline points="8,96 108,86 208,70 312,60 410,63 512,54" fill="none"
             stroke="#B4622F" stroke-width="5"/>
          <polyline points="8,116 108,112 208,108 312,102 410,105 512,98" fill="none"
             stroke="#2C4A3B" stroke-width="4" stroke-dasharray="9 7"/>
          <circle cx="512" cy="54" r="8" fill="#B4622F"/>
        </svg>
        <div class="body">See exactly where your home sits &mdash; and which way the
          local signals are pointing.</div>
        <div class="brandbar"><img src="{A['LOGO_GRASS']}">
          <span>fieldsestate.com.au &middot; Smarter with data</span></div>
      </div></div>"""
    return page(css, html)


# ---- Card 03 : the person (quote) -------------------------------------------
def card03(sub):
    css = """
    .c3 .pad{justify-content:center}
    .c3 .qmark{font-family:%s;font-size:150px;line-height:.42;color:#B4622F;height:70px}
    .c3 blockquote{font-family:%s;font-style:italic;font-weight:400;font-size:44px;
        line-height:1.34;color:#2B2A25;margin:44px 0 48px}
    .c3 .who{display:flex;align-items:center;gap:28px}
    .c3 .who img{width:120px;height:120px;border-radius:50%%;object-fit:cover;border:4px solid #B4622F}
    .c3 .who .n{font-weight:700;font-size:30px;color:#2B2A25}
    .c3 .who .r{font-size:25px;color:#7B7466;margin-top:2px}
    """ % (SERIF, SERIF)
    html = f"""<div class="card c3 c-cream"><div class="pad">
        <div class="qmark">&ldquo;</div>
        <blockquote>The Gold Coast is underpinned by a strong economy that has served us
          well up until now. However, some key leading indicators of price change are
          starting to show early signs of moving. Those are the signals I&rsquo;ll be
          watching next.</blockquote>
        <div class="who"><img src="{A['PORTRAIT']}">
          <div><div class="n">Will Simpson</div><div class="r">Fields Real Estate</div></div></div>
      </div></div>"""
    return page(css, html)


# ---- Card 04 : the proof (three questions) ----------------------------------
def card04(sub):
    css = """
    .c4 .kick{color:#C89B4A}
    .c4 .qlist{display:flex;flex-direction:column;gap:34px;margin-top:44px}
    .c4 .q{font-family:%s;font-weight:700;font-size:38px;line-height:1.14;color:#F4EFE3}
    .c4 .a{font-size:24px;line-height:1.42;color:#C4D1BF;margin-top:8px;max-width:34ch}
    .c4 .brandbar{color:#B9C7B4;font-size:24px}
    """ % SERIF
    html = f"""<div class="card c4 c-green"><div class="pad">
        <div class="kick">Three questions, answered</div>
        <div class="qlist">
          <div><div class="q">Why did the wider market turn down?</div>
            <div class="a">Inflation, interest rates and buyer confidence &mdash; with the figures behind each.</div></div>
          <div><div class="q">Why is the Gold Coast holding?</div>
            <div class="a">Interstate migration, local jobs, and what the same money buys.</div></div>
          <div><div class="q">Will the Gold Coast turn too?</div>
            <div class="a">Four indicators that tend to move before prices. Some are beginning to stir.</div></div>
        </div>
        <div class="brandbar"><img src="{A['LOGO_BIRCH']}">
          <span>The full analysis on your address</span></div>
      </div></div>"""
    return page(css, html)


# ---- Card 05 : the ask (CTA) ------------------------------------------------
def card05(sub):
    css = """
    .c5 .pad{justify-content:space-between}
    .c5 .kick{color:#C89B4A}
    .c5 h2{font-size:62px;color:#F4EFE3;margin-top:30px}
    .c5 ul{list-style:none;margin-top:38px;display:flex;flex-direction:column;gap:22px}
    .c5 li{font-family:%s;font-weight:700;font-size:37px;line-height:1.2;color:#DCE5D8;
        position:relative;padding-left:40px}
    .c5 li::before{content:"";position:absolute;left:0;top:16px;width:16px;height:16px;
        border-radius:50%%;background:#C89B4A}
    .c5 .foot{display:flex;flex-direction:column;gap:34px}
    .c5 .btn{align-self:flex-start;background:#B4622F;color:#FBF6EC;font-weight:700;font-size:28px;
        letter-spacing:.12em;text-transform:uppercase;padding:26px 44px;border-radius:8px}
    .c5 .brandbar{color:#B9C7B4;font-size:24px;margin-top:0}
    """ % SERIF
    html = f"""<div class="card c5 c-green"><div class="pad">
        <div>
          <div class="kick">Prepared for your address</div>
          <h2 class="serif">See where your home stands now.</h2>
          <ul>
            <li>Its estimated trajectory.</li>
            <li>Its position within {sub['name']}.</li>
            <li>The four signals we&rsquo;re watching next.</li>
          </ul>
        </div>
        <div class="foot">
          <span class="btn">Find your home &rarr;</span>
          <div class="brandbar"><img src="{A['LOGO_BIRCH']}"><span>fieldsestate.com.au</span></div>
        </div>
      </div></div>"""
    return page(css, html)


CARDS = [("01", card01), ("02", card02), ("03", card03), ("04", card04), ("05", card05)]


def main():
    manifest = []
    with sync_playwright() as p:
        exe = "/usr/bin/google-chrome"
        browser = p.chromium.launch(executable_path=exe, args=["--force-color-profile=srgb"])
        pg = browser.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=2)
        for key, sub in SUBURBS.items():
            for num, fn in CARDS:
                html = fn(sub)
                pg.set_content(html, wait_until="networkidle")
                png = pg.screenshot(clip={"x": 0, "y": 0, "width": 1080, "height": 1080})
                img = Image.open(io.BytesIO(png)).convert("RGB")
                if img.size != (1080, 1080):
                    img = img.resize((1080, 1080), Image.LANCZOS)
                name = f"{key}_card{num}.png"
                img.save(os.path.join(OUT, name), "PNG")
                manifest.append({"suburb": key, "card": num, "file": name})
                print("  rendered", name)
        browser.close()
    json.dump(manifest, open(os.path.join(OUT, "_manifest.json"), "w"), indent=1)
    print(f"\nDONE — {len(manifest)} cards -> {OUT}")


if __name__ == "__main__":
    main()
