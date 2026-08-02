# Matrix Digital Rain — Fields concepts

Four standalone digital-rain animations, built 2 August 2026. Every file is
**self-contained**: one HTML file, no build step, no dependencies, no network
calls. Drop any of them anywhere and it runs.

---

## ⭐ Preferred version

**`code-sequence-local.html` — the Local Recognition Sequence.**

> https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/code-sequence-local.html

This is the one to use, demo, or build on. The other three are earlier steps
kept for reference — do not edit them expecting the good version to change.

What it does, end to end:

| t | Beat |
|---|---|
| 0s | A curtain of code drops from the top, every column at once, already carrying readable text |
| 0–11.2s | Recognition ramps: suburb → wider area → the actual street grid around the home → their own block and their own questions |
| throughout | Keywords about *this* owner light white, with a crest of light sweeping down them |
| 11.2–13.7s | The field switches off, right → left |
| 13.7s+ | Screen goes fully dark, then the message types **into the code grid**: `searching...` ×2 · `Found it` · the address · `There's a problem...` · `ERROR` ×3 · `ABORT` |

Controls: `R` replay · `L` toggle loop · `F` fullscreen.

---

## Where everything lives

| | |
|---|---|
| **Source of truth** | `/home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Matrix_Recreation/` |
| **Live URL** | `https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/` |
| **GitHub** | `Will954633/Fields_Orchestrator`, same path |
| **Build notes** | [ENGINEERING-NOTES.md](ENGINEERING-NOTES.md) — design reasoning, measured numbers, bugs found |
| **Fix history** | `logs/fix-history/2026-08-02.md`, entries beginning `[CONCEPT-MATRIX-…]` |

**How the live URL works.** nginx maps `location /concepts/` → alias
`/home/fields/concept-previews/`, which holds a symlink `off-market` →
`15_Off-Market/Concepts`. So **anything saved into this folder is live on the
next request** — there is no build and no deploy step. `autoindex` is on, so the
folder URL lists all four files. Served `no-store` and `noindex`.

### The files

| File | What it is |
|---|---|
| **`code-sequence-local.html`** | ⭐ **Preferred.** Local recognition + in-grid message |
| `code-sequence.html` | v3 — in-grid message, generic glyphs, no local words |
| `homeowner-sequence.html` | v2 — same message, but typed as an HTML overlay rather than in the code |
| `index.html` | v1 — faithful film recreation (mirrored katakana), no message. Live tuning panel on `C` |

There is **no shared library** — each file duplicates the rain engine. That is
deliberate for concept files that need to survive being copied around on their
own, but it means a fix in one does not propagate to the others. If these ever
become production components, that is the first thing to change.

---

## Where the content came from

The words in the rain are not invented:

- **Street names are real.** Queried from `Gold_Coast.burleigh_waters` — 7,065
  cadastral records, 6,885 geocoded, 193 distinct streets. Fields are uppercase:
  `LATITUDE`, `LONGITUDE`, `STREET_NAME`, `STREET_TYPE`, `LOT`, `PLAN`.
  The tier-3 list is the genuine nearest streets to the Avocet Avenue centroid
  by haversine distance: Jabiru 55m, Fantail 58m, Burleigh St 86m, Corella 147m,
  Bluejay 173m, Skua 238m, Bittern 243m, Dunlin 247m.
- **House numbers are invented.** Real streets, mock numbers — so no real
  neighbour's address ever appears beside a word like `WITHDRAWN`.
- **Owner-voice phrases** (`WHERE WOULD I GO`, `IS THE NUMBER REAL`) come from
  §3 and §5 of
  `15_Off-Market/Home_Owner_Perspective/Gold-Coast-Homeowner-Selling-Mindset-2026-08-02.md`.
- **POIs are from general knowledge, not the database** — Marymount,
  Caningeraba, Treetops Plaza, Stockland Burleigh, David Fleay. **Unverified.**

### Deliberately excluded

The mindset brief is marked INTERNAL and its own §9/§10 flag several figures as
not publishable. None appear in the animation, and they should not be added: the
Burleigh Waters median, the +6.9% year-on-year, and the 292→161 volume drop
(which needs a lag reconciliation first). `DOM 29` is included because the brief
identifies volume and days-on-market as the reliable layer.

---

## Changing it

**The address** — no code edit needed, it is a query parameter:

```
code-sequence-local.html?street=12%20Curlew%20Court&locality=Robina,%20QLD%204226
```

Defaults to 3 Avocet Avenue, Burleigh Waters. Input is control-character
stripped, length capped, and inserted via glyph lookup — never as HTML.

**Everything else** is a named constant at the top of the `<script>`:

| Constant | Controls |
|---|---|
| `T_OPEN` | How long the rain runs before collapsing (11.2s) |
| `OPENING` | `'top'` curtain, or `'sweep'` for the old left→right switch-on |
| `RAMP` | How much of the field carries real text over time (0.62 → 0.98) |
| `TOKEN_TIERS` | The words themselves, and when each tier unlocks |
| `HOT_RE` | Which phrases highlight regardless of tier |
| `SURVIVOR` | Columns still raining after the collapse (0 = fully dark) |
| `SCRIPT` | The typed message, its colours and pacing |

**Live tuning:** `window.__rainStats()` in the browser console reports text
density and highlight counts against target — use it rather than guessing when
the field looks too sparse, too dense, or too subtle.

---

## Open decisions before this goes public

1. **A real address under "There's a problem / ERROR / ABORT."** Fine as a
   concept, or on an owner's own page. As a broad ad against real addresses it
   asserts something negative about an identifiable home. Needs a deliberate
   call.
2. **The POI list is unverified** — worth a local sanity check, since a wrong
   landmark is exactly what this audience notices.
3. **Length.** ~14s before the message starts. Good for the slow-burn effect,
   long for paid social where the first 2–3 seconds decide everything. Scale
   `T_OPEN` and the four `TOKEN_TIERS.from` values by the same factor for a
   shorter cut.

---

## Performance

Bloom is blurred inside a 1/5-resolution canvas rather than via a full-screen
CSS filter — measured 8 fps → 32 fps at 1080p on this GPU-less VM. Scanlines use
plain alpha instead of `mix-blend-mode: multiply`. Glyphs are pre-rendered into
per-palette atlases at 24 brightness tiers, so the animation loop is pure
`drawImage`. Safari < 16.4 lacks canvas `filter` and falls back to the CSS path
automatically.
