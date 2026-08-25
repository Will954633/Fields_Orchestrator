# Owner-Subject Article — direct-mail asset

**Status:** working generator, production-quality output. **Nothing has been posted.**
**Owner:** Will Simpson · **Established:** 2026-08-05 · **Doc current as of:** 2026-08-25
(question-led structure, six figures + references, per-suburb comparison — see §6, §12, §13)

Preview: `https://vm.fieldsestate.com.au/concepts/owner-article/<slug>.html`

---

## 1. What this asset is

A short printed piece about **one specific off-market home**, addressed and posted to
that home. It sets the most recent nearby sales — each one adjusted to the recipient's
own property — against the national headlines, and stops there.

The reader **owns the home and did not ask us to write this.** Everything below follows
from that single fact.

**Its job in the programme:** this is **piece 1 of a multi-piece mail campaign**. The
intended trigger is an engagement threshold on a `/off-market/:slug` page — a person
googles their own address, lands on our page for it, engages past some depth, and is
classified as a lead. The campaign then runs weekly or fortnightly for some months
(Will, 2026-08-07).

⚠ **It is deliberately SEPARATE from the `11_House_Mini_Site/Version_Two` 7-session
booklet system**, which describes a similar-looking fortnightly posted sequence. Will,
2026-08-07: *"ignore those session pieces, keep this article process separate."* The two
share a worked example (20 Heidelberg Circuit) and will look related. Do not merge them.

**What does NOT exist yet** — the campaign layer. There is no sequence state machine, no
mail history, no suppression list, no scheduler, no per-address asset code. This asset
generates one piece for one address on demand. See `../00_SCOPING.md`.

---

## 2. Running it

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator/17_Direct_Letterbox/Owner_Subject_Article

