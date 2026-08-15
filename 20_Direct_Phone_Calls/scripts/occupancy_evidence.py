#!/usr/bin/env python3
"""
occupancy_evidence.py — is this person still at this address?

ID4ME returns EVERY person it has ever associated with an address — 12 people at
20 Chantilly Place, spanning 1997 to 2023. Most are previous occupants. Dialling
them wastes the call, wastes a DNC wash credit (we pay per number), and puts a
stranger on the phone being asked about a house they sold fifteen years ago.

This module dates each person against the property's last recorded SALE and against
our own contact history, and returns a verdict with its reasoning.

    from occupancy_evidence import assess_occupancy
    a = assess_occupancy(gc_doc, person, our_contacts)
    a["verdict"]      # current_likely | prior_occupant | unknown
    a["confidence"]   # 0.0 - 1.0
    a["reasoning"]    # a sentence naming the dates it compared

CLI:
    python3 occupancy_evidence.py --address "20 Chantilly Place, Robina, QLD 4226"
    python3 occupancy_evidence.py --audit-queue        # re-assess every call_queue row

⚠ THE INFERENCE IS DELIBERATELY ASYMMETRIC — READ THIS BEFORE TRUSTING A VERDICT
--------------------------------------------------------------------------------
`ID4ME_Source_Date_Latest` is the date the DATA VENDOR last saw this person
associated with this address. It is NOT a move-in date and NOT a "last contacted"
date. That asymmetry drives everything here:

  record date BEFORE the last sale  -> STRONG evidence they left.
      The vendor's most recent sighting of them predates a change of ownership.
      People do not usually stay after selling.

  record date AFTER the last sale   -> WEAK-MODERATE evidence they are current.
      It only means the vendor saw them there post-sale. They may have moved out
      since without any sale occurring — a rental, a death, a family change. The
      older the record, the weaker this gets.

So a `prior_occupant` verdict is far more reliable than a `current_likely` one.
Treat `current_likely` as "not excluded", never as "confirmed owner".

⚠ ID4ME'S OWN CONTACT-RECENCY FIELDS ARE EMPTY. Verified 2026-08-15 across every
raw record we hold: `ID4ME_Raw_last_called_date_mobile`, `..._landline`, `..._name`,
`..._address`, `ID4ME_Raw_live_called` and `ID4ME_Raw_home_owner_renter` are all
None — the search index does not populate them. So "date of last contact" cannot
come from ID4ME. It comes from OUR OWN records (a lead who typed their address into
our site, an off-market page view, a previous call), which is better evidence anyway
because we know exactly what it means.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from zoneinfo import ZoneInfo  # noqa: E402

AEST = ZoneInfo("Australia/Brisbane")

# A settlement and the vendor's record of it do not land on the same day. A person
# record dated within this window BEFORE a sale is treated as ambiguous rather than
# conclusively prior — it may be the buyer captured around settlement.
SETTLEMENT_GRACE_DAYS = 120

# A record this old tells us little about who lives there now, whatever it says
# relative to the sale.
STALE_RECORD_YEARS = 6.0

VERDICT_CURRENT = "current_likely"
VERDICT_PRIOR = "prior_occupant"
VERDICT_UNKNOWN = "unknown"


def _parse_date(v):
    """ID4ME and Domain both hand us several shapes. Return tz-aware UTC or None."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return None
    s = s.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def last_sale(gc_doc: dict):
    """(date, price) of the most recent genuine SALE, or (None, None).

    ⚠ Filters on type == 'Sale'. The timeline also carries Rental/Lease events, and
    this codebase has twice shipped bugs that read a lease as a sale
    (memory: rental_as_sale_bug_2026-07-22, sold_pipeline_lease_as_sale_gap).
    Treating a rental listing as a sale here would date every tenant as an owner.
    """
    tx = ((gc_doc.get("enriched_data") or {}).get("transactions")) or []
    best, best_price = None, None
    for t in tx:
        if str(t.get("type", "")).strip().lower() != "sale":
            continue
        d = _parse_date(t.get("date"))
        if d and (best is None or d > best):
            best, best_price = d, t.get("price")
    return best, best_price


def person_record_date(person: dict):
    return _parse_date(person.get("ID4ME_Source_Date_Latest"))


def our_last_contact(our_contacts: list | None):
    """Most recent date WE have evidence of this household engaging with us.

    Unlike the ID4ME vendor date, we know precisely what this means: somebody at
    this address typed it into our site, opened their off-market page, or answered
    our call. Each entry: {"date": ..., "kind": "...", "detail": "..."}.
    """
    best = None
    for c in (our_contacts or []):
        d = _parse_date(c.get("date"))
        if d and (best is None or d > best):
            best = d
            best_kind = c.get("kind", "contact")
            best_detail = c.get("detail", "")
    return (best, best_kind, best_detail) if best else (None, None, None)


