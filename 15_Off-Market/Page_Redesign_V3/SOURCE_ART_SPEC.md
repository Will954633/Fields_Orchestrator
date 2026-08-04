# Source art spec — drawings that animate like the pandanus

What a drawing must be for the reveal pipeline to turn it into the pandanus
effect: ink arriving stroke by stroke, cream on black, floating in the page with
no frame and no visible edge.

Eight files clear this bar: the pandanus and the whale, plus the five-drawing v2
emblem set delivered 2026-08-02 (gum, reeds, banksia, retriever, satchel). The
six v1 landscape scenes do not, and none of them can be fixed by tuning the
animation — it is a property of the artwork. Together the emblems cover **84% of
all 18,070 built decks**; §5 lists the one drawing still missing.

Verify any new drawing in one command before anything else is done with it:

```bash
cd 15_Off-Market/Page_Redesign_V3/reveals
python3 measure_source.py sources/your_new_drawing.png
```

`PASS` means it will animate like the palm. `FAIL` names the specific property
that is wrong.

---

## 1. The rule, in one sentence

**One object, drawn in line and hatch, floating on blank paper.**

Not a scene. Not a view. Not a photograph rendered as a sketch.

The reveal works by inverting the drawing — paper becomes the deck's black, ink
becomes cream. That is what removes the rectangle and lets the drawing sit *in*
the page instead of *on* it. Inversion only survives if the paper is genuinely
blank, because whatever is the largest area of paper becomes the largest area of
ink. In a landscape the sky is the largest area of paper, so a landscape inverts
into a photographic negative in a hard box. `Parkland.png` is 77% ink and
`bushland.png` is 90%; the pandanus is 24%.

---

## 2. File requirements

| | |
|---|---|
| Format | **PNG**, 8-bit. Never JPEG — its ringing around fine hatch survives cleanup and reads as grey haze. |
| Size | Long edge **≥ 1400px**. The deck renders at ~1024px wide, so this leaves headroom for retina and for cropping. |
| Colour | Greyscale, or RGB that is effectively neutral (mean chroma ≤ 5/255). Colour is discarded. |
| Background | Any of **three** conventions: transparent (alpha 0, preferred), pure white paper, or an already-inverted **light-on-dark plate** — light strokes on a dark ground, drawn as the finished look. All three are read correctly. Transparency is still preferred; pure white (255) accepted. Transparency keeps both polarities available — a filled-body subject can only be rendered correctly if the background can be knocked out (§4). What must not happen is a *near*-white wash, a paper texture, or a soft grey gradient. |
| Transparency | If transparent, it must be true alpha 0 — not a white matte, and no dark fringe on the cutout. |
| Nothing else in the file | No signature, no border, no watermark, no caption, no drop shadow, no vignette. |

`Whale_V2.png` is the model file: true transparency, 100% clean paper.

> The pipeline flattens transparency onto white before doing anything else. It
> did not always — the original palm build called `convert("RGB")`, which
> *discards* alpha and keeps whatever RGB sits underneath. Whale_V2 stores dark
> RGB under its transparent pixels, so that call turned its entire blank
> background into solid ink. Fixed in `build_reveal.py:load_luma`, but it is why
> "transparent" and "white" both need saying out loud.

---

## 3. Composition requirements

**One subject, complete, with air around it.**

- The whole object in frame, with roughly **5–10% clear margin** on every side.
  Nothing may touch or run off the edge. `water_adjacent .png` has ink on 34% of
  its border; the pandanus has 0%.
- **No ground plane, no horizon, no sky, no background objects.** A tree with a
  strip of grass under it fails — the grass is a second subject and it anchors
  the drawing to a bottom edge.
- **No cast shadow.** A shadow pooling under the subject inverts into a bright
  smear.
- **One connected mass of ink.** Small detached elements (a falling leaf, a
  distant bird) are revealed *last* rather than in place, because the growth
  order can only travel through ink. Keep detached bits to under 10% of the ink.
- **No human faces.** This is the reason `Walk to school.png` cannot be used as
  is: inversion turns eyes and teeth into dark holes and the children read as
  ghostly. It is also the only drawing with identifiable people, which is a
  separate question from this spec.

**Build the form out of strokes. Do not outline it.**

This is what decides whether a drawing joins the house style — cream strokes
glowing on black, the way the banksia and the reeds do.

