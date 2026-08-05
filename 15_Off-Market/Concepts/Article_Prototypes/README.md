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

1. **Confidence label is not trustworthy.** Robina `high` 11.7% MAE vs `medium` 11.4%;
   Burleigh Waters `high` 16.4% vs `medium` 9.4% — inverted. The owner draft currently
   prints "confidence grade: high". Strip it or fix the label.
2. **No radius filter exists** — distance is only a weight (linear decay to 0 at 5 km).
   Comps reached 2.57 km while the copy said "near your street".
3. **Spread-narrowing varies wildly** — 55% on Moorabbin, **5%** on Heidelberg. The
   $610,000 → $274,000 example is an outlier. Measure the distribution across the 262
   eligible homes before it carries any marketing claim.
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
