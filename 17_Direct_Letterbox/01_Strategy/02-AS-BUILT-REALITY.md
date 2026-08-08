# As-built: what exists, what is broken, what is fiction

**Verified in code and against the live database, 2026-08-08.** Nothing below is taken from a
markdown file's description of itself.

This document exists because the strategy in this folder assumes a trigger that does not fire and a
postal channel that does not exist. Both assumptions are load-bearing.

---

## 1. ⚠ The engagement trigger does not fire, and has not since 2026-08-04

This is the most important finding in the audit.

The brief for this project describes leads triggered *"at certain engagement levels on the page that
may indicate an owner from that address has looked up their own property."* That mechanism is
**real code that nothing calls.**

| Layer | State |
|---|---|
| **The rule** | `netlify/functions/offmarket-intent-alert.mjs:47-59` — qualifies on `≥6 cards` **and** `≥45s deck dwell`, with internal-id and bot-city suppression, deduped per `distinct_id\|slug\|day`, alerting Will by Telegram |
| **Who calls it** | `src/pages/OffMarketPage/discovery/DiscoveryDeck.tsx:27-64` — **the legacy deck only** |
| **What actually ships** | `off-market.$slug.tsx:616-655` — **DeckV3 is the default for every off-market home** since 2026-08-04 (*"V3 IS THE DEFAULT … Will, 2026-08-04"*). `grep fireIntentAlert` in `discovery-v3/` returns **nothing** |
| **Consequence** | The alert is unreachable from production traffic. `offmarket_intent_signals` last document: **2026-08-04T06:44:08Z**. The 45s / 6-card thresholds shipped 2026-08-07 and have **never evaluated a single live signal** |

The V3 deck does emit rich engagement telemetry — `card_dwell`, `card_viewed`, `deck_exit` with
`max_index_reached` / `reached_pct` / `final_dwell_ms`, scroll depth, time-on-page milestones — but
**only to PostHog. No backend job reads card progression or dwell.**

**What actually creates a lead** is a much blunter thing: `scripts/samantha/lead_intelligence.py:305-330`
runs a nightly PostHog query for the **`offmarket_report_view` event** — i.e. *the page loaded* —
filters to Australia, excludes internal ids and bot cities, and resolves the slug to an address.
There is no depth condition at all.

**So the real trigger today is "someone in Australia opened the page", not "someone engaged deeply."**
Any strategy that says "we mail people who engaged past a threshold" is describing something that
would have to be built first. It is a small build — the telemetry already exists — but it is a build.

---

## 2. What is in the lead pool right now

`system_monitor.lead_worklist`, live counts:

| Measure | Value |
|---|---|
| Total leads | **456** |
| From off-market page engagement (`offmarket_view:*`) | **283** |
| Date range of those | **2026-07-20 → 2026-08-07** (i.e. ~18 days, and the surface is new) |
| With a street-number address | **223** of 283 |
| Resolved to an actual property document | **9** |
| Priority `high` | **0** — and a pure page view *cannot* reach high: `score()` requires owner-occupier **and** a pre-market signal |
| Whole-collection priority | 1 high · 49 medium · 351 low · 41 unset · 13 test |
| `crm_contacts.offmarket_home` | 279 |
| **`print_post_queue`** | **0 documents** |

**223 addresses is a real, warm-ish, growing list.** At ~16 new off-market leads a day it reaches
Brain 1's 1,000-home farm size in roughly two months without any acquisition spend. That is the
single most valuable fact in this document.

Two caveats that bite:

- **The address is a display string, not a postal record.** No `postal_address` field, no postcode
  normalisation, no addressee. Only the legacy `offmarket-ladder-lead.mjs:55` writes a real
  `postal_address`, and it is on an arm that no longer ships.
- **There are no owner names anywhere.** Every piece goes to "The Homeowner", which forfeits the
  measured OR 1.25 from a handwritten personal address. Not fatal — the *property* is the
  personalisation — but it should be a conscious trade, not a discovery at the printer.

---

## 3. Assets — what could physically go in an envelope tomorrow

**Six are real files on disk. Three are per-address at scale.**

