# JustCall Integration Scoping (2026-07-23)

Will asked two related but genuinely SEPARATE questions in the same note — splitting them, because
the right tool differs for each.

## Question 1: "How can we integrate JustCall into our workflows?"

JustCall is a business calling/SMS platform with a full REST API + real-time webhooks, built for
exactly this. Concrete, well-fitted use cases for Fields:

1. **Lead follow-up automation.** Missed-call webhook → auto-SMS reply with a link (e.g. "Sorry we
   missed you — here's your property's data snapshot: [link]"). Fits the existing DRAFT-ONLY rule
   for contacting real people if the auto-reply is a neutral, pre-approved template, not a
   personalized sales message — worth a specific ruling from Will on which auto-replies count as
   "contact" requiring his send vs a neutral utility message (e.g. a link resend) that's closer to
   a receipt than an outreach.
2. **Call/SMS activity logged to CRM.** JustCall's webhooks can fire on every call/SMS event —
   pipe into `crm_contacts` so Will's phone activity with a lead shows up alongside their web
   behaviour (the same attribution join already used elsewhere: email/phone as the key).
3. **Two-way SMS conversations tracked as lead signals.** A lead replying to an SMS is a strong
   engagement signal — could feed `lead_worklist` the same way `offmarket_report_view` was just
   added this session (see fix-history `[LEAD-WORKLIST-MISSING-OFFMARKET]`).

**Not yet built.** Needs: JustCall API key (check `.env`/ask Will if already provisioned), a webhook
receiver (a new Netlify function, matching the pattern of `offmarket-ladder-lead.mjs`), and a
decision on which JustCall events warrant a CRM/lead-worklist write.

## Question 2: "Do we need a phone services company for SMS authentication [mini-site phone-gate]?"

**Yes — but NOT JustCall.** Checked: JustCall's API is built for outbound/inbound business calling
and two-way SMS conversations, not one-time-passcode (OTP) verification. Using it to hand-build an
OTP flow means implementing code generation, expiry, rate-limiting, and fraud/abuse prevention
ourselves — all solved problems in dedicated **Verify APIs** (Twilio Verify, Telnyx Verify are the
two most established). This is a separate vendor decision from the JustCall subscription, not an
extension of it.

**Recommendation:** if the phone-gate feature (lock sensitive mini-site data behind a phone number,
verified via OTP, per Will's note) moves forward, evaluate Twilio Verify or Telnyx Verify
specifically for that — small per-verification cost, but it removes an entire class of security/
abuse risk (rate-limit bypass, OTP brute-forcing) that a hand-rolled JustCall-based flow would need
to solve from scratch.

## What this doesn't answer yet
This is a scoping pass (web research), not implementation. Before building either: confirm JustCall
API access is provisioned (Will's subscription), and get a decision on the auto-reply "is this
contact" boundary for Question 1's missed-call automation.

Sources: [JustCall APIs & Webhooks](https://justcall.io/product/api-and-webhooks/),
[JustCall Help Center — API/Webhook build guide](https://help.justcall.io/en/articles/9891572-build-integration-with-justcall-using-apis-and-webhooks),
[Twilio Verify](https://www.twilio.com/en-us/user-authentication-identity/verify),
[Telnyx Verify API](https://telnyx.com/products/verify-api).
