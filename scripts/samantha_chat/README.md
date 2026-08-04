# Break Glass → Override Protocol → Samantha

The hidden interaction in the home page footer, and the chat assistant it hands over to.
Shipped 2026-08-04.

Someone finds the emergency case in the footer, smashes the glass, pulls the lever — the
page loses power, an alarm comes up, a ship's-computer voice announces an override, and a
restricted channel opens onto **Samantha**, who answers questions about the three suburbs
using real market data.

The framing throughout is: *"Most people browse the public Fields website. You just opened
the part beneath it."* The visitor is treated as someone who found the back door, not
someone who needs rescuing.

---

## Where everything lives

| Piece | Path | Repo |
|---|---|---|
| React shell (mount, lazy-load, analytics) | `src/components/BreakGlass/BreakGlass.tsx` | Website |
| Box + lever behaviour | `src/components/BreakGlass/breakGlassEngine.js` | Website |
| The sequence (quake → blackout → alarm → voice) | `src/components/BreakGlass/overrideSequence.js` | Website |
| Chat panel UI | `src/components/BreakGlass/samanthaChat.js` | Website |
| Per-page context + voice line | `src/components/BreakGlass/pageContext.js` | Website |
| Light envelope, quake, surge audio | `powerFailure.js`, `quake.js`, `quakeRecording.js`, `surges.js` | Website |
| Assets (voice, alarm, quake, frames) | `public/break-glass/` | Website |
| Chat service | `scripts/samantha_chat/service.py` | Orchestrator |
| Her data | `scripts/samantha_chat/facts.py` | Orchestrator |
| Her rules | `scripts/samantha_chat/system_prompt.md` | Orchestrator |
| systemd unit | `deploy/fields-samantha-chat.service` | Orchestrator |

**Workbench:** `vm.fieldsestate.com.au/concepts/off-market/Break_glass_emergency/workbench/`
— tuning sliders for every beat, served statically with **no build step**. It loads the
*same files* production imports, via symlinks, so there is nothing to port and the two
cannot drift. This is why the iteration loop is sub-second.

**Chat-only test page:** `vm.fieldsestate.com.au/concepts/samantha/` — talk to her without
sitting through the sequence.

---

## The .js / .tsx split

Behaviour is plain JS, not TypeScript, on purpose: the workbench loads it directly in a
browser with `<script type="module">` and no compiler. The React side gets real types from
hand-written `.d.ts` files instead.

This exists because every bug in the original port came from keeping two copies of one
behaviour in sync. There is one copy now.

---

## Front end

Nothing loads until it is needed. The footer renders on every route, so:

- Six box frames (~840KB) — first one on `IntersectionObserver`, the rest on hover/focus
- Sequence + chat + audio (~670KB) — **only on the lever pull**, via dynamic `import()`

A visitor who never touches the box pays for one image.

### Tunables, switchable without a deploy

Will has not settled these. Append to the home page URL:

| Param | Values | Default |
|---|---|---|
| `?tone=` | 1, 2, 3 — tonal reading of the announcement | 1 |
| `?alarm=` | `1x`, `2x` — one burst or two | `1x` |
| `?quake=` | 600–6000 ms — build length before blackout | 3200 |
| `?long=1` | use the longer middle voice line | short |

All three tonal sets ship, so switching is a constant change in `BreakGlass.tsx`.

### Things that are load-bearing

- **Flash safety.** `powerFailure.js` clamps `surgePeak` at runtime if the envelope would
  breach WCAG 2.3.1. Do not remove the clamp to make the surge brighter.
- **100Hz, not 50Hz.** AU mains is 50Hz, but light ripple and transformer hum are at
  *twice* mains. Grid frequency does not slide down under load — it gets louder and dirtier.
- **Shake follows audio by construction.** With the recorded quake, `intensity()` is live
  RMS off an `AnalyserNode`, so re-levelling a layer re-levels the shake automatically.
- The lever needs a real pointer **drag** — `hitHandle` has no click listener. Synthetic
  clicks do nothing, which has fooled the verification harness more than once.

---

## Samantha

### Why the browser calls the VM directly

A turn measures **6–15s** and `claude -p` does not usefully stream — the whole message
lands in one chunk. Netlify's synchronous function timeout is 10s, so a three-sentence
answer would time out every time. The browser calls `vm.fieldsestate.com.au/samantha/chat`
over existing TLS; Netlify is not in the path.

**Consequence:** if the VM is down, the panel says so. Every failure path ends in a stated
message, never a spinner.

### What she can and cannot do

**Can:** six figures per suburb for Robina, Varsity Lakes and Burleigh Waters — median
house price, its confidence range, year-on-year, median days on market, DOM change, and
12-month settled sales.

**Cannot** (and will say so): search or see any listing; value a specific property; quote
one property's sale history; unit medians; quarterly medians or QoQ; sales volume by
quarter; months of supply or absorption; anything about waterfront homes.

That is roughly **one of the seven** categories the Market Intelligence page covers. She is
a suburb-stats assistant that refuses cleanly outside that, which is the honest version of
what exists today.

### Why `facts.py` exists

Before it, asked the same question four times she answered **32, 30, 28 days and one
refusal** — the real figure is 34 — and attached invented provenance ("274 sold listings",
which do not exist).

The prompt already forbade this in the strongest terms available. **That cannot work:** a
model with no data and a direct factual question produces a plausible number some fraction
of the time. The fix is data, not prompt.

