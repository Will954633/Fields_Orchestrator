# W1 — The Direct Mail Evidence Base

**Research date:** 2026-08-08
**Question:** What does the actual measured evidence say about direct mail response and ROI, across all industries?
**Method:** ~20 web searches; primary PDFs downloaded and text-extracted locally where the publisher's own text was retrievable (ANA 2023, Royal Mail/WARC, Canada Post, USPS Informed Delivery, Gerber & Green GOTV handbook).

**Labelling convention used throughout:**
- **[PRIMARY DATA]** — a real study or dataset with a stated methodology that I could retrieve and read.
- **[SECONDARY]** — a trade-press or industry-body report *of* a primary source, where I could not retrieve the primary itself.
- **[VENDOR CLAIM]** — a print/mail/martech vendor's marketing page.
- **[UNSOURCED]** — widely repeated, no traceable origin.

---

## 1. What we can actually rely on

| Claim | Figure | Source quality | Verdict |
|---|---|---|---|
| Cold/prospect addressed mail response rate | **0.9%** (UK, FY2025, ~5,000 campaigns) | **[PRIMARY DATA]** JICMAIL Response Rate Tracker | **Most reliable single number in this report.** Campaign-level, matchback/control-verified. |
| Warm/house addressed mail response rate | **7.2%** (FY2025); 7.9% (FY2024) | **[PRIMARY DATA]** JICMAIL | Reliable. ~8x cold. |
| Door drops (unaddressed) response rate | **0.5–0.6%** | **[PRIMARY DATA]** JICMAIL | Reliable. |
| Cold DM ROI | **£3.20** per £1; warm **£9.00–£11.50** | **[PRIMARY DATA]** JICMAIL | Reliable but self-selected contributors (see §8). |
| Cold DM CPA vs warm | Cold CPA ≈ **8x** warm CPA | **[PRIMARY DATA]** JICMAIL via WARC | Reliable directionally. |
| Repeat cold mailings beat one-offs | **2.5x** response, **+37%** ROI vs new campaigns | **[PRIMARY DATA]** JICMAIL | Strong; the single most actionable finding. |
| Direct mail lift on a *behaviour* under RCT | **+0.75 percentage points** pooled (85 studies) | **[PRIMARY DATA]** Green & Gerber GOTV meta-analysis | The honest ceiling for cold persuasion mail. |
| "Social pressure" / personally-relevant data mail | **+2.3pp** pooled; **+4.9pp** for the "Self" mailer | **[PRIMARY DATA]** Green & Gerber | The one content manipulation that reliably replicates. |
| Mail prompts a website visit | **9.4%** of *all* mail items (Q1 2026) | **[PRIMARY DATA]** JICMAIL panel | Panel self-report, but measured per-item. |
| Mail attention / dwell | **141 seconds** over **7.8 days** in home, **4.5** interactions, reaches **1.14** people | **[PRIMARY DATA]** JICMAIL panel | Reliable; diary-based. |
| ANA/DMA "direct mail gets 4.4%" | **Not in the report it is attributed to** | **[UNSOURCED]** | **Zombie statistic. Do not use.** |
| ANA/DMA "9% house / 4.9% prospect" | From the **2018** edition, superseded | **[SECONDARY]** | Stale; do not present as current. |
| ANA 2023 actual DM response rates | **15.6% house / 10.8% prospect** | **[PRIMARY DATA]** but **N=26 / N=25**, self-reported | **Implausible. Report itself disclaims it as benchmark data.** |
| Personalisation/VDP "2–3x lift" | 36% / 135% / 300% / 500% depending on who you ask | **[VENDOR CLAIM]** / **[UNSOURCED]** | **No retrievable primary source. Treat as marketing.** |
| QR scan rate on addressed mail | 1–5%, 4–10%, 10–15%, "64%" | **[VENDOR CLAIM]** | **No denominator-based primary source exists.** |
| Canada Post neuroscience findings | 21% lower cognitive load, 20% higher motivation | **[PRIMARY DATA]** but N=270, **2015**, neural proxies only | Real study; measures attention, not response. Metric has known reliability problems. |
| Informed Delivery "+37% response" | USPS marketing figure, no control group described | **[VENDOR CLAIM]** (postal operator) | Not a controlled test. |
| Australian-specific response data | **Essentially none public** | — | **We are extrapolating from UK/US throughout.** |

---

## 2. Response rates by list type, format and industry

### 2.1 The best source: JICMAIL (UK) — [PRIMARY DATA]

JICMAIL is a Joint Industry Committee — the mail equivalent of BARB for TV or ABC for print. It runs two separate instruments:

**(a) The consumer panel.** 1,100 UK nationally representative households, recruited and managed by **Kantar**, matched to UK Census. Households are split into four cohorts, each assigned one week per month. A designated household co-ordinator photographs every commercial mail item received and logs every interaction across a **28-day window**, reporting on behalf of all household members. A Technical Committee oversees methodology and Kantar runs automated anomaly detection.
Source: https://www.jicmail.org.uk/about-jicmail/methodology/ (accessed 2026-08)

**(b) The Response Rate Tracker.** Aggregated *anonymous campaign-level* data from **15 organisations** (sell-side businesses, agencies, data and technology partners), covering **~3,800 campaigns** in the 2024 dataset and **~5,000 campaigns** in the full-year 2025 dataset, with contributions reaching back to **January 2021**. Critically, the tracker states responses are "measured using **matchback, unique-tracking code, or test and control** techniques" — i.e. actual campaign measurement, not a marketer opinion survey.
Source: https://www.jicmail.org.uk/data/response-rate-tracker-2025/

**Headline benchmarks (full-year 2025, published 2026):**

