# Direct Letterbox — personalised card + fridge magnet

**Scoped:** 2026-08-01 · **Owner:** Will Simpson · **Status:** scoping, nothing built

Every claim below is tagged. **[VERIFIED]** = checked against our own systems today. **[RESEARCHED]**
= from prior documented research. **[ASSUMPTION]** = not yet tested — treat as a question, not a fact.
That discipline is deliberate: twice today a fix was designed on top of a measurement that turned
out to be wrong, and this project's whole value rests on measuring something the industry doesn't.

---

## 1. The concept

A postcard-sized (or slightly larger) addressed mail piece carrying:

- **A photo of the recipient's own home** on the front
- Fields branding + short explanatory copy
- **A QR code unique to that address**, landing on that home's own mini-site — pre-built, so the
  reader never types their address

Optionally paired with a **Fields fridge magnet** carrying its own QR — a long-lived asset seen
daily, versus a card that gets binned or filed within days.

Target first wave: **1,000 homes** in the core suburbs.

## 2. Why this, strategically

Two gaps in the current plan, both identified 2026-08-01:

**The frequency gap.** The quarterly report is 4 touches a year, ~90 days apart. Coaching-corpus
evidence (Brain 1, verified against source units) says *"80% of sales are made from the fifth to
the twelfth contact"* (u1229) and that printed material *"tapers off very quickly"* after ~14 days
(u1468, u2267). A quarterly-only programme takes 15+ months to reach the fifth contact. This card
is the cheap, repeatable rail between quarterlies.

**The list-building bottleneck.** [VERIFIED] `lead_worklist` holds **297 non-test leads**: 232 with
a mailable address, **27 with email, 3 with phone**, and **210 carrying "no strong intent signal
yet"**. The genuinely warm list is ~46 people. We are not in a database-nurture game yet; we are in
a list-building game, and this is a list-building instrument.

**The measurement moat.** Brain 1's clearest finding across the whole corpus: **no direct
readership measurement exists anywhere.** Every "they read it" claim is the agent's assertion or an
inference from downstream sales. A per-address QR converts a 30-year industry assumption into an
observed, attributable intent signal.

## 3. What we already have

| Asset | Status | Detail |
|---|---|---|
| **Home photos** | [VERIFIED] | **14,546 properties** with photo sets in `/data/blobs/property-images/cadastral/` — Robina 6,455 · Burleigh Waters 4,186 · Varsity Lakes 3,905. 12–96 images each, 1024×768 JPG/PNG. |
| **Blob→record join** | [VERIFIED] | Blob directory name is the Mongo `_id`. Sampled 400 Burleigh Waters dirs → **400/400 matched** a `Gold_Coast.burleigh_waters` document. Clean join, no fuzzy matching needed. |
| **Address universe** | [VERIFIED] | `system_monitor.offmarket_discovery` = **18,070** addresses (robina 5,082 · burleigh_waters 4,972 · varsity_lakes 4,617 · nerang 3,399), each with a `slug` and pre-built deck cards. |
| **Mini-sites** | [VERIFIED] | Off-market pages live at `/off-market/:slug`; discovery deck shipped 2026-07-31. QR can land on a real page today. |
| **QR tracking** | [VERIFIED] | `tracking-server` resolves `/a/<asset_code>` against `system_monitor.print_assets` → inserts one `asset_scans` doc per scan, increments counters, fires PostHog + Telegram, then 302s with UTMs. **Codes are arbitrary strings, so per-address needs no infrastructure change.** `?m=` distinguishes the surface a code was scanned from — so a card code and a magnet code for the same address are separable. |
| **Print/post vendor** | [RESEARCHED 2026-07-17] | **Pronto Direct, Molendinar (Gold Coast)** — VDP, insertion, bulk Australia Post lodgement. API route for ongoing drip: PostGrid AU Letter API. *ClickSend Post is deprecated — do not use.* |
| **Currently-listed guard** | [VERIFIED, exists] | Real-time PropRadar sale check already used by AYH and the property-report builder. |

**Current state of `print_assets`: 1 asset, 0 scans.** It was built per *issue* (the quarterly cover),
never per address. That is the change this project needs.

## 4. What is NOT verified — resolve before printing

1. **Hero-photo selection.** [ASSUMPTION] With 12–96 images per property, something must choose a
   front elevation. A kitchen or bathroom on a postcard front fails the one-second
   "that's my house" test. GPT-vision photo reorder (step 105) exists but has **not** been confirmed
   to run over the cadastral set. **Must sample and eyeball before any print run.**
2. **Photo age.** [ASSUMPTION] Sampled records were scraped 2025 (379/400), but `scraped_at` records
   when *we* fetched, **not when the photo was taken**. These are very likely historical Domain
   listing photos and could show a previous owner's furniture, garden or cars. Charming or
   unsettling depending on age — needs a human look at ~30 samples.
3. **Print resolution.** [VERIFIED source size, ASSUMPTION on fitness] 1024×768 at 300 dpi gives a
   clean **~86×65 mm** image. Fine for a postcard front; tight beyond A6. **Card size is constrained
   by the photos we hold**, not the other way round.
4. **Variable-data fridge magnets.** [UNKNOWN] Digital presses handle variable data on magnetic
   stock in principle; the AU supplier landscape at 1,000 units and the price premium are not known.
   One call to Pronto Direct answers it.
5. **Legal/brand.** [UNKNOWN] Unsolicited mail carrying a photo of the recipient's home is
   legitimate but sits close to a line. Needs a considered view on tone and an opt-out, and a check
   of what the photo licence actually permits in print.

