# The Fridge — what happens after someone scans the magnet

**Status:** scoping + a **working prototype**. Nothing on the live site, no route
exists yet.
**Scope:** the landing experience at `https://fieldsestate.com.au/fridge` — a
monochrome fridge door that opens to reveal a short list of things the owner can
do next.

> ### ▶ Look at it
> **https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/**
>
> Open it on a phone. It opens itself after 0.8 s, or on any touch. There is no
> build step — edit `fridge.css` and refresh.
>
> **There is no fridge artwork and there is no video.** Every surface — door,
> handle, gasket, shelves, lamp, thickness — is a CSS gradient. The images are
> the magnet twin (8.5 KB, a downscale of the real print file), a 128 px grain
> tile (12 KB) that stops the large gradients banding on OLED, and the child's
> drawing (49 KB gzipped SVG). Total added weight: **~70 KB**.
>
> | Param | |
> |---|---|
> | `?art=mono` | drawing in greyscale instead of colour |
> | `?sound=0` | silent |
> | `?debug=1` | log events + audio state to the console |

---

## 1. What already exists (verified today, not assumed)

This is not a greenfield concept. Three quarters of the physical half is already
built and the destination is already wired. Checked directly rather than taken
from notes:

| Thing | State | Evidence |
|---|---|---|
| Magnet artwork | **Print-ready**, 4 products, RGB + CMYK vector PDFs | [`00_Run_Commands/Logo_Files/fridge_magnet/`](../../../00_Run_Commands/Logo_Files/fridge_magnet/) |
| QR payload | `https://fieldsestate.com.au/fridge` | Decoded back out of both 300 DPI print PNGs with OpenCV — exact string match |
| `/fridge` short link | **Live**, 301 | `curl -I` → `301` → `/analyse-your-home?utm_source=fridge_magnet&utm_medium=print&utm_campaign=fridge_magnet_bizcard` |
| Scan attribution | Working | `utm_*` survives the `strip-tracking-params` edge fn (it only removes `fbclid`/`gclid`) |
| Physical print run | **No record of an order** | No fix-history entry, no invoice, no supplier note |

The current magnet is the **green business-card variant** — 90 × 55 mm, grass
`#22382C` field, white lockup, copper full-stop, and a 22 mm white-tiled QR in
the bottom-right corner. It is not a white card; the later `_GREEN_` build
inverted it, and that is the one to treat as current.

### The insertion point is a single line of `netlify.toml`

```toml
[[redirects]]
  from = "/fridge"
  to = "/analyse-your-home?utm_source=fridge_magnet&utm_medium=print&utm_campaign=fridge_magnet_bizcard"
  status = 301
  force = true
```

**This is the most valuable thing in the whole file.** The QR encodes a short
link, not a page. Whoever set that up bought the ability to change the
destination forever without reprinting a single magnet. The fridge animation
does not require new artwork, a new QR, or a reprint — it requires repointing
one redirect.

Two consequences worth stating before anything is designed:

1. **The QR must not change.** If magnets have already been printed, changing
   the payload orphans every one of them. If they haven't, there is still no
   reason to — `/fridge` is already the right level of indirection.
2. **`utm_source=fridge_magnet` must survive the move.** It is the only
   evidence a scan ever happened. A new route that drops the query string makes
   the entire channel invisible, which is the exact failure
   [[self_monitoring_ongoing_processes]] exists to prevent.

The `strip-tracking-params` edge function removes only `fbclid` and `gclid`
(`netlify/edge-functions/strip-tracking-params.js:9`) and skips `/api/*` and
`/assets/*` entirely — so `utm_*` survives, and so would a future `?k=<code>`
token. That is what makes §7's v2 rung possible without touching the edge layer.

### One defect worth fixing while we're here

There is already a shipped physical-scan attribution path, and **the magnet
misses it by one word.** `netlify/functions/minisite-visit.mjs:121` classifies a
printed-QR scan as:

```js
const isQr = !!utmContent && (utmMedium === "qr" || (data.utm_source||"") === "printed_appraisal");
```

The `/fridge` redirect sets `utm_medium=print`, not `qr`, and sets no
`utm_content`. So a magnet scan is **not** currently recognised as a QR event by
the code built to recognise QR events. Either move the redirect to
`utm_medium=qr`, or widen that condition. It's a one-line decision, but left
alone it silently keeps magnet scans out of the physical-attribution data.

---

## 2. Why this moment is worth building something for

Every other landing page we run has to guess where the reader is. This one
doesn't. When the QR fires we know, with more confidence than anywhere else in
the business:

- They are **in a kitchen**, standing at a fridge.
- They are **holding the phone up to the object the screen is about to depict**.
- They **chose** this. A QR scan is a deliberate act — raise the phone, hold it
  steady, tap the banner. It is a far stronger intent signal than a click.
- They are almost certainly **alone and unhurried**. Nobody scans a fridge
  magnet in a meeting.

That last point matters more than it sounds. Our whole funnel problem, per
[[contact_capture_reality_and_address_mail_strategy]], is that people won't hand
over details to an agent. A hesitant homeowner standing alone in their own
kitchen, having volunteered the scan, is the least defended this audience ever
gets. It is worth more than a good page.

**The trick to spend it on: continuity of place.** They look up at the fridge,
look down at the phone, and the phone has a fridge on it — with our magnet still
stuck to the door. For about a second they are looking at the same object twice.
Then it opens, and something is inside.

Nothing else we ship gets to do that, because nothing else knows where the
reader is standing.

---

## 3. "Black and white" — what it should actually mean here

Will's brief says black and white. That instinct is right, and it's right for
three reasons worth writing down so the treatment doesn't drift in build:

1. **The payload of the moment is light.** A door opens and the interior lamp
   spills out. Light is a luminance event, and monochrome is a luminance-only
   medium. Colour would compete with the single thing that has to dominate.
2. **Colour would make it a product shot.** [[illuminus_neon_cta]] cost four
   variants to learn this: the more photographic the object got, the less it
   read as something you could press. A rendered stainless fridge in colour
   looks like an appliance listing. Flattened to graphite and bone it reads as a
   graphic — and a graphic is pressable.
3. **It dodges a real clash.** The magnet is grass-green and copper. A photoreal
   steel-white fridge carrying green UI would look like two brands. Monochrome
   removes the question entirely.

### But not `#000` and `#fff` — the theme file forbids it

`src/styles/theme.css:41` states the rule outright:

> *"Every dark in the product is a shade of the brand green, not an invented
> near-black. Same hue (147.3°) and saturation (24.4%) throughout; only
> lightness varies."*

So a pure black-and-white fridge would be **off-brand by an explicit written
rule**, and it would look subtly wrong next to every other Fields surface
without anyone being able to say why. Build the monochrome from the existing
ramp instead:

| Role | Token | Value |
|---|---|---|
| Kitchen dark / void behind the fridge | `--grass-900` | `#0b110e` |
| Door face, unlit side | `--grass-800` | `#101a14` |
| Door face, lit side / edge slab | `--grass-700` → `--grass-600` | `#16241c` → `#1c2e24` |
| Interior light, cool falloff | `--fields-birch` at low alpha | `#e6ddd2` |
| Interior light, hot core | near-white, birch-tinted | `#f4efe8` |

Read side by side with a true greyscale this is indistinguishable to the eye —
147° at 24% saturation is barely a colour — but it sits in the same family as
every other page. It is black and white *in the way Fields does black and
white*.

Worth knowing: **a monochrome surface is net-new here.** The only `grayscale()`
in the entire codebase is on the ContactPage map
(`ContactPage.module.css:146`), and there is no `data-theme` value other than
`light` and `dark`. Nothing existing needs to be respected or matched — but
equally, nothing existing can be borrowed.

### Reserve the one piece of colour

The entire sequence stays monochrome, and **copper enters exactly once** — on
the chosen option, or on the final action. One accent in an otherwise colourless
world carries enormous weight, and it is free. Use `--copper-on-dark` (`#dd8f6d`),
not `--fields-copper`; theme.css:34 records that plain copper fails WCAG AA on
grass at 3.02:1, and the lifted value clears it at 4.92:1.

---

## 4. The sequence

Total to fully open: **~2.6 s**, with the first meaningful frame immediate.

| # | Phase | Duration | What happens |
|---|---|---|---|
| 0 | **Recognition** | 0.0 → 0.8 s | Closed door, dead centre. A child's drawing pinned up by **two of our magnets** — the same green card they just scanned. Faint specular sheen drifts across the steel. |
| 1 | **Seal** | — | A hairline of warm light down the hinge seam. The promise: something is lit in there. |
| 2 | **Break** | 0.8 → 0.95 s | The gasket lets go. Fast initial movement, then the door's mass takes over. |
| 3 | **Swing** | 0.95 → 2.5 s | Heavy deceleration through to 100°. Light wedge widens across the floor. |
| 4 | **Strike** | 1.06 → 2.2 s | **The lamp strikes and stutters** — 6 dropouts over ~1.1 s, then catches and holds. Every edge is a hard step. |
| 5 | **Reveal** | 1.4 → 2.5 s | Shelves light in sequence, top first, on a 90 ms stagger driven by the same door angle. |
| 6 | **Rest** | 2.5 s → | Door held open. Lamp breathes ±3% on a 6 s cycle. Compressor hum, if the tap earned audio. |
| — | **Close** | 1.02 s | Reversed easing: you push it, the gasket *snatches* it shut. The light stays on until the door seats, then cuts. |

Two deliberate choices in that table:

**The reveal overlaps the swing.** Waiting for the door to finish before showing
options adds a full second of nothing. Driving the option opacity off the same
angle variable means content is readable at ~1.8 s while the motion is still
resolving.

**The magnet is on the door in phase 0.** This is the whole idea and it costs one
image. If it gets cut for time, cut something else.

### Pull, or open by itself? Both — and it closes again

- The door responds to **any touch anywhere**, not a handle hitbox. Asking
  someone to find a 40 px handle on a phone in a kitchen is a failure mode with
  no upside.
- If untouched, it **auto-opens at 0.8 s**. Nobody may be left staring at a
  closed fridge wondering whether the page is broken.
- **It closes again.** Tapping the room around the fridge — or the prompt below
  it, which swaps to "Close" — shuts the door. Being able to shut it and open it
  again is most of what makes the thing feel like an object rather than an
  intro animation, and it costs nothing.
- **A tap inside the cavity does *not* close it.** Otherwise people lose the
  menu while reaching for an option. The interior is deliberately inert; only
  the door and the room are close targets.
- A real touch is worth capturing separately (`fridge_pulled` vs `fridge_auto`) —
  it's a genuine engagement signal, and it is the **only** way to get the user
  activation that audio needs (§10).

> ⚠ **Measured, not assumed:** once open at 100°, the door's own hit area is only
> **~25 px wide**. That is far too small to be the sole close affordance, which
> is why the prompt stays on screen and swaps its copy. Found with
> `document.elementFromPoint`, not by looking at it.

## 5. How it's built

**CSS 3D transforms on a `perspective` parent. Not video, not WebGL.**

```
.stage      { perspective: 1400px; perspective-origin: 50% 45%; }
.door       { transform-origin: left center;
              transform: rotateY(calc(var(--open) * -72deg)); }
.doorEdge   { transform: rotateY(90deg) translateZ(...); }   /* the thickness */
.interior   { /* sibling, painted behind, revealed as the door leaves */ }
```

Everything — light wedge width, face luminance, option opacity, shadow length —
is a function of the single custom property `--open` (0 → 1). One variable
drives the whole frame, which is what makes it draggable, interruptible, and
trivially reversible.

**Why not the alternatives:**

| Approach | Why not |
|---|---|
| Pre-rendered video / sprite sequence | Fixed aspect (fatal across phone viewports), 0.5–3 MB, can't be dragged or interrupted, and autoplay policy makes the first frame a coin toss |
| WebGL / three.js | ~150 KB of runtime before a single pixel, battery cost, and a fallback path to write anyway — for a rectangle rotating about one axis |
| Lottie / After Effects | Another dependency, still fixed-geometry, and nobody here can iterate on it without AE |

CSS is not the cheap option here; it is the *correct* one. The object is one
rigid body rotating about one axis. That is exactly what `rotateY` is.

### Follow the BreakGlass file layout — the prototype *is* the production code

This is the most useful thing in the recon and it changes the build plan. In
`src/components/BreakGlass/`, the 3,064 lines of behaviour deliberately live in
**plain `.js` and `.css` under `public/`, not in `.tsx`** — with hand-written
`.d.ts` files for types. The `.tsx` is a 184-line SSR shell and nothing more.

The reason (`BreakGlass.tsx:19-21`, `README.md:11-16`): the concept workbench at
`vm.fieldsestate.com.au/concepts/…` loads *those exact files* in a browser with
no build step, so the prototype and production **cannot drift**. The same
pattern runs the V3 outro (`discovery-v3/useOutro.ts` injects ordered
`<script async=false>` tags pointing at `public/off-market-v3/`).

Applied here: write `fridge.css` + `fridge.js` in this folder, iterate them live
at the concepts URL, then symlink or copy them to `public/fridge/` and add a thin
route module. **Step 1 of the build is not a throwaway mock — it's the shipping
artifact.** That collapses steps 1 and 4 of §13 into largely the same work.

One hard constraint that comes with the pattern: assets go in `public/`, **never
`src/assets/`** — Vite bundles the latter and defeats the whole lazy-load.

### The seven details that make it read as a fridge

A naive `rotateY` looks like a flipping card. Each of these is small, and each
one is load-bearing:

1. **Thickness.** A fridge door is ~65 mm of insulation. A single plane has no
   edge. Build it as two faces joined at 90° — front + edge slab — so the slab
   comes into view as it swings. Without this it reads as paper.
2. **The gasket break.** A fridge is magnetically sealed. The motion is
   *resist → release → heavy*, never a smooth ease-out. Phase 2 exists solely
   for this. It is the single highest-value detail in the list.
3. **Cosine falloff.** The face luminance follows `cos(angle)` as it turns from
   the front light. One line, and it stops the door looking like a flat sticker.
4. **The light wedge.** The interior lamp throws a hard-edged wedge onto the
   floor that widens with the door angle. Same `--open` variable. This is what
   sells "a light just came on in a dark room".
5. **Mass.** Deceleration must be long and asymmetric — a heavy door decelerates
   over roughly 4× the time it accelerates. `cubic-bezier(.12,.72,.16,1)` or a
   short spring.
6. **Contact shadow.** The door casts a moving shadow on the fridge body. Cheap,
   and the frame looks pasted-together without it.
7. **Never fully dead.** After rest, the lamp breathes ±3% on a 6 s cycle. A
   perfectly static frame reads as a screenshot, and people stop expecting it to
   respond.

---

## 6. What's inside

**Recommendation: shelves as rails, options as clean typographic rows.** Not
milk cartons and jars.

The temptation is to make each option a fridge item. Resist it — it's slow to
read, impossible to label clearly, and it makes a data business look like a
game. The fridge should be the *frame*, and the joke should be the container,
not the contents. The delight is the light sweeping across the shelves and
lighting each row in turn — not the props.

Four options, because a fridge has three or four shelves and five is a menu
rather than a moment:

| Shelf | Label | Destination | Verified |
|---|---|---|---|
| Top (lit first) | What's happening in *your suburb* | `/market-intelligence/:suburb` | `200` |
| 2 | What sold near you recently | `/sold` | `200` |
| 3 | What's for sale nearby | `/for-sale` | `200` |
| 4 | What's my home worth | `/analyse-your-home` | `200` |

All four destinations were fetched live and return 200. `/analyse-your-home` is
last deliberately — it is the current destination and the conversion page, and
putting the ask at the bottom of a list of free things is the buyer-first
sequencing the business already runs on.

**The door shelves are free real estate.** A real fridge door has its own
shelves, and once it swings toward the viewer they face the camera. That is the
natural home for the low-priority secondary actions — save this, or contact —
without cluttering the main list. Geometry doing layout work.

### Editorial constraints on the copy

Non-negotiable, per [[feedback_no_advice_data_only]]:

- **No advice.** "What sold near you recently" ✅. "Now's a good time to sell" ❌.
- **No figure in a headline.** "What's my home worth" ✅ as a question.
  "$1,250,000" on a shelf ❌ — see [[feedback_no_valuation_in_headlines]].
  If a number ever appears here it must be a **range**
  ([[valuation_method_comparables]]).
- **Don't assert where they are.** The magnet travels. It ends up on a rental, a
  friend's fridge, a parent's fridge. Copy may *assume* a kitchen; it must not
  *state* it. "Look up at your fridge" is a bad line the first time it's read on
  a couch.
- No forbidden words. Nothing on that list would naturally appear here anyway.

---

## 7. Personalisation — the ladder, cheapest first

The strongest version of this is a fridge that opens to reveal **their own
house**. Top shelf reads *14 Fern Street* and every option below it is about
that address. That is a different emotional event to a generic menu.

Three rungs, and v1 must work with none of it:

| Rung | Mechanism | Print change | Effort |
|---|---|---|---|
| **v1** | Generic. Four options, no identity. Suburb from IP or omitted. | None | — |
| **v1.5** | On load, call `GET /api/v1/my-home?distinct_id=&device_token=`. If it resolves, swap the top shelf to their address. | **None** | Hours |
| **v2** | Per-magnet code `/fridge?k=<code>` on the run that ships with posted appraisals. Resolves to a known address. | New QR on *future* magnets only | Days |

**v1.5 is the buy.** The resolver already exists, is already read-only and
address-only, and already ranks candidates by confidence
([[home_recognition_personalization]]). Anyone who has previously used Analyse
Your Home or landed on their own `/off-market` page from Google is already
recognisable. It costs one fetch and changes one line of text, and it changes
the page from a menu into a greeting.

Two landmines that memory says will bite:

- Any **new** `crm_contacts` field written here must be added to `crm_sync.py`'s
  carry-forward allow-list or the hourly `replace_one` wipes it within the hour.
- If it's a sub-document, carry it forward as `.get("field") or {}`, never
  `.get("field")` — a bare null makes every later dotted `$set` raise
  `WriteError 28`. This has already broken three jobs.

`physical_scan` is already in that allow-list and is already written by
`minisite-visit.mjs` for printed-mailer scans. A magnet scan is the same class of
event and should reuse it rather than inventing a parallel field.

---

## 8. Asset register

Deliberately short. Almost everything is CSS, and that is the point — every
byte is a byte that has to arrive over kitchen 4G before the moment works.

### Must have

| # | Asset | Format | Est. size | Source |
|---|---|---|---|---|
| 0 | **The child's drawing** — `assets/artwork.svg`, generated by `build_artwork.py` | SVG, exact A4 landscape | 49 KB gzip | **The single best thing on the door.** Generated so it scales and can be recoloured; drop in a real photo as `assets/artwork.jpg` to replace it. |
| 1 | **Magnet twin** — ×2, straddling the drawing's top edge | WebP, ~400 px wide, 2× | ~12 KB | Derive from existing `Fields_BusinessCard_90x55_QR_GREEN_300dpi.png`. Downscale + slight desaturate so it sits in the monochrome world without going grey. |
| 2 | **Grain tile** — tileable luminance noise | PNG, 128×128, 8-bit grey | ~8 KB | Generated. **Not optional** — large smooth gradients band severely on phone OLED, and this door is nothing but large smooth gradients. |
| 3 | Door face, handle, edge slab, hinges | CSS gradients | **0 B** | Built, not drawn |
| 4 | Shelves, wire grid, interior walls | CSS (`repeating-linear-gradient`) | **0 B** | Built |
| 5 | Interior lamp + light wedge | CSS radial + `mix-blend-mode` | **0 B** | Built |
| 6 | Option labels + microcopy | Text | — | Written to §6 rules, Will to approve |
| 7 | Fields lockup, mono | Existing PNG | ~48 KB → re-export ~6 KB | `Fields_Logo_FullName_tight_white.png` exists |
| 8 | OG image + title for `/fridge` | PNG 1200×630 | ~40 KB | The link will get shared; today it would inherit AYH's card |

### Scale — everything on the door is at real size

Not "about right". The stage is 340 × 620 px and the door is **700 mm wide**
(standard AU single fridge door), which makes the scale 2.06 mm/px and the door
read as 700 × 1276 mm. Everything else derives from that, and is measured:

| | Should be | Renders as |
|---|---|---|
| Door | 700 mm wide | **700.0 × 1276.5 mm** |
| Drawing | A4 landscape, 297 × 210 mm | **296.5 × 210.0 mm** |
| Magnet | 90 × 55 mm | **88.5 × 53.5 mm** |

Two things that fell out of measuring rather than eyeballing:

1. **The magnet PNG is the 96 × 61 mm bleed artboard, not the 90 × 55 mm card.**
   `PRINT_SPEC.md` says so plainly — 3 mm bleed all round — but the file name
   says `90x55` and it is easy to use whole. Shown uncropped it renders the
   magnet **6.7% oversized at the wrong aspect** (1.573 vs the real 1.636).
   `assets/` now crops to the trim box. Anyone reusing that PNG on screen
   anywhere else will hit this.
2. **`getBoundingClientRect()` lies here.** The sheet is rotated 1.2°, and the
   rect returns the *rotated bounding box* — which measured the aspect as 1.393
   and made a correct A4 look wrong. Use `offsetWidth`/`offsetHeight` for
   anything rotated.

The magnet is sized as a percentage of the *sheet* (30.4% = 90/296.5), so it
stays correct at any door size for free. Change the door width and the whole
composition rescales together.

### Nice to have

| # | Asset | Format | Est. size | Note |
|---|---|---|---|---|
| 9 | Silhouette shelf items (bottle, jar, carton) | Inline SVG paths | ~2 KB ea | Depth and life at the edges of frame. Silhouettes only — no detail, no colour. |
| 10 | Handwritten "note under a magnet" | SVG | ~4 KB | The natural treatment for the **personalised** shelf at v1.5. Charming precisely because it's the one hand-made thing. |

### Audio — **Will's own fridge, recorded**

The synthesised version is gone. Will recorded his actual fridge; the raw files
are in `assets/source/` and `assets/build_audio.sh` turns them into web assets.

| Ships as | From | Size |
|---|---|---|
| `fridge-open.m4a` — the gasket peeling off the frame | `fridge_opening.m4a` (6.19 s) | 11 KB |
| `fridge-close.m4a` — the door landing, seal snatching shut | `fridge_closing.m4a` (5.59 s) | 13 KB |
| `fridge-hum.m4a` — the compressor, **seamless 4 s loop** | `Fridge Running.m4a` (10.97 s) | 42 KB |

Three things the processing had to solve, none of them obvious:

**1. The events are buried in silence.** Measured with a 5 ms RMS envelope, not
guessed: the open transient peaks at **1.930 s** into its recording and the
close impact at **2.160 s**. Each door event is under 0.4 s. Shipping the 6 s
files would put half a second between the tap and the sound.

**2. The hum recording ramps in level** end to end — mic AGC settling — so the
first half is unusable as a bed and a naive loop pumps. We take the steady tail
from 6 s, even it with `dynaudnorm`, then build a genuinely seamless loop: for a
loop of length *L* from a source of *L+C*, `acrossfade(S[C..L+C], S[0..C], d=C)`
ends in a crossfade into `S[0..C]`, whose tail lands on `S[C]` — exactly where
the output begins. **Verified: the wrap-point sample delta is 1, against a
median step of 107 inside the loop.** No click.

**3. The sounds are scheduled, not fired.** Both clips have their transient in
the middle, and the door takes over a second to move — so playing either on the
tap desynchronises it from the picture. Solved from the CSS easing curves:

| | transient is | door reaches | so the clip starts at |
|---|---|---|---|
| Open | 0.130 s into the clip | seal breaks at 0.224 s | **0.094 s** after the tap |
| Close | 0.060 s into the clip | seats at 1.015 s | **0.955 s** after the tap |

Fire the close sound on the tap and you hear the slam a full second before the
door arrives. ⚠ **These numbers are solved against the two CSS easings — change
either curve or duration and the sound desynchronises.** The open easing was
retuned to `cubic-bezier(.42,.03,.28,1)` in the process: the old curve left the
door visually motionless for **433 ms** after a tap, which reads as a dead page.

**The hum runs continuously**, open or shut — a fridge doesn't stop when you
close the door — and lifts from 0.10 to 0.28 gain when the door opens, because
you're then hearing into the cabinet rather than through it.

⚠ **It cannot start before the visitor touches the screen.** Audible autoplay is
blocked in every browser; that is policy, not a bug and not something to work
around. What we *can* do, and do: create the context and decode all three clips
on load (a context made without a gesture starts suspended, and `decodeAudioData`
works fine suspended), so the hum begins the instant they first touch rather
than a fetch later. The 0.8 s auto-open is therefore **silent by design** — no
gesture has happened, so on Android the context would report `running` and emit
nothing, with no way for us to detect it.

Ambient audio that runs continuously needs an off switch, so there's a small
mute control bottom-right. It only appears once audio is actually running.

### Not needed — worth saying explicitly

- **No new webfont.** The site's fonts are already loaded; adding one is
  render-blocking on exactly the connection this page will be opened over.
- **No photographic fridge render.** A 2× render for a tall phone screen is
  300–800 KB, locks the aspect ratio, and per §3 actively hurts pressability.
- **No new QR, no reprint.** §1.

---

## 9. Performance — the constraint that decides whether this works at all

Measured on the live destination today:

| Metric | Measured |
|---|---|
| SSR HTML | 27,921 B |
| Time to HTML (incl. the 301) | 0.584 s |
| JS + CSS, compressed, 25 files | **224,640 B (219 KB)** |

219 KB of JavaScript has to land and hydrate before a React component can
animate anything. Over a kitchen 4G connection with two bars that is plausibly
1.5–2.5 s of blank screen *before* a 2.6 s animation starts. The moment would be
dead on arrival.

**So the door must not be a React animation.** The requirement:

> The closed door, the magnet, and the swing must all be in the **SSR HTML and
> CSS**, and the animation must run on a pure CSS keyframe/transition with no
> JavaScript. JS enhances — drag-to-open, audio, personalisation, analytics —
> and every one of those is optional.

That inverts the usual build order and it is the single most important technical
decision in this document. Concretely:

- Door paints at **~0.6 s** (HTML + CSS only), auto-opens at 0.8 s, options
  readable at ~1.8 s — all before the bundle has necessarily arrived.
- The four option links must be **real `<a>` elements in the initial HTML**,
  merely occluded by the door. Not injected after the animation. This is also
  what makes them work for screen readers, for no-JS, and for crawlers.
- Budget: **first meaningful paint < 1.2 s on 4G**, total added weight over the
  SSR HTML **< 40 KB**.
- Any query-param-dependent state (the suburb, a future `?k=` code) must be read
  **in the route loader, server-side**, not in a client effect — exactly as
  `src/routes/off-market.$slug.tsx:373-376` does for its printed-report param.
  Reading it client-side gives an SSR/hydration mismatch, and this app has
  already been bitten by React #418 in `root.tsx`.

Worth measuring before committing: whether `/fridge` should be a route inside
the React app at all, or a near-static page that skips the app shell. The 219 KB
number argues strongly for the latter.

---

## 10. Known landmines

Each of these has already cost this codebase real time. None is hypothetical.

1. **⚠ Android audio is unsolved.** `touchstart` and `pointerdown` grant **no
   user activation** on Android Chrome — activation lands on `touchend` /
   `pointerup` / `click`. The V3 neon sign is *still silent* on Will's handset
   after five rounds of fixes. **Ship v1 silent.** If audio is wanted, arm it on
   `pointerup`, ask `navigator.userActivation.isActive` rather than latching a
   flag off the event type, and reuse the existing `hasActivation` helper in
   `src/components/WhaleMoment/whaleAudio.ts`. Read
   `Page_Redesign_V3/NEON_SOUND_UNSOLVED.md` first. Headless Chrome grants
   activation cold and has no speaker — **it cannot reproduce this class of bug
   at all.**
2. **iOS Safari: `filter: blur()` on a 3D-transformed element** triggers
   catastrophic repaint. Put blur on separate, untransformed layers or pre-bake
   it into a gradient.
3. **`backdrop-filter` drops frames badly on iOS during a transform.** Don't.
4. **Gradient banding** on large monochrome fills is severe on OLED. This is
   what asset #2 is for.
5. **Safe areas.** The door should bleed under the notch — it's a physical
   object filling the frame — but every option row must respect
   `env(safe-area-inset-*)` or the bottom shelf lands under the home indicator.
6. **Landscape and tablet.** A left-hinged door on a wide viewport looks wrong
   and wastes the frame. Needs a breakpoint; the fridge should stay portrait-ish
   and let the room fall away either side.
7. **Double-scan.** iOS camera preview means people commonly scan twice. Dedupe
   in analytics or the denominator is inflated.
8. **A pointer-driven door cannot be tested with a synthetic click.** BreakGlass
   binds `pointerdown`/`move`/`up` and **no** `click` listener
   (`breakGlassEngine.js:268`); its README records that synthetic clicks
   silently do nothing and this has produced false "the feature is broken"
   readings more than once. If drag-to-open is built, the test must dispatch a
   real pointer sequence.
9. **`git status` is unreliable in this repo** ([[git_local_drift_gh_api]]) —
   verify what's actually deployed with `gh api`, and push with
   `scripts/push_website_files.py`, never a loop of `gh api contents` calls
   ([[batched_website_push_tool]]).

---

## 10a. Verification — the existing harness will not catch a broken fridge

This is worth its own heading because the failure is silent.
`01_New_Versions/August_2026/break-glass-check.mjs:1-8` records that the
24-capture `visual-check.mjs` suite **does not cover interaction components** —
it measures page-level properties, never scrolls to the component, and reports
"no measurable differences" whether the component works perfectly or is
completely broken. That is the instrument-failure class in
[[website_verification_gates]]: a green check that means nothing.

So a **dedicated check script is required**, modelled on `break-glass-check.mjs`.
Puppeteer is a direct dependency of the website project
(`package.json:19`, `^24.36.1`), resolved with an absolute `createRequire` so it
works from any cwd:

```js
import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
```

What it must assert, at 390×844 and 1440×950:

1. The four option `<a>` hrefs are present in the **SSR HTML** (curl, before any
   JS) — this is the §9 contract and the one most likely to regress.
2. `utm_source=fridge_magnet` survives the redirect into the final URL.
3. The door reaches its open transform without JS enabled.
4. With `prefers-reduced-motion: reduce` emulated, the door starts open.
5. No horizontal overflow, and the bottom shelf clears `env(safe-area-inset-bottom)`.

Plus `node scripts/site-inspector.js --url /fridge --mobile` and **read the
screenshot** — CLAUDE.md steps 3–5, mandatory after any website push.

**Headless proves none of the things that matter most.** It grants user
activation cold, has no speaker, and cannot tell you whether the recognition
beat lands. The real gate is Will opening the URL on his own handset.

---

## 11. Accessibility

- `prefers-reduced-motion: reduce` → **door starts open**, no swing, no light
  sweep, options immediately listed. There is established precedent — 24 files
  in `src/` already honour it, including WhaleMoment and BreakGlass.
- Options are real links in the DOM from first paint (§9), so keyboard and
  screen-reader users never depend on the animation completing.
- The door is decorative: `aria-hidden="true"` on the whole 3D stage, with the
  option list exposed normally.
- Contrast: interior text is birch on grass-900 — comfortably AA. Copper must be
  `--copper-on-dark`, never `--fields-copper`, on any dark surface.
- Nothing flashes. Nothing in this sequence approaches a seizure threshold, but
  the lamp "breathe" should stay under ±3% and slower than 0.2 Hz.

---

## 12. Analytics

Fire through the existing wrapper, `phCapture()` in `src/utils/posthog.ts:33` —
it null-guards `window.posthog`, which is loaded by script tag rather than npm
because of SSR.

**Adopt the Discovery deck's *pattern*, but not its event names.** The deck
(`DiscoveryDeck.tsx:319-343`) builds a `base = { slug, suburb, arm }`, calls
`phRegister({ offmarket_arm })` on mount and `phUnregister` on cleanup, spreads
`base` into every event, and sends its terminal event with
`{ transport: "sendBeacon" }` so it survives the tab closing. Copy all of that.

Do **not** reuse `offmarket_report_view` / `card_viewed` / `deck_exit`. Those
names are deliberately shared between the two off-market arms so the offline
journey builder and the RL reward ledger consume both alike — a third surface
firing them would silently corrupt the off-market funnel metrics. Same mistake
the QR concept flagged and avoided. Use a `fridge_*` namespace.

Two existing helpers are worth reusing verbatim: `phTrackScrollDepth(page, base)`
and `phTrackTimeOnPage(page, thresholds, base)` (`posthog.ts:244`, `:278`).

| Event | When | Why it matters |
|---|---|---|
| `fridge_land` | Page view with `utm_source=fridge_magnet` | The only observable proxy for a scan. **The denominator for everything.** |
| `fridge_open` | Door reaches rest | Split `{method: "pulled" \| "auto"}` — pulled is a real engagement signal, auto is not |
| `fridge_time_to_touch` | ms from paint to first touch | Tells you whether the recognition beat is landing or boring people |
| `fridge_option_click` | Option tapped | `{option, shelf_index}` — which of the four actually earns the tap |
| `fridge_idle` | Open, 15 s, no tap | The failure mode to design against |
| `fridge_exit` | `visibilitychange → hidden` + React cleanup, `sendBeacon` | Terminal event; carries whether the door ever opened |
| `fridge_recognised` | v1.5 only | `{confidence, source}` from the my-home resolver — is personalisation firing at all |

Register `fridge_arm` as a super property if variants are ever tested, and
**unregister on unmount** so it doesn't leak onto later pages in the session —
the existing helper's own docs call this out.

One honest caveat: `fridge_land` counts *arrivals*, not *scans*. Someone typing
the URL, or a second scan from the iOS preview, is indistinguishable. It is the
best signal available and it should be described as such wherever it's reported,
not quietly treated as a scan count.

---

## 13. Build sequence

| Step | What | Effort | Gate |
|---|---|---|---|
| 1 | **`fridge.css` + `fridge.js` + `index.html`** in this folder — door, swing, light, four static rows. No React, no build. | ~3 h | **Will opens it on his own phone.** Everything downstream is wasted if the motion doesn't land. |
| 2 | Iterate the swing curve and the gasket break against his feedback | ~2 h | The break beat reads as a fridge, not a cupboard |
| 3 | Copy pass on the four options | ~1 h | §6 editorial rules |
| 4 | Move the *same files* to `public/fridge/`, add a thin SSR route module, repoint `/fridge` preserving UTMs | ~2 h | 301 keeps the query string; options in SSR HTML |
| 5 | Analytics, reduced-motion, safe areas, dedicated check script (§10a) | ~3 h | Events visible in PostHog; check script red when broken |
| 6 | v1.5 personalisation via `/api/v1/my-home` | ~3 h | Only after v1 shows real scan volume |
| 7 | Audio | ~4 h, **risky** | Only after an isolated tone test passes on Will's Android |

Steps 1–3 are the whole concept. Steps 4–5 are the ship. 6 and 7 are earned, not
assumed.

Step 4 is short precisely because of the BreakGlass layout (§5) — the files
built in step 1 are the files that ship. The tempting alternative, prototyping in
HTML then rewriting as a React component, is how prototype and production drift,
and this codebase already chose against it twice.

**Step 1 is served with no build step** at
`https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/` —
drop an HTML file in this folder and it is live on next request
([[concept_previews_path]]). A markdown file is not a way to evaluate an
animation; Will needs a URL on a handset.

---

## 14. Open questions for Will

1. **Have the magnets actually been printed?** There's no record of an order. It
   changes nothing technically — `/fridge` is repointable either way — but it
   changes whether v2's per-magnet codes are a reprint or just a change to the
   next run.
2. **Where do these get distributed?** Letterbox-dropped cold, handed over at a
   door, or included with the posted appraisal? The third is by far the
   strongest case, because it arrives with a known address and unlocks the
   personalised fridge without any guessing.
3. **Four options, or fewer?** My view: four, and `/analyse-your-home` last. But
   the case for **two** — the market update and their own home — is real, and
   fewer choices usually convert better.
4. **Is the magnet-on-the-door beat worth 0.8 s?** It's the whole idea, but it
   is 0.8 s before anything useful appears, and it's the first thing to cut if
   the numbers say people are bouncing.
5. **Audio at all?** Given the unsolved Android problem, my recommendation is
   ship silent and revisit. A gasket thunk would be genuinely great; it is not
   worth a sixth round of the bug that is still open on the neon sign.
6. **Fix the `utm_medium=print` vs `qr` mismatch now or later?** (§1) It is a
   one-line change and it is the difference between magnet scans appearing in
   the physical-attribution data or not. Worth doing independently of whether
   this concept ever gets built.
7. **Should the drawing be in colour?** It currently is — and it is the only
   colour in the whole sequence, which is a far better place to spend a single
   accent than on a CTA. But it is arguably a departure from "black and white".
   Compare on your phone with `?art=mono`. My view: keep the colour. A
   monochrome child's drawing is a sad object, and the point of it is warmth.
8. **Is the close affordance discoverable enough?** The door's hit area once
   open is only ~25 px, so closing is done by tapping the room or the prompt.
   It works, but nobody is *told*. The alternative — letting a tap anywhere
   inside the fridge close it — risks shutting the menu on someone reaching for
   an option.
9. **Whose drawing?** The one shipped is generated. Using a real child's drawing
   is warmer, but if it is a real client's child that is a permission question,
   and if it is Will's own it ties the brand to his family. Worth a decision
   before this goes near production.

---

## 15. What this document is and isn't

**Verified:** magnet artwork inventory read from disk; QR payload decoded out of
both 300 DPI print files with OpenCV and string-matched; `/fridge` 301 and its
exact destination fetched live; page weight measured by fetching all 25 assets
compressed; all four candidate destinations fetched (200); theme tokens and the
"no invented near-black" rule read from `theme.css`; `phCapture` signature read
from source; reduced-motion precedent counted (24 files); the concepts preview
path fetched (200). Route table, edge-function param handling, `minisite-visit`
QR classifier, the Discovery deck event schema, the BreakGlass `public/*.js`
layout, and the puppeteer/verification harness all read from source in a
separate pass.

**Built and verified in headless Chrome:** the prototype renders at five frozen
door angles and in a real 3-second live run at 390×844; all four option `<a>`
hrefs present; no horizontal overflow; no console errors; the reduced-motion
path renders the door already open. Three bugs were caught by looking rather
than reading, and each is worth carrying into the port:

1. **The palette was unmistakably green** at the theme ramp's own 24%
   saturation. Held at ~7% it reads as black and white. Nobody would have
   predicted the first number was wrong.
2. **At 78° the door still covered 21% of the opening** and cut every option
   label in half — projected width is `W·cos θ`, so it has to swing *past*
   perpendicular (100°) to clear. Separately, the cavity sat exactly coplanar
   with the door's inner panel and the two z-fought, rendering the door
   translucent mid-swing. Both invisible at the endpoints.
3. **The shelves never appeared in the real run.** `--open` was animated on
   `.door`, but the shelves live in `.cavity` — a *sibling* — so they inherited
   nothing. The frozen screenshots hid this precisely because posing a frame
   means setting `--open` on the parent. The same mistake had also silently
   killed the prompt's fade-out (`.is-open .prompt` can't match a sibling).
   **Frozen frames verify geometry; only a live run verifies the sequence.**
4. **Every option link was untappable.** `.fridge` is a full-bleed box at Z=0
   and `.cavity` sits at Z−8 behind it, so in a `preserve-3d` context the
   *parent* won hit-testing and swallowed every pointer event. The render was
   pixel-perfect throughout. Only `document.elementFromPoint()` over the open
   fridge exposed it — a menu you cannot tap, one push from shipping.

**Not verified, and load-bearing:** no claim here about how the animation
*feels* is tested. **No handset has been touched** — headless Chrome has no
speaker, grants user activation cold, and cannot tell you whether the
recognition beat lands. The 4G timing in §9 is extrapolated from a measured byte
count, not measured on a phone. Whether phase 0 is worth its 0.8 s — the premise
the whole concept rests on — is exactly what showing it to Will is for, and it
is entirely possible the answer is no.

---

## Files

| File | What |
|---|---|
| `index.html` | The page. The four options are real `<a>`s in the markup, occluded by the door — that is the §9 contract, not a detail. |
| `fridge.css` | The entire fridge. One animated custom property (`--open`) drives door angle, face luminance, light, shadow and option opacity. |
| `fridge.js` | Decides *when* the door opens. Nothing else — delete it and the sequence still runs. |
| `assets/magnet.webp` | 8.5 KB. Downscale of `Fields_BusinessCard_90x55_QR_GREEN_300dpi.png`. |
| `assets/grain.png` | 12 KB, 128×128 tileable luminance noise. Anti-banding. |
| `verify/shots.mjs` | Renders five frozen door angles. Geometry checks. |
| `fridgeAudio.js` | Loads, schedules and ducks the three recordings. |
| `assets/build_audio.sh` | Raw recordings → trimmed, normalised, seamlessly-looped web audio. |
| `assets/source/*.m4a` | **Will's original recordings.** Never served; the only copies besides GitHub. |
| `assets/fridge-{open,close,hum}.m4a` | What ships. 66 KB total. |
| `assets/build_artwork.py` | Generates the drawing. Re-run it for a different one (change the seed). |
| `assets/artwork.svg` | The drawing. Replaceable with a real photo. |
| `verify/live.mjs` | Real 3-second run + reduced-motion emulation. **This is the one that catches sequence bugs.** |
| `verify/toggle.mjs` | Open → close → reopen, plus the "a tap inside must not close it" rule. |
| `verify/audio.mjs` | Files fetch, decode, hum arms on gesture, ducks with the door, mutes. |
| `verify/*.png` | Output, regenerated — not source. |
| `README.md` | This document |

Related: [[concept_previews_path]] for how to make step 1
viewable, [[illuminus_neon_cta]] for the realism-vs-affordance trap,
[[two_glass_shatter_engines]] for the CSS-rotation precedent,
[[web_audio_user_activation_touch]] before any audio,
[[home_recognition_personalization]] for the v1.5 resolver.
