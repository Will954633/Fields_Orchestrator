#!/usr/bin/env python3
"""
render_cards.py — regenerate all 18 "Before You List" carousel creatives (1080x1080).

Self-contained: reads ../photos (property heroes) + ../Images (book mockups),
renders each card HTML with headless Chrome, crops to 1080x1080, writes ../creatives/{A,B,C}/.

Run:  python3 scripts/render_cards.py      (from the campaign folder, or anywhere)
Deps: PIL (source /home/fields/venv/bin/activate), google-chrome.

Headless-Chrome note (see memory headless_chrome_card_render): a 1080x1080 window only
fills ~992px of usable viewport, so we render at 1080x1200 and PIL-crop the top 1080x1080.

Card copy is the single source of truth — edit CARDS below, re-run, done.
All figures are public sale prices / third-party estimate gaps (no single Fields
valuation stated as worth). Cautionary homes: suburb only, no street. Wins: named.
"""
import os, io, base64, subprocess, tempfile, shutil
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PH   = os.path.join(ROOT, "photos")
BK   = os.path.join(ROOT, "Images")
OUT  = os.path.join(ROOT, "creatives")
BOOK_TABLE  = os.path.join(BK, "ChatGPT Image Jul 28, 2026, 09_53_03 AM (1).png")   # cover on table
BOOK_SPREAD = os.path.join(BK, "ChatGPT Image Jul 28, 2026, 09_53_03 AM (3).png")   # data spread

