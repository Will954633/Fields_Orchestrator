# Pronto Direct — order register

The numbered log of every job sent to Pronto. **The next order number is one above the
highest below.** Allocate it when you create the Drive folder; never reuse or renumber.
Convention and process: `fulfilment/README.md`.

| Order | Date sent | Flow code(s) | Pieces | Pack-out | Drive folder | Status |
|-------|-----------|--------------|-------:|----------|--------------|--------|
| PD-0001 | 2026-08-17 | Fields_01.1 (38) + Fields_02.1 (12) | 50 | C4 + mailer_v2 + 2 magnets | `2026-08-17_Fields_01.1_and_02.1_PD-0001` | prepared |
| PD-0002 | 2026-08-26 | Fields_OT.1 | 50 | C4 + teaser + hand-written note + 2 magnets | `Fields_OT.1_2026-08-26_PD-0002` | prepared |
| PD-0003 | 2026-09-02 | Fields_OTN.1 | 50 | C4 + teaser + 2 magnets (NO note) | `Fields_OTN.1_2026-09-02_PD-0003` | prepared |

**Next order number: PD-0004.**

**A/B test (PD-0002 vs PD-0003):** identical teaser + QR to the same audience
(off-market page viewers, organic from Google), disjoint address sets. PD-0002 =
WITH hand-written note (`Fields_OT.1`, arm A); PD-0003 = NO note (`Fields_OTN.1`,
arm B). Measures whether the note changes QR-scan/engagement. Attribution: each
scan's `/off-market/<slug>` maps to exactly one arm via the manifest (mail_log).

Stock once all three post: 150 C4 envelopes + 300 magnets consumed, against 100 / 250
received 2026-08-17 — **short ~50 envelopes and ~50 magnets; PD-0003 needs a restock**
(Will to arrange with John). Live balance: `python3 scripts/fulfilment_stock.py`
(now shows negative available = the shortfall).

Every mailed address is recorded in `system_monitor.mail_log` (mirror
`fulfilment/MAIL_LOG.csv` + Live Leads Tracker "Mail Log" tab) — the durable
"who got what, and when posted" record. `python3 scripts/mail_log.py mailed-slugs`
lists everything already sent (use it to exclude next batch).

Notes:
- PD-0002 carries the combined code `Fields_OT.1` on John's paperwork, but its pieces
  are ALSO logged as a `Fields_OT.1` work order now (was previously missing).
- Status is `prepared` until John confirms lodged with Australia Post, then `posted`:
  run `python3 scripts/mail_log.py set-posted --order PD-000N --date YYYY-MM-DD` AND
  flip the work-order status so the stock tool moves it from reserved to consumed.
