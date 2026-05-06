# Phase 1 Sprint 1 — Test Render Analysis

Three test renders executed 2026-05-06 to validate M6 (Limits of Our Evidence) and M11 (Morning Narrative) in production AI output. Total cost: ~$4 (Robina re-rendered via cache, BW + VL fresh).

| Property | Suburb | Tier | Status |
|---|---|---|---|
| 81 Thorngate Drive | Robina | mid-range $1.4M | ✓ rendered (PASS 16/16) |
| 59 Pintail Crescent | Burleigh Waters | premium $3.4M | ✓ rendered (3 FAIL — see §4) |
| 40 Gerona Circuit | Varsity Lakes | mid-range $1.4M | ✓ rendered (1 FAIL — see §4) |

Output files: `output/seller_reports/2026-05-06_*_reference_v2.pdf` + `*_editorial.json` (cached for free re-rendering).

---

## 1. Headline finding

**M6 + M11 work.** The AI produced high-quality, property-specific output for both modules in all three runs. The strategy is operationally sound. The remaining issues are *tuning*, not foundational.

The validator caught real problems before they shipped — including one we hadn't seen before (152-word morning narrative on BW). The `--strict` flag would have blocked the BW render; we ran without it deliberately to inspect the output.

---

## 2. M6 — Limits of Our Evidence

### What worked
**All three properties produced 4 well-structured items** with the correct titles (interior_condition, build_defects, neighbour_disputes, council_DAs). Each item:
- Names a specific risk signal (moisture damage, electrical wiring, termite damage, concrete cancer, telecom infrastructure, etc.)
- Quantifies a % range impact (3–8%, 5–12%, etc.)
- Adapts to property type — 2-storey BW mentioned "upper-floor leaks", single-level VL mentioned "shared fence maintenance agreements"
- Adapts to price tier — BW upper bound 5–15% (premium-appropriate), Robina/VL 3–8%

### Sample (Burleigh Waters — premium-aware)
> **Interior condition** — Our 9/10 condition score derives from listing photos and renovation status, but in-person inspection might reveal issues like water damage in bathrooms, degraded grout, or ceiling stains from past leaks. If significant defects exist beyond normal wear, expect 3–8% value impact. **Particular attention should be paid to wet areas in a two-storey home where upper floor leaks can cause expensive damage.**