python3 build_owner_article.py --address "20 Heidelberg Circuit, Robina"
python3 build_owner_article.py --list-candidates --suburb robina --limit 20
```

| Flag | Effect |
|---|---|
| `--address` | the subject property (required unless listing candidates) |
| `--suburb` | `robina` / `varsity_lakes` / `burleigh_waters`; skips the search if known |
| `--out-dir` | defaults to `./output`, which is symlinked to the preview URL above |
| `--no-hero` / `--no-html` | skip the aerial / skip HTML |
| `--skip-market-check` | **dev only.** Skips the live PropRadar mailability guard. Never for print. |
| `--list-candidates` | addresses that pass the structural gates |

Exit codes: `0` ok · `2` rejected by a guard · `3` failed fact-check, guardrails or
cross-surface consistency.

**Files:** `build_owner_article.py` (orchestration, data, copy) · `charts.py` (the six
figures) · `factbook.py` (numeric gate) · `guardrails.py` (editorial gate) ·
`subject_trajectory.py` (as-of valuation engine) · `refresh_article_data.py` (scheduled
data refresh) · `test_build_smoke.py` (pre-batch gate) · five context JSONs (§12).

---

## 3. The rules it enforces, and why each one exists

Every one of these is a scar. None is stylistic.

| Rule | Why |
|---|---|
| **Never a single valuation figure, anywhere, including the headline** | The RANGE of adjusted comparables *is* the valuation. A point estimate implies a precision the method does not have. |
| **No CTA, no invitation, no mention of selling or appraisals** | Unsolicited mail about someone's home that reads as solicitation has failed, whatever else it did. |
| **No confidence grade** | Measured across 512 sold homes the label is *non-discriminating*: `high` 56.0% range-hit vs `medium` 57.5%. Printing it would tell the reader something untrue about how much to trust the number. |
| **No advice, no prediction, no urgency** | CLAUDE.md Rule 5. A fitted trend line is a prediction with a haircut, so the charts have none. |
| **Every figure minted before it can be printed** | A draft once shipped *"four of the eight"* when it was six. In a format whose entire value is numerical honesty, proof-reading does not scale to hundreds of addresses. See §4. |
| **Never recompute a figure the website already publishes** | See §5. This one nearly shipped. |

---

## 4. Why the copy is Python, not an LLM

Composition is deterministic. That is what makes `factbook.verify()` meaningful: every
figure is *minted* (`fb.money`, `fb.pct`, `fb.word_count`, `fb.address`, `fb.date`)
before it can appear, and the finished text is then re-scanned for anything that looks
like a figure but has no mint record. A number typed by hand, copied from an older
draft, or surviving a template edit **fails the build**. It caught seven real leaks on
its first run.

It also makes a run reproducible and free, and it matches the standing editorial
LLM→Python migration direction.

This cannot catch a number minted from *wrong input* — that is the data layer's job. It
catches the entire class of "the prose and the data disagree", which is the one that
actually bit us.

---

## 5. ⚠ The single-source-of-truth rule

**The Market Intelligence pages are the source of truth. This article READS them and
never recomputes them.**

This is not theoretical. The first build computed its own suburb median and published
**"Robina median moved +6.8%, from 268 recorded sales"** while `precomputed_indexed_prices`
— the union series the website serves — said **+5.8% from 265**. Two Fields surfaces,
two numbers, and an owner potentially holding both with no way to tell which is stale.

So:

- Suburb median → `Gold_Coast.precomputed_indexed_prices` (Domain ∪ onthehouse union),
  **provenance-gated**: if `median_source` is not the union, the passage is omitted
  entirely rather than falling back to something weaker.
- Days on market → `Gold_Coast.precomputed_market_charts`, the same collection the
  Market Intelligence page renders.
- `check_surface_consistency()` asserts the article's DOM equals
  `system_monitor.market_pulse.data_snapshot.dom_median`, and **fails the build** on
  disagreement. Verified 2026-08-08: **34 / 26 / 29** for Robina / Varsity Lakes /
  Burleigh Waters — exact match.

### Why days-on-market is publishable and sales VOLUME is not

Our own PropRadar cross-check (memory `data_source_undercapture_reset`) found DOM and
price growth matched closely — Varsity 23–26 vs 23, Burleigh 33 vs 33 — while scraped
sold **volume under-counts by ~2×**. A median survives a partial sample; a count is
precisely what sampling destroys. So `transaction_count` appears only as the sample size
beneath each chart point, **never as a market figure in its own right**.

### ⚠ The median series is SPARSE

Robina is missing Q3 2024 *inside* the recent window. Plotting entries by list index
would space non-consecutive quarters evenly and **invent continuity**. Points are placed
by true quarter ordinal, and the chart draws only the most recent *unbroken* run.

---

## 6. The data visuals (Figures One–Six)

The article is now **question-led** (Barbara Minto S-C-Q): a national-picture opener →
the complication (the Gold Coast has so far bucked it) → the Key Question (will this home
fall too?) → four sections answering it from the home outward. Six figures, auto-numbered
in document order by `_fig()` ("Figure One … Six"):

1. **Subject price trajectory** — this home valued as-of 18/12/6/0 months (see §12).
2. **Suburb median house price** — rolling 12-month median with a bootstrap 90% CI ribbon.
3. **Days on market** — median DOM by quarter, sample size under each point.
4. **Unemployment rate by state** — QLD/NSW/VIC horizontal bars (`charts.state_bar_chart`).
5. **Wage growth (WPI), QLD** · 6. **Household spending, QLD** — the two live leading
   indicators, each a %-YoY line (`charts.indicator_chart`).

Empirical claims (e.g. liquidity leads price) carry **superscript citations** that
hyperlink to a **References** section — three source-verified papers (Genesove & Han
2012; Carrillo 2013; Khezr & Menezes 2015, Australian). Anchors use unicode superscripts
so `factbook.verify()` ignores them. The two core charts, in detail:

1. **How long homes are taking to sell** — median days on market by quarter, sample size
   under every point, quarters under 15 sales drawn hollow. Placed *before* the median
   section deliberately: the homeowner brief §8.3 says lead with time-on-market over
   medians, because it is more reliable in our data and cannot accidentally become advice.
2. **Suburb median house price** — rolling 12-month median with its **bootstrap 90%
   confidence interval** drawn as a ribbon. This is brief §8.2, *"publish the confidence,
   not just the number… Every competitor draws the line anyway. Refusing to is a
   credential"*, made literal — aimed at ranked fear #3, *"the number in my head might not
   be real."* The ribbon visibly narrows as the sample grows.

Inline SVG, greyscale- and print-safe, theme-aware. Chart figures are minted through the
factbook too, so a chart that contradicts the prose beside it fails the same gate a wrong
sentence does.

⚠ **Two intervals, only one of which is a lie.** The property's ±12% band is **not** a
statistical CI — it contains the actual sale price ~57% of the time, and `guardrails.py`
blocks calling it a confidence range. The *suburb median's* interval **is** a genuine
bootstrap 90% CI (`precompute_union_prices.bootstrap_ci(confidence=0.90)`) and may be
disclosed. The exemption is scoped to that one rule, not to the label.

---

## 7. Guards — reasons an address is refused

Checked in order; any one rejects.

1. `listing_status` is `for_sale` or `under_contract` in our records.
2. **Live PropRadar mailability check** (`propradar.market_status`) — listed with another
   agent, or otherwise not ours to write about. A failure of the guard *itself* also
   rejects; it never fails open.
3. No `valuation_data`, or fewer than 4 adjusted comparables.
4. `directional_only`, or the adjusted-comparable midpoint outside the **$1,000,000–
   $2,000,000 design envelope** (memory `valuation_design_envelope`).
5. Fewer than 4 comparables within 3.0 km.

⚠ **Eligibility is not stable between runs.** 28 Wedgebill Parade passed on 2026-08-07
and was rejected on 2026-08-08 — the nightly recompute moved its midpoint from
$1,976,692 to $2,263,910 and flagged it `directional_only`. Any mail list built ahead of
a print run must be re-validated at lodgement, not just at selection.

**Comparable radius:** hard **2.0 km** (comp-distance p90 is 2.04 km across 1,197 sampled
homes), widened in 0.5 km steps only if fewer than 4 remain — and the widening is
disclosed in the article. The engine itself has no radius filter; distance is only a
weight decaying to zero at 5 km, which is how a prototype claimed "near your street"
over comps reaching 2.57 km.

---

## 8. The hero image

A **satellite aerial with the true cadastral boundary drawn on it** — not a listing photo.
`domain_hero_image_url` is expired by Domain once a home comes off the market, and curl
cannot detect it (memory `image_url_verification_orb`: *curl is not a browser*). A broken
image on a piece of unsolicited mail is worse than no image. Rendered by
`scripts/render_property_aerial.py`; boundary geometry from the Queensland public cadastre,
so the outline follows real fence lines rather than a guessed rectangle. Gold (`sun`)
rather than copper, because copper disappears into the terracotta rooflines here.

---

## 9. Current batch

A five-address review set (all three suburbs) was built to `output_review/` and reviewed
by Will 2026-08-24/25 through the final copy/structure pass: 5 Chantilly Pl & 16
Cheltenham Dr (Robina), 11 Placid Ct & 14 Ranier Cr (Varsity Lakes), 3 Fimiston Pl
(Burleigh Waters). All pass every gate. **Run `test_build_smoke.py` before any real
batch** — it builds across all three suburbs and hard-fails on any unminted figure,
guardrail trip, or cross-surface disagreement (passing 9/9).

---

## 10. Copy variants (added 2026-08-08)

Six compositions of the same data, same gates. Compare them at
`/concepts/owner-article/index.html`. Build with `--variant <name>` or
`--all-variants`; `make_index.py` rebuilds the comparison board.

| Variant | The gap it opens |
|---|---|
| `report` | none — states the finding, then evidences it (the original) |
| `anomaly` | *two sales near you point to very different numbers for your home* — our strongest prediction error; adjustment is the resolution |
| `anchor` | *you already have a number for this address — where did it come from?* — ranked fear #3, a gap the reader already carries |
| `features` | *what are your land, condition and floor area actually worth?* — the most self-relevant |
| `timing` | *half sold within N days; which half would yours be?* — leads with time-on-market per brief §8.3 |
| `contradiction` | *the national numbers and your street disagree* — brief §8.1, name the ambiguity before resolving it |

**The theory.** Loewenstein: awareness of a gap between what you know and what you want
to know creates tension that motivates closing it. A gap is *strong* rather than
irritating only when it is (1) self-relevant, (2) unresolvable alone, and (3) **credibly
closeable by us** — which is why the named, dated sales appear *before* the biggest
question in every variant. A gap opened before credibility is established reads as a tease.

⚠ **The line between this and manipulation.** Every gap opened must be **closed in the
same piece, with real evidence.** We are not withholding to drive an action — the piece
has no CTA. In particular we never defer a gap to a later mailing: holding back
information about someone's own home to make them wait is leverage over something that
matters to them, and this reader has been burned by confident people twice in eighteen
months. `guardrails.py` gained a **TEASE** rule class enforcing this ("read on", "find
out", "in our next letter", "you may be surprised").

Mostly these do not *manufacture* gaps — they make an existing one felt. The reader
already carries "the number in my head might not be real"; `anchor` just names it.

**Two things caught while writing them, worth keeping in mind:**
- The `anomaly` variant compares the cheapest and dearest raw sales, which is the pair
  where adjustment does the most visible work. Left alone that overstates the method
  (standing rule: never quote the best pair as typical — median narrowing is ~40%). The
  copy now states the whole-set figure in the same breath.
- A draft of `timing` asserted that how fast a home sells "is not mostly about the
  market". We have not measured that. Removed — an opinion in a fact's clothes is exactly
  what this format cannot afford.

## 11. Open

1. **Length.** ~1,100 words plus two charts and a table. Possibly long for a cold
   letterbox drop; awaiting Will's read.
2. **Visual treatment** is a first pass — hero, accent on the adjusted column, print
   stylesheet. Colours and layout await direction.
3. **Aerials are ~1.6 MB each.** Fine on screen; wants compression before any print run.
4. **Time adjustment is computed but not composed** with the feature adjustments —
   inherited from the valuation engine, unchanged here.
5. **No valuation history exists.** `precompute_valuations.py` writes a destructive
   `$set`, so we cannot say "your range moved from X to Y". Snapshotting forward is cheap
   (one small doc per property when the range moves) and would make the strongest visual
   in the piece — the reader's own home rather than their suburb. Not started.
6. **The campaign layer** — trigger threshold, sequence, suppression, scheduler. See
   `../00_SCOPING.md`.

Related memory: `two_article_workflows_public_and_posted`, `adjusted_comparables_evidence`,
`data_source_undercapture_reset`, `union_median_pipeline`, `valuation_design_envelope`,
`homeowner_mindset_brief`.

---

## 12. The data pipeline and how it is kept fresh (added 2026-08-24)

The article body is composed from five **context files**. Three refresh from live
sources; two are human-maintained. Every figure the reader sees is minted from one
of these, then verified by `factbook.verify()`.

| Context file | Feeds | Source / refresher | Freshness |
|---|---|---|---|
| `macro_context.json` | national picture, "why it turned", the headline | **human** Cotality `history` + `stats`; `update_macro_context.py` recomputes `derived` (falling-streak, Brisbane flip) — no external fetch | staleness-gated in `load_macro()` |
| `fundamentals_context.json` | Q3 migration/affordability, Q4 lead/lag figures | **human**, cited to `14_Articles/Market_Research` dossiers | staleness-gated in `load_fundamentals()` |
| `labour_context.json` | jobs (vacancies/capita, unemployment), the WPI + household-spending charts | `update_labour_context.py` → ABS Data API (Labour Force, Job Vacancies, WPI, Monthly Household Spending Indicator) | self-monitors (Rule 7) |
| `arbitrage_context.json` | "what the same money buys" anchor + Sydney price-match, **per suburb** | **human/curated**, `angle` per suburb (land vs lifestyle). Builder emits the old single-suburb shape and is SUPERSEDED | manual |
| `comparison_examples.json` | the two real-home cards, **per suburb** (GC full-res listing photo + Sydney Street View) | **human/curated** (see §13). Builder SUPERSEDED | manual |

Both `arbitrage_context.json` and `comparison_examples.json` are now **suburb-keyed**
(`robina` / `varsity_lakes` / `burleigh_waters`) and **hand-curated**, so they are
excluded from the auto-refresh — `build_arbitrage.py` / `build_comparison_examples.py`
still write the old single-suburb (Robina) shape and would clobber the curation. Treat
them like `fundamentals_context.json`: human-maintained.

**Keeping it fresh — `refresh_article_data.py` is the single scheduled entry point.**
It runs the **two live refreshers** (`update_macro_context.py` recompute + `update_labour_context.py`),
then **asserts each file is fresh**, and self-reports via `job_status` (job
`owner_article_data_refresh`). It **raises** (Rule 7b) if a required pull failed or a
required file is older than its bound — so a dead ABS pull shows up on the **Fields
Systems Health** sheet instead of quietly feeding the mail-out last month's numbers.

```bash
python3 refresh_article_data.py --no-heartbeat   # ad-hoc, validated end-to-end
# cron (install from the MAIN checkout after merge; VM is Australia/Brisbane):
# 0 6 * * 0 set -a && . ./.env && set +a && \
#   /home/fields/venv/bin/python 17_Direct_Letterbox/Owner_Subject_Article/refresh_article_data.py \
#   >> logs/owner_article_data_refresh.log 2>&1
```

### The price-trajectory system
`subject_trajectory.py` runs the real valuation engine as-of four dates (18/12/6/0
months) via a frozen clock + `<=T` comp pool — no engine edits, no lookahead. Backed
by `trajectory_backtest.py` (n=60): the 18-month **direction** tracks the suburb 98% of
the time; 6-month segments are noise. So the copy speaks only to the whole-window move.

### The research engine that feeds this
Migration, jobs, arbitrage, leading-indicator and "why the market turned" facts trace to
**`14_Articles/Market_Research/`** — the central research engine (dossiers + a fortnightly
`claude -p` cycle indexed into `system_monitor.market_research_briefs`). This article is
one consumer of it. (This folder is also reachable at
`14_Articles/Owner_Subject_Article` via symlink.)

### ⚠ Known gaps before a real mail-out
1. **Macro history has one confirmed month.** `macro_context.json` holds July 2026 only
   (`derived.uses_provisional: false`), reconciled to the primary Cotality release. The
   headline therefore renders the sourced-safe line ("The southern capitals are falling…");
   the punchier "falling for N months, Brisbane just turned" form lights up automatically
   once ≥2 southern-falling months + a Brisbane flip are entered. Provisional placeholders
   were removed 2026-08-24 (factual-accuracy rule) — never re-add unsourced figures.
2. **Photo imagery.** Sydney comparison cards use Street View (Google attribution). Gold
   Coast cards use **our full-res listing photos** (via the `bucket-api` rewrite, §13) —
   these are the agents'/photographers' **copyright**; their use on a mailed piece is
   Will's call (flagged 2026-08-25). The GC-glossy vs Sydney-Street-View look is a
   deliberate source mismatch Will approved.
3. **onthehouse is flaky.** The Sydney median/comp scan returned 2/20 suburbs on one run
   and prices vary run-to-run — which is why the Sydney foils are hand-curated, not scanned.

**Resolved this cycle (2026-08-24/25):** the "Our reading" and every directional/comparative
claim are now **sign-aware** (branch on the home/suburb/DOM actual direction), so nothing
inverts on an easing suburb; `check_dom_prose_consistency()` fails the build if a DOM trend
verb disagrees with the chart's year-ago delta; the market-intelligence link and the
subject-land figure are now per-article (was hardcoded Robina / 907 m²).

### Monitored jobs this asset registers
- `owner_article_data_refresh` (this orchestrator) · `owner_article_labour_context` ·
  `owner_article_macro_context`. All on the Process Registry / Systems Health sheet.

---

## 13. The per-suburb comparison ("what the same money buys") — added 2026-08-25

Each suburb's article shows **its own** Gold Coast home against a **price-matched Sydney**
home, not one Robina example everywhere. Data lives in `arbitrage_context.json` (anchor +
Sydney match + `angle`) and `comparison_examples.json` (the two card homes with embedded
photos), both suburb-keyed. `build()` selects the current suburb's slice.

**`angle` drives the framing, and it is honesty-gated:**
- `land` (Robina, Burleigh Waters) — blocks are bigger than outer Sydney's, so the copy
  leads on **more land + beach**.
- `lifestyle` (Varsity Lakes) — blocks are *smaller* (~400 m² vs Seven Hills' 556), so the
  copy does **not** claim more land; it leads on the lake/coast and lower entry price, and
  states the smaller block plainly.
- Wording is **price-aware**: "the same money / near the same price" only when the Sydney
  comp is within ~10%; otherwise "even $X — less than that — reaches only … m²".

**Curated homes (2026-08-25):** Robina 28 Olympus Dr ↔ The Ponds · Varsity 16 Dartmouth Ct
$1.30M/400m² ↔ Seven Hills $1.20M/556m²/27km · Burleigh 5 Coral Sea Ct $1.87M/776m² ↔ The
Ponds $1.53M/352m²/34km. Sydney foils hand-curated (onthehouse too flaky to scan).

### ⚠ Full-res photo retrieval (the working path)
Gold Coast card photos are our own listing photos at full resolution. **How to get them
(this is the only reliable path):**
- `domain_image_urls` / `domain_hero_image_url` render at **150×100** — HMAC-locked
  thumbnails, useless for a card.
- `property_images` point at the **decommissioned Azure host** (`…blob.core.windows.net`) —
  they 404.
- **Working:** take a `rimh2` thumbnail URL's **final path segment** (the Domain asset
  token) and fetch `https://bucket-api.domain.com.au/v1/bucket/image/<segment>` → the
  full-res original (1500–2000 px). This mirrors the website's `toFullResUrl()` (memory
  [[photo_full_res_serving]]). The facade is **not always image[0]** — eyeball a few and
  pick the exterior. Photos are embedded as resized (~680 px) data-URIs so the piece is
  self-contained.
