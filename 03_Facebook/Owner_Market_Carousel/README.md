# Owner-Market Carousel — Facebook campaign

**Status (2026-08-26):** creative rendered, landing pages LIVE, **campaign not yet created.**
Next step is to build the three ad sets in Meta **PAUSED**. Nothing is spending.

Owner: Will Simpson. A homeowner-targeted carousel that runs the Owner-Subject
article narrative (national turn → Gold Coast holding → will it turn → answered) and
drives to a per-suburb landing page where the owner opens the analysis for their own home.

---

## 1. The three geofenced ad sets (one per suburb)

| Suburb | Postcode | Landing page | Aerial on card 01 |
|---|---|---|---|
| Robina | 4226 | `https://fieldsestate.com.au/find/robina` | 16 Cheltenham Dr (sample) |
| Varsity Lakes | 4227 | `https://fieldsestate.com.au/find/varsity-lakes` | 11 Placid Ct (sample) |
| Burleigh Waters | 4220 | `https://fieldsestate.com.au/find/burleigh-waters` | 3 Fimiston Pl (sample) |

Each ad set is **geofenced to its one suburb + a tight radius** so the ad and its landing
page always match. Campaign objective: Leads / traffic. Start **PAUSED**, budget caps per the
FB experimentation playbook. Ad-decision logging (`system_monitor.ad_decisions`) is mandatory
on create.

## 2. The creative — `cards/`

5 cards × 3 suburbs = **15 PNGs at 1080×1080**, rendered by `render_cards.py`
(system Chrome + Playwright, 2× then downscaled). Only cards 01 (aerial + suburb) and 02
(suburb name) vary by suburb; 03/04/05 are identical but rendered per set so each ad set
gets a complete 5-image set.

| Card | Content |
|---|---|
| 01 | Hook — aerial + "Prices are falling. Is your home next?" |
| 02 | "We tracked your home's estimated value over 18 months — against {Suburb}'s wider market" + trajectory motif |
| 03 | Will Simpson portrait + quote |
| 04 | Three questions answered (why turned / why GC holding / will GC turn) |
| 05 | CTA — "See where your home stands now" + Find your home → |

Re-render: `python3 render_cards.py` (regenerates all 15 from `assets.json`).

**Post copy / targeting / A-B ideas** live in the concept board (Claude artifact, 2026-08-26).
Primary text leads on Sydney/Melbourne/Brisbane, "search your address at fieldsestate.com.au",
button **Learn More**. No `$` figures anywhere (stays clear of the FB single-valuation rule).

## 3. The landing pages — `/find/:suburb` (LIVE, commit d639a062)

Website repo `Will954633/Website_Version_Feb_2026`:
- `src/pages/FindYourHomePage/FindYourHomePage.tsx` + `.module.css`
- `src/routes/find.$suburb.tsx` (meta/SEO **noindex,follow**, ErrorBoundary, cdnCache)
- `src/routes.ts` (route `find/:suburb?`)

Two options on the page:
1. **Enter address** → reuses `AnalyseYourHomePage.handleAddressSelected` verbatim: `AddressSearch`
   → `POST /api/v1/analyse-your-home-submit` → for the measured suburbs `navigate('/off-market/<slug>')`.
   Handles currently-listed (→ `/property/:id`) and out-of-suburb (→ mini-site build) exactly as the
   proven flow does.
2. **Google your address** — an *illustration* of the Google result (fictitious "29 Example St").
   Off-market pages are indexed (avg position 6.7, page 1), so the copy promises "**first page**,"
   NOT "top 3."

Styling = mailer_v2 house style (cream / forest green / terracotta), single light theme to match
the creative. Methodology + confidence disclaimer is deliberately visible.

### ⚠ Known gaps before spend
- **The "no page yet" state.** Units, waterfront and no-sale-history addresses are `noindex` and have
  no off-market page; currently-listed and out-of-envelope also miss. The submit flow redirects
  listed homes but a truly unresolvable address needs a friendly "we don't have an analysis for that
  address yet" path — not yet designed.
- **Aerials on cards are sample homes**, not the viewer's (a broadcast ad has no per-user address).
  Fine — they read as "a home in your suburb."
- Campaign not built. Do not create ad objects without Will's go-ahead + ad-decision logging.

## 4. Compliance (CLAUDE.md Rule 5)
No advice, no predictions, no single valuation figure. "Prices are falling" is anchored to the cities
that have (Sydney/Melbourne/Brisbane); the Gold Coast is stated as holding. All questions stay
conditional. Same rules apply to the post copy and the landing pages.
