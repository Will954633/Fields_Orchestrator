# User Journey — the first warm, returning visitor to read an off-market report end to end

**Visitor:** PostHog `distinct_id` / `$device_id` `019feb00-5692-7d6a-a478-9e642a9b4fa0`
**CRM:** `system_monitor.crm_contacts` `_id 66251069328bd0104f5f4096` — `engagement_score: 77`,
`status: "lead"`, **`name` / `email` / `phone` all `null`**
**Device:** Google Pixel 8a, Android, Chrome 151, `en-AU`, GeoIP Brisbane QLD
**Window:** Mon 10 Aug 2026 19:28 AEST → Tue 18 Aug 2026 19:33 AEST (8 days)
**Volume:** 4 sessions, 226 PostHog events, 10 distinct pages, plus 42 server-side report-viewer events
**Documented:** 2026-08-18

All times below are **AEST (UTC+10)**. PostHog and MongoDB both store UTC; every timestamp here has
been converted. Client-side (PostHog) and server-side (MongoDB) evidence are labelled separately —
they disagree on one material point, documented under *The download that wasn't*.

---

## Why this journey is worth a document

Across the entire life of the V4 off-market deck there have been **95 distinct visitors, 104 deck
views, 3 report requests and 2 report opens.** This visitor is one of the two opens — and the only
one of the three requesters who was not a cold, single-session, single-page arrival:

| Visitor | Sessions | Events | Pages | Requested | Opened report |
|---|---|---|---|---|---|
| `019ffd0b…` (13 Aug) | 1 | 22 | 1 | ✅ | ❌ |
| `01a00f16…` (17 Aug) | 1 | 21 | 1 | ✅ | ✅ |
| **`019feb00…` (this one)** | **4** | **226** | **10** | ✅ | ✅ **all 20 pages** |

So this is the **first observed instance of the intended funnel actually working end to end**: a
stranger arrives from search, spends real time across several first-party surfaces, leaves, comes
back a week later through search, converts on the deepest asset we publish, and reads it completely.

It is also the first evidence that the off-market deck earns a **returning** audience rather than
only intercepting cold search traffic.

---

## The four sessions

### Session 1 — Mon 10 Aug, 19:28–19:36 AEST (8 min, 23 events, 1 page)
`google.com` → `/property/3-corina-close-robina`

Landed cold from Google directly onto the property page for **3 Corina Close, Robina**. Stayed on
that single page for eight minutes. Scrolled to 75% depth in three stages over three minutes
(19:31 → 19:34), which is reading pace, not skimming.

At 19:35:08 the **Whale Moment** overlay fired on a `scroll_reversal` trigger (`season: 2026`,
`surface: /property/3-corina-close-robina`, `is_internal: false`). They dismissed it six seconds
later — and then, one second after dismissing, clicked a CTA:

```
cta_click  click_target: "valuation_info_scroll"  property_id: 3-corina-close-robina
```

They dismissed the whale and immediately went looking for **how the valuation was calculated**.

### Session 2 — Tue 11 Aug, 05:51–06:03 AEST (12 min, 100 events, 5 pages)
Returned ~10 hours later. This is the broad session — a tour of most of the site:

| Time | Page | Dwell |
|---|---|---|
| 05:51 | `/property/3-corina-close-robina` (again) | ~9 min, incl. a re-visit at 06:01 |
| 05:52 | `/for-sale` | ~3 min, scrolled to 75%, 23 interactions |
| 05:54 | `/property/7-jurien-crescent-varsity-lakes` | ~35 s |
| 05:55 | `/market-intelligence/Robina/buy` | ~6 min, scrolled to 75% |
| 06:01 | `/analyse-your-home` | ~40 s |

**The decisive moment is at 06:01:36.** On Analyse Your Home they typed their way to one address —
four keystroke-level `address_search` events, `"3 co"` → `"3 Corina "` → `"3 corina"` →
`"3 Corina cl"` — and submitted:

```
analyse_home_address_submit   address: "3 Corina Close, Robina, QLD 4226"
```

The same address they had arrived on from Google the night before. Four seconds later:

```
analyse_home_currently_listed  listed_property_id: 690bd89c8b8f54659264a66c
```

The **currently-listed guard** (`analyse-your-home-submit.mjs` → `findLiveListing()`, shipped
2026-07-31) fired correctly, refused to build a bespoke mini-site, and redirected them back to the
`/property/:id` editorial page. The session ended there.

### Session 3 — Tue 11 Aug, 16:26–16:30 AEST (4 min, 71 events, 5 pages)
`/property/3-corina-close-robina` → `/news/Burleigh-Waters` → `/for-sale-v3` → `/` → `/news`

