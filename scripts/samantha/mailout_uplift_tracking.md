# Mailout engagement-uplift tracking (QR scan → mini-site visit)

**Purpose:** measure whether posting a printed positioning package to a no-phone
engaged owner lifts their engagement with Fields. Set up 2026-07-27 (Samantha),
per Will's 2026-07-27 mailout direction.

## The attribution mechanism
Every mailer's QR points at that home's own mini-site with a **per-address** UTM tag:

```
https://fieldsestate.com.au/your-home/<slug>?utm_source=mailer&utm_medium=print&utm_campaign=home_report&utm_content=<slug>
```

`utm_content=<slug>` is the change that makes uplift measurable **per posted address**
(added to `11_House_Mini_Site/mailer/generate_mailers.py::make_qr`, 2026-07-27). A scan
is a physical→digital action that would not happen without the mailer, so any
mailer-attributed session is **pure incremental engagement** — no confounder to net out.

## Before / after read
- **BEFORE (baseline):** organic `/your-home/<slug>` (and `/off-market/<slug>`) sessions in
  the 90 days pre-mailout. For this first batch the baseline is ~0–4 sessions/address
  (mostly the single owner-lookup that triggered the report). Snapshot saved alongside the
  mail list: `output/mailout/mailout_candidates_2026-07-27.csv` (visitors/views/dwell_s cols).
- **AFTER:** sessions with `utm_source=mailer` (and `utm_content=<slug>` for the exact address)
  in the weeks after Will posts. Also watch total `/your-home/<slug>` sessions (a scan often
  precedes an un-tagged return visit).

## Re-measure query (PostHog, run ~2 and ~4 weeks after posting)
`query-web-stats`, breakdownBy `Page`, dateRange from the post date, filter
`$pathname regex /(your-home|off-market)/`, plus a second run breakdownBy
`InitialUTMContent` filtered to `InitialUTMSource = mailer` — that row list IS the set of
addresses whose owner scanned. Cross-check against `crm_contacts` / `leads` for any that
then raised a hand (report-review booking, price alert, AYH submit) = the real conversion.

## Reporting
Log the batch as a change-ledger entry (`change_ledger.py`, type `mailout`, metric =
mailer-attributed sessions, baseline 0, direction up, review-days 14,28) so the uplift
read is due-tracked and can't silently lapse. Fold the result into the KPI Monitor sheet
under intent-signals.

## Gotchas
- Will's own browser is opted out of PostHog + a scan on his phone would pollute the read —
  he should not test-scan the posted copies (or do so from a device we can exclude).
- `website_daily_metrics` Mongo rollup is broken (all zeros) — PostHog is the source of truth.
