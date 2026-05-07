# Market Report Research Log

**Project:** 10x Property Market Update Report — Fields Real Estate
**Owner:** Will Simpson
**Started:** 2026-05-06
**Goal:** Set a new global standard for property market reporting. Drive seller and buyer engagement. Position Fields as the definitive data authority on the Gold Coast.

---

## Constraint stack (must obey throughout)

1. **No advice.** Data only. Never tell readers what to do. Liability risk.
2. **No predictions.** Indicators and conditional language only.
3. **No single valuation in headlines.** Comparable ranges in any public-facing context.
4. **Trade-offs are value, never flaws.** Frame as Will would for an honest seller.
5. **Factual accuracy.** Cite source + limitations. Exact prices, never rounded. Verify "all/none/every".
6. **Forbidden words:** stunning, nestled, boasting, rare opportunity, robust market.
7. **Number format:** $1,250,000 (never $1.25m). Suburbs always capitalised.
8. **Source of truth for stats:** market-metrics pages / `precomputed_market_charts` / `precomputed_indexed_prices`. Never raw DB queries on listings.

## Context (from memory)

- Pre-revenue, sole operator (Will). Stage = trust-building.
- Q3 2026 = must have market interest / listings. **The report has to convert.**
- Buyer-first, seller-funded model. Report must serve buyers truthfully *and* attract sellers.
- Three target suburbs: **Robina (4226), Burleigh Waters (4220), Varsity Lakes (4227)**.
- Tagline: "Smarter with data".
- Daniel feedback: site is confusing — splitting into Buyer Assist + Seller Assist. Report must not amplify this confusion; it must clarify.
- Editorial voice: data-led, no hype, conditional, contrarian where evidenced.

---

## Workflow log

(Populated as I go. Use this as a scratchpad — the polished outputs go in /strategy and /draft.)

---

## Foundation findings (2026-05-06, before web research returns)

### Editorial constraints (HARD)
- **No advice.** Liability risk. "Data only — reader draws conclusions."
- **No predictions.** Conditional language — "if X has historically preceded Y…" never "X will…"
- **No single valuation in headlines.** Comparable ranges. Single figures only inside Valuation Guide tab.
- **Trade-offs are value, not flaws.** A flood overlay is *why you can buy a pool home for $2.2M instead of $3.5M*, not a defect.
- **Factual accuracy.** Cite source + limitations. Exact prices ($1,930,000 not $1.93m). Verify "all/none/every" claims.
- **Forbidden words:** stunning, nestled, boasting, rare opportunity, robust market.
- **Source of truth for stats:** `precomputed_market_charts` and `precomputed_indexed_prices`. Never raw DB.
- **Tagline:** "Smarter with data".

### Proprietary research stack we own (and competitors don't)
- **Wages lead prices by 3-4 months** (r = 0.940). Best forward indicator.
- **Household spending** (r = 0.914). Best real-time indicator.
- **Income elasticity 1.71x** (Abelson et al. 2005). 1% income rise → 1.71% price rise.
- **Asymmetric adjustment** (Abelson). Prices take 6 quarters to fall vs 4 to rise → sharp crashes are structurally rare.
- **Housing supply elasticity −3.6** — rising completions are the largest structural risk.
- **ASX substitution effect** — equity weakness drives capital into property.
- **Interest rates lag by 12 months** — RBA is reactive, not predictive.
- **Credit/lending lags 3.5 months** — confirms what already happened.
- **2,153 sold properties** analysed across Robina/BW/VL.
- **1,683 properties benchmarked** vs Domain valuations.

