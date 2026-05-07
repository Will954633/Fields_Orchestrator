# Conversion Architecture — Funnel, Capture, Nurture, Convert

**Document:** 05 of 7 (Strategy series)
**Purpose:** How the report turns attention into email subscribers, subscribers into qualified leads, and leads into seller / buyer engagements. Operational, not aspirational.

---

## 1. The four-stage funnel

```
Stage 0: Awareness     →  Web edition (free, ungated until ~50%)
Stage 1: Email capture →  Soft-gate at the value tipping point
Stage 2: Nurture       →  4-email + monthly Pulse + audio
Stage 3: Lead          →  Print edition / interactive / Position Report
Stage 4: Engagement    →  15-min consult / pre-list analysis / Buyer Assist
```

No stage skips ahead. The report is the most patient sales artefact Fields owns — it earns the next stage rather than asking for it.

## 2. Stage 0 — Awareness (top of funnel)

**Channels (ranked by expected volume):**
- **Facebook ads** to the report landing page (existing channel — tested at $0.12 CPC).
- **Organic search** for "Burleigh Waters market", "Robina property data", "Varsity Lakes house prices", "Gold Coast property report" — own the SEO with quarterly fresh content.
- **LinkedIn organic** — Will's posts citing the report. The Informed Observer audience.
- **Inbound press citations** — once Issue 1-2 is published with novel data (four-source reconciliation, real Pain & Gain), local press and brokers cite. Free.
- **Per-chart social cuts** — auto-extracted from each report, distributed across 12 weeks per issue.

**Landing page:** `fieldsestate.com.au/quarterly/q[X]-[Y]`

The landing page is the **web edition** — not a marketing page asking for an email. It opens with the cover stat, the FCI, and the issue's tension. The reader gets value before being asked for anything.

## 3. Stage 1 — Email capture (the soft gate)

### The gating decision: ungated until ~50%

**Hard gate** (form before any content): converts ~2-3% on cold traffic.
**Soft gate / delayed gate** (content first, then form): converts 35-45% higher (Brixon 2025).
**No gate** (ungated everything): converts <1% but has the highest reach.

**Decision:** **Delayed soft gate at the 50% scroll mark.** The reader has consumed:
- The cover, FCI numeral, and three-sentence cover stat.
- The FCI explainer page.
- The Conviction Map (the signature visual — the one they want to share).
- The Tension chapter (the editorial through-line).
- The first part of "Where prices actually are."

By the gate point, they've seen value. The form is now a low-friction request, not a barrier.

### The form (single field, no friction)

```
[ Email address                                ]
[ Send me the next edition (free) ]

Privacy: Your email is used only to send the next quarterly. One-click unsubscribe.
```

**Forbidden additions:**
- Phone number field
- Postcode field
- "Tell us what you're looking for" intent capture
- Any second screen
- "Verify with phone for security"

The form has *one input*. Nothing else. Studies show single-field forms outperform 3+ field forms by ~12%. We have an entire nurture sequence to ask for more — we don't need to compress it into the gate.

### What happens after capture

1. **Instant delivery email**: PDF attached + link to the live web edition. Sent within 60 seconds of capture.
2. **PostHog event fired**: `quarterly_subscribed`, with `utm_*` super-property attribution.
3. **MailChimp / sender list addition**: tagged with the issue (`quarterly_q2_2026`) so future issues, nurture, and segmentation are clean.
4. **Welcome line in the delivery email**: "I'm Will. I built this. Reply to this email if anything is wrong, unclear, or wrong but interesting."

The instant-reply line is doing important work: it positions Will as a human and makes the relationship two-way before any commercial step.

### Conversion benchmark for Stage 1

- **Cold traffic → email**: target 4-6%. Financial-services landing-page average is 2-3%; soft-gating + value density should beat that.
- **Warm traffic (FB ad with Facebook Pixel match)**: target 7-10%.

## 4. Stage 2 — Nurture (4-email sequence + ongoing Pulse)

### Email sequence (4 emails, sent over the first 14 days)

#### Email 1 — Day 0: Instant delivery

**Subject:** Your Q2 2026 Fields Quarterly is attached.
**From:** Will Simpson <will@fieldsestate.com.au>
**Body:**
> [The PDF is attached. Online edition: fieldsestate.com.au/quarterly/q2-2026.]
>
> I built this. The data, the charts, the methodology, the words. So if anything is wrong, unclear, or wrong but interesting, reply to this email — I read every reply.
>
> The headline number this quarter is 108.4 on the Fields Conviction Index. That's a still-tight market, but cooling at the edges. The fuller story is on page 9.
>
> Will

#### Email 2 — Day 2: The audio version

**Subject:** The 22-minute audio of this quarter's report.
**From:** Will
**Body:**
> If you'd rather listen than read — the Q2 audio is online: [link].
>
> It's not a verbatim reading. I picked the three things I'd want a friend to know if they only had twenty minutes between Robina and Brisbane.