def _years_between(a: datetime, b: datetime) -> float:
    return abs((b - a).days) / 365.25


def assess_occupancy(gc_doc: dict, person: dict, our_contacts: list | None = None,
                     now: datetime | None = None) -> dict:
    """Verdict + confidence + the dates it compared. Never raises on missing data —
    an absent date yields `unknown`, which is a fact, not a failure."""
    now = now or datetime.now(timezone.utc)
    sale_dt, sale_price = last_sale(gc_doc)
    rec_dt = person_record_date(person)
    ours_dt, ours_kind, ours_detail = our_last_contact(our_contacts)

    ev = {
        "last_sale_date": sale_dt.date().isoformat() if sale_dt else None,
        "last_sale_price": sale_price,
        "id4me_record_date": rec_dt.date().isoformat() if rec_dt else None,
        "our_last_contact_date": ours_dt.date().isoformat() if ours_dt else None,
        "our_last_contact_kind": ours_kind,
        "our_last_contact_detail": ours_detail,
        "record_age_years": round(_years_between(rec_dt, now), 2) if rec_dt else None,
        "assessed_at": datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST"),
    }

    # --- 1. OUR OWN contact is the best evidence we have. ------------------------
    # Somebody at this address engaged with us. If that happened after the last
    # sale, the household that engaged is the post-sale household. This is a
    # property-level signal, not a person-level one — it does not tell us WHICH
    # person, so it can raise the floor but never confirm an individual.
    ours_after_sale = bool(ours_dt and sale_dt and ours_dt > sale_dt)

    # --- 2. No sale on record -> nothing to date against. ------------------------
    if not sale_dt:
        if ours_after_sale:  # unreachable without sale_dt, kept for clarity
            pass
        if rec_dt and _years_between(rec_dt, now) <= 2.0:
            return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.45,
                    "reasoning": (
                        f"No sale is recorded for this property, so there is no ownership "
                        f"change to date the person against. Their record is recent "
                        f"({ev['record_age_years']}y old), which is mildly encouraging and "
                        f"nothing more.")}
        return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.2,
                "reasoning": ("No sale is recorded for this property and the person record "
                              "is old or undated — we cannot say who lives here.")}

    # --- 3. No usable person date. -----------------------------------------------
    if not rec_dt:
        if ours_after_sale:
            return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.4,
                    "reasoning": (
                        f"This person carries no record date, so they cannot be dated "
                        f"against the {ev['last_sale_date']} sale. However someone at this "
                        f"address contacted us on {ev['our_last_contact_date']} "
                        f"({ours_kind}), after that sale — so the household is current even "
                        f"though this individual is unverified.")}
        return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.15,
                "reasoning": ("This person carries no record date — there is nothing to "
                              "compare against the sale.")}

    # --- 4. The core comparison. --------------------------------------------------
    days = (rec_dt - sale_dt).days

    if days < -SETTLEMENT_GRACE_DAYS:
        # STRONG negative. The vendor's last sighting predates the sale.
        conf = 0.85 if abs(days) > 730 else 0.7
        return {**ev, "verdict": VERDICT_PRIOR, "confidence": conf,
                "days_record_after_sale": days,
                "reasoning": (
                    f"Their most recent record is {ev['id4me_record_date']}, which is "
                    f"{abs(days)} days BEFORE the property sold on {ev['last_sale_date']}. "
                    f"The data vendor has not seen them at this address since before it "
                    f"changed hands — they are almost certainly a previous occupant.")}

    if days < 0:
        # Inside the settlement window — genuinely ambiguous, could be the buyer.
        return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.4,
                "days_record_after_sale": days,
                "reasoning": (
                    f"Their record ({ev['id4me_record_date']}) falls {abs(days)} days before "
                    f"the {ev['last_sale_date']} sale — inside the {SETTLEMENT_GRACE_DAYS}-day "
                    f"settlement window, so they may be the buyer captured around settlement "
                    f"or the seller on the way out. Cannot separate the two.")}

    # Record postdates the sale — consistent with current occupancy, but this is
    # the WEAK direction (see the module docstring), so confidence stays capped and
    # decays with the age of the record.
    age = _years_between(rec_dt, now)
    if age > STALE_RECORD_YEARS:
        return {**ev, "verdict": VERDICT_UNKNOWN, "confidence": 0.35,
                "days_record_after_sale": days,
                "reasoning": (
                    f"Their record ({ev['id4me_record_date']}) postdates the "
                    f"{ev['last_sale_date']} sale, but it is {age:.1f} years old. They could "
                    f"have moved on since without a sale being recorded — too stale to call.")}

    conf = 0.75 if age <= 2 else 0.6 if age <= 4 else 0.5
    if ours_after_sale:
        conf = min(0.9, conf + 0.1)
    reason = (f"Their record ({ev['id4me_record_date']}) postdates the "
              f"{ev['last_sale_date']} sale by {days} days and is {age:.1f} years old, "
              f"so they were at this address after it last changed hands.")
    if ours_after_sale:
        reason += (f" Someone at this address also contacted us on "
                   f"{ev['our_last_contact_date']} ({ours_kind}), after that sale.")
    reason += (" This is consistent with current occupancy but does not confirm it — a "
               "vendor record date is not a move-in date.")
    return {**ev, "verdict": VERDICT_CURRENT, "confidence": round(conf, 2),
            "days_record_after_sale": days, "reasoning": reason}


