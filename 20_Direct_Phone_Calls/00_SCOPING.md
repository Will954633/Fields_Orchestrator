# Direct Phone Calls — System Scoping

**Built:** 2026-08-15 · **Owner:** Will Simpson · **Status:** build in progress, 2 hard gates open

Goal: make direct outbound calls to Gold Coast homeowners, from the JustCall number, recorded,
with transcripts landing in the CRM, driven by a daily call list in a Google Sheet the human
caller edits in place.

First round: **30–50 connects** to test the system and the script end to end.

---

## 1. The three call tracks — they are NOT legally the same

The brief said "test against our leads list and against the open market". Those are two tracks
legally, and the leads list is really two:

| Track | Who | n available | Number source | Legal basis |
|---|---|---|---|---|
| **A — Warm, self-supplied** | Gave us their own number (17 FB Lead Ads + 2 AYH) | **19** | They typed it | DNCR s11(2) consent defence arguable; ACMA: express consent lasts **3 months** — check each date |
| **B — Warm intent, appended** | Entered their address on our site / opened their off-market page | **327** core-suburb | ID4ME append | **Cold.** Address ≠ phone consent. Full DNC + Standard applies |
| **C — Open market** | Any core-suburb owner, no intent signal | ~22,000 dwellings | ID4ME append | **Cold.** Same as B, weaker hook |

**⚠ Track A is only 19 people and cannot produce 30–50 connects.** At a realistic 25–35% connect
rate it yields 5–7 conversations. The volume for the first round has to come from B (and C).

### Funnel math for the first round (Track B)

327 core addresses → ID4ME resolve ~97% → has callable phone ~75% → **~245 dialable**
→ minus DNC-registered (unmeasured; the one sampled address had 11 of 12 people blocked at the
*person* level) → connect ~25–30% → **plausibly 40–70 connects.** Enough, if DNC attrition is
not catastrophic. **DNC attrition is the number that decides the round and we have never measured
it.** Measure it before committing to a volume.

⚠ ID4ME freshness: only **38.9%** of the 36-address sample was "has mobile AND record ≤2 years
old" (Robina 66.7%, Burleigh Waters 41.7%, **Varsity Lakes 8.3%**). Median record age 3.12 years.
Expect wrong-number and previous-occupant rates to be high, and weight the list toward Robina.

---

## 2. ⛔ GATE 1 — Do Not Call Register subscription (blocks Tracks B and C entirely)

**ID4ME's DNC flag does not protect us.** The 30-day safe harbour in **DNCR Act 2006 s11(3)(a)**
requires the number to have been on a list *"submitted **by the person**"* under s19(1). ACMA's own
real-estate guidance (IS 157) is explicit:

> "this defence is only available to the person who washed the list… where a real estate agent
> obtains an externally provided list and does not carry out their own list wash, they cannot rely
> on the 30-day defence."

Without our own wash we fall back to s11(5) "reasonable precautions", a much weaker position, and
**s11(6) puts the evidential burden on us**. Civil penalties run to **$2.22M/day** (court) /
$222,000/day (infringement).

ACMA also states plainly that **"a call to solicit the listing of a person's property"** and
**"a call to offer a free property appraisal"** ARE telemarketing calls. There is no real estate
exemption — Schedule 1 covers government, charity, political, research only.

**Action required from Will:** buy a **Type B subscription, $126/yr, 20,000 wash credits** at
donotcall.gov.au. Manual CSV upload is fine at our volume — Type D (API/SFTP) is $5,058 and 40× the
cost for no benefit at hundreds of dials. Scripted export + scripted re-import, manual upload in the
middle. ⚠ Invalid numbers are charged silently with no warning — validate AU format before submitting.

⚠ **The wash is a rolling 30-day safe harbour, not a clearance.** Re-wash every 30 days; a list that
sits for 5 weeks is unprotected. Store the wash date per number and refuse to dial an expired one —
this is enforced in code (`dnc_wash.py`), not left to the caller.

Track A can proceed without this only where we hold evidence of express consent under 3 months old.

## 3. ⛔ GATE 2 — recording consent must be verbal, and it is not optional

**Making** the recording is lawful: QLD *Invasion of Privacy Act 1971* **s43(2)(a)** exempts a party
to the conversation. (Commonwealth TIA Act does not bite — recording at our own endpoint happens
after the communication has ceased "passing over" the system, s5F/s6(1).)

**Using it is the problem. s45(1)** makes it an offence for a party who recorded a private
conversation to "communicate or publish to any other person any record of the conversation… **or any
statement prepared from such a record**". A transcript is a statement prepared from the record.
**Storing the transcript in the CRM where anyone else can read it, or sending audio to a
transcription vendor, is prima facie a s45 communication.** Max 40 penalty units or 2 years.
**s49A** extends liability to the executive officer personally — for a sole operator, that is Will.

