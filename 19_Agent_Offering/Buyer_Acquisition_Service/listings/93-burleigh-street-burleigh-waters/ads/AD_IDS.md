# 93 Burleigh — paid ad campaign (Meta)

**Format:** click-to-Messenger carousel · **Status:** PAUSED (Will activates) · built 2026-08-20

- **Campaign:** `93 Burleigh St — Messenger Carousel` — `120252341379830134`
- **Objective:** OUTCOME_ENGAGEMENT → CONVERSATIONS · destination MESSENGER · special category HOUSING

| Ad set | Geo | Budget | Ad set ID | Ad ID |
|---|---|---|---|---|
| AcreageMovers | Mudgeeraba/Worongary/Tallai/Bonogin | $20/day | `120252341527850134` | `120252341528940134` |
| LocalSGC | Burleigh Waters/Miami/Palm Beach/Burleigh Heads | $25/day | `120252341529320134` | `120252341529890134` |
| Sydney | Greater Sydney (30 km) | $20/day | `120252341548240134` | `120252341548860134` |

**Creative mockups:** [`mockups/`](mockups/) (carousel_A/B/C).
**Builder + clean card images + activate command:**
`03_Facebook/Campaigns/2026-08-20_93Burleigh_Messenger/` — `launch_messenger_carousel.py`
(`--activate` flips live). Card renderer: `render_native.py`. IDs: `campaign_ids.json`.

**Before go-live:** set the Messenger greeting + ice-breakers in Business Suite → Inbox →
Automations (can't be set via API). Attribute the listing agent in the ad copy (see listing
README open items). Log any change to `system_monitor.ad_decisions` (CLAUDE Rule 3).