The dense session. On `/for-sale-v3` they completed the preference ladder in 17 seconds:

```
forsale_ladder_answer  question: "suburbs"   value: ["Burleigh Waters"]
forsale_ladder_answer  question: "bedrooms"  value: ["4"]
forsale_ladder_answer  question: "special"   value: "yes"  (has_text: true)
forsale_ladder_optin   opted_in: FALSE
forsale_ladder_complete
```

PostHog redacts the free-text answer, but the server stores it —
`system_monitor.forsale_ladder_responses` `6a7ac0c5…` records `special: "Pool"`, `opt_in: "no"`.
**They want a 4-bedroom home with a pool in Burleigh Waters.**

They then consumed nearly every V3 section: `v3_seller_anchor_view` ×2, `v3_interaction_view` ×2,
`v3_big_mistake_view`, `v3_insight_view` ×2, `v3_compare_view`, `v3_value_reinforcement_view`,
`surprise_card_view`, 7 × `v3_card_impression`, 2 × `v3_filter_apply`.

**They told us what they want to buy — 4 bedrooms in Burleigh Waters — and declined to give
contact details in the same breath.**

### Session 4 — Tue 18 Aug, 19:27–19:31 AEST (4 min, 32 events, 1 page)
`google.com` → `/off-market/8-gum-court-burleigh-waters`

Seven days and three hours after session 3, they came back through Google and landed on the V4
off-market deck for **8 Gum Court, Burleigh Waters** — a 4-bedroom home in the exact suburb they
had named in the ladder a week earlier.

Engagement on this single page:

| Metric | Value |
|---|---|
| `engaged_seconds` / `wall_seconds` | **224 / 225** — 99.6% engaged |
| `sections_read` | **14** (18 × `v4_section_read`) |
| `max_scroll_pct` | 84% |
| `deepest_section` | `changed` (index 13) |
| `top_section` | `comps` — **42 s** |
| `scrolled_back` | **true** |
| `n_comps` shown | 48 |
| `valuation_method` | `engine`, `has_range: true` |

Time by section (seconds): `comps` 42, `stood-out` 35, `answer` 28, `timing` 21, `changed` 20,
`report` 16, `nearby` 16, `dispersion` 14, `buyer` 11, `hero` 9, `different` 6, `reliable` 3,
`now` 2, `which` 2.

Then the conversion, inside 6 seconds (client-side):

```
19:31:33.750  offmarket_report_requested   slug: 8-gum-court-burleigh-waters
19:31:36.534  offmarket_report_ready       path: "prebuilt"   waited_ms: 2848
19:31:39.792  offmarket_report_downloaded  surface: "viewer"
19:31:40.310  v4_report_exit               reason: "hidden"
```

The report was served from the **prebuilt** path — the one-shot precompute (built 14 Aug 08:41
UTC) worked, and they waited 2.8 seconds instead of a cold build.

### And then they read the whole thing

`v4_report_exit … reason: "hidden"` is the deck tab going to background — not the visitor leaving.
Server-side, `system_monitor.email_tracking` `tracking_id f7fd9fae-8ff` picks the story straight up:

```
19:31:39  viewer_opened
19:31:39 → 19:33:23   page_view × 20  (pages 1–20 — every page)
                      heartbeat × 20
19:33:23  session_end   total_time_seconds: 102   max_scroll_pct: 100
```

**They opened the report and read all twenty pages, to 100% scroll, in 1 minute 42 seconds.**

Total engaged time across the deck and the report: **326 seconds — 5½ minutes on one property.**

---

## The download that wasn't

The PostHog event is named `offmarket_report_downloaded`. **No PDF was downloaded.**

`server.py:334` defines a `pdf_downloaded` event type on route `/download/<tracking_id>`, and it
fires for five other tracking documents — so its absence here is a verified negative, not a missing
field name. What actually happened is `viewer_opened`: the client event fires when the in-page
viewer opens, and carries `surface: "viewer"` saying exactly that.

This matters for two reasons:

1. **Any funnel or count built on `offmarket_report_downloaded` is measuring viewer opens.** The
   event is misnamed and will overstate PDF downloads.
2. **The real outcome is better than the name suggests.** A download tells you nothing about
   whether the report was read. The viewer telemetry says it was read completely.

---

## What this tells us

**1. The valuation *method* is the product, not the number.** Twice, independently, they went
straight at the workings: the `valuation_info_scroll` CTA one second after dismissing the whale on
day 1, and `comps` as the single longest-read section (42 s of 224) on day 8. Nothing else in
either session comes close.

