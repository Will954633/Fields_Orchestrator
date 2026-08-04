# The claim step — "text us to claim your website"

The beat after `Construction completed.` The camera pans down off the build log
and onto an offer; pressing the button opens the reader's own SMS app with the
message already written. They press send; we reply with their mini-site link.

**Front end: built and rendering.** **Back end: not started, and blocked on a
number.**

---

## Why the message goes the wrong way round

The obvious design is a form: "enter your mobile and we'll text you the link."
This does the opposite — it makes the reader send the message. Three reasons,
and they are the whole point of the mechanic:

**It collects the one thing nobody will type.** Every measurement we have says
the public will not hand a phone number to a website — the whole
address-capture-then-direct-mail strategy exists because of that. But people
send texts without thinking about it. The number arrives as a side effect of
them asking for something, rather than as a toll charged before they get it.

**The consent is unambiguous.** They messaged us, in their own words, asking for
a specific thing. A reply carrying that thing is a response to a request. That is
a much cleaner footing than an opt-in checkbox, and it is the strongest consent
position any funnel we run has ever had.

**It kills the OTP requirement.** The earlier phone-gate scoping recommended
Twilio Verify or Telnyx Verify to prove a number belongs to the person using it
(`scripts/samantha/justcall_integration_scoping.md`, Question 2). This design
needs none of it: **sending the text IS the verification.** A number that
receives our reply is by definition a number the sender controls. One fewer
vendor, one fewer failure mode, no rate-limiting or brute-force surface.

---

## What is built

- `outro/claim.js` — listens for `fields:strategy-built`, pans the camera, types
  the three lines in the same hand as the opening sequence, then fades the action
  up last so nobody can press before the offer has been made.
- `preview/deck.css` — `#fx-claim` and the pan. Both layers travel the same
  distance in the same direction at the same time, which is what makes it read as
  one camera move rather than a crossfade.
- `preview/build_deck_preview.py` — `claim_config()` injects
  `window.__FIELDS_CLAIM` per deck and builds the QR at build time with `segno`.

**Copy, as supplied:**

> **Your website is ready.**
> Now claim your private access.
> We'll send a secure link to your mobile.
> `[ Claim my website ]`

**Phone** gets an `sms:` deep link. **Desktop** gets a QR of the same message,
plus the number and the text printed underneath — a QR that fails to scan
otherwise leaves you with nothing.

Two encodings, deliberately. The in-page link is an `sms:` URI, where iOS wants
`sms:NUMBER&body=` and everything else wants `?body=`; `claim.js` picks per
device. Getting that wrong does not throw — it opens SMS with an **empty**
message, which is the worst kind of failure because it looks like it worked. The
QR cannot pick, because it is scanned by a phone we know nothing about, so it
uses `SMSTO:NUMBER:MESSAGE`, the format QR readers have agreed on for this.

---

## The inbound half — BUILT AND LIVE, 2026-08-04

`netlify/functions/justcall-sms.mjs` → `POST /api/v1/justcall-sms?k=<secret>`,
registered with JustCall on `sms.received` and reporting Active.

What it does, in order:

1. **Fails closed** on a missing or wrong shared secret. JustCall signs nothing,
   so the secret lives in the registered URL. This matters more than usual: an
   open endpoint that sends SMS on demand is an SMS-bombing tool pointed at
   whatever number the caller supplies, billed to us.
2. Ignores anything that is not an **incoming** message starting with `SEND`.
3. Resolves the address against `offmarket_discovery` — the text carries no
   suburb, so the index is what turns "27 Protea Court" into a full address, a
   `suburb_key` and a slug. **A second match is treated as no match.**
4. POSTs that address to `/api/v1/analyse-your-home-submit`, exactly as the
   Analyse Your Home page does — one build path, not two.
5. Texts back the single URL that call hands it.

**Correction to an assumption worth recording:** opening a mini-site URL does
*not* start a build. `property-report-progress.mjs` and `property-report.mjs` are
both strictly read-only; the build is enqueued by the **submit POST**, and the
orchestrator's `scripts/property_reports/poller.py` picks the stub up within
~15s. So the webhook's submit call is what starts it, and by the time the reader
taps the link their site is already building. That is the right way round, and
better than the assumption — but it means the build cannot be started by sending
someone a link.

Three destinations, chosen exactly as the website's own flow chooses them:

| Case | URL |
|---|---|
| Currently listed | `/property/:id` |
| Report already built | `/your-home/:slug` |
| Anything else | `/analyse-your-home/building/:slug` (live build feed, polls, auto-forwards when ready) |

**It only ever auto-replies to a matched address.** An unknown address, an
ambiguous one, an out-of-service suburb or a failed submit is logged to
`system_monitor.sms_claims` and pushed to Telegram for Will to answer himself.
That holds the automated half to the single case that was approved: link only,
to someone who asked for it.

### Verified live

- Endpoint rejects a missing secret (403) and a wrong secret (403).
- Unknown address → `{"ok":true,"outcome":"no_match"}`, no SMS sent, Telegram fired.
- Webhook registered, `status: Active`.
- **Not yet exercised: the happy path.** It needs a real inbound text.

