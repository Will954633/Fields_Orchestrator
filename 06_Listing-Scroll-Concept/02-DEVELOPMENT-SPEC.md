# Decision Feed v2 -- Development Specification

**Document:** `06_Listing-Scroll-Concept/02-DEVELOPMENT-SPEC.md`
**Date:** 2026-03-28
**Live mockup:** https://fieldsestate.com.au/for-sale-v2.html
**Status:** Ready for implementation

---

## 1. Technical Overview

### Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React 19 + TypeScript + Vite | Existing app, React Router 7 |
| Styling | CSS Modules | Codebase convention -- `*.module.css` per component |
| Backend | Netlify Functions (Node.js ESM) | Existing `properties-for-sale.mjs` extended |
| Database | Azure Cosmos DB (MongoDB API) | `Gold_Coast` database, suburb-per-collection |
| Analytics | PostHog | `phCapture()` from `src/utils/posthog.ts` |
| Deployment | Push to GitHub -> Netlify auto-deploys | Repo: `Will954633/Website_Version_Feb_2026` |

### What This Replaces

The current `ForSalePage` component (`src/pages/ForSalePage/ForSalePage.tsx`) renders a traditional grid of `PropertyCard` components with pagination, filters, and A/B test variants (`control`, `test_a`, `test_b`, `test_c`). The Decision Feed replaces the entire page with a curated, editorially-ordered feed that surfaces value intelligence before showing the full listing grid.

The existing `PropertyCard`, `PropertyGrid`, `PropertyFilters`, and `SoldPropertyGrid` components remain in the codebase but are no longer rendered on `/for-sale`. The Recently Sold tab (`/recently-sold`) continues to work as-is and should be preserved -- it will be moved to its own route component in Phase 3.

### Design Intent

The mockup demonstrates a mobile-first, single-column feed that replaces passive browsing ("scroll through 127 cards") with active decision support ("9 look worth your time"). Every card has a hook line and a tap-to-reveal section that explains the trade-off. Interaction cards (quizzes, comparisons, surprises) are interspersed to maintain engagement and build trust.

---

## 2. React Component Architecture

### Full Component Tree

```
<ForSalePage>                          // Route: /for-sale
  <SiteHeader />                       // Existing -- no changes
  <StickyProgressBar />                // Appears after hero scroll
  <HeroSection />                      // Dark hero with verdict pills
  <DecisionFeed>                       // Feed container with scroll tracking
    <SectionDivider />                 // "Best Deals Right Now" etc.
    <FeedCard />                       // Property card with reveal
    <FeedCard />
    <QuizCard />                       // "Spot the Catch" / "Would You Buy"
    <FeedCard />
    <SurpriseCard />                   // "What overpaying costs" etc.
    <FeedCard />
    <CompareCard />                    // Side-by-side comparison
    <QuizCard />
    <FeedCard />
    <CautionBlock />                   // Overpriced/caution listings
    <LeadCapture />                    // CTA: "Analyse my property"
  </DecisionFeed>
  <ExploreAllSection>                  // Transition to full grid
    <FilterPills />                    // Classification + suburb + type
    <MiniListItem />                   // Compact list rows for all properties
    <MiniListItem />
    ...
  </ExploreAllSection>
  <SiteFooter />                       // Existing -- no changes
</ForSalePage>
```

### Component Specifications

---

#### `ForSalePage` (replaces current)

**File:** `src/pages/ForSalePage/ForSalePage.tsx`

This is the page-level orchestrator. It fetches the decision feed data on mount, manages page-level state, and renders child components.

```typescript
// No props -- this is a route component

// State:
const [feedData, setFeedData] = useState<DecisionFeedResponse | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [dealsViewed, setDealsViewed] = useState(0);
const [revealedCards, setRevealedCards] = useState<Set<string>>(new Set());
const [quizAnswers, setQuizAnswers] = useState<Record<string, QuizAnswer>>({});
const [activeFilters, setActiveFilters] = useState<ExploreFilters>({ classification: 'all' });
const [expandedCautions, setExpandedCautions] = useState<Set<string>>(new Set());

// On mount: fetch decision feed
useEffect(() => {
  decisionFeedService.getFeed()
    .then(setFeedData)
    .catch(err => setError(err.message))
    .finally(() => setLoading(false));
}, []);

// PostHog tracking: scroll depth, time on page, Meta/Google attribution
// (same pattern as current ForSalePage)
```

**Key behavior:**
- Single fetch on mount via `decisionFeedService.getFeed()`
- No pagination -- the feed is pre-assembled server-side
- The ExploreAll section reuses the same data, filtered client-side
- URL state: `?classification=best_value&suburb=robina` for explore filters (optional, not required for MVP)

---

#### `StickyProgressBar`

**File:** `src/components/DecisionFeed/StickyProgressBar.tsx`

```typescript
interface StickyProgressBarProps {
  dealsViewed: number;
  totalDeals: number;
  visible: boolean;  // controlled by parent scroll listener
}
```

**CSS Module:** `StickyProgressBar.module.css`

| Class | Purpose |
|-------|---------|
| `.bar` | `position: sticky; top: 49px; z-index: 40; background: #fff;` |
| `.barVisible` | `opacity: 1; transform: translateY(0)` (applied when `visible=true`) |
| `.track` | 4px gray track bar |
| `.fill` | Green fill, `width: ${pct}%`, 0.4s ease transition |
| `.text` | "3 of 9 best deals viewed" label |

**Behavior:**
- Hidden by default (`opacity: 0; transform: translateY(-100%)`)
- Parent sets `visible=true` when `window.scrollY > 400`
- Progress: `(dealsViewed / totalDeals) * 100`
- Sticks below the SiteHeader (top: 49px matches header height)

---

#### `HeroSection`

**File:** `src/components/DecisionFeed/HeroSection.tsx`

```typescript
interface HeroSectionProps {
  summary: FeedSummary;
  onStartClick: () => void;  // scrolls to first card
}

interface FeedSummary {
  total_properties: number;
  best_value_count: number;
  fair_value_count: number;
  premium_count: number;
  one_of_a_kind_count: number;
  last_updated: string;       // ISO timestamp
  suburbs: string[];          // ["Robina", "Burleigh Waters", "Varsity Lakes"]
}
```

**CSS Module:** `HeroSection.module.css`

| Class | Purpose |
|-------|---------|
| `.hero` | Dark background (`var(--dark)`), padding 32px 20px 28px, radial copper gradient |
| `.heroTag` | "MARKET INTELLIGENCE" -- 11px uppercase, copper color |
| `.heroTitle` | 28px bold, `<span>` for copper-colored number |
| `.heroSub` | 14px, 55% white opacity |
| `.verdictRow` | Flex row of 3 verdict pills |
| `.verdictPill` | Flex-1, 12px padding, rounded, tap-to-filter behavior |
| `.vpGreen` / `.vpAmber` / `.vpRed` | Background + border tints per classification |
| `.vpCount` | 28px bold number |
| `.vpLabel` | 10px uppercase, 50% white opacity |
| `.heroCta` | Full-width copper button "Start with the best deals" |
| `.heroUpdated` | 11px, 30% white opacity, centered date + suburbs |

**Behavior:**
- Verdict pills are tappable -- clicking one scrolls to the first card of that classification (stretch goal, not MVP)
- CTA button smooth-scrolls to the first `FeedCard`
- `fade-up` animations on mount (CSS `@keyframes fadeUp` with staggered delays)

---

#### `DecisionFeed`

**File:** `src/components/DecisionFeed/DecisionFeed.tsx`

