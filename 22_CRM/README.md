# 22_CRM — Fields Real Estate CRM

The CRM is not one app — it is a **MongoDB collection at the centre of a mesh of feeders,
channels, and surfaces**. This README maps the whole thing. The weekly outreach runbook
(sending campaigns like the walkthrough one) is in [WEEKLY_OUTREACH.md](WEEKLY_OUTREACH.md).

---

## The spine: `system_monitor.crm_contacts`

One document per known person (~1,275 as of Sep 2026, of which ~65 are genuinely
reachable — the rest are anonymous analytics/off-market shells). Key fields:

| Field | Meaning |
|---|---|
| `_id` | ⚠ **Mixed types.** `crm_sync`-created docs use a 24-hex *string*; `crm_lead_sync` uses a real ObjectId. Always look up by string first, then fall back to `ObjectId(id)`. Server endpoints do exactly this. |
| `name`, `email`, `phone` | Contact identity. Phone stored E.164 (`+61…`). |
| `source` / `lead_attribution` | Where they came from (`fb_lead_ad`, `messenger`, `owner_market_leadpage`, …) + FB form/campaign detail. |
| `communications[]` | **The timeline.** Every outbound email/SMS (auto-appended by the send endpoints), every human touch (via `log_contact_touch.py`), inbound SMS replies. Renders on the CRM contact page. |
| `notes[]` | Free-form human notes (same script). |
| `follow_up_at` | ⚠ **The only field that makes a lead resurface** on the Priority tab. A touch logged without one goes quietly cold. |
| `link_token` | Opaque uuid4-hex. Powers `?lead=<token>` links — the identity join between a message click and on-site behaviour. Minted by `email-track.mjs` on first click, or by outreach tooling at draft time. |
| `lead_web` | Device join block written by `lead-link-visit.mjs`: current + accumulated `distinct_ids` (every device they've clicked from), first/last click-through, landing URL. ⚠ distinct_ids live here ONLY — never in `posthog_ids` (crm_sync re-keys on that and would fork the contact). |
| `engagement_score`, `email_engagement`, `tags` | Bumped by email opens/clicks and web activity. |
| `do_not_email`, `do_not_sms` | Suppression. ⚠ `do_not_sms` **does not exist until someone texts STOP** — absence of the field is normal, not evidence of consent record-keeping. Send gates live server-side. |
| `messenger_psid` | FB Messenger thread id (from `messenger_leads_sync.py`). Messenger-only contacts have no email/phone. |

## Feeders (how people get in / stay fresh)

- `scripts/crm_sync.py` — hourly full-doc sync from PostHog behaviour. ⚠ Two landmines
  documented in memory `home_recognition_personalization`; carry-forward allow-list
  protects `lead_web`, `link_token`, `follow_up_at`, etc.
- `scripts/nightly_lead_chain.py` (00:15 AEST) — runs `messenger_leads_sync.py` (FB inbox →
  contacts), `source_leads_sync.py` (sweeps `leads`, `campaign_leads`, `lead_signups`,
  `subscribers`, `five_property_friday_subscribers`, `analyse_leads`, `launch_leads`),
  `lead_web_activity` (pulls each bound device's pageview journey onto the contact), then
  rebuilds the sheets.
- `scripts/log_contact_touch.py` — **the only write path for human call/contact outcomes**
  (what Will said, what was sent, when to follow up). Everything else is automation.

## Surfaces (where you look at it)

- **Priority tab** — first tab of the Live Leads Tracker sheet
  (`1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs`). Two sections: follow-ups due, then
  every reachable lead with no follow-up set. Done-checkbox round-trips into the CRM
  before each rebuild. Built by `scripts/priority_calls_to_sheet.py`.
- **CRM contact page** — signed link `https://fieldsestate.com.au/api/v1/crm-contact?id=<id>&k=<key>`
  (`netlify/functions/crm-contact.mjs`): full timeline (web activity + emails with
  opens/clicks + SMS), plus compose boxes that send through the endpoints below.
- **Ops → Marketing tab** — Email Campaigns panel aggregates `email_sends` by `type`
  (campaign slug) with open/click rates.

## Channels (how we reach people)

| Channel | Send path | Tracking | Gates (server-side) |
|---|---|---|---|
| **Email** | `POST /api/v1/crm-contact-send {id,k,subject,body,type?}` → Resend via `mailer.mjs` | Open pixel + click rewrite (`email-track.mjs`); click redirect appends `?lead=<token>`; logs `email_sends`/`email_events`; Telegram ping on open/click | `do_not_email`, contact must have email |
| **SMS** | `POST /api/v1/crm-contact-sms {id,k,body}` → JustCall | No opens (channel limit). Delivery status via `justcall-sms.mjs` webhook into `sms_messages`. Put `&lead=<token>` in the link yourself — there is no rewrite layer | `do_not_sms`, appended/purchased numbers refused, auto sender-ID + "Reply STOP", STOP sets `do_not_sms` |
| **Messenger** | Manual, from the Meta Business inbox (no API send path by policy) | Only via a personalised `?lead=` link in the message; mark sends into the CRM manually | 24h/human-agent messaging window is Meta's, not ours |

Both endpoints authenticate with the contact-scoped HMAC:
`k = base64url(HMAC-SHA256(REPORT_LINK_SECRET, "crm:"+id))[:16]` — recipient is always
the contact on file, never the request, so blast radius is one known lead.
`REPORT_LINK_SECRET` is in the orchestrator `.env`, so VM-side scripts can compute `k`.

## The identity loop (why clicks turn into named engagement)

1. Message link carries/acquires `?lead=<link_token>` (email: appended at click-redirect;
   SMS/Messenger: baked into the link at draft time).
2. `useLeadIdentify` in `src/root.tsx` (global, all routes) calls `phIdentifyLead`:
   PostHog `identify(token)` + `lead_link_visit` + POST `/api/v1/lead-link-visit`.
3. `lead-link-visit.mjs` stamps `lead_web` on the contact and attaches email/phone/name to
   the PostHog person **server-side** (no PII ever in URLs).
4. The device stays identified — later visits with no link still attribute to the contact.
   The nightly chain harvests the journey onto the CRM record.

⚠ History: this loop was dead site-wide until 2026-09-11 (`useLeadIdentify` lived in
unrendered `App.tsx`; `phIdentifyLead` also skipped the server bind pre-posthog-load).
Fix-history `[LEAD-IDENTIFY-DEAD-APPTSX]`, `[PHIDENTIFY-STUB-BIND-SKIP]`.

## Consent & legal position

Every emailable/SMS-able contact self-submitted via our FB lead forms or site forms =
inferred consent (Spam Act). **Never** message appended/purchased/skip-traced numbers
(the SMS endpoint refuses them), **never cold SMS** (memory
`cold_contact_legal_position_2026-08`), and phone calls have their own statutory rules —
read memory `direct_phone_calls_system` (IPA s45 / POA s215) before any call-related work.

## Known warts (worth fixing over time)

- **Duplicate people**: same human under 2 records (Michele/Michele Woodrick,
  Lou/Louise Boettcher, Dee ×2 — Dee got a campaign email twice on 2026-09-11 because
  drafts deduped by contact id, not email). Dedupe outreach by **email**, and merge
  records when touched.
- Data quality: landline numbers in `phone` (07/08 — not SMS-able), one literal `0400`,
  one `@bigpong.com` typo domain.
- ~37 reachable contacts have **no suburb signal** for personalisation.
