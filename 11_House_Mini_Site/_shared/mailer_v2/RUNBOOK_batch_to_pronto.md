# Runbook — lead addresses → printed mail with Pronto Direct

How to produce another batch. Written 2026-08-17 immediately after the first real
run (50 pieces), while the traps were still fresh.

`README.md` in this folder covers the ARTWORK — what the mailer says and why.
This file covers the PROCESS — how a batch gets built, coded, checked and sent.

---

## The chain, end to end

```
Live Leads Tracker "All Leads"          real leads, post-reconciliation
        │                               (scripts/leads_came_to_market.py +
        │                                scripts/leads_prune_nonleads.py run nightly)
        ▼
scripts/build_mailer_batch.py           select → mint stub → build report
        │                               ~54 s each, ZERO model calls
        ▼
system_monitor.property_reports         must pass check_ready() in
        │                               generate_mailers_v2.py
        ▼
generate_mailers_v2.py --slug …         one PDF per address (VDP)
        │                               QR carries the flow code
        ▼
system_monitor.fulfilment_work_orders   what went where, and why
        │
        ▼
Drive: Fulfilment — Pronto Direct/<codes>_<date>/     artwork zip + manifest + registry
```

---

## 1. Check the pool

```bash
cd /home/fields/Fields_Orchestrator
set -a && source .env && set +a && source /home/fields/venv/bin/activate

# How many lead addresses are already mailable, and what is buildable
python3 scripts/build_mailer_batch.py --limit 200 --dry-run
```

**Selection criteria** (all four, each for a reason):

| Rule | Why |
|---|---|
| on "All Leads" | post-prune, so no test builds or came-to-market leads |
| NOT `Listing Nearing Expiry` | those homes ARE listed — separate Form 6 process |
| has a **floor area** | the comps engine EXCLUDES a subject without one → `valuation method='thin'` → `comps` stays pending → gate fails. **The single biggest determinant.** |
| `property_type == "House"` exactly | valuation design envelope is detached houses. ⚠ never `"house" in type` — that matches **Townhouse** |

---

## 2. Build

```bash
python3 scripts/build_mailer_batch.py --limit 127 --workers 3
```

**Measured 2026-08-17: 124 built, 94 ready (76% yield), ~35 min, 0 model calls.**
Budget roughly **66 builds per 50 mailable**.

⚠ **Do NOT pass `--mode full`.** `no_llm` (V1.5) is the current shipped build — see
`11_House_Mini_Site/README.md`. `full` is ~8 min/build and 11 model calls for the
same gate result. The AI path's fallback is OpenRouter, which is out of credit.

⚠ **`build_state: "complete"` is not the same as "built".** Judging `no_llm` by
counting failures across all `no_llm` docs is wrong — most are minted stubs that
were never built. Always filter `build_state: "complete"` first.

---

## 3. Register the flow code BEFORE generating artwork

`config/fulfilment_flows.yaml` is the registry. **One trigger per flow, even when the
envelope is identical.** Two audiences with the same pack-out still get different
codes, or the first response rate you ever measure is uninterpretable.

Current codes:

| code | audience | ownership evidence |
|---|---|---|
| `Fields_01.x` | looked an address up on `/off-market` | **inferred** from a page view |
| `Fields_02.x` | submitted the address via Analyse Your Home | **self-submitted** |

Write the work order into `system_monitor.fulfilment_work_orders` before generating,
because `generate_mailers_v2.flow_for()` reads the code back out of it per slug. A
mixed batch then gets the right code per piece automatically.

⚠ A code is never reused or redefined. Pieces already posted carry the old meaning.

---

## 4. Generate artwork

```bash
python3 11_House_Mini_Site/_shared/mailer_v2/generate_mailers_v2.py --slug <slug> [<slug> …]
```

The QR encodes:

```
/your-home/<slug>?utm_source=mailer&utm_medium=print&utm_campaign=home_report_v2
                 &utm_content=<slug>&utm_term=<flow_code>#market
```

`utm_term` is the flow code — invisible to the reader, on every scan. Verified to
survive `strip-tracking-params` (strips only fbclid/gclid), to register as a PostHog
super property, and to persist in first-touch `sessionStorage` for conversion-time
read-back. No website change needed.

`--flow-code` overrides the per-slug lookup if you need to force one.

---

## 5. Verify — the checks that actually catch things

**a. Artwork verification is automatic** (`verify_pdf`) — 2 pages, every load-bearing
line present, character budgets. A failure renames to `<slug>.REJECTED.pdf`.

**b. Decode the QR out of the RENDERED PDF.** The string you intended to encode and
the string in the print file are separate claims.

```python
subprocess.run(["pdftoppm","-png","-r","300","-f","1","-l","1",pdf,base])
data,_,_ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(f"{base}-1.png"))
```

⚠ The source `assets/gen/<slug>/qr.png` does **not** decode under OpenCV at native
size even when the artwork is perfect. Verify the rendered PDF, never the source PNG.
⚠ Detection is resolution-sensitive: one piece failed at 300 dpi and read clean at
150, 450 and 600. Retry at another dpi before believing a failure.

**c. Look at the hero photos.** The gate cannot judge an image.
**27 of the first 50 had a Google Street View capture as their only photo** (homes
never listed have no Domain photos), and **7 were unusable** — house behind a tree, a
parked car or a boat filling the frame. Render them to a contact sheet and look.
Swap bad ones out; the ready pool is usually far larger than the batch.