### A real gap this surfaced

**The discovery index is wider than the service area.** `analyse-your-home-submit`
serves Robina, Burleigh Waters, Varsity Lakes, Merrimac, Mudgeeraba, Reedy Creek
and Worongary. The discovery index also holds **3,399 Nerang addresses** — every
one of which can reach the claim step, text in, and be rejected. Confirmed by
probe: Nerang returns a 400 with the service-area message.

Today that path is safe — it sends no SMS and pings Will instead. But a Nerang
reader is being shown "Your website is ready" for a website that cannot be built.
Either restrict the deck's claim step to served suburbs, or add Nerang to the
service area. **Not yet decided.**

### ~~Blocker 1 — there is no SMS number~~ RESOLVED 2026-08-04

**`+61 440 131 629`**, Will's JustCall line. Verified against
`GET https://api.justcall.io/v2.1/phone-numbers`: `number_type: Mobile`,
`sms_compliance: Verified`, `capabilities: {call, sms, mms}` all `Yes`, owner
`will.simpson@blueoceans.com.au`. The decks now ship it and
`SMS_NUMBER_IS_PLACEHOLDER` is `False`.

**It is a live number.** Anything built against it reaches a real handset, so a
test send is a real message to a real person and needs asking for.

Credentials are in `.env` as `JUSTCALL_API_KEY` / `JUSTCALL_API_SECRET` /
`JUSTCALL_SMS_NUMBER`, read out of `00_Run_Commands/gh-token-29Mar.txt` (which is
git-ignored via `*-token-*.txt` and untracked — checked).

Auth is a single header, and it is not Basic — no base64, no `Bearer`:

```
Authorization: {api_key}:{api_secret}
Accept: application/json
```

Endpoints that matter, all on `https://api.justcall.io/v2.1`:

| Purpose | Method | Path |
|---|---|---|
| List account numbers | GET | `/phone-numbers` |
| Send an SMS | POST | `/texts/new` |
| List webhooks | GET | `/webhooks` |
| Register a webhook | POST | `/webhooks` |

**No webhooks are registered on the account** (`GET /webhooks` returns
`count: 0`), so nothing currently receives an inbound text.

The earlier scoping said JustCall was the wrong tool for this because it is
built for human conversations rather than programmatic auto-reply. That
judgement was about OTP verification, which this design does not need — for
"receive a text, send a reply", the v2.1 API and its webhooks are a direct fit
and there is no reason to add a second vendor.

### Blocker 2 — what the reply actually links to

The sequence promises a finished website. So either the mini-site already exists
for every address in the discovery index, or the text arrives and the build
starts then. The second is not a problem — it is arguably better, because "we're
building it now, link in a few minutes" is true and the outro has already told
that story. But it decides the shape of the webhook, so it needs answering before
any of it is written.

### Blocker 3 — the auto-reply consent ruling

We have a standing DRAFT-ONLY rule for contacting real people. An automated reply
to someone who just texted us asking for a link is closer to a receipt than an
outreach, but that boundary has been flagged before and never ruled on
(`justcall_integration_scoping.md`, Question 1). **Will needs to make the call.**

Separately, under the Spam Act 2003 the reply itself is safe — they requested it
— but *any subsequent message* is marketing and needs express consent plus a
functional unsubscribe. The reply should be link-only, and follow-up is a
separate decision, not a default.

---

## One question that turned out not to be a problem

`SEND 27 Protea Court` carries no suburb, so the obvious worry is two homes with
the same street address in different suburbs. **Checked: zero collisions across
all 17,775 addresses in `system_monitor.offmarket_discovery`** — Robina,
Varsity Lakes, Burleigh Waters and Nerang. The copy works exactly as written.

**But that is a fact about today's coverage, not a property of the design.**
Street names repeat across the Gold Coast, and the index is already four suburbs
and growing. Add suburbs and this breaks quietly — the webhook resolves to the
wrong house and sends a stranger's report to someone. The check is one line and
must run at expansion time:

```python
# collisions must stay at zero, or the SMS body needs the suburb appended
```

Recommendation: put that assertion in the discovery pipeline now, so the first
address that collides fails loudly instead of the reply going to the wrong home.

---

## Not verified

- **The QR has never been scanned by a real phone.** `SMSTO:` is the de-facto
  standard and is what QR generators emit for SMS, but iOS Camera and Android
  need testing separately before this goes to a reader.
- **The `sms:` deep link has never been opened on a real handset.** The iOS
  `&` vs Android `?` split is from the specification and from how every other
  implementation does it, not from a device test here.
- Both were rendered and driven end-to-end in headless Chrome, which proves the
  markup, the timing and the hrefs — and nothing about what a phone does with
  them.

---

## Files

- `outro/claim.js`
- `preview/deck.css` — `#fx-claim`, `#fx-msg.gone`
- `preview/build_deck_preview.py` — `SMS_NUMBER`, `claim_config()`
- Fix history: `[V3-CLAIM-STEP]`, 2026-08-04
