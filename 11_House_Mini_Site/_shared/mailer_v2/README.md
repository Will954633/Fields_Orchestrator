# Homeowner Mailer V2 — sell the finding, not the analysis

A4 double-sided direct mail, one bespoke PDF per address, QR to that home's
`/your-home/<slug>`. **Completely separate from V1** — its own folder, template,
assets, output and code. Neither reads the other; `../mailer/` is untouched and
still runnable.

## The one-sentence difference

V1 sold the analysis. V2 sells the finding. The homeowner already knows their
house — what they cannot know is **where it sits**, so every statement here is
relative (against the competing set, the cohort, or the sales record) and the
page withholds the answers.

## What V2 changes, and why

| # | Change | Why |
|---|---|---|
| 1 | **Findings are selected, not fixed** (`hooks.py`) | V1 printed the same three stats on every mailer. Two were *inputs* (sales reviewed, distance to school) — they prove the machinery ran but ask no question. V2 builds every finding the report supports, scores it, and lets the best lead. |
| 2 | **Scores come from the data, not the finding type** | First cut hardcoded scores per type and every mailer led with `competition` — the fixed-hook problem, relocated. Now 1-of-220 outscores 13-of-226, and 5.7× land outscores 1.2×. |
| 3 | **Page 1 withholds** | Counts only — *how many* competitors / strengths / trade-offs, never which. V1 printed the buyer persona's description on page 2, closing the loop it had just opened. |
| 4 | **Asymmetric layout** | One dominant card + two supporting. Three equal cards told the reader all three findings mattered equally. They never do. |
| 5 | **Analytical volume demoted to a proof line** | "49 sales reviewed" is evidence the finding is trustworthy, not a finding. |
| 6 | **The three-business-day line is gone** | It turned "your analysis is ready" into "partly ready" at the moment of conversion. Removed by making it *untrue* rather than unsaid — the gate now requires a real valuation. |
| 7 | **QR deep-links to `#market`** | The promise is "see the homes buyers would compare with yours"; `/your-home/<slug>` opens on tab 01 (their own data) and the competitors sit in tab 02. |
| 8 | **"Private" dropped** | The URL is public if unlisted. An exclusivity claim we cannot defend is not worth the trust it costs. |
| 9 | **Question-led page 2, objection-killer trust boxes** | Headings moved to the owner's internal monologue; the four boxes now answer the four reasons this gets binned (generic? just an algorithm? stale? a sales funnel?). |
| 10 | **"No login. No details. No phone call." sits on the QR** | Friction removal is the single biggest reason a homeowner lets themselves look. It was a paragraph below the CTA. |

## ⚠ The correction that matters most: the competitor count was wrong

V1's headline — *"Only N of TOTAL homes reviewed genuinely compete with yours"* —
took N from `len(comparables.closest_active)`. **That array is a map plotting
cap, not a measurement.** It is `min(active_in_band, 6)`: `TARGET_MAX = 6` in
`scripts/property_reports/competitor_matcher.py`, applied a second time as a
literal `active[:6]` in `comparable_feed.py`. It came out as exactly 6 on 23 of
the 25 mailable addresses because it saturates.

The real measure is `slots.competitor_map.ranked_comparison.funnel.close_tier`
(`n_close`) — computed over the **full** candidate set, scored within
`CLOSE_MATCH_THRESHOLD` and passed through a ±50% price guard. It ranges 0–13
across the mailable pool.

V1's number was wrong in both directions:

| Address | V1 printed | Actually closely competes |
|---|---|---|
| 26 Ballyliffen Court | 5 | **7** |
| 22 Mapleton Circuit | (would print 6) | **0** |
| 3 Woodland Drive | (would print 6) | **0** |

Six of the 25 mailable addresses have **nothing** that closely competes — which
is a far stronger hook than a capped 6, and V1 could not express it at all.
`f_no_competition` now leads on those.

The price guard is only active once a valuation exists, which is a second reason
the stricter gate (below) is right.

## The contradiction guard