```typescript
interface DecisionFeedProps {
  items: FeedItem[];
  revealedCards: Set<string>;
  onReveal: (propertyId: string) => void;
  quizAnswers: Record<string, QuizAnswer>;
  onQuizAnswer: (quizId: string, answer: QuizAnswer) => void;
  expandedCautions: Set<string>;
  onCautionToggle: (propertyId: string) => void;
}

// FeedItem is a discriminated union
type FeedItem =
  | { type: 'section_divider'; title: string; subtitle?: string }
  | { type: 'feed_card'; property: FeedProperty }
  | { type: 'quiz_card'; quiz: QuizConfig }
  | { type: 'compare_card'; compare: CompareConfig }
  | { type: 'surprise_card'; surprise: SurpriseConfig }
  | { type: 'caution_block'; properties: CautionProperty[] }
  | { type: 'lead_capture' };
```

**Behavior:**
- Renders the `items` array sequentially using a switch on `item.type`
- Each item type maps to its child component
- The parent `ForSalePage` passes down state/handlers for reveals, quizzes, etc.

---

#### `FeedCard`

**File:** `src/components/DecisionFeed/FeedCard.tsx`

```typescript
interface FeedCardProps {
  property: FeedProperty;
  isRevealed: boolean;
  onReveal: () => void;
  index: number;  // for eager/lazy image loading
}
```

**CSS Module:** `FeedCard.module.css`

| Class | Purpose |
|-------|---------|
| `.card` | White bg, 14px margin, 14px radius, shadow, `:active` scale 0.985 |
| `.imageWrap` | 220px height, relative, overflow hidden |
| `.badge` | Absolute top-left, colored per classification |
| `.badgeValue` / `.badgePremium` / `.badgeFair` / `.badgeUnique` | Green/red/amber/copper backgrounds |
| `.views` | Absolute top-right, dark semi-transparent pill |
| `.gradient` | Bottom gradient overlay on image |
| `.body` | 14px 16px padding |
| `.suburb` | 11px uppercase, gray |
| `.address` | 17px bold |
| `.stats` | Flex row: "4 bed", "2 bath", "205 m2", "402 m2 lot" |
| `.hook` | 16px bold, cream bg, copper left border -- the ONE big claim |
| `.reveal` | `max-height: 0; overflow: hidden; opacity: 0; transition: 0.4s` |
| `.revealOpen` | `max-height: 600px; opacity: 1` |
| `.revealInner` | Padding wrapper |
| `.tradeoff` | 13px gray text, `<strong>` tags for emphasis |
| `.bestFor` | Flex-wrap row of green chips |
| `.bestForChip` | Green background pill |
| `.actions` | Flex row: "See why" button + "Full analysis" button |
| `.revealBtn` | Cream bg, grass color, toggles to green-bg when revealed |
| `.ctaBtn` | Grass bg, white text |

**Behavior:**
- Tap "See why" -> toggles `.revealOpen` on the reveal section
- When first revealed, calls `onReveal()` which increments `dealsViewed` in parent
- "Full analysis" links to `/property/${property.url_slug || property.id}`
- First 2 cards use `loading="eager"`, rest use `loading="lazy"`
- Badge text:
  - `best_value` -> "Best Value" (green)
  - `premium` -> "Paying a Premium" (red)
  - `fair_value` -> "Full Price" (amber)
  - `one_of_a_kind` -> "One of a Kind" (copper)

---

#### `QuizCard`

**File:** `src/components/DecisionFeed/QuizCard.tsx`

```typescript
type QuizVariant = 'spot_the_catch' | 'would_you_buy';

interface QuizConfig {
  id: string;
  variant: QuizVariant;
  property_id: string;
  property_url_slug?: string;
  property_address: string;
  question: string;             // The setup prompt
  options: QuizOption[];
  result_correct: QuizResult;   // Shown when correct answer picked
  result_wrong: QuizResult;     // Shown when wrong answer picked
  result_opinion?: QuizResult;  // For "would you buy" -- shown for any answer
}

interface QuizOption {
  text: string;
  is_correct?: boolean;   // For "spot the catch" -- one is correct
  answer_key?: string;    // For "would you buy" -- 'yes' | 'depends' | 'no'
}

interface QuizResult {
  title: string;
  text: string;
  cta_label: string;
  cta_url: string;
}

interface QuizAnswer {
  selectedIndex: number;
  isCorrect?: boolean;
  answeredAt: number;  // timestamp
}

interface QuizCardProps {
  quiz: QuizConfig;
  answer?: QuizAnswer;
  onAnswer: (answer: QuizAnswer) => void;
}
```

**CSS Module:** `QuizCard.module.css`

| Class | Purpose |
|-------|---------|
| `.card` | White bg, same margin/radius/shadow as feed cards |
| `.top` | Dark gradient background, white text, centered |
| `.topTitle` | 17px bold ("Spot the Catch" / "Would You Buy This?") |
| `.topSub` | 13px, 55% white opacity |
| `.body` | 16px padding |
| `.question` | 15px semibold, centered, 14px bottom margin |
| `.options` | Flex column, 8px gap |
| `.option` | 13px padding, 2px border, rounded, centered text |
| `.optionSelected` | Green border + green background |
| `.optionWrong` | Red border + red background |
| `.result` | Green-bg panel, `max-height: 0; opacity: 0` hidden by default |
| `.resultShow` | `max-height: 300px; opacity: 1` |
| `.resultWrong` | Amber background variant |
| `.resultTitle` | 14px bold green (or amber for wrong) |
| `.resultText` | 13px gray |
| `.resultCta` | 13px semibold grass-colored link |

**Behavior:**
- **Spot the Catch:** One option is correct. Wrong picks show red + highlight correct. Correct shows green. Result reveals.
- **Would You Buy:** All options are valid (opinion). Any pick shows the Fields verdict result.
- All options disabled after first pick (`pointer-events: none`)
- PostHog event on answer

---

#### `CompareCard`

**File:** `src/components/DecisionFeed/CompareCard.tsx`

```typescript
interface CompareConfig {
  id: string;
  title: string;                // "This or That?"
  subtitle: string;             // "Two Burleigh Waters homes..."
  property_a: CompareProperty;
  property_b: CompareProperty;
  rows: CompareRow[];
}

interface CompareProperty {
  id: string;
  url_slug?: string;
  address_short: string;        // "27 Seville Cct"
  price_display: string;        // "$1,699,000"
  main_image_url: string;
  suburb: string;
}

interface CompareRow {
  label: string;                // "Floor Area", "Condition", "Catch", "Price gap"
  value_a: string;              // "205 m2"
  value_b: string;              // "173 m2"
  highlight_a?: 'good' | 'bad'; // green or red text
  highlight_b?: 'good' | 'bad';
}

interface CompareCardProps {
  compare: CompareConfig;
}
```

**CSS Module:** `CompareCard.module.css`

| Class | Purpose |
|-------|---------|
| `.card` | White bg, standard margin/radius/shadow |
| `.top` | Dark bg, white centered text |
| `.body` | 16px padding |
| `.vsGrid` | CSS Grid: `1fr auto 1fr`, center-aligned |
| `.prop` | Centered: thumbnail + short address + price |
| `.propImg` | 100% width, 90px height, 8px radius |
| `.propAddr` | 12px semibold |
| `.propSub` | 10px gray |
| `.divider` | "vs" text, 20px bold gray |
| `.rows` | Flex column, 1px gap |
| `.row` | 2-column grid on gray background |
| `.cell` | White bg, 10px 12px padding, 12px font |
| `.cellLabel` | 10px uppercase gray |
| `.cellValue` | Semibold |
| `.cellGood` | Green text |
| `.cellBad` | Red text |
| `.cta` | Flex row of 2 buttons: cream-left, grass-right |

**Behavior:**
- CTA buttons link to respective property pages
- PostHog event: `compare_view` on mount (viewport intersection)

---

#### `SurpriseCard`

**File:** `src/components/DecisionFeed/SurpriseCard.tsx`