## 5. Cost model

[RESEARCHED 2026-07-17] The addressing decision dominates everything:

| Route | Cost/piece | Personalised photo? |
|---|---|---|
| Unaddressed letterbox drop | ~$0.20–0.60 | **No** — generic only |
| Addressed mail, regular letter | ~$1.20–1.70 | **Yes** |
| Addressed C4 flat A4 | ~$3.50–4.80 | Yes |

**A photo of their home requires addressed mail.** "Letterbox drop" and "their own house on the
front" are mutually exclusive; the concept as described is an addressed campaign.

**1,000 personalised addressed cards ≈ $1,200–1,800 postage plus print.** A postcard should land
under the DL-fold figure (no envelope, no insertion) but is the same order of magnitude. Existing
figures are for A4/C4 in envelopes — **get a postcard-specific quote.**

**Expected response** [RESEARCHED]: ANA/DMA average ~4.4%; house lists 5–9%, cold 2–4.4%; VDP
personalisation adds a **2–3× lift**; QR alongside a URL lifts response further. On 1,000
personalised addressed cards that is plausibly **40–90 responses** — which would multiply the
current 46-strong warm list several times over in a single wave. That is the business case.

## 6. Measurement design — the part that matters most

This is where the project earns more than its postage.

- **One `asset_code` per address per wave.** Encodes address + wave + surface. Registered in
  `print_assets` with the destination mini-site URL.
- **A scan is the signal, not the conversion.** Someone who scans and leaves without acting is
  still a warm lead — with a campaign-level code that is an anonymous blip; with a per-address code
  it is *"23 Bellbird Avenue looked at 7:42pm and didn't finish."* Given 210 of 297 current leads
  carry no strong signal, **incomplete scans are precisely the signal we lack.**
- **Card vs magnet attribution.** Separate codes (or `?m=`) for the two surfaces, so we can measure
  whether the magnet's claimed longevity is real — a response in month nine attributable to the
  magnet is the only way to know.
- **Feed `lead_worklist`.** A scan should create or upgrade a lead with its own origin type, so the
  existing intent scoring picks it up.
- **Define success before the wave ships.** Scan rate, scan→mini-site-engagement, engagement→enquiry.
  Log the target now so the result cannot be rationalised afterwards.

## 7. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Mailing a home currently listed with another agent | **High** — reputational | Sampled 400 records: **2 for_sale + 1 under_contract = 0.75%**, i.e. ~7–8 homes per 1,000. Run the PropRadar guard against the whole wave immediately before lodgement, not at list-build time. |
| Wrong/unrecognisable hero photo | High — kills the one-second recognition | Sample + human eyeball; consider aerial as a fallback where no front elevation exists |
| Stale photo (previous owner's home) | Medium | Sample against known sale dates; consider suppressing where the home has sold since the photo |
| Photo licence in print | Medium — unresolved | Confirm provenance and permitted use before print |
| Reads as intrusive | Medium — brand | Copy tone; clear opt-out; explain *why* we have the photo |
| Magnet VDP unavailable or costly | Low | Fall back to a generic magnet as the second touch |

## 8. Suggested phasing

**Phase 0 — de-risk (no spend).** Sample 30 hero photos and eyeball them; check photo age; get a
postcard + magnet VDP quote from Pronto Direct; settle the licence question.

**Phase 1 — build the rail.** Per-address `asset_code` generation, `print_assets` registration,
mini-site pre-build for the selected addresses, artwork with variable photo + QR, a PropRadar
suppression pass, and a print-ready export. Wrap the generator in `job_run()` per CLAUDE.md rule 7.

**Phase 2 — pilot, not 1,000.** Send **200** across the three suburbs before committing the full
wave. Enough to measure scan rate; cheap enough that a hero-photo or tone problem costs ~$300
rather than ~$1,800.

**Phase 3 — wave 1** at 1,000, one A/B axis only (our prior research is explicit: one axis per
wave). Card-only vs card+magnet is the obvious first test, since it also prices the magnet's value.

## 9. Open decisions for Will

1. **Which 1,000 of 18,070?** Highest-intent, or geographic saturation? Changes the copy entirely —
   and only saturation is a true "letterbox drop".
2. **Card + magnet together, or magnet as the second touch?** Sending both spends the long-lived
   asset on a cold contact. Holding the magnet for people who scanned halves wave-1 cost and makes
   the magnet a reward for engagement. *Recommendation: hold it back.*
3. **Aerial or street-level hero** where no good front elevation exists?
4. **QR destination** — their own mini-site (stronger, personal) or market content (safer, generic)?
5. **Are we comfortable with the tone** of an unsolicited card carrying a photo of their house?

---

## Appendix — commands used to verify

```bash
# photo inventory
for s in burleigh_waters robina varsity_lakes; do
  echo "$s: $(ls /data/blobs/property-images/cadastral/$s | wc -l)"; done

# blob -> record join (dir name is the Mongo _id)
python3 -c "from bson import ObjectId; from shared.db import get_client; ..."

# address universe
system_monitor.offmarket_discovery.count_documents({})     # 18,070

# QR route
tracking-server/server.py:412  @app.route("/a/<asset_code>")
```

**Related:** `10_Market_Report/working_notes/03_q2_2026_evidence_pack.md` (verified market numbers
for any data on the card) · memory `flyer_print_post_vendors` · memory `ops_dashboard_secret_path`
(never print an internal path on a public asset).
