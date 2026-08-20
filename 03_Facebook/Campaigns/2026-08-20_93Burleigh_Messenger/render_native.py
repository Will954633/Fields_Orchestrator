#!/usr/bin/env python3
"""Render 93 Burleigh carousels in Meta's NATIVE style: clean photo + white panel
with bold headline, grey description and a 'Send message' button underneath.
Matches the $4,150,000 Sandpiper ad's format. Also writes clean 1080x1080 crops
(no text) that become the actual carousel images uploaded to the API."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
RAW  = os.path.join(HERE, "raw")
CLEAN = os.path.join(HERE, "cards_clean")   # <- real API images (no text)
PREV  = os.path.join(HERE, "cards_native")  # <- preview mocks
for d in (CLEAN, PREV): os.makedirs(d, exist_ok=True)

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def square(name, bias_top=False, box=1080):
    im = Image.open(os.path.join(RAW, name)).convert("RGB")
    w, h = im.size; s = min(w, h)
    left = (w - s)//2; top = 0 if bias_top else (h - s)//2
    return im.crop((left, top, left+s, top+s)).resize((box, box), Image.LANCZOS)

def native_card(photo, headline, desc):
    """Photo 1080 + white panel ~236 -> 1080x1316, FB-style."""
    W = 1080; PH = 1080; PANEL = 236; H = PH + PANEL
    canvas = Image.new("RGB", (W, H), (255,255,255))
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas)
    hb = ImageFont.truetype(FB, 40); dr = ImageFont.truetype(FR, 34)
    tx = 40; ty = PH + 40
    # headline (truncate to keep one line, like FB)
    d.text((tx, ty), headline, font=hb, fill=(28,30,33))
    d.text((tx, ty+64), desc, font=dr, fill=(120,124,128))
    # 'Send message' button, right side
    bl = "Send message"; bf = ImageFont.truetype(FB, 32)
    bw = d.textlength(bl, font=bf); bx1 = W-40; bx0 = bx1-(bw+56); by0 = PH+62; by1 = by0+92
    d.rounded_rectangle([bx0,by0,bx1,by1], radius=14, fill=(232,234,238))
    d.text((bx0+28, by0+28), bl, font=bf, fill=(28,30,33))
    return canvas

SETS = {
 "A": {"title":"SET A - Acreage movers",
   "primary":"Want to move closer to Burleigh without giving up your space? 93 Burleigh Street "
             "is 822m2 - proper backyard, a 7x6.2m powered workshop, a 220m2 home - and a 1km "
             "walk from Burleigh Beach. It's unrenovated, which is exactly why it's $1,915,000. "
             "Message me for the full property pack.",
   "cards":[("01_Hero",True, "822m2 in Burleigh Waters","A 1km walk to the beach"),
            ("25",False,"7 x 6.2m powered workshop","Room for the tools, boat + projects"),
            ("26",False,"220m2 family home","Four bedrooms upstairs"),
            ("22t",False,"A separate downstairs zone","Its own kitchenette + bathroom"),
            ("09t",False,"Unrenovated - priced for it","$1,915,000"),
            ("02",True, "93 Burleigh Street","Message me for the property pack")]},
 "B": {"title":"SET B - Local: buy what you can't renovate",
   "primary":"Buy the things you can't renovate. 93 Burleigh Street, Burleigh Waters: 822m2, "
             "~19.9m frontage, a 1km walk to the beach - and a 44m2 powered workshop. The kitchen "
             "and bathroom are original, which is exactly why it's $1,915,000. Change the house; "
             "keep the land and location for good. Message me for the property pack.",
   "cards":[("01_Hero",True,"822m2 . ~19.9m frontage","1km walk to Burleigh Beach"),
            ("25",False,"44m2 powered workshop","Hard to find this close to Burleigh"),
            ("26",False,"220m2 . 4 bed . 3 bath","Solid family home on the block"),
            ("09t",False,"Original kitchen","Shown honestly"),
            ("21t",False,"Original bathroom","That's why it's $1,915,000"),
            ("02",True,"Change the house, keep the land","Message me for the property pack")]},
 "C": {"title":"SET C - Sydney",
   "primary":"What does $1,915,000 buy walking distance to Burleigh Beach? 93 Burleigh Street, "
             "Burleigh Waters: 822m2 of land, a 220m2 home (4 bed, 3 bath), a 7x6.2m workshop and "
             "a big backyard - a 1km walk from the sand. The catch? It hasn't been renovated, so "
             "you're not paying for someone else's. Message me for the floorplan, data + a video walkthrough.",
   "cards":[("01_Hero",True,"$1,915,000 in Burleigh Waters","822m2, 1km to the beach"),
            ("26",False,"220m2 . 4 bed . 3 bath","A full house, not an apartment"),
            ("25",False,"7 x 6.2m workshop + backyard","Space that's hard to buy down south"),
            ("12t",False,"Room to spread out","Living upstairs and down"),
            ("09t",False,"Not renovated","So you're not paying for someone else's"),
            ("01_Hero",True,"93 Burleigh Street","Message me for floorplan + video")]},
}

def wrap(draw, text, font, maxw):
    words=text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if draw.textlength(t,font=font)<=maxw: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines

for arm, spec in SETS.items():
    os.makedirs(f"{CLEAN}/{arm}", exist_ok=True)
    mocks=[]
    seen={}
    for i,(name,bias,hl,de) in enumerate(spec["cards"],1):
        sq = square(f"{name}.jpg", bias_top=bias)
        sq.save(f"{CLEAN}/{arm}/{arm}{i}_{name}.png")   # clean API image
        mocks.append(native_card(sq, hl, de))
    # Build a phone-style preview: primary text block + filmstrip of native cards
    th=430; gap=16; n=len(mocks)
    strip_w = gap + n*(int(th*1080/1316)+gap)
    cw = int(th*1080/1316)
    # primary text area
    tmp=Image.new("RGB",(10,10)); dd=ImageDraw.Draw(tmp)
    pf=ImageFont.truetype(FR,30); tf=ImageFont.truetype(FB,30)
    plines=wrap(dd,spec["primary"],pf,strip_w-80)
    ptop=54+len(plines)*40+30
    page=Image.new("RGB",(strip_w, ptop+th+40),(255,255,255))
    d=ImageDraw.Draw(page)
    d.text((40,20),"Fields Real Estate  ",font=tf,fill=(24,26,29))
    d.text((40,54),"Ad",font=pf,fill=(130,134,138))
    for j,ln in enumerate(plines):
        d.text((40,90+j*40),ln,font=pf,fill=(30,32,35))
    y0=ptop
    for k,m in enumerate(mocks):
        t=m.copy(); t.thumbnail((cw,th))
        page.paste(t,(gap+k*(cw+gap), y0))
    page.save(f"{PREV}/preview_{arm}.jpg",quality=90)
    print("preview", arm, page.size)
print("clean images ->", CLEAN)