```typescript
interface SurpriseConfig {
  id: string;
  emoji: string;                // e.g. the money-wings emoji
  title: string;                // "What overpaying $200K actually costs"
  subtitle: string;             // "On a 30-year mortgage at 6.2%"
  big_number: string;           // "+$1,220/mo"
  footnote: string;             // "$439,200 extra over the life of the loan"
}

interface SurpriseCardProps {
  surprise: SurpriseConfig;
}
```

**CSS Module:** `SurpriseCard.module.css`

| Class | Purpose |
|-------|---------|
| `.card` | Dark bg, white text, 20px padding, centered |
| `.emoji` | 32px font size |
| `.title` | 16px bold |
| `.subtitle` | 13px, 60% white opacity |
| `.bigNumber` | 36px bold, copper color |
| `.footnote` | 12px, 40% white opacity |

---

#### `SectionDivider`

**File:** `src/components/DecisionFeed/SectionDivider.tsx`

```typescript
interface SectionDividerProps {
  title: string;               // "Best Deals Right Now"
  linkText?: string;           // "9 found >"
  onLinkClick?: () => void;
}
```

**CSS Module:** `SectionDivider.module.css`

| Class | Purpose |
|-------|---------|
| `.divider` | Flex between, 20px 20px 8px padding |
| `.title` | 17px bold |
| `.link` | 12px semibold copper |

---

#### `CautionBlock`

**File:** `src/components/DecisionFeed/CautionBlock.tsx`

```typescript
interface CautionProperty {
  id: string;
  url_slug?: string;
  address: string;
  detail: string;              // Hidden text revealed on tap
  days_on_market: number;
  value_gap_pct: number;
}

interface CautionBlockProps {
  properties: CautionProperty[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}
```

**CSS Module:** `CautionBlock.module.css`

| Class | Purpose |
|-------|---------|
| `.block` | White bg, red tint border, standard shadow |
| `.top` | Red background strip with warning icon + title |
| `.item` | Padding, bottom border, cursor pointer |
| `.itemRow` | Flex between: address/detail vs arrow |
| `.itemAddr` | 13px semibold |
| `.itemDetail` | 12px gray, hidden by default, toggle on tap |
| `.itemDays` | Inline red pill: "67 days listed" |
| `.itemArrow` | Chevron right |

**Behavior:**
- Tap item toggles detail visibility
- Tapping address navigates to property page
- PostHog: `caution_expand` event

---

#### `LeadCapture`

**File:** `src/components/DecisionFeed/LeadCapture.tsx`

```typescript
interface LeadCaptureProps {
  // No props needed -- content is static
}

// State:
const [submitted, setSubmitted] = useState(false);
```

**CSS Module:** `LeadCapture.module.css`

| Class | Purpose |
|-------|---------|
| `.box` | White bg, centered text, standard margin/radius/shadow |
| `.title` | 16px bold |
| `.text` | 13px gray |
| `.btnPrimary` | Full-width copper button: "Analyse my property" |
| `.btnSecondary` | Full-width outline button: "Talk through my situation" |

**Behavior:**
- Primary CTA links to `/analyse-your-home`
- Secondary CTA opens email mailto or a contact form (TBD)
- PostHog: `lead_cta_click` with `{ cta_type: 'analyse' | 'talk' }`

---

#### `ExploreAllSection`

**File:** `src/components/DecisionFeed/ExploreAllSection.tsx`

```typescript
interface ExploreFilters {
  classification: 'all' | 'best_value' | 'fair_value' | 'premium';
  suburb?: string;
  property_type?: string;
}

interface ExploreAllSectionProps {
  properties: FeedProperty[];
  summary: FeedSummary;
  filters: ExploreFilters;
  onFiltersChange: (filters: ExploreFilters) => void;
}
```

**CSS Module:** `ExploreAllSection.module.css`

| Class | Purpose |
|-------|---------|
| `.gate` | White bg card, centered text, 24px 20px padding |
| `.gateTitle` | 18px bold: "Explore all 127 properties" |
| `.gateSub` | 13px gray |

---

#### `FilterPills`

**File:** `src/components/DecisionFeed/FilterPills.tsx`

```typescript
interface FilterPillsProps {
  summary: FeedSummary;
  activeFilters: ExploreFilters;
  suburbs: string[];
  onFilterChange: (filters: ExploreFilters) => void;
}
```

**CSS Module:** `FilterPills.module.css`

| Class | Purpose |
|-------|---------|
| `.pills` | Flex, 6px gap, wrap, centered |
| `.pill` | 8px 14px padding, 20px radius, 12px semibold, 1px border |
| `.pillActive` | Grass bg, white text, grass border |
| `.pillCount` | Inline, 60% opacity, 400 weight |

---

#### `MiniListItem`

**File:** `src/components/DecisionFeed/MiniListItem.tsx`

```typescript
interface MiniListItemProps {
  property: FeedProperty;
}
```

**CSS Module:** `MiniListItem.module.css`

| Class | Purpose |
|-------|---------|
| `.item` | White bg, flex row, 12px padding+gap, 10px radius, shadow |
| `.img` | 72x72px, 8px radius, flex-shrink-0 |
| `.content` | Flex column, min-width 0 (for text truncation) |
| `.badge` | Inline pill: green/amber/red per classification |
| `.badgeGreen` / `.badgeAmber` / `.badgeRed` | Color variants |
| `.addr` | 13px semibold, nowrap ellipsis |
| `.meta` | 11px gray: "Burleigh Waters . 4 bed . $1,699,000" |
| `.hook` | 11px gray, 2-line clamp |
| `.arrow` | 16px gray chevron, align-self center |

---

## 3. Data Model / TypeScript Types

**File:** `src/types/decisionFeed.ts`

