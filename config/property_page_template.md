# Property Page Production Template

> Reference implementation: [36 Kingfisher Crescent, Burleigh Waters](https://fieldsestate.com.au/property/36-kingfisher-crescent-burleigh-waters)
>
> This document defines every section of the property detail page, whether it is
> **FIXED** (hardcoded / data-pipeline) or **DYNAMIC** (Opus agent-generated),
> the exact JSON field that drives it, and the formatting contract the agent must honour.

---

## Section Map (top → bottom)

### 1. HERO IMAGE
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — data pipeline |
| **Image** | `property_images[0]` (Azure Blob URL) |
| **Badge left** | `building_type` capitalised (e.g. "House") |
| **Badge right** | `suburb` (e.g. "Burleigh Waters") |
| **Waterfront badge** | `is_waterfront === true` → shows "Waterfront" |
| **Alt text** | `"{address} — {bedrooms} bedroom {property_type} for sale"` |

**No agent involvement.** Pipeline must ensure `property_images` is populated and first image is the best exterior shot (GPT photo-reorder handles this).

---

### 2. HEADLINE + ADDRESS
| Attribute | Source |
|-----------|--------|
| **Type** | DYNAMIC — Opus agent |
| **H1 headline** | `ai_analysis.headline` |
| **Address line** | FIXED — `address` field |

**Agent contract:**
- `headline`: ≤80 characters, specific, contains a number, passes Seller Test + Click Test
- Must NOT reference flood, day counts, or internal jargon
- Fallback: if no `ai_analysis`, H1 shows the address

---

### 3. TAB NAVIGATION
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — hardcoded |
| **Tabs** | "Fields Take" (default) · "Valuation Guide" · "How to Buy" · "How to Sell" |

---

### 4. FIELDS TAKE HOOK BLOCK (dark green card)
| Attribute | Source | JSON field |
|-----------|--------|------------|
| **Type** | DYNAMIC — Opus agent | |
| **Label** | FIXED: "Fields Take" | |
| **H2 verdict** | DYNAMIC | `ai_analysis.verdict` |
| **Sub-text** | DYNAMIC | `ai_analysis.sub_headline` |
| **Stat pills (right side)** | FIXED — data pipeline | |

**Stat pills (always shown, data pipeline):**
| Pill | Source |
|------|--------|
| Beds | `bedrooms` |
| Baths | `bathrooms` |
| Land | `lot_size_sqm` + "m²" |
| Price | `price` (strip "Offers Over" prefix if >20 chars) |

**Agent contract:**
- `verdict`: ≤25 words, one or two sentences, memorable, uses listing DATE not day count
- `sub_headline`: ≤150 chars, elaborates on the headline angle with a data point

---

### 5. METRICS STRIP (4 quick-scan cards)
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — computed from data pipeline |

| Card | Computation |
|------|------------|
| **Estimate** | `${ (valuation_data.confidence.range_low / 1M).toFixed(1) }M – ${ (range_high / 1M).toFixed(1) }M` |
| **Days listed** | `days_on_market` (or computed from `first_listed_timestamp`) |
| **Per m²** | `listing_price / lot_size_sqm` (rounded) |
| **Floor-to-land** | `floor_area / lot_size_sqm * 100` (rounded, + "%") |

**No agent involvement.** All values computed at render time from property document fields.

---

### 6. FAST SCAN (satellite + quick take)

#### 6a. Aerial View (left column)
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — data pipeline |
| **Label** | FIXED: "Aerial view" |
| **Image** | `satellite_image_url` |
| **Fallback** | If no satellite image → show beds/baths/lot stat panel |

#### 6b. Quick Take (right column)
| Attribute | Source | JSON field |
|-----------|--------|------------|
| **Type** | DYNAMIC — Opus agent | |
| **Label** | FIXED: "Quick take" | |
| **Title** | FIXED: "What you need to know" | |
| **Green ✔ items** | DYNAMIC | `ai_analysis.quick_take.strengths[]` |
| **Amber ⚠ item** | DYNAMIC | `ai_analysis.quick_take.trade_off` |

**Agent contract — NEW FIELD `quick_take`:**
```json
{
  "quick_take": {
    "strengths": [
      "A 14-minute walk to Burleigh Beach, 129 metres to the park, and a pool in the backyard",
      "The kitchen scores 8 out of 10, the exterior scores 8 out of 10, and the pool is in genuine good condition"
    ],
    "trade_off": "Weatherboard cladding, split-system air conditioning, and a cosmetic-not-complete renovation"
  }
}
```

**Rules:**
- `strengths`: exactly 2 items, each ≤1 sentence, each opens with a specific number or measurement
- `trade_off`: exactly 1 item, ≤1 sentence, names the 2-3 things a buyer trades off
- These are the 3-second scan layer — a buyer who reads nothing else gets the picture

---

### 7. INDEPENDENT DISCLAIMER
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — template with dynamic agent data |

**Template:**
> Fields Estate provides independent, data-driven analysis — we are not the listing agent for this property.
> For sale enquiries regarding {street_name}, contact **{agent_name}** at **{agency}**.

| Dynamic value | Source |
|---------------|--------|
| `street_name` | `address.split(',')[0]` |
| `agent_name` | `agent_name` field |
| `agency` | `agency` or `agency_name` field |

---

### 8. ANALYSIS SECTION LABEL
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — hardcoded |
| **Text** | "Analysis" with horizontal rule |

---

### 9. INSIGHT CARDS (×4 analysis sections)

Each insight renders as a dark card with:
- Section label (top)
- H2 headline (bold, full width)
- Two-column grid: "Key points" (left) + "What this means" (right)

| Section # | Fixed Label | JSON field |
|-----------|-------------|------------|
| 1 | "The Property" | `ai_analysis.insights[0]` |
| 2 | "Condition & Value" | `ai_analysis.insights[1]` |
| 3 | "Price Analysis" | `ai_analysis.insights[2]` |
| 4 | "Market Position" | `ai_analysis.insights[3]` |

**Agent contract — UPDATED INSIGHT STRUCTURE:**

Each insight in the `insights` array must be:

```json
{
  "h2": "A 14-minute walk to Burleigh Beach, 129 metres to the park, and a pool in the backyard — this is a home for the family that wants to stop driving everywhere.",
  "key_points": [
    "Coffee from Flockd Espresso Bar — a 2-minute walk",
    "Kids bike on a no-through-traffic crescent; Acanthus Park across the street; Burleigh Beach 1.11 km",
    "Woolworths 592m, ALDI under 650m, Burleigh Heads State School 776m",
    "Covered alfresco area 4.4 × 6.5m, seats 12, next to pool",
    "Triple-car setup for boat/caravan"
  ],
  "key_points_label": "Key points",
  "what_this_means": [
    "If you need a single-level showpiece with ducted air and rendered walls, this isn't it.",
    "If you want 678 sqm, a pool, and a life you can walk to, keep reading."
  ],
  "comparables": null
}
```

**When insight 2 (Price Analysis) contains comparable sales:**

```json
{
  "h2": "Two comparable sales adjust to a range of $2,160,000 to $3,413,000 — and the asking price sits in the lower half.",
  "key_points": [
    "Asking price of $2,495,000 sits roughly one-third of the way up the range",
    "The discount from the Curlew benchmark reflects real differences — cosmetic vs full reno, weatherboard vs render, split-system vs ducted",
    "At $2,495,000, you're not paying top-end money for a mid-tier finish"
  ],
  "key_points_label": "Comparable sales",
  "what_this_means": [
    "The land, floor area, and beach proximity carry the value.",
    "The discount is about finish — not fundamentals. Budget accordingly."
  ],
  "comparables": [
    {
      "address": "4 Curlew Crescent",
      "distance": "560m away",
      "sold_price": 3500000,
      "adjusted_price": 3413000,
      "summary": "Fully renovated benchmark — same bedrooms and bathrooms, 607 sqm, 187 sqm floor, ducted, rendered, 9/10 condition",
      "delta_label": "$918,000 below this benchmark"
    },
    {
      "address": "17 Beaconsfield Drive",
      "sold_price": 1600000,
      "adjusted_price": 2160000,
      "distance": "3.0km away",
      "summary": "Smaller home, inferior position — 3-bed on 420 sqm, 2.4 km from beach",
      "delta_label": "Sets the lower bound"
    }
  ]
}
```

**Formatting rules for key_points:**
- Each bullet is one self-contained fact (not a paragraph)
- Numbers are formatted: `$1,250,000` not "$1.25m", comma-separated thousands
- Measurements use × not x: "4.4 × 6.5m"
- Maximum 7 bullets per section
- Each bullet should be ≤2 sentences
- Bold key terms by wrapping in `**` (e.g. `"**Stone benchtops** and modern cabinetry"`)

**Formatting rules for what_this_means:**
- 2-3 items maximum
- Each item answers "what does this mean for the buyer?"
- Written in second person ("you")
- Can include a conditional framing ("If you need X, this isn't it")

---

### 10. BRIDGE CTA (after Price Analysis — insight index 2)
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — hardcoded template |
| **Label** | "Thinking of buying this property?" |
| **Body** | "Your outcome depends on how well you position your sale..." |
| **Button** | "Analyse My Property" → `/analyse-your-home?suburb={suburb}&type={type}&from={id}` |

**No agent involvement.** Dynamic values are suburb, building_type, and property ID.

---

### 11. THE FIELDS VERDICT (section label + dark card)

#### 11a. Section Label
FIXED: "The Fields Verdict" with horizontal rule

#### 11b. Verdict Card
| Attribute | Source | JSON field |
|-----------|--------|------------|
| **Label** | FIXED: "The bottom line" | |
| **Verdict text** | DYNAMIC | `ai_analysis.verdict` (same as hook block) |
| **Best for** | DYNAMIC | `ai_analysis.best_for[]` |
| **Not ideal for** | DYNAMIC | `ai_analysis.not_ideal_for[]` |
| **What to do next** | DYNAMIC | `ai_analysis.next_steps[]` |

**Agent contract — NEW FIELDS `best_for` and `not_ideal_for`:**

```json
{
  "best_for": [
    "Owner-occupiers",
    "Families upsizing locally",
    "Long-term holders"
  ],
  "not_ideal_for": [
    "Bargain buyers",
    "Short-term investors",
    "Turnkey-only buyers"
  ]
}
```

**Rules:**
- Exactly 3 items each
- Each item is 2-4 words (a buyer persona, not a sentence)
- `best_for` items get ✓ icon (green)
- `not_ideal_for` items get ✗ icon (muted)
- Must be specific to THIS property (not generic)

**Next steps contract (existing, unchanged):**
- 4-5 items, each actionable
- Reference specific data (comp range, scores, specific actions)
- Last item should point to "Valuation Guide"

#### 11c. Verdict CTA
FIXED template:
> "If you're selling in order to buy, your negotiation position is defined before you make an offer."
> Button: "See Where You Stand" → `/analyse-your-home?...`

---

### 12. CROSS-LINK CARDS (2-card grid)
| Card | Source | JSON field |
|------|--------|------------|
| **Valuation Guide CTA** | DYNAMIC | `ai_analysis.cta_valuation` |
| **Market Briefing CTA** | DYNAMIC | `ai_analysis.cta_market_buy` |

**Agent contract (existing, unchanged):**
```json
{
  "cta_valuation": {
    "hook": "Two comparable sales, twelve adjustments, and a range of $2,160,000 to $3,413,000...",
    "label": "Walk through the valuation step by step",
    "tab": "valuation"
  },
  "cta_market_buy": {
    "hook": "The BURLEIGH WATERS median has jumped from $1,468,750 to $1,800,000...",
    "label": "Read the Burleigh Waters buyer's market briefing",
    "url": "/market-metrics/Burleigh_Waters#buy"
  }
}
```

---

### 13. SELLING CONVERSION BLOCK
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — hardcoded template |
| **Label** | "Selling in order to buy?" |
| **Title** | "Most buyers at this price point need to sell first." |
| **Body** | "The difference between securing this home or missing it..." |
| **Button 1** | "Get My Property Analysis" → `/analyse-your-home?...` |
| **Button 2** | "Talk Through My Situation" → `mailto:will@fieldsestate.com.au` |

**No agent involvement.**

---

### 14. VALUATION GUIDE SECTION
| Attribute | Source |
|-----------|--------|
| **Type** | FIXED — data pipeline (from `valuation_data`) |

All content in this section is rendered by the `HowToValuePage` component using:
- `valuation_data.confidence.range_low / range_high`
- `valuation_data.confidence.confidence_level`
- `valuation_data.confidence.comparable_count`
- `valuation_data.comparables[]` — each with sold_price, adjusted_price, address, distance, weight, adjustments
- `valuation_data.confidence.weighted_std_dev`

**No agent involvement.** This is the transparent methodology section — all computed from real comparable sales data.

---

### 15. SEO / FAQ SECTION
| Attribute | Source | JSON field |
|-----------|--------|------------|
| **Type** | DYNAMIC — Opus agent | |
| **Title** | FIXED template: "{address} — Value, Price, and Market Analysis" | |
| **FAQ items** | DYNAMIC | `ai_analysis.faqs[]` |

**Agent contract (existing, refined):**
```json
{
  "faqs": [
    {
      "question": "What is 36 Kingfisher Crescent Burleigh Waters worth in 2026?",
      "answer": "Based on 2 verified comparable sales..."
    }
  ]
}
```

**Required FAQ topics (in this order):**
1. "What is {address} worth in {year}?" — cite comp range, point to Valuation Guide
2. "Is {address} overpriced or fairly priced?" — position in range
3. "What comparable sales support the asking price?" — name top 2-3 comps
4. "How does this property compare to others in {suburb}?" — percentile data
5. "Is {suburb} a good suburb to buy in right now?" — median trend
6. "What is happening in the {suburb} property market in {year}?" — supply + median
7. "How was this property valued?" — methodology summary
8. "How much is my house worth in {suburb}?" — CTA to /analyse-your-home
9. "Should I sell before buying another property?" — CTA to /analyse-your-home
10. "How do I know what my property will sell for?" — CTA to /analyse-your-home
11. "Is Fields Estate the listing agent?" — clarify no, name actual agent

---

### 16. FOOTER
FIXED — hardcoded site-wide component. No agent involvement.

---

## Complete `ai_analysis` JSON Schema (v2)

This is the full output the Opus agent pipeline must produce and store in the
`ai_analysis` field of each property document:

```json
{
  "headline": "string — ≤80 chars, H1 on hero",
  "sub_headline": "string — ≤150 chars, hook block sub-text",
  "meta_title": "string — ≤60 chars, SEO <title>",
  "meta_description": "string — ≤155 chars, SEO meta description",

  "verdict": "string — ≤25 words, bottom-line summary",

  "quick_take": {
    "strengths": ["string", "string"],
    "trade_off": "string"
  },

  "insights": [
    {
      "h2": "string — section H2, 8-15 words with a specific number",
      "key_points": ["string — one fact per bullet"],
      "key_points_label": "Key points | Comparable sales",
      "what_this_means": ["string — buyer implication"],
      "comparables": null
    },
    {
      "h2": "...",
      "key_points": ["..."],
      "key_points_label": "Key points",
      "what_this_means": ["..."],
      "comparables": null
    },
    {
      "h2": "...",
      "key_points": ["..."],
      "key_points_label": "Comparable sales",
      "what_this_means": ["..."],
      "comparables": [
        {
          "address": "string",
          "distance": "string",
          "sold_price": "number",
          "adjusted_price": "number",
          "summary": "string — one line description",
          "delta_label": "string — e.g. '$918,000 below this benchmark'"
        }
      ]
    },
    {
      "h2": "...",
      "key_points": ["..."],
      "key_points_label": "Key points",
      "what_this_means": ["..."],
      "comparables": null
    }
  ],

  "best_for": ["string — 2-4 word persona", "string", "string"],
  "not_ideal_for": ["string — 2-4 word persona", "string", "string"],

  "next_steps": ["string — actionable step", "..."],

  "cta_valuation": {
    "hook": "string — makes buyer need to see comp walkthrough",
    "label": "Walk through the valuation step by step",
    "tab": "valuation"
  },
  "cta_market_buy": {
    "hook": "string — uses suburb median movement data",
    "label": "Read the {SUBURB} buyer's market briefing",
    "url": "/market-metrics/{SUBURB_SLUG}#buy"
  },
  "cta_market_sell": {
    "hook": "string — supply + timing for sell-to-buy buyers",
    "label": "Read the {SUBURB} seller's market briefing",
    "url": "/market-metrics/{SUBURB_SLUG}#sell"
  },

  "flood_section": {
    "title": "string",
    "body": "string",
    "source": "Gold Coast City Council ArcGIS flood mapping"
  },

  "faqs": [
    {
      "question": "string",
      "answer": "string"
    }
  ],

  "generated_at": "ISO timestamp",
  "model": "claude-opus-4-6",
  "status": "draft | published | failed_factcheck"
}
```

---

## Insight Ordering Contract

The 4 insights MUST follow this exact thematic order:

| Index | Section Label | Theme | Opens with |
|-------|---------------|-------|------------|
| 0 | The Property | WHO + OUTCOME | Lifestyle, location, walkability, who this home is for |
| 1 | Condition & Value | PHYSICAL PROOF | Condition scores, materials, renovation status, room dimensions |
| 2 | Price Analysis | PRICE STORY | Comparable range, asking price position, value gap |
| 3 | Market Position | TRADE-OFFS | What keeps the price where it is, upgrade costs, market context |

**This order is non-negotiable.** The React component maps `insights[0]` → "The Property", etc. If the agent produces insights in a different order, the page will mislabel sections.

---

## Data Pipeline Requirements (fields that MUST exist)

For the page to render fully, the property document must have:

| Field | Pipeline step | Used by |
|-------|--------------|---------|
| `property_images` (array, ≥1) | Step 110 (image download) | Hero image |
| `building_type` | Scraper (step 101) | Hero badge |
| `bedrooms`, `bathrooms`, `car_spaces` | Scraper | Stats |
| `lot_size_sqm`, `total_floor_area` | Scraper + enrichment | Stats, metrics |
| `price` | Scraper | Stats, SEO |
| `days_on_market` or `first_listed_timestamp` | Scraper | Metrics strip |
| `satellite_image_url` | Step 117 (satellite analysis) | Aerial view |
| `agent_name`, `agency` / `agency_name` | Scraper | Disclaimer |
| `valuation_data` | Step 6 (valuation) | Valuation Guide section |
| `ai_analysis` (status: published) | Backend enrichment | All editorial sections |
| `address` | Scraper | Throughout |
| `suburb` | Scraper | Hero badge, CTAs |

---

## Migration Notes

### Breaking changes from v1 → v2 schema

| v1 field | v2 field | Change |
|----------|----------|--------|
| `insights[].lead` | `insights[].h2` | Renamed for clarity |
| `insights[].detail` | `insights[].key_points[]` + `insights[].what_this_means[]` | Split paragraph into structured arrays |
| *(hardcoded)* | `best_for[]` | NEW — was hardcoded in React |
| *(hardcoded)* | `not_ideal_for[]` | NEW — was hardcoded in React |
| *(extracted from insights)* | `quick_take` | NEW — was fragile extraction |
| *(not present)* | `insights[].comparables[]` | NEW — structured comp data |
| *(not present)* | `insights[].key_points_label` | NEW — "Key points" or "Comparable sales" |

### Backward compatibility

The React component must support BOTH v1 and v2 formats during migration:
- If `insights[0].h2` exists → v2 format, use structured fields
- If `insights[0].lead` exists → v1 format, use existing extraction logic
- If `best_for` exists → use it; else fall back to hardcoded defaults
- If `quick_take` exists → use it; else extract from insights[0-1].lead + insights[3].lead
