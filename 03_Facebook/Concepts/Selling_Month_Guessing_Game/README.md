# Selling-Month Guessing Game — "Worst month to sell in Robina"

**Hook:** *"Pick the selling month that could cost you $154,000 on your sale price."*

An interactive Reel that turns Robina's sale-price seasonality into a two-round quiz. The ad
is a game the viewer plays; every wrong answer is a reason to hand over an email; a completed
game is a reason to hand over an address. The reel → landing page transition is seamless — the
landing page opens on an exact replica of the reel's final frame (same layout, same four month
tiles) so there is no visible cut between watching and playing.

---

## Flow

### Reel (the ad)
- Full-screen: a Robina home + **four month tiles** to choose from.
- On-screen: *"Worst month to sell in Robina"* → *"Pick the month that could cost you
  $154,000 on your sale price."*
- One tile pulses invitingly. CTA button → landing page.

### Landing page (replicates the reel environment exactly)
**Round 1 — Worst month to sell**
- Same four month tiles the viewer saw in the reel. They pick one.
- **Wrong guess** → show the name + email form: *"Not quite — enter your details and we'll
  send you the month that costs Robina sellers the most."*
- **Right guess** → advance to Round 2.

**Round 2 — Best month to sell**
- *"Now pick the BEST month to sell your house in."*
- *"On average this month adds +$98,000 to a typical Robina home."* (framing TBD — see
  compliance)
- Same four-tile mechanic.
- **Wrong guess** → name + email form: *"Close — enter your details and we'll send you the
  single best month to list."*
- **Right guess (game complete)** → address capture: *"Want to see how this plays out for YOUR
  home? Enter your address for the analysis."* → hands off to the property-analysis funnel.

### Capture logic (summary)
| Point | Trigger | We collect | We promise |
|-------|---------|-----------|------------|
| R1 wrong | wrong month | name + email | send the worst month |
| R2 wrong | wrong month | name + email | send the best month |
| R2 right | game complete | address | personalised seasonal analysis |

Everyone who plays either converts on an answer they're curious about, or completes and gives
an address. No dead ends.

---

## Data required (BLOCKER — validate before build)

The whole concept rests on two numbers that **must be real** and reproducible from Robina sale
records before a single dollar figure goes to air:

- **$154,000** — the sale-price gap between Robina's worst and (implied) best selling month.
- **$98,000** — the best-month uplift vs the average.

Open questions to resolve with the data:
- Is Robina's monthly seasonality signal large enough and stable enough (multi-year) to state
  a "worst" and "best" month at all, or is it noise? Seasonality on a single suburb's median is
  easily swamped by mix (a few big waterfront sales in one month).
- Median vs mean, and controlled for property mix? A raw monthly median swing is mostly
  composition, not timing — that must be disclosed or the claim is misleading.
- Source + sample size + years covered, for the methodology panel.

See memory `minisite_seasonality_strip.md` for prior seasonality work; reuse that pipeline if
the signal holds. **Do not ship placeholder figures.**

---

## Compliance flags (CLAUDE.md §5 — mandatory)

- **No advice.** "Worst/best month to sell" edges toward telling a reader when to act. Keep it
  as *reported historical data* ("historically, homes sold in <month> transacted for X% less"),
  never *"you should list in <month>"*. Conditional, past-tense, data-attributed language only.
- **No single valuation in a headline.** The $ figures here are **gaps/differences**
  ($154K spread, +$98K uplift), which the 2026-07-27 update explicitly permits in ads
  ("$98K hiding in plain sight" is the cited-OK pattern) — as long as they are framed as
  differences, never as a single home's worth.
- **Mandatory pre-flight:** the landing page carrying these $ claims must visibly show the
  seasonality **methodology + confidence/sample disclaimer**. Build that panel into the
  landing page, not a footnote.
- **Number format:** `$154,000`, `$98,000`; "Robina" capitalised.

---

## Build checklist (when promoted from brief)

- [ ] Validate $154K / $98K against multi-year Robina sale data; write methodology panel copy.
- [ ] Reel scene (`reel_scene.html`, deterministic `seek(ms)`) — four-tile final frame is the
      handoff frame. Follow `../../Price_Your_Own_Home/` render pattern.
- [ ] Landing page replicating the final frame + the two-round quiz + three capture states.
- [ ] Lead storage + the two fulfilment emails (worst month / best month) + address → analysis handoff.
- [ ] Launch script + campaign/adset/form IDs json (see `../../Owner_Market_Carousel/` pattern).
- [ ] Log ad decision to `system_monitor.ad_decisions` (CLAUDE.md §3).