```typescript
// ============================================================
// Classification
// ============================================================

export type PropertyClassification =
  | 'best_value'
  | 'fair_value'
  | 'premium'
  | 'one_of_a_kind'
  | 'unclassified';

// ============================================================
// Feed Property -- extends PropertySummary with decision fields
// ============================================================

export interface FeedProperty {
  // Core identity (same as existing PropertySummary)
  id: string;
  url_slug?: string | null;
  address: string;
  suburb: string;
  postcode?: string | null;
  price_display: string;
  price_numeric: number | null;
  bedrooms: number;
  bathrooms: number;
  car_spaces: number;
  land_size: number | null;
  floor_area?: number | null;
  property_type: string;
  main_image_url: string;
  days_on_market: number;

  // Classification (new)
  classification: PropertyClassification;
  feed_score: number;           // 0-100, determines feed ordering

  // Valuation intelligence
  value_gap_pct: number | null;
  reconciled_valuation: number | null;
  valuation_confidence: string | null;
  valuation_positioning: 'overpriced' | 'fair' | 'underpriced' | null;

  // AI editorial content (from ai_analysis)
  hook: string | null;          // The ONE big claim line
  trade_off: string | null;     // "The catch:" / "The trade-off:" text
  best_for: string[] | null;    // ["Families near Marymount", "Turnkey-only buyers"]
  verdict: string | null;       // Short verdict summary
  strengths: string[] | null;   // From quick_take.strengths

  // Engagement signals
  condition_score: number | null;
  is_waterfront: boolean;
  has_pool: boolean;
  price_changed: boolean;
  price_change_direction: 'up' | 'down' | null;
  rarity_label: string | null;
}

// ============================================================
// Feed Summary -- hero section counts
// ============================================================

export interface FeedSummary {
  total_properties: number;
  best_value_count: number;
  fair_value_count: number;
  premium_count: number;
  one_of_a_kind_count: number;
  last_updated: string;
  suburbs: string[];
}

// ============================================================
// Feed Items (discriminated union)
// ============================================================

export type FeedItem =
  | { type: 'section_divider'; title: string; subtitle?: string }
  | { type: 'feed_card'; property: FeedProperty }
  | { type: 'quiz_card'; quiz: QuizConfig }
  | { type: 'compare_card'; compare: CompareConfig }
  | { type: 'surprise_card'; surprise: SurpriseConfig }
  | { type: 'caution_block'; properties: CautionProperty[] }
  | { type: 'lead_capture' };

// ============================================================
// Quiz types
// ============================================================

export type QuizVariant = 'spot_the_catch' | 'would_you_buy';

export interface QuizOption {
  text: string;
  is_correct?: boolean;
  answer_key?: string;
}

export interface QuizResult {
  title: string;
  text: string;
  cta_label: string;
  cta_url: string;
}

export interface QuizConfig {
  id: string;
  variant: QuizVariant;
  property_id: string;
  property_url_slug?: string;
  property_address: string;
  question: string;
  options: QuizOption[];
  result_correct: QuizResult;
  result_wrong: QuizResult;
  result_opinion?: QuizResult;
}

export interface QuizAnswer {
  selectedIndex: number;
  isCorrect?: boolean;
  answeredAt: number;
}

// ============================================================
// Compare types
// ============================================================

export interface CompareProperty {
  id: string;
  url_slug?: string;
  address_short: string;
  price_display: string;
  main_image_url: string;
  suburb: string;
}

export interface CompareRow {
  label: string;
  value_a: string;
  value_b: string;
  highlight_a?: 'good' | 'bad';
  highlight_b?: 'good' | 'bad';
}

export interface CompareConfig {
  id: string;
  title: string;
  subtitle: string;
  property_a: CompareProperty;
  property_b: CompareProperty;
  rows: CompareRow[];
}

// ============================================================
// Surprise types
// ============================================================

export interface SurpriseConfig {
  id: string;
  emoji: string;
  title: string;
  subtitle: string;
  big_number: string;
  footnote: string;
}

// ============================================================
// Caution types
// ============================================================

export interface CautionProperty {
  id: string;
  url_slug?: string;
  address: string;
  detail: string;
  days_on_market: number;
  value_gap_pct: number;
}

// ============================================================
// Full API response
// ============================================================

export interface DecisionFeedResponse {
  summary: FeedSummary;
  feed_items: FeedItem[];
  all_properties: FeedProperty[];  // Full list for ExploreAll section
}
```

---

## 4. API Specification

### New Endpoint: `GET /api/v1/properties/decision-feed`

**File:** `netlify/functions/decision-feed.mjs` (new file)

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `suburb` | string | (all target suburbs) | Filter to single suburb |

**Response Shape:**

```json
{
  "summary": {
    "total_properties": 127,
    "best_value_count": 9,
    "fair_value_count": 71,
    "premium_count": 22,
    "one_of_a_kind_count": 5,
    "last_updated": "2026-03-28T10:30:00.000Z",
    "suburbs": ["Robina", "Burleigh Waters", "Varsity Lakes"]
  },
  "feed_items": [
    { "type": "section_divider", "title": "Best Deals Right Now", "subtitle": "9 found" },
    { "type": "feed_card", "property": { /* FeedProperty */ } },
    { "type": "feed_card", "property": { /* FeedProperty */ } },
    { "type": "quiz_card", "quiz": { /* QuizConfig */ } },
    { "type": "feed_card", "property": { /* FeedProperty */ } },
    { "type": "surprise_card", "surprise": { /* SurpriseConfig */ } },
    { "type": "feed_card", "property": { /* FeedProperty */ } },
    { "type": "compare_card", "compare": { /* CompareConfig */ } },
    { "type": "quiz_card", "quiz": { /* QuizConfig */ } },
    { "type": "feed_card", "property": { /* FeedProperty */ } },
    { "type": "section_divider", "title": "Where to Be Careful" },
    { "type": "caution_block", "properties": [ /* CautionProperty[] */ ] },
    { "type": "lead_capture" }
  ],
  "all_properties": [
    { /* FeedProperty -- every active listing, sorted by feed_score */ }
  ]
}
```

**Netlify Function Config:**

```javascript
export const config = {
  path: [
    "/api/v1/properties/decision-feed",
    "/api/v1/properties/decision-feed/*",
  ],
};
```

### Modified Endpoint: `GET /api/v1/properties/for-sale`

No changes required to the existing endpoint. The decision feed endpoint is separate and self-contained. The existing `/for-sale` endpoint continues to serve the `ExploreAll` section if we decide to lazy-load it separately (Phase 2 optimization).

### MongoDB Query Strategy

The decision feed endpoint queries all target suburb collections (same pattern as existing `properties-for-sale.mjs`) with these additions to the projection:

```javascript
// Additional projection fields for decision feed
const feedProjection = {
  // ... all existing listProjection fields ...

  // AI analysis fields needed for hook/trade-off/quiz content
  'ai_analysis.headline': 1,
  'ai_analysis.verdict': 1,
  'ai_analysis.quick_take': 1,
  'ai_analysis.best_for': 1,
  'ai_analysis.not_ideal_for': 1,
  'ai_analysis.insights': 1,          // For quiz question generation
  'ai_analysis.sub_headline': 1,
  'ai_analysis.status': 1,
  'ai_analysis.cta_valuation': 1,

  // Valuation fields for classification
  'valuation_data.summary.positioning': 1,
  'valuation_data.summary.value_gap_pct': 1,
  'valuation_data.confidence.reconciled_valuation': 1,
  'valuation_data.confidence.confidence': 1,
  'valuation_data.confidence.range': 1,

  // Condition score for compare cards
  'property_valuation_data.condition_summary.overall_score': 1,
};
```

**Aggregation/count by classification:**

Classification is computed in JavaScript after fetch (not a Mongo aggregation), because `value_gap_pct` lives in a nested field and price is stored as a string. Same pattern as existing sort logic.

```javascript
// Count by classification
const counts = { best_value: 0, fair_value: 0, premium: 0, one_of_a_kind: 0, unclassified: 0 };
for (const doc of allDocs) {
  const cls = classifyProperty(doc);
  counts[cls]++;
}
```

---

## 5. Backend Classification Logic

### Classification from `value_gap_pct`

```javascript
/**
 * Classify a property based on its value gap percentage.
 * value_gap_pct = (asking_price - reconciled_valuation) / reconciled_valuation
 *   Negative = below valuation (good value)
 *   Positive = above valuation (premium)
 *
 * @param {Object} doc - Raw MongoDB document
 * @returns {string} Classification: 'best_value' | 'fair_value' | 'premium' | 'one_of_a_kind' | 'unclassified'
 */
function classifyProperty(doc) {
  const valSummary = (doc.valuation_data || {}).summary || {};
  const valueGapPct = valSummary.value_gap_pct;
  const positioning = valSummary.positioning;
  const conditionScore = (doc.property_valuation_data || {}).condition_summary?.overall_score;
  const priceNumeric = parsePriceString(doc.price || doc.price_display || '');

  // No valuation data = unclassified
  if (valueGapPct == null || priceNumeric == null) {
    return 'unclassified';
  }

  // One of a Kind: exceptional properties regardless of price
  // - waterfront + condition >= 8
  // - or explicitly flagged in ai_analysis
  const isWaterfrontProp = isWaterfront(doc);
  if (isWaterfrontProp && conditionScore >= 8) {
    return 'one_of_a_kind';
  }

  // Best Value: asking price is meaningfully below comparable-adjusted value
  // value_gap_pct <= -0.10 (10% or more below valuation)
  if (valueGapPct <= -0.10) {
    return 'best_value';
  }

  // Premium: asking price is meaningfully above comparable-adjusted value
  // value_gap_pct >= 0.15 (15% or more above valuation)
  if (valueGapPct >= 0.15) {
    return 'premium';
  }

  // Fair Value: everything in between (-10% to +15%)
  return 'fair_value';
}
```

