# Twilight Photo Enhancement — repeatable process

Turn a home's harsh-daylight listing photos into a cohesive **twilight** set — dusk skies,
warm window glow, lamps switched on — using Google's Gemini 2.5 Flash Image model
(codename **"nano-banana"**), billed on our own `GOOGLE_GEMINI_API_KEY` (GCP `fields-estate`).
**No third-party editor, no reseller** — the "nano banana" websites are just wrappers around
this same model, which we call directly.

First run: **93 Burleigh Street, Burleigh Waters** (conjunction listing with Coomera Realty,
signed — Tyler Benson has authorised enhancement). 25 of 32 photos enhanced.

---

## TL;DR — do it for any home

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator/19_Agent_Offering/Buyer_Acquisition_Service/photos

# One command: pull photos, classify, enhance, annotate.
python3 enhance_property_photos.py --address "12 Example Street, Robina"

# Cheap dry-run first — just the annotation, no image generation:
python3 enhance_property_photos.py --address "12 Example Street, Robina" --classify-only
```

Output lands in `./<address-slug>/`:

| File | What |
|---|---|
| `original/NN.jpg` | full-res source photos, de-duplicated |
| `enhanced/NN__<category>.jpg` | twilight-enhanced versions (floor plans / diagrams skipped) |
| `manifest.json` | **per-photo annotation** — category, room, caption, style applied |
| `contact_sheet.jpg` | labelled before/after grid so you can see every shot at a glance |

---

## Why this works / key facts

- **The model is `gemini-2.5-flash-image` ("nano-banana").** It edits an input image from a
  text instruction and returns a new image. We already have `google-genai` (v2.19+) in the venv
  and a working `GOOGLE_GEMINI_API_KEY`.
- **Full-res photos come from OUR blob CDN, not Domain.** The Domain image URLs on the property
  doc (`domain_image_urls`) are signed Thumbor links that only render **147×110 thumbnails**, and
  the live Domain listing **403s** any scraper now. The pipeline already stored full-res copies in
  Azure blob — read them from `doc["image_history"][-1]["urls"]`
  (`https://blobs.fieldsestate.com.au/property-images/...`, ~2880 px).
- **The blob list mixes originals and size-derivatives** (e.g. 32 photos → 62 blob URLs). The
  script de-duplicates with an average-hash and keeps the highest-resolution copy of each.
- **Two Gemini models, two jobs:** `gemini-2.5-flash` (cheap, fast) classifies each photo;
  `gemini-2.5-flash-image` generates the enhanced one.

---

## The enhancement styles

Defined once in [`twilight_edit.py`](twilight_edit.py) (`STYLES` dict) and imported by the pipeline.

| Style | Use | What it does |
|---|---|---|
| `default` | exteriors, aerials, alfresco | deep-blue dusk sky, warm cloud, glowing windows, soft façade light |
| `subtle` | hero alt | restrained blue-hour, clean sky, gentle glow — least dramatic |
| `dramatic` | hero alt | rich sunset gradient, strong window glow, warm uplighting — most stylised |
| `interior_twilight` | **all rooms** | **switches interior lights ON (warm lamp/ceiling glow), dusk sky through the windows, warm evening mood** — the interior half of a twilight shoot |
| `interior` | (superseded) | neutral exposure/white-balance/window-pull only — **too subtle to read; don't use for twilight** |

**Style routing** is automatic, keyed off the photo's category (`CATEGORY_STYLE` in
`enhance_property_photos.py`):

```
exterior_* / aerial / alfresco_outdoor  → default
living / kitchen / dining / bedroom /
  bathroom / laundry / interior_other    → interior_twilight
floor_plan / boundary_diagram / other    → skipped (never enhanced)
```

Run a single style by hand on specific images with the lightweight tool:

```bash
python3 twilight_edit.py 03 04 31 --style default
python3 twilight_edit.py 09 12 15 --style interior_twilight
```

---

## The annotation (answering "what is each photo of?")

`gemini-2.5-flash` classifies every photo into:

- **`category`** — one of `exterior_front, exterior_rear, exterior_other, alfresco_outdoor,
  aerial, living, kitchen, dining, bedroom, bathroom, laundry, interior_other, floor_plan,
  boundary_diagram, other`
- **`room_or_subject`** — e.g. *"master bedroom"*, *"front façade from street"*
- **`caption`** — one short human line
- **`twilight_suitable`** — `false` for shots a dusk relight would look odd on (tightly cropped
  wet rooms, floor plans); those fall back to being kept as-is

This drives the routing, the file names (`NN__kitchen.jpg`), and the labelled contact sheet.
Enforced with a JSON response schema, so the output is always valid structured data — see
`_CLASSIFY_SCHEMA`.

---

## ⚠ The one rule that matters: enhance the light, never the house

This is a **lighting/sky edit, not a renovation.** The prompts explicitly forbid the model from
changing any benchtop, cabinet, tile, splashback, floor, appliance, fixture, wall, window frame
or furniture, and from adding/removing/tidying any object. This is **non-negotiable** here because
the 93 Burleigh campaign's whole thesis is honesty about original 1975 condition
("*you're choosing the finishes, not inheriting someone else's*") — a model that quietly swaps the
laminate benchtop for stone or retiles the bathroom destroys that.

**Always eyeball `contact_sheet.jpg` before using anything.** Validated on 93 Burleigh: the dated
kitchen tile border, mustard bathroom skirting, brick feature walls and the portable aircon unit
all survived. But verify every time — the model *can* drift.

### Known, accepted artefacts
- **Window-pull invents the outside view.** Where a window was blown pure white, the model
  synthesizes a dusk sky / greenery behind it. Standard "window masking", but the view is *not the
  real outlook* — never caption a room as showing "the actual view".
- **Grass/foliage can get subtly lusher** on exteriors. Watch it against the original, especially
  where the yard's condition is part of the honest story.
- **Wet rooms at dusk** read slightly oddly (a lit bathroom at night). `twilight_suitable=false`
  catches the worst; otherwise consider keeping bathrooms/laundry as clean daytime.

### Publishing
- Enhanced images should carry a **"digitally enhanced"** disclosure (standard REIQ practice).
- Keep the originals — never overwrite them.

---

## Files

| File | Role |
|---|---|
| [`enhance_property_photos.py`](enhance_property_photos.py) | **the repeatable pipeline** — pull, dedup, classify, route, enhance, annotate |
| [`twilight_edit.py`](twilight_edit.py) | lightweight per-image tool + the shared `STYLES` prompts |
| `README.md` | this file |
| `<address-slug>/` | per-property output (originals, enhanced, manifest, contact sheet) |

## Cost / performance
- ~1 cheap vision call + ~1 image-generation call per photo. A 32-photo home ≈ a few minutes.
- Transient `503 UNAVAILABLE` from the image model happens; both scripts retry (up to 4×).

## Requirements
- `GOOGLE_GEMINI_API_KEY` in `.env` (source it first).
- `pip install google-genai` (already in the venv). `Pillow` for image handling.