- Sydney photos are heading-tuned Google Street View (compute camera→house bearing, else
  you get a streetscape of bins/cars).

To re-curate a pair: pick a sold home near the suburb median with a clean facade, resolve
its `land_size_sqm`, fetch the full-res facade (above), pick/frame the Sydney foil, and
hand-edit the two suburb-keyed JSONs. Do **not** run the SUPERSEDED builder scripts.

---

## 14. The printable mailer branch — `build_owner_mailer.py` (added 2026-08-26)

`build_owner_mailer.py` is a **thin branch** over `build_owner_article.build()` that emits
a **print-ready A4 PDF** carrying a **QR code to this home's `/off-market/<url_slug>`
page** — the asset we actually post to the homeowner. It re-implements none of the data,
copy, factbook or guardrail logic: it *calls* `build()`, so every gate in §3–§6 still runs
and still hard-fails. It adds only what a mailed sheet needs:

```bash
python3 build_owner_mailer.py --address "20 Heidelberg Circuit, Robina"
python3 build_owner_mailer.py --address "..." --variant anchor --out-dir ./mail_batch
```

Outputs to `./output_mail/` (override `--out-dir`): `<slug>.pdf` (the mail asset),
`<slug>.mailer.html` (the PDF's source, article HTML + QR panel), plus everything
`build()` already writes.

**The QR target** is `https://fieldsestate.com.au/off-market/<url_slug>`, where `url_slug`
is the **stored** field on the property doc (route `/off-market/:slug`, resolved by the
website loader). This is the campaign entry point in §1: the reader scans, lands on our
page for their own address, and engagement there is what classifies them as a lead.

**Two guards on top of `build()`'s** (both fail the build; §8 spirit — a broken asset on
unsolicited mail is worse than none):
1. **No `url_slug` → no mail.** We refuse to print a QR to a page that cannot exist.
2. **Live resolve check.** By default the off-market URL is fetched and must return 200 as
   a genuine off-market report before the QR is printed. `--skip-url-check` = dev only.