The reveal paints ink. A form built from hatch is ink all the way through, so
inverting it lights the whole form up. A form drawn as an **outline around blank
paper** has nothing inside to light: it inverts into a black shape with a bright
edge, and no amount of processing fixes it. Gamma can lift faint ink; it cannot
invent ink where the artist left paper.

`flag_pole_golf.png` is the case that proved it. Composition was perfect —
transparent background, clean margins, one subject — but the flag's fabric was
blank white inside an outline, so **only 47.8% of its own silhouette carried
ink** against 78–89% for every other emblem. Rebuilt at four gamma values, it
stayed a black flag every time.

`flag_pole_golf_v2.png` is the fix and the model: the same flag with the cloth
**hatched**, fine parallel lines following the fold the way an engraving renders
cloth. It drops straight into the stroke language beside the banksia.

The test in words: **if you deleted the paper, would the drawing still exist?**

`measure_source.py` reports this as `subj%`, and it needs an alpha channel to
know where the subject ends — one more reason to deliver true transparency.

**Give it a base if you can.** A subject that grows from a single point at the
bottom — a trunk, a stem, a clump of reeds — can use the `growth` reveal, where
ink travels up through the drawing and the thing appears to grow. Subjects
without one (the whale, a cone, a flag) use `develop`, where the darkest
structure lands first and the hatch fills in behind it. Both look good; growth
is the more striking of the two, and it is what makes the palm memorable.

---

## 4. The gate

`measure_source.py` enforces three checks. All three are about **composition**,
because composition is what decides whether inversion survives.

| Check | Limit | Why |
|---|---|---|
| `paper_purity_pct` | ≥ 95% | Is there genuinely blank paper behind the subject. This is the one that matters. |
| `edge_contact_pct` | ≤ 2% | Ink at the frame edge means the crop cuts flush and it reads as a box. |
| `largest_blob_pct` | ≥ 90% | One connected mass — **only enforced with `--growth`**. The geodesic reveal travels through ink, so anything detached pops in at the end instead of growing. `develop` never touches the growth channel, and a detached piece there is often deliberate: the pandanus fruit and the golf ball are the elements that leave the drawing for card 04. |
| `subject_ink_pct` | ≥ 70% | Is the form built from strokes, or outlined around blank paper (§3). Needs alpha; skipped without it. |

Density (`ink%`, `solid%`) is **reported but not enforced**. An earlier cut of
this gate capped ink coverage at 35% on the theory that dense drawings invert
badly. The v2 set disproved it: the school satchel is 54% dense once cropped and
renders perfectly, while the parkland scene is 77% dense and renders as a
negative. Density was a proxy that happened to correlate across the first nine
files and broke on the tenth. What actually separates them is that one has blank
paper behind it and the other has a sky.

Use the density figures to judge **visual weight** instead — a 54% drawing is a
solid mass beside the copy where a 23% one is airy. That is a layout decision,
not a defect.

```
drawing                                  size  paper%  edge%  blob%  | ink%  solid%
Bushland_Tree.png                   1024x1536   100.0    0.0   99.2  | 23.0     9.7  PASS
whale.png                           1530x1028    98.5    0.0   99.0  | 23.1     8.9  PASS
bushand_creek_native_flower.png     1024x1536   100.0    0.0   99.9  | 24.1    11.5  PASS
Whale_V2.png                        1536x1024   100.0    0.0   98.6  | 24.9     7.3  PASS
Native_reeds.png                    1024x1536   100.0    0.0   99.3  | 26.1    12.5  PASS
Large_block_dog.png                 1536x1024   100.0    0.0   98.2  | 31.7     7.6  PASS
Hatch_Sketch_Pandanas_Palm.png      1024x1536   100.0    0.0   98.4  | 32.9    19.5  PASS
Walk to school.png                  1342x1172    88.9    0.0   93.7  | 37.1    14.7  FAIL
Pandanas_Palm_Fruit.png             1254x1254   100.0    0.0   99.5  | 52.2    32.2  PASS
School_Walk.png                     1024x1536   100.0    0.0   99.6  | 54.2    18.6  PASS
Golf_course.png                     1448x1086    44.2   10.8   84.5  | 67.4    17.3  FAIL
Parkland.png                        1535x1024    36.5    2.9   96.8  | 76.8    39.5  FAIL
water_adjacent .png                 1535x1024    13.5   34.1   98.5  | 85.1    37.3  FAIL
Robina_Pavillion.png                1536x1024     8.9   14.9   98.6  | 89.1    38.8  FAIL
bushland.png                        1449x1086    10.8    1.7   99.5  | 90.1    29.9  FAIL
```

