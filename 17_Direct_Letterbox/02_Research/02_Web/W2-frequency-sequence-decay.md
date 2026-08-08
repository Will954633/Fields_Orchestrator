# W2 — Frequency, Sequence Length and Decay in Direct Mail and Multi-Touch Marketing

**Research date:** 2026-08-08
**Question:** What is the evidence on frequency, sequence length and decay in addressed direct mail and multi-touch sequences?
**Method:** ~20 web searches, source-chasing to primary papers where they exist (two PDFs pulled and text-extracted in full: Gerber & Green's field-experiment handbook, FCA Occasional Paper 12, van Diepen et al. ERIM working paper).

**Labelling convention used throughout:**
- **[PRIMARY DATA]** — randomised experiment, large-N observational study with a control, or an industry measurement panel with published methodology.
- **[VENDOR CLAIM]** — a number published by a party selling the thing being measured; no control group, sample size, or method disclosed.
- **[UNSOURCED FOLKLORE]** — no traceable origin, or an origin that turns out to be someone's assertion rather than a measurement.

---

## 1. Summary table: frequency recommendations and what actually backs them

| Recommendation | Source / context | Grade | What the evidence actually is |
|---|---|---|---|
| **Diminishing returns set in after ~6 mailings to the same household** | Gerber & Green, New Haven 1999 mayoral election; up to 8 nonpartisan mailings, RCT ([Gerber & Green handbook, 2016](https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf)) | **[PRIMARY DATA]** | The only experiment found that deliberately extended a mail sequence to find its ceiling. Effect accumulates roughly linearly to ~6, then flattens. |
| **~+0.5pp effect per additional mailing, 1→3 pieces, no early saturation** | Gerber & Green, New Haven 1998, n=31,098 RCT (same source) | **[PRIMARY DATA]** | Turnout: control 42.2% → 1 mailer 42.6% → 2 mailers 43.3% → 3 mailers 44.6%. Narrowly significant. |
| **Repetition of *persuasion* content does not accumulate at all — 5, 9 and 12-piece sequences produced null or negative results** | Cardy 2005; Gerber, Green & Green 2003; Cubbison 2015 (same source) | **[PRIMARY DATA]** | Cardy's 5 glossy mailings: treatment turnout *below* control. Cubbison's 12-mailer test: no effect. A 9-mailer negative campaign showed slight *demobilisation*. |
| **One mailing per month, per sender, is the average consumer's stated ceiling** | van Diepen, Donkers & Franses, [ERIM 2006](https://repub.eur.nl/pub/7832/ERS-2006-029-MKT.pdf), survey n=213 Dutch households | **[PRIMARY DATA]** (survey, self-reported) | "Individuals, on average, find a charitable direct mailing once a month acceptable, but this ranges from zero to almost twice a week." |
| **25 mailings/year was profit-optimal** | Rhenania (German catalogue), Elsner/Krafft/Huchzermeier, [Interfaces 33(1) 2003](https://econpapers.repec.org/RePEc:inm:orinte:v:33:y:2003:i:1:p:50-66) / Marketing Science 23(2) 2004 | **[PRIMARY DATA]**, but wrong population | Real optimisation on 1.1m *existing catalogue buyers*. Customer base +55%, profitability quadrupled, #5 → #2 in the German market. Do not read across to cold homeowners. |
| **Quarterly "pulsing" (one quarter on, one off) optimal** | 5 Dutch charities, 22 quarters, via [Agitator/DonorVoice 2022](https://agitator.thedonorvoice.com/what-the-hell-is-pulsing/) | **[PRIMARY DATA]** (underlying study) / **[VENDOR CLAIM]** (the recommendation) | The underlying finding is real ("response does not follow the spend"); the "one quarter on, one off" prescription is the blog's interpretation. |
| **4–6 appeals/year minimum for nonprofits; 2→4 appeals = +32% net revenue** | Fundraising blogs, Russ Reid agency cases | **[VENDOR CLAIM]** | No control group. Gross revenue in the 5→10 (+123%) and 3→6 (+110%) cases; net and LTV effects never reported. |
| **Real estate: mail your farm 12×/year; 33 "touches"/year** | Gary Keller, *The Millionaire Real Estate Agent* (2004); Buffini/KW coaching | **[UNSOURCED FOLKLORE]** | See §7. No underlying study located. |
| **"NAR data shows 12×/year vs 8× more than doubles ROI"** | Repeated across real-estate mail vendors | **[UNSOURCED FOLKLORE]** | Searched NAR's research portal and general web; **no such NAR publication found**. |
| **"It takes 8.4 contacts before a prospect remembers your name"** | Real-estate mail vendors | **[UNSOURCED FOLKLORE]** | **No source of any kind located.** The decimal point is doing rhetorical work. |
| **"7 touches"** | See §8 | **[UNSOURCED FOLKLORE]** | Descends from an 1885 advertising salesman who said *twenty*. |
| **"80% of sales happen between the 5th and 12th contact"** | See §8 | **[UNSOURCED FOLKLORE]** — traceable, but to a 1942 survey with n<40 | See §8 for the full trail. |

---

## 2. Optimal mailing frequency: what has actually been tested

### 2.1 The strongest evidence is political, and it says ~6

The only body of literature that has *randomly assigned different numbers of mail pieces to the same households and measured a behavioural outcome at scale* is US voter-mobilisation field experimentation. It is the highest-quality evidence in this entire report.

**[PRIMARY DATA]** New Haven, 1998 general election (Gerber & Green). Registered voters received one, two, or three pieces of nonpartisan direct mail over the four weeks before the election. Results ([Gerber & Green field-experiments handbook, 2016, p.19](https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf)):

| Treatment | Turnout | n |
|---|---|---|
| Control (no mail, no phone, no canvass) | 42.2% | 11,596 |
| 1 mailer | 42.6% | 2,550 |
| 2 mailers | 43.3% | 2,699 |
| 3 mailers | 44.6% | 2,527 |

Regression across the full sample (n=31,098), controlling for phone and canvassing: **+0.5 percentage points per additional mailer** (SE = 0.3). No significant differences among the three message themes (civic duty / neighbourhood / close election). Note the shape: **linear over 1–3 pieces, no sign of saturation.**

**[PRIMARY DATA]** New Haven, 1999 mayoral election. Same authors, and the study exists *specifically* to find the ceiling: "The innovation of this study was to send **up to eight mailings** in order to assess diminishing returns... **The results suggest that returns from mailings begin to diminish after six mailings per household.**"

That single sentence is the most directly useful finding in the literature for sequence-length design, and it is the only clean answer to "how long should the sequence be?" that comes from an experiment rather than an opinion.

**[PRIMARY DATA]** The meta-analytic anchor: Green & Gerber (2015) pool **85 distinct studies conducted 1998–2014**, derived from 220 treatment/control comparisons. Pooled effect of sending a piece of mail: **about ¾ of a percentage point on turnout.** Social-pressure mail pools at **2.3pp**.

### 2.2 The critical caveat: repetition only accumulates for *reminder* content, not *persuasion* content

This is the most important structural finding, and it is easy to miss.

**[PRIMARY DATA]** Advocacy mail — mail that argues a case for a candidate or cause, which is the nearest analogue to commercial persuasion mail — produces "essentially a string of null findings" even at high frequency:

- Cardy (2005): an abortion-rights group sent **five full-colour glossy mailings** to strongly pro-choice voters (treatment n=1,974, control n=2,008) between 19 and 6 days before the election. **Turnout in the control group was slightly higher than in the treatment group.**
- Gerber, Green & Green (2003), New Jersey: mailings boosted turnout among high-propensity Democrats only; combined across samples, "mail did not significantly increase voter turnout." A negatively-toned mayoral campaign sending **nine mailings per household** showed "some slight evidence for **demobilisation**."
- Cubbison (2015): a massive test sending **up to nine pieces** for a gubernatorial candidate in 2005, and **up to twelve mailers** for Republican state legislative districts in 2014 — no effect.

So: **piling up more pieces of an argument does not accumulate into a decision.** Frequency compounds for mail that reminds/nudges a person about an action they were already disposed toward; it does nothing (or backfires) for mail that tries to argue someone into a position.

### 2.3 Frequency in charity fundraising: the numbers everyone quotes are gross, not net

**[VENDOR CLAIM]** The widely-circulated fundraising frequency numbers — 2 appeals/year → 4 appeals/year producing **+32% net revenue**; one organisation going 5 → 10 solicitations for **+123% YoY revenue**; another 3 → 6 for **+110% YoY** (attributed to the Russ Reid agency) — appear in fundraising trade content without control groups, without net-of-cost figures in two of the three cases, and without any LTV or retention follow-up. Discussed critically by [Michael Rosen (2015)](https://michaelrosensays.wordpress.com/2015/04/17/is-it-better-or-worse-to-send-more-appeals/), who flags exactly these gaps.

**[VENDOR CLAIM / correlational]** M+R's analysis of appeal volume vs online donor retention found a *moderate positive* correlation: every additional fundraising message per subscriber associated with **+0.2% overall annual donor retention** — and M+R themselves caveat that this "does not suggest there is no limit to appeal frequency." ([M+R Lab](https://www.mrss.com/lab/appeal-volume-and-the-impact-on-retention/))

**[VENDOR CLAIM]** Roger Craver's four-part Agitator series on solicitation frequency reports that **net income from successive appeals declines after a point**, that some file segments are far more receptive to multiple appeals than others, and that **mailing fewer appeals to certain individuals raised net income**. No published tables.

**[PRIMARY DATA]** The Dutch charity pulsing study (5 charities, 22 consecutive fiscal quarters, ~5 years, with spend and donation timing linked) found "response does not follow the spend" and that a **quarterly on/off pulsing schedule** beat continuous mailing. ([summarised, Agitator 2022](https://agitator.thedonorvoice.com/what-the-hell-is-pulsing/))

### 2.4 Catalogue/retail: high frequency is optimal — but the population is wrong for us

**[PRIMARY DATA]** Rhenania, a German mail-order company with 1.1m addresses, used Dynamic Multi-Level Modeling to optimise frequency, size and segmentation. **The profit-optimal frequency was 25 mailings a year.** Customer base grew >55%, profitability quadrupled, and the firm moved from #5 to #2 in its market. (Elsner, Krafft & Huchzermeier, *Interfaces* 33(1):50–66, 2003; *Marketing Science* 23(2):192–206, 2004 — ISMS Practice Prize winner.)

**[PRIMARY DATA]** Simester, Sun & Tsitsiklis, "Dynamic Catalog Mailing Policies," *Management Science* 52(5):683–696 (2006): the standard industry practice — mail whoever looks most likely to order from *this* catalogue — is **myopic**, and ignores the long-run consequences of the mailing decision. Their dynamic policy was validated in a large-scale field test. ([INFORMS](https://pubsonline.informs.org/doi/10.1287/mnsc.1050.0504))

**Extrapolation warning.** Both of these optimise contact with **people who have already bought**. The transaction is small, repeatable and immediate. A homeowner deciding whether to sell is the opposite on every axis. Rhenania's "25 a year" must not be read across.

---

## 3. Diminishing returns, wear-out and irritation

### 3.1 The cannibalisation finding — the cleanest number in the section

**[PRIMARY DATA]** van Diepen, Donkers & Franses, "Dynamic and Competitive Effects of Direct Mailings: A Charitable Giving Application," *Journal of Marketing Research* 46(1):120–133 (2009). Household-level donation data from three major Dutch charities. Findings ([Erasmus repository](https://repub.eur.nl/pub/16327/)):

- **A charity's own mailings act as short-term substitutes**: an additional mailing cannibalises revenue from the ones that follow it.
- **Competitors' mailings act as short-term complements**: other charities' mail *expands* the donating pool.
- **In the long run, these effects die out.**

Cannibalisation was estimated at roughly **63%** — i.e. an extra mailing is only profitable while its cost stays below ~37% of the revenue it generates. (Figure as reported in [Rosen's 2015 review](https://michaelrosensays.wordpress.com/2015/04/17/is-it-better-or-worse-to-send-more-appeals/) of the literature.)

Read plainly: **most of what an extra mail piece "earns" is money that would have arrived from the next piece anyway.** Any frequency test that measures gross response per campaign, and not incremental revenue against a no-mail holdout, will systematically overstate the value of adding touches.

### 3.2 Irritation: real, measurable — and the two best studies disagree

**[PRIMARY DATA — survey]** van Diepen, Donkers & Franses, "Irritation Due to Direct Mailings from Charities," [ERIM Report ERS-2006-029-MKT, June 2006](https://repub.eur.nl/pub/7832/ERS-2006-029-MKT.pdf), survey of 213 Dutch respondents:

- Mean **maximum acceptance level ≈ one charitable mailing per month, per charity**; individual range from zero to almost twice a week.
- **55.4%** (118/213) scored above the midpoint on the irritation scale — i.e. are annoyed by charitable direct mail. **23.0%** (49/213) scored 4 or 5 on *every* irritation item — very irritated.
- The effect is **asymmetric**: exceeding a person's acceptance level hurts more than under-mailing them helps. Loss-aversion shaped.
- Total mailing *volume* was insignificant once the excess-over-acceptance term was included. **It is not how many pieces you send; it is how many more than that person will tolerate.**
- Conclusion: "too many mailings do indeed lead to irritation, and **such irritation reduces annual donations**."

**[PRIMARY DATA — field experiment]** The same three authors then ran a controlled field experiment with **five of the largest charities in the Netherlands** to create exogenous variation in irritation, published as "Does irritation induced by charitable direct mailings reduce donations?", *International Journal of Research in Marketing* 26(3):180–188 (2009). Result: **direct mailings do cause irritation, but the irritation affects neither stated nor actual donating behaviour.** ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167811609000305) / [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1154287))

These two results are not reconcilable by hand-waving. The 2006 study is a **survey**: irritation and giving are both self-reported and both correlate with a third thing (being a heavily-mailed good donor). The 2009 study **manipulates** irritation and finds the causal path is absent. The honest reading:

> **Irritation is real, it is common (>50% of recipients), and it is caused by frequency. But the best-identified evidence says irritation is not, by itself, the mechanism that destroys revenue. Cannibalisation is.**

Which does *not* make irritation harmless — it makes it a **reputational and regulatory** risk rather than a directly measurable revenue leak. Which is exactly how it went wrong in the UK.

### 3.3 The tail risk: what over-mailing actually costs

**[PRIMARY DATA — regulatory/journalistic record]** The 2015 UK charity fundraising crisis. Olive Cooke, a 92-year-old poppy seller, was found to have her details on file with **99 charities** and to have received **466 mailings in one year** — reportedly up to 267 charity contacts in a single month. Context: **201,400,512 addressed and 242,940,851 unaddressed** direct-mail asks were sent by 1,203 UK charities in 2013 (Fundraising Standards Board). The [Etherington Review (September 2015)](https://publications.parliament.uk/pa/cm201516/cmselect/cmpubadm/431/43104.htm) found self-regulation inadequate and led to the creation of the Fundraising Preference Service.

The lesson is not that any single charity mailed too often. **No individual sender in that story was behaving unusually.** The damage came from aggregate frequency across senders, landing on an identifiable, sympathetic individual, and it was a *sector-level* regulatory event. That is a tail risk of high-frequency addressed mail to older homeowners which does not show up anywhere in a response-rate table.

### 3.4 Advertising wear-out theory (for completeness)

**[PRIMARY DATA]** Krugman, "Why Three Exposures May Be Enough," *Journal of Advertising Research* 12(6), 1972 — the only measured source in the whole "effective frequency" lineage. Exposure 1 = "What is it?"; exposure 2 = "What of it?"; exposure 3 = reminder. The ARF's Naples Report (1979) later showed effectiveness does not simply top out at three.

Habituation–tedium theory: as repetitions increase, tedium grows faster than habituation; beyond a point further repetition has no positive impact and may build negative association. This is theory, widely supported in lab settings, and is the mechanism people *mean* when they say "wear-out."

---

## 4. Recency: how long does a mail piece stay live?

### 4.1 In-home behaviour — good primary measurement exists

**[PRIMARY DATA]** [JICMAIL](https://www.jicmail.org.uk/about-jicmail/useful-definitions/) is the UK Joint Industry Committee for mail measurement — a continuous household panel that tracks individual mail items for 28 days. Definitions matter: *Lifespan* = average days between an item first being interacted with and being discarded or filed (capped at 28 days). *Item Frequency* = number of interactions in a four-week window. *Item Reach* = number of people in the household who interacted with it.

Q2 2025 benchmarks ([via Whistl](https://www.whistl.co.uk/insights/jicmail-mail-driven-digital-interactions-reach-five-year-high)):

| Mail type | Lifespan | Frequency (28d) | Reach | Attention |
|---|---|---|---|---|
| Business Mail | 8.7 days | 4.9 | 1.16 | 186 sec |
| **Direct Mail** | **7.6 days** | **4.6** | **1.13** | **145 sec** |
| Partially Addressed | 6.6 days | 4.1 | 1.09 | 86 sec |
| Door Drops | 6.0 days | 3.1 | 1.05 | 60 sec |

Q1 2026 figures are directionally identical (Direct Mail 7.8 days / 4.5 interactions; Door Drops 5.6 days / 3.0).

Two things follow. First, **an addressed mail piece is physically live in the home for roughly a week and gets picked up ~4–5 times** — it is not a single impression. Second, **addressed mail outperforms an unaddressed door drop on every dimension by 25–140%** (attention 145s vs 60s is the widest gap). If the choice is between a weekly door drop and a fortnightly addressed letter, the per-piece quality difference is large.

### 4.2 Response timing — the weakest-evidenced part of this report

**[VENDOR CLAIM]** The trade consensus, repeated across mail vendors without a dataset attached: first responses begin **3–5 days after delivery**, peak within **2 weeks**, most responses arrive within **30 days**, and campaigns should be tracked for **60–90 days**. I could not find a published response-by-day curve from a controlled source.

**[PRIMARY DATA — single case, secondhand]** The one substantive counterpoint comes from BBC TV licence renewal modelling, described in [Recast's adstock article](https://getrecast.com/adstock-rates/): direct mail response there "did not follow a simple decay pattern," with most people acting **"sometime in the next month, often peaking at around three weeks after the DM drop date."** The BBC's model tracked **six sequential reminder letters** with varying response rates, and the author notes a simple geometric adstock "would be of no use" — a Weibull-shaped, delayed-peak curve was needed.

**Implication for cadence design.** If response peaks at ~2–3 weeks rather than day 2, then a **weekly** sequence stacks piece 2 and piece 3 on top of the response window of piece 1. You cannot attribute, you cannot learn, and per §3.1 most of piece 2's apparent yield is piece 1's cannibalised. A **fortnightly-to-monthly** interval is the shortest interval at which each piece gets a clean read.

### 4.3 Spacing beats bunching — the one experiment on interval

**[PRIMARY DATA]** Sahni, "Effect of temporal spacing between advertising exposures: Evidence from online field experiments," *Quantitative Marketing and Economics* 13(3):203–247 (2015) — winner of the Dick Wittink Prize. Using individual-level exogenous variation in exposure *and its spacing*: **the likelihood of purchase increases when ads are spread apart rather than bunched together — even when spreading them apart means moving some exposures further from the purchase occasion.** Traditional advertising models could not reproduce the pattern; Sahni built a memory-based model to explain it. ([Springer](https://link.springer.com/article/10.1007/s11129-015-9159-9))

This is online display, not mail, so the read-across is medium-confidence. But it is the only clean causal evidence on *interval* rather than *count*, and it points the same way as the mail-response-curve reasoning: **spread the sequence out.**

---

## 5. Sequence design: does a developing argument beat a repeated one?

This is the thinnest area of published evidence, and the answer is largely inferential.

**[PRIMARY DATA — strong, indirect]** The single best evidence that *escalating* a sequence beats repeating it comes from Gerber, Green & Larimer's 2006 Michigan primary experiment (treatment groups of 20,000 each, control of 100,000), which used **four mailers representing a graded escalation of social pressure**:

| Mailer | Content | Turnout effect |
|---|---|---|
| Civic Duty | forceful "do your duty" appeal | **+1.8pp** |
| Hawthorne | adds "you are being studied / monitored" | (intermediate) |
| Self | shows *your household's own* voting record, promises a follow-up | **+4.9pp** |
| Neighbors | shows your record *and your neighbours'* | **+8.1pp** |

Baseline for a typical nonpartisan GOTV mailing: **under 0.5pp**. So the top of the escalation ladder was **~16× the effect** of a generic piece. Each step is distinguishable from the others at these sample sizes.

Two things this proves and one it does not. It proves (a) **content dominates frequency by more than an order of magnitude**, and (b) **the escalation direction that works is toward specific data about the recipient themselves.** It does *not* prove that the four pieces sent *sequentially to the same household* would compound — they were tested as separate treatments, not as a series.

It also has a cost. The "Neighbors" mailing "provoked outrage among some recipients" (Matland & Murray 2014), prompting a search for versions producing the effect without the agitation. The "Self" variant — your own data, no neighbours — retained most of the lift (+4.9pp, a 16% relative boost over a 29.7% base) with "only a modest level of resistance."

**[PRIMARY DATA — the negative case]** Against this, §2.2: 5, 9 and 12-piece *advocacy* sequences produced nulls. Long sequences of argument do not compound. Long sequences that each deliver a *new specific fact about you* have never been properly tested, but the cross-sectional evidence above says the per-piece ceiling is far higher for the latter.

**[VENDOR CLAIM]** Hotkar, Garg & Sussman, "Strategic social media marketing: An empirical analysis of sequential advertising," *Production and Operations Management* (2023), ran a large randomised field experiment with a human services organisation on Facebook/Instagram testing **sequenced ads against a simultaneous-burst baseline**, and report that the sequential strategy is effective. I could not retrieve the effect sizes (paywalled), so this is flagged as unverified rather than primary. ([SAGE](https://journals.sagepub.com/doi/10.1111/poms.14075))

**[VENDOR CLAIM]** Renewal series design from magazine publishing gives a rough shape for a serialised sequence: Bloomberg Personal Finance used a **seven-effort renewal series** starting six months before expiry and running one month past it, with the **first effort earning 15–20% response**, the second effort next best, then the cover wrap. ([Chief Marketer](https://www.chiefmarketer.com/the-art-of-renewals/)) That is a monotonically declining series in which the *first* piece does the heavy lifting — the opposite shape to the "80% happens on touch 5–12" folklore.

---

## 6. Trigger-based vs calendar-based mail

### 6.1 The one clean experiment says: a *better first piece* beats *a second piece*

**[PRIMARY DATA]** [FCA Occasional Paper No. 12, "Encouraging consumers to act at renewal", December 2015](https://www.fca.org.uk/publication/occasional-papers/occasional-paper-12.pdf). Randomised controlled trials with a combined sample of **over 300,000 customers** across one home insurer and two motor insurers, plus follow-up surveys of 4,000, testing what content in a renewal notice makes people shop around, switch or negotiate.

Results:

- **Disclosing last year's premium alongside this year's** increased switching or negotiating by **3.2 percentage points** — equivalent to **11–18% more customers acting**. Effect scaled with the size of the price increase: **+1.2pp** in the lowest price-change quartile rising to **+4.7pp** in the highest.
- **"We tested sending reminder letters, text messages and emails two weeks after sending renewal notices with one motor insurer and found no statistically significant effects on switching or negotiating."**
- Using bullet points, simpler language, a leaflet on how to shop around, or a glossary leaflet: **no relevant impact.**

This is the single most decision-relevant experiment I found, because the setup is close to ours: a cold-ish relationship, a household financial decision, a defined moment of relevance, and a letter. And it says three things bluntly. **(1)** Putting a specific number *about the recipient* in front of them moved real behaviour. **(2)** A generic follow-up touch two weeks later moved nothing. **(3)** Making the piece clearer, friendlier and more helpful moved nothing.

The read-across: **frequency is not the lever; recipient-specific data is the lever.** A second calendar touch that carries no new personal information about the recipient has a measured effect indistinguishable from zero in a 300,000-person RCT.

### 6.2 Programmatic direct mail vendor numbers — capture but discount

All of the following are **[VENDOR CLAIM]**. None disclose sample size, holdout design, or measurement window.

- **PebblePost**: "average 8× incremental ROAS" on prospecting; retention programmes "running 5–9% response rates and 4–8× ROAS"; a jewellery brand seeing "nearly 30% conversion rate lift" from PDM+digital vs single-channel. Earlier (2015 launch-era) claims of "**response rates around 20 percent, and conversion rates of 40+ percent**" against a 1–2% industry baseline. ([PebblePost](https://www.pebblepost.com/blog/performance-and-lift-measurement-for-programmatic-direct-mail/), [MarTech 2015](https://martech.org/pebbleposts-new-platform-brings-direct-mail-into-the-age-of-quick-retargeting/))
- **PostPilot** ([BFCM Benchmark Report](https://www.postpilot.com/bfcm-benchmark-report)): Dr Squatch 10×+ ROAS / 6% CVR; KURU Footwear 11.5× ROAS / 4.5% CVR (full-funnel); Caden Lane **cold prospecting** 3.8× ROAS / **1.2% CVR**. No dates, no sample sizes.
- General programmatic claims: triggered programmes ship **48–72 hours** after the trigger; "mail with three or more personalization points — name, plus a relevant offer, plus a behavioral trigger — lifts response 135 percent over static mail"; "automated behavioural-trigger mail consistently pulls **2 to 3 times** the response rate of generic mail."

**Why the 20%/40% numbers must be discounted almost entirely.** Triggered mail is sent to people who *just demonstrated intent* (browsed, abandoned a cart). The measured "response" therefore conflates the mail's effect with the selection effect of having chosen high-intent recipients. Without a randomised holdout among triggered users, these numbers measure the trigger's quality as a selector, not the mail's causal lift. Note that PostPilot's one **cold prospecting** case — the only comparable to our situation — reports **1.2% conversion**, roughly an order of magnitude below the triggered figures. That gap *is* the selection effect.

The directional claim (triggered > calendar) is almost certainly true and is consistent with the FCA result (relevance beats repetition). The **magnitudes are not usable.**

### 6.3 Baseline response rates: the widely-quoted DMA figures are not reliable

**[VENDOR CLAIM, low grade]** The ANA/DMA Response Rate Report 2018 is the source of the ubiquitous "**9% house list / ~5% prospect list**" figures. Prior editions: 2017 gave **5.1% / 2.9%**; the 2003–2015 average was **3.6% / 1.6%**. A near-doubling in one year with no market event behind it is a methodology artefact, and **the report itself states the sample size was small and that the numbers "should be used for information purposes only."** ([Dunhill's summary of the 2018 report](https://www.dunhills.com/2019/03/06/takeaways-from-the-ana-dma-response-rate-report-2018/); [ANA listing](https://www.ana.net/miccontent/show/id/rr-2018-ana-dma-respose-rate)) The 2026-vintage "4.4% average / 36× email" figures now circulating across mail vendors are downstream restatements of this same series. **Do not plan against them.**

---

## 7. Real-estate-specific farming cadence claims

Every frequency claim in real-estate farming that I could find is folklore. I chased each one.

**"33 touches per year."** **[UNSOURCED FOLKLORE]** Originates with Gary Keller's *The Millionaire Real Estate Agent* (2004) and is propagated by Keller Williams and Buffini & Company coaching materials. The claim as repeated — "Keller's research indicates that people need to hear from you 33 times per year to remember you" — has no accompanying study, sample, or measurement. ([Rev Real Estate School](https://www.revrealestateschool.com/tips/33-touch-campaign))

**"12 pieces over 12 months produces roughly one transaction per 50 recipients."** **[UNSOURCED FOLKLORE]** Cited by ReminderMedia, attributed to *The Millionaire Real Estate Agent*. Same book, same absence of underlying data. Note that a 2% annual conversion of a cold farm list would be an extraordinary result — for comparison, the entire political-mail literature struggles to move a *low-cost, low-commitment* behaviour by more than 1–8 percentage points.

**"NAR stats show mailing 12 times per year versus 8 or less more than doubles effectiveness and ROI."** **[UNSOURCED FOLKLORE]** Repeated by multiple real-estate mail vendors. Searched NAR's research portal and the general web; **no NAR publication containing this claim was located.**

**"It can take up to 8.4 contacts within a 30-day window before a prospect remembers an agent's name."** **[UNSOURCED FOLKLORE]** **No source of any kind found.** The false precision of the decimal is a reliable marker of a number that was invented rather than measured.

**"Postcard ROI is measured in listings won over a 12–18 month horizon, not immediate inbound calls."** **[VENDOR CLAIM]** — but this one is probably right, and is the single most useful piece of industry framing here. It also means that any real-estate farming cadence claim is essentially unfalsifiable in the short run, which is precisely why the folklore has survived.

**One genuinely relevant NAR-sourced fact:** 66% of sellers used an agent who was referred to them or one they had used before ([NAR Profile of Home Buyers and Sellers](https://www.nar.realtor/research-and-statistics/research-reports)). That is real data, and it says the mechanism farming is trying to buy — being the remembered, referred name — is the right target. It says nothing about the cadence required to get there.

---

## 8. The provenance of the "7 touches" / "5-to-12 contacts" claims

The business has partially built a plan on the second claim. Here is the trail.

### 8.1 "80% of sales are made between the 5th and 12th contact"

The claim always travels with a ladder: **2% of sales close on the 1st contact, 3% on the 2nd, 5% on the 3rd, 10% on the 4th, and 80% between the 5th and 12th** — attributed to the "**National Sales Executive Association**."

**Step 1 — the attributed organisation does not exist under that name.** An [investigation published in June 2014](https://askthemanager.com/2014/06/92-percent-of-linkedin-users-believe-made-up-statistics/) searched for the National Sales Executive Association and found nothing: no such body in Google, and various unrelated NSEAs (National Student Employment Association, Nevada State Education Association). Others report the Council of Better Business Bureaus and IRS non-profit search also returning nothing. The author also notes **the percentages don't add up correctly** (2+3+5+10+80 = 100, leaving nothing for contacts beyond the 12th, which is not how the claim is used).

**Step 2 — there *is* a real successor organisation, and it has published on the statistic.** Sales & Marketing Executives International (SMEI) is the modern name of what was the National Sales Executives Association. On its own [Sales Statistics page](https://smei.org/sales-statistics/), SMEI states:

> "In 1942, the Long Island, NY chapter of NSEA (now SMEI) surveyed their members to determine the ratio of calls made to sales made."

**Step 3 — SMEI itself disowns the number's authority.** Rather than defending it, SMEI's page notes that **the sample size was less than 40**, that the results "have been widely distributed, copied and pasted" across the internet, and advocates scrutinising such statistics by asking who conducted the research, whether it is unbiased, how recent it is, and whether the sample size was adequate. **The organisation the statistic is attributed to is using it as a worked example of a statistic you should not trust.**

**Verdict.** The claim is not a fabrication — it has a real origin. But that origin is:

- **1942** — 84 years old, pre-television, pre-direct-response-as-we-know-it;
- **a single local chapter survey**, self-reported by members;
- **n < 40**;
- about **in-person and telephone sales calls by salespeople**, not mail, not marketing touches;
- and **not a randomised or controlled measurement of anything.**

It should carry **zero** weight in a mail sequence design. It is, at best, evidence that in 1942 fewer than forty Long Island salesmen believed persistence mattered.

*(Secondary note: VentureBeat published a piece titled "Those incredible sales stats everyone cites are actually completely false" reaching the same conclusion; the page returned 403 to automated retrieval, so I have not verified its contents directly and do not rely on it above.)*

### 8.2 "The Rule of 7"

The trail here is longer and ends in a worse place: the number has been **falling** for 140 years, and the only measured link in the chain says three, not seven.

| Year | Source | Claimed number | Basis |
|---|---|---|---|
| 1885 | Thomas Smith, *Successful Advertising* (London) | **Twenty** | Assertion by a man selling advertising advice. [Full text](https://cros.land/wp-content/uploads/2011/10/Successful-Advertising.pdf) |
| 1923 | Claude Hopkins, *Scientific Advertising* | ~twenty | Assertion by an advertising practitioner |
| 1930s | "Hollywood studios found filmgoers needed 7 poster views" | **Seven** | Origin story; **no documentation located** |
| 1972 | Herbert Krugman, "Why Three Exposures May Be Enough," *JAR* 12(6) | **Three** | **Actual experimental psychology** |
| 1989 | Jeffrey Lant, *Cash Copy* | **Seven within 18 months** | Marketing advice book; no study cited |

Smith's 1885 passage is the ancestor of the whole family, and it is worth reading because it is *obviously* a piece of rhetoric rather than a measurement: the first time a man sees an ad he does not see it; the second he does not notice it; the third he is conscious of it; the fourth he faintly remembers it; the fifth he reads it; the sixth he turns up his nose at it; the seventh he reads it through and says "Oh brother!"; the eighth "Here's that confounded thing again!"... the seventeenth he makes a memorandum to buy it; the eighteenth he swears at his poverty; the nineteenth he counts his money carefully; **and the twentieth time he buys.** ([Branding Strategy Insider](https://brandingstrategyinsider.com/advertising-frequency-theory-circa-1885/))

Note *who* was making the claim in every unmeasured case: a man selling advertising space, or advertising advice, to a buyer who pays per insertion. The number is a **sales argument for buying more insertions**, and has been since 1885. ([Analysis: anartfulscience](https://anartfulscience.com/insights/rule-of-7-marketing/); [Inversion Agency, "Zombie Marketing Myths"](https://inversion.agency/articles/zombie-myths))

**Verdict.** "7 touches" is **[UNSOURCED FOLKLORE]** with a commercially-motivated pedigree. The one empirically grounded member of the family — Krugman 1972 — argues for **three**, and even that has been qualified since the ARF's Naples Report (1979).

### 8.3 How the folklore reached real estate

The bridge is visible in the trade press. [RISMedia, "Why 12 is the Magic Number in Your Marketing Plan" (December 2009)](https://www.rismedia.com/2009/12/13/why-12-is-the-magic-number-in-your-marketing-plan/) is a real-estate-industry article whose "12" is derived from the "5th to 12th contact" claim. That is how a 1942 survey of <40 Long Island salesmen became a monthly real-estate mailing cadence.

### 8.4 What to do with this

The claims are not merely unsupported — they are **directionally misleading in a specific, expensive way.** They say the yield is concentrated *late* in a long sequence, which justifies paying for touches 5 through 12 before you are allowed to conclude anything. Every controlled measurement in this report says the opposite shape:

- New Haven: effect accumulates but **flattens after ~6**;
- Magazine renewals: the **first** effort pulls 15–20%, each subsequent one less;
- van Diepen JMR 2009: extra mailings largely **cannibalise** later ones (~63%);
- FCA: an extra reminder touch two weeks later did **nothing** in a 300,000-person RCT;
- Political advocacy mail: 5, 9 and 12-piece sequences produced **nulls**.

**If a mail programme is losing money at touch 4, no evidence in this report supports the belief that touches 5–12 will rescue it.**

---

## 9. Extrapolation to a homeowner mail sequence: how safe is each read-across?

| Evidence base | Distance from our case | Safety |
|---|---|---|
| **FCA insurance renewal RCT (2015)** | Household financial decision, cold-ish relationship, addressed letter, single decision moment, recipient-specific numbers | **Closest analogue found.** Read across with reasonable confidence, especially the two negatives (reminders don't work, simplification doesn't work). |
| **Political mail RCTs** | Cold, non-transactional, unsolicited, low base rate, addressed. Outcome (voting) is far lower-commitment than listing a house | **Medium.** Use the *shape* findings (diminishing after ~6; repetition of argument fails; recipient-specific data multiplies effect ~16×). Do not use the effect *sizes*. |
| **Charity fundraising** | Warm, opted-in, repeat relationship; small transactions | **Medium-low** for frequency ceilings, **high** for the cannibalisation warning and the irritation/regulatory tail risk. Their "acceptable = monthly" finding is about an *existing supporter*, so it is an upper bound for a cold homeowner, not a target. |
| **Catalogue / retail (Rhenania, Simester)** | Existing buyers, small repeat transactions, immediate response | **Low.** "25 mailings/year is optimal" is true for their population and would be reckless applied to ours. The transferable idea is the *method* — optimise against long-run value with holdouts, not against per-campaign response. |
| **Programmatic DM vendors** | E-commerce, high-intent triggered audiences | **Very low for magnitudes.** The direction (triggered > calendar) is safe; every number is contaminated by selection. |
| **Real-estate farming coaching** | Same industry | **Zero.** Same industry, no evidence. Industry proximity is not evidential proximity. |

The important asymmetry: **the closest analogue by *situation* (FCA insurance) and the closest by *method quality* (political RCTs) agree with each other**, and they agree against the folklore. Both say content specificity dominates frequency, and both say added generic touches are worth approximately nothing.

---

## 10. What we still don't know

These are genuine gaps, not hedging. Each one is a place where I looked and the evidence does not exist publicly.

1. **No published randomised test of mail frequency to *cold homeowners* about a property decision.** Not one. Every frequency experiment found is voting, charity donation, catalogue purchase, or insurance renewal.

2. **No published day-by-day response decay curve for addressed direct mail from a controlled source.** The "3–5 days to first response, peak at 2 weeks, 30-day window" consensus is vendor lore. The one substantive data point (BBC TV licence, ~3-week peak, non-geometric) is secondhand and from a single campaign. **We should measure our own curve; nobody else's is publishable-grade.**

3. **Whether a *serialised argument* compounds across pieces.** The Michigan social-pressure ladder proves escalating *content* has escalating effect when tested cross-sectionally. It does not prove that sending the same four pieces in sequence to one household compounds. This is directly testable and appears to be untested in public.

4. **The frequency at which complaint/opt-out rates rise for addressed commercial mail.** Extensive searching returned only email benchmarks (Gmail/Yahoo 0.3% spam-complaint threshold). No published dose-response curve of mail frequency to complaints. The Olive Cooke case tells us the *aggregate* ceiling exists and is catastrophic when crossed; it tells us nothing about where a single sender's line is.

5. **Whether the van Diepen contradiction resolves in our favour.** The 2006 survey (irritation reduces giving) and the 2009 field experiment (it doesn't) disagree. Neither was run on cold recipients — both studied people with an existing relationship to the charity. For a *cold* homeowner, irritation and non-response may be the same event, in which case neither study applies.

6. **Effect sizes from the Hotkar/Garg/Sussman (2023) sequential-advertising field experiment** — paywalled; the direction is reported, the magnitudes were not retrievable.

7. **Whether the ~6-mailing ceiling is a property of the sequence or of the campaign window.** New Haven's eight mailings were compressed into a pre-election period of weeks. A ceiling of six pieces in four weeks and a ceiling of six pieces in eighteen months are very different claims, and the published account does not distinguish them. Given Sahni's spacing result, **this is the single most consequential unknown for choosing weekly vs monthly.**

---

## Source index

**Primary research**
- Gerber & Green, *Field Experiments on Voter Mobilization: An Overview* (handbook chapter, ~2016) — https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf
- Gerber, Green & Larimer, "Social Pressure and Voter Turnout," 2008 — https://isps.yale.edu/sites/default/files/publication/2012/12/ISPS08-001.pdf
- FCA Occasional Paper No.12, *Encouraging consumers to act at renewal*, December 2015 — https://www.fca.org.uk/publication/occasional-papers/occasional-paper-12.pdf
- van Diepen, Donkers & Franses, *Irritation Due to Direct Mailings from Charities*, ERIM ERS-2006-029-MKT, June 2006 — https://repub.eur.nl/pub/7832/ERS-2006-029-MKT.pdf
- van Diepen, Donkers & Franses, "Does irritation induced by charitable direct mailings reduce donations?", *IJRM* 26(3):180–188, 2009 — https://www.sciencedirect.com/science/article/abs/pii/S0167811609000305
- van Diepen, Donkers & Franses, "Dynamic and Competitive Effects of Direct Mailings," *JMR* 46(1):120–133, 2009 — https://repub.eur.nl/pub/16327/
- Simester, Sun & Tsitsiklis, "Dynamic Catalog Mailing Policies," *Management Science* 52(5), 2006 — https://pubsonline.informs.org/doi/10.1287/mnsc.1050.0504
- Elsner, Krafft & Huchzermeier, "Optimizing Rhenania's Mail-Order Business Through DMLM," *Interfaces* 33(1):50–66, 2003 — https://econpapers.repec.org/RePEc:inm:orinte:v:33:y:2003:i:1:p:50-66
- Sahni, "Effect of temporal spacing between advertising exposures," *QME* 13(3):203–247, 2015 — https://link.springer.com/article/10.1007/s11129-015-9159-9
- Hotkar, Garg & Sussman, "Strategic social media marketing: sequential advertising," *POM*, 2023 — https://journals.sagepub.com/doi/10.1111/poms.14075
- JICMAIL metric definitions — https://www.jicmail.org.uk/about-jicmail/useful-definitions/
- JICMAIL Q2 2025 results (via Whistl) — https://www.whistl.co.uk/insights/jicmail-mail-driven-digital-interactions-reach-five-year-high
- UK Parliament PACAC, *The 2015 charity fundraising controversy* — https://publications.parliament.uk/pa/cm201516/cmselect/cmpubadm/431/43104.htm

**Provenance chase**
- SMEI, *Sales Statistics* (the 1942 / n<40 admission) — https://smei.org/sales-statistics/
- Ask The Manager, *92.6% of LinkedIn Users Believe Made Up Statistics*, June 2014 — https://askthemanager.com/2014/06/92-percent-of-linkedin-users-believe-made-up-statistics/
- Thomas Smith, *Successful Advertising*, 1885 (full text) — https://cros.land/wp-content/uploads/2011/10/Successful-Advertising.pdf
- Branding Strategy Insider, *Advertising Frequency Theory: Circa 1885* — https://brandingstrategyinsider.com/advertising-frequency-theory-circa-1885/
- An Artful Science, *The Marketing Rule of 7 & the 7-Touchpoint Myth* — https://anartfulscience.com/insights/rule-of-7-marketing/
- Inversion Agency, *Zombie Marketing Myths Debunked* — https://inversion.agency/articles/zombie-myths
- RISMedia, *Why 12 is the Magic Number in Your Marketing Plan*, December 2009 — https://www.rismedia.com/2009/12/13/why-12-is-the-magic-number-in-your-marketing-plan/
- Rev Real Estate School, *33 Touch Campaign* — https://www.revrealestateschool.com/tips/33-touch-campaign

**Practitioner / vendor**
- Agitator (DonorVoice), *What the Hell is "Pulsing"?*, Sept 2022 — https://agitator.thedonorvoice.com/what-the-hell-is-pulsing/
- Agitator (DonorVoice), *Donor vs Fundraiser Fatigue* — https://agitator.thedonorvoice.com/donor-vs-fundraiser-fatigue/
- Michael Rosen, *Is It Better or Worse to Send More Appeals?*, April 2015 — https://michaelrosensays.wordpress.com/2015/04/17/is-it-better-or-worse-to-send-more-appeals/
- M+R Lab, *Appeal Volume and the Impact on Retention* — https://www.mrss.com/lab/appeal-volume-and-the-impact-on-retention/
- PebblePost, *Performance and Lift Measurement for PDM* — https://www.pebblepost.com/blog/performance-and-lift-measurement-for-programmatic-direct-mail/
- MarTech, *PebblePost brings direct mail into the age of quick retargeting*, 2015 — https://martech.org/pebbleposts-new-platform-brings-direct-mail-into-the-age-of-quick-retargeting/
- PostPilot, *Direct Mail BFCM Benchmark Report* — https://www.postpilot.com/bfcm-benchmark-report
- Dunhill, *Takeaways from the ANA|DMA Response Rate Report 2018* — https://www.dunhills.com/2019/03/06/takeaways-from-the-ana-dma-respose-rate-report-2018/
- Recast, *Adstocks: Accounting for the Lagged Effect of Advertising* (BBC TV licence DM case) — https://getrecast.com/adstock-rates/
- Chief Marketer, *The Art of Renewals* — https://www.chiefmarketer.com/the-art-of-renewals/

**Note on retrieval failures:** the following returned HTTP 403 to automated fetch and are cited from search-result extracts rather than direct reading: VentureBeat's sales-stats debunk, Michael Rosen's blog, M+R Lab, the POMS sequential-advertising paper, SSRN, click2mail. Where a claim rests only on such a source it is labelled as vendor/secondhand above.