The clean fix is **s45(2)(a): consent of all parties.** So the caller says "this call is being
recorded, is that OK?" and **waits for a yes**. If no → stop recording or end the call. The consent
is logged against the record.

This also satisfies **APP 5** notification and removes the "intentional or reckless" element the new
**statutory tort of serious invasion of privacy** needs (Privacy Act Sch 2, commenced 10 June 2025;
cl 6(b) covers "listening to or recording the person's private activities"; **cl 7(2) actionable
without proof of damage**; damages to $478,550). ⚠ **The small-business exemption does not shield us
from the tort.**

⚠ JustCall has **no documented automatic recording announcement** — its compliance features are
built for US states. The announcement is the caller's mouth, or an IVR greeting on the number.

## 4. ⚠ GATE 3 — the Privacy Act probably already applies to us

**s6D(4)(d)**: the small-business exemption is lost by an entity that "provides a benefit, service or
advantage to collect personal information about another individual from anyone else". **Paying ID4ME
for homeowner contact data is exactly that.** s6D(8) saves only collection with the individual's
consent or under legislation — an appended list is neither.

So assume the APPs bind us: APP 5 collection notice, APP 6 secondary use (using calls to train or
analyse is a *secondary* purpose needing its own consent), APP 7.3 direct marketing from
third-party-sourced data, **APP 7.6 — the person can demand to know where we got their number, and
the only honest answer is "we bought it."** Retention period and deletion required.

**Not a blocker for the test round, but it is a decision Will should take knowingly.**

## 5. ⚠ GATE 4 — s215 CMA trap (the one that will actually happen on a call)

**Property Occupations Act 2014 s215**: if a person wanting to sell **asks** a real estate agent
about the price and the agent answers, the agent must at that moment give a **comparative market
analysis** — Schedule 2 defines it hard: **≥3 properties sold within the previous 6 months, similar
standard/condition, within 5km**. Max 540 penalty units (≈$93,000).

"So what's my place worth?" is the most likely question on every single call. **The caller must not
give a figure verbally.** The compliant answer is to offer to send the analysis — which we can
generate, and which is the actual conversion event we want anyway.

⚠ **s212(4)–(5) reverse onus**: any representation made without reasonable grounds "**is taken to be
misleading**", and "the onus of establishing the person had reasonable grounds… **is on the person**".
Every price, comparable or "buyers waiting" claim must be logged with its grounds at the time.

⚠ **s216(6)**: once a CMA is given to a seller, it must not be given to anyone else without the
seller's **written** approval.

### Correction to existing memory
`withdrawn_expired_listings_strategy` records "POA Reg s21(3) bans it". **That is wrong.**
POA Regulation s21 is *"Prior appointment of another property agent"* and turns on an appointment
that **"is in force"**. Expired and withdrawn appointments fall outside s21 entirely — there is no
restriction on approaching those owners. The test is also **conjunctive** (both limbs), **s21(4) is a
complete carve-out** if a written double-commission statement is given first, and breach is
**disciplinary (QCAT), not an offence**. There is **no general anti-soliciting provision in the POA**.
⚠ But the 39 **"Listing Nearing Expiry"** leads in our list are the one group where an appointment
IS still in force — s21(3) genuinely applies to them. **Excluded from round 1.**

## 6. ⚠ ACL unsolicited consumer agreements — the largest commercial risk

A listing authority won **by cold call** is very likely an *unsolicited consumer agreement*
(ACL s69(1)(b)(ii)); **s70 presumes** it is unless we prove otherwise. Consequences:
**10 business days cooling-off** (s82(3)(b)), and **s86(1) forbids supplying the service during it** —
**marketing the property in that window extends the client's termination right to 6 months**
(s82(3)(d)). ⚠ **s69(2)**: "an invitation merely to quote a price… is not an invitation to enter into
negotiations" — so even an inbound "what's it worth?" converted by phone can still be caught.

**ACL s73 calling hours are stricter than ACMA's and therefore govern.**

---

## 7. Calling rules the system enforces (not left to the caller)