### Feed Score Calculation

The feed score determines which properties appear in the curated feed (top N) and in what order. Higher = more likely to appear.

```javascript
/**
 * Calculate a feed score (0-100) for a property.
 * Composed of 5 signals, each 0-20.
 *
 * @param {Object} doc - Raw MongoDB document
 * @param {string} classification - Result of classifyProperty()
 * @returns {number} Score 0-100
 */
function calcFeedScore(doc, classification) {
  let score = 0;

  // 1. VALUE SIGNAL (0-20): How interesting is the value proposition?
  const valueGapPct = (doc.valuation_data || {}).summary?.value_gap_pct;
  if (valueGapPct != null) {
    // Best value: bigger negative gap = higher score
    // Premium: bigger positive gap = higher score (noteworthy)
    const absGap = Math.abs(valueGapPct);
    score += Math.min(20, Math.round(absGap * 50)); // 40% gap = 20 points
  }

  // 2. CLARITY SIGNAL (0-20): How much editorial content exists?
  const ai = doc.ai_analysis || {};
  let clarity = 0;
  if (ai.headline) clarity += 5;
  if (ai.verdict) clarity += 5;
  if (ai.quick_take?.trade_off) clarity += 5;
  if (ai.best_for && ai.best_for.length > 0) clarity += 3;
  if (ai.insights && ai.insights.length >= 3) clarity += 2;
  score += Math.min(20, clarity);

  // 3. CURIOSITY SIGNAL (0-20): Does this property have an interesting story?
  let curiosity = 0;
  const conditionScore = (doc.property_valuation_data || {}).condition_summary?.overall_score || 0;
  if (conditionScore >= 8) curiosity += 5;            // High condition = interesting
  if (isWaterfront(doc)) curiosity += 5;              // Waterfront premium
  const features = Array.isArray(doc.features) ? doc.features : [];
  if (features.some(f => /pool/i.test(f))) curiosity += 3;
  if (doc.days_on_domain >= 90) curiosity += 4;       // Stale listing = story
  const priceHistory = ((doc.history || {}).price) || [];
  if (priceHistory.length > 0) curiosity += 3;        // Price changed = story
  score += Math.min(20, curiosity);

  // 4. TRUST SIGNAL (0-20): How confident is our data?
  let trust = 0;
  const confidence = (doc.valuation_data || {}).confidence?.confidence;
  if (confidence === 'High') trust += 10;
  else if (confidence === 'Medium') trust += 6;
  else if (confidence === 'Low') trust += 3;
  const priceNumeric = parsePriceString(doc.price || '');
  if (priceNumeric != null) trust += 5;               // Has numeric price
  if (doc.floor_area_sqm || (doc.enriched_data || {}).floor_area_sqm) trust += 5;
  score += Math.min(20, trust);

  // 5. FRESHNESS SIGNAL (0-20): Newer listings get a boost
  const dom = doc.days_on_domain || doc.days_on_market || 999;
  if (dom <= 7) score += 20;
  else if (dom <= 14) score += 15;
  else if (dom <= 30) score += 10;
  else if (dom <= 60) score += 5;
  // 60+ days: 0 freshness points

  return Math.min(100, score);
}
```

### Fallback Classification When No Numeric Price

When a property has `price_display = "Contact Agent"` or another non-numeric string, `value_gap_pct` cannot be computed. These properties are classified as `unclassified` and will appear in the ExploreAll section but not in the curated feed cards.

If a property has `reconciled_valuation` but no numeric asking price, it still cannot be classified because the gap requires both values.

---

## 6. Feed Assembly Algorithm

### Pseudocode

```
function assembleFeed(allProperties: FeedProperty[]): FeedItem[] {
  // 1. Separate by classification
  bestValue  = allProperties.filter(p => p.classification === 'best_value')
                             .sort((a,b) => b.feed_score - a.feed_score)
  premium    = allProperties.filter(p => p.classification === 'premium')
                             .sort((a,b) => b.feed_score - a.feed_score)
  unique     = allProperties.filter(p => p.classification === 'one_of_a_kind')
                             .sort((a,b) => b.feed_score - a.feed_score)

  // 2. Select featured properties for the feed
  //    - Up to 3 best-value cards
  //    - Up to 1 premium card (trust builder -- shows we flag overpriced too)
  //    - Up to 1 one-of-a-kind card
  //    Total: 5 feed cards max (+ caution block for remaining premium)

  featuredBestValue = bestValue.slice(0, 3)
  featuredPremium   = premium.slice(0, 1)
  featuredUnique    = unique.slice(0, 1)

  // 3. Apply diversity constraint: no same suburb twice in a row
  feedCards = interleaveWithDiversity(
    featuredBestValue, featuredPremium, featuredUnique
  )

  // 4. Select quiz candidates
  //    - "Spot the Catch": pick a best-value property with ai_analysis.quick_take.trade_off
  //    - "Would You Buy": pick a property with high curiosity (long DOM, price drops, or unique features)
  quizCandidates = allProperties.filter(p =>
    p.hook && p.trade_off && p.classification !== 'unclassified'
  )
  spotTheCatch = buildSpotTheCatchQuiz(quizCandidates[0])  // if available
  wouldYouBuy  = buildWouldYouBuyQuiz(quizCandidates[1])   // if available

  // 5. Select compare pair
  //    - Two properties in the same suburb with different prices
  //    - Both must have condition_score and floor_area
  comparePair = findComparePair(allProperties)

  // 6. Build surprise card
  //    - Static content: overpay simulator using median best-value gap
  medianGap = median(bestValue.map(p => Math.abs(p.value_gap_pct)))
  surpriseCard = buildOverpaySimulator(medianGap)

  // 7. Assemble the feed in order
  items = []
  items.push({ type: 'section_divider', title: 'Best Deals Right Now', subtitle: `${bestValue.length} found` })
  items.push({ type: 'feed_card', property: feedCards[0] })  // Best value #1
  items.push({ type: 'feed_card', property: feedCards[1] })  // Premium (trust builder)
  items.push({ type: 'quiz_card', quiz: spotTheCatch })      // If available
  items.push({ type: 'feed_card', property: feedCards[2] })  // Best value #2 (different suburb)
  items.push({ type: 'surprise_card', surprise: surpriseCard })
  items.push({ type: 'feed_card', property: feedCards[3] })  // Unique
  items.push({ type: 'compare_card', compare: comparePair }) // If available
  items.push({ type: 'quiz_card', quiz: wouldYouBuy })       // If available
  items.push({ type: 'feed_card', property: feedCards[4] })  // Best value #3 (different suburb)
  items.push({ type: 'section_divider', title: 'Where to Be Careful' })
  items.push({ type: 'caution_block', properties: premium.slice(0, 5) })
  items.push({ type: 'lead_capture' })

  // 8. Remove null items (when quiz/compare not available)
  return items.filter(Boolean)
}
```

### Diversity Constraint

```
function interleaveWithDiversity(bestValue, premium, unique) {
  // Merge all featured cards
  const all = [
    ...bestValue.map(p => ({ ...p, _source: 'best_value' })),
    ...premium.map(p => ({ ...p, _source: 'premium' })),
    ...unique.map(p => ({ ...p, _source: 'unique' })),
  ]

  // Sort by feed_score descending
  all.sort((a, b) => b.feed_score - a.feed_score)

  // Apply constraint: no same suburb twice in a row
  const result = []
  const remaining = [...all]

  while (remaining.length > 0) {
    const lastSuburb = result.length > 0 ? result[result.length - 1].suburb : null

    // Find first property not in lastSuburb
    const idx = remaining.findIndex(p => p.suburb !== lastSuburb)

    if (idx >= 0) {
      result.push(remaining.splice(idx, 1)[0])
    } else {
      // No choice -- allow same suburb
      result.push(remaining.shift())
    }
  }

  return result
}
```

