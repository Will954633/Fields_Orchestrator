# Pronto Direct — order register

The numbered log of every job sent to Pronto. **The next order number is one above the
highest below.** Allocate it when you create the Drive folder; never reuse or renumber.
Convention and process: `fulfilment/README.md`.

| Order | Date sent | Flow code(s) | Pieces | Pack-out | Drive folder | Status |
|-------|-----------|--------------|-------:|----------|--------------|--------|
| PD-0001 | 2026-08-17 | Fields_01.1 (38) + Fields_02.1 (12) | 50 | C4 + mailer_v2 + 2 magnets | `2026-08-17_Fields_01.1_and_02.1_PD-0001` | prepared |
| PD-0002 | 2026-08-26 | Fields_OT.1 | 50 | C4 + teaser + hand-written note + 2 magnets | `Fields_OT.1_2026-08-26_PD-0002` | prepared |

**Next order number: PD-0003.**

Stock consumed once both post: 100 C4 envelopes, 200 magnets (of 100 / 250 received
2026-08-17). Live balance: `python3 scripts/fulfilment_stock.py`.

Notes:
- PD-0002 carries the combined code `Fields_OT.1` on John's paperwork, but the pieces
  are registered under `Fields_01.1`/`Fields_02.1` work orders. Reconcile the code
  before relying on scan attribution (see README pack-out / flow rules).
- Status is `prepared` until John confirms lodged with Australia Post, then `posted`
  (also flip the work-order status so the stock tool moves it from reserved to
  consumed).