Figures come from the **same precomputed documents the live charts render**
(`precomputed_indexed_prices`, `precomputed_market_charts`, `propradar_suburb_stats`), so
she cannot contradict the page in front of the visitor.

Deliberately withheld:

- **Volume, months of supply, absorption** — Domain's sold-side capture is 53–66%, making
  these ~2× wrong in the direction that manufactures a false oversupply story. Where volume
  is genuinely needed it comes from PropRadar, which counts settlements.
- **Medians**, entirely, unless `median_source == domain_union_onthehouse` — a blind
  `replace_one` from a manual precompute silently reverts them.

**Fact values must be self-describing.** A key is not a specification. Labelled
`days_on_market_change_vs_year_ago: 9.5`, she reported a change measured in *days* as "up
9.5 percent". Labelled `median_range`, she called a confidence interval "the middle range
of sales". Both are wrong claims built from real numbers, and no guard can catch them.

### The three guards

Prompting is probabilistic. Anything stated as absolute is enforced in code.

| Guard | Catches | On trigger |
|---|---|---|
| `_unsourced_figures()` | a money/percentage/quantity not in the supplied facts | logs + Telegram, flags in `meta` |
| `_redact_sources()` | any supplier name (portals, vendors, government datasets) | **substitutes it out** before sending, then alerts |
| `facts.py` withholding | unreliable metrics never reach her at all | structural — nothing to comply with |

Attribution is always **"the Fields internal database"**. If asked where the data comes
from: *"compiled from commercial sources"*, and nothing further — not even to confirm or
deny a provider the visitor names first.

**Known residual risk:** a *real* figure in the *wrong place*. She once quoted Burleigh
Waters' 6.9% for Robina. Both numbers were real and supplied, so the guard passed it
correctly. Mitigated by prompt only.

### Her hard limits

Beyond the editorial rules (no advice, no predictions, no single valuation figure), each of
these exists because it went wrong before — see `system_prompt.md`:

never claim accuracy superiority (our own backtest points the other way in two suburbs) ·
waterfront out of scope · Fields has no track record, listings, clients or subscribers ·
never name another agency or agent · flooding always gets the planning-layer caveat and
FloodWise · no per-property figures (some stored sale prices are corrupted rents) · no
appraisal of a listed home · never reveal what we know about the visitor · no negotiation
coaching · no hard CTAs.

### Controls

| | |
|---|---|
| Per IP | 25/hour |
| Global | 400/day, Telegram warning at 75% |
| Message | 1200 chars |
| Origin | allowlist; anything else → **403** |
| Model | `claude-opus-5` on Claude **Max** |

Max has a hard five-hour window with overage **rejected**, so at the cap she replies "at
capacity" rather than failing silently.

---

## Operating it

```bash
sudo systemctl status fields-samantha-chat
sudo journalctl -u fields-samantha-chat -f
curl -s https://vm.fieldsestate.com.au/samantha/health
```

Health board: **Process Registry** on the Fields Systems Health sheet — 30-minute
heartbeat, STALE within ~45 minutes if it dies.

**Telegram fires on every engagement**, plus near-capacity, quota exhaustion, errors,
unsourced figures and redacted supplier names.

### Reading the journal

| Line | Meaning |
|---|---|
| `[telegram] sent` | alert delivered (confirmed from the API's `ok`, not assumed) |
| `[telegram] NO CREDENTIALS` | **alerts are silently off** — check `.env` |
| `[fabrication] unsourced figures […]` | she stated a figure we did not supply |
| `[source-leak] redacted […]` | she named a supplier; it was removed before sending |

The service reads `/home/fields/Fields_Orchestrator/.env` **itself**. It is not given
credentials by the unit file: the first deployment passed them on the command line, the
`sudo -u` switch dropped them, and six conversations were served with zero alerts and no
error anywhere.

---

## Before changing anything

1. **Never trust a passing check you have not proved runs.** Bare `tsc` checks *zero* files
   here — use `tsconfig.app.json` and confirm with `--listFiles`.
2. **When a check says it is broken, verify the check first.** Live verification called this
   feature dead on production three times while the deploy was fine: it matched the loading
   indicator as a reply, clicked a button hidden for 2.6s, then used `.click()` on a
   drag-only handle. A false negative and a real fault look identical from the output.
3. **One commit, not N.** Use `scripts/push_website_files.py`. Every commit to the website
   repo is a Netlify build; file-by-file pushing has twice exhausted the allowance and
   served 503s to real visitors.
4. **Test her adversarially after any prompt change** — prediction, single valuation figure,
   company internals, prompt injection, off-topic, "are you human", waterfront, flooding,
   "is it Domain or CoreLogic", and a suburb question with two suburbs in play.

---

## What we are waiting to learn

Shipped to find out whether anyone engages at all. If they do, what they ask decides what
gets built next: **listings search** (she has no listing data), **seller research** (the
corpus exists, closest to ready), or **negotiation signals** (data exists, but "which
owners are desperate" is the failure mode Will identified — worth a conversation before
code).

Related: `logs/fix-history/2026-08-04.md` — `SAMANTHA-FABRICATED-FIGURES`,
`SAMANTHA-TELEGRAM-SILENT`, `SAMANTHA-SOURCE-DISCLOSURE`, `SAMANTHA-GUARDRAIL-SWEEP`,
`SAMANTHA-CROSS-SUBURB-FIGURE`, `BREAKGLASS-LIVE-VERIFY-INSTRUMENT`.