### Quiz Content Generation

```
function buildSpotTheCatchQuiz(property) {
  if (!property || !property.trade_off) return null

  const ai = property._raw_ai_analysis  // full ai_analysis from DB
  const tradeOff = ai?.quick_take?.trade_off || property.trade_off

  // Extract the "catch" as the correct answer
  // Generate 3 plausible but wrong options
  // This is deterministic based on property data:
  const wrongOptions = generateWrongOptions(property)

  return {
    id: `quiz_stc_${property.id}`,
    variant: 'spot_the_catch',
    property_id: property.id,
    property_url_slug: property.url_slug,
    property_address: property.address,
    question: `${property.address} -- ${property.bedrooms} bed, ...`,
    options: shuffle([
      { text: extractCatchSummary(tradeOff), is_correct: true },
      ...wrongOptions.map(text => ({ text, is_correct: false })),
    ]),
    result_correct: {
      title: 'Correct',
      text: tradeOff,
      cta_label: `See ${shortAddress(property.address)} analysis`,
      cta_url: propertyPath(property.id, property.address, property.suburb, property.url_slug),
    },
    result_wrong: {
      title: `Not quite -- ${extractCatchSummary(tradeOff).toLowerCase()}`,
      text: tradeOff,
      cta_label: `See ${shortAddress(property.address)} analysis`,
      cta_url: propertyPath(property.id, property.address, property.suburb, property.url_slug),
    },
  }
}
```

**Important:** Quiz content is assembled server-side from `ai_analysis` fields. The frontend receives the fully-formed `QuizConfig` and only handles interaction state.

---

## 7. CSS Architecture

### Design Tokens (CSS Custom Properties)

The mockup defines its own token set. These must be mapped to Fields' existing design system variables where possible, with new tokens added for feed-specific values.

```css
/* Add to :root in the existing global styles or in a feed-specific module */
:root {
  /* Existing Fields tokens (already defined in global CSS) */
  /* --fields-grass: #22382c   */
  /* --fields-copper: #b76749  */
  /* --card: #fff              */
  /* --radius-lg: 14px         */
  /* --shadow-soft: ...        */
  /* --font-mono: ...          */

  /* New tokens for Decision Feed */
  --feed-dark: #1a1a1a;
  --feed-mid: #555;
  --feed-light: #999;
  --feed-cream: #FAF8F5;
  --feed-border: #e8e4df;
  --feed-green: #2e7d32;
  --feed-green-bg: #e8f5e3;
  --feed-red: #c62828;
  --feed-red-bg: #fce8e8;
  --feed-amber: #e65100;
  --feed-amber-bg: #fff3e0;
  --feed-copper: #B87333;
  --feed-radius: 14px;
  --feed-radius-sm: 10px;
  --feed-shadow: 0 2px 16px rgba(0,0,0,0.08);
  --feed-shadow-lg: 0 8px 40px rgba(0,0,0,0.12);
}
```

### Mobile-First Breakpoints

The mockup is designed mobile-first (single column). Breakpoints add horizontal padding and max-width constraints:

```css
/* Mobile: default (< 640px) */
.feed { padding: 0 0 100px; }
.feedCard { margin: 12px 14px; }

/* Tablet: 640px+ */
@media (min-width: 640px) {
  .feedCard { margin: 12px auto; max-width: 540px; }
  .hero { padding: 40px 32px 36px; }
}

/* Desktop: 1024px+ */
@media (min-width: 1024px) {
  .feedCard { max-width: 600px; }
  .hero h1 { font-size: 36px; }
  /* ExploreAll section can optionally go 2-column grid */
  .miniList {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    max-width: 1000px;
    margin: 0 auto;
  }
}
```

### Animation Specifications

```css
/* Fade-up on mount (hero elements) */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.fadeUp { animation: fadeUp 0.5s ease forwards; }
.delay1 { animation-delay: 0.1s; opacity: 0; }
.delay2 { animation-delay: 0.2s; opacity: 0; }
.delay3 { animation-delay: 0.3s; opacity: 0; }

/* Tap-to-reveal (FeedCard) */
.reveal {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height 0.4s ease, opacity 0.3s ease;
}
.revealOpen {
  max-height: 600px;
  opacity: 1;
}

/* Quiz result reveal */
.quizResult {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: all 0.4s ease;
}
.quizResultShow {
  max-height: 300px;
  opacity: 1;
  margin-top: 14px;
}

/* Progress bar fill */
.progressFill {
  transition: width 0.4s ease;
}

/* Card press feedback */
.feedCard:active { transform: scale(0.985); }
.quizOption:active { border-color: var(--fields-grass); background: var(--feed-green-bg); }

/* Pulse animation for loading states */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
```

---

## 8. State Management

### Page-Level State (ForSalePage)

| State | Type | Purpose |
|-------|------|---------|
| `feedData` | `DecisionFeedResponse | null` | Full API response |
| `loading` | `boolean` | Initial load state |
| `error` | `string | null` | Error message |
| `dealsViewed` | `number` | Count of revealed best-value cards |
| `revealedCards` | `Set<string>` | Property IDs that have been revealed |
| `quizAnswers` | `Record<string, QuizAnswer>` | Quiz ID -> answer state |
| `activeFilters` | `ExploreFilters` | ExploreAll filter state |
| `expandedCautions` | `Set<string>` | Expanded caution item IDs |
| `progressVisible` | `boolean` | Whether progress bar is shown (scroll > 400px) |

### Card-Level State

Card-level state is NOT managed locally -- it is passed down from `ForSalePage` via props. This ensures:
1. Progress bar accurately reflects total reveals
2. State survives re-renders
3. PostHog events fire from a single source of truth

### URL State

URL parameters for the ExploreAll section filters (optional, for shareable links):

```
/for-sale?classification=best_value&suburb=robina&type=house
```

Parsing:
```typescript
const searchParams = useSearchParams();
const initialFilters: ExploreFilters = {
  classification: (searchParams.get('classification') as ExploreFilters['classification']) || 'all',
  suburb: searchParams.get('suburb') || undefined,
  property_type: searchParams.get('type') || undefined,
};
```

### PostHog Integration

All events fire through `phCapture()` from `src/utils/posthog.ts`. Events are dispatched from `ForSalePage` handler functions, not from individual components. This prevents duplicate events and ensures consistent property metadata.

---

## 9. Event Tracking Specification

### PostHog Events

| Event Name | Trigger | Payload |
|------------|---------|---------|
| `decision_feed_view` | Page mount | `{ total_properties, best_value_count, premium_count, suburbs }` |
| `feed_card_reveal` | User taps "See why" on a FeedCard | `{ property_id, property_address, suburb, classification, feed_position, value_gap_pct }` |
| `feed_card_click` | User taps "Full analysis" on a FeedCard | `{ property_id, property_address, suburb, classification, was_revealed }` |
| `quiz_answer` | User selects a quiz option | `{ quiz_id, quiz_variant, property_id, selected_option, is_correct, answer_key }` |
| `compare_view` | CompareCard enters viewport | `{ compare_id, property_a_id, property_b_id, suburb }` |
| `compare_click` | User clicks a CompareCard CTA | `{ compare_id, property_id, side: 'a' or 'b' }` |
| `caution_expand` | User taps a caution item | `{ property_id, property_address, value_gap_pct, days_on_market }` |
| `filter_apply` | User changes an ExploreAll filter pill | `{ filter_type: 'classification' or 'suburb' or 'type', filter_value, result_count }` |
| `progress_milestone` | dealsViewed reaches 3, 5, 7, 9 | `{ deals_viewed, total_deals }` |
| `lead_cta_click` | User clicks "Analyse my property" or "Talk" | `{ cta_type: 'analyse' or 'talk' }` |
| `hero_cta_click` | User clicks "Start with the best deals" | `{}` |
| `hero_verdict_click` | User clicks a verdict pill | `{ classification }` |
| `mini_list_click` | User clicks a MiniListItem | `{ property_id, property_address, classification, list_position }` |
| `surprise_card_view` | SurpriseCard enters viewport | `{ surprise_id }` |