The bolded sentence is property-aware (knows it's two-storey from the data) and adds genuine value beyond a generic statement.

### Layout issue (real)
- **Robina M6 + Varsity Lakes M6 rendered on header-less orphan pages.** The `<div class="page">` wrapping the Honest Assessment overflowed when M6 was added; the browser broke onto a new page that lost the standard page header (street address + F-mark) but kept the footer.
- **BW didn't have this problem** because the 7th value-equation ("Buyer Scarcity") + M6 fitted on the same overflow page, which inherited the header naturally.
- **Fix:** wrap M6 in its own dedicated `<div class="page">` with explicit header/footer macros. M6 deserves a full page anyway — it's a credibility moment.

---

## 3. M11 — A Morning In This Home

### What worked across all 3
- **Five absolute rules**: respected in 2 of 3 (Robina + VL passed all five). BW passed 4 of 5 (length undershot).
- **Rich named-everything**: actual POIs by name (Robina State School, Robina Town Centre, Robina Common, Marymount College, Caningeraba State School, Burleigh Waters canals, Lake Orr, Mermaid Waters, M1, Emmanuel College).
- **Property-feature anchors**: pool, stone benchtop, split-system, single-storey roofline, kookaburras, eucalypts, Burleigh Waters canals, willie wagtail, cul-de-sac.
- **Multiple time markers**: 6:30am, 7:15am, 8am, 9am, 10am, lunchtime, Sunday morning, Saturday morning, etc.
- **Quiet endings**: "somewhere, a lawnmower starting up again" / "The water barely ripples" / "the promise of water at precisely 25 degrees" — all sensory, none promotional.

### What broke (significant)

**Hallucinations — the biggest content risk:**

| Property | Hallucinated detail | Severity |
|---|---|---|
| Robina | "kids grab goggles from the **pool house**" | High — verified false (property has pool but no pool house in data) |
| Robina | "**Robina State School's weekend fair**" | Medium — likely invented event |
| BW | "**the Mustang waiting for its Sunday drive, the boat ready for Tuesday's fishing trip**" | **CRITICAL** — pure invention of seller's possessions |
| BW | "the gang prepares for **Marymount College's rugby game** — just 8 minutes away" | Medium — Marymount is real and nearby; the rugby specifically may be invention |
| VL | "neighbour's kids emerge in **Emmanuel College uniforms**, wheeling bikes from the garage for their 1.8km ride" | Low — Emmanuel College is real and ~1.8km away; the specific neighbour scene is fictional but generic enough to read as illustrative |

The BW Mustang/boat case is the most serious. We'd send a report to a seller who doesn't own a Mustang and they'd dismiss the entire document.

**Length variance:**
- Robina: 198 words (within 170–290 tolerance, just under 200 target)
- BW: **152 words** — 24% under target, validator caught it
- VL: 199 words (target hit)

The "EXACTLY 200–250" prompt language wasn't enough for BW. Claude interpreted liberally.

---

## 4. Validator behaviour (what it caught, what it missed)

### Caught correctly
| Hit | Suburb | Severity | Verdict |
|---|---|---|---|
| `morning_narrative` (152 words) | BW | FAIL | Real — would have shipped the wrong-length narrative |
| `value_equation_quality #7` lacks specific anchor | BW | FAIL | Real — VE body has "1.7%" + "12–18 months" but my regex doesn't match those — see §5 |
| `strengths_quality` lacks dollar/measurement/count | VL | FAIL | Real — strength has "15%" but my regex doesn't match `%` — see §5 |

### False positive
| Hit | Suburb | Verdict |
|---|---|---|
| `no_advice` matched "move quickly" | BW | **False positive** — actual context: "buyers carrying cash from acreage sales… make them strong negotiators who **move quickly** on the right property". Describing buyer behaviour, not seller-directed advice. |

### Missed (gaps)
- Hallucinations (pool house, Mustang, boat) — these aren't pattern-matchable; needs a different mechanism (cross-check editorial against property data fields)
- POI hallucinations (Robina State School weekend fair) — likewise

---

## 5. Recommended tunings

### A. Prompt — M11 length discipline (ship next)
Replace `"EXACTLY 200-250 words"` with a self-correcting instruction:
> Word count target: 200–250 words. **Before returning, count your words.** If under 200, expand by adding one more sensory beat (a sound, a texture, a small movement). If over 250, trim the least-essential sentence. Verify and only return when 200–250.

### B. Prompt — M11 hallucination guard (ship next)
Add to absolute rules:
> **(f) DO NOT invent the seller's possessions, hobbies, vehicles, pets, hosted events, neighbours by name, or specific local events. Reference ONLY: items present in the property data (pool, deck, kitchen, room types, gardens), nearby_pois POI names, public local landmarks, and generic family-life moments (kids, coffee, weekend mornings, lawnmowers, birds). Do NOT name a specific car model, boat, school event, named neighbour, or specific weekend activity unless that activity is explicitly named in the property's data fields.**

### C. Validator gaps (ship same commit)
1. **`check_no_advice`** — drop or scope `move quickly`, `act now`, `move/list immediately` patterns. They're too brittle. Replace with: only match when prefixed by "you" or "the seller" or in imperative form at sentence start.
2. **`check_value_equation_quality has_specific`** — extend to also match `%`, count-of-N (`\d+ of \d+`), and time periods (`\d+[-–]\d+ months/years`).
3. **`check_strengths_quality has_count`** — extend to match `%`, `premium`, `segment`, and any count-with-unit.

### D. Layout fix (ship same commit)
Wrap M6 (and optionally M11) in its own `<div class="page">` with the standard header + footer. Solves the orphan-page issue.

### E. Hallucination guard (next sprint)
Build a `check_hallucination_signals` validator that cross-references M11 prose against `property_valuation_data` and `nearby_pois`. E.g.:
- If M11 mentions "pool house", verify `outdoor.pool_house` is truthy (it isn't on Robina).
- If M11 names a specific neighbour activity ("Mustang", "boat", "horses", etc.), flag for manual review.
- If M11 names a specific event ("weekend fair", "rugby game", "open house"), flag — these are almost always invented.

### F. Data quality (deferred)
- **Property Through Our Eyes** showing `None/10` for most rooms on all three properties. This is upstream of M6/M11 — the visual analysis pipeline isn't producing room-level scores reliably. Investigate `property_valuation_data.kitchen / bathrooms / living / master / exterior / outdoor` schema vs what `build_room_assessments()` expects.
- **Varsity Lakes POIs** rendered the "What's Nearby" header but no items. Check `nearby_pois.by_category` shape on 40 Gerona Circuit.

### G. Quality bar (next sprint)
After A+B+C+D ship, re-run all three test renders and measure:
- Validator: target 16/16 PASS on all three with `--strict` enabled
- Visual: confirm M6 has consistent header/footer treatment
- Hallucination: re-read M11 for invention signals

---

## 6. Cross-suburb consistency observations

Across the three runs, the AI demonstrated:
- **Voice consistency** — all three reports felt like the same brand. Same restraint, same source-citing, same data-density.
- **Property awareness** — the AI used 2-storey vs single-level, premium vs mid-range, water-view vs no-water cues to tune each module differently.
- **Suburb awareness** — Robina mentioned Robina-specific landmarks; BW mentioned Burleigh canals; VL mentioned Lake Orr. None of these are hard-coded — they came from the comp data + POI data feeding the prompt.
- **Pricing tier appropriateness** — M6 risk impact ranges scaled with property value. BW upper bound was higher (15%); Robina + VL were 3–12%. Appropriate.

This is encouraging — the foundation is sound. The fixes above are sharpening, not redirecting.

---

## 7. What to ship next

In priority order (each row is a separate commit):

1. **Prompt updates A + B** + **validator fixes C** + **layout fix D** — single commit, ~30 min work. Re-run the three test renders ($4) to verify.
2. **Hallucination guard E** — separate commit, half a day's work.
3. **Sprint 2 modules** (M13 Risk + Protection, M22 Outcome Projection) per the roadmap — next sprint cycle.

**Will's manual review remains the final gate.** The validator + the prompt rules reduce review burden by surfacing obvious failures programmatically; Will catches the subtler issues (hallucinations, voice nuance, factual errors).

---

*Owner: Will Simpson · Logged 2026-05-06 13:55 AEST · Read alongside `08_roadmap.md`, `04_content_modules.md §G`, `01_psychology_principles.md §3.4 + §4.1`.*