`competition` ("7 closely compete") and `scarcity` ("57 of 206 share your
feature combination") are both true and measure different things, but printed
together against near-identical denominators a five-second reader sees a
contradiction and trusts neither. This was a real defect in V1's output.

`CONFLICTS` in `hooks.py` makes it structurally impossible rather than relying
on whoever writes the copy next to remember. It is enforced in **two** places —
card selection *and* the closing "we also found…" paragraph, which leaked the
same contradiction through a second path until the artwork verifier caught it.

## Readiness gate (stricter than V1)

Mailable requires all of: `build_state=complete`; `scarcity` +
`competitor_matches` slots approved; **`comps` slot approved**; **`model_range.method`
not `thin`/absent**; `funnel.close_tier` present; at least one competing listing
to name; hero photo; aerial.

The two bolded conditions are what let us delete the three-business-day caveat.
Cost: **25 of 71** complete reports qualify, against 45 under V1's gate. That is
the honest trade — V1 mailed homes whose valuation was still pending and
admitted it on the page.

Run `--audit` to see the pool, what each address would lead with, and why the
rest are blocked.

## Artwork verification (mandatory, automatic)

`.page` is a fixed 210×297mm box with `overflow:hidden`, so copy that no longer
fits is **silently cropped** — the PDF still looks plausible. Every generated
PDF is therefore re-read with `pdftotext` and checked for:

- exactly 2 pages
- every load-bearing line actually present on the artwork
- page-1 flowing copy within its character budget (the CTA band is absolutely
  positioned and will render *on top of* an overlong paragraph — present in the
  PDF, invisible on paper, which text extraction alone cannot detect)

A failure renames the file to `<slug>.REJECTED.pdf` and raises. **Nothing
unverified reaches a print run.** Comparison is done with whitespace and case
stripped, because `text-transform:uppercase` and `letter-spacing` make
`pdftotext` emit `T E M P L AT E` for `TEMPLATE`.

**⚠ Text extraction proves copy EXISTS; it cannot prove copy is VISIBLE.**
Overlapping text is present in the PDF and extracts perfectly. That is why the
character budgets exist alongside the presence checks — they are the only guard
against a label wrapping onto an extra line and rendering on top of the line
below. Both classes of check are load-bearing; do not drop one for the other.

Defects this caught during the build, none of which threw an error anywhere:
the closing paragraph rendering under the CTA band; the scarcity contradiction
leaking into that paragraph; two over-long support labels clipping; sub-lines
overflowing every support card while their labels rendered fine; and — its own
bug — probes failing because `&rsquo;` prints as `’` (U+2019) while `strip()`
folded it to an ASCII `'`.

Current state: **25 of 25 mailable addresses generate and verify clean.**
Leads: 20 `competition`, 5 `no_competition`. Support cards:
21 `advantages_tradeoffs`, 17 `buyer`, 6 `land_rank`, 4 `recent_activity`,
1 `feature_rarity`.

## Files

- `hooks.py` — finding builders + scoring + conflict rules. **Start here.**
- `generate_mailers_v2.py` — data → copy → PDF → verification.
- `mailer_v2_template.html` — A4 duplex template.
- `assets/gen/<slug>/` — per-address hero.jpg, aerial.png, qr.png.
- `output/<slug>.pdf` · `output/all_mailers_v2.pdf` (combined print file).
- `output/<slug>.REJECTED.pdf` — failed verification; never post these.

## Usage

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator/11_House_Mini_Site/_shared/mailer_v2

python3 generate_mailers_v2.py --audit            # pool + what each would lead with
python3 generate_mailers_v2.py --slug <slug>      # one address
python3 generate_mailers_v2.py --all-ready --combine
python3 generate_mailers_v2.py --slug <s> --dry-run   # selected findings, no PDF
```

`--force` generates despite readiness failures. Proofing only — never post those.

## Editorial compliance (CLAUDE.md §5)

No single valuation figure in any headline (competition-led). No advice, no
predictions. Trade-offs framed as value, and *named as existing* rather than
hidden. Feature rarity is printed as **prevalence** (a plain frequency), never as
the stored `premium_pct` — that figure is a raw median gap between homes with and
without a feature, and the same record's `like_for_like_pct` is typically far
smaller (13.6% vs 3.8% on 6 Huntingdale) because most of the headline gap is the
company the feature keeps.

## Known limitations / not done

- **The landing page still does not fulfil the promise on first paint.** `#market`
  deep-links to the Competition tab, but `YourHomePage.tsx` seeds `useState("home")`
  to avoid a hydration mismatch and applies the hash in a `useEffect`, behind a
  client-fetch loading shell. A scan shows: "Loading your property report…" →
  home tab → Competition tab. Fixing that is a website change and needs Will.
- **No true percentiles.** `cohort_stats` carries a median and a sample size but
  no distribution, so "larger than 84% of its competitive set" would be
  fabricated precision. Land is stated against the median instead.
- **Hook variety is still competition-dominated** (20 of 25 lead with
  competition/no-competition). That is a fair reflection of which finding is
  genuinely strongest, but `land_rank` only reaches hero grade at ≥1.5× median
  and `scarcity` rarely wins. Worth revisiting once more reports carry trade-offs
  (only 48% do today).