| Mail type | Response rate | ROI |
|---|---|---|
| Warm Direct Mail | **7.2%** | **£9.00** (retail warm maintained £12+) |
| Cold Direct Mail | **0.9%** | **£3.20** |
| Door Drops | **0.5%** | **£2.90** |
| Partially Addressed Mail | (first year reported) | **£2.00** |

FY2024 equivalents were warm **7.9%**, cold **0.9%**, door drops **0.6%**.
Sources: https://dma.org.uk/article/jicmails-2025-response-rate-tracker-update-reveals-growing-performance-of-customer-acquisition-mail-campaigns · https://www.jicmail.org.uk/data/response-rate-tracker-2025/ · https://ipia.org.uk/jicmail-reports-continued-uplift-in-mails-digital-effectiveness-in-q1-2026-while-unveiling-the-latest-results-from-its-response-rate-tracker/

**Two further JICMAIL findings that matter more than the headline rates:**

- **CPAs from cold direct mail are typically ~8x higher than warm direct mail** to existing customers. [PRIMARY DATA via WARC] — https://www.warc.com/newsandopinion/opinion/warm-cpas-might-be-higher-than-cold-but-theres-nothing-expensive-about-customer-acquisition/en-gb/6145
- **Repeat cold DM sends achieve 37% higher ROI and 2.5x higher response rate than new campaigns**, with greater AOV and lower CPA. [PRIMARY DATA] — https://www.warc.com/content/feed/cold-direct-mail-campaigns-are-effective-when-repeated/10567

**Engagement metrics, Q1 2026 [PRIMARY DATA]:**

| Type | Interactions | Reach per item | Days in home | Attention |
|---|---|---|---|---|
| Direct Mail | 4.5 | 1.14 people | 7.8 | 141 sec |
| Door Drops | 3.0 | 1.06 | 5.6 | 57 sec |
| Business Mail | 4.8 | 1.16 | 9.1 | 182 sec |
| Partially Addressed | 4.1 | 1.09 | 6.7 | 94 sec |

**9.4% of mail items prompted a website visit** in Q1 2026 (up from 8.7% in Q1 2025). **56%** of mail-driven purchases were fulfilled online. **43%** of Direct Mail items are still in the home after four weeks (vs 12% of door drops).
Sources: https://ipia.org.uk/jicmail-reports-continued-uplift-in-mails-digital-effectiveness-in-q1-2026-while-unveiling-the-latest-results-from-its-response-rate-tracker/ · https://www.jicmail.org.uk/about-jicmail/methodology/

### 2.2 The most-quoted source is the weakest: ANA/DMA Response Rate Report

I retrieved and text-extracted the actual **ANA Response Rate Report 2023** (published Feb 2024). What it actually says is materially different from what the industry quotes.

**Methodology, in the report's own words** [PRIMARY DATA]:
> "This report is based on **self-reported data** collected using an **online survey** that was deployed from **July through November 2023**. The survey was promoted to **ANA members and members of the Demand Metric community**. During this period, **250 responses** were qualified and complete enough for inclusion… **Study participants received an incentive** for completing the survey."

And the report's own disclaimer:
> "The ideal response option to this question is 'Actual metrics,' but those choosing this response ranged from **5 percent to 50 percent, with an average of 21 percent**… For these reasons, **the report data should not be considered benchmark data, but used for informational purposes only.**"

So: ~79% of the figures in the world's most-cited direct mail benchmark are the respondent's *estimate*, from a self-selected, incentivised sample of marketing-association members.

**The actual direct mail numbers (Table 7, ANA RRR 2023)** [PRIMARY DATA, tiny N]:

| | House file | Prospect file |
|---|---|---|
| CPM | $201.86 (N=31) | $210.57 (N=26) |
| **Response rate** | **15.6% (N=26)** | **10.8% (N=25, flagged "small base")** |
| Cost per conversion | $24.48 (N=26) | $97.74 (N=25*) |
| ROI | 160.9% (N=27) | 33.7% (N=22*) |

A 15.6% response rate on house-file mail is not a credible market-wide figure — it is roughly **double** JICMAIL's warm figure measured across 5,000 real campaigns, and it rests on **26 self-reported answers**. The report is candid that "due to the very small number of responses by campaign type… as well as list and format type… there was insufficient data to report on response rates and other metrics at this level of granularity" — i.e. **there is no format-level (postcard vs letter vs oversized) response rate data in the 2023 report at all.**

**Format usage (not performance)** — house lists: postcard 76%, letter-sized envelope 48%, catalog 36%, dimensional 20%, oversized 16% (N=25*). Prospect lists: letter-sized 67%, postcard 62%, catalog 48%, oversized 29%, dimensional 14% (N=21*). These are *adoption* percentages, not response rates.

Cross-media ROI table (ANA 2023): direct mail to house lists 161%, email to house lists 44%, paid search branded 38%, digital display 23%, social 21%, SMS 20%. Overall campaign CPA across all media averaged $143.74 (N=90), range $1–$800.

Source (full PDF, retrievable mirror): https://theworldsgreatestmarketing.com/wp-content/uploads/2025/04/rr-2024-02-ana-response-rate-report-2023.pdf · ANA landing page (403s to automated fetch): https://www.ana.net/miccontent/show/id/rr-2024-02-ana-response-rate-report-2023

### 2.3 The "4.4%" figure is a zombie statistic — [UNSOURCED]

