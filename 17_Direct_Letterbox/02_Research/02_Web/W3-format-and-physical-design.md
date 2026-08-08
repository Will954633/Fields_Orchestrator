# W3 — Direct Mail: Physical Format & Presentation

**Research question:** What physical format and presentation of addressed homeowner direct mail performs best, and what is the actual evidence?
**Compiled:** 2026-08-08 · **Scope:** Australia-relevant, homeowner-addressed, recurring sequence

---

## 0. The single most important finding, up front

**The direct mail response-rate numbers everyone quotes by format do not exist as reliable data.**

The ANA *Response Rate Report 2023* — the source the entire industry launders as "direct mail gets 4.4%", "oversized envelopes pull best", "dimensional gets 5–15%" — says the following in its own text:

> "Due to the very small number of responses by campaign type … as well as list and format type (e.g., dimensional mail sent to prospect lists), **there was insufficient data to report on response rates and other metrics at this level of granularity.**"
> — ANA Response Rate Report 2023, Ch. 6, p.62 ([PDF mirror](https://theworldsgreatestmarketing.com/wp-content/uploads/2025/04/rr-2024-02-ana-response-rate-report-2023.pdf), 2024) **[PRIMARY DATA — but see caveats]**

And in its methodology:

> "Those choosing [*Actual metrics*] ranged from 5 percent to 50 percent, with an average of **21 percent** … For these reasons, **the report data should not be considered benchmark data, but used for informational purposes only.**" (p.5)

The direct mail chapter runs on **N = 21 to 40 respondents**, self-reported, ~79% of whom were estimating. The format tables are `N = 25*` and `N = 21*`, both flagged "*Small base" by ANA itself. The famous "oversized envelope wins / postcard 5.7% / letter 4.3%" split is from the **2018** DMA report and has been recycled and re-dated ever since without anyone re-measuring it.

**Consequence for us:** any format decision justified by "industry response rates by format" is justified by nothing. The defensible evidence comes from three other places — randomised trials in the survey/health literature, randomised field experiments in economics and political science, and the UK JICMAIL campaign panel. Those are used below.

---

## 1. Format comparison table with evidence grade

| Format | Best available evidence | Number | Grade | Cost-adjusted read (AU, postage only, see §8) |
|---|---|---|---|---|
| **Addressed letter in envelope, warm/known relationship** | JICMAIL Response Rate Tracker 2025, 1,735 campaigns | **7.2% response, £9.00 ROI** | [PRIMARY DATA] industry-funded, audited | Best response of anything measured. AU postage $1.10 (C5 Promo Post) → ~$15 postage/response |
| **Addressed letter in envelope, cold** | JICMAIL RRT 2025, 1,659 campaigns | **0.9% response, £3.20 ROI** | [PRIMARY DATA] industry-funded | ~111 pieces/response → ~$122 postage/response at C5 Promo Post |
| **Cold addressed, *repeat* send to same list** | JICMAIL RRT 2025 | **2.5× response rate, +37% ROI vs first send** | [PRIMARY DATA] | The single largest format-independent lever found in any real-campaign dataset |
| **Unaddressed door drop** | JICMAIL RRT 2025, 324 campaigns | **0.5% response, £2.90 ROI** | [PRIMARY DATA] | ~200 pieces/response × $0.405 → ~$81 postage/response. *Cheapest per response, but cannot carry the recipient's address — which is our entire product* |
| **Postcard** | Canada Post/True Impact 2015 (EEG, n=270): postcard **motivation:cognitive-load ratio 0.90** — the **worst of all five physical formats tested and below email-on-smartphone (0.91)** | ratio 0.90 vs envelope 1.40 | [PRIMARY DATA] postal-operator-funded lab study, n=30/cell | Cheapest print, but the only format the pro-mail study itself found *did not beat digital* |
| **Postcard (response proxy)** | Cochrane/Edwards 2009: double postcard vs one page in envelope | **OR 0.47 (0.34–0.66)** — postcard roughly **halved** response | [PRIMARY DATA] RCT, n=600, single trial | Strongly negative, but one trial, survey context |
| **Envelope (plain letter)** | Canada Post 2015 | ratio **1.40** | [PRIMARY DATA] postal-funded lab | AU $1.10–$1.90 postage |
| **Dimensional / "lumpy"** | Canada Post 2015 | ratio **1.46** (2nd best) | [PRIMARY DATA] postal-funded lab | Vendor cost claims $5–$25/piece [VENDOR CLAIM]; needs ~10× the response of a letter to break even |
| **Dimensional — response rates** | "8.5% B2B", "20%+", "5–15% per ANA/DMA 2025" | — | **[UNSOURCED / fabricated citation]** — the ANA report *explicitly says it could not compute this*. Treat all dimensional response figures as marketing | — |
| **Envelope + scent** | Canada Post 2015 | ratio **1.75** (best tested) | [PRIMARY DATA] postal-funded lab, n=30 | No behavioural outcome measured. Do not act on this |
| **Multi-page booklet vs stapled pages** | Cochrane/Edwards 2009, 3 trials, 5,681 participants | **OR 1.10 (0.99–1.23) — no effect** | [PRIMARY DATA] RCT meta-analysis | Binding/production spend does not buy response |
| **Recurring personalised multi-page household report** | Allcott 2011 *J Public Econ*; Allcott & Rogers 2014 *AER* (Opower) — 600,000+ households randomised, 6.2M by 2013 | **1.4–3.3% sustained behaviour change**, no habituation over 60 months, effects persist 10–20%/yr decay after stopping | [PRIMARY DATA] **best-quality evidence in this entire document** | The closest structural analogue to our use case |
| **Handwritten address on envelope** | Cochrane/Edwards 2009, 7 trials, 5,091 participants | **OR 1.25 (1.08–1.45)**, low heterogeneity I²=14% | [PRIMARY DATA] RCT meta-analysis | Real, replicated, modest. ~+25% odds |
| **Handwritten envelope "99% open rate / 300% lift"** | Handwritten-mail vendors | — | **[VENDOR CLAIM]** — sourced to vendors selling handwritten mail; no controlled test published | Ignore the magnitude, keep the direction |
| **Self-mailer** | "DMA study showed nearly as good as oversized" | — | **[UNSOURCED]** — no locatable primary study; traces back to the same 2018 recycling | Unknown |
| **Fridge magnet / keepsake** | See §5 | — | **[VENDOR CLAIM] only** | No measured response evidence exists |

---

## 2. The neuroscience evidence — what was measured, and its limits

All three headline studies are funded by postal operators. That does not make them wrong; it makes the *selection of what got published* unreliable, and it means the outcome measures were chosen by people who needed a particular answer.

### 2.1 Canada Post / True Impact, *A Bias for Action* (2015)
Source: [twosidesna.org PDF](https://twosidesna.org/wp-content/uploads/sites/16/2018/05/CPC_Neuroscience_EN_150717.pdf) **[PRIMARY DATA — postal-operator-funded]**

- **Method:** 270 participants split into **nine cells of 30**, one media format each. EEG (cognitive load, motivation via frontal alpha asymmetry) + eye tracking. Two offers per participant (retail = low-involvement, travel = high-involvement). Baseline resting-state normalisation.
- **Headline results:** direct mail required **21% less cognitive effort** (5.15 vs 6.37), scored **20% higher on motivation** (6.77 vs 5.52) and **30% above the 5.2 neuromarketing benchmark**; brand recall **70% higher**; motivation:cognitive-load ratio **1.31 vs 0.87**.
- **The finding nobody quotes:** broken down by format, **the postcard scored 0.90 — below email-on-smartphone at 0.91, and last of all five physical formats.** Envelope+scent 1.75, dimensional 1.46, envelope 1.40, dimensional+sound 1.12, then email-smartphone 0.91, postcard 0.90, banner-smartphone 0.89, email-laptop 0.84, banner-laptop 0.78.

**Limits.** n=30 per cell. Single exposure in a lab. **No behavioural outcome was measured at all** — not a click, not a purchase, not a reply. "Motivation" is derived from frontal alpha asymmetry, a contested proxy whose link to real approach behaviour is asserted by the vendor ("the only metric that correlates with future behaviour, she says") rather than demonstrated in this study. Direct mail was "experienced in 3.5 seconds overall" — so the comparison is a 3.5-second glance, not a reading. **Plausibly self-serving:** the study was commissioned by a postal operator, executed by a neuromarketing firm whose business is selling this methodology, and the hypothesis ("direct mail is more action-oriented") is stated in the abstract as the thing to be confirmed.

### 2.2 USPS OIG × Temple University CNDM, *Tuned In: The Brain's Response to Ad Sequencing* (2017, RARC-WP-17-004)
Source: [uspsoig.gov PDF](https://www.uspsoig.gov/sites/default/files/reports/2023-01/RARC-WP-17-004.pdf) **[PRIMARY DATA — postal-operator-funded, but unusually candid]**

- **Method:** three sessions a week apart; 48 ads/week; physical ads were **printed postcards**, digital ads on a monitor. Week 3 = fMRI. Plus willingness-to-pay ($1–$50) and choice tasks. Plus two exploratory field campaigns.
- **Results:** physical ads created stronger memories and stronger brand recall; digital captured attention faster. **Single-media sequences beat mixed-media for memory**, with physical→physical strongest — *the opposite of the OIG's own pre-registered hypothesis*, which they say plainly.
- **Limits stated in the report itself:** "*The usual sample size for an fMRI study is 25–30 participants.*" "*The results of the field study are not statistically significant.*" "*There was not total agreement between what participants said they liked most, at what price they valued items, and what the brain scans showed.*" Participants said they preferred physical-physical but **would pay more for items shown in mixed-media** — the measures point different ways.

This is the most honest of the three. It is also, on its own terms, not evidence that any particular format sells anything.

### 2.3 Royal Mail MarketReach / Neuro-Insight, *The Private Life of Mail* (2015) and WARC/Marketreach *The Attention Advantage* (2023)
Sources: [royalmailwholesale.com PDF](https://www.royalmailwholesale.com/mint-project/uploads/423811624.pdf); [marketreach.co.uk](https://www.marketreach.co.uk/resource/WARC-Attention-Advantage) **[PRIMARY DATA — postal-operator-funded]**

- Neuro-Insight measured **engagement, emotional intensity, and long-term memory encoding (LTME)**. Mail out-scored email and TV on all three. The widely-quoted "**44% stronger** memory encoding when mail precedes a related digital ad" comes from this family of work.
- *Attention Advantage* (2023, Marketreach + Blue Yonder, 1,475 mail pieces, 1,000-person panel, analysed by WARC): four-week attention — **Business Mail 150s, Direct Mail 108s, Partially Addressed Mail 65s**; **63% "claimed" mail attracted their undivided attention**.

**Limits.** LTME is a proprietary Neuro-Insight metric; it is not independently validated against sales. The "63%" is claimed self-report, which is the weakest possible measure of attention. Both studies exist to sell mail. **Where they are useful:** the *relative ordering* is consistent across three independent labs on three continents (physical > digital for memory), which is more than can be said for the response-rate literature.

### 2.4 What the neuroscience actually licences us to say
- ✅ "Physical mail is encoded into memory more strongly than the same message on screen." Defensible, replicated across three funders.
- ✅ "Mail requires less cognitive effort to process." Defensible (Canada Post; consistent with the print-vs-screen reading literature).
- ❌ "Mail is 20% more persuasive" / "drives 20% more action." **Not defensible.** No study here measured an action.
- ❌ "Neuroscience proves postcards work." **The postal operator's own study found the postcard was the worst physical format tested.**

---

## 3. Envelope vs no envelope; teaser copy

| Question | Evidence | Number | Grade |
|---|---|---|---|
| Envelope vs postcard, on getting a response | Cochrane 2009: double postcard vs one page | **OR 0.47 (0.34–0.66)** against the postcard | [PRIMARY DATA] single RCT, n=600 |
| Envelope vs postcard, on brain response | Canada Post 2015 | envelope 1.40 vs postcard 0.90 | [PRIMARY DATA] postal-funded lab |
| **Brown vs white envelope** | Cochrane 2009, 5 trials, 8,637 participants | **OR 1.23 (0.81–1.87) — no effect** | [PRIMARY DATA] |
| **Window vs regular envelope** | Cochrane 2009 | **OR 0.96 (0.61–1.49) — no effect** | [PRIMARY DATA] |
| **Larger envelope vs standard** | Cochrane 2009, 1 trial, n=1,200 | **OR 0.93 (0.74–1.17) — no effect** | [PRIMARY DATA] |
| **Hand-written address vs printed** | Cochrane 2009, 7 trials, 5,091 participants | **OR 1.25 (1.08–1.45)**, I²=14% | [PRIMARY DATA] — one of the most robust findings in the set |
| **Hand-written signature on the letter** | Cochrane 2009, 14 trials, 15,006 participants | **OR 1.24 (1.08–1.41)** | [PRIMARY DATA] |
| **Organisation's name printed on the envelope** (university-branded vs plain) | Cochrane 2009, 1 trial, n=500 | **OR 0.88 (0.61–1.28) — no effect** | [PRIMARY DATA] |
| **Teaser copy on the envelope** | Cochrane 2009 | **OR 3.08 (1.27–7.44)** | [PRIMARY DATA] but **a single trial, n=190**, CI spans a 6-fold range |
| Teaser copy "+25–50%, +5–25% for back-of-envelope copy" | [cdmginc.com](https://cdmginc.com/2025/08/05/the-little-known-envelope-trick-that-can-skyrocket-your-direct-mail-response-by-25-50/), 2025 | — | **[VENDOR CLAIM]** — a direct mail agency, no test data shown |
| "Blind envelopes work best on cold prospects, teasers on house files" | Multiple agency blogs | — | **[UNSOURCED]** folklore, though it is at least *consistent* with the Cochrane pattern that relevance-signalling helps people who already have a reason to open |

**Reading it honestly.** The teaser OR of 3.08 is the most-cited number in this space and it rests on **190 people in one study**. It is the weakest evidence in the Cochrane review and is presented as if it were the strongest. The genuinely well-supported envelope findings are boring: **hand-address it, hand-sign it, and stop spending money on envelope colour, windows, size and stock.**

The "looks personal vs looks like junk" trade-off has a clean resolution in this data: the things that make an envelope look *personal* (hand-addressing, hand signature) work; the things that make it look *designed* (colour, branding, larger format, heavier stock) do not.

---

## 4. Long-form vs short-form

This splits cleanly along a line the marketing literature refuses to draw: **asking someone to do work** vs **selling them something**.

**When you are asking for effort, shorter wins — decisively.**
- Cochrane 2009, **56 trials, 60,119 participants**: shorter questionnaires **OR 1.64 (1.43–1.87)**. [PRIMARY DATA]
- Edwards 2002 BMJ (292 RCTs, 258,315 participants) put the same effect at **OR 1.86 (1.55–2.24)**. [PRIMARY DATA]
- Single-sided vs double-sided: **OR 1.22 (1.01–1.47)** for single-sided. [PRIMARY DATA]

**When you are selling something considered and expensive, long-form is claimed to win — but the evidence is trade folklore.**
- "In head-to-head tests, the package with a six or eight page letter wins time and time again"; "long-form sales letters (4–16 pages) consistently outperform short letters for cold lists and complex offers" — [mccarthyandking.com](https://www.mccarthyandking.com/how-long-should-a-letter-be/), [robpalmer.com](https://robpalmer.com/blog/long-form-copy-vs-short-form-copy) **[VENDOR CLAIM / practitioner assertion]**. No underlying dataset, no sample sizes, no losing tests reported. The "MECLABS 2004 series" citation circulates without a retrievable report.

**The one piece of real evidence for long-form-to-households is Opower**, and it is excellent:
- Allcott (2011) *J Public Econ*; Allcott & Rogers (2014) *AER* 104(10):3003–3037. **[PRIMARY DATA — independent academic RCT]**
- A **multi-page, personalised, data-dense report mailed repeatedly to homeowners about their own house**. 600,000+ households randomised across 12 utilities; 234,000 in the persistence sub-trials; 6.2M households receiving reports by 2013.
- Sustained **1.4–3.3%** behaviour change. **No habituation after 60 consecutive months.** After reports stop, effects decay only **10–20% per year** — regulators had been assuming zero persistence and were understating cost-effectiveness by more than 2×.

Opower is not a sales letter, but it is exactly our structure: recurring, addressed, personalised to the dwelling, data-led, no hard ask. It is the strongest evidence in this document that **a genuinely informative recurring homeowner report changes behaviour and does not wear out.**

**And the strongest evidence on *content* design comes from a randomised mail field experiment, not a marketing blog:**
- Bertrand, Karlan, Mullainathan, Shafir & Zinman (2010), *What's Advertising Content Worth?*, **QJE 125(1):263–306**. A South African lender randomised advertising content, price and deadline **simultaneously** across a direct mail campaign. **[PRIMARY DATA — independent academic RCT]**
- **Showing *fewer* example loans**, not suggesting a use for the loan, or including a photo each increased demand by **as much as a 25% cut in the interest rate**.
- Conclusion of the paper: content persuades **"peripherally" — by appealing to intuition rather than reason.**
- Two lessons that survive translation to us: **(a) reducing the number of options shown increased response** — one idea per panel is empirically supported, not just a design cliché; **(b) which feature mattered was not predictable in advance**, which is an argument for building the mail sequence to be testable from day one.

---

## 5. Long-lived / keepsake assets — fridge magnets, calendars, notepads

**Verdict: this is entirely vendor claim and anecdote. There is no measured evidence.**

What is circulated:
- "78% of recipients can identify the brand on a magnet received more than 12 months prior"; "retention rate increase around 70%" — [carsigns.com](https://www.carsigns.com/blogs/marketing-tips/are-branded-fridge-magnets-worth-the-investment) **[VENDOR CLAIM — a company that sells magnets]**. No study, no sample, no methodology, no publication.
- "Magnets stay on the fridge for years, driving referrals" — [trulyengaging.com](https://www.trulyengaging.com/blog/maximizing-roi-how-magnets-can-boost-your-real-estate-marketing-efforts) **[VENDOR CLAIM]**.
- I could locate **no** randomised test, no controlled holdout, and no independent panel measurement of magnet-driven response anywhere.

**The nearest real measurement is against the magnet's premise, not for it.** JICMAIL's panel (1,100 UK households, Kantar-run) tracks *"Put it on display (e.g. on a fridge, noticeboard)"* as one of its explicit physical actions — so the behaviour is real and measurable — but published numeric values for that action were not obtainable. What *is* published is the counterweight:

- **Item lifespan** ("days between first interaction and being discarded or filed away"): **Direct Mail 7.6–7.8 days**, Business Mail 8.9–9.1, Partially Addressed 6.7–7.3, **Door Drops 5.5–5.6 days**. [PRIMARY DATA — [JICMAIL Q1 2025/Q1 2026 via Post-Hub](https://www.post-hub.co.uk/resources/news/jicmail-direct-mail-attention-reaches-new-high)]
- **Item reach 1.14 people; frequency 4.43 interactions; attention 145 seconds** across 28 days for direct mail.

So the honest framing is: **an ordinary mail piece is gone in about a week.** The entire theoretical case for a magnet is that it defeats that 7.6-day clock and is still present at an unpredictable future trigger (the moment a homeowner decides to sell). That is a *coherent* hypothesis — it is exactly the availability logic that makes Opower's recurring cadence work — but it is a hypothesis, not a finding. **Anyone who tells you magnets have a measured response rate is quoting a magnet vendor.**

---

## 6. QR codes and PURLs

| Claim | Source | Grade |
|---|---|---|
| **82% of marketers who track direct mail response now use online tracking (QR codes / specific URLs)** — up from 67% | ANA RRR 2023, Chart 39, N=39 | [PRIMARY DATA] small base, but this is a usage stat not a performance stat, so it's more trustworthy than the rest of the report |
| "QR scan rates on direct mail 4–10%" | [linkbreakers.com](https://linkbreakers.com/help/article/qr-code-scan-rate-benchmarks-by-industry), 2026 | **[VENDOR CLAIM]** — QR platform vendor |
| "41% of people are likely to scan a QR code on direct mail" | [lettrlabs.com](https://www.lettrlabs.com/post/direct-mail-stats-2025) | **[VENDOR CLAIM]** — stated intent, not behaviour; treat as ~0 |
| "Campaigns with QR codes see roughly 9% higher response" | vendor aggregation | **[UNSOURCED]** |
| "PURLs convert 2–4× generic landing pages"; "adding a PURL increases response 20%" | [mailpro.org](https://www.mailpro.org/post/purl-qr-code-direct-mail-tracking/), [linemark.com](https://www.linemark.com/personalized-urls-purls-for-direct-mail-the-2026-strategic-guide/) | **[VENDOR CLAIM]** — both sell PURL services |
| **QR codes were scanned more often when the physical piece arrived first, followed by an email** | USPS OIG 2017 field study | [PRIMARY DATA] but the report states the field results are **"not statistically significant"** |

**Honest position.** There is no credible public benchmark for QR scan rates on addressed mail. Every number in circulation comes from a company selling QR or PURL software. The *one* thing that is well-evidenced and directly relevant is from JICMAIL: **9.2% of Business Mail, Direct Mail and Door Drops prompted a visit to an advertiser website** in Q2 2025, a five-year high, and **5.9% prompted an account look-up** ([Whistl/JICMAIL, 2025](https://www.whistl.co.uk/insights/jicmail-mail-driven-digital-interactions-reach-five-year-high)) — that is a measured panel figure for mail→web behaviour of any kind, and it is the right order of magnitude to plan against. It is not a QR scan rate.

**Design implication that *is* supported:** Bertrand et al. found that **reducing the number of choices shown** raised response as much as a 25% price cut. One QR code, one destination, one sentence saying what is behind it. Not three codes for three things.

---

## 7. Design fundamentals — what the RCTs say

All from Edwards et al., *Methods to increase response to postal and electronic questionnaires*, Cochrane Database of Systematic Reviews (2009, MR000008.pub4; updated 2023) — [full text PDF](https://researchonline.lshtm.ac.uk/id/eprint/5119/1/Edwards_et_al-2009-The_Cochrane_library.pdf). **[PRIMARY DATA — the largest independent body of randomised evidence on mail design that exists.]**

**⚠ Domain caveat, stated once and applying throughout:** these trials measure *compliance with a request to return a form*, not *purchase of a considered service*. The mechanism (get it opened, get it read, get it acted on) overlaps heavily; the outcome does not. Treat effect *directions* as strong and effect *sizes* as indicative.

### Works (odds ratio, 95% CI, trials/participants)
| Treatment | OR | n |
|---|---|---|
| Shorter document | **1.64 (1.43–1.87)** | 56 trials / 60,119 |
| Special/recorded delivery | **1.76 (1.43–2.18)** | 15 trials / 18,931 |
| Assurance of confidentiality | **1.33 (1.24–1.42)** | — |
| Hand-written address label | **1.25 (1.08–1.45)** | 7 trials / 5,091 |
| Hand-written signature on letter | **1.24 (1.08–1.41)** | 14 trials / 15,006 |
| Stamped **return** envelope vs franked return | **1.24 (1.14–1.35)** | — |
| Single-sided vs double-sided | **1.22 (1.01–1.47)** | 4 trials / 4,966 |
| Personalisation of materials | **1.14 (1.07–1.22)** | 58 trials / 60,184 |
| First-class outward postage | **1.11 (1.02–1.21)** | 2 trials / 8,300 |
| From a university rather than government/commercial sender | **1.32 (1.13–1.54)** (Edwards 2002) | 14 trials / 21,628 |

### Does **not** work — no evidence of effect
| Treatment | OR | n |
|---|---|---|
| **Stamp vs franking on the OUTGOING envelope** | **0.95 (0.88–1.03)** | 6 trials / 13,964 |
| Brown vs white envelope | 1.23 (0.81–1.87) | 5 trials / 8,637 |
| Coloured paper | 1.04 (0.99–1.10) | 14 trials / 41,421 |
| Coloured ink | 1.16 (0.95–1.42) | 3 trials / 7,040 |
| Coloured letterhead | 1.08 (0.91–1.28) | 2 trials / 2,356 |
| **High-quality / thicker paper** | **0.80 (0.60–1.06)** — trends *negative* | 2 trials / 1,039 |
| Booklet vs stapled pages | 1.10 (0.99–1.23) | 3 trials / 5,681 |
| Larger paper size | 0.88 (0.56–1.39) | 2 trials / 2,145 |
| Larger font | 1.26 (0.87–1.82) | 1 trial / 650 |
| Including a picture | 1.07 (0.76–1.53) | 4 trials / 3,710 |
| **Including the recipient's name or ID number as an "identifying feature"** | **1.12 (0.82–1.52)** | 8 trials / 4,134 |
| Logo repeated across the mailing pack | 0.92 (0.72–1.18) | 1 trial / 1,000 |
| Window envelope | 0.96 (0.61–1.49) | — |
| Commemorative stamps on return envelope | 0.92 (0.81–1.06) | 5 trials / 5,461 |
| Sender's organisation printed on the envelope | 0.88 (0.61–1.28) | 1 trial / 500 |
| Mailing on a Monday vs Friday | 0.83 (0.58–1.17) | 1 trial / 504 |

### Actively harmful
| Treatment | OR |
|---|---|
| Double postcard instead of one page in an envelope | **0.47 (0.34–0.66)** |
| Adding a second form for another household member | **0.67 (0.60–0.76)** |
| Sending a supplement alongside the main piece | 0.86 (0.70–1.07) |

### The one that should worry us: personalisation has a ceiling and a cliff
- Cochrane: personalisation helps, but only **OR 1.14** — and merely *printing the person's name/ID* does **nothing** (OR 1.12, CI crosses 1). Personalisation only pays when it changes the *content*, not the salutation.
- Gerber, Green & Larimer (2008) *APSR* 102(1):33–48 — 180,000 Michigan households randomised. **[PRIMARY DATA]** Mailing a household **its own public voting record: +4.9pp turnout. Adding the neighbours' records: +8.1pp.** The most powerful mail ever measured in the GOTV literature works by showing people their own data and their neighbours'. Green, McGrath & Aronow's meta-analysis puts a generic GOTV mailing at **0.16pp** and a social-pressure mailing at **2.85pp** — an ~18× gap driven purely by content.
- **And the backlash is documented in the same paper:** many households receiving the neighbours' records phoned in to demand removal from the list. Christopher Mann's follow-up (*Is There Backlash to Social Pressure?*, 2010) exists specifically because this is a known hazard.
- Peer-reviewed 2025 experiment (3×2, n=360, *Behavioral Sciences*, [doi 10.3390/bs15101323](https://doi.org/10.3390/bs15101323)) **[PRIMARY DATA]**: moving from *contextual* personalisation to *PII-based* personalisation crosses an intrusiveness threshold under high situational privacy concern, and response flips negative.

**This is the sharpest constraint on our product.** Our differentiator is mailing a homeowner analysis of *their* address. That is precisely the treatment with the largest measured effect **and** the largest measured backlash. The line between the two, in the evidence, is whether the data is *publicly-sourced and about the property* (works) or *inferred and about the person* (backfires).

---

## 8. Australia-specific: formats, tiers and what they do to design

All figures from the **Australia Post Post Charges Guide, July 2026** — [official PDF](https://auspost.com.au/content/dam/auspost_corp/media/documents/post-guides/post-charges-guide-ms11.pdf) **[PRIMARY DATA]**

### 8.1 The size classes that govern every design decision
| Size | Examples | Max weight | Max dimensions | **Max thickness** |
|---|---|---|---|---|
| Small | DL, C6 | 125 g | 130 × 240 mm | **5 mm** |
| Small Plus | C5 | 125 g | 162 × 240 mm | **5 mm** |
| Large | C4, B4 | 500 g | 260 × 360 mm | **20 mm** |

Applies to PreSort, Promo Post, Charity Mail, Imprint/Metered, Print Post, Reply Paid and Unaddressed Mail.

### 8.2 Addressed bulk pricing (per item, GST-inclusive, barcode direct tray)

**Promo Post — Regular timetable only. Minimum lodgement 4,000 barcoded letters. For articles "promotional in nature", pre-sorted.**
| Size | Same state | Other state | Barcode residue | Unbarcoded |
|---|---|---|---|---|
| Small | **$0.825** | $0.860 | $0.905 | $1.630 |
| Small Plus (C5) | **$1.100** | $1.160 | $1.405 | $2.615 |
| Large 0–125 g | **$1.560** | $1.635 | $2.045 | $3.260 |
| Large 125–250 g | **$2.060** | $2.225 | $2.655 | $4.545 |

**PreSort Letters — Regular timetable, same state** (min 300 machine-addressed sorted items)
| Size | Regular same state | Priority same state |
|---|---|---|
| Small | $1.530 | $2.070 |
| Small Plus | $1.895 | $2.740 |
| Large 0–125 g | $2.640 | $3.640 |
| Large 125–250 g | $3.525 | $4.525 |
| Large 250–500 g | $4.545 | $5.545 |

**Unaddressed Mail (letterbox drop)**
| Weight | Standard same state | Standard other state | Premium same state |
|---|---|---|---|
| ≤ 50 g | **$0.405** | $0.470 | $0.516 |
| 50–100 g | $0.685 | $0.835 | $0.874 |
| (heavier class) | $0.635 / $0.945 | $0.718 / $1.100 | $0.809 / $1.206 |

Over 100 g: contact Australia Post. *Regular* = must target all delivery points in the locality; *Select* = may exclude.

**Basic Postage Rate** rises **$1.70 → $1.85 from 1 September 2026** (ACCC did not oppose) — [ACCC](https://www.accc.gov.au/by-industry/postal-services/postal-services-price-notification-and-monitoring/australia-post-letter-pricing-2025). PreSort/Print Post prices also rising from mid-2026.

### 8.3 What these constraints actually do to the design
1. **Promo Post is ~46% cheaper than PreSort for the same envelope** ($1.100 vs $1.895 for C5 same-state). The cost is the 4,000-piece minimum lodgement and Regular-only delivery. For a three-suburb homeowner programme this is easily met and is the correct rate class.
2. **Unbarcoded C5 costs $2.615 vs $1.100 barcoded — a 138% penalty.** Address hygiene and barcoding is the largest single cost lever in the entire programme, larger than any creative decision in this document.
3. **The 5 mm thickness ceiling on Small and Small Plus is the binding constraint on anything "lumpy."** A magnet (typically 0.5–0.85 mm) fits inside a C5 within 5 mm and 125 g. Almost nothing else does. A genuine dimensional mailer forces you into **Large** (20 mm) at $1.560+ — still cheap by international standards.
4. **A C4 multi-page report costs only ~42% more postage than a C5 letter** ($1.560 vs $1.100, same state, ≤125 g). Given that the Cochrane data says paper stock and binding buy nothing, **page count and physical size are cheap; the money should go to data quality, not production values.**
5. **"No Junk Mail" stickers block unaddressed mail but not addressed mail.** Australia Post instructs posties not to deliver unaddressed material to those letterboxes, and delivers only **~10% of all unaddressed mail** in Australia — the rest goes via operators who may ignore the sticker entirely ([Australia Post](https://auspost.com.au/receiving/mail-redirection-mail-hold/junk-mail)). **[PRIMARY DATA]** This is a decisive structural argument for addressed over unaddressed: an unaddressed drop has an unmeasurable, self-selected hole in its coverage exactly where the engaged, organised households are.
6. **Opt-out for addressed advertising** runs through the **ADMA "Do Not Mail" register**, binding on ADMA members only. Suppression against it is a compliance requirement to build into the pipeline before the first send.

---

## 9. Design rules we can defend with evidence

1. **Use an addressed envelope, not a postcard.** Cochrane: double postcard vs one page in an envelope **OR 0.47**. Canada Post's own postal-funded neuroscience: postcard **0.90**, the worst physical format and below email-on-smartphone. Two independent methodologies, same direction.
2. **Hand-address the envelope where volume permits.** **OR 1.25 (1.08–1.45)**, 7 trials, low heterogeneity — one of the cleanest findings in the review.
3. **Hand-sign the letter.** **OR 1.24 (1.08–1.41)**, 14 trials.
4. **Use Promo Post indicia and spend nothing on stamps.** Stamp vs franking on the *outgoing* envelope: **OR 0.95 (0.88–1.03)** across 6 trials and 13,964 participants — a well-powered null. Save the stamp for a business-reply device, where it *does* work (**OR 1.24**).
5. **Keep each piece short and single-purpose.** Shorter document **OR 1.64**; single-sided **OR 1.22**; and Bertrand et al.'s randomised finding that **showing fewer options raised demand as much as a 25% price cut.** One idea per panel is empirically supported.
6. **Make the personalisation about the *property*, using publicly-sourced data — never about the *person*.** Gerber/Green: own-record mail **+4.9pp**, neighbour-record mail **+8.1pp**, and documented opt-out backlash from the latter. The 2025 personalisation-backfire experiment locates the cliff precisely at PII-based personalisation.
7. **Repeat the send.** JICMAIL: repeat cold DM achieves **2.5× the response rate and +37% ROI** vs a first send. Opower: **no habituation across 60 consecutive months**, and effects persist after the mail stops (10–20%/yr decay). Recurrence is the best-evidenced lever available to us — better than any format choice.
8. **State a confidentiality/data-provenance assurance explicitly.** **OR 1.33 (1.24–1.42)**. Cheap, and doubly necessary given rule 6.
9. **Barcode and sort everything.** 138% postage penalty for unbarcoded C5. Not a design rule, but it dwarfs every design rule.
10. **Prefer addressed to unaddressed** — not on response rate alone (0.9% vs 0.5%, closer than expected once cost is netted off) but because unaddressed cannot carry the recipient's address, and because "No Junk Mail" stickers create a non-random coverage hole.
11. **Build one tracked destination per piece and instrument it from send #1.** Bertrand et al.'s deeper finding is that *which* feature mattered was not predictable in advance. The literature will not tell us; only our own holdout will.

---

## 10. Design beliefs that are actually folklore

1. **"Oversized envelopes pull the highest response, postcards 5.7%, letters 4.3%."** From the 2018 DMA report, endlessly re-dated. The 2023 ANA report **explicitly could not compute response by format** and told readers not to use its data as benchmarks. Anything citing "ANA/DMA 2025 by format" is citing a document that does not exist.
2. **"Direct mail gets a 4.4% response rate."** Self-reported by ~26 marketers, ~21% of whom had actual metrics. JICMAIL's 1,659 real cold-mail campaigns say **0.9%** — a 12× discrepancy. Plan against 0.9%.
3. **"Teaser copy lifts response 25–50%."** The only randomised evidence is **one trial, n=190, OR 3.08 with a CI of 1.27–7.44.** Testable, not knowable.
4. **"Real stamps beat franking."** **OR 0.95 (0.88–1.03)** on outgoing mail, 6 trials, ~14,000 participants. This is a well-powered null and one of the most confidently wrong beliefs in the trade.
5. **"Heavier stock signals quality and lifts response."** **OR 0.80 (0.60–1.06)** — if anything it trends the wrong way.
6. **"Colour lifts response."** Coloured paper 1.04. Coloured ink 1.16 (CI crosses 1). Coloured letterhead 1.08. Three separate nulls. (The 2002 review's OR 1.39 for coloured ink did not survive the 2009 update — a useful reminder that this literature updates.)
7. **"Use their name."** Printing an identifying feature: **OR 1.12 (0.82–1.52)** — nothing. Personalisation works only when it changes the *substance*.
8. **"Blue ink on hand-addressed envelopes because black looks like junk mail."** Pure vendor advice, from companies selling handwriting services. The hand-addressing is evidenced; the ink colour is not.
9. **"Handwritten envelopes get 99% open rates and 300% response lifts."** Sourced entirely to handwritten-mail vendors. The real, replicated number is **+25% odds**.
10. **"Dimensional mail gets 8.5–20% response."** No retrievable primary source; the ANA citation used to support it says the opposite. Dimensional's only credible support is a **30-person EEG cell** with no behavioural outcome.
11. **"Scented mail works."** Best score in Canada Post's study (1.75) — from **30 people, one glance, no measured action.** Do not build anything on this.
12. **"Fridge magnets have 78% brand recall after 12 months."** Magnet vendor, no study. See §5.
13. **"QR codes on mail get 4–10% scan rates."** QR software vendors. The only measured adjacent figure is JICMAIL's **9.2% of mail prompting any website visit**.
14. **"Mail is 20% more persuasive than digital / drives more action."** Canada Post measured EEG frontal asymmetry, not action. The USPS OIG's actual field test of this was **"not statistically significant"** by its own admission.
15. **"Send on a Tuesday / never land on a Monday."** OR 0.83 (0.58–1.17). Nothing.
16. **"Put your branding on the envelope so they know it's from you."** OR 0.88 (0.61–1.28). Nothing — and it conflicts with rule 2, which does work.

---

## 11. Source ledger

**[PRIMARY DATA — independent]**
- Edwards PJ et al., *Methods to increase response to postal and electronic questionnaires*, Cochrane DSR 2009 (MR000008.pub4), upd. 2023 — https://researchonline.lshtm.ac.uk/id/eprint/5119/1/Edwards_et_al-2009-The_Cochrane_library.pdf
- Edwards P et al., *Increasing response rates to postal questionnaires: systematic review*, BMJ 2002 (292 RCTs, 258,315 participants) — https://pubmed.ncbi.nlm.nih.gov/12016181/
- Bertrand M, Karlan D, Mullainathan S, Shafir E, Zinman J, *What's Advertising Content Worth?*, QJE 125(1):263–306, 2010 — https://academic.oup.com/qje/article/125/1/263/1880334
- Allcott H, *Social norms and energy conservation*, J Public Econ, 2011 — https://eml.berkeley.edu/~saez/course131/allcott2011.pdf
- Allcott H & Rogers T, *The Short-Run and Long-Run Effects of Behavioral Interventions*, AER 104(10):3003–3037, 2014 — https://www.aeaweb.org/articles?id=10.1257/aer.104.10.3003
- Gerber A, Green D, Larimer C, *Social Pressure and Voter Turnout*, APSR 102(1):33–48, 2008 — https://isps.yale.edu/research/publications/isps08-001
- Mann CB, *Is There Backlash to Social Pressure?*, 2010 — https://www.christopherbmann.com/wp-content/uploads/2014/11/Mann-Is-There-Backlash-Against-Social-Pressure-Final-April-20-2010.pdf
- *Triggering the Personalization Backfire Effect*, Behavioral Sciences 2025 — https://doi.org/10.3390/bs15101323
- Australia Post, *Post Charges Guide*, July 2026 — https://auspost.com.au/content/dam/auspost_corp/media/documents/post-guides/post-charges-guide-ms11.pdf
- ACCC, *Australia Post letter pricing 2025–26* — https://www.accc.gov.au/by-industry/postal-services/postal-services-price-notification-and-monitoring/australia-post-letter-pricing-2025

**[PRIMARY DATA — mail-industry-funded, methodology disclosed]**
- JICMAIL Response Rate Tracker 2025 (3,800 campaigns, 15 organisations) — https://www.jicmail.org.uk/data/response-rate-tracker-2025/ ; figures via https://www.citipostmail.co.uk/direct-mail-powers-customer-acquisition-2025-jicmail-insights/
- JICMAIL panel metrics & definitions (1,100 households, Nielsen AdIntel circulation) — https://www.jicmail.org.uk/about-jicmail/useful-definitions/ ; https://www.post-hub.co.uk/resources/news/jicmail-direct-mail-attention-reaches-new-high
- JICMAIL Q2 2025 digital interactions — https://www.whistl.co.uk/insights/jicmail-mail-driven-digital-interactions-reach-five-year-high
- ANA, *Response Rate Report 2023* — https://www.ana.net/miccontent/show/id/rr-2024-02-ana-response-rate-report-2023 (**self-declared not benchmark data**)

**[PRIMARY DATA — postal-operator-funded, treat directionally]**
- Canada Post / True Impact, *A Bias for Action*, 2015 — https://twosidesna.org/wp-content/uploads/sites/16/2018/05/CPC_Neuroscience_EN_150717.pdf
- USPS OIG / Temple CNDM, *Tuned In: The Brain's Response to Ad Sequencing*, RARC-WP-17-004, 2017 — https://www.uspsoig.gov/sites/default/files/reports/2023-01/RARC-WP-17-004.pdf
- Royal Mail MarketReach / Neuro-Insight, *The Private Life of Mail*, 2015 — https://www.royalmailwholesale.com/mint-project/uploads/423811624.pdf
- WARC / Marketreach, *The Attention Advantage*, 2023 — https://www.marketreach.co.uk/resource/WARC-Attention-Advantage
- WARC / Royal Mail Marketreach, *Driving effectiveness with direct mail*, 2021

**[VENDOR CLAIM — do not cite as evidence]**
letterfriend.com (handwritten mail) · cdmginc.com (teaser copy) · carsigns.com & trulyengaging.com (magnets) · mailpro.org, linemark.com, postalytics.com, lettrlabs.com (PURL/QR/mail software) · linkbreakers.com, pageloot.com (QR platforms) · mccarthyandking.com, robpalmer.com (copywriting practice) · blog.crst.net (self-flagged as "directional industry guidance", not benchmarks)

---

## 12. Gaps this research could not close

- **No published numeric value for JICMAIL's "put it on display (fridge/noticeboard)" action** — the one measurement that would directly test the magnet hypothesis. Requires a JICMAIL Discovery subscription.
- **No Australian response-rate benchmark of any quality.** All real-campaign data here is UK (JICMAIL) or US (ANA). Assume UK figures transfer directionally and validate locally.
- **No independent replication of any postal-operator neuroscience result** by a non-postal funder.
- **No AU print cost quotes** — the cost-per-response figures in §1 are **postage only**. Print, personalisation and lettershop must be quoted before any format is costed properly.
- **No evidence at all on newsletters as a distinct format.** Every claim located was assertion. Opower is the closest analogue and is a report, not a newsletter.
