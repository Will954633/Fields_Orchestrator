# 20_Direct_Phone_Calls — runbook

Outbound calls to Gold Coast homeowners: ID4ME-sourced numbers → DNC wash → daily
call list in a Google Sheet → human caller on JustCall → recording + transcript → CRM.

**Read [`00_SCOPING.md`](00_SCOPING.md) before touching anything.** It holds the legal
contract, the funnel maths and the open gates. The compliance pack the caller actually
uses is [`01_Compliance/CALLER_CARD.md`](01_Compliance/CALLER_CARD.md) and
[`01_Compliance/CALL_SCRIPT.md`](01_Compliance/CALL_SCRIPT.md).

**Sheet:** [Marketing Phone Calls](https://docs.google.com/spreadsheets/d/1txehsp26ZkF3t7wDEbewNJ35UWpyk3d286uc8oUQMP8/edit) · tab **Call List**

---

## ⛔ Before the first dial

| # | Gate | Who | Status |
|---|---|---|---|
| 1 | Buy DNC Register **Type B** subscription, $126/yr, 20,000 washes, donotcall.gov.au | Will | **open — blocks all cold calls** |
| 2 | Turn call recording **ON** for +61440131629 (JustCall dashboard → Phone Numbers → Advanced Settings — **no API for this**) | Will | **open** |
| 3 | Prove transcription entitlement: one recorded test call, then `justcall_sync.py --test-transcription` | either | **open** |
| 4 | Ask ID4ME for the **licensed API** ($155/mo). `can_use_api` is false and their ToS forbids automated extraction, cap 800/day | Will | **open** |
| 5 | Measure DNC attrition on a 100-number sample — it decides the round size | agent | blocked on #1 |

⚠ Gate 1 is not paperwork. **ID4ME's DNC flag gives us no legal defence** — the
DNCR Act s11(3) safe harbour belongs only to whoever submitted the list, and ACMA
says so explicitly for real estate agents. Penalties reach $2.22M/day. Nothing dials
until we hold our own wash.

---

## Daily cycle

```bash
cd /home/fields/Fields_Orchestrator/20_Direct_Phone_Calls/scripts
source /home/fields/venv/bin/activate

# 1. Build/refresh the candidate pool  (does NOT call ID4ME — consumes stored data)
python3 build_call_list.py --build --track B_intent --dry-run
python3 build_call_list.py --build --track B_intent
python3 build_call_list.py --needs-id4me --out /tmp/append.csv   # human-paced append list

# 2. Wash — the legal gate. Nothing is dialable until this round-trips.
python3 dnc_wash.py --export                     # -> CSV; upload manually at donotcall.gov.au
python3 dnc_wash.py --import result.csv --submission-id SUB-...
python3 dnc_wash.py --status                     # re-wash before the earliest expiry

# 3. Push tomorrow's list to the TOP of the sheet
python3 call_list_to_sheet.py --limit 25 --dry-run
python3 call_list_to_sheet.py --limit 25

# 4. ——— the human makes the calls, typing into columns K / L / M ———

# 5. Harvest what they typed, and sync JustCall
python3 read_call_outcomes.py
python3 justcall_sync.py --since 2
python3 read_call_outcomes.py --report           # connects vs the 30–50 target
```

⚠ **Re-wash every 30 days.** `dnc_wash.py --status` prints the earliest expiry and the
latest safe re-export date. A number whose wash has lapsed is not dialable and
`call_list_to_sheet.py` will not list it.

---

## The sheet contract — why the caller's work is safe

The sheet is **never rebuilt and never cleared.** Each day's block is *inserted* at
row 2 (`insertDimension`, `inheritFromBefore:false`), so everything below shifts down
carrying its values, comments, notes and colours. Newest day sits at the top.

| Cols | Owner | Behaviour |
|---|---|---|
| **A–K** | machine | written once at insert, never touched again |
| **L ☎ OUTCOME · M ☎ COMMENTS · N ☎ CALL BACK** | **human** | **never written by any script** |
| **O Recording · P Transcript** | machine | refreshed one cell at a time, located by the hidden Call ID |
| **Q Call ID** | machine | hidden; the stable key — rows move daily, positions are never used |

---

## Occupancy dating — who actually lives there

[`occupancy_evidence.py`](scripts/occupancy_evidence.py) dates every ID4ME person
against the property's **last recorded sale**, because ID4ME returns everyone it has
*ever* associated with an address — 12 people at 20 Chantilly Place spanning 1997→2023,
against a 2009 sale. Column **I (Occupant?)** carries the verdict.

```bash
python3 occupancy_evidence.py --address "20 Chantilly Place" --suburb robina
python3 occupancy_evidence.py --audit-queue
```

⚠ **The inference is asymmetric — do not read the two verdicts as equally strong.**
`ID4ME_Source_Date_Latest` is when the *data vendor* last saw that person at that
address. It is **not** a move-in date.

- Record dated **before** the sale → **strong** evidence they left. Row is dropped and
  counted as `prior_occupant_dated_before_sale`, so we also don't pay to wash the number.
- Record dated **after** the sale → **weak-moderate** evidence they're current. They may
  have moved on since with no sale recorded. Labelled *"likely current"*, never
  *"confirmed"*, and confidence is shown so a 0.5 doesn't read like a 0.85.

⚠ **ID4ME's own contact-recency fields are empty** — `last_called_date_mobile`,
`..._landline`, `..._name`, `..._address`, `live_called` and `home_owner_renter` are
`None` on every raw record we hold (verified 2026-08-15). So "date of last contact"
comes from **our** records, which is better evidence anyway because we know what it
means: 179 of 218 candidate addresses have at least one dated engagement with us
(worklist first/last seen, property report, AYH submission, seller message).

⚠ **Prior call outcomes are not yet a signal** — `call_outcomes` and `call_activity` are
empty because no call has been made. That will be the strongest signal of the lot.
**Wire it in after round 1.**

Rows are capped at **2 per address** (`--max-per-address`) in rank order. Dialling five
people at one house is exactly what gets us complained about.

`sheet_common.assert_machine_range()` **raises** if any write range overlaps K/L/M.
It is a runtime guard, not a comment, so a future refactor that widens a range fails
loudly instead of erasing a week of the caller's notes.

**Verified empirically 2026-08-15**, not assumed: two day-blocks inserted with
simulated caller edits between them — the edits moved down intact and stayed attached
to the correct person; separator rows are skipped by the harvester; the guard fires;
unit addresses like `1/35 Thornleigh Crescent` are not coerced into dates (writes are
`RAW`, `USER_ENTERED` is confined to the two hyperlink columns).

The **outcome dropdown is non-strict on purpose**: a rejected keystroke mid-call loses
the note entirely, a non-standard value we can clean up later. Free-hand outcomes are
kept verbatim and counted separately.

Write-back is **strictly one-way, sheet → Mongo**. The sheet is the source of truth for
human columns.

### Suppression is mechanical
An outcome of *not interested*, *DO NOT CONTACT AGAIN* or *refused recording* sets the
queue doc to `do_not_contact` permanently, **and suppresses the same phone number at
every other address**. Standard s13(1)(b) and ACL s75(2) mean this must not depend on
a human re-reading a free-text comment before the next round.

---

## Collections (`system_monitor`)

| Collection | Written by | Holds |
|---|---|---|
| `call_queue` | `build_call_list.py` | one doc per (address, phone); `dnc` sub-doc; `status` queued→listed→called / do_not_contact |
| `dnc_submissions` | `dnc_wash.py` | the s11(6) evidence trail — what we submitted, when |
| `call_list_sheet_ledger` | `call_list_to_sheet.py` | dedupe; a row deleted by hand is never resurrected |
| `call_outcomes` | `read_call_outcomes.py` | what the caller typed |
| `call_activity` | `justcall_sync.py` | calls, recordings, transcripts, keyed on `call_sid` |

⚠ **JustCall's API only exposes the last 3 months.** Anything unsynced in that window
is unrecoverable except by emailing their support — which is why the nightly
reconciliation is mandatory and must never advance its watermark on a failed run.

---

## Deliberately not built

- **No AI voice agent** — Pro Plus + metered, and its own `has_consent:true` flag blocks cold use.
- **No cold SMS, ever** — Spam Act 2003; an appended number carries no consent and the onus is on the sender. DNC status is irrelevant to this.
- **No auto-dialler** — every call is a human pressing dial.