Audio is a multiplier — 76% of consumers remember audio content; audio drives 84% listener action (Acast 2024). Sending it as a separate email creates a second touchpoint with no ask.

#### Email 3 — Day 7: The personalised section

**Subject:** Want to see the report's data for your suburb?
**From:** Will
**Body:**
> The web edition has an "enter your address" box. Type in your home and you'll get a one-page chart pack — your suburb's FCI, your price tier's recent comps, where you sit on the distribution.
>
> [link]
>
> Why I'm telling you: it's the only way I can give you the report's analysis applied to where you actually live without you typing it into a form.

This is the **personalisation hook**. It moves the reader from "this is interesting" to "this is about me." It also captures address-level intent without asking for an address upfront — the user types it themselves into the interactive.

#### Email 4 — Day 14: The print edition / Position Report soft offer

**Subject:** A print copy, or a one-off custom analysis?
**From:** Will
**Body:**
> Two things, only relevant if you want them.
>
> 1. We mail a small print run of the Quarterly to subscribers who'd like one. Reply with your address if you'd like one. Free, while supplies last.
>
> 2. If you'd like the same methodology applied to your home — a Position Report — reply with your address and I'll prepare one. Free, no listing commitment, no follow-up sales call. (We cover the cost because subscribers who request these are the buyers we eventually want to know.)
>
> Will

This email is the first commercial signal in the entire sequence. Sent two weeks after capture, after three value-only emails. Even sceptics interpret this as fair.

### Ongoing — Monthly Pulse (between issues)

Between quarterly issues, subscribers receive a **monthly Pulse email**:
- One paragraph summary.
- One chart.
- Three numbers to watch.
- Optional: one question we asked the data and couldn't answer.

Modeled on John Burns' newsletter playbook (40k subscribers, the secret-sauce of his consulting business). Keeps the email warm; gives the reader a reason to remain subscribed.

### From Issue 4 — Weekly micro-update

When the data infrastructure supports it:
- One chart, one paragraph, three numbers.
- Sub-1000-word email, every Friday.
- Not all subscribers opt into this — only those who upgrade to the "weekly" tier (single click, free).

## 5. Stage 3 — Lead (the first commercial signal)

### Print edition trigger
- Anyone who replies to Email 4 with an address gets the print edition mailed.
- Cost: ~$15-20 + postage per copy.
- Quality of lead is screened — only people who actively requested it.
- Australia Post Express Parcel for the box-experience.

### Position Report trigger
- Anyone who replies asking for one gets a custom Position Report (existing per-property report, already designed).
- Free for the first ~50 per issue, then evaluated for a tiered model.

### The interactive (web-only personalisation)
- Reader enters address.
- The web layer pulls suburb + bedrooms + land size + closest comps and renders a personalised chart pack.
- Data captured: address (for our internal funnel), tier (auto-classified), behaviour (which suburbs they explored).
- Soft CTA at the bottom of the personalised chart pack: "Want this expanded into a full Position Report? [reply by email]."

## 6. Stage 4 — Engagement (the conversion)

### What this stage looks like
- Reader emails back with their address.
- Will (or a future team member) prepares the Position Report.
- Position Report is delivered with one quiet next-step question: "Would you like a 15-minute call to walk through the comparable set?"
- Some take the call; many don't. Both outcomes are fine.

### Conversion benchmarks
- **Email subscribers → print/Position Report request**: target 8-12% of subscribers on first cycle.
- **Print/Position Report → 15-min consult**: target 20-30%.
- **15-min consult → seller intent (within 12 months)**: target 40-50%.

With 1,000 cold visitors → 50 subscribers (5%) → 4-6 Position Report requests (10%) → 1-2 consults (25%) → ~0.5 seller engagements within 12 months (40%). Run at 4,000 visitors per issue and the math becomes meaningful.

### What this stage does NOT look like (Q2-Q3 2026)
- "Book a call now" buttons.
- Phone number capture.
- Sales emails ("limited time", "I noticed you didn't reply").
- Calendar booking widgets.
- Any kind of urgency theatre.

The Q3 deadline is real — but the discipline is to *not* compress the funnel under deadline pressure. Compressed funnels destroy the trust the report builds.

## 7. Embedded CTAs in the report itself

### Frequency rule
**One CTA per 8-10 pages.** Never mid-chart. Never mid-section. Always at section breaks.

### CTA language patterns

**Aligned with editorial rule (no advice):**
- "If you want to test this on your own home, [link]."
- "Curious how your suburb compares? [link]."
- "See what's similar to your home → [link]."

**Forbidden patterns:**
- "You should book a call."
- "Don't wait."
- "Limited time."
- "Now is a good time to sell."
- "Last chance to subscribe."

