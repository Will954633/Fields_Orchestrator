# SEO Tab Optimisation Playbook

**Author:** Claude (VM Agent) | **Date:** 2026-03-27 | **Status:** Crash Risk tab complete, 6 tabs remaining

This document describes the exact process used to SEO-optimise the Crash Risk tab on the Market Metrics page, and provides step-by-step instructions for repeating it on each remaining tab.

---

## What Was Already Done (Shared Infrastructure)

These changes apply to **all 7 tabs** and do not need to be repeated:

| Change | File(s) | What It Does |
|--------|---------|-------------|
| Path-based routing | `src/routes.ts`, `src/routes/market-metrics.$suburb.tsx` | URLs are now `/market-metrics/:suburb/:category?` instead of hash fragments |
| Dynamic H1 | `src/pages/MarketMetricsPage/MarketMetricsPage.tsx` | H1 auto-renders from `marketMetricsSeo.ts` based on active tab |
| Dynamic title + meta | `src/App.tsx`, `MarketMetricsPage.tsx` | Title tag, meta description, canonical URL, OG tags — all set per tab |
| SEO meta config | `src/config/marketMetricsSeo.ts` | Titles, descriptions, H1s for all 7 tabs already defined |
| BreadcrumbList JSON-LD | `MarketMetricsPage.tsx` | Updates automatically per tab per suburb |
| Breadcrumb nav (visible) | `MarketMetricsPage.tsx` + CSS | Renders above page header for all tabs |
| Suburb tab links | `MarketMetricsPage.tsx` | Suburb tabs now link to `/market-metrics/Suburb/current-tab` (preserves tab) |

**In short:** The routing, meta tags, H1, breadcrumbs, and canonical URLs are already working for every tab. What remains per tab is **content-level SEO** — the changes inside each tab's component.

---

## Remaining Tabs to Optimise

| # | Tab ID | Label | Component | Has Custom Layout? |
|---|--------|-------|-----------|--------------------|
| 1 | `sell-now` | Should I Sell Now? | Standard chart grid via `CategorySummary` + `NarrativeSection` | No (uses shared layout) |
| 2 | `buy` | Is Now a Good Time to Buy? | Standard chart grid | No |
| 3 | `overview` | Market Overview | Standard chart grid | No |
| 4 | `houses-vs-units` | Houses vs Units | Standard chart grid | No |
| 5 | `direction` | Market Direction | Standard chart grid | No |
| 6 | `suburb-compare` | Suburb Comparison | Standard chart grid | No |

Unlike Crash Risk (which has its own `CrashRiskSection` component with a completely custom layout), the other 6 tabs all use the shared layout in `MarketMetricsPage.tsx` lines ~512-573: `CategorySummary` + chart grid or `NarrativeSection`. This means the changes for each tab are applied in fewer places.

---

## Step-by-Step Process Per Tab

### Step 1: Research Keywords

Query the search intent database to find the highest-frequency keywords for the tab's topic.

```python
# Run on VM (activate venv + load .env first)
from shared.db import get_client
import json
client = get_client()
sm = client['system_monitor']

# Replace SEED_TERMS with tab-specific terms
SEED_TERMS = ['should i sell', 'sell my house', 'best time to sell']  # example for sell-now

# Autocomplete suggestions
docs = list(sm['search_suggestions'].find(
    {'$or': [{'seed_query': {'$regex': t, '$options': 'i'}} for t in SEED_TERMS]},
    {'_id': 0, 'seed_query': 1, 'suggestions': 1, 'suburb': 1}
).limit(30))
for d in docs:
    print(f"Seed: {d['seed_query']}")
    for s in (d.get('suggestions') or [])[:5]:
        print(f"  -> {s}")

# PAA questions
paa = list(sm['search_paa_questions'].find(
    {'question': {'$regex': '|'.join(SEED_TERMS), '$options': 'i'}},
    {'_id': 0, 'question': 1}
).limit(20))
for p in paa:
    print(f"  Q: {p['question']}")

# Fears (for fear-based tabs like sell-now, buy)
analysis = sm['search_intent_analysis'].find_one(sort=[('date', -1)])
if analysis and 'fears' in analysis:
    for ftype, data in analysis['fears']['by_type'].items():
        print(f"\nFear type: {ftype} ({data['count']} signals)")
        for s in data['signals'][:5]:
            print(f"  {s['text']} (freq: {s['frequency']})")
```

