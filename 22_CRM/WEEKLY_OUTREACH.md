# Weekly CRM Outreach — Runbook

How to run a personalised email + SMS (+ Messenger) campaign to CRM contacts, with
per-contact tracking through to on-site engagement. First run: the suburb-walkthrough
campaign, 2026-09-11 (`walkthrough_sep26`) — 55 email + 9 SMS, 64/64 delivered.

The tool is [`walkthrough_outreach.py`](walkthrough_outreach.py). For a new campaign,
copy it, change `CAMPAIGN` (slug, becomes the `email_sends.type` grouping and the
`utm_campaign`), the copy in `compose()`, and the link builder in `links_for()`.
Campaign artifacts (targets, review files) live in `campaigns/<slug>/` —
**⚠ those files contain PII (names/emails/phones): never push them to GitHub.**
Code and docs push; data stays on the VM.

```bash
cd /home/fields/Fields_Orchestrator && source /home/fields/venv/bin/activate
```

## 1. Build the target list

`campaigns/<slug>/targets_*.json` — one record per contact: `{id, name, email,
phone_norm, source, suburb_assignment, suburb_basis, lead_brief_area, do_not_email,
do_not_sms, internal_or_test}`. Build it by querying `crm_contacts` (reachable = email
or valid `+614` mobile, not internal/test). Suburb assignment comes from, in order:
lead-form area answer, address in `follow_up_reason`/lead data, campaign/form name.

⚠ Lessons encoded from run 1:
- **Dedupe by EMAIL, not contact id** — duplicate records sent Dee two emails.
- `internal_or_test` must be honoured (test-campaign leads, Will's own devices,
  `scripts/test_addresses.py` addresses).
- Landlines (`+617/8…`) are not SMS-able; the build flags and suppresses them.

## 2. Build drafts

```bash
python3 22_CRM/walkthrough_outreach.py --build
```

- Writes one draft per contact to `system_monitor.walkthrough_outreach_drafts`
  (email draft + SMS draft where reachable; `recommended_channel` = email if they have
  one, else SMS — **one message per person**, overlap contacts are not double-channelled).
- Mints/reuses `crm_contacts.link_token`; SMS links carry `&lead=<token>` directly
  (email links get the token appended by the click tracker).
- Writes `campaigns/<slug>/DRAFTS_REVIEW.md` for Will to read.

**Review before sending:** scan the ⚠ flags — suburb-defaulted contacts (no signal →
Robina), suppressed channels, suspect emails. Re-suburb anything you know better.

## 3. Sample send (always, before bulk)

```bash
# to Will himself (self-test draft exists on his own contact):
python3 22_CRM/walkthrough_outreach.py --send --contact will@fieldsestate.com.au --channel both
# then optionally 1-2 real contacts
python3 22_CRM/walkthrough_outreach.py --send --contact <email|phone|id>
```

Check: email renders + reply-to is will@; link click lands with video auto-starting;
`--report` shows the open/click and (from a non-internal device) the walkthrough events.

## 4. Bulk send — **only on Will's explicit go**

```bash
python3 22_CRM/walkthrough_outreach.py --send-all
```

Throttled 1.5s; aborts after 5 consecutive failures; skips anything already `sent`.
Both endpoints append every send to the contact's `communications[]` timeline
automatically — verify a sample afterwards anyway.

## 5. Messenger-only contacts

Contacts with `messenger_psid` but no email/phone can't be reached by the endpoints.
Generate personalised messages + tracked links into `campaigns/<slug>/MESSENGER_DRAFTS.md`
(see the generator invocation in fix-history / run-1 transcript), then **Will pastes them
in the Meta Business inbox by hand**. When he says what he sent, mark those drafts
`sent` and append a `communications[]` entry so the timeline is truthful.

⚠ Check for duplicate records first — two of run 1's "Messenger-only" people were
already emailed under a second record (Michele Woodrick, Lou Boettcher).

## 6. Report

```bash
python3 22_CRM/walkthrough_outreach.py --report
```

Per contact: email opens/clicks (pixel + click tracker), SMS delivery status (JustCall
webhook), and — via the lead token — on-site walkthrough engagement:
`walkthrough_start`, `_progress` (25/50/75%), `_film`, `_complete`, `_exit` (drop-off
point), `_unmute`, plus `lead_link_visit`/`$pageview`. The report is scoped to events
**after the first campaign send** (tokens are reused across campaigns; unscoped queries
resurrect old activity — that bug is already fixed, don't reintroduce it).

Delivery ground truth if in doubt: query JustCall's list API directly
(`GET /v2.1/texts`, auth `key:secret` raw) — our rows depend on the webhook.

## Known sharp edges (all hit in run 1)

| Edge | Consequence | Guard |
|---|---|---|
| `crm_contacts._id` mixed string/ObjectId | silent no-match on `update_one` with the wrong type | always string-then-ObjectId fallback; **check `matched_count`** |
| JustCall `/texts/new` returns `data` as an ARRAY | `justcall_id` null → delivery webhook can't reconcile | fixed in `crm-contact-sms.mjs` 2026-09-11; don't regress |
| Headless verification of PostHog | webdriver mask alone is NOT enough — HeadlessChrome UA also kills ingest | mask webdriver AND set a real Chrome UA |
| Suppression flags | `do_not_sms` absent until first STOP | rely on the endpoint gates, don't infer consent from field absence |
| Sends look fine, tracking dead | the `?lead=` loop has silently broken before | before each campaign: one headless click-through, confirm `lead_link_visit` lands |