| Asset | State | Format | Count | Per-address? |
|---|---|---|---|---|
| **Owner-Subject Article** | ✅ works, generated today | HTML + MD (**no PDF path**) | 24 files / 8 addresses / **6 copy variants** | **Yes** |
| **Mini-site mailer** | ✅ works | **2-page A4 PDF**, real comps, competitor count, buyer persona, hero photo, aerial, **per-address QR** with UTMs | 21 PDFs, 2.5–6.6 MB | **Yes** |
| **V4 appraisal** | ✅ works | PDF, ~11 MB each | **184 PDFs** (re-runs included) | **Yes** |
| **Quarterly market report** | ✅ works, print-ready | PDF, **41 pp**, 10.4 MB | 2 genuine editions (Q1, Q2 2026) | No — generic |
| **Seller book** | ✅ print-ready press files | 100 pp hardcover | 1 | No — generic |
| **Fridge magnet** | ✅ **artwork is real** — CMYK vector PDF + 300 dpi PNG, 4 products, manufacturer-ready `PRINT_SPEC.md` | 75×75 square, 29 mm round, 90×55 card | — | **No — the QR is generic** |
| **Property aerials** | ✅ works — QLD cadastre boundary on satellite | PNG, 1.0–1.9 MB | ~18 | **Yes** |
| **Mailing lists** | ✅ real full postal addresses | CSV | **7,693** rows + 3×1,000 shortlists | Yes — **but no owner names** |
| **Property positioning report** | ❌ **not a document.** Writes a `positioning` object into Mongo. No PDF, no HTML | — | — | — |
| **Mini-site Version_Two** (7 booklets) | ❌ markdown only, no generator | — | — | — |

**399+ printable PDFs exist. Zero have been posted.** One homeowner has ever received a Fields
seller product, on 2026-04-10, in a format since retired.

### Blockers on the assets we would actually use

1. **The Owner-Subject Article has no PDF path** — HTML only. A print run needs one.
2. **Aerials are ~1.6 MB each and the article's own README flags them as too heavy for print.**
3. **Article length is ~1,100 words** plus two charts and a table. Long for a letterbox piece;
   right for an envelope piece. That choice is now forced by §2.4 of the evidence doc anyway.
4. **Eligibility is not stable between runs.** 28 Wedgebill Parade passed on 07-08 and was rejected
   on 08-08 because the nightly recompute moved its midpoint out of the design envelope. **Any mail
   list must be re-validated at lodgement, not at selection.**
5. **The `directional_only` / design-envelope gate rejects a large share of addresses** — houses
   outside $1M–$2M get no figure and no range. The mailable universe is smaller than 223.

---

## 4. The measurement rail — built, correct, and unused

`tracking-server/server.py:402-469` resolves `/a/<asset_code>` against `system_monitor.print_assets`,
inserts an `asset_scans` document, increments a counter, fires PostHog + Telegram, then 302s with
UTMs. **Asset codes are arbitrary strings, so per-address codes need no infrastructure change.**

Current contents: **`print_assets` = 1 document** (the Q2 quarterly cover). **`asset_scans` = 2
documents**, one of which has `user_agent: curl/7.81.0` from `34.40.230.132` — our own VM. A
self-test.

**This is the good news in the audit.** The hardest part of measuring print — a per-asset redirect
that attributes a physical piece to a digital session — already exists and works. It has simply
never been pointed at an address.

---

## 5. What does not exist at all

- **Any postal vendor integration.** A repo-wide grep for `postgrid|clicksend|lob|auspost|mailhouse`
  returns **zero hits in any `.py`, `.mjs` or `.ts`** — prose in markdown only.
- **A send queue.** `print_post_queue` exists as a name in two Facebook-book scripts and holds
  **0 documents**.
- **A sequence state machine** — no mail history, no suppression list, no scheduler, no per-address
  asset code, no "which piece is this household up to".
- **A holdout mechanism.**
- **An inbound instrument.** No contact form, no call tracking, no inbound-email capture. Lifetime
  hard-evidenced inbound contacts from any channel: **1**. This is what makes the whole programme
  currently unfalsifiable — we could not detect success if it happened.

---

## 6. What this means for the options

Four constraints fall out, and they shape every option in `03-STRATEGY-OPTIONS.md`:

1. **Any "engagement-triggered" option needs the trigger built first.** It is small — the telemetry
   is already in PostHog — but it is not there now.
2. **The 223 addresses are the most valuable asset in the estate** and they are accumulating for
   free at ~16/day. Warm beats cold by 8×. Nothing else on the table moves that number.
3. **Procurement, not engineering, is the critical path.** Every asset that matters already renders.
   The blocker is a mail house and a lodgement account.
4. **Instrument inbound before, or at the same time as, the first send.** Otherwise the programme
   produces an unreadable result, which is the failure mode that makes the entire farming category
   unfalsifiable — and the one the critics are right about.