**Keyword sources available:**
- `system_monitor.search_suggestions` — Google Autocomplete (1,652 docs)
- `system_monitor.search_paa_questions` — People Also Ask (3,710 docs)
- `system_monitor.search_trends` — Google Trends (130 docs)
- `system_monitor.search_intent_analysis` — Clustered analysis with fears, content gaps
- `system_monitor.search_scored_questions` — Ranked questions by importance score
- `system_monitor.google_ads_keywords` — Google Ads keyword data (729 docs)
- `system_monitor.search_console_queries` — Where site already appears in Google

### Step 2: Review Existing SEO Meta

The titles, descriptions, and H1s are already defined in `src/config/marketMetricsSeo.ts`. Review them against the keyword research from Step 1. If adjustments are needed:

```typescript
// src/config/marketMetricsSeo.ts
// Each entry has: title, description, h1, canonical
// {suburb} is replaced at runtime
```

**Rules for meta:**
- **Title:** Under 60 characters visible portion. Include primary keyword + year + suburb. End with `| Fields Estate`
- **Description:** 140-160 characters. Include primary keyword, suburb, "Gold Coast", what the page contains. End with freshness signal ("Updated [Month Year]")
- **H1:** One per page. Should match or closely mirror the primary search query

If you add a Gold Coast city-wide variant, add an entry to `GOLD_COAST_OVERRIDES` to avoid "Gold Coast, Gold Coast" in descriptions.

### Step 3: Add FAQ Section

This is the highest-impact content change for each tab. The FAQ section:
- Targets Google's "People Also Ask" boxes directly
- Provides visible content that matches long-tail queries
- Feeds the FAQPage JSON-LD schema for rich results

**For tabs using the shared layout** (all tabs except crash-risk), the FAQ needs to be added to the shared rendering logic in `MarketMetricsPage.tsx`. Two approaches:

**Option A — Per-tab FAQ component (recommended for tabs with many questions):**
Create a component like `SellNowFAQ.tsx` and conditionally render it:
```tsx
// In MarketMetricsPage.tsx, after the chart grid/narrative section
{category.id === 'sell-now' && <SellNowFAQ suburb={displaySuburb} />}
{category.id === 'buy' && <BuyTimingFAQ suburb={displaySuburb} />}
```

**Option B — FAQ data config (recommended for consistency):**
Create a config file `src/config/marketMetricsFaqs.ts` with FAQ data per tab:
```typescript
export const TAB_FAQS: Record<string, Array<{ question: string; answer: string }>> = {
  'sell-now': [
    {
      question: 'Should I sell my house now in {suburb}?',
      answer: 'The data for {suburb} shows... [2-3 sentences, data-driven, no advice]',
    },
    // ... more questions
  ],
};
```
Then render a shared `<TabFAQ>` component in the main layout.

**FAQ content rules (from CLAUDE.md editorial policy):**
- NO advice — never tell readers what to do ("you should sell", "now is a good time")
- NO predictions — use conditional language ("if X continues, data suggests Y")
- Data only — cite specific numbers, sources, time periods
- Include {suburb} and "Gold Coast" in every answer for keyword density
- 2-4 sentences per answer — concise, scannable

**Example FAQs per tab:**

**sell-now:**
- "Should I sell my house now in {suburb}?"
- "What time of year is best to sell a house on the Gold Coast?"
- "How long does it take to sell a house in {suburb}?"
- "Are {suburb} house prices going up or down?"
- "What is the vendor discount in {suburb}?"

**buy:**
- "Is now a good time to buy a house in {suburb}?"
- "Is the Gold Coast property market slowing down?"
- "Will Gold Coast property prices drop in 2026?"
- "How much deposit do I need to buy in {suburb}?"
- "What is the first home buyer grant in QLD 2026?"

**overview:**
- "What is the {suburb} property market doing?"
- "What is the median house price in {suburb}?"
- "How many houses sell in {suburb} per quarter?"
- "Is {suburb} a good place to live?"

**houses-vs-units:**
- "Is Gold Coast property a good investment?"
- "Should I buy a house or unit in {suburb}?"
- "What is a good rental yield on the Gold Coast?"
- "Do houses or units grow faster in {suburb}?"

