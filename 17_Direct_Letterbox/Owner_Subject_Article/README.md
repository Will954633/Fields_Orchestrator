# Owner-Subject Article — direct-mail asset

**Status:** working generator, production-quality output. **Nothing has been posted.**
**Owner:** Will Simpson · **Established:** 2026-08-05 · **Productionised:** 2026-08-07/08

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

**Files:** `build_owner_article.py` (orchestration, data, copy) · `charts.py` (the two
visuals) · `factbook.py` (numeric gate) · `guardrails.py` (editorial gate) ·
`macro_context.json` (**human-maintained** macro block).

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

## 6. The two data visuals

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

Eight articles in `output/`, generated 2026-08-08, all passing every gate:

| Address | Comps | Radius |
|---|---|---|
| 20 Heidelberg Circuit, Robina | 6 | 2.5 km (widened) |
| 16 Cheltenham Drive, Robina | 8 | 2.0 km |
| 3 Springvale Street, Robina | 8 | 2.0 km |
| 13 Chantilly Place, Robina | 7 | 2.0 km |
| 14 Ranier Crescent, Varsity Lakes | 7 | 2.0 km |
| 11 Placid Court, Varsity Lakes | 8 | 2.0 km |
| 37 Manakin Avenue, Burleigh Waters | 6 | 2.0 km |
| 8 Whitehead Drive, Burleigh Waters | 7 | 2.5 km (widened) |

Chosen for spread: all three suburbs, adjusted midpoints $1.15M–$1.98M, comp counts 6–8,
two needing a widened radius.

---

## 10. Open

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
