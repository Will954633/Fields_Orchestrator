# 10 — The market-timing paragraph (and the shared workflow it should become)

**Built 2026-08-07** as `timing_answer()` in `Prototypes/render_prototype_a.py`, answering the
second of the three questions posed at the top of the page, under that exact headline:
**"Is now the right time to be selling, or should I wait?"**

Source research: `15_Off-Market/Home_Owner_Perspective/Gold-Coast-Homeowner-Selling-Mindset-2026-08-02.md`
(to be re-run on a cadence still to be decided).

---

## What it is

Four paragraphs plus the seasonality chart:

1. **Macro, reported and attributed, never adopted.** The forecaster reversal (Westpac tipping two
   more rises in early July, withdrawing it by month-end; all four majors now expecting a hold),
   and national values falling three months running *with the correction attached* — Brisbane is
   close to flat, and the Gold Coast is a different market again.
2. **Local, COMPUTED per suburb** from `market_pulse.data_snapshot` — days on market against a year
   earlier, active listings against a month earlier, and whether those two readings agree.
3. **Seasonality**, from the canonical dataset, labelled as catchment-wide.
4. **The refusal.** *"None of that tells you what to do, and we are not going to."*

## ⚠ Why it is computed and not written once

The obvious narrative — *"listings rising while prices hold firm"* — is true in Varsity Lakes
(+43.8%) and Robina (+5.5%) and **false in Burleigh Waters, where listings are DOWN 27.3%.** Days on
market moves in different directions too: **faster** in Burleigh Waters (29 against 37), **slower**
in Robina (34 against 24) and Varsity Lakes (26 against 21).

A single hand-written paragraph asserting one trend would have been contradicted by our own data on
one suburb in three. The first version of the logic made exactly this mistake — it said *"those two
readings do not point the same way"* in every case except faster-and-fewer, which was wrong for two
of the three. All four direction combinations are now handled explicitly.

## Editorial constraints it has to survive

From the mindset brief §8 and CLAUDE.md Rule 5:

- no advice, no prediction, no urgency, **no framing of timing** ("while conditions last", "before
  rates move") — the fastest way to lose a reader who has just watched forecasters reverse
- report the numbers; **the reader draws the inference**
- **"the market is strong / holding up / resilient" is banned** — a prediction in disguise, and
  adjacent to the prohibited "robust market"
- no quarter-on-quarter claims for Robina or Burleigh Waters; our quarterly figures move around
  more than the underlying market does
- reassurance as a posture is detectable and signals that we want something
- never characterise the direction as good or bad — state which way each reading moved and whether
  they agree

Verified clean against the full banned-phrase list on all five pages.

## Seasonality — use these figures, do not re-derive

`scripts/seasonality_analysis.py`, 2010–2025 **excluding 2019–2020**, **18,978 sales**, 375 strata.
H1 −0.18%, H2 +2.25%, November strongest (+3.29). **Catchment level** — per-suburb months are too
thin and must never be presented as suburb-specific.

⚠ The `december-listing-paradox` article shipped overstated once (Dec +6.05% against the real
+2.81%; a Jan −3.83% that was a COVID artefact) and had to be corrected and republished. Re-run the
script rather than copying figures from another file.

---

## The workflow this should become (Will, 2026-08-07 — NOT built)

One paragraph, generated centrally, slotting into **four** assets:

1. Market Intelligence "Should You Sell Now or Wait" pages
2. The subject-property article
3. The ops article generator that publishes to the website
4. The market update report (`10_Market_Report`)

Plus the associated data visuals. Reference for the commentary standard Will wants:
`https://vm.fieldsestate.com.au/concepts/off-market/Article_Prototypes/article_representative.html`
(that flow is itself in development) — better coverage of policy changes (negative gearing / CGT,
effective 1 July 2027, **main residence exemption unchanged**), interest rates, local median
movement against national, and the listings-versus-price divergence.

**Design note for whoever builds it:** the generator must take the suburb as an input and compose
from live figures, exactly as `timing_answer()` does. A single stored paragraph reused across four
assets would reintroduce the Burleigh Waters contradiction at four times the blast radius.

See [[homeowner_mindset_brief]], [[minisity_seasonality_strip]], [[feedback_no_advice_data_only]].