def rank_people(gc_doc: dict, id4me: dict, our_contacts: list | None = None) -> list:
    """Every person at the address, best current-occupant candidate first."""
    order = {VERDICT_CURRENT: 0, VERDICT_UNKNOWN: 1, VERDICT_PRIOR: 2}
    out = []
    for p in (id4me.get("ID4ME_People") or []):
        a = assess_occupancy(gc_doc, p, our_contacts)
        out.append({"person": p, "assessment": a})
    out.sort(key=lambda r: (order[r["assessment"]["verdict"]],
                            -r["assessment"]["confidence"],
                            -(len(r["person"].get("ID4ME_Mobiles") or []))))
    return out


# ---------------------------------------------------------------------------
def _mask(n):
    return ("*" * max(0, len(n) - 3)) + n[-3:] if n else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    ap.add_argument("--suburb")
    ap.add_argument("--audit-queue", action="store_true",
                    help="re-assess every call_queue row and report the split")
    ap.add_argument("--apply", action="store_true",
                    help="with --audit-queue, write the assessment onto each queue doc")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"), override=False)
    from shared.db import get_client, get_gold_coast_db

    if args.audit_queue:
        from collections import Counter
        q = get_client()["system_monitor"]["call_queue"]
        gdb = get_gold_coast_db()
        counts, applied = Counter(), 0
        for d in q.find({}):
            sub = d.get("suburb")
            doc = None
            if sub and d.get("address"):
                doc = gdb[sub].find_one({"address": d["address"]})
            if not doc:
                counts["no_property_doc"] += 1
                continue
            sale_dt, _ = last_sale(doc)
            counts["sale_known" if sale_dt else "no_sale_recorded"] += 1
            if args.apply and sale_dt:
                q.update_one({"_id": d["_id"]},
                             {"$set": {"occupancy.last_sale_date": sale_dt.date().isoformat(),
                                       "occupancy.assessed_at": datetime.now(AEST)}})
                applied += 1
        print(f"call_queue audit — {sum(counts.values())} rows")
        for k, v in counts.most_common():
            print(f"  {v:>5}  {k}")
        if args.apply:
            print(f"  wrote occupancy data to {applied} rows")
        return

    if not args.address:
        ap.error("need --address or --audit-queue")

    gdb = get_gold_coast_db()
    subs = [args.suburb] if args.suburb else gdb.list_collection_names()
    doc = None
    for s in subs:
        doc = gdb[s].find_one({"address": re.compile(f"^{re.escape(args.address)}", re.I)})
        if doc:
            break
    if not doc:
        print(f"no property document found for {args.address!r}")
        sys.exit(1)

    id4me = doc.get("ID4ME_Contact_Data")
    if not id4me:
        print(f"{doc.get('address')}: no ID4ME_Contact_Data on this document — "
              "nothing to assess (run the append first).")
        sys.exit(1)

    sale_dt, sale_price = last_sale(doc)
    print(f"\n{doc.get('address')}")
    print(f"last recorded SALE: {sale_dt.date() if sale_dt else '(none)'}"
          + (f"  ${sale_price:,.0f}" if sale_price else ""))
    print(f"{len(id4me.get('ID4ME_People') or [])} people on record\n")

    for r in rank_people(doc, id4me):
        p, a = r["person"], r["assessment"]
        phones = (p.get("ID4ME_Mobiles") or []) + (p.get("ID4ME_Landlines") or [])
        blocked = set(p.get("ID4ME_DNCR_Blocked") or [])
        free = [x for x in phones if x not in blocked]
        name = (p.get("ID4ME_First_Name") or "?")[:1] + "."
        print(f"  {a['verdict']:<15} conf={a['confidence']:<5} {name:<4} "
              f"rec={a['id4me_record_date'] or '—':<11} "
              f"phones={len(phones)} (advisory-clear {len(free)})")
        print(f"      {a['reasoning']}")
        if free:
            print(f"      advisory-clear: {', '.join(_mask(x) for x in free)}")
        print()


if __name__ == "__main__":
    main()
