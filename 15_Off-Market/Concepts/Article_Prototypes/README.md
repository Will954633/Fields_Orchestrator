# Article Prototypes — adjusted comparables

Prototypes only. Nothing here is published. Established 2026-08-05.

Preview: `https://vm.fieldsestate.com.au/concepts/off-market/Article_Prototypes/<file>.html`

**There are two distinct workflows here.** They share the adjusted-comparables engine
and the guardrail linter; almost everything else differs.

---

## 1. PUBLIC — sold-home article, website / general circulation

`article_v3_comparables.html` · `.md` — subject: 26 Moorabbin Place, Robina (sold
$1,620,000, 6 Jul 2026).

The local market claim is the thesis; the sale is the **evidence** backing it. Gives a
worried owner recognisable context — a home near theirs, and how it actually went.

Carries the delta: sold above 6 of 8 adjusted comps, +6.2% against their median, comps
averaging 7.6 months old, implying ~+10.1% annualised against a measured +5.8% rolling
median — and the honest limit that +6.2% sits inside our own ~11% error.

**⚠ Comp-set construction.** Must use `valuation_backtest.backtest_single_property()`.
`precompute_valuations.precompute_property_valuation()` **cannot value a sold home**: its
sold-comp filter tests only property type, price and a 12-month window, so the subject's
own transaction comes back as its own top-weighted comparable and the valuation simply
reproduces the sale price. The backtest path excludes the subject by `_id` and drops
every sale dated on or after it.

## 2. OWNER-SUBJECT — printed and POSTED to that address

`article_owner_subject.html` · `.md` — subject: 20 Heidelberg Circuit, Robina (off-market,
3 bed / 2 bath, 477 sqm, 8 comps at 0.19–2.57 km).

The reader **owns this home and did not ask for this**. Distribution is direct mail to
the address, not a web page — the address → post → inbound call channel.

**Never a single valuation figure, anywhere, including the headline.** The range of
adjusted comparables IS the valuation. No CTA, no invitation, no mention of selling or
appraisals — reading as solicitation is the failure mode for unsolicited mail about
someone's home.

The production engine is correct here: an unsold subject has no sale to leak. 2,884
Robina off-market houses carry the needed attributes; 36 already have `valuation_data`.

**The result that made it work:** the eight comps adjusted to this home, split by date,
moved **+5.8%** — matching the Robina rolling 12-month median computed independently from
265 sales. Local evidence reproducing the suburb trend is the point of the format. Report
the direction; the decimal-place match is luck on 4-a-side halves.

---

## Open issues — blocking either workflow

1. **Confidence label is not trustworthy — CONFIRMED AND WORSE, 2026-08-06.** Measured
   across 512 sold homes: `high` range-hit **56.0%** vs `medium` **57.5%**, median error
   10.1% vs 9.7%. The label is not merely inverted, it is **non-discriminating** — high
   and medium are the same number. Also: **our stated range contains the actual sale price
   only 56.8% of the time.** Strip the label. Do not print a confidence grade anywhere
   until it is recalibrated. (`Page_Redesign_V4/Prototypes/RESULT_dispersion_512.md` §4)
2. **No radius filter exists** — distance is only a weight (linear decay to 0 at 5 km).
   Comps reached 2.57 km while the copy said "near your street".
3. ~~**Spread-narrowing varies wildly**~~ — **CLOSED 2026-08-06.** Measured across 512
   eligible sold homes: **median narrowing 38.8%** (p25 23.8%, p75 56.2%); narrows at all
   in **91.0%** of cases, widens in 8.6%. Median raw spread **$351,000 → $204,805**.
   **The README had the outlier backwards** — Moorabbin's 55% is the **73rd** percentile
   (flattering, not exceptional); Heidelberg's 5% is the **11th**. Quotable claim is the
   median: *adjusting comparables narrows the range by about 40%, and narrows it at all
   nine times in ten.* Never quote $610,000 → $274,000 as typical.
   (`Page_Redesign_V4/Prototypes/RESULT_dispersion_512.md` §3b)
4. **No numeric fact-check pass.** A draft shipped "four of the eight" when it was six.
5. **Time adjustment is computed but not composed** with the feature adjustments.

## Files

| File | What |
|---|---|
| `article_v3_comparables.*` | Public sold-home article (current) |
| `article_v2_comparables.*` | Earlier public draft, before the delta sections |
| `article_owner_subject.*` | Owner-subject article, for posting |

Generators, prompts and the guardrail linter live in the session scratchpad and are not
yet productionised.

See memory: `two_article_workflows_public_and_posted`, `adjusted_comparables_evidence`.