### Engagement principles (battle-tested in video / FB / V3 feed)
- **Story = tension between two data points.** Price-volume divergence, speed paradox, milestone, suburb divergence.
- **Information gap (Loewenstein 1994).** Hint, don't reveal.
- **Withhold the payoff.** But never withhold in reels — different format.
- **The WHY beats the WHAT.** Anyone can read out numbers; the structural reason is the moat.
- **BBQ test.** Can you summarise in one sentence?
- **Share test.** Would a homeowner send this to their partner?
- **Specificity beats generality.** "84% sold under 30 days" beats "selling fast."
- **One insight per piece, not five facts.**
- **Vulnerability builds trust.** Always include one number that complicates the narrative.
- **Confrontational hooks** (FB test): "Robina just got beaten" beats "VL outperformed Robina."
- **V3 narrative test:** narrative sequencing → +24% time on page, +37% 2min+ retention. Narrative WORKS.

### Strategic context
- **Q3 2026 = critical** (must have market interest / listings). **Q4 = real trouble** if no traction.
- **Buyer-first, seller-funded.** "Helping you find your right home is how we find the right buyer for our listings."
- **Daniel feedback (April):** site is confusing — split into Buyer Assist + Seller Assist. Report must clarify, not amplify confusion.
- **Pre-revenue, sole operator.** No team to dilute voice.
- **Daniel's verdict:** unclear who, why, how. The report has to make audience and value obvious.

### Data assets
- 6 databases, 390+ collections, 90+ suburbs.
- Source-of-truth pipelines: `precomputed_indexed_prices`, `precomputed_market_charts`, `precomputed_macro_indicators`.
- Editorial pipeline: `market_pulse` (21 docs, 7 categories × 3 suburbs), with verdict ladders.
- Photo analysis: `photo_inventory` (Ollama ML, 175 docs).
- Valuation: comparable-sales engine (the public-facing one) + CatBoost (internal ML benchmark).
- Local photography: Will954633/fields-local-photography (Robina/BW/VL).
- HTML→PDF pipeline already exists for per-property reports. Reuse for market report.

### Tech delivery pattern
- HTML + CSS template → Jinja2 variables → headless Chrome → PDF.
- Existing per-property pipeline = `scripts/generate_appraisal_report.py`.
- For market report: parallel `scripts/generate_market_report.py` consuming the same precomputed data.

### Existing draft / template (KB)
- `Copy of Market Update Report_Runaway Bay.docx` exists in KB — old structure to learn from / improve on.
- Per-property designer brief at Drive `1W6dmy5kT4vK-V3JXeO8VaaJdsUBtPc3p` — different deliverable but the print conventions transfer.

### Conversion test learnings (FB V3, April)
- Article-led entry beats listings-led entry for engagement (Test 4 hypothesis).
- Time on page +24% from narrative sequencing.
- Conversion content sits where most readers don't reach — must compress / front-load.
- Cards/visitor down but CTR up = deeper engagement.
- 50%-scroll-depth ceiling on FB cold traffic. Search-intent traffic predicted to scroll deeper.

### Implications for the report
1. The report is the **most valuable thing** Fields can put in front of a buyer or seller right now — single longest, most attention-rich piece of content. Q3 lead-gen depends on it.
2. It must look and read like a **piece of journalism / research**, not real-estate marketing. Daniel's feedback proves the existing site is too vendor-shaped.
3. It has to **land both audiences honestly** — a buyer reads and feels equipped; a seller reads and feels Fields would represent them honestly.
4. It needs **one true WOW moment** in the first 60 seconds — single chart, single sentence, single number — that makes the reader screenshot or share.
5. It needs **a narrative spine, not a stat dump.** Pick one tension per quarter (e.g. "the standoff", "the resilient one") and let the data prove it.
6. It needs **transparent methodology** — to build trust and to differentiate from Domain/CoreLogic which gloss methodology.
7. It needs **a calibrated information gap** — the headline tease creates a question, the body answers it, the digital layer extends it.
8. It needs to **cite vulnerabilities** — what we don't know — to earn credibility against incumbents.
9. It needs **a soft CTA stack** — not "call me", but "Live Burleigh dashboard", "Get next quarter's report", "Try our valuation engine on your address."
10. It needs to **trigger continued engagement** — not be a dead-end PDF.