This is a finding in its own right. Dozens of vendor pages currently assert *"the average direct mail response rate is 4.4%, according to the 2025 ANA/DMA Response Rate Report"* (e.g. https://www.mailpro.org/post/direct-mail-response-rates/, https://blog.crst.net/direct-mail-response-rates/, https://www.mydoceo.com/blog/direct-mail-response-rates-2026).

I searched the full extracted text of the actual ANA Response Rate Report 2023. **The strings "4.4%" and "2.7%" do not appear anywhere as a direct mail response rate.** The only DM response rates in that report are 15.6% and 10.8%.

Tracing it back: "4.4%" is variously attributed to the DMA's **2016** and **2017** Response Rate Reports; "9% house / 4.9% prospect" comes from the **2018** ANA/DMA edition (https://www.ana.net/miccontent/show/id/rr-2018-ana-dma-respose-rate). Neither is current, and neither matches the figures in the most recent edition I could actually read. The number has become detached from any retrievable source and is now recycled with a fabricated recent-sounding citation.

**Practical consequence: any plan, budget or pitch built on "industry average 4.4%" is built on nothing.**

### 2.4 Industry breakdowns

Thin. The ANA 2023 report explicitly abandoned format- and sector-level DM breakdowns for insufficient sample. JICMAIL publishes some sector splits (retail cold/warm DM response rates both grew, +21% and +26% YoY respectively in the 2025 dataset) but the granular sector table sits behind JICMAIL Discovery and I could not retrieve it. **Real-estate-specific direct mail response data is entirely vendor-blog recycling of the ANA/DMA numbers** — every "real estate direct mail gets 3.32%" or "4–9% for agents" page I checked traces back to the same unsourced DMA figures, not to real estate campaign data. See §7.

---

## 3. Cost per acquisition vs digital

**What is solid:**
- **Cold DM CPA ≈ 8x warm DM CPA** [PRIMARY DATA, JICMAIL]. This is the dominant cost fact and it is a ratio, which travels across currencies and markets better than an absolute figure does.
- **Cold DM ROI £3.20 vs warm £9.00–£11.50** [PRIMARY DATA, JICMAIL FY2025].
- ANA 2023 cross-campaign CPA averaged **$143.74**, ranging $1–$800 (N=90, all media, self-reported) [PRIMARY DATA, low quality].
- ANA 2023 DM cost-per-conversion: **$24.48 house / $97.74 prospect** (N=26/25) [PRIMARY DATA, tiny N].

**What is not solid:** essentially every "direct mail beats digital on CPA" claim. The comparison is structurally unfair in both directions — DM CPA is usually computed via matchback over a 30–90 day window (which overstates it, §6) while digital CPA is usually last-click (which understates assisted value). I found no independent study that puts mail and digital CPA on a like-for-like incrementality footing.

**Australian cost inputs** (for building our own CPA model rather than importing someone else's):
- Basic Postage Rate rose from **$1.50 to $1.70** effective 17 July 2025 (a 13% increase on reserved ordinary letters). Australia Post has lodged a draft notification to take the small-letter BPR to **$1.85** from mid-to-late 2026. [PRIMARY DATA — ACCC] https://www.accc.gov.au/by-industry/postal-services/postal-services-price-notification-and-monitoring/australia-post-letter-pricing-2025
- **Clean Mail was discontinued 1 July 2025**; that volume now lodges as PreSort Letters unbarcoded. A Letters Lodgement Correction Fee was introduced 3 March 2025. [PRIMARY DATA] https://auspost.com.au/disruptions-and-updates/pricing-updates/2025-product-changes

At a 0.9% cold response rate, every 1,000 addressed pieces yields ~9 responses. **The postage line alone at $1.70 is $1,700 per 1,000, i.e. ~$189 per response before print, data, creative or any conversion step.** That is the arithmetic the whole programme has to survive.

---

## 4. Personalisation and Variable Data Printing — the "2–3x lift" is not traceable

**Verdict: [VENDOR CLAIM] / [UNSOURCED]. I could not find a primary source, and the secondary figures contradict each other by an order of magnitude.**

What is in circulation:
- "InfoTrends: personalised DM yields response rates **36% higher**"
- "Keypoint Intelligence (formerly InfoTrends): **up to 135% higher**"
- "PODi: personalised pieces are **over 300% higher**"
- "**6% vs 2%** — a 3x lift — according to the ANA"

Sources for the above are all vendor pages: https://mailingcenter.net/why-variable-data-printing-is-key/ · https://blog.crst.net/personalized-direct-mail-variable-data-printing/ · https://www.shawmutdelivers.com/blog/why-it-pays-to-personalize-with-variable-data-printing/ · https://gonextpage.com/variable-data-printing-guide/

Three problems:
1. **No retrievable primary.** InfoTrends/Keypoint and PODi studies are cited without a report title, year, sample size or URL. PODi is a **print-industry consortium** — i.e. the beneficiary of the finding, not a neutral party. I could not locate any of these as retrievable documents.
2. **The "6% vs 2% per the ANA" claim is false.** The ANA 2023 report I read contains no personalised-vs-static comparison whatsoever.
3. **The spread (36% → 500%) is itself diagnostic.** Numbers that range over an order of magnitude while all claiming the same underlying phenomenon are not measurements; they are marketing.

**What *is* real about personalisation** — and it is a narrower, more specific claim:

- **[PRIMARY DATA] Munz, Jung & Alter (2020), *Marketing Science*, "Name Similarity Encourages Generosity: A Field Experiment in Email Personalization."** RCT, **N = 30,297**, DonorsChoose.org. Recipients were more likely to open, click and donate — and donated more — to teachers sharing their **surname**; a shared surname *first letter* also produced measurable generosity. https://pubsonline.informs.org/doi/10.1287/mksc.2019.1220
  → Real effect, but it is *name-similarity* in email, not VDP in print, and the effect size is nothing like 300%.

- **[PRIMARY DATA] Bertrand, Karlan, Mullainathan, Shafir & Zinman (2010), *Quarterly Journal of Economics* 125(1), "What's Advertising Content Worth? Evidence from a Consumer Credit Marketing Field Experiment."** A direct-mail field experiment by a South African consumer lender that randomised advertising *content*, loan price and offer deadline simultaneously. Finding: **content sensitivity is large relative to price sensitivity** — showing fewer example loans, not suggesting a use for the loan, or including a photo of an attractive woman each increased demand by about as much as a **25% reduction in the interest rate**. But the authors stress it was **difficult to predict ex ante which content features would matter**. https://academic.oup.com/qje/article/125/1/263/1880334
  → This is the strongest evidence that *creative content* on a mail piece has real, large, monetisable effects. It is also the strongest evidence that **you cannot guess which ones** — you have to test.

- **[PRIMARY DATA] Green & Gerber GOTV meta-analysis** (see §6): the *only* mail content manipulation that reliably replicates at scale is **showing the recipient their own data** — the "Self" mailer lifted turnout **4.9pp** against a baseline where typical mail managed **under 0.5pp**.

**Synthesis: the evidence supports "showing someone specific, personally-relevant information about themselves" — not "mail-merging their first name."** These get conflated by vendors selling VDP.

---

## 5. QR codes on mail — no honest scan-rate benchmark exists

**Verdict: [VENDOR CLAIM] throughout. There is no published, denominator-based scan rate for addressed mail from a neutral source.**

The claims found, all from vendors, all mutually inconsistent:
- "1–5% scan-through rate" — https://linkbreakers.com/help/article/qr-code-scan-rate-benchmarks-by-industry
- "4–10% typical for direct mail" — https://raminzamani.com/blog/direct-mail-qr-code-scan-rate/
- "2–3% when the scan is a commitment; 10–15% with a softer CTA" — https://www.fancircles.com/blog/how-to-reach-qr-codes-scan-rates-of-10-to-15/
- "**over 64% of recipients scanned**" (a higher-education postcard campaign) — not credible; no methodology given
- "14% industry benchmark for retail/healthcare/hospitality" — https://pageloot.com/blog/qr-code-scanning-trends-by-industry-a-breakdown/
- "41% of people are *likely to* scan a QR code on direct mail" — a **stated-intent survey**, not behaviour.

**Bitly is the largest real scan dataset and it does not answer the question.** QRCG by Bitly analysed **~2 billion real scans, Jan–Dec 2025**, and reports growth (usage +25% YoY; scan rates up 42% in Europe, 40% LATAM) and design effects (custom patterns get 2–3x the scans of plain squares). But Bitly only ever sees the **numerator**. It has no idea how many pieces were printed or mailed, so it structurally cannot produce a scan *rate*. https://bitly.com/blog/state-of-qr-code-scans-2026/ · https://www.qr-code-generator.com/blog/how-to-create-high-performing-qr-codes/

**The two closest things to a real number:**
1. **[PRIMARY DATA] JICMAIL Q1 2026: 9.4% of mail items prompted a website visit** (all mail types, all mechanisms — QR, printed URL, search, app). This is a household-panel measurement with a proper denominator. It is the best available upper bound: **if under 10% of mail items drive *any* web visit by *any* route, a QR-specific scan rate on an addressed piece cannot plausibly exceed that, and will be a fraction of it.**
2. **[PRIMARY DATA] ANA 2023: 82% of DM users track response via online tracking (QR codes / PURLs)**, up from 67% in the prior study. That is *adoption of QR as a tracking method*, not a scan rate — and it is frequently misquoted as though it were a performance figure.

**Realistic planning assumption: 1–3% scan rate on a cold addressed piece, and treat anything above that as a result to be verified, not expected.** Design so the piece works without the scan.

---

## 6. Mail + digital integration

### 6.1 USPS Informed Delivery — [PRIMARY DATA for reach, [VENDOR CLAIM] for lift]

From the USPS Informed Delivery Year in Review (April 2024 – March 2025), text-extracted from the official PDF:
- **72.9M active users** (+17% YoY)
- **45.1 billion impressions**; 7.9B campaign impressions
- **34.7% national saturation** of eligible delivery points
- **58.6% average Daily Digest email open rate** (consistently above 58%)
- **1,025,694 campaigns completed**
- **1:13** average time spent
- 94% of users satisfied/very satisfied; 93% would recommend
Source: https://www.usps.com/business/pdf/informed-delivery-year-review.pdf

The widely-quoted **"+37% response rate lift from adding Informed Delivery"** ( https://www.uspsdelivers.com/informeddelivery-calculator/ ) is a **postal operator's marketing calculator**. No control group, holdout design or sample is described. **Do not treat it as a measured lift.** Note also that Informed Delivery is US-only and has **no Australian equivalent** — it is not available to us.

### 6.2 Mail + retargeting — [VENDOR CLAIM] only

Every source I found on "direct mail retargeting lift" is a mail-tech vendor (Lob, Poplar, Amsive, LS Direct, Measured). They agree on the *right method* — a randomised holdout of 10–20% of the audience, measuring incremental conversion rate, incremental CPA and incremental ROAS — but **none publishes an independent measured lift figure**. https://www.lob.com/blog/incremental-lift-direct-mail-2024 · https://heypoplar.com/articles/a-complete-guide-to-direct-mail-attribution · https://www.measured.com/faq/optimizing-direct-mail-testing-measuring-incrementality/

### 6.3 Royal Mail Marketreach / WARC — [PRIMARY DATA with fatal selection bias]

Headline claims in circulation: campaigns with mail in the mix are **52% more likely to report ROI effects** and **43% more likely to report revenue uplifts**; 35% of mail-in-mix campaigns recorded an ROI benefit vs 23% UK average; mail adds **12% larger ROI** (Brand Science); **70% of consumers** have been driven to an online activity by mail.

I downloaded and extracted the actual report. Its stated methodology:
> "WARC's database of successful case studies is made up of campaigns that have been **entered into, or won at, competitions that award effectiveness**… This research analyses case studies from the UK that were tagged as using direct mail as the lead media or in the media mix, published by WARC **between 2016 and 2020**. **135 and 83 case studies** fit these criteria respectively."

**This is survivorship bias by construction.** The sample is, definitionally, campaigns successful enough that someone paid to enter them into an effectiveness award. There is no failure arm. A statement of the form "X% of these campaigns reported an ROI benefit" cannot be generalised to campaigns in the wild.

**Also note the dating.** Marketreach hosts this at a `2025-07` URL — https://www.marketreach.co.uk/system/files/2025-07/Marketreach_WARC_Driving_Effectiveness_with_Direct_Mail.pdf — but the document footer reads **"© Copyright WARC 2021"** and the underlying case studies are **2016–2020**. Some of its supporting data is IPA TouchPoints **2020**. It is presented as current research; it is five-to-ten-year-old data.

---

## 7. What fails — the negative evidence

This section matters more than the rest, because the mail industry does not publish it.

### 7.1 The best RCT evidence says mail barely moves behaviour — [PRIMARY DATA]

The most rigorously studied direct mail literature in existence is not in marketing — it is in political science, where mail effects have been measured by **randomised controlled trial** for 25 years, with the control group receiving nothing.

Gerber & Green's meta-analysis collects **85 distinct studies conducted 1998–2014**, derived from **220 distinct treatment/control comparisons**. Their conclusion, verbatim from the extracted handbook:

> "Pooling all mail studies together shows that sending a piece of mail to a voter increases the subject's turnout rate by **about ¾ of a percentage point**."

> "…a typical non-partisan GOTV mailing raises turnout by **less than half a percentage point**."

> "The literature gauging the turnout effects of **advocacy mailings is essentially a string of null findings**."

Specific failures in that literature:
- A study sending **up to eight mailings** found effects of ~0.5pp per additional mailer — turnout 42.2% control (N=11,596) vs 42.6% with one mailer (N=2,550), 43.3% with more.
- **Cubbison (2015): twelve mailers, no effect.**
- Advocacy mail from an abortion-rights group: null.
- Mailings boosted turnout among "prime" Democrats but not other Democrats; New Jersey samples suggest "mail did not significantly increase voter turnout."

Source: https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf (Gerber & Green, "Field Experiments on Voter Mobilization: An Overview"); book version Green & Gerber, *Get Out the Vote*, 2015.

**Why this matters for a marketing programme:** these are the only large-scale direct mail experiments with genuine no-contact control groups. They measure the *incremental* effect of mail on a behaviour. When you do that properly, mail's effect is **fractions of a percentage point** — orders of magnitude below the 4.4%/9%/15.6% "response rates" the marketing industry quotes. The difference is not that voting is harder than buying; it is that **a "response rate" is not an incremental effect.** Some of the people who respond to your mail would have acted anyway.

### 7.2 The exception that replicates — and it is a design instruction

The same literature identifies the one content approach that produces **large and reproducible** effects: **social pressure and personally-specific data**.

- Pooled across social-pressure studies: **+2.3 percentage points**.
- The **"Self" mailer** — which showed the recipient information from the voter file listing **their own** voting history, and promised a follow-up mailing reporting whether they voted — produced **+4.9pp**, roughly **ten times** a typical GOTV mailer.
- A forceful civic-duty appeal: +1.8pp.
- The "Neighbors" mailer (showing neighbours' records) produced more still.

Green, McGrath & Aronow report **0.16pp per generic GOTV mailing vs 2.85pp per social pressure mailing**. https://www.cambridge.org/core/journals/ps-political-science-and-politics/article/getting-the-message-out-why-maildelivered-gotv-interventions-succeed-or-fail/9798F335F3044B09224061598E7172E1

**The generalisable lesson: mail that tells the recipient something specific and verifiable about themselves works. Mail that makes a general appeal does not.**

Caveat the authors themselves raise: there are few true "horserace" studies holding all else constant, so some apparent message differences may reflect other varying conditions.

### 7.3 Matchback attribution systematically overstates mail

> "Matching sales back to the mail file for +/- 90 days **inevitably overstates** direct mail's impact."
> — https://gundersondirect.com/the-marketers-guide-to-direct-mail-response-attribution/ [VENDOR, but conceding against interest]

This is the mechanism by which the industry's headline numbers get inflated without anyone lying: a "response rate" counts everyone who bought within a window after receiving mail, including everyone who would have bought regardless. Only a **randomised holdout** separates the two. JICMAIL's tracker accepts matchback data alongside test-and-control data, so **even the best dataset in this report is partly contaminated by this** — its warm figures in particular, since existing customers have a high base rate of buying anyway. This is a strong argument for why **cold 0.9% is a more trustworthy number than warm 7.2%**.

### 7.4 The ANA report's own self-assessment

Repeated because it is the single most important sentence in the whole evidence base:
> "For these reasons, **the report data should not be considered benchmark data, but used for informational purposes only.**" — ANA Response Rate Report 2023

The report also concedes: "one challenge for respondents appeared to be having access to the data the survey calls for"; ROI data "proved the hardest to collect due to the low number of responses." Prior editions carried similar warnings — coverage of the DMA reports has long noted that "sample sizes were too small to measure direct response television or mobile marketing response rates" and that ROI benchmarks derive from small samples. https://www.marketingcharts.com/featured-53645 · https://adage.com/article/media/dma-snail-mail-phone-beat-digital-response-rates/235364

### 7.5 Selection bias in who answers these surveys

The mechanism, stated plainly: organisations with strong results are more likely to participate in industry surveys than those with poor results, so published benchmarks skew optimistic. (Found on vendor pages — https://blog.crst.net/direct-mail-response-rates/ — rather than in an academic critique, so **[SECONDARY]**, but it is the obvious and correct reading of the ANA methodology, which recruited **incentivised volunteers from marketing-association membership lists**.)

### 7.6 The neuroscience is real but does not measure response — and its key metric is unreliable

**Canada Post, "A Bias for Action," with True Impact Marketing** [PRIMARY DATA]. Full document retrieved and extracted.

Methodology: **270 participants split into nine groups of 30** — one group per media format. Each saw two offers. EEG (cognitive load, motivation) plus eye tracking, with pre/post surveys and post-exposure memory tests. Formats tested: postcard, envelope, 3D mailer, 3D mailer with sound, 3D mailer with scent; vs email on laptop, email on smartphone, display on laptop, display on smartphone.

Findings:
- Direct mail required **21% less cognitive effort** to process (score 5.15 vs 6.37 for digital).
- **Motivation response 20% higher.**
- **Unaided brand recall 75% (mail) vs 44% (digital)** — a 70% relative improvement.
- Mail exceeded the motivation-to-cognitive-load ratio threshold of 1.

**Four caveats that are not optional:**
1. **The document is dated July 31, 2015.** It is routinely presented as current. It predates the entire modern mobile and social advertising environment it compares mail against.
2. **N=30 per cell.**
3. **It measures neural and attention proxies, not response or purchase.** Canada Post's own framing is that motivation "is the only metric that correlates with future behaviour" — a correlation claim, not a measured behavioural outcome. No one bought anything in this study.
4. **The metric underpinning "motivation" is frontal alpha asymmetry, which the peer-reviewed literature identifies as the *least* reliable EEG measure.** A large-scale short-term reliability investigation across distinct EEG systems found "the **lowest reliability level** was found for frontal alpha-asymmetry," warranting caution in applied and academic use — asymmetry scores are difference scores carrying measurement error from two measurements. https://link.springer.com/article/10.1007/s00429-021-02399-1 A systematic review of 174 neuromarketing papers found FAA was the most reliable time-frequency signal of preference but with "limited consistency across papers," each measure showing "mixed results when related to preference and purchase behaviour." https://pubmed.ncbi.nlm.nih.gov/36376735/ See also https://www.tandfonline.com/doi/full/10.1080/00913367.2024.2418109 on the reliability of EEG metrics for assessing advertisements.

Source PDF: https://twosidesna.org/wp-content/uploads/sites/16/2018/05/CPC_Neuroscience_EN_150717.pdf

### 7.7 There is no real-estate direct mail evidence base

Every real-estate-specific figure I could find ("3.32% industry-wide", "4–9% for agents in 2026", "up to 9% on house lists", "personalised mailers increase response by 135%") is a vendor or coaching blog restating the unsourced ANA/DMA numbers with a real-estate label attached. The one "case study" offered — 500 homes × 3 drops → 50 landing-page visits, 12 calls/forms, 4 listing appointments — has no control group, no verification, and appears on a vendor page. https://blog.crst.net/real-estate-direct-mail-response-rates/ · https://www.jamilacademy.com/blog/direct-mail-for-real-estate-agents

**[UNSOURCED]. We should assume we have no industry benchmark and generate our own.**

---

## 8. Australian evidence — thin, and mostly attitudinal

**This is the weakest area of the entire report. We are extrapolating from UK (JICMAIL) and US (ANA, USPS) data throughout, and should say so in any internal or external document.**

What exists:
- **Australia Post runs a quarterly online survey of 1,000–2,000 Australians** about attitudes to mail and email — what they receive, open and read, and their preferred channels. This is **attitudinal self-report, not campaign response measurement.** https://auspost.com.au/business/business-admin/research-case-studies/research-reports
- The flagship public document, **"Better connections: Australian attitudes to mail and email," is dated November 2013** — thirteen years old. https://auspost.com.au/content/dam/auspost_corp/media/documents/better-connections-report-australian-attitudes-to-mail-and-email-nov13.pdf
- "Creating connections that matter: How Australians want to hear from brands" was conducted **July 2013**, covering 45 real-life scenarios. Also thirteen years old.
- A frequently quoted AU figure — **83% brought promotional direct mail into their home, 45% read it straight away, 43% waited until evening** — is survey self-report and I could not date it to a retrievable current report.
- The Australia Post "Effectiveness of mail and email" research page now surfaces **eCommerce** statistics rather than mail-effectiveness metrics; the mail research appears to have been de-emphasised.
- Australia Post is a **beneficiary** of a positive finding about mail, exactly as Royal Mail Marketreach and Canada Post are. Treat all postal-operator research as interested.

**There is no Australian equivalent of JICMAIL.** No joint industry committee, no independent panel, no campaign-level response tracker. For a mail programme in Australia, **our own holdout tests will very quickly be the best Australian data in existence** — which is both an opportunity and an obligation.

---

## 9. Weakest links in this evidence

Ranked by how much damage the weakness would do if we planned around it.

1. **We have no Australian response-rate data at all.** Every response, ROI and CPA figure in this report is UK or US. UK letterbox culture, postal costs, mail volumes and clutter levels differ from Australia's, and Australian postage is expensive and rising ($1.70 → proposed $1.85). Directional transfer is defensible; numeric transfer is not.

2. **"Response rate" ≠ incremental effect, and almost nothing here measures incrementality.** JICMAIL's tracker accepts matchback (which overstates), the ANA report is self-reported, and Marketreach's is award-winners. The only genuinely incremental measurements in this report are the political-science RCTs — and they show mail moving behaviour by **fractions of a percentage point**. The gap between "7.2% responded" and "0.75pp were caused" is the central unresolved tension in the entire evidence base, and no source I found addresses it honestly.

3. **JICMAIL's Response Rate Tracker contributors are self-selected.** 15 organisations — sell-side businesses, agencies and data partners — voluntarily contribute campaign data. They are commercially invested in mail performing well, and there is no audit of which campaigns they choose to submit. It is *far* better than the ANA survey (real campaign measurement, ~5,000 campaigns, matchback/control techniques, a JIC governance structure) but it is not a random sample of all mail.

4. **The most-cited numbers in the industry are unsourced or misattributed.** "4.4%" is not in the report it is credited to. "9% / 4.9%" is from 2018. Anyone who has built a business case on these has built it on nothing, and that includes most real-estate mail advice.

5. **The VDP/personalisation lift claim has no primary source whatsoever**, and the circulating figures span 36%–500%. Do not budget for a personalisation multiplier.

6. **No honest QR scan-rate benchmark exists.** The largest real dataset (Bitly, ~2bn scans) has no denominator. Plan for 1–3% and instrument our own.

7. **The neuroscience is a decade old, N=30 per cell, measures proxies not purchases, and its key metric has documented reliability problems.** It is useful as a rationale for *why* physical mail might work; it is not evidence that it *did* work.

8. **Two sources I could not fully retrieve:** JICMAIL's sector-level and CPA/AOV absolute figures sit behind JICMAIL Discovery; the DMA article on the 2025 tracker returned HTTP 403. Absolute cold-mail CPA in £ is therefore missing — I have the 8x warm/cold ratio but not the base. **If we want the absolute CPA benchmark, a JICMAIL subscription or direct enquiry is the route.**

9. **Publication bias across the whole field.** Every institutional funder of mail research — Royal Mail, Canada Post, Australia Post, USPS, ANA (a marketing trade body), PODi (a print consortium), Two Sides (a paper-industry advocacy group, which hosts several of the PDFs cited here) — profits from mail looking effective. There is no well-funded party with an interest in publishing that mail underperforms. The political-science literature is the only body of evidence in this report produced by researchers with no stake in the answer, and it is by far the least flattering.

---

## Sources

**Primary reports retrieved and text-extracted**
- ANA Response Rate Report 2023 (published Feb 2024; survey fielded Jul–Nov 2023; 250 qualified responses) — https://theworldsgreatestmarketing.com/wp-content/uploads/2025/04/rr-2024-02-ana-response-rate-report-2023.pdf
- ANA landing page (403 to automated fetch) — https://www.ana.net/miccontent/show/id/rr-2024-02-ana-response-rate-report-2023
- ANA/DMA 2018 Response Rate Report — https://www.ana.net/miccontent/show/id/rr-2018-ana-dma-respose-rate
- Royal Mail Marketreach × WARC, "Driving Effectiveness with Direct Mail" (© WARC 2021; cases 2016–2020) — https://www.marketreach.co.uk/system/files/2025-07/Marketreach_WARC_Driving_Effectiveness_with_Direct_Mail.pdf
- Marketreach resource page — https://www.marketreach.co.uk/resource/direct-mail-effectiveness
- Canada Post / True Impact Marketing, "A Bias for Action" (31 July 2015; N=270) — https://twosidesna.org/wp-content/uploads/sites/16/2018/05/CPC_Neuroscience_EN_150717.pdf
- USPS Informed Delivery Year in Review, Apr 2024 – Mar 2025 — https://www.usps.com/business/pdf/informed-delivery-year-review.pdf
- Gerber & Green, "Field Experiments on Voter Mobilization: An Overview" (85 studies, 1998–2014) — https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf

**JICMAIL**
- Methodology (1,100 households, Kantar, 28-day diary) — https://www.jicmail.org.uk/about-jicmail/methodology/
- Response Rate Tracker 2025 — https://www.jicmail.org.uk/data/response-rate-tracker-2025/
- Response Rate Tracker (flagship research) — https://www.jicmail.org.uk/flagship-research/response-rate-tracker/
- JICMAIL data hub — https://www.jicmail.org.uk/data/
- Q4 2024 results (77% read rate, all-time high) — https://www.jicmail.org.uk/news/news-q4-2024-results-mail-read-rates-hit-an-all-time-high-as-the-channel-continues-to-assert-its-super-touchpoint-strengths/
- Q1 2026 results + FY2025 tracker — https://ipia.org.uk/jicmail-reports-continued-uplift-in-mails-digital-effectiveness-in-q1-2026-while-unveiling-the-latest-results-from-its-response-rate-tracker/
- DMA coverage of 2025 tracker (403 to fetch) — https://dma.org.uk/article/jicmails-2025-response-rate-tracker-update-reveals-growing-performance-of-customer-acquisition-mail-campaigns
- DMA, mail drives record digital engagement Q1 2026 — https://www.dma.org.uk/about/articles/mail-drives-record-levels-of-digital-engagement-in-q1-2026
- WARC: JICMAIL's definitive view on warm vs cold — https://www.warc.com/content/feed/jicmails-definitive-view-on-warm-vs-cold-direct-mail-response-rates/7945
- WARC: cold DM effective when repeated — https://www.warc.com/content/feed/cold-direct-mail-campaigns-are-effective-when-repeated/10567
- WARC: warm vs cold CPA — https://www.warc.com/newsandopinion/opinion/warm-cpas-might-be-higher-than-cold-but-theres-nothing-expensive-about-customer-acquisition/en-gb/6145
- Printweek coverage — https://www.printweek.com/content/news/jicmail-data-reveals-growth-in-customer-acquisition-through-mail-campaigns

**Peer-reviewed**
- Bertrand, Karlan, Mullainathan, Shafir & Zinman (2010), *QJE* 125(1):263 — https://academic.oup.com/qje/article/125/1/263/1880334 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1332007
- Munz, Jung & Alter (2020), "Name Similarity Encourages Generosity," *Marketing Science* (N=30,297) — https://pubsonline.informs.org/doi/10.1287/mksc.2019.1220
- Green, McGrath & Aronow, "Getting the Message Out: Why Mail-Delivered GOTV Interventions Succeed or Fail," *PS: Political Science & Politics* — https://www.cambridge.org/core/journals/ps-political-science-and-politics/article/getting-the-message-out-why-maildelivered-gotv-interventions-succeed-or-fail/9798F335F3044B09224061598E7172E1
- Frontal/parietal EEG alpha asymmetry reliability (large-scale) — https://link.springer.com/article/10.1007/s00429-021-02399-1
- Systematic review of EEG prediction of consumer preference (174 papers) — https://pubmed.ncbi.nlm.nih.gov/36376735/
- Reliability of EEG metrics for assessing video advertisements — https://www.tandfonline.com/doi/full/10.1080/00913367.2024.2418109
- Gerber & Green, *Get Out the Vote* (book) — https://www.jstor.org/stable/10.7864/j.ctt1657t5x
- Social Pressure and Voter Turnout (ISPS) — https://isps.yale.edu/sites/default/files/publication/2012/12/ISPS08-001.pdf

**Australian**
- ACCC, Australia Post letter pricing 2025–26 (BPR $1.50→$1.70; draft →$1.85) — https://www.accc.gov.au/by-industry/postal-services/postal-services-price-notification-and-monitoring/australia-post-letter-pricing-2025
- Australia Post 2025 product changes (Clean Mail discontinued) — https://auspost.com.au/disruptions-and-updates/pricing-updates/2025-product-changes
- Australia Post research reports index — https://auspost.com.au/business/business-admin/research-case-studies/research-reports
- Australia Post, "Better connections: Australian attitudes to mail and email," Nov 2013 — https://auspost.com.au/content/dam/auspost_corp/media/documents/better-connections-report-australian-attitudes-to-mail-and-email-nov13.pdf
- IPC / Australia Post "Connections That Matter" — https://www.ipc.be/services/markets-and-regulations/direct-marketing/research-analysis/reports/connections-that-matter

**QR / digital integration (mostly vendor)**
- Bitly, State of QR Code Scans 2026 (~2bn scans Jan–Dec 2025) — https://bitly.com/blog/state-of-qr-code-scans-2026/
- QRCG by Bitly original data report — https://www.qr-code-generator.com/blog/how-to-create-high-performing-qr-codes/
- USPS Informed Delivery calculator (source of "+37%") — https://www.uspsdelivers.com/informeddelivery-calculator/
- USPS Informed Delivery campaign best practices — https://www.usps.com/business/pdf/informed-delivery-campaign-best-practices.pdf
- Pageloot QR benchmarks by industry — https://pageloot.com/blog/qr-code-scanning-trends-by-industry-a-breakdown/
- Linkbreakers QR scan rate benchmarks — https://linkbreakers.com/help/article/qr-code-scan-rate-benchmarks-by-industry
- Ramin Zamani, direct mail QR scan rate — https://raminzamani.com/blog/direct-mail-qr-code-scan-rate/
- FanCircles, 10–15% scan rates — https://www.fancircles.com/blog/how-to-reach-qr-codes-scan-rates-of-10-to-15/
- Lob, incremental lift 2024 — https://www.lob.com/blog/incremental-lift-direct-mail-2024
- Poplar, guide to direct mail attribution — https://heypoplar.com/articles/a-complete-guide-to-direct-mail-attribution
- Measured, optimizing direct mail testing — https://www.measured.com/faq/optimizing-direct-mail-testing-measuring-incrementality/
- Gunderson Direct, response attribution (matchback overstatement) — https://gundersondirect.com/the-marketers-guide-to-direct-mail-response-attribution/

**VDP / personalisation claims (all vendor)**
- https://mailingcenter.net/why-variable-data-printing-is-key/
- https://blog.crst.net/personalized-direct-mail-variable-data-printing/
- https://www.shawmutdelivers.com/blog/why-it-pays-to-personalize-with-variable-data-printing/
- https://gonextpage.com/variable-data-printing-guide/

**Circulating "4.4%" and real-estate claims (unsourced)**
- https://www.mailpro.org/post/direct-mail-response-rates/
- https://blog.crst.net/direct-mail-response-rates/
- https://www.mydoceo.com/blog/direct-mail-response-rates-2026
- https://blog.crst.net/real-estate-direct-mail-response-rates/
- https://www.jamilacademy.com/blog/direct-mail-for-real-estate-agents
- https://www.taradel.com/blog/direct-mail-response-rate

**Trade press / critique**
- Marketing Charts, direct media response/CPA/ROI benchmarks — https://www.marketingcharts.com/featured-53645
- Ad Age, DMA survey coverage — https://adage.com/article/media/dma-snail-mail-phone-beat-digital-response-rates/235364
- Chief Marketer, DMA response vs ROI — https://www.chiefmarketer.com/direct-mail-gets-most-response-but-email-has-highest-roi-dma/
- SSIR, "Getting Out the Vote Is Tougher Than You Think" — https://ssir.org/articles/entry/getting_out_the_vote_is_tougher_than_you_think
