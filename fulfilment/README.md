# Pronto Direct — order handbook

**What this is:** the single place that says *how we run a printed-mail order through
Pronto Direct*. Read this before building, naming, or sending any new job. It is the
admin/handoff layer; the build pipeline itself is documented separately (see
[Related docs](#related-docs)).

Everything about an order lives in three places, and they must agree:

| Layer | Lives in | Owns |
|-------|----------|------|
| **This handbook** | `fulfilment/README.md` | conventions, print spec, pack-out, checklist |
| **Order register** | `fulfilment/ORDER_REGISTER.md` | the numbered log of every job (PD-000N) |
| **Flow + stock registry** | `config/fulfilment_flows.yaml` | flow codes, supplier, stock ledger |
| **Live stock balance** | `scripts/fulfilment_stock.py` | computed on-hand / available |

---

## The supplier

**Pronto Direct** — Molendinar, Gold Coast. Our print-pack-post mail house.
- Contact: **John Thwaites** — 0400 526 533 — sales@prontodirect.com.au
- Confirmed in person 2026-08-17. **John holds our stock on site** (C4 branded
  envelopes + fridge magnets) and packs each job from it. We never ship envelopes or
  magnets with a job — only the artwork and, where a flow needs it, the hand-written
  notes.
- John works from **standing instructions per flow code**, so a work order names the
  code + address list; it does not re-explain the pack-out. But every order folder
  still carries a plain-English `READ_ME_print_spec` so nothing depends on memory.

---

## Order numbers — `PD-000N`

**Every job gets one sequential order number.** Prefix `PD` (Pronto Direct),
4-digit zero-padded, allocated in `ORDER_REGISTER.md` — the register is the source of
truth for "what number is next".

The order number is **appended** to the Drive folder name, existing name kept as-is:

```
<existing descriptive name>_PD-000N
```

Live examples:
- `2026-08-17_Fields_01.1_and_02.1_PD-0001`
- `Fields_OT.1_2026-08-26_PD-0002`

Allocate the number when you create the Drive folder, log it in the register the same
moment, and never reuse or renumber — a posted job carries its number forever.

---

## Drive layout

Parent folder: **Fulfilment — Pronto Direct** (shared with John)
`https://drive.google.com/drive/folders/1zL4I7AbEquGFqyb40WoSsa4bVnEVYD95`

One sub-folder per order (`..._PD-000N`), each containing:

| File | What |
|------|------|
| `<combined print PDF>` | ONE PDF, all pieces laid up (see print spec) |
| `manifest.csv` | one row per piece, **mailing order** — the master list |
| `READ_ME_print_spec_<date>.txt` | plain-English spec + pack-out + inventory note for John |

Only the artwork, manifest and README go in the Drive folder. Per-address source PDFs
stay on the VM in the build folder.

---

## Filename convention

- **Per-piece source artwork** (on the VM, named in the manifest):
  `<flow_code>_<NN>_<slug>.pdf` — e.g. `Fields_OT.1_07_19-casetta-court-varsity-lakes.pdf`
  (`NN` = 2-digit mailing position, `slug` = kebab-case address).
- **Combined print file** (what John prints from):
  `Fields_<count>pieces_<pages>pp_bleed3mm_crops_<YYYY-MM-DD>.pdf`
- **Manifest:** always `manifest.csv`. **Spec sheet:** `READ_ME_print_spec_<YYYY-MM-DD>.txt`.

### manifest.csv schema
`artwork_file,pages,flow_code,slug,address` — one row per piece, in the order they
should be posted. Piece *n* = pages `2n-1` and `2n` of the combined PDF (front then
back). The full postal address is on every row; it is the key John matches everything
else to.

---

## Print spec (John's standing format, given 2026-08-20)

This is a **standing RIP spec**, not a per-job choice — state it on every order:

- **Bleed:** 3 mm, **with crop + registration marks** (not a tagged TrimBox alone).
- **File:** ONE combined PDF, in `manifest.csv` row order; piece *n* = pages `2n-1`/`2n`.
- **Colour:** supply **RGB** — Pronto converts to CMYK. Embed **no** CMYK profile.
- **Media boxes:** media 230×317 mm; trim 210×297; bleed 216×303 (both tagged).
  Artwork placed 1:1 on trim, never scaled to make bleed.
- **Stock — per product** (this is the one thing that varies by flow):
  - Owner teaser (Fields_OT): **A4, 4-colour, 2 sides, 170 gsm satin**.
  - Mini-site mailer (mailer_v2, Fields_01/02): **A4 duplex, 210 gsm Silk**
    (Will's decision 2026-08-17 — silk holds the aerial without glare).
- Re-decode every QR **in the combined file** after lay-up — a lay-up is a re-render.

---

## Pack-out recipes (what goes in each envelope)

Recorded canonically in `config/fulfilment_flows.yaml`. As of this writing:

| Flow | Envelope | Contents per address |
|------|----------|----------------------|
| `Fields_01` / `Fields_02` | C4 branded | 1 mailer_v2 + 2 fridge magnets |
| `Fields_OT` (owner teaser) | C4 branded | 1 teaser + 1 **matching hand-written note** + 2 fridge magnets |

**Address matching is the failure point.** Where a flow includes a hand-written note
(or any per-address insert delivered separately), the README must tell John to match
it to the teaser bearing the **same address**, and to set aside + call rather than
guess on any piece he can't match confidently. One C4 envelope per address.

---

## Stock

John holds our stock; we never store a running balance — it is **computed** so it
can't drift:

```
on_hand   = sum(receipts in fulfilment_flows.yaml) - pieces on "posted" work orders
available = on_hand - pieces on prepared/sent-but-not-posted work orders
```

```bash
python3 scripts/fulfilment_stock.py            # current position
python3 scripts/fulfilment_stock.py --plan 50  # can we run 50 more?
```

⚠ **Envelopes bind before magnets** at 1 + 2 per piece. When you size a batch, check
the binding item first. Every order's `READ_ME_print_spec` tells John his remaining
count after that job posts — keep it accurate; the envelope figure drives re-supply.

---

## Checklist for a new order

1. Build the batch (see the runbook under Related docs) → combined PDF + manifest.
2. `python3 scripts/fulfilment_stock.py --plan <N>` — confirm stock covers it.
3. Allocate the next `PD-000N` in `ORDER_REGISTER.md`; create the Drive sub-folder
   `<name>_PD-000N` under Fulfilment — Pronto Direct.
4. Upload combined PDF + `manifest.csv` + `READ_ME_print_spec_<date>.txt`.
   The README must state: print spec, pack-out (incl. any address-matched inserts),
   and John's remaining stock **after** this job.
5. Record the work order in `system_monitor.fulfilment_work_orders` (status
   `prepared`). Log the ad/decision if applicable.
6. Send John the Drive link.
7. **When John confirms lodged:** set the work order status to `posted` (so
   `fulfilment_stock.py` moves it from reserved to consumed) and mark the order
   `posted` in `ORDER_REGISTER.md`.

---

## Related docs

- **Build pipeline (how the artwork is made):**
  `11_House_Mini_Site/_shared/mailer_v2/RUNBOOK_batch_to_pronto.md` — flow codes,
  yields, and the build traps. Read it before generating a batch.
- **Flow + stock registry:** `config/fulfilment_flows.yaml`
- **Stock balance tool:** `scripts/fulfilment_stock.py`
- **Order log:** `fulfilment/ORDER_REGISTER.md`