### Scroll Depth and Time on Page

Reuse existing patterns:
```typescript
const cleanupScroll = phTrackScrollDepth('decision_feed', { total_properties: feedData.summary.total_properties });
const cleanupTime = phTrackTimeOnPage('decision_feed', [10, 30, 60, 120, 300], {});
```

### Meta / Google Ads Attribution

Same as current ForSalePage:
```typescript
trackMetaEvent("ViewContent", {
  content_name: "Decision Feed",
  content_category: "listings",
  content_type: "product_group",
});
trackGoogleConversion("property_search");
```

---

## 10. Performance Requirements

### LCP Target

- **Target:** < 2.5 seconds on mobile 3G
- **Strategy:** The hero section renders immediately from static content (counts from API). First FeedCard image is `loading="eager"` with `fetchPriority="high"`.

### Image Loading Strategy

```typescript
// FeedCard:
const isAboveFold = index < 2;  // First 2 cards load eagerly
<img
  src={property.main_image_url}
  loading={isAboveFold ? 'eager' : 'lazy'}
  fetchPriority={isAboveFold ? 'high' : undefined}
  width={600}
  height={220}
  alt={property.address}
/>

// MiniListItem: ALL lazy (below fold by definition)
<img src={property.main_image_url} loading="lazy" width={72} height={72} />

// CompareCard: lazy
// QuizCard: no images
```

### Skeleton/Loading States

While `loading === true`, render:
1. Hero skeleton: dark rectangle with pulsing opacity
2. 3 card skeletons: white rectangles with pulsing image placeholders
3. No text content shown until data arrives

```typescript
if (loading) {
  return (
    <>
      <SiteHeader />
      <div className={styles.skeleton}>
        <div className={styles.heroSkeleton} />
        <div className={styles.cardSkeleton} />
        <div className={styles.cardSkeleton} />
        <div className={styles.cardSkeleton} />
      </div>
      <SiteFooter />
    </>
  );
}
```

### Bundle Size

- The `DecisionFeed` components should be code-split via `React.lazy()` if the total component JS exceeds 30KB gzipped
- The existing `PropertyGrid`, `PropertyFilters`, `SoldPropertyGrid` imports should be removed from ForSalePage to reduce the bundle

### API Response Size

The `all_properties` array will contain ~127 items at ~500 bytes each = ~63KB. This is acceptable for a single fetch. The `feed_items` array adds ~5KB.

**Cache headers:** `Cache-Control: public, max-age=300, s-maxage=300` (5 minute cache, same as existing endpoint).

---

## 11. Migration Plan

### Phase 1: New API Endpoint + Classification Logic

**Duration:** 1 session

1. Create `netlify/functions/decision-feed.mjs`
2. Implement `classifyProperty()`, `calcFeedScore()`, `assembleFeed()`
3. Implement quiz/compare/surprise content generation
4. Test via curl: `curl https://fieldsestate.com.au/api/v1/properties/decision-feed | jq .summary`
5. Push to GitHub (Netlify auto-deploys the function)

**Files created:**
- `netlify/functions/decision-feed.mjs`

### Phase 2: New React Components

**Duration:** 2-3 sessions

1. Create `src/types/decisionFeed.ts`
2. Create `src/services/decisionFeedService.ts`
3. Create all component files in `src/components/DecisionFeed/`
4. Create CSS modules for each component
5. Wire up ForSalePage to use new components
6. Test locally with `npm run dev`

**Feature flag:** Use PostHog feature flag `decision_feed_v1` to gate rollout:
```typescript
const [useDecisionFeed, setUseDecisionFeed] = useState(false);

useEffect(() => {
  phOnFlagsReady(() => {
    const flag = phGetFlag('decision_feed_v1');
    setUseDecisionFeed(flag === true || flag === 'test');
  });
}, []);

if (useDecisionFeed) {
  return <DecisionFeedPage />;
} else {
  return <LegacyForSalePage />;
}
```

### Phase 3: Replace ForSalePage, Remove Old A/B Test Code

**Duration:** 1 session

1. Remove feature flag -- Decision Feed becomes the default
2. Remove A/B test variant code (`test_a`, `test_b`, `test_c` branches)
3. Move `/recently-sold` tab to its own route component `RecentlySoldPage`
4. Remove unused imports: `PropertyGrid`, `PropertyFilters`, `SoldPropertyGrid` from ForSalePage
5. Delete PostHog feature flag `for_sale_page_v1` (old A/B test)
6. Update JSON-LD to reflect new page structure
7. Push all changes to GitHub

### Rollback Plan

If the Decision Feed causes issues:
1. Set `decision_feed_v1` flag to `false` in PostHog dashboard -> instant rollback
2. The old ForSalePage code remains in the codebase until Phase 3 is complete

---

## 12. Data Dependencies

### Required Fields Per Card Type

| Card Type | Required Fields | Source |
|-----------|----------------|--------|
| **FeedCard** | `address`, `suburb`, `main_image_url`, `price_display`, `bedrooms`, `bathrooms`, `classification`, `hook` | Core listing fields + `ai_analysis.headline` or `ai_analysis.quick_take.trade_off` |
| **FeedCard (reveal)** | `trade_off`, `best_for` | `ai_analysis.quick_take.trade_off`, `ai_analysis.best_for` |
| **QuizCard (spot_the_catch)** | `hook`, `trade_off`, `ai_analysis.insights[*].key_points` | Full `ai_analysis` object |
| **QuizCard (would_you_buy)** | `verdict`, `trade_off` | `ai_analysis.verdict`, `ai_analysis.quick_take` |
| **CompareCard** | `condition_score`, `floor_area`, `price_numeric`, `main_image_url` for both properties | `property_valuation_data.condition_summary.overall_score`, `enriched_data.floor_area_sqm` |
| **CautionBlock** | `address`, `value_gap_pct`, `days_on_market` | `valuation_data.summary.value_gap_pct` |
| **MiniListItem** | `address`, `suburb`, `main_image_url`, `price_display`, `bedrooms`, `classification`, `hook` | Same as FeedCard |

### Minimum Data Coverage

| Requirement | Current Status | Notes |
|-------------|---------------|-------|
| `ai_analysis` on active listings | ~30-40% coverage | Run `--backfill` to increase before launch |
| `valuation_data` on active listings | ~70% coverage | Properties without valuation are `unclassified` |
| `condition_score` | ~50% coverage | Only needed for CompareCard and curiosity signal |
| `floor_area` | ~60% coverage | Enrichment step provides this |

**Minimum viable feed:** The feed can be assembled with as few as 3 properties with `ai_analysis`. The algorithm gracefully degrades:
- < 3 best-value properties with `hook` -> fewer feed cards, no quiz
- 0 compare-eligible pairs -> no CompareCard
- 0 quiz-eligible properties -> no QuizCard

### Fallback Behavior When `ai_analysis` Is Missing