def datauri(path, box=1200):
    im = Image.open(path).convert("RGB"); w, h = im.size; s = min(w, h)
    im = im.crop(((w-s)//2, (h-s)//2, (w-s)//2+s, (h-s)//2+s)).resize((box, box), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

IMG = {
  "huntingdale": datauri(f"{PH}/A1_huntingdale.jpg"),   # A1 loss (de-identified)
  "whitehead":   datauri(f"{PH}/A3_whitehead.jpg"),     # A3 win (named)
  "majorca":     datauri(f"{PH}/B1_majorca.jpg"),       # B1 (de-identified)
  "christine":   datauri(f"{PH}/B2_christine.jpg"),     # B2 (de-identified)
  "windemere":   datauri(f"{PH}/C1_windemere.jpg"),     # C1 win (named)
  "woody":       datauri(f"{PH}/C2_woody.jpg"),         # C2 win (named)
  "book_table":  datauri(BOOK_TABLE),
  "book_spread": datauri(BOOK_SPREAD),
}

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1080px;overflow:hidden;background:#11161b}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.card{position:absolute;top:0;left:0;width:1080px;height:1080px;color:#f3efe6;overflow:hidden;background:#11161b}
.card>*{position:relative}
.brand{position:absolute;top:52px;left:56px;z-index:5;font-size:34px;font-weight:800;letter-spacing:.01em;color:#f3efe6;display:flex;align-items:center;gap:16px;opacity:.96}
.brand .m{width:40px;height:40px;border-radius:9px;background:linear-gradient(135deg,#d9645b,#e69084)}
.brand.dark{color:#1a232a}
.photo>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;z-index:0}
.scrim{position:absolute;left:0;right:0;bottom:0;z-index:3;padding:230px 62px 78px;display:flex;flex-direction:column;background:linear-gradient(to top,rgba(10,14,18,.97) 0%,rgba(10,14,18,.95) 30%,rgba(10,14,18,.72) 58%,rgba(10,14,18,.32) 80%,transparent 100%)}
.desc{font-size:27px;letter-spacing:.13em;text-transform:uppercase;color:#d3dad7;margin-bottom:22px;font-weight:600}
.desc.named{color:#ec9182}
.hl{font-size:52px;line-height:1.1;font-weight:820;letter-spacing:-.015em;max-width:17ch}
.gap{display:flex;align-items:baseline;gap:20px;margin-top:30px;font-variant-numeric:tabular-nums;flex-wrap:wrap}
.gap .est{font-size:40px;color:#c2cac7;text-decoration:line-through;text-decoration-color:rgba(230,120,104,.9);text-decoration-thickness:3px}
.gap .arr{color:#ec9182;font-size:38px}
.gap .sold{font-size:66px;font-weight:860;color:#fff;letter-spacing:-.02em}
.gap .tag{font-size:40px;font-weight:750;color:#84bd95}
.data{display:flex;flex-direction:column;justify-content:center;padding:96px 72px;gap:34px;background:radial-gradient(120% 100% at 78% 8%,#33434c,#212c33 46%,#161f26 100%)}
.data.bone{background:#f3efe6;color:#1a232a}
.klabel{font-size:30px;letter-spacing:.18em;text-transform:uppercase;color:#9aa3a3;font-weight:600}
.data.bone .klabel{color:#7c766a}
.statement{font-size:78px;line-height:1.04;font-weight:850;letter-spacing:-.025em;max-width:15ch}
.statement em{font-family:Georgia,serif;font-style:italic;font-weight:500;color:#e0645b}
.sub{font-size:33px;line-height:1.42;color:#aeb6b5;max-width:26ch}
.data.bone .sub{color:#5f665f}
.bars{display:flex;flex-direction:column;gap:40px;width:100%}
.bl{display:flex;justify-content:space-between;font-size:32px;color:#aeb6b5;margin-bottom:18px}
.bl .v{color:#fff;font-weight:800;font-size:40px}
.track{height:34px;border-radius:18px;background:rgba(255,255,255,.11);overflow:hidden}
.fill{height:100%;border-radius:18px}
.fast .fill{width:14%;background:#7fb890}.slow .fill{width:100%;background:#e0645b}
.twonum{display:flex;flex-direction:column;gap:0;width:100%}
.trow{display:flex;align-items:baseline;justify-content:space-between;padding:34px 0;border-bottom:2px dashed rgba(255,255,255,.2)}
.trow .lab{font-size:32px;letter-spacing:.12em;text-transform:uppercase;color:#9aa3a3}
.trow .fig{font-size:56px;font-weight:840}.trow .fig.est{color:#c2cac7}.trow .fig.real{color:#e0645b;font-family:Georgia,serif;font-style:italic;font-weight:600}
.book>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.bookscrim{position:absolute;left:0;right:0;bottom:0;z-index:3;padding:150px 64px 70px;background:linear-gradient(to top,rgba(12,16,20,.9),rgba(12,16,20,.5) 55%,transparent)}
.cap{font-size:60px;font-weight:840;line-height:1.08;color:#fff;letter-spacing:-.015em;max-width:16ch}
.capsub{font-size:32px;color:#cdd4d1;margin-top:22px}
.ctabtn{display:inline-block;margin-top:38px;background:#d9645b;color:#fff;font-weight:800;font-size:38px;letter-spacing:.01em;padding:26px 44px;border-radius:16px}
"""

def brand(dark=False): return f'<div class="brand{" dark" if dark else ""}"><span class="m"></span>Fields</div>'
def photo_card(img, desc, hl, gap_html, named=False):
    return f'<div class="card photo">{brand()}<img src="{img}"><div class="scrim"><div class="desc{" named" if named else ""}">{desc}</div><div class="hl">{hl}</div>{gap_html}</div></div>'
def estgap(est, sold): return f'<div class="gap"><span class="est">{est}</span><span class="arr">&rarr;</span><span class="sold">{sold}</span></div>'
def wingap(sold, tag): return f'<div class="gap"><span class="sold">{sold}</span><span class="arr">&middot;</span><span class="tag">{tag}</span></div>'
def data_card(inner, bone=False): return f'<div class="card data{" bone" if bone else ""}">{brand(bone)}{inner}</div>'
def book_card(img, cap, capsub=None, cta=None):
    extra = (f'<div class="capsub">{capsub}</div>' if capsub else '') + (f'<span class="ctabtn">{cta}</span>' if cta else '')
    return f'<div class="card book">{brand()}<img src="{img}"><div class="bookscrim"><div class="cap">{cap}</div>{extra}</div></div>'

BOOK5 = book_card(IMG["book_spread"], "A hardcover guide. Real local data &mdash; not a brochure.")
BOOK6 = book_card(IMG["book_table"], "We'll post you a copy. Free.", "Printed, bound, sent to your door. No sales pitch.", "Post me the book &rarr;")

CARDS = {
 # ---- VERSION A · LOSS -> PROOF (contrast) ----
 "A1": photo_card(IMG["huntingdale"], "A 5-bedroom Robina home &middot; sold this year",
        "The estimate everyone was comfortable with. It sold for less.", estgap("$2,300,000","$1,910,000")),
 "A2": data_card('<div class="klabel">61 days on the market</div><div class="statement">A high asking price feels like a safety net.</div>'
        '<div class="sub">In the sales we studied, homes launched above the evidence sat longer &mdash; and more often closed below it. A listing that waits reads as a problem.</div>'),
 "A3": photo_card(IMG["whitehead"], "3 Whitehead Drive, Burleigh Waters",
        "Priced right, it sold in two days &mdash; for more than the home that reached too high.", wingap("$1,965,000","2 days"), named=True),
 "A4": data_card('<div class="statement">You only get one launch.</div>'
        '<div class="sub">The difference between the home that waited and the one that sold in days wasn\'t the house. It was the homework done before the sign went up.</div>', bone=True),
 "A5": BOOK5, "A6": BOOK6,

 # ---- VERSION B · TRUST ----
 "B1": photo_card(IMG["majorca"], "A 5-bedroom Varsity Lakes home",
        "The number a seller checks first, at 11pm &mdash; set $378,000 too high.", estgap("est $2,120,000","$1,742,000")),
 "B2": photo_card(IMG["christine"], "A 4-bedroom Burleigh Waters home",
        'Wrong by over a million &mdash; and rated &ldquo;high confidence.&rdquo;', estgap("est $1,440,000","$2,500,000")),
 "B3": data_card('<div class="twonum"><div class="trow"><span class="lab">The tool sees</span><span class="fig est">beds &middot; old sales</span></div>'
        '<div class="trow"><span class="lab">It never sees</span><span class="fig real">your home</span></div></div>'
        '<div class="sub">It reads bedroom counts and past sales &mdash; not the renovation, the aspect, or the market that turned up the week you listed.</div>'),
 "B4": data_card('<div class="statement">So what <em>is</em> it worth?</div>'
        '<div class="sub">Every real sale near you, adjusted for what makes your home different. The evidence &mdash; not the guess.</div>', bone=True),
 "B5": BOOK5, "B6": BOOK6,

 # ---- VERSION C · CONTROL / HOPE (drumbeat of wins) ----
 "C1": photo_card(IMG["windemere"], "29 Windemere Crescent, Varsity Lakes",
        "Two days on the market. No price cuts. No months of strangers.", wingap("$1,380,000","2 days"), named=True),
 "C2": photo_card(IMG["woody"], "56 Woody Views Way, Robina",
        "It wasn't a bargain they gave away &mdash; the price simply matched the market.", wingap("$1,420,000","10 days"), named=True),
 "C3": data_card('<div class="klabel">Same region &middot; same kind of home</div><div class="bars">'
        '<div class="bar fast"><div class="bl"><span>Priced to the evidence</span><span class="v">2 days</span></div><div class="track"><div class="fill"></div></div></div>'
        '<div class="bar slow"><div class="bl"><span>Priced ahead of it</span><span class="v">61 days</span></div><div class="track"><div class="fill"></div></div></div></div>'
        '<div class="sub">The quick one didn\'t get less for moving fast. Its first ten days weren\'t spent on the wrong price.</div>'),
 "C4": data_card('<div class="statement">More in your hands than anyone tells you.</div>'
        '<div class="sub">Not luck, not the market, not the agent\'s charm. The decisions before the sign goes up decide how it ends.</div>', bone=True),
 "C5": BOOK5, "C6": BOOK6,
}

def render():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="byl_cards_")
    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser")
    for k, body in CARDS.items():
        arm = k[0]; os.makedirs(f"{OUT}/{arm}", exist_ok=True)
        html = f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style></head><body>{body}</body></html>"
        hp = f"{tmp}/{k}.html"; open(hp, "w").write(html)
        raw = f"{tmp}/{k}_raw.png"
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=1080,1200",
                        f"--screenshot={raw}", f"file://{hp}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        Image.open(raw).convert("RGB").crop((0, 0, 1080, 1080)).save(f"{OUT}/{arm}/{k}.png")
        print(f"  rendered {arm}/{k}.png")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Done -> {OUT}/{{A,B,C}}/  (18 cards, 1080x1080)")

if __name__ == "__main__":
    render()
