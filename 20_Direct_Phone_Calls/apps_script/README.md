# ☎ Call panel — install & operate

A sidebar in the **Marketing Phone Calls** sheet. Select a row → the panel shows
that person's brief → one button opens the JustCall dialer in a small popup, with
the spreadsheet still visible behind it so you type notes straight into the row.

---

## Why it is built this way

**The JustCall API cannot place this call.** All 87 documented endpoints were
checked. The only outbound one — [`initiate_outbound_call_v21`][init] — triggers an
*AI Voice Agent* to speak to the person instead of you, and requires documented
prior consent. It is a different product, not this feature.

What JustCall does offer is a **dialer deep link**:

```
https://app.justcall.io/dialer?numbers=+61416529481&medium=custom&metadata=<call_id>&metadata_type=string
```

It is a plain URL. No credentials, so **no secret is ever stored in a spreadsheet
that gets shared**.

**Why a sidebar and not a link in the cell.** Two reasons, both fatal to the
simpler approach:

1. Google Sheets' `HYPERLINK()` only permits `http/https/mailto/aim/ftp/gopher/
   telnet/news`. A `tel:` link renders as plain unclickable text — it fails
   *silently*, the worst failure mode for a dial button.
2. An `https` link in a cell opens a full browser **tab**, covering the sheet.
   You asked to keep the grid visible. Only a sidebar popup does that.

---

## Install (once, ~3 minutes)

You have to do this part — a service account cannot attach a script to a
spreadsheet, and this script deliberately holds no credentials.

1. Open the [Marketing Phone Calls sheet][sheet].
2. **Extensions → Apps Script**. A new tab opens.
3. Delete the stub in `Code.gs`, paste the full contents of
   [`Code.gs`](Code.gs), and save.
4. **＋ → HTML** next to *Files*. Name it exactly **`Sidebar`** (Apps Script adds
   `.html`). Delete its stub, paste [`Sidebar.html`](Sidebar.html), save.
5. Back on the spreadsheet tab, reload the page. A **☎ Calling** menu appears
   next to *Help*.
6. **☎ Calling → Open call panel**. First run asks for authorisation — approve
   it; the scope is this spreadsheet only.

Then, so it is always there: **☎ Calling → Open call panel** each session, or
leave the tab open.

---

## Using it

Select any row in the `Call List` tab. The panel shows name, number, address,
the *Why now* hook, property facts, occupancy verdict and DNC status — then one
green **☎ Call** button.

Clicking it opens a 420×720 popup with the number pre-loaded. Press call in
JustCall. **The sheet is still there behind it** — click back onto the grid and
type into the ☎ OUTCOME / ☎ COMMENTS / ☎ CALL BACK columns while you talk.

The panel also has an outcome dropdown and comment box if that is faster than
reaching for the cell. Comments are **appended with a timestamp, never
replaced**, and an existing outcome is never overwritten without a confirm — see
"human-owned columns" below.

If the popup is blocked, allow popups for `docs.google.com`, or use the smaller
*open the JustCall desktop app* link, which uses `justcall://` and floats the
slim desktop dialer over everything.

---

## The compliance gate

Making dialling one click means every reason **not** to dial has to be enforced
at that click rather than remembered. The button does not render at all unless
the row passes all of:

| Check | Source |
|---|---|
| Column J holds a real wash date — not blank, not `⛔ NOT WASHED` | DNCR Act 2006 s11(3), burden on us under s11(6) |
| Mon–Fri 9:00am–6:00pm · Sat 9:00am–5:00pm | ACL s73 (stricter than ACMA, so it governs) — mirrors [CALLER_CARD.md §2](../01_Compliance/CALLER_CARD.md) |
| Not a Sunday | Telemarketing Standard s8(1)(e) |
| Not a national public holiday | Standard s8(3) |
| Column D parses as a dialable AU number | — |

A blocked row shows **why, in words**, instead of a button.

Two deliberate design choices:

- **The DNC test is positive, never negative.** The row is dialable only if the
  wash column holds a real date. Blank, unwashed, and unrecognised all fail —
  the safe direction.
- **An unknown year does not silently pass.** `NATIONAL_HOLIDAYS` covers 2026 and
  2027. Past that, the panel does not quietly allow calling; it shows a warning
  and disables the button behind a checkbox you must tick. **Extend the table in
  `Code.gs` when 2028 approaches.**

**Known gap, inherited not introduced:** QLD-only public holidays are *not*
blocked. Standard s8(3) covers Commonwealth holidays; whether to block state ones
is still an open decision ([CALLER_CARD.md §123](../01_Compliance/CALLER_CARD.md)).

Occupancy is a **warning, not a block** — `⚠ PRIOR OCCUPANT` means you may be
about to ask a stranger about a house they sold years ago, but it is a judgement
call, not a legal bar.

---

## Two safeguards worth knowing about

**The layout guard.** `assertLayout()` checks the header row on every read and
refuses to run if columns C/D/J/L/Q are not where it expects. If someone inserts
a column, every lookup would shift by one and the panel would offer to dial *a
different person than the one whose name it displays*. That is the worst thing
this tool could do, so it is checked rather than assumed. If you see **"Panel
disabled"**, that is this guard — fix the sheet, or update `C{}` in `Code.gs` and
`HEADERS` in [`sheet_common.py`](../scripts/sheet_common.py) **together**.

**Human-owned columns.** L/M/N (`☎ OUTCOME`, `☎ COMMENTS`, `☎ CALL BACK`) hold the
only copy of your notes until `read_call_outcomes.py` copies them out, and
`assert_machine_range()` stops the Python side from ever writing them. The panel
writing them is a different thing — that is *you* pressing a button — but it
honours the same intent: comments append, outcomes need a confirm to replace, and
rows are located by the hidden Call ID in column Q, **never by row number**
(every new day's block is inserted at the top and pushes every row down).

---

## The `metadata` parameter is the second half of this

Every deep link carries the row's Call ID as `metadata`, and **JustCall relays it
back in every webhook payload**. So a call event arrives already knowing which row
it belongs to.

That is what lets [`justcall_sync.py`](../scripts/justcall_sync.py) join on an
exact key instead of normalised phone digits. Under the old join an unmatched call
is a fact the code cannot resolve — "Will dialled someone by hand" and "the join
broke" look identical. With metadata they are distinguishable.

[init]: https://developer.justcall.io/reference/initiate_outbound_call_v21.md
[sheet]: https://docs.google.com/spreadsheets/d/1txehsp26ZkF3t7wDEbewNJ35UWpyk3d286uc8oUQMP8/edit