⚠ "has 7 photos" does NOT mean a good hero — `photos[0]` may still be a
`street_view_fallback`. Check `photos[0].meta.picked_by`.

---

## 6. Lay up for the press — ONE file, bleed, marks

Pronto's RIP spec, from John 2026-08-20 — treat it as the standing format, not a
one-off:

| Question | Answer |
|---|---|
| Bleed | **3 mm, with crop + registration marks** (not a tagged TrimBox alone) |
| File shape | **one combined PDF, 100 pages, in manifest row order** — not 50 files |
| Colour | **RGB is fine, Pronto convert** — do not embed a CMYK profile |

```bash
python3 build_pronto_print_pdf.py --batch pronto_batch_YYYY-MM-DD --verify
python3 build_pronto_print_pdf.py --batch pronto_batch_YYYY-MM-DD --write
```

Reads `manifest.csv` in row order and lays each A4 page onto a 230×317 sheet:
trim 210×297, bleed 216×303 (both boxes tagged), crop marks offset 3 mm, reg
targets mid-edge. Piece *n* lands on pages *2n-1* and *2n*.

⚠ **The artwork is never scaled to create bleed.** Enlarging to fill 3 mm eats
3 mm of design at every edge, and the tightest text on page 2 sits 5.6 mm off
trim. The bleed is made by stretching the outermost 0.5 mm of each edge outward
— exact here only because every edge is flat colour (green band, cream field,
green CTA band) and no photo reaches an edge. **If the layout changes so that a
photo or text touches the trim edge, this stops being lossless** — re-render with
real bleed instead.

⚠ `show_pdf_page` defaults to `keep_proportion=True`, which scales a 0.5 mm
strip to fit and centres it, leaving a **white hairline** just outside trim. It
is invisible at page zoom and prints on any cut that runs 1 mm out. That is why
`bleed_gaps()` checks all 100 pages pixel-wise across the trim line, and why the
build refuses on a gap. It also re-decodes all 50 QRs **in the combined file** —
the lay-up is a re-render, so the codes are re-proved after it, not before.

## 6b. Package and send

```
Fulfilment — Pronto Direct/            permanent parent, automation targets this
└── <codes>_<YYYY-MM-DD>/
    ├── Fields_50pieces_100pp_bleed3mm_crops_<date>.pdf   ← the print file
    ├── manifest.csv                   one row per piece, flow_code column
    ├── fulfilment_flows.yaml          so John can see the spec
    └── READ_ME_print_spec_<date>.txt  what changed + the three spec answers
```

Superseded artwork goes into a dated `SUPERSEDED_..._DO_NOT_PRINT` subfolder —
never left beside the live file, never silently deleted (John may already hold it).

⚠ **Zipping does not help** — 99% of original, because the PDFs already contain
compressed JPEGs. 50 pieces ≈ 120 MB, ~5× Gmail's limit. Drive link, always.

Keep `manifest.csv` **outside** any zip so John can read the address list in the
browser without a 120 MB download.

**Sharing:** grant `sales@prontodirect.com.au` viewer access on the folder. Do not
use "anyone with the link" — it is a list of home addresses.

---

## 7. Stock — check before planning the run

**Pronto hold our C4 envelopes and fridge magnets** (they print the mailer per job
from our PDFs, so paper is not our stock).

```bash
python3 scripts/fulfilment_stock.py            # current position
python3 scripts/fulfilment_stock.py --plan 50  # feasible? exits 1 if short
```

Receipts are recorded in the `stock:` block of `config/fulfilment_flows.yaml`.
Balance is **computed, never stored**, so it cannot drift:

    on_hand   = receipts - pieces on work orders with status "posted"
    available = on_hand  - pieces on work orders prepared/sent but not yet posted

The reserved half matters: a work order at "prepared" has not burned an envelope
yet, but it is spoken for. Counting only "posted" would let two batches be planned
against the same 100 envelopes, and the second would fail at Pronto rather than here.

⚠ **Envelopes bind before magnets** at 1 + 2 per piece. Opening position
(confirmed by Will, delivered 2026-08-17): **100 envelopes, 250 magnets**. With the
first 50 reserved that leaves **50 postable pieces** — one more run — against 113
addresses already mailable and a 6-touch flow planned.

`build_mailer_batch.py` warns (does not block) when a batch exceeds postable stock —
building is harmless, posting is not.

⚠ **Mark a work order `posted` once Pronto confirm lodgement**, or stock will read
as permanently reserved and never consumed.

---

## Contacts

**Pronto Direct**, Molendinar — John Thwaites,
`sales@prontodirect.com.au`, 0400 526 533. Holds stock, packs and lodges from a
coded work order.

---

## Open items (2026-08-17)

- **`229 homes` claim.** The headline says "the 229 homes buyers can choose from" and
  "reviewing **all** 229". There are **419** for sale in that catchment; 229 is the 55%
  we hold feature data for. `DEFAULT_CATCHMENT` is a fixed 9-suburb list so *every*
  property prints the same 229, and 3 of those 9 suburbs have no data at all. The
  ratio is sound; the wording is not. Will chose to ship and refine later.
- **Google Maps imagery in print.** Aerials and Street View carry "Google" and
  "Imagery ©Airbus, Vexcel". Maps Platform terms restrict print use. Unresolved.
- **Lead hook repetition.** 17 of 19 mailers led with `competition` — the fixed-hook
  problem the scoring rewrite was meant to solve (see README).
- **Touches 2–6 undefined** for both flows, deliberately. Define each before dispatch
  so it has a recorded hypothesis.