**2. The off-market deck holds attention that nothing else on the site holds.** 224 engaged
seconds on the deck with 99.6% engagement and a scroll-back, then 102 seconds through all 20 report
pages — 5½ minutes on a single property, against 4-to-12-minute sessions spread across five pages
everywhere else.

**3. Organic search is doing the re-acquisition, not us.** Both cold entries (day 1 and day 8)
came from `google.com`. We have no email, no phone, no lead record, and nothing that could have
pulled them back — they found us twice on their own. That is an SEO asset working, and
simultaneously a retargeting capability we do not have.

**4. We have their intent and not their identity.** They told us the suburb, the bedroom count and
"Pool" — then set `opt_in: "no"`. The report required no contact capture either. The CRM knows
exactly how valuable they are: `crm_contacts` scores them **77**, `status: "lead"`, tagged
`high_intent`, `repeat_visitor`, `returning`, `address_searcher`, `burleigh_waters_interest`,
`robina_interest`, `varsity_lakes_interest` — with `name`, `email` and `phone` all `null`.
**This is the highest-intent visitor the site has ever recorded and we cannot contact them.**

**5. The CRM knows and the worklist doesn't.** Despite score 77 and `status: "lead"`, there is **no
`lead_worklist` row** for this person. `crm_contacts.addresses_searched` is `[]` and
`probable_address` is `null`, even though `journey.key_events` holds the raw typing and
`all_conversions.submitted_address` holds the resolved `"3 Corina Close, Robina, QLD 4226"`. The
address never propagated into the fields the worklist consumes.

**6. The currently-listed guard worked as designed** — and closed the one door that would have
captured them. Their own home is already on the market, so AYH correctly refused to build a
mini-site. Worth noting: a vendor already listed with another agent is not a bad lead, and the
guard currently routes them to an editorial page with no capture step.

---

## Server-side record — every trace, and every verified absence

**Present:**

| Collection | `_id` / key | What it holds |
|---|---|---|
| `crm_contacts` | `66251069328bd0104f5f4096` | `primary_posthog_id` = this id, score 77, `status: "lead"`, 8 tags, `first_seen 08-10` / `last_seen 08-18`, **no name/email/phone** |
| `organic_journeys` | 3 rows | Sessions 1–3. Session 2 `converted: true`, `pattern: "valued_the_listing_itself"`, `searched_address_category: "current_listing"`. Session 4 not yet ingested (nightly job, latest site-wide `t_last` = 08-17) |
| `all_conversions` | 1 row | `submitted_address: "3 Corina Close, Robina, QLD 4226"`, `contact_captured: false`, channel Organic Search |
| `whale_moments` | `6a799b4f…` | 08-10 19:35:09, `first_trigger: scroll_reversal`, `audio: "playing"` |
| `forsale_ladder_responses` | `6a7ac0c5…` | Burleigh Waters / 4 bed / **Pool** / `opt_in: "no"` |
| `offmarket_intent_signals` | `6a84267e…` | 08-18 19:31:40, `dwell_ms: 224003`, `reached_pct: 84`, `sections_read: 14`, `top_section: "comps"` |
| `email_tracking` | `f7fd9fae-8ff` | 42 events, 20 page views, `max_scroll_pct: 100`, `total_time_seconds: 102` |
| `Gold_Coast.robina` | `690bd89c8b8f54659264a66c` | 3 Corina Close — **`listing_status: "for_sale"`**, House, 4/2, "Present All Offers", `ai_analysis` published 08-04, `valuation_data.confidence.reconciled_valuation` **$1,302,858** (medium, $1,143,910–$1,461,808) |

**Verified absent** (exact field names checked, per Rule 8 — a zero here is a fact about the data,
not about a guessed name):

- `property_reports` — no doc for either slug. Checked `owner.posthog_distinct_id`,
  `owner.attribution.posthog_distinct_id`, `owner.device_token`: 0 hits.
- `lead_worklist` — 0 hits on `extra.posthog_distinct_id` and on `lead_key` regex.
- `leads`, `analyse_leads`, `fb_leads`, `lead_signups`, `launch_leads`, `subscribers`,
  `price_alert_subscriptions`, `sms_claims`, `report_review_bookings`, `offmarket_orders`,
  `offmarket_qualification`, `asset_scans`, `physical_attribution` — 0 hits on
  `posthog_distinct_id` / `anonymous_visitor_id` / `device_token` / address regex.
- `engagement_activity_ledger` (61 docs) — no row mentions Corina or Gum Court.
- `email_tracking.events[].type` — no `pdf_downloaded`. The type exists and fires for five other
  documents, so this absence is real.
- `offmarket_report_requests` — **no user row for either address.** See below.

### The request that left no row