```javascript
function buildFeedProperty(doc, suburbName) {
  const ai = doc.ai_analysis || {};
  const quickTake = ai.quick_take || {};

  // Hook: prefer ai_analysis.headline, fall back to auto-generated
  let hook = ai.headline || null;
  if (!hook && doc.valuation_data?.summary?.value_gap_pct != null) {
    const gapPct = Math.abs(doc.valuation_data.summary.value_gap_pct);
    const gapDir = doc.valuation_data.summary.value_gap_pct < 0 ? 'below' : 'above';
    hook = `Asking ${Math.round(gapPct * 100)}% ${gapDir} our comparable-adjusted range.`;
  }

  // Trade-off: prefer ai_analysis, fall back to null (reveal section hidden)
  const tradeOff = quickTake.trade_off || null;

  // Best-for: prefer ai_analysis, fall back to empty (chips hidden)
  const bestFor = ai.best_for || null;

  // Verdict: prefer ai_analysis, fall back to null
  const verdict = ai.verdict || null;

  // Strengths from quick_take
  const strengths = quickTake.strengths || null;

  return {
    // ... core fields from buildListSummary() ...
    hook,
    trade_off: tradeOff,
    best_for: bestFor,
    verdict,
    strengths,
  };
}
```

**Card rendering when fields are missing:**
- No `hook` -> FeedCard is excluded from the curated feed (still appears in ExploreAll)
- No `trade_off` -> "See why" button is hidden, card has no reveal section
- No `best_for` -> Best-for chips are hidden
- No `condition_score` -> CompareCard omits the Condition row

### Handling Properties with Insufficient Valuation Data

Properties without `valuation_data.summary.value_gap_pct`:
1. Classified as `unclassified`
2. Excluded from the curated feed (not shown as FeedCards)
3. Shown in ExploreAll section under "All" filter
4. MiniListItem renders without a classification badge
5. Not counted in hero verdict pills (they only count classified properties)

---

## 13. File Manifest

### New Files (to create)

All paths are relative to the **GitHub repo root** (`Will954633/Website_Version_Feb_2026`):

| # | File Path | Description |
|---|-----------|-------------|
| 1 | `src/types/decisionFeed.ts` | All TypeScript interfaces and types |
| 2 | `src/services/decisionFeedService.ts` | API client for decision feed endpoint |
| 3 | `src/components/DecisionFeed/HeroSection.tsx` | Dark hero with verdict pills |
| 4 | `src/components/DecisionFeed/HeroSection.module.css` | Hero styles |
| 5 | `src/components/DecisionFeed/StickyProgressBar.tsx` | Scroll-activated progress indicator |
| 6 | `src/components/DecisionFeed/StickyProgressBar.module.css` | Progress bar styles |
| 7 | `src/components/DecisionFeed/DecisionFeed.tsx` | Feed container rendering FeedItems |
| 8 | `src/components/DecisionFeed/DecisionFeed.module.css` | Feed container styles |
| 9 | `src/components/DecisionFeed/FeedCard.tsx` | Property card with tap-to-reveal |
| 10 | `src/components/DecisionFeed/FeedCard.module.css` | Feed card styles |
| 11 | `src/components/DecisionFeed/QuizCard.tsx` | Interactive quiz component |
| 12 | `src/components/DecisionFeed/QuizCard.module.css` | Quiz styles |
| 13 | `src/components/DecisionFeed/CompareCard.tsx` | Side-by-side comparison |
| 14 | `src/components/DecisionFeed/CompareCard.module.css` | Compare styles |
| 15 | `src/components/DecisionFeed/SurpriseCard.tsx` | Data surprise/insight |
| 16 | `src/components/DecisionFeed/SurpriseCard.module.css` | Surprise styles |
| 17 | `src/components/DecisionFeed/SectionDivider.tsx` | Section heading separator |
| 18 | `src/components/DecisionFeed/SectionDivider.module.css` | Divider styles |
| 19 | `src/components/DecisionFeed/CautionBlock.tsx` | Overpriced property warnings |
| 20 | `src/components/DecisionFeed/CautionBlock.module.css` | Caution styles |
| 21 | `src/components/DecisionFeed/LeadCapture.tsx` | CTA card |
| 22 | `src/components/DecisionFeed/LeadCapture.module.css` | Lead capture styles |
| 23 | `src/components/DecisionFeed/ExploreAllSection.tsx` | Full listing section with filters |
| 24 | `src/components/DecisionFeed/ExploreAllSection.module.css` | Explore section styles |
| 25 | `src/components/DecisionFeed/FilterPills.tsx` | Classification/suburb/type pills |
| 26 | `src/components/DecisionFeed/FilterPills.module.css` | Filter pill styles |
| 27 | `src/components/DecisionFeed/MiniListItem.tsx` | Compact property row |
| 28 | `src/components/DecisionFeed/MiniListItem.module.css` | Mini list styles |
| 29 | `src/components/DecisionFeed/index.ts` | Barrel export for all components |
| 30 | `netlify/functions/decision-feed.mjs` | Backend API endpoint |

### Modified Files

| # | File Path | Changes |
|---|-----------|---------|
| 31 | `src/pages/ForSalePage/ForSalePage.tsx` | Replace current implementation with Decision Feed (Phase 2), add feature flag gate |
| 32 | `src/pages/ForSalePage/ForSalePage.module.css` | Replace with new styles or import feed module styles |

### Files to Delete (Phase 3)

| # | File Path | Reason |
|---|-----------|--------|
| - | None deleted | Old components (`PropertyGrid`, `PropertyCard`, etc.) remain -- they are used by other pages or may be reused for `/recently-sold` |

### Local Files (not pushed to GitHub)

| File | Purpose |
|------|---------|
| `Fields_Orchestrator/06_Listing-Scroll-Concept/02-DEVELOPMENT-SPEC.md` | This specification |
| `Fields_Orchestrator/drafts/for-sale-v2.html` | Design mockup |

---

## Appendix A: Overpay Simulator Calculation

The SurpriseCard uses a mortgage cost calculation to dramatize the cost of overpaying:

```javascript
function buildOverpaySimulator(medianOverpayAmount) {
  // Default to $200K if not enough data
  const overpay = medianOverpayAmount || 200000;
  const rate = 0.062;  // Current Australian variable rate benchmark
  const years = 30;
  const monthlyRate = rate / 12;
  const payments = years * 12;

  // Monthly payment on the overpay amount alone
  const monthlyExtra = overpay * (monthlyRate * Math.pow(1 + monthlyRate, payments)) /
                       (Math.pow(1 + monthlyRate, payments) - 1);
  const totalExtra = monthlyExtra * payments;

  return {
    id: 'surprise_overpay',
    emoji: '\uD83D\uDCB8',  // money-with-wings emoji
    title: `What overpaying $${Math.round(overpay / 1000)}K actually costs`,
    subtitle: `On a ${years}-year mortgage at ${(rate * 100).toFixed(1)}%`,
    big_number: `+$${Math.round(monthlyExtra).toLocaleString()}/mo`,
    footnote: `$${Math.round(totalExtra).toLocaleString()} extra over the life of the loan`,
  };
}
```

## Appendix B: Wrong Quiz Option Generation

For "Spot the Catch" quizzes, three plausible wrong options are generated from property data:

```javascript
function generateWrongOptions(property) {
  const options = [];

  // Option pool (generic plausible reasons for value gaps)
  const pool = [
    'Smaller land than competitors',
    'Poor location',
    'Needs major renovation',
    'No pool',
    'Traffic noise',
    'Flood zone',
    'Steep block',
    'Outdated kitchen',
    'Single garage only',
    'Body corporate fees',
    'No air conditioning',
    'Small backyard',
    'North-south orientation',
    'Termite history',
  ];

  // Filter out options that match the actual catch
  // (crude text matching -- good enough for v1)
  const catchLower = (property.trade_off || '').toLowerCase();
  const filtered = pool.filter(opt => {
    const optLower = opt.toLowerCase();
    // Exclude if key words overlap
    return !catchLower.includes(optLower.split(' ')[0].toLowerCase());
  });

  // Shuffle and pick 3
  const shuffled = filtered.sort(() => Math.random() - 0.5);
  return shuffled.slice(0, 3);
}
```

---

*End of specification. Reference the live mockup at https://fieldsestate.com.au/for-sale-v2.html for visual design intent.*