**direction:**
- "Where is the Gold Coast property market heading?"
- "Will Gold Coast property prices go up in 2026?"
- "What is the Gold Coast property market forecast?"
- "Is the Gold Coast property market going to crash?" (cross-link to crash-risk)

**suburb-compare:**
- "Is {suburb} a good suburb to buy in?"
- "Is {suburb} a good place to live?"
- "Best suburbs on the Gold Coast to invest in?"
- "How does {suburb} compare to Burleigh Waters?"

### Step 4: Add JSON-LD FAQPage Schema

For each tab, inject a FAQPage schema using the same pattern as crash-risk. This can be done:
- In the tab-specific component (if it has one), or
- In `MarketMetricsPage.tsx` inside the SEO meta `useEffect`, keyed by `activeCategoryId`

```typescript
// In the SEO meta useEffect in MarketMetricsPage.tsx
if (activeCategoryId === 'sell-now') {
  setJsonLd('sell-now-faq', {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: [
      {
        '@type': 'Question',
        name: `Should I sell my house now in ${displaySuburb}?`,
        acceptedAnswer: {
          '@type': 'Answer',
          text: '...',
        },
      },
      // ... more questions
    ],
  });
}
```

**Important:** Clean up JSON-LD when switching tabs. Add cleanup in the effect:
```typescript
return () => {
  document.querySelectorAll('script[data-seo-id]').forEach(el => {
    if (el.getAttribute('data-seo-id') !== 'breadcrumb') el.remove();
  });
};
```

### Step 5: Optimise Section Headings (Chart Titles)

The shared chart grid renders chart titles from `src/config/marketMetrics.ts` via the `metric.label` field. These are currently generic ("Median Price", "Days on Market").

Two approaches:

**Option A — Override in ChartSection component:**
In the `ChartSection` component in `MarketMetricsPage.tsx`, add category-aware heading overrides:
```typescript
const getCategoryHeading = (chartId: string, categoryId: string, suburb: string): string | null => {
  const overrides: Record<string, Record<string, string>> = {
    'sell-now': {
      'median-price': `What Is the Median House Price in ${suburb}?`,
      'days-on-market': `How Quickly Are Homes Selling in ${suburb}?`,
      'absorption-rate': `Is ${suburb} a Seller's Market Right Now?`,
    },
    'buy': {
      'median-price': `How Much Does a House Cost in ${suburb}?`,
      'active-listings': `How Many Houses Are For Sale in ${suburb}?`,
      'price-growth-yoy': `Are ${suburb} House Prices Still Growing?`,
    },
    // ... etc
  };
  return overrides[categoryId]?.[chartId] || null;
};
```

**Option B — Keep current headings, add keyword-rich section intros:**
Add a paragraph above each chart group with natural keyword usage. Less disruptive.

**Recommendation:** Option A for highest-impact tabs (sell-now, buy), Option B for lower-priority tabs (overview, houses-vs-units).

### Step 6: Add Cross-Links Section

Each tab should link to:
1. The same tab for other suburbs (e.g., "Should I Sell Now in Burleigh Waters?")
2. Related tabs for the same suburb (e.g., from sell-now → crash-risk, direction)
3. The Gold Coast city-wide version
4. `/analyse-your-home` (conversion page)

This can be implemented as a shared component:
```tsx
// src/components/TabCrossLinks/TabCrossLinks.tsx
interface TabCrossLinksProps {
  currentTab: string;
  suburb: string;
  relatedTabs: Array<{ id: string; label: string }>;
}
```

### Step 7: Add Intro Paragraph

Below the `CategorySummary` component (or below the H2 heading for each tab), add a keyword-rich 2-3 sentence intro. This should:
- Include the primary keyword naturally
- Include the suburb name and "Gold Coast"
- Describe what data is on the page
- Signal freshness ("Updated weekly")

Example for sell-now:
```
Deciding whether to sell your house in {suburb}? This page shows the data that matters —
days on market, absorption rate, vendor discounts, and price adjustments. Track whether
{suburb} sellers currently have the advantage on the Gold Coast. Updated weekly.
```

### Step 8: Verify and Deploy

1. **Type check:** `tsc --noEmit --project tsconfig.json`
2. **Build:** `npx react-router build` (must succeed)
3. **Push to GitHub:** Use `gh api` method (git push hangs on this VM — see CLAUDE.md)
4. **Wait for Netlify deploy** (~2-3 minutes)
5. **Screenshot & verify:** `node scripts/site-inspector.js --url "/market-metrics/Robina/<tab-id>"`
6. **Check rendered text:** Read the `page-text.txt` output — verify H1, FAQ questions, cross-links, intro paragraph all present
7. **Log to fix-history:** Write entry in `logs/fix-history/YYYY-MM-DD.md`

---

## Priority Order for Remaining Tabs

Based on search volume from the keyword database:

| Priority | Tab | Why |
|----------|-----|-----|
| 1 | **sell-now** | "should i sell my house now" is the #1 transactional query in the dataset |
| 2 | **buy** | "is now a good time to buy" is the #2 transactional query |
| 3 | **overview** | "gold coast property market 2026" captures broad informational intent |
| 4 | **direction** | "gold coast property market forecast" is high-volume but overlaps with crash-risk |
| 5 | **houses-vs-units** | "houses vs units gold coast" is niche but low competition |
| 6 | **suburb-compare** | "is robina a good suburb" is suburb-specific, already partially served by other tabs |

---

## File Reference

| File | Purpose | Needs Editing Per Tab? |
|------|---------|----------------------|
| `src/config/marketMetricsSeo.ts` | Title, description, H1 per tab | Only if adjusting meta |
| `src/config/marketMetricCategories.ts` | Tab config, seoKeywords, summaryTemplate | Only if adding keywords |
| `src/pages/MarketMetricsPage/MarketMetricsPage.tsx` | Main page — shared layout, JSON-LD, SEO effect | Yes (FAQ, JSON-LD, intros) |
| `src/pages/MarketMetricsPage/MarketMetricsPage.module.css` | Page styles | If adding new visual elements |
| `src/components/CrashRiskSection/CrashRiskSection.tsx` | Crash-risk custom layout (DONE) | No |
| `src/App.tsx` | Fallback title/meta (useDocumentTitle) | Already handles all 7 tabs |
| `src/utils/seoMeta.ts` | `updateSeoMeta()` + `setJsonLd()` utilities | No changes needed |
| `src/routes/market-metrics.$suburb.tsx` | SSR meta tags | Already handles all categories |

---

## Keyword Data Access Quick Reference

```bash
# Activate environment
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a