Both addresses appear in `offmarket_report_requests` only as `source: "prewarm"` builds
(3 Corina Close 08-13, 8 Gum Court 08-14). Of 8,300 rows only **2** carry `source: "offmarket_v4"`,
and neither is ours.

This is by design: `offmarket-report-request.mjs` returns a cached `completed` row without
inserting when the prior build is under `CACHE_MAX_AGE_MS` (7 days), and the insert path
deliberately stores no device token. A real reader arriving 4 days after a prewarm therefore leaves
**zero** trace in the request queue. The viewer event log is the only evidence the request happened.

**Consequence: any count of "reports requested" built from `offmarket_report_requests` undercounts
every cache hit.** The two `offmarket_v4` rows are not the demand figure.

---

## Honest limits on this reading

Recorded facts and inferences are separated deliberately here.

- **We do not know the Google query on either entry.** Google strips it; `$referrer` is only
  `https://www.google.com/`. The day-1 claim that they searched their own address is a *strong
  inference* (they landed on it, returned to it in all three early sessions, and typed that exact
  address into Analyse Your Home) — not a recorded fact. For day 8 we know nothing about the query
  at all, only that the landing page was 8 Gum Court.
- **We do not know that 3 Corina Close is their home.** Typing it into "Analyse Your Home" is the
  strongest available signal, but a buyer researching that listing would produce the same events.
  The `/for-sale-v3` ladder answers are buyer-shaped, which is consistent with an owner-occupier
  who is selling and buying at once — the most common case in this market — but that is a reading,
  not a record.
- **Day 8 is a different property in a different suburb** from day 1. The visitor did not return to
  their own address; they returned to a home matching their stated buying criteria.
- **One person is one person.** n=1 out of 95 deck viewers. This documents that the funnel *can*
  complete, not how often it will.
- **They did not download a PDF.** The client event says "downloaded"; the server says
  `viewer_opened` with no `pdf_downloaded`. Trust the server.
- **PostHog is client-side and lossy.** Ad blockers, tab closes and `navigator.webdriver` all drop
  events. Absence of an event here is not proof the action did not happen.
- **The IP in `email_tracking.events[].ip` (`13.55.15.16`, AWS ap-southeast-2) is not theirs** —
  `/track/*` is proxied through Netlify (`netlify.toml:97`), so that is proxy egress.
- **`anonymous_visitor_id: 49bbf41b-…`** on the ladder response appears in no other collection, so
  the ladder answers are joined to this person only via session, not via a durable id.

---

## Open actions this raises

1. **`offmarket_report_downloaded` is misnamed** — it fires on viewer open. Rename it, or add a
   distinct event for the actual `/download/<tracking_id>` hit, before anyone reports a download
   count from it.
2. **Cache hits leave no request row.** `offmarket_report_requests` cannot be used to measure
   demand while `CACHE_MAX_AGE_MS` short-circuits the insert. Needs a product decision on whether a
   cache hit should be recorded.
3. **`crm_contacts.addresses_searched` / `probable_address` never populate** even when
   `all_conversions.submitted_address` resolved the address. This is very likely why a score-77
   `high_intent` lead has no `lead_worklist` row. Plain bug, independent of the rest.
4. **No contact capture anywhere on the deepest conversion.** The single best outcome the site has
   produced yields an anonymous device token.
5. **The listed-vendor path dead-ends.** AYH correctly blocks listed addresses, but offers nothing
   in their place beyond an editorial page — and a vendor already listed with another agent is not
   a bad lead.
6. **`comps` is the most-read deck section** (42 s, top of 14) while `which` and `now` got 2 s each.
   A layout signal worth acting on.
7. **Ladder intent is captured and unused.** We knew "4 bed, pool, Burleigh Waters" on 11 Aug and
   had a Burleigh Waters deck they would go on to read for 5½ minutes on 18 Aug. Nothing connected
   the two — Google did.

---

## Reproducing this analysis

```bash
cd /tmp && python3 - <<'EOF'
import sys; sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from whale_moment_monitor import hogql, _load_env
_load_env()
ID = "019feb00-5692-7d6a-a478-9e642a9b4fa0"
for r in hogql(f"""
  select timestamp, event, properties.$pathname path
  from events where distinct_id='{ID}' and timestamp > now() - interval 30 day
  order by timestamp
"""): print(r)
EOF
```

`hogql()` in [scripts/whale_moment_monitor.py](../scripts/whale_moment_monitor.py) raises on any
failure rather than returning `[]`, so an empty result here is a real empty result.

Related: [[offmarket_v4_reading_analytics]], [[offmarket_v4_live]],
[[offmarket_report_one_shot_precompute]], [[ayh_currently_listed_guard]],
[[property_page_visitor_behaviour]], [[whale_moment]].