**Why the QR does not break the no-CTA rule (§3):** it points at the reader's **own data**,
not an offer. The panel copy stays data-framed — kicker *"The full data set for this
address"*, one neutral line, and the printed URL as a fallback. No "sell", "appraisal",
"contact", no urgency. ⚠ It is nonetheless the **one outward-pointing element** on an
otherwise CTA-free piece — flagged for Will 2026-08-26.

**Rendering & QR technique (scars):**
- PDF is rendered by **headless Chrome** (Playwright → `google-chrome`), forced to the
  `print` + `light` media, so the article's own `@media print` stylesheet, inline-SVG
  charts and data-URI photos come out exactly as designed. weasyprint mangles
  `aspect-ratio` / CSS-vars / our SVG here — do not swap it in.
- QR is a **PNG data-URI**, *not* inline SVG: the SVG's intrinsic `width/height` fought the
  flex box and the code rendered **clipped**. `error='q'` (25% recovery, survives a fold),
  `border=4` (the **mandatory 4-module quiet zone** — without it the code will not scan).
- **Verification that matters:** decode the QR back out of the *rendered PDF* (pyzbar), not
  just the source — proves it is physically scannable at print size. Confirmed for Robina
  and Burleigh Waters, each to its own correct per-address URL.

**Not done:** batch mode / smoke gate for the mailer (use the batch pattern in §9 around
it), and aerial compression (§11.3) — the PDF inherits the ~1.6MB aerial (~1.2MB PDF).
