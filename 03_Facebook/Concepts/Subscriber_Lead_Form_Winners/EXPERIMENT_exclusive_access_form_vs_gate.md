# A/B: autofill Instant Form vs manual `/exclusive-access` gate

**Launched:** 2026-08-28 · **Owner:** Will · **Status:** LIVE (both arms)

---

## Why we're running this

The **Subscriber Lookalike — Houses for sale (Advantage+)** ad sends clicks to a landing page,
`https://fieldsestate.com.au/exclusive-access`, that asks the visitor to type their **name +
email** into a web form before continuing to the listings. The point of the ad is to **capture
subscribers**.

It isn't. First-day numbers on the manual gate:

| Control (Advantage+ → `/exclusive-access` manual gate) | |
|---|---|
| Impressions | 1,449 |
| Clicks to the page | 33 |
| Spend | $6.07 |
| CPC | **$0.18** (cheap — the creative works) |
| **Subscribers captured** | **0 / 33** |

For context: `system_monitor.subscribers` holds **4 subscribers total**, all from the site
footer — **none from any ad, ever.** So the creative pulls cheap clicks, but the manual
name+email gate converts nobody.

The obvious lever is a **Meta Instant (lead) Form** — the fields prefill from the viewer's
Meta profile, so signing up is one tap instead of typing. That's almost always higher-
converting than a web form. The reason we *didn't* already do this: this specific ad uses an
**Advantage+ dynamic creative** (per-placement crops of the same image), and Meta won't attach
an Instant Form to a dynamic creative — you must flatten it to a single creative first. The
original build deliberately kept the dynamic creative intact (on the theory it's *why* the ad
won) and paid for that with a manual gate. This test challenges that trade.

## What we did

Left the control **untouched and running**, and launched a second ad — same audience, same
budget — that swaps the capture mechanism:

- **Flattened the creative.** The 4 Advantage+ "images" all share one image hash
  (`9f80727ae1f203b051083d8aec204677`) — they're just crops — so flattening is lossless on the
  image. Same body copy, same LEARN_MORE button.
- **Attached a prefilled Instant Form** asking **Full Name + Email + Phone**, all prefilled.
  Phone is **required** — we want the numbers (Will, 2026-08-28). One headline statement,
  *"Fields exclusive access for subscribers only"*, no intro card, no extra questions.
- **Same hand-off.** The form's thank-you screen continues to `/for-sale-v4b`, matching what
  the manual gate does after capture.
- **Equal test conditions.** Targeting and daily budget copied verbatim from the source ad set
  ($10/day each), objective `OUTCOME_LEADS` / `LEAD_GENERATION` / `destination_type=ON_AD`.

Built PAUSED by `build_ad5_leadform_variant.py`, activated on Will's go.

### The two arms

| | **Control** (unchanged) | **Variant** (new) |
|---|---|---|
| Creative | Advantage+ dynamic | Same image, flattened |
| Capture | Manual web gate (`/exclusive-access`) | Prefilled Instant Form |
| Fields | Name + Email | Name + Email + **Phone** |
| Objective | Traffic | Leads |
| Budget | $10/day | $10/day |
| Campaign | `120252450385330134` | `120252455741540134` |
| Ad | `120252450388660134` | `120252455742200134` |
| Form | — | `1017406421335871` |
| Captures land in | `system_monitor.subscribers` (`source: fb_ad_v4b_lp`) | `system_monitor.fb_leads` + CRM |

## What we're looking for

**The deciding metric is cost per captured contact — not CPC, not CTR.** A cheaper click that
never converts (the control's problem) is worth nothing.

1. **Cost per subscriber/lead, each arm.**
   - Control = spend ÷ new rows in `system_monitor.subscribers` (`source: fb_ad_v4b_lp`).
   - Variant = spend ÷ leads (Meta reports these natively in the ad's Results column;
     they also arrive in `system_monitor.fb_leads`, pulled every 3 min by `fb-lead-puller.py`,
     with a Telegram alert per lead).
2. **Does the form capture at all?** The bar is low — the control is at 0. Any positive
   capture rate on the variant is already a win on the core question.
3. **Phone completeness.** Since phone is the reason for the test's field choice, check what
   fraction of variant leads actually include a usable phone number (prefill can be blank if
   the profile has none).
4. **Delivery health of the flattened creative.** Watch impressions/reach and CPM vs the
   control. If the flat creative reaches far fewer people or costs more per impression, that
   tells us the dynamic creative was doing real work — a factor to weigh even if the form wins
   on capture.

### Read carefully — the confound
The two arms differ in **two** things at once: creative format (dynamic vs flat) **and**
capture mechanism (web gate vs prefilled form). We couldn't isolate them, because Meta forbids
a form on a dynamic creative. Interpretation:

- **Form captures meaningfully cheaper** → switch to the form. Decision made; the creative-
  format question is moot because the outcome (subscribers) improved.
- **Form also captures ~nothing** → the problem isn't the gate, it's the offer/audience.
  Rethink what we're asking people to sign up for.
- **Form captures well but delivery/CPM is much worse than control** → the dynamic creative was
  carrying reach; consider running the form on a *manually* multi-placement (non-Advantage+)
  creative to get most of the reach back with a form attached.

## Decision point

Give it **~48–72h of delivery** for a fair read (Meta's lead optimisation needs a learning
window). Then compare cost-per-captured-contact across the two arms and either:
- roll the winner out and pause the loser, or
- if both capture poorly, treat it as evidence the *offer* — not the mechanism — is the
  bottleneck.

## Provenance / files
- Build script: `build_ad5_leadform_variant.py` (this folder)
- Control build: `build_ad5_lookalike.py` · landing page: website repo
  `src/pages/ExclusiveAccessPage/*`
- Decision logged: `system_monitor.ad_decisions`, 2026-08-28
- Lead capture: `scripts/fb-lead-puller.py` (cron every 3 min → `fb_leads` + CRM + Telegram)