### Footer / sidebar persistence
- **Web edition:** small persistent sidebar — "Q[X] [YEAR] Edition. Get next quarter delivered." + email field.
- **PDF edition:** one-line footer on every page — "Next edition: [DATE]. fieldsestate.com.au/quarterly".
- **No sticky pop-ups, no exit-intent overlays.** The brand is the antithesis of those tactics.

## 8. Tracking architecture

Every entry point and conversion event is tracked.

### UTM parameters (set on every outbound link from ads, social, email)
- `utm_source` = facebook | linkedin | google | email | print
- `utm_medium` = paid | organic | nurture | direct
- `utm_campaign` = quarterly_q2_2026 | quarterly_q3_2026 ...
- `utm_content` = ad bucket name (e.g. `tension_hook`, `flood_section_teaser`, `fci_chart`)

### PostHog events (already extended in test 4 architecture — extend further)
- `quarterly_landing_view` — entry to the report
- `quarterly_section_reach_[name]` — fired at each major section boundary (cover, FCI, conviction_map, tension, prices, velocity, demand, supply, suburb_robina, suburb_burleigh, suburb_varsity, pain_gain, methodology, closing)
- `quarterly_gate_reached` — soft gate impression
- `quarterly_subscribed` — email capture
- `quarterly_pdf_download` — download click
- `quarterly_audio_play` — audio start
- `quarterly_audio_complete_[N]_pct` — audio retention milestones
- `quarterly_interactive_address_entered` — personalisation engagement
- `quarterly_print_request` — print copy requested
- `quarterly_position_report_request` — custom report requested
- `quarterly_chart_share_[chart]` — social sharing of a chart
- `quarterly_external_citation` — manual log when an external outlet cites

Funnel views built per issue + per ad bucket; cohort comparisons across issues to learn what works.

## 9. Distribution scheduling

Each issue runs an 8-week distribution cycle:

| Week | Activity |
|---|---|
| Week -2 | Final draft locked. Charts QA. Print press order. |
| Week -1 | Audio recorded + edited. PDF/web final. CSV published. |
| Week 0 | **Issue ships.** Email to existing list (instant). Press copies sent. |
| Week 1 | First Facebook ad bucket launched (the cover stat). |
| Week 2 | Second ad bucket (the conviction map). |
| Week 3 | LinkedIn organic round 1 — Will's posts on the four-source reconciliation. |
| Week 4 | Real Pain & Gain section as standalone article on the website + LinkedIn. |
| Week 5 | Audio episode socialised; "guest" appearance in adjacent podcasts pitched. |
| Week 6 | Featured suburb section as a deep-dive article (Burleigh flood data Issue 1). |
| Week 7 | "What we got wrong" pre-release tease for Issue 2 forecasted-tracker. |
| Week 8 | **Next issue draft starts.** Pulse-month between issues kept warm. |

Per-chart social cuts run weekly across all 8 weeks.

## 10. Conversion targets — Year 1

By the time Issue 4 ships (Q4 2026 → Feb 2027 distribution):

| Metric | Issue 1 target | Issue 4 target |
|---|---|---|
| Web edition unique visitors | 1,500 | 6,000 |
| Email subscribers acquired per issue | 75 | 350 |
| Cumulative subscribers | 75 | 1,500 |
| Audio episode plays | 200 | 2,500 |
| Print copies sent | 100 | 200 |
| Position Report requests | 5 | 25 |
| 15-min consults | 1 | 5 |
| Seller engagements (12-month attribution) | 0 | 8-12 |
| External press citations | 0 | 3+ |
| Internal CSV downloads | 50 | 500 |

These are deliberately ambitious. Trim by 50% and the report still pays its way.

## 11. The "what happens if it doesn't convert" plan

If by Issue 2 the conversion math is below targets:

- **Audit gating**: shift the gate position (earlier = more captures, lower quality; later = fewer captures, higher intent).
- **Audit Email 4** (the first commercial email): is the Position Report ask landing? If reply rate is <2%, rewrite.
- **Audit the personalisation interactive**: is it hitting? If reach is high but address entries are <5%, redesign.
- **Audit the report itself**: do readers reach the sections that contain the conversion content? PostHog section-reach events tell us.
- **Audit channel mix**: if Facebook is bringing browse-mode traffic (per V3 test learning), shift weight to Google and LinkedIn for higher-intent traffic.

The discipline is to **adjust the funnel, not the report**. The report's job is trust; the funnel's job is to harvest the trust the report builds.

## 12. Two principles to never violate

1. **Never make the report look like a sales artefact.** Every piece of conversion machinery sits *outside* the body content — in the gate, the email, the back-page CTA. Inside, the report reads like a research note.
2. **Never break a promise made on the gate.** "Your email is used only to send the next quarterly" means: no third-party sale, no aggressive re-marketing, no SMS, no phone calls without explicit consent. One broken promise destroys the entire funnel.

These two are non-negotiable. The conversion architecture works precisely because it is ethically over-built; weaken it and the value evaporates.