| Rule | Value | Source |
|---|---|---|
| Mon–Fri | **9:00am – 6:00pm** | ACL s73 (stricter than Standard's 8pm) |
| Saturday | **9:00am – 5:00pm** | ACL s73 / Standard s8(1)(d) |
| Sunday | **never** | Standard s8(1)(e) |
| National public holidays | **never, any time** | Standard s8(3) — Cth holidays only; QLD-only holidays not caught |
| Caller ID | must be on; return number reachable **30 days** | Standard s14(1),(3) |
| Opening disclosure | name, business, who caused the call, **purpose** — "as soon as the call starts" | Standard s9(2) |
| Contact details on request | **immediately** | Standard s9(4), s11 |
| Terminate | **immediately** on any indication they want it to end | Standard s13(1)(b) |
| After a request to stop | **no contact for 30 days** | ACL s75(2) |

⚠ There is **no "5 second" termination rule** — that 5 seconds is only the abandoned-predictive-dialler
exception to the *opening disclosure* (s9(3)(b)). Termination is immediate. Do not script a window.

---

## 8. Architecture

```
Gold_Coast.<suburb> ──┐
Live Leads Tracker  ──┼─→ build_call_list.py ─→ system_monitor.call_queue
ID4ME append        ──┘         (score + hook)          │
                                                        ├─→ dnc_wash.py ──(manual CSV upload)──→ ACMA
                                                        │      ↑ wash date per number, 30d expiry
                                                        ▼
                                        call_list_to_sheet.py
                                                        │  insert-at-top day block
                                                        ▼
                            ┌───────  "Marketing Phone Calls" sheet  ───────┐
                            │  machine cols A–J,N,O   human cols K,L,M      │
                            └──────────────────┬────────────────────────────┘
                                               │ read_call_outcomes.py (write-back)
                                               ▼
                                    system_monitor.call_outcomes
JustCall ──webhook jc.call_ai_generated──→ justcall_sync.py ─→ system_monitor.call_activity
         └─nightly reconcile GET /v2.1/calls (3-MONTH API WINDOW — see below)
```

**⚠ JustCall exposes only the last 3 months of call history via API.** Anything not synced inside
that window is unrecoverable except by emailing their support. The nightly reconciliation job is
therefore mandatory, not a nicety, and per **Rule 7b** must raise when calls exist in the window but
zero were ingested, and must never advance its watermark on a failed run.

### Sheet contract — how human edits survive a rebuild

The sheet is **never rebuilt**. New day-blocks are inserted at row 2 via `insertDimension`
(`startIndex:1`, `inheritFromBefore:false`), exactly the pattern proven in `live_leads_to_sheet.py`
and `sold_homes_to_sheet.py`; everything below shifts down with its comments, notes and formatting
intact. Newest day therefore sits at the top, as asked.

- **Machine columns (A–J, N, O)** — written once at insert, then never re-touched, except N/O
  (JustCall link, transcript) which are refreshed in place *one cell at a time*, addressed via the
  hidden **Call ID column P**, never by row position.
- **Human columns (K Outcome, L Comments, M Call back on)** — **the script never writes them.**
  `read_call_outcomes.py` only ever *reads* them.
- **The sheet is the source of truth for human columns.** Write-back is one-way, sheet → Mongo.
- Dedupe ledger `system_monitor.call_list_sheet_ledger`, `_id` = the call-queue candidate id,
  `$setOnInsert` — so a row Will deletes by hand is never resurrected.

⚠ No script in this repo has used `dataValidation` before. The K-column dropdown is new ground;
**verify empirically that validation survives `insertDimension`** with `inheritFromBefore:false`
(inherit direction matters) rather than assuming it.

---

## 9. Open items before the first dial

1. ⛔ **Will buys the DNC Register Type B subscription** ($126) — blocks Tracks B and C.
2. ⛔ **Turn call recording ON for +61440131629** — JustCall dashboard → Phone Numbers → Advanced
   Settings. **There is no API for this.** Unrecorded calls are unrecoverable.
3. ⚠ **Prove transcription entitlement**: make one recorded test call, then
   `GET /v2.1/calls_ai?fetch_transcription=true`. We are on the **Team** plan; JustCall's blog says
   transcription is included from Team, third-party pricing analyses say it is an add-on, the
   developer docs are silent, and our probe returned 200 with zero calls so it proves nothing.
   **This 10-minute test decides the architecture.** Fallback if it fails: download the MP3 and
   transcribe with Gemini via Vertex, already wired at `VISION_BACKEND=gemini_vertex`.
4. ⚠ **Measure DNC attrition** on a 100-number sample before committing to a round size.
5. **ID4ME**: subscription auto-renews 2026-08-16 (confirmed by Will). ⚠ `can_use_api` is **false**
   and the ToS forbids "automated programs or other data extraction systems", cap **800 searches/day**.
   Appending 327 addresses is a ToS breach at any pace. **Ask ID4ME for the licensed API product
   ($155/mo) first** — it converts a terms-breaching integration into a contract.
6. **Only one JustCall number and one active user** (Will, ext 101; the second seat has never logged
   in). If the human caller is not Will, they need a seat.

## 10. Deliberately NOT built

- **No AI voice agent.** JustCall's `POST /v2.1/voice-agents/calls` exists but is Pro Plus
  ($89/user) + metered, and its own `has_consent: true` flag is a hard blocker against cold use.
  An AI robocalling QLD homeowners is a different legal and brand proposition entirely.
- **No cold SMS, ever.** Spam Act 2003 — an appended number carries no consent and the onus of
  proving consent is on the sender. Unaffected by DNC status.
- **No auto-dialler.** Every call is a human pressing dial.