### Polarity — three routes, one destination

**The test is not whether the output differs from the source. It is whether the
drawn strokes end up light.** That is the house look: black sketch strokes shown
as greys and whites on black. Three source constructions reach it, and which one
a drawing needs can only be told by zooming to pixel level — several of them
look identical at a glance and are opposite underneath.

| `--polarity` | Source construction | What it does |
|---|---|---|
| **`invert`** *(default)* | dark ink on white paper, full frame | Inverts. Paper becomes black, strokes come up cream. The botanicals: pandanus, gum, reeds, banksia, whale. |
| **`invert_cutout`** | dark ink on light material, sitting on a dark ground | Cuts the ground away, then inverts exactly as above. `flag_pole_golf_v2.png` — its cloth is light fabric with dark hatch over it, the same construction as the banksia; only the surround differs. |
| **`positive`** | light strokes on a dark ground (scratchboard), or a light body on a transparent cutout | Paints the subject's own light. The strokes are *already* the light, so nothing is flipped. `Large_block_dog_v2.png`, the satchel. |

Getting this wrong is the single most repeated mistake in this pipeline — six
fix-history entries, every one of them an assumption about what kind of image a
file is. Two worked examples:

- Under `invert`, "light fur" means "little ink" means "nothing painted", so the
  first retriever came out as a **black** dog with bright fur edges, and its
  eyes and nose inverted into bright blobs.
- The flag v2 and the dog v2 are both delivered light-on-dark and look like the
  same kind of file. They are opposites: the flag is dark hatch **on** light
  cloth, the dog is light hatch **on** dark ground. The flag inverts; the dog
  must not.

**So: zoom in before you build.** Crop a patch of the subject at source
resolution and answer one question — *are the marks darker or lighter than what
they sit on?* Darker means `invert` (or `invert_cutout` if the surround is
dark). Lighter means `positive`.

The ground is cut with `ground_mask()`: connected regions of dark pixels **that
touch the frame border**. Ink strokes are dark too, but they are enclosed by the
material they are drawn on and never reach the border, so this keeps them where
a plain threshold would erase them along with the background. It also matters
that the cut is a hard knockout rather than a levels adjustment — these plates
have a mottled ground, and everything above the modal dark tone survives
`CLEAN_FLOOR` and paints a faint grey wash across the deck.

### Reveal mode

`growth` is the house animation — the thing grows rather than resolves, ink
travelling up through the drawing from a seed. It needs a base to travel from,
and `--seed X,Y` when the automatic rule would pick the wrong origin (on the
golf flag it picks the **ball** over the foot of the pole).

Five of the eight grow: pandanus, gum, reeds, banksia, flag. The dog, satchel
and whale use `develop`, which brings the whole form up at once and resolves it.
The dog was tested on `growth` from both a paw and the chest: both leave a
headless torso on screen for most of the animation. A subject that does not grow
from a base should not be made to.

### What the gate still cannot check

**Never faces.** Under `invert`, eyes and teeth become dark holes; under
`positive` the tone survives but AI-drawn faces remain their own problem. It is
why the v1 `Walk to school.png` was unusable even before it failed paper purity,
and why the replacement is a satchel rather than the children.

Always render before committing:

```bash
node render_reveal.js --html out/<stem>.html --mode develop --stills 3 --width 900 \
     --paper "#000000" --ink "#E6DDD2" --grain 0 --vignette 0
```

---

## 5. What to draw

The pandanus works because it is a **symbol of the coast**, not a photograph of
a beach. Every replacement needs to be the equivalent: the single object that
stands for the thing the card is claiming.

The v2 set delivered on 2026-08-02 covers **84% of all 18,070 decks**.