# Collections in system_monitor database:
# - search_suggestions        (1,652 docs) — Google Autocomplete
# - search_youtube_suggestions (5,057 docs) — YouTube Autocomplete
# - search_trends              (130 docs)   — Google Trends
# - search_paa_questions       (3,710 docs) — People Also Ask
# - search_ad_queries          (69 docs)    — Google Ads search terms
# - search_console_queries     (23 docs)    — Google Search Console
# - search_reddit_posts        (1,422 docs) — Reddit discussions
# - search_intent_summary      (5 docs)     — Cross-source daily aggregation
# - search_intent_analysis     (2 docs)     — Bottom-up clustering, fears, content gaps
# - search_scored_questions    (1 doc)      — Ranked questions by weighted score
# - google_ads_keywords        (729 docs)   — Google Ads keyword performance
```

---

## Editorial Compliance Checklist

Before publishing any FAQ or intro text, verify:

- [ ] No advice — does not tell readers what to do
- [ ] No predictions — uses conditional language only
- [ ] No single valuations in headlines — uses ranges
- [ ] No forbidden words ("stunning", "nestled", "boasting", "rare opportunity", "robust market")
- [ ] Numbers formatted correctly ($1,250,000 not "$1.25m")
- [ ] Suburbs capitalised
- [ ] Data sources cited where specific figures are used
- [ ] "Gold Coast" and suburb name appear naturally in answers

---

## What "Done" Looks Like Per Tab

A tab is fully SEO-optimised when:

1. URL works: `/market-metrics/Robina/<tab-id>` returns 200 and renders the correct tab
2. Title tag matches `marketMetricsSeo.ts` config (visible in page-info.json)
3. H1 is keyword-targeted and unique to the tab
4. Meta description includes primary keyword + suburb + Gold Coast
5. FAQPage JSON-LD is injected with 4-6 questions
6. Visible FAQ section renders at bottom of tab content
7. Cross-links to other suburbs + related tabs are present
8. Intro paragraph with keywords appears below the category header
9. Section headings are keyword-optimised (where applicable)
10. Screenshot shows correct rendering with no console errors
11. Fix-history entry written
12. All files pushed to GitHub