| Angle | Share | Drawing | Stem | Reveal | Detachable for card 04 |
|---|---|---|---|---|---|
| `parkland` → park | **32.4%** | `Bushland_Tree.png` | `tree` | growth | — needed: a gum nut or leaf |
| `school_walk` | **12.8%** | `School_Walk.png` (satchel) | `satchel` | develop | none plausible |
| `water_adjacent` → lake | **12.6%** | `Native_reeds.png` | `reeds` | growth | — needed: a seed head |
| `land_prestige` | **12.4%** | `Large_block_dog.png` | `dog` | develop | the ball |
| `beachside` | 9.3% | `Hatch_Sketch_Pandanas_Palm.png` | `pandanus` | growth | ✅ the fruit |
| `parkland` → bushland / creek | 3.2% | `bushand_creek_native_flower.png` | `banksia` | growth | — needed: a seed |
| `parkland` → reserve / open space | 1.3% | shares `tree` | `tree` | growth | — |
| `water_views` | ~0% | `Whale_V2.png` | `whale` | develop | none plausible |

**Still outstanding — one drawing:**

| Angle | Share | Draw | Reveal |
|---|---|---|---|
| `parkland` → golf course | 3.0% | ✅ `flag_pole_golf_v2.png` — hatched cloth, no crest, no shadow | develop |

`Large_block_dog.png` was a better idea than the fig tree originally specced
here — a big block means room for the dog, which is the emotional claim rather
than the horticultural one. It and the satchel build with `--polarity positive`
(see §4); everything else is the default `invert`.

**Deliberately no drawing:** `market_context` (8.3%), `scarcity` and
`thin_competition` (4.1%), and the 0.2% tail. Those angles are abstract — there
is no object to draw. A decorative image on a card that isn't claiming a
physical feature is just decoration, and the deck has no decoration anywhere
else. Those cards should stay text-only.

`Robina_Pavillion.png` has no angle. It is also a specific named building in one
of three target suburbs, so it can't serve a generic fallback.

### The detachable element

On the beach card the pandanus fruit detaches from the finished drawing, travels
across the page on a canvas layer and comes to rest beside the card-04 copy.
That is what carries the reader from card 03 to card 04.

If you can, supply that second element as its **own file** on the same terms — a
gum nut, a seed head, a leaf. It needs to be a thing that could plausibly fall
off the main drawing, and it should be visible in the main drawing at roughly
the position it will detach from.

Where there is no plausible detachable element (the satchel, the flag), card 04
will need a different continuation and that is a design question, not an art
one.

---

## 6. If you are generating these

The existing set are AI-generated (`Hatch_Sketch_*`). What matters is that the
prompt asks for a plate, not a photograph. A starting point:

> Pen-and-ink cross-hatch illustration of **[subject]**, in the style of a
> 19th-century botanical or natural-history plate. Single isolated subject,
> complete and centred, on a **pure white background**. Fine parallel hatching
> and stippling, white paper visible between the strokes. **No background, no
> sky, no ground, no grass, no horizon, no cast shadow, no border, no frame, no
> signature, no colour.** Line weight varies from hairline to bold; solid black
> used only for the deepest accents.

Then, before anything else:

```bash
python3 measure_source.py sources/new_drawing.png
```

If it fails on `paper_purity` or `ink_coverage`, the generator has almost
certainly given you a background. Ask again for pure white and no environment
rather than trying to clean it up — a background painted out by hand leaves an
edge that shows the moment the drawing is inverted.

---

## 7. Delivery checklist

- [ ] PNG, long edge ≥ 1400px, no JPEG anywhere in its history
- [ ] Background true alpha 0 (preferred) or pure white
- [ ] One subject, complete, 5–10% margin, nothing touching the edge
- [ ] No ground, horizon, sky, shadow, border, signature or people
- [ ] Hatch and line, paper visible between strokes, solid black only as accent
- [ ] `python3 measure_source.py <file>` prints **PASS**
- [ ] Detachable companion element supplied where the table asks for one
- [ ] Dropped into `15_Off-Market/Page_Redesign_V3/reveals/sources/`

Then it is one line to build and one to render:

```bash
# linear subject (strokes) — the default
python3 build_reveal.py --src sources/park_gum.png --stem park --order geodesic --mode growth
# filled-body subject (needs alpha)
python3 build_reveal.py --src sources/golf_flag.png --stem golf2 --polarity positive

node render_reveal.js --html out/park.html --mode growth \
     --paper "#000000" --ink "#E6DDD2" --grain 0 --vignette 0 --out out/park_deck
```
