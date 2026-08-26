#!/usr/bin/env python3
"""
build_call_list.py — select, score and queue homeowner candidates for outbound calls.

This is the TOP of the direct-call funnel described in 20_Direct_Phone_Calls/00_SCOPING.md.

  Gold_Coast.<suburb> ──┐
  lead_worklist       ──┼─→ build_call_list.py ─→ system_monitor.call_queue
  ID4ME (already on doc)┘        (score + hook)          │
                                                         ├─→ dnc_wash.py (owns DNC status)
                                                         ▼
                                              call_list_to_sheet.py (owns the Sheet)

What this script deliberately does NOT do
-----------------------------------------
* It does NOT dial. Every call is a human pressing dial (scoping §10).
* It does NOT decide DNC status. Every row leaves here `dnc.status = "unwashed"`.
  Only dnc_wash.py — which performs OUR OWN wash, the only thing that buys the
  DNCR Act 2006 s11(3)(a) 30-day safe harbour (ACMA IS 157: an externally
  provided list carries no defence) — may promote a number. ID4ME's own flag is
  recorded as *advisory only* under `dnc.id4me_advisory`.
* It does NOT write the Google Sheet. `call_list_to_sheet.py` owns that surface.
* It does NOT call ID4ME. Their ToS forbids "automated programs or other data
  extraction systems" and caps 800 searches/day, and `can_use_api` is false on our
  subscription (scoping §9.5). This script CONSUMES `ID4ME_Contact_Data` already
  present on a property document, and `--needs-id4me` emits the ranked address list
  for a HUMAN-PACED append run.

Seller intent (added 2026-08-15)
-------------------------------
Ranking used to answer only "can we reach this person?". It now also answers "is
there a reason to ring them?", by JOINING the seller-intent layer this repo already
computes nightly — `system_monitor.lead_worklist.seller_intent`
(scripts/samantha/seller_intent.py). Read-only: nothing here writes lead_worklist.

  * `moment` (a <=3-day-old strong signal, e.g. "Just generated a home valuation") is
    the largest single intent term AND DECAYS TO NOTHING BY 14 DAYS, measured from the
    signal itself, not from the last enrichment run.
  * `hotness` / `behavioral_score` are continuous and saturated, not bucketed.
  * ⚠ `on_market_fresh` is a STRONG NEGATIVE. It means the owner has just committed to
    a competing agent — seller_intent scores it hotness -6 — and must never read as hot.
  * Positive intent is scaled by ID4ME record freshness (`reach_factor`), so a hot lead
    on a six-year-old phone record keeps only 40% of the bonus. An unreachable hot lead
    is worth nothing.
  * The join is asserted (Rule 7b): a collapse below a 50% address join rate raises,
    because the measured baseline is 100% and a silent zero would restore the old
    reachability-only order while looking like a normal run.
  * `--needs-id4me` uses the SAME score. The append is human-paced at ~50/day, so that
    ordering decides who we are able to call in week 1.
  * `intent_note` is a NEW, separate one-line field for the sheet. The property-specific
    `hook` is never overwritten, and the seller_intent `story` paragraph is never put in
    a cell — it is written for a CRM reader, carries PropRadar valuation figures and
    explicit "Approach:" coaching, and both are forbidden here (POA s215/s216; CLAUDE.md
    editorial rules). Every note is passed through `editorial_violations` before storage.

⛔ The POA Reg 2014 s21(3) listing-expiry exclusion is UNCHANGED and no scheduling is
built. --stats and --needs-id4me now only COUNT how many excluded leads carry the
`on_market_expiring` label, so the size of that open legal question is visible.

Tracks (scoping §1 — they are not legally the same thing)
---------------------------------------------------------
  A_warm       lead supplied their OWN number (FB Lead Ads + Analyse Your Home).
  B_intent     lead supplied their ADDRESS (off-market view / AYH / price alert);
               the number must be appended. COLD.
  C_openmarket core-suburb owner with no intent signal. COLD, weaker hook.

Usage
-----
  python3 build_call_list.py --stats
  python3 build_call_list.py --build --dry-run
  python3 build_call_list.py --build [--track A|B|C] [--suburb robina] [--limit 50]
                             [--max-per-address 2] [--include-prior]
  python3 build_call_list.py --needs-id4me [--out addresses.tsv] [--limit 200]

Who is still at the address
---------------------------
ID4ME returns every person it has ever associated with an address — 12 people at the
one sample property, spanning 1997 to 2023. Most are previous occupants. Every
ID4ME-sourced person is therefore dated against the property's last recorded SALE by
`occupancy_evidence.assess_occupancy` BEFORE a queue row exists:

  prior_occupant  -> NO ROW. Counted under `prior_occupant_dated_before_sale`, which
                     appears in --stats, because each suppressed number is a DNC wash
                     credit we would have paid for and a stranger we would have rung.
  current_likely  -> row, scored up. ⚠ "not excluded", NOT "confirmed owner".
  unknown         -> row, scored flat.

Rows per address are capped (--max-per-address, default 2) and ordered by
`rank_people`, so the strongest current-occupant candidate is the one that survives.

Never prints real names or phone numbers — everything human-readable is masked.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# repo root on the path (this file lives two levels down)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))
sys.path.insert(0, _HERE)

# Dating people against the property's last SALE — see occupancy_evidence.py.
# ⚠ The inference is ASYMMETRIC: `prior_occupant` is strong evidence, `current_likely`
# is weak ("not excluded", never "confirmed owner"). Everything downstream of this
# import — the exclusion, the score term, the sheet label — is written to respect that.
from occupancy_evidence import assess_occupancy, rank_people, last_sale  # noqa: E402
from test_addresses import TEST_ADDRESS_SLUGS, is_test_address  # noqa: E402

AEST = ZoneInfo("Australia/Brisbane")

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
SUBURB_LABEL = {"robina": "Robina", "varsity_lakes": "Varsity Lakes",
                "burleigh_waters": "Burleigh Waters"}
SUBURB_POSTCODE = {"robina": "4226", "varsity_lakes": "4227", "burleigh_waters": "4220"}

QUEUE_DB = "system_monitor"
QUEUE_COLL = "call_queue"

TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au"}
# Shared registry of Will's test addresses (scripts/test_addresses.py) — one place
# to edit so every lead surface (sheet, worklist, call list) blocks the same set.
TEST_SLUGS = set(TEST_ADDRESS_SLUGS)

# ── EXCLUSION: POA Regulation 2014 s21(3) ────────────────────────────────────
# s21 ("Prior appointment of another property agent") bites only where another
# agent's appointment IS IN FORCE. Expired/withdrawn appointments fall outside
# s21 entirely (see scoping §5 "Correction to existing memory"), BUT the
# "Listing Nearing Expiry" cohort is precisely the group whose appointment is
# still on foot — approaching them is the conduct s21(3) restricts. Named,
# explicit, and logged as a count in --stats so it can never become a silent
# omission. Round 1 excludes them.
S21_EXCLUDED_SOURCES = {"listing_expiry"}

# EXCLUSION: currently-listed properties (memory ayh_currently_listed_guard).
LISTED_STATUSES = {"for_sale", "under_contract"}

# Statuses a re-run must never downgrade back to "queued".
TERMINAL_STATUSES = {"called", "do_not_contact", "connected", "removed"}

# Editorial guard (CLAUDE.md Editorial Content Rules).
FORBIDDEN_WORDS = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]
ADVICE_PATTERNS = [
    r"\byou should\b", r"\bshould (?:sell|list|buy)\b", r"\bconsider (?:selling|listing|buying)\b",
    r"\bnow is a good time\b", r"\bgood time to (?:sell|list|buy)\b", r"\bwe recommend\b",
    r"\bworth selling\b", r"\byou need to\b", r"\bdon't miss\b",
]
PREDICTION_PATTERNS = [
    r"\bwill (?:rise|fall|increase|decrease|grow|drop|climb)\b", r"\bexpected to\b",
    r"\bforecast\b", r"\bpredict\w*\b", r"\bis set to\b", r"\bpoised to\b",
]
# "$1.25m" / "$1.2 million" style — CLAUDE.md requires $1,250,000.
BAD_MONEY_PATTERN = r"\$\s?\d+(?:\.\d+)?\s?(?:m\b|million\b|k\b)"


# ─────────────────────────────────────────────────────────────────────────────
# env / db
# ─────────────────────────────────────────────────────────────────────────────
def set_env_from_file():
    """Load our own environment (CLAUDE.md Rule 7 checklist item 3) — never trust
    the caller's cron line to have exported anything."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"), override=False)


# ─────────────────────────────────────────────────────────────────────────────
# small helpers
# ─────────────────────────────────────────────────────────────────────────────
def now_utc():
    return datetime.now(timezone.utc)


def now_aest_str():
    return datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")


def slugify(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")


def address_slug(address: str) -> str:
    """'20 Chantilly Place, Robina, QLD 4226' -> '20-chantilly-place-robina'.
    Matches the url_slug convention already in Gold_Coast (state + postcode dropped)."""
    a = (address or "").strip()
    a = re.sub(r",?\s*(QLD|NSW|VIC|SA|WA|NT|TAS|ACT)\b.*$", "", a, flags=re.I)
    a = re.sub(r"\b\d{4}\b\s*$", "", a)
    return slugify(a)


def suburb_from_address(address: str) -> str | None:
    a = (address or "").lower()
    for key in CORE_SUBURBS:
        if SUBURB_LABEL[key].lower() in a or key in a:
            return key
    return None


def normalise_phone(raw) -> tuple[str, str] | None:
    """-> (digits, 'mobile'|'landline') or None if not a dialable AU number.

    Deliberately strict: the DNC Register charges silently for invalid numbers
    (scoping §2), so anything we cannot positively resolve to an AU mobile or
    fixed line is dropped here rather than paid for later."""
    if not raw:
        return None
    d = re.sub(r"\D", "", str(raw))
    if d.startswith("0011"):
        d = d[4:]
    if d.startswith("61"):
        d = "0" + d[2:]
    if len(d) == 9 and d.startswith("4"):
        d = "0" + d
    if len(d) != 10 or not d.startswith("0"):
        return None
    if d.startswith("04"):
        return d, "mobile"
    if d[1] in "23478":
        return d, "landline"
    return None


def mask_phone(p: str) -> str:
    return ("*" * max(0, len(p) - 3)) + p[-3:] if p else ""


def mask_name(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "(unknown)"
    return parts[0][:1].upper() + "." + (" " + parts[-1][:1].upper() + "." if len(parts) > 1 else "")


def parse_iso(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def years_since(v) -> float | None:
    dt = parse_iso(v)
    if not dt:
        return None
    return round((now_utc() - dt).days / 365.25, 2)


def fmt_money(n) -> str | None:
    """CLAUDE.md: '$1,250,000' — never '$1.25m', never rounded."""
    try:
        return "${:,}".format(int(round(float(n))))
    except (TypeError, ValueError):
        return None


def fmt_date(s) -> str | None:
    dt = parse_iso(s)
    return dt.strftime("%-d %B %Y") if dt else None


# ─────────────────────────────────────────────────────────────────────────────
# editorial guard
# ─────────────────────────────────────────────────────────────────────────────
def editorial_violations(line: str) -> list[str]:
    """Return the reasons `line` breaches the Fields editorial rules. Empty = safe.
    Applied to every hook BEFORE it is stored — the caller reads these aloud."""
    v = []
    low = (line or "").lower()
    for w in FORBIDDEN_WORDS:
        if w in low:
            v.append(f"forbidden word: {w}")
    for pat in ADVICE_PATTERNS:
        if re.search(pat, low):
            v.append(f"advice: /{pat}/")
    for pat in PREDICTION_PATTERNS:
        if re.search(pat, low):
            v.append(f"prediction: /{pat}/")
    if re.search(BAD_MONEY_PATTERN, low):
        v.append("abbreviated money format (use $1,250,000)")
    for key in CORE_SUBURBS:
        label = SUBURB_LABEL[key]
        if label.lower() in low and label not in (line or ""):
            v.append(f"suburb not capitalised: {label}")
    return v


# ─────────────────────────────────────────────────────────────────────────────
# ID4ME consumption (read-only — never a lookup)
# ─────────────────────────────────────────────────────────────────────────────
def _person_phone_rows(person: dict, blob: dict) -> list[dict]:
    """Every dialable (person, phone) pair for ONE ID4ME person record."""
    retrieved_at = blob.get("ID4ME_Retrieved_At")
    gnaf = blob.get("ID4ME_GNAF_PID")
    blocked = {re.sub(r"\D", "", str(b)) for b in (person.get("ID4ME_DNCR_Blocked") or [])}
    has_dncr_detail = bool(person.get("ID4ME_DNCR_Detail"))
    source_date = person.get("ID4ME_Source_Date_Latest") or blob.get("ID4ME_Most_Recent_Source_Date")
    out = []
    for raw in list(person.get("ID4ME_Mobiles") or []) + list(person.get("ID4ME_Landlines") or []):
        norm = normalise_phone(raw)
        if not norm:
            continue
        phone, ptype = norm
        if phone in blocked or re.sub(r"\D", "", str(raw)) in blocked:
            advisory = "blocked"
        elif has_dncr_detail:
            advisory = "clean"
        else:
            advisory = "unknown"
        out.append({
            "phone": phone, "phone_type": ptype,
            "person_name": person.get("ID4ME_Full_Name") or "",
            "first_name": person.get("ID4ME_First_Name") or "",
            "suburb_hint": person.get("ID4ME_Suburb"),
            "postcode": person.get("ID4ME_Postcode"),
            "state": person.get("ID4ME_State") or "QLD",
            "gnaf_pid": person.get("ID4ME_GNAF_PID") or gnaf,
            "id4me_retrieved_at": retrieved_at,
            "id4me_source_date_latest": source_date,
            "record_age_years": years_since(source_date),
            "id4me_advisory": advisory,
        })
    return out


def id4me_people(gc_doc: dict, our_contacts: list | None = None,
                 include_prior: bool = False, max_per_address: int = 2,
                 occ: Counter | None = None) -> list[dict]:
    """Every (person, phone) pair worth dialling at this address, best first.

    Verified against the ONE document in Gold_Coast that currently has this object
    (20 Chantilly Place, Robina — 12 people spanning 1997-2023, 47 raw records).
    Written defensively because n=1: any missing key degrades to None rather than
    raising.

    Three things happen here that did not before, and all three exist because that
    one sample has TWELVE people on it:

    1. Every person is DATED against the property's last recorded sale
       (occupancy_evidence.assess_occupancy). `prior_occupant` — the vendor's most
       recent sighting of them predates a change of ownership — produces NO ROW. This
       is the money filter: we pay per DNC wash credit, and the call itself would put
       a stranger on the phone. `--include-prior` overrides it for analysis.
    2. People are ordered by rank_people(), so the best current-occupant candidate is
       reached first and the cap below bites on the weakest, not the strongest.
    3. `max_per_address` caps how many ROWS one address may contribute. Dialling five
       people at one house is the behaviour that gets us complained about — and the
       cap is on rows, not people, because two numbers for one person is two calls to
       that house just the same.

    ⚠ The `current_likely` verdict is the WEAK direction of an asymmetric inference.
    It means "not excluded", not "confirmed owner", and nothing here treats it as more.
    """
    blob = gc_doc.get("ID4ME_Contact_Data") or {}
    if blob.get("ID4ME_Status") != "ok":
        return []
    occ = occ if occ is not None else Counter()

    seen, uniq = set(), []
    suppressed_seen: set = set()
    capped = 0
    for ranked in rank_people(gc_doc, blob, our_contacts):
        person, a = ranked["person"], ranked["assessment"]
        rows = [p for p in _person_phone_rows(person, blob) if p["phone"] not in seen]
        if not rows:
            # No dialable number we do not already hold: nothing was suppressed by
            # occupancy and no slot is consumed.
            occ[f"no_new_phone_{a['verdict']}"] += 1
            continue
        if a["verdict"] == "prior_occupant" and not include_prior:
            occ["prior_occupant_people"] += 1
            # Count DISTINCT numbers, not raw rows: the count is read as "DNC wash
            # credits not spent", and we would only ever have washed a number once.
            new = {p["phone"] for p in rows} - suppressed_seen
            suppressed_seen |= new
            occ["prior_occupant_rows_suppressed"] += len(new)
            continue
        if max_per_address and len(uniq) >= max_per_address:
            capped += len(rows)
            continue
        occ[a["verdict"]] += 1
        for p in rows:
            if p["phone"] in seen:
                # One person can carry the same number twice (two raw landline
                # records normalising to one). The pre-filter above cannot catch
                # that — it runs before any of THIS person's numbers are seen.
                continue
            if max_per_address and len(uniq) >= max_per_address:
                capped += 1
                continue
            seen.add(p["phone"])
            p["occupancy"] = a
            uniq.append(p)
    occ["rows_capped_by_max_per_address"] += capped
    return uniq


# ─────────────────────────────────────────────────────────────────────────────
# property facts
# ─────────────────────────────────────────────────────────────────────────────
def last_transaction(gc_doc: dict) -> tuple[str | None, float | None]:
    """Most recent sale from enriched_data.transactions (64% fill on Gold_Coast.robina)
    falling back to the top-level `transactions` array. Both confirmed via
    scripts/db_fields.py — no guessed names (CLAUDE.md Rule 8)."""
    txs = ((gc_doc.get("enriched_data") or {}).get("transactions")
           or gc_doc.get("transactions") or [])
    dated = [t for t in txs if isinstance(t, dict) and t.get("date")]
    if not dated:
        return None, None
    latest = max(dated, key=lambda t: str(t["date"]))
    return str(latest["date"])[:10], latest.get("price")


def property_facts(gc_doc: dict) -> dict:
    sale_date, sale_price = last_transaction(gc_doc)
    return {
        "beds": gc_doc.get("bedrooms"),
        "baths": gc_doc.get("bathrooms"),
        "cars": gc_doc.get("car_spaces") if gc_doc.get("car_spaces") is not None
                else gc_doc.get("carspaces"),
        "land_sqm": gc_doc.get("land_size_sqm") or gc_doc.get("land_area"),
        "last_sale_date": sale_date,
        "last_sale_price": sale_price,
        "years_held": years_since(sale_date),
    }


# ─────────────────────────────────────────────────────────────────────────────
# hook engine
# ─────────────────────────────────────────────────────────────────────────────
class HookContext:
    """Suburb-level facts computed ONCE per run, so every hook's grounds can name
    the exact query, collection and moment they were measured at — POA s212(4)-(5)
    puts the onus of proving reasonable grounds on US, at the time the
    representation is made."""

    def __init__(self, gc_db):
        self.gc_db = gc_db
        self.measured_at = now_aest_str()
        self.suburb_stats = {}
        self._street_cache = {}

    def stats(self, suburb: str) -> dict:
        if suburb not in self.suburb_stats:
            coll = self.gc_db[suburb]
            self.suburb_stats[suburb] = {
                "for_sale": coll.count_documents({"listing_status": "for_sale"}),
                "sold": coll.count_documents({"listing_status": "sold"}),
            }
        return self.suburb_stats[suburb]

    def street_sales(self, suburb: str, street_name: str, since: str) -> list[dict]:
        """Recorded sales on the same street since `since` (YYYY-MM-DD), newest first."""
        if not street_name:
            return []
        key = (suburb, street_name, since)
        if key in self._street_cache:
            return self._street_cache[key]
        sales = []
        cur = self.gc_db[suburb].find(
            {"STREET_NAME": street_name},
            {"address": 1, "enriched_data.transactions": 1, "transactions": 1})
        for d in cur:
            date, price = last_transaction(d)
            if date and price and date >= since:
                sales.append({"address": d.get("address", ""), "date": date, "price": price})
        sales.sort(key=lambda s: s["date"], reverse=True)
        self._street_cache[key] = sales
        return sales


def build_hook(ctx: HookContext, track: str, address: str, suburb: str,
               gc_doc: dict | None, facts: dict, lead_signals: list[str]) -> dict:
    """ONE short factual sentence the caller can open with.

    Rules it must survive (checked, not assumed, by editorial_violations):
      no advice, no prediction, no single valuation figure, no forbidden words,
      exact prices never rounded, suburbs capitalised, $1,250,000 not $1.25m.

    Note what is deliberately absent: any estimate of what the home is worth. A
    verbal price answer to a seller triggers POA s215's mandatory comparative
    market analysis (scoping §5) — the hook must never invite the caller into it.
    """
    label = SUBURB_LABEL.get(suburb) or "the Gold Coast"
    candidates = []

    # 1. Same-street sales in the last 24 months, with the exact most recent price.
    if gc_doc and gc_doc.get("STREET_NAME"):
        since = (now_utc().replace(year=now_utc().year - 2)).strftime("%Y-%m-%d")
        sales = ctx.street_sales(suburb, gc_doc["STREET_NAME"], since)
        sales = [s for s in sales if s["address"] != address]
        if sales:
            top = sales[0]
            street = " ".join(w.capitalize() for w in
                              f"{gc_doc.get('STREET_NAME','')} {gc_doc.get('STREET_TYPE','')}".split())
            money, when = fmt_money(top["price"]), fmt_date(top["date"])
            candidates.append({
                "line": (f"Our records show {len(sales)} recorded sale"
                         f"{'s' if len(sales) != 1 else ''} on {street}, {label} in the past "
                         f"two years — the most recent at {money} on {when}."),
                "evidence": {"street": street, "sales_since": since,
                             "n_sales": len(sales),
                             "most_recent": {"address": top["address"], "date": top["date"],
                                             "price": top["price"]}},
                "grounds": (f"Counted from Gold_Coast.{suburb} documents matching "
                            f"STREET_NAME='{gc_doc['STREET_NAME']}' with a transaction dated on or "
                            f"after {since}, measured {ctx.measured_at}. Prices are the recorded "
                            f"transaction figures, unrounded. Coverage caveat: our sold capture is "
                            f"incomplete (Domain misses an estimated 40-50% of sales), so this is a "
                            f"floor on street activity, not a complete count."),
            })

    # 2. The subject property's own last recorded sale (a transaction, not a valuation).
    if facts.get("last_sale_date") and facts.get("last_sale_price"):
        money, when = fmt_money(facts["last_sale_price"]), fmt_date(facts["last_sale_date"])
        held = facts.get("years_held")
        candidates.append({
            "line": (f"Our records show {address} last changed hands on {when} for {money}"
                     + (f", {int(held)} years ago." if held and held >= 1 else ".")),
            "evidence": {"last_sale_date": facts["last_sale_date"],
                         "last_sale_price": facts["last_sale_price"],
                         "years_held": held},
            "grounds": (f"enriched_data.transactions on the Gold_Coast.{suburb} document for this "
                        f"address, read {ctx.measured_at}. This is a recorded transaction price, "
                        f"not an estimate of current value — no valuation figure is stated."),
        })

    # 3. Suburb-level activity — always available, never property-specific.
    st = ctx.stats(suburb) if suburb in CORE_SUBURBS else {"for_sale": 0, "sold": 0}
    if st["for_sale"]:
        candidates.append({
            "line": (f"We track every home listed in {label} — there are {st['for_sale']} on the "
                     f"market right now, and {st['sold']} sales recorded in our database."),
            "evidence": {"for_sale_now": st["for_sale"], "sold_recorded": st["sold"],
                         "collection": f"Gold_Coast.{suburb}"},
            "grounds": (f"count_documents on Gold_Coast.{suburb} with listing_status 'for_sale' and "
                        f"'sold', measured {ctx.measured_at}. Both are counts of documents we hold, "
                        f"stated as such — not a claim about the whole market."),
        })

    # 4. Last resort — states only what WE did, which is always true, and is the
    #    only line available for a warm lead who never gave us an address.
    # `address` can be a whitespace-only string on leads that carry a phone but no
    # address (Facebook Lead Ads). A bare truthiness test lets that through and
    # renders "…and  is one of the addresses we cover." — a broken line the caller
    # would read aloud. Test the stripped value.
    if address and address.strip():
        line4 = f"We publish property data for {label}, and {address.strip()} is one of the addresses we cover."
        grounds4 = (f"The address resolves to a document we hold in Gold_Coast.{suburb}"
                    if gc_doc else "The address was supplied to us by the lead themselves")
    else:
        line4 = (f"You asked us for home data on {label} through one of our Facebook forms, "
                 f"and left this number for us to follow up on.")
        grounds4 = (f"The lead record carries the signals {lead_signals!r}, and the phone number "
                    f"was typed into our own form by the person themselves — no appended data "
                    f"is involved. No address was supplied, so no property claim is made")
    candidates.append({
        "line": line4,
        "evidence": {"track": track, "lead_signals": lead_signals, "address_known": bool(address)},
        "grounds": grounds4 + f", checked {ctx.measured_at}.",
    })

    for c in candidates:
        viol = editorial_violations(c["line"])
        if not viol:
            c["editorial_checked_at"] = ctx.measured_at
            return c
        c["rejected"] = viol
    # Every candidate failed the editorial guard — never emit an unchecked line.
    return {"line": "", "evidence": {"error": "all hook candidates failed the editorial guard"},
            "grounds": "", "editorial_checked_at": ctx.measured_at,
            "rejected": [v for c in candidates for v in c.get("rejected", [])]}


# ─────────────────────────────────────────────────────────────────────────────
# scoring
# ─────────────────────────────────────────────────────────────────────────────
# Freshness dominates because it is the only factor we have MEASURED against
# outcome risk: of a 36-address ID4ME sample only 38.9% were "has mobile AND
# record <=2y old", median record age 3.12 years, and it splits hard by suburb
# (Robina 66.7% fresh, Burleigh Waters 41.7%, Varsity Lakes 8.3%). A stale record
# is a previous occupant — the wrong-number rate, not a preference. record_age_years
# is stored on every row so that assumption can be tested against real outcomes later.
SUBURB_FRESHNESS_WEIGHT = {"robina": 0.10, "burleigh_waters": 0.05, "varsity_lakes": 0.0}
TRACK_BASE = {"A_warm": 0.45, "B_intent": 0.30, "C_openmarket": 0.10}


# ── the occupancy-evidence term ──────────────────────────────────────────────
# Whether the person still LIVES there is a better predictor of a useful
# conversation than tenure, phone type or suburb, so it is weighted above all of
# them. It is deliberately NOT weighted above record_freshness (max 0.30):
#
#   1. The two are partly the same measurement. Both are driven by
#      ID4ME_Source_Date_Latest; letting occupancy dominate would double-count one
#      date and let a 2011 record ride a `current_likely` verdict to the top of the
#      list purely because the house last sold in 2009.
#   2. `current_likely` is the WEAK direction of an asymmetric inference (see the
#      occupancy_evidence docstring). A signal that cannot confirm should not be the
#      largest term in the score. The STRONG direction — `prior_occupant` — is not
#      expressed as a penalty at all; it removes the row entirely, upstream.
#
# So: current_likely 0.10-0.25 (scaled by its own confidence, so a 0.5 does not buy
# what a 0.9 buys), unknown 0.03, and the -0.25 for prior_occupant is only ever
# reachable under --include-prior, where it must not out-rank a real candidate.
OCCUPANCY_WEIGHT_BASE = 0.10
OCCUPANCY_WEIGHT_CONF = 0.15
OCCUPANCY_WEIGHT_UNKNOWN = 0.03
OCCUPANCY_WEIGHT_PRIOR = -0.25


def occupancy_score(assessment: dict | None) -> float:
    if not assessment:
        return 0.0                                  # Track A: never assessed
    verdict = assessment.get("verdict")
    conf = assessment.get("confidence") or 0.0
    if verdict == "current_likely":
        return round(OCCUPANCY_WEIGHT_BASE + OCCUPANCY_WEIGHT_CONF * conf, 4)
    if verdict == "prior_occupant":
        return OCCUPANCY_WEIGHT_PRIOR
    return OCCUPANCY_WEIGHT_UNKNOWN


# ── the SELLER-INTENT term ───────────────────────────────────────────────────
# Everything above answers "can we reach this person?". Nothing above answered
# "is there any reason to ring them?" — even though we already compute that, every
# night, in scripts/samantha/seller_intent.py and store it on
# system_monitor.lead_worklist.seller_intent. This block consumes it. It does not
# recompute it, and it never writes back to lead_worklist.
#
# ⚠ THE SCORE IS AN UNBOUNDED RANKING SCORE, NOT A PROBABILITY. It always was
# (reachability alone already reaches 1.45). It is stated here rather than left
# implicit, and every term below has a NAMED, ENUMERABLE maximum so the ceiling can
# be recomputed by reading this file:
#
#     reachability   -0.20 .. +1.45   (track 0.45, phone 0.12, record freshness 0.30,
#                                      suburb 0.10, tenure 0.15, owner-occupier 0.08,
#                                      occupancy evidence 0.25, DNC advisory -0.20)
#     intent         -0.35 .. +0.85   (capped at INTENT_CAP; see below)
#     TOTAL          -0.55 .. +2.30
#
# WHY THESE WEIGHTS
# -----------------
# * `moment` is the single largest intent term (0.35 — bigger than any other intent
#   component on its own) because a fresh strong signal is the best call we will ever
#   make: somebody who valued their own home this week has already asked the question
#   we are ringing to answer. It is also PERISHABLE. Full weight for <=3 days
#   (seller_intent only ever sets `moment` on a <=3-day-old signal in the first
#   place), then LINEAR DECAY TO ZERO at 14 days. Decay is measured from
#   `seller_intent.behavioral.last_seen` — the event itself — not from `computed_at`,
#   which is just the last time the nightly job ran and would keep a July moment
#   looking fresh forever.
# * `behavioral_score` and `hotness` are continuous and unbounded (measured max 170
#   and 186, p95 13 and 22), so they are SATURATED, not bucketed: a smooth ramp to
#   full weight at 20 / 25 respectively. They overlap by construction — hotness IS
#   behavioral_score + listing_bonus — so hotness carries the smaller weight (0.08)
#   and exists mainly to let listing_bonus register; behavioral_score (0.22) is the
#   honest "what this person actually did" term.
# * Labels carry what the numbers cannot. `engaged_owner_researching` and
#   `pre_market_withdrawn` are the two strongest positives (+0.15) — an owner testing
#   the water on their own home, and one who pulled a listing to wait.
# * ⚠ `on_market_fresh` is a STRONG NEGATIVE (-0.35, the largest single weight in
#   either direction). It does not mean "hot", it means COMMITTED TO A COMPETITOR:
#   seller_intent scores it hotness -6 for exactly this reason, and READS says
#   "not a lead yet". Without this, a fresh competitor listing with a busy PostHog
#   journey would rank as high intent. It is a penalty rather than an exclusion
#   because the exclusion that matters legally (s21(3), listings whose appointment
#   is in force and nearing expiry) is upstream and untouched.
# * `on_market_expiring` is deliberately weighted ZERO, not positive. Those leads are
#   excluded upstream under s21(3) and whether they should be is Will's decision, not
#   this file's; a positive weight here would pre-empt it.
#
# WHY INTENT CANNOT SWAMP REACHABILITY
# ------------------------------------
# The positive intent total is multiplied by REACH_FACTOR, derived from the ID4ME
# record age: 1.0 at a same-day record, falling linearly to 0.40 at 5 years and
# staying there. A six-year-old phone number for the hottest lead in the database
# keeps only 40% of its intent bonus, because it is still probably a wrong number —
# and the wrong-number rate is the one thing here we have actually measured (38.9%
# of a 36-address sample was "mobile AND record <=2y"; median age 3.12 years).
# The NEGATIVE half is NOT scaled: a competitor commitment is a fact about the
# vendor, not about our phone record, and must not be softened by a stale record.
INTENT_MOMENT_MAX = 0.35
INTENT_BEHAVIOURAL_MAX = 0.22
INTENT_HOTNESS_MAX = 0.08
INTENT_PRIORITY_MAX = 0.05
INTENT_CAP = 0.85           # 0.35 + 0.22 + 0.08 + 0.15 + 0.05 — the enumerated ceiling
INTENT_FLOOR = -0.35

MOMENT_FULL_DAYS = 3.0      # seller_intent only sets `moment` inside this window
MOMENT_DEAD_DAYS = 14.0     # ...and we let it decay to nothing here
BSCORE_SATURATION = 20.0
HOTNESS_SATURATION = 25.0

# `moment` is a fixed vocabulary written by seller_intent.analyze(). Matched on the
# exact strings it emits — a miss scores 0.0 rather than guessing, so a new moment
# type shows up as "no boost" rather than as a silent wrong weight.
MOMENT_STRENGTH = {
    "Just generated a home valuation": 1.00,
    "Just visited a 'sell now' page": 0.90,
    "Actively exploring their report (incl. Messages)": 0.70,
    "Just engaged seller-focused content": 0.50,
    "Just opted into the weekly buyer email": 0.35,
}
# ⚠ Not a moment we act on. seller_intent sets it when a tracked lead's home flips to
# on-market — i.e. they just signed with somebody else. Scored 0, never a note.
MOMENT_JUST_LISTED_PREFIX = "Just listed with another agent"

INTENT_LABEL_WEIGHT = {
    "engaged_owner_researching": 0.15,   # owner quietly valuing their own home
    "pre_market_withdrawn": 0.15,        # pulled the listing to wait
    "browsing_while_unlisted": 0.10,
    "on_market_stale": 0.06,             # past the first agency term, still unsold
    "viewing_listings_home_unknown": 0.03,
    "on_market_active": 0.0,
    "on_market_expiring": 0.0,           # ⚠ excluded upstream under s21(3) — not ours to rank
    "no_cross_signal": 0.0,
    "on_market_fresh": -0.35,            # ⚠ COMMITTED TO A COMPETITOR, never a positive
}


def moment_decay(age_days: float | None) -> float:
    """1.0 while the signal is <=3 days old, linear to 0.0 at 14 days, 0 after.

    None means we could not date the signal at all — score it as dead rather than as
    fresh. An undated moment is exactly the stale one this decay exists to kill."""
    if age_days is None:
        return 0.0
    if age_days <= MOMENT_FULL_DAYS:
        return 1.0
    if age_days >= MOMENT_DEAD_DAYS:
        return 0.0
    return round((MOMENT_DEAD_DAYS - age_days) / (MOMENT_DEAD_DAYS - MOMENT_FULL_DAYS), 4)


def reach_factor(record_age_years: float | None) -> float:
    """How much of a positive intent bonus a record this old is allowed to keep.

    1.0 (same-day) -> 0.40 (>=5 years). Unknown age sits at 0.70: it covers BOTH a
    Track A lead who typed their own number minutes ago (should be ~1.0) and an ID4ME
    record with no source date (should be low), and we cannot tell them apart from
    this argument alone — so it takes the middle rather than either optimistic or
    pessimistic extreme."""
    if record_age_years is None:
        return 0.70
    return round(0.40 + 0.60 * max(0.0, min(1.0, 1.0 - record_age_years / 5.0)), 4)


def intent_score(intent: dict | None) -> tuple[float, dict]:
    """-> (raw intent total BEFORE reach scaling, per-term breakdown).

    `intent` is the joined `seller_intent` payload built by IntentIndex — never a
    guessed shape. Every key read here was confirmed against the live collection with
    `scripts/db_fields.py system_monitor lead_worklist --grep seller_intent`
    (CLAUDE.md Rule 8), all at 400/400 fill:
      seller_intent.hotness / .behavioral_score / .label / .moment / .computed_at
      seller_intent.behavioral.last_seen   (str, 342/490 non-null on non-test docs)
    `priority` is the TOP-LEVEL lead_worklist field written by lead_intelligence.py
    (low 385 / medium 50 / high 2 / absent 52 on non-test docs) — not part of
    seller_intent, and read as such."""
    if not intent:
        return 0.0, {}
    parts = {}
    moment = intent.get("moment") or ""
    strength = 0.0 if moment.startswith(MOMENT_JUST_LISTED_PREFIX) \
        else MOMENT_STRENGTH.get(moment, 0.0)
    parts["intent_moment"] = round(
        INTENT_MOMENT_MAX * strength * moment_decay(intent.get("signal_age_days")), 4)
    b = intent.get("behavioral_score") or 0
    parts["intent_behavioural"] = round(
        INTENT_BEHAVIOURAL_MAX * min(1.0, max(0.0, b) / BSCORE_SATURATION), 4)
    h = intent.get("hotness") or 0
    parts["intent_hotness"] = round(
        INTENT_HOTNESS_MAX * min(1.0, max(0.0, h) / HOTNESS_SATURATION), 4)
    parts["intent_label"] = INTENT_LABEL_WEIGHT.get(intent.get("label"), 0.0)
    pri = intent.get("priority")
    parts["intent_priority"] = (INTENT_PRIORITY_MAX if pri == "high"
                                else round(INTENT_PRIORITY_MAX / 2, 4) if pri == "medium"
                                else 0.0)
    total = max(INTENT_FLOOR, min(INTENT_CAP, round(sum(parts.values()), 4)))
    return total, parts


def score_candidate(track: str, suburb: str, phone_type: str, record_age_years: float | None,
                    years_held: float | None, occupancy_type: str | None,
                    advisory: str, occupancy_assessment: dict | None = None,
                    intent: dict | None = None) -> tuple[float, dict]:
    parts = {"track_base": TRACK_BASE.get(track, 0.0)}
    parts["phone_type"] = 0.12 if phone_type == "mobile" else 0.0
    if record_age_years is None:
        parts["record_freshness"] = 0.05          # unknown age: not free, not fatal
    else:
        parts["record_freshness"] = round(0.30 * max(0.0, 1.0 - record_age_years / 5.0), 4)
    parts["suburb_freshness"] = SUBURB_FRESHNESS_WEIGHT.get(suburb, 0.0)
    if years_held is None:
        parts["tenure"] = 0.0
    else:
        parts["tenure"] = round(0.15 * min(1.0, years_held / 15.0), 4)
    parts["occupancy"] = 0.08 if occupancy_type == "owner_occupier" else 0.0
    # Is this PERSON still at the address (occupancy_evidence), as distinct from
    # `occupancy` above, which is whether the PROPERTY is owner-occupied or tenanted.
    parts["occupancy_evidence"] = occupancy_score(occupancy_assessment)
    # ID4ME's DNC flag buys us no legal defence (ACMA IS 157) but it is still the
    # best available signal that a wash will reject the number — deprioritise, do
    # not drop, because dnc_wash.py is the only thing entitled to decide.
    parts["dnc_advisory"] = -0.20 if advisory == "blocked" else 0.0
    # Seller intent, scaled by how reachable this record actually is. Positive only:
    # a competitor commitment (on_market_fresh) is a fact about the vendor and must
    # not be softened by a stale phone record.
    raw_intent, intent_parts = intent_score(intent)
    reach = reach_factor(record_age_years)
    parts["intent"] = round(raw_intent * reach, 4) if raw_intent > 0 else raw_intent
    parts["intent_detail"] = {**intent_parts, "raw_total": raw_intent,
                              "reach_factor": reach,
                              "reach_applied": raw_intent > 0}
    return round(sum(v for k, v in parts.items() if k != "intent_detail"), 4), parts


# ─────────────────────────────────────────────────────────────────────────────
# candidate assembly
# ─────────────────────────────────────────────────────────────────────────────
class Excluded:
    """Named, counted exclusions — never a silent omission."""

    def __init__(self):
        self.counts = Counter()
        # ⛔ NOT a scheduling hook. The s21(3) exclusion below is UNCHANGED. This
        # counter only makes the SIZE of the open legal question visible: how many of
        # the leads we drop under s21(3) are the `on_market_expiring` cohort — the
        # group seller_intent scores highest and whose appointment is precisely the
        # thing s21(3) turns on. Whether they should be scheduled rather than excluded
        # is Will's decision; this file does not take it.
        self.s21_labels = Counter()
        self.reasons = {
            "s21_listing_expiry": "POA Regulation 2014 s21(3) — another agent's appointment IS IN FORCE",
            "currently_listed": "listing_status for_sale/under_contract (memory ayh_currently_listed_guard)",
            "tenanted_investor": "occupancy_classifier: rental listed after last sale — not an owner-occupier",
            "outside_core_suburbs": "address is not in Robina / Varsity Lakes / Burleigh Waters",
            "test_or_internal": "is_test / internal / known diagnostic address",
            "no_address": "no usable address on the lead",
            "unresolved_address": "address did not resolve to a Gold_Coast property document",
            "no_dialable_phone": "no AU-format mobile or landline could be normalised",
            "no_id4me_data": "no ID4ME_Contact_Data on the property document (human-paced append pending)",
            "prior_occupant_dated_before_sale":
                "occupancy_evidence: ID4ME last saw this person at the address BEFORE it "
                "last sold — a previous occupant. Counted in dialable numbers suppressed, "
                "because each one is a DNC wash credit we would have paid for and a "
                "stranger we would have phoned (--include-prior to keep them)",
        }

    def hit(self, key, n=1):
        self.counts[key] += n

    def report(self) -> list[str]:
        return [f"  {self.counts[k]:>6}  {k:<22} — {self.reasons[k]}"
                for k in self.reasons if self.counts[k]]


def resolve_gc_doc(gc_db, address: str, suburb: str | None):
    """Address -> Gold_Coast document. url_slug first (the convention every other
    script uses), then a whitespace-tolerant exact-ish address match."""
    slug = address_slug(address)
    subs = [suburb] if suburb else CORE_SUBURBS
    for s in subs:
        if not s:
            continue
        d = gc_db[s].find_one({"url_slug": slug})
        if d:
            return d, s
    # fall back to a regex on the street-number + street portion
    head = re.split(r",", address or "")[0].strip()
    if head:
        pat = re.compile(r"^\s*" + re.escape(head).replace(r"\ ", r"\s+") + r"\s*,", re.I)
        for s in subs:
            if not s:
                continue
            d = gc_db[s].find_one({"address": pat})
            if d:
                return d, s
    return None, suburb


def occupancy_for_doc(gc_doc: dict) -> dict:
    """FREE stored-timeline path only — never a paid Bright Data pull. Same call
    live_leads_to_sheet.py makes for exactly this filter."""
    from scripts.property_reports import occupancy_classifier as occ
    if not gc_doc:
        return occ.classify_from_timeline([])
    return occ.classify_from_timeline(occ.normalise_stored_timeline(gc_doc))


class ContactHistory:
    """When did anyone at THIS address engage with US? Keyed by address_slug.

    This is the `our_contacts` argument to assess_occupancy. It matters because
    ID4ME's own contact-recency fields are all empty (verified 2026-08-15 — see the
    occupancy_evidence docstring), so "date of last contact" can only come from our
    own records. Ours is better evidence anyway: we know exactly what it means.

    ⚠ It is an ADDRESS-level signal, not a person-level one. Somebody at this address
    used our site; it does not identify WHICH of the twelve names ID4ME lists. It can
    raise the floor on a verdict; it can never confirm an individual, and
    assess_occupancy is written that way.

    ⚠ CLAUDE.md Rule 8 — every path below was confirmed with
    `python3 scripts/db_fields.py system_monitor <collection>` before it was queried,
    with its fill count:
      lead_worklist.address            400/400 (100%)   .last_seen 370/400 (92%)
      lead_worklist.first_seen         400/400 (100%)   .seller_intent.behavioral.last_seen 100%
      analyse_leads.address             11/11  (100%)   .submitted_at_date 11/11 (100%)
      property_reports.address         105/106 (99%)    .slug 106/106  .created_at 75/106 (71%)
      property_reports.messages[].sender / .created_at  74/106 (70%)  (values: agent|seller)
      offmarket_report_requests.slug   400/400 (100%)   .requested_at 100%  .source 100%

    ⚠ NOT WIRED — `system_monitor.call_outcomes` and `system_monitor.call_activity`
    are BOTH EMPTY (0 documents; call_outcomes is not even a created collection yet —
    no call has been made). A prior call outcome would be the strongest possible
    signal here, and it is deliberately left out rather than coded against guessed
    field names. Wire it after the first round of calls, when the documents exist and
    their shape can be read instead of assumed.
    """

    # `prewarm` (7,303 docs) and `test` are OUR OWN precompute, not a human opening a
    # page — counting them as contact would mark every off-market address "engaged".
    _OFFMARKET_MACHINE_SOURCES = {"prewarm", "test", None, ""}

    def __init__(self, sm_db):
        self.by_slug: dict[str, list[dict]] = {}
        self.sources_loaded = Counter()
        self.call_outcomes_available = False   # see the class docstring
        self._load(sm_db)

    def _add(self, address_or_slug: str, date, kind: str, detail: str = ""):
        if not date:
            return
        slug = address_slug(address_or_slug) if " " in (address_or_slug or "") \
            else (address_or_slug or "").strip().lower()
        if not slug:
            return
        self.by_slug.setdefault(slug, []).append(
            {"date": date, "kind": kind, "detail": detail})
        self.sources_loaded[kind] += 1

    def _load(self, sm_db):
        # 1. lead_worklist — the address was searched / the off-market page opened.
        for d in sm_db.lead_worklist.find(
                {}, {"address": 1, "last_seen": 1, "first_seen": 1, "is_test": 1,
                     "sources": 1, "seller_intent.behavioral.last_seen": 1}):
            if d.get("is_test") or not d.get("address"):
                continue
            det = ",".join(sorted(d.get("sources") or []))[:120]
            self._add(d["address"], d.get("last_seen"), "lead_worklist_last_seen", det)
            self._add(d["address"], d.get("first_seen"), "lead_worklist_first_seen", det)
            beh = ((d.get("seller_intent") or {}).get("behavioral") or {}).get("last_seen")
            self._add(d["address"], beh, "behavioral_last_seen", det)

        # 2. analyse_leads — they typed the address into /analyse-your-home themselves.
        for d in sm_db.analyse_leads.find({}, {"address": 1, "submitted_at_date": 1,
                                               "submitted_at": 1, "source": 1}):
            if not d.get("address") or d["address"].strip().lower() in ("test", ""):
                continue
            self._add(d["address"], d.get("submitted_at_date") or d.get("submitted_at"),
                      "analyse_your_home_form", str(d.get("source") or ""))

        # 3. property_reports — a report was requested for this address, and any
        #    message the SELLER (not us) sent back through it.
        for d in sm_db.property_reports.find({}, {"address": 1, "slug": 1, "created_at": 1,
                                                  "is_test": 1, "source": 1,
                                                  "messages.sender": 1,
                                                  "messages.created_at": 1}):
            if d.get("is_test") or d.get("source") == "diagnostic_test":
                continue
            key = d.get("address") or d.get("slug") or ""
            if not key or d.get("slug") in TEST_SLUGS:
                continue
            self._add(key, d.get("created_at"), "property_report_requested",
                      str(d.get("source") or ""))
            for m in d.get("messages") or []:
                if m.get("sender") == "seller":
                    self._add(key, m.get("created_at"), "seller_message")

        # 4. offmarket_report_requests — only visitor-triggered builds.
        for d in sm_db.offmarket_report_requests.find(
                {"source": {"$nin": list(self._OFFMARKET_MACHINE_SOURCES)}},
                {"slug": 1, "requested_at": 1, "source": 1}):
            self._add(d.get("slug") or "", d.get("requested_at"),
                      "offmarket_report_request", str(d.get("source") or ""))

    def for_address(self, address: str) -> list[dict]:
        """[] means "we have no record of this household engaging with us" — which is
        the normal case for Track C, not a failure."""
        return self.by_slug.get(address_slug(address), [])

    def report(self) -> list[str]:
        out = [f"  {n:>6}  {k}" for k, n in self.sources_loaded.most_common()]
        out.append("       0  prior_call_outcome — system_monitor.call_outcomes is EMPTY "
                   "(no call has been made yet); deliberately not queried rather than "
                   "coded against guessed field names")
        return out


class IntentIndex:
    """The EXISTING seller-intent layer, joined onto call candidates.

    scripts/samantha/seller_intent.py already answers "is there a reason to ring this
    person?" every night and stores it on `system_monitor.lead_worklist.seller_intent`.
    Until now this script ignored all of it and ranked purely on reachability. This
    class is the join, and nothing more — it READS lead_worklist and never writes it.

    Join keys, in the order they are tried (the strongest identifier first):
      1. lead_key   — exact. Track B candidates carry `source_ref`
                      "lead_worklist:<lead_key>", so this is an identity join.
      2. address    — address_slug of `lead_worklist.address`. The measured path:
                      100% of the 202 ID4ME-append candidates join this way.
      3. email      — lower-cased. Only Track A (Facebook Lead Ads / AYH) has one.

    ⚠ CLAUDE.md Rule 8 — every path below was confirmed against the live collection
    with `python3 scripts/db_fields.py system_monitor lead_worklist --grep seller_intent`
    before it was read, with its fill count (490 non-test docs):
      lead_worklist.address                        386/490   lead_worklist.lead_key 100%
      lead_worklist.priority                       438/490 (low 385/med 50/high 2)
      seller_intent.hotness                        400/400 (100%)  int
      seller_intent.behavioral_score               400/400 (100%)  int
      seller_intent.label                          400/400 (100%)  str
      seller_intent.moment                         400/400 (100%)  null/str  (2 non-null)
      seller_intent.story                          451/490 non-empty
      seller_intent.behavioral.last_seen           342/490 non-null, str
      seller_intent.own_property.days_on_market    120/400
      seller_intent.propradar.dom                   11/400
    Nothing is queried by a name that was not on that list.
    """

    def __init__(self, sm_db):
        self.by_lead_key: dict[str, dict] = {}
        self.by_slug: dict[str, dict] = {}
        self.by_email: dict[str, dict] = {}
        self.n_docs = 0
        self.label_counts = Counter()
        self.lookups = Counter()          # joined_from -> n, plus "miss"
        self._addr_joined = 0
        self._addr_tried = 0
        for d in sm_db.lead_worklist.find(
                {}, {"lead_key": 1, "address": 1, "email": 1, "is_test": 1, "priority": 1,
                     "sources": 1, "seller_intent": 1}):
            if d.get("is_test"):
                continue
            self.n_docs += 1
            payload = self._payload(d)
            self.label_counts[payload.get("label")] += 1
            if d.get("lead_key"):
                self.by_lead_key.setdefault(str(d["lead_key"]), payload)
            slug = address_slug(d.get("address") or "")
            if slug:
                # Several worklist rows can share an address (a report request and a
                # behavioural surface). Keep the hottest — never silently the last one.
                cur = self.by_slug.get(slug)
                if cur is None or (payload.get("hotness") or 0) > (cur.get("hotness") or 0):
                    self.by_slug[slug] = payload
            em = (d.get("email") or "").strip().lower()
            if em:
                self.by_email.setdefault(em, payload)

    @staticmethod
    def _signal_age_days(si: dict) -> float | None:
        """Age of the BEHAVIOURAL SIGNAL, not of the last enrichment run.

        `computed_at` is when seller_intent.py last executed — it advances nightly
        whether or not anything happened, so decaying against it would keep a
        five-week-old "just generated a valuation" permanently fresh. The event time
        is `behavioral.last_seen`. Fall back to computed_at only when there is no
        behavioural record at all, in which case the moment cannot have come from
        behaviour either."""
        last_seen = ((si.get("behavioral") or {}).get("last_seen"))
        dt = parse_iso(last_seen) or parse_iso(si.get("computed_at"))
        if not dt:
            return None
        return round((now_utc() - dt).total_seconds() / 86400.0, 2)

    def _payload(self, d: dict) -> dict:
        si = d.get("seller_intent") or {}
        return {
            "hotness": si.get("hotness"),
            "behavioral_score": si.get("behavioral_score"),
            "label": si.get("label"),
            "moment": si.get("moment"),
            "priority": d.get("priority"),
            # The full story paragraph is stored (it is the audit trail for the
            # one-line note) but NEVER rendered into a sheet cell — it is written for
            # a different reader and runs to several hundred characters.
            "story": si.get("story") or "",
            "signal_age_days": self._signal_age_days(si),
            "listing_bonus": si.get("listing_bonus"),
            "days_on_market": ((si.get("own_property") or {}).get("days_on_market")
                               or (si.get("propradar") or {}).get("dom")),
            "n_current_listings_viewed": si.get("n_current_listings_viewed"),
            "lead_key": d.get("lead_key"),
            "sources": sorted(d.get("sources") or []),
            "computed_at": si.get("computed_at"),
        }

    def lookup(self, source_ref: str | None = None, address: str | None = None,
               email: str | None = None) -> dict | None:
        if source_ref and str(source_ref).startswith("lead_worklist:"):
            hit = self.by_lead_key.get(str(source_ref).split(":", 1)[1])
            if hit:
                self.lookups["lead_key"] += 1
                return {**hit, "joined_from": "lead_key"}
        slug = address_slug(address or "")
        if slug and slug in self.by_slug:
            self.lookups["address"] += 1
            return {**self.by_slug[slug], "joined_from": "address"}
        em = (email or "").strip().lower()
        if em and em in self.by_email:
            self.lookups["email"] += 1
            return {**self.by_email[em], "joined_from": "email"}
        self.lookups["miss"] += 1
        return None

    def address_join_rate(self) -> tuple[int, int]:
        """(joined, tried) for the ADDRESS path only — the one the 100%-join
        measurement was taken on, and the one that silently breaks if address_slug or
        the worklist's address format ever drifts. lead_key joins are tautological
        (the candidate came FROM lead_worklist) and prove nothing about the index."""
        return self._addr_joined, self._addr_tried

    def probe_address(self, address: str) -> bool:
        """Does this address resolve through the ADDRESS index? Counted for the Rule 7b
        join-rate assertion. Separate from lookup() so the assertion measures the
        address path even when lead_key already answered."""
        if not (address or "").strip():
            return False
        self._addr_tried += 1
        ok = address_slug(address) in self.by_slug
        if ok:
            self._addr_joined += 1
        return ok


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def intent_note(intent: dict | None) -> str:
    """ONE short factual line for the sheet's caller-facing intent column.

    Deliberately NOT the `story` paragraph: story is written for a CRM reader, runs
    to several hundred characters, and contains PropRadar valuation figures and
    explicit "Approach:" coaching. Both are wrong in a call sheet — the figures
    because POA s215/s216 make a spoken price a CMA trigger, the coaching because
    CLAUDE.md's editorial rules forbid telling the reader what to do.

    So this composes a new line from the same facts: what happened, and when. No
    advice, no prediction, no valuation figure, no forbidden words. The result is
    passed through `editorial_violations` and dropped if it fails — the caller reads
    this aloud-adjacent, and an unchecked line must never reach them.

    Returned as "" when there is nothing factual to say. "" is a real answer here
    (most leads carry no cross-signal); it is never a stand-in for a failed lookup.
    """
    if not intent:
        return ""
    label = intent.get("label")
    moment = intent.get("moment") or ""
    age = intent.get("signal_age_days")
    line = ""

    # 1. A live moment — the strongest and most perishable thing we know. Only while
    #    it is still inside the decay window; a dead moment is not "why now".
    if moment and not moment.startswith(MOMENT_JUST_LISTED_PREFIX) \
            and MOMENT_STRENGTH.get(moment) and moment_decay(age):
        when = ("today" if age is not None and age < 1
                else f"{int(age)} day{'' if int(age) == 1 else 's'} ago" if age is not None
                else "recently")
        phrase = {
            "Just generated a home valuation": "Generated a valuation for their own home",
            "Just visited a 'sell now' page": "Visited a selling page on our site",
            "Actively exploring their report (incl. Messages)":
                "Opened their own property report, including its Messages tab",
            "Just engaged seller-focused content": "Read seller-focused content on our site",
            "Just opted into the weekly buyer email": "Signed up to our weekly buyer email",
        }.get(moment)
        if phrase:
            line = f"{phrase} {when}."

    # 2. Otherwise, the situation label — facts about the property, not a read on it.
    if not line:
        dom = intent.get("days_on_market")
        nviewed = intent.get("n_current_listings_viewed") or 0
        if label == "engaged_owner_researching":
            line = "Generated a valuation for their own home; it is not currently listed."
        elif label == "pre_market_withdrawn":
            line = "Their listing was withdrawn from the market."
        elif label == "browsing_while_unlisted" and nviewed:
            line = (f"Own home not listed; viewed {_plural(nviewed, 'live listing')} "
                    f"on our site.")
        elif label == "on_market_stale" and dom:
            line = (f"Listed with another agency for {_plural(int(dom), 'day')} — past the "
                    f"first 90-day appointment term.")
        elif label == "on_market_expiring" and dom:
            # Excluded upstream under s21(3); the note exists only so a row that
            # reaches a sheet by some other route still states the fact plainly.
            line = f"Listed with another agency for {_plural(int(dom), 'day')}."
        elif label == "on_market_fresh" and dom:
            line = (f"Recently listed with another agency ({_plural(int(dom), 'day')}) — "
                    f"an appointment is in force.")
        elif label == "viewing_listings_home_unknown" and nviewed:
            line = (f"Viewed {_plural(nviewed, 'live listing')} on our site; we have not "
                    f"tied a home to them.")

    # 3. Last resort — plain site activity, stated as activity.
    if not line:
        b = intent.get("behavioral_score") or 0
        if b > 0 and age is not None and age <= 45:
            line = f"Last active on our site {int(age)} day{'' if int(age) == 1 else 's'} ago."

    if not line:
        return ""
    if editorial_violations(line):
        return ""
    return line[:160]


def collect_track_a(sm_db, ex: Excluded) -> list[dict]:
    """Leads who typed their OWN number. No ID4ME involved, no append needed.

    ⚠ Consent is not permanent: ACMA treats express consent as lasting 3 months
    (scoping §1), so consent_age_days is recorded and consent_stale flagged on
    every row. It is not used to drop the row — dnc_wash.py and the caller decide."""
    out = []
    for d in sm_db.fb_leads.find({}):
        if d.get("is_test"):
            ex.hit("test_or_internal")
            continue
        f = d.get("fields") or {}
        if (f.get("email") or "").lower() in TEST_EMAILS:
            ex.hit("test_or_internal")
            continue
        norm = normalise_phone(f.get("phone_number"))
        if not norm:
            ex.hit("no_dialable_phone")
            continue
        phone, ptype = norm
        # ⚠ `area` is a form CHOICE (values seen: 'robina', 'burleigh_waters',
        # 'open_to_all_three', 'elsewhere_on_the_gold_coast') — it is the suburb they
        # said they were interested in, NOT their address. Never promote it to an
        # address: a hook built on a fabricated address is exactly the kind of
        # unfounded representation POA s212(4)-(5) reverses the onus on.
        addr = f.get("property_address") or ""
        suburb = suburb_from_address(addr) or suburb_from_address(f.get("area") or f.get("suburb") or "")
        given = parse_iso(d.get("created_time"))
        out.append({
            "track": "A_warm", "address": addr, "suburb": suburb,
            "phone": phone, "phone_type": ptype,
            "person_name": f.get("full_name") or "", "first_name": (f.get("full_name") or "").split(" ")[0],
            "id4me_retrieved_at": None, "id4me_source_date_latest": None, "record_age_years": None,
            "id4me_advisory": "unknown", "gnaf_pid": None, "postcode": None, "state": "QLD",
            # Carried ONLY as a join key for IntentIndex (lead_worklist.email). Never
            # written to the queue row and never printed.
            "email": (f.get("email") or "").strip().lower(),
            "lead_signals": [f"fb_lead:{d.get('form_name') or d.get('campaign_name') or ''}"]
                            + ([f"area_of_interest:{f['area']}"] if f.get("area") else []),
            "consent": {"basis": "self-supplied on a Facebook Lead Ad form",
                        "given_at": given.isoformat() if given else None,
                        "age_days": (now_utc() - given).days if given else None,
                        "stale_over_3_months": bool(given and (now_utc() - given).days > 92)},
            "source_ref": f"fb_leads:{d['_id']}",
        })
    for d in sm_db.property_reports.find({"owner.phone": {"$nin": [None, ""]}}):
        owner = d.get("owner") or {}
        if owner.get("is_internal") or (owner.get("email") or "").lower() in TEST_EMAILS:
            ex.hit("test_or_internal")
            continue
        if d.get("slug") in TEST_SLUGS or d.get("source") == "diagnostic_test":
            ex.hit("test_or_internal")
            continue
        norm = normalise_phone(owner.get("phone"))
        if not norm:
            ex.hit("no_dialable_phone")
            continue
        phone, ptype = norm
        addr = d.get("address") or (d.get("slug") or "").replace("-", " ").title()
        given = parse_iso(d.get("created_at"))
        out.append({
            "track": "A_warm", "address": addr, "suburb": suburb_from_address(addr),
            "phone": phone, "phone_type": ptype,
            "person_name": owner.get("name") or "", "first_name": (owner.get("name") or "").split(" ")[0],
            "id4me_retrieved_at": None, "id4me_source_date_latest": None, "record_age_years": None,
            "id4me_advisory": "unknown", "gnaf_pid": None, "postcode": None, "state": "QLD",
            "email": (owner.get("email") or "").strip().lower(),
            "lead_signals": ["analyse_your_home"],
            "consent": {"basis": "self-supplied on the Analyse Your Home form",
                        "given_at": given.isoformat() if given else None,
                        "age_days": (now_utc() - given).days if given else None,
                        "stale_over_3_months": bool(given and (now_utc() - given).days > 92)},
            "source_ref": f"property_reports:{d['_id']}",
        })
    return out


def collect_track_b_leads(sm_db, ex: Excluded) -> list[dict]:
    """lead_worklist entries that gave us an ADDRESS in a core suburb. Cold — the
    address is not phone consent. Phone must come from ID4ME on the property doc."""
    leads = []
    for d in sm_db.lead_worklist.find({}):
        if d.get("is_test"):
            ex.hit("test_or_internal")
            continue
        sources = set(d.get("sources") or [])
        if sources & S21_EXCLUDED_SOURCES:
            ex.hit("s21_listing_expiry")
            # Count, do not change. See Excluded.s21_labels.
            ex.s21_labels[(d.get("seller_intent") or {}).get("label") or "(no seller_intent)"] += 1
            continue
        addr = d.get("address") or ""
        if not addr:
            ex.hit("no_address")
            continue
        suburb = suburb_from_address(addr)
        if not suburb:
            ex.hit("outside_core_suburbs")
            continue
        leads.append({
            "address": addr, "suburb": suburb,
            "lead_signals": sorted(sources),
            "years_held_hint": d.get("years_held"),
            "occupancy_hint": (d.get("occupancy") or {}).get("type"),
            "source_ref": f"lead_worklist:{d.get('lead_key')}",
        })
    # one row per address (a lead can appear under several sources)
    by_addr = {}
    for l in leads:
        key = address_slug(l["address"])
        if key in by_addr:
            by_addr[key]["lead_signals"] = sorted(set(by_addr[key]["lead_signals"]) | set(l["lead_signals"]))
        else:
            by_addr[key] = l
    return list(by_addr.values())


def collect_track_c_addresses(gc_db, suburbs, known_slugs: set, limit: int) -> list[dict]:
    """Open-market owners: core-suburb properties with ID4ME data already on the
    document and no intent signal. In practice this is empty until the human-paced
    append run has happened — which is exactly what --needs-id4me is for."""
    out = []
    for s in suburbs:
        for d in gc_db[s].find({"ID4ME_Contact_Data": {"$exists": True}}):
            if d.get("url_slug") in known_slugs:
                continue
            out.append({"address": d.get("address") or d.get("complete_address") or "",
                        "suburb": s, "lead_signals": [], "years_held_hint": None,
                        "occupancy_hint": None, "source_ref": f"Gold_Coast.{s}:{d['_id']}",
                        "_doc": d})
            if limit and len(out) >= limit:
                return out
    return out


def property_rows(gc_db, ctx, track, addresses, ex: Excluded, stats: Counter,
                  contacts: "ContactHistory | None" = None,
                  include_prior: bool = False, max_per_address: int = 2,
                  occ_counts: Counter | None = None,
                  intents: "IntentIndex | None" = None) -> list[dict]:
    """Turn address-level candidates (B or C) into (address, phone) rows.

    Every exclusion is counted so --stats can say honestly how many candidates are
    blocked on the ID4ME append versus genuinely unusable — and, since the occupancy
    module landed, how many people were dated to BEFORE the property last sold and
    therefore never became a row at all."""
    occ_counts = occ_counts if occ_counts is not None else Counter()
    rows = []
    for cand in addresses:
        gc_doc = cand.get("_doc")
        suburb = cand["suburb"]
        if gc_doc is None:
            gc_doc, suburb = resolve_gc_doc(gc_db, cand["address"], cand["suburb"])
        if not gc_doc:
            ex.hit("unresolved_address")
            continue
        if gc_doc.get("listing_status") in LISTED_STATUSES:
            ex.hit("currently_listed")
            continue
        occ_res = occupancy_for_doc(gc_doc)
        if occ_res.get("type") == "investor":
            ex.hit("tenanted_investor")
            continue
        stats["candidates_considered"] += 1
        # The EXISTING seller-intent layer, joined on. Attached to the candidate here
        # (not only to the finished rows) so that --needs-id4me — which never gets as
        # far as a row — ranks on exactly the same signal.
        addr_for_join = gc_doc.get("address") or cand["address"]
        if intents is not None:
            if str(cand.get("source_ref") or "").startswith("lead_worklist:"):
                # Only lead_worklist-sourced candidates are expected to have an
                # address in the index; probing Track C would measure the wrong thing.
                intents.probe_address(addr_for_join)
            cand["_intent"] = intents.lookup(source_ref=cand.get("source_ref"),
                                             address=addr_for_join)
            if cand["_intent"]:
                stats["intent_joined"] += 1
            else:
                stats["intent_missed"] += 1
        # Our own engagement history for this address — an ADDRESS-level signal that
        # can raise the floor on a verdict, never confirm an individual.
        our_contacts = contacts.for_address(gc_doc.get("address") or cand["address"]) \
            if contacts else []
        if our_contacts:
            stats["addresses_with_our_contact"] += 1
        has_id4me = bool((gc_doc.get("ID4ME_Contact_Data") or {}).get("ID4ME_People"))
        if has_id4me:
            # Counted so "everything was excluded as a prior occupant" can never be
            # confused with "we found nothing" (Rule 7b, applied to a read).
            stats["people_assessed"] += len(gc_doc["ID4ME_Contact_Data"]["ID4ME_People"])
            stats["sale_known" if last_sale(gc_doc)[0] else "no_sale_recorded"] += 1
        before = occ_counts["prior_occupant_rows_suppressed"]
        people = id4me_people(gc_doc, our_contacts=our_contacts,
                              include_prior=include_prior,
                              max_per_address=max_per_address, occ=occ_counts)
        suppressed = occ_counts["prior_occupant_rows_suppressed"] - before
        if suppressed:
            ex.hit("prior_occupant_dated_before_sale", suppressed)
        if not people:
            if has_id4me and suppressed:
                # NOT "no ID4ME data" — we had data, dated it, and every dialable
                # person predates the last sale. A real, reportable outcome.
                stats["all_people_prior_occupants"] += 1
                continue
            ex.hit("no_id4me_data")
            stats["blocked_on_id4me"] += 1
            cand["_needs_id4me"] = True
            cand["_facts"] = property_facts(gc_doc)
            cand["_occupancy"] = occ_res.get("type")
            cand["_gc_doc"] = gc_doc
            continue
        stats["with_id4me"] += 1
        facts = property_facts(gc_doc)
        hook = build_hook(ctx, track, gc_doc.get("address") or cand["address"], suburb,
                          gc_doc, facts, cand.get("lead_signals") or [])
        for p in people:
            rows.append({
                "track": track,
                "address": gc_doc.get("address") or cand["address"],
                "suburb": suburb,
                "postcode": p.get("postcode") or gc_doc.get("POSTCODE") or SUBURB_POSTCODE.get(suburb),
                "state": p.get("state") or "QLD",
                "lead_signals": cand.get("lead_signals") or [],
                "facts": facts, "hook": hook,
                # ⚠ `hook` is the property-specific opener and is NOT touched. The
                # intent reason is a SEPARATE, shorter field so the sheet can show
                # both — see intent_note().
                "intent": cand.get("_intent"),
                "intent_note": intent_note(cand.get("_intent")),
                "occupancy_type": occ_res.get("type"),
                # Full assessment, stored so the sheet can label the row and so a
                # verdict can be argued with later. call_list_to_sheet.build_row reads
                # occupancy.verdict / occupancy.confidence — that contract exactly.
                "occupancy": p.get("occupancy"),
                "source_ref": cand["source_ref"],
                **{k: p[k] for k in ("phone", "phone_type", "person_name", "first_name",
                                     "gnaf_pid", "id4me_retrieved_at",
                                     "id4me_source_date_latest", "record_age_years",
                                     "id4me_advisory")},
            })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# queue writing
# ─────────────────────────────────────────────────────────────────────────────
def queue_id(track: str, address: str, phone: str) -> str:
    return f"{track}:{address_slug(address) or 'no-address'}:{phone}"


def upsert_rows(coll, rows: list[dict], dry_run: bool) -> dict:
    """$set for mutable fields, $setOnInsert for created_at AND status.

    status lives in $setOnInsert precisely so a re-run can NEVER downgrade a row
    from "called"/"do_not_contact" back to "queued" — the guard is structural, not
    a conditional someone can forget. dnc.status is likewise only ever seeded
    "unwashed" here; dnc_wash.py owns every later transition."""
    res = {"inserted": 0, "updated": 0, "skipped_terminal": 0, "skipped_suppressed_phone": 0}

    # ⛔ Suppression is a property of the PERSON, not of this (track, address, phone) key.
    # `_id` embeds the track and the address, so the terminal-status guard below — which only
    # ever looks up that exact `_id` — misses two real cases:
    #   1. TRACK CHANGE. Someone suppressed as "B_intent:12-smith-st:0412..." reappears as
    #      "C_openmarket:12-smith-st:0412..." — same human, same number, different key, so
    #      `existing` is None and they are re-queued. Track B -> C is the planned expansion
    #      path (00_SCOPING.md §1), not a hypothetical.
    #   2. NEW ADDRESS. read_call_outcomes.py sweeps a suppressed number across other
    #      addresses, but only over docs that are "queued"/"listed" AT THAT MOMENT. A later
    #      ID4ME append that finds the same number at a second property (investor, previous
    #      occupant) creates a doc that sweep never saw.
    # Either one re-queues a person who asked not to be called, which makes the caller's
    # "I'll get it taken off" false. That is the fact pattern most likely to satisfy the
    # "reckless" element of the statutory tort (Privacy Act Sch 2), where cl 6(3) means the
    # small-business exemption is no shield.
    # So: suppression is looked up BY PHONE, across every track and address, before insert.
    suppressed_phones = set()
    if not dry_run:
        suppressed_phones = {
            d["phone"] for d in coll.find(
                {"status": "do_not_contact", "phone": {"$ne": None}}, {"phone": 1})
            if d.get("phone")
        }

    for r in rows:
        if r.get("phone") and r["phone"] in suppressed_phones:
            res["skipped_suppressed_phone"] += 1
            continue
        _id = queue_id(r["track"], r["address"], r["phone"])
        existing = coll.find_one({"_id": _id}, {"status": 1}) if not dry_run else None
        if existing and existing.get("status") in TERMINAL_STATUSES:
            res["skipped_terminal"] += 1
            continue
        mutable = {
            "track": r["track"], "address": r["address"], "suburb": r["suburb"],
            "postcode": r.get("postcode"), "state": r.get("state") or "QLD",
            "gnaf_pid": r.get("gnaf_pid"),
            "person_name": r.get("person_name"), "first_name": r.get("first_name"),
            "phone": r["phone"], "phone_type": r["phone_type"],
            "id4me_retrieved_at": r.get("id4me_retrieved_at"),
            "id4me_source_date_latest": r.get("id4me_source_date_latest"),
            "record_age_years": r.get("record_age_years"),
            "dnc.id4me_advisory": r.get("id4me_advisory") or "unknown",
            "score": r["score"], "score_parts": r.get("score_parts"),
            "hook": r["hook"], "property": r["facts"],
            # The joined seller-intent payload and its one-line caller note. Written
            # unconditionally (including None / "") because a moment that has decayed
            # or a lead whose label changed MUST clear, not linger from a prior run.
            "intent": r.get("intent"),
            "intent_note": r.get("intent_note") or "",
            "occupancy_type": r.get("occupancy_type"),
            "lead_signals": r.get("lead_signals") or [],
            # `occupancy` (the person-level occupancy_evidence assessment) is written
            # only when we HAVE one. A Track A row was never assessed, and writing
            # None would render as "not assessed" — true — but would also overwrite a
            # real assessment on a re-run that happened to lose its ID4ME data.
            "source_ref": r.get("source_ref"),
            "updated_at": now_utc(),
        }
        if r.get("occupancy"):
            mutable["occupancy"] = r["occupancy"]
        if r.get("consent"):
            mutable["consent"] = r["consent"]
        if dry_run:
            res["inserted" if not existing else "updated"] += 1
            continue
        coll.update_one({"_id": _id}, {
            "$set": mutable,
            # dnc.status is seeded once and never touched again by this script.
            # Dotted path (not a whole `dnc` sub-document) because $set already
            # addresses dnc.id4me_advisory — a nested-object $setOnInsert collides
            # with it ("Updating the path 'dnc' would create a conflict at 'dnc'").
            "$setOnInsert": {"created_at": now_utc(), "status": "queued",
                             "dnc.status": "unwashed"},
        }, upsert=True)
        res["updated" if existing else "inserted"] += 1
    return res


# ─────────────────────────────────────────────────────────────────────────────
# commands
# ─────────────────────────────────────────────────────────────────────────────
def do_build(gc_db, sm_db, args, beat) -> dict:
    ctx = HookContext(gc_db)
    ex = Excluded()
    stats = Counter()
    occ_counts = Counter()
    contacts = ContactHistory(sm_db)
    intents = IntentIndex(sm_db)
    max_per_address = args.max_per_address if args.max_per_address is not None else 2
    tracks = {"A": "A_warm", "B": "B_intent", "C": "C_openmarket"}
    wanted = [tracks[args.track]] if args.track else list(tracks.values())
    suburbs = [args.suburb] if args.suburb else CORE_SUBURBS

    rows: list[dict] = []
    needs_id4me: list[dict] = []

    if "A_warm" in wanted:
        a_rows = collect_track_a(sm_db, ex)
        if args.suburb:
            a_rows = [r for r in a_rows if r["suburb"] in (None, args.suburb)]
        for r in a_rows:
            stats["candidates_considered"] += 1
            # No default suburb. A warm lead who never gave us an address genuinely
            # has none, and the hook must say so rather than invent one.
            gc_doc, resolved = (resolve_gc_doc(gc_db, r["address"], r["suburb"])
                                if r["address"] else (None, r["suburb"]))
            if gc_doc and gc_doc.get("listing_status") in LISTED_STATUSES:
                ex.hit("currently_listed")
                continue
            occ_type = occupancy_for_doc(gc_doc).get("type") if gc_doc else None
            if occ_type == "investor":
                ex.hit("tenanted_investor")
                continue
            facts = property_facts(gc_doc) if gc_doc else {
                "beds": None, "baths": None, "cars": None, "land_sqm": None,
                "last_sale_date": None, "last_sale_price": None, "years_held": None}
            r["suburb"] = resolved or r["suburb"]
            r["facts"] = facts
            r["occupancy_type"] = occ_type
            r["hook"] = build_hook(ctx, "A_warm", r["address"], r["suburb"],
                                   gc_doc, facts, r["lead_signals"])
            # Track A joins on address where they gave one, else on the email they
            # typed into the form. Most warm leads gave neither an address nor a
            # worklist row, so a miss here is normal, not a broken join.
            r["intent"] = intents.lookup(source_ref=r.get("source_ref"),
                                         address=r.get("address"),
                                         email=r.get("email"))
            r["intent_note"] = intent_note(r["intent"])
            rows.append(r)
        stats["track_a_rows"] = len(rows)

    b_addresses = []
    if "B_intent" in wanted or args.needs_id4me:
        b_addresses = collect_track_b_leads(sm_db, ex)
        if args.suburb:
            b_addresses = [a for a in b_addresses if a["suburb"] == args.suburb]
    if "B_intent" in wanted:
        b_rows = property_rows(gc_db, ctx, "B_intent", b_addresses, ex, stats,
                               contacts, args.include_prior, max_per_address, occ_counts,
                               intents)
        stats["track_b_rows"] = len(b_rows)
        rows += b_rows
        needs_id4me += [a for a in b_addresses if a.get("_needs_id4me")]

    if "C_openmarket" in wanted:
        known = {address_slug(a["address"]) for a in b_addresses}
        c_addresses = collect_track_c_addresses(gc_db, suburbs, known, args.limit or 0)
        c_rows = property_rows(gc_db, ctx, "C_openmarket", c_addresses, ex, stats,
                               contacts, args.include_prior, max_per_address, occ_counts,
                               intents)
        stats["track_c_rows"] = len(c_rows)
        rows += c_rows

    for r in rows:
        r["score"], r["score_parts"] = score_candidate(
            r["track"], r["suburb"], r["phone_type"], r.get("record_age_years"),
            (r.get("facts") or {}).get("years_held"), r.get("occupancy_type"),
            r.get("id4me_advisory") or "unknown", r.get("occupancy"), r.get("intent"))
    rows.sort(key=lambda r: r["score"], reverse=True)
    if args.limit:
        rows = rows[: args.limit]

    coll = sm_db[QUEUE_COLL]
    write = upsert_rows(coll, rows, args.dry_run)

    # ── Rule 7b: the outcome assertion ───────────────────────────────────────
    # A clean exit is not an outcome. Two distinct zero-paths, only one of which
    # is success:
    #   * "no new candidates / everything is blocked on the human-paced ID4ME
    #     append" -> SUCCESS. The append is a documented manual gate, not a bug.
    #   * "we held ID4ME data for N properties and extracted zero phone rows" ->
    #     FAILURE. That is our parsing, not an empty upstream.
    #   * "we held ID4ME data and every person on it dated to before the last sale"
    #     -> SUCCESS, and a DIFFERENT fact from either of the above. It must be
    #     distinguishable, or the filter that saves the money looks like the bug.
    considered = stats["candidates_considered"]
    with_id4me = stats["with_id4me"]
    prior_suppressed = ex.counts["prior_occupant_dated_before_sale"]
    if stats["people_assessed"] > 0 and sum(
            v for k, v in occ_counts.items()
            if k in ("current_likely", "unknown", "prior_occupant", "prior_occupant_people")
            or k.startswith("no_new_phone_")) == 0:
        raise RuntimeError(
            f"{stats['people_assessed']} ID4ME people were read but occupancy_evidence "
            f"returned a verdict for none of them — the assessment is broken, not empty.")
    if with_id4me > 0 and stats["track_b_rows"] + stats["track_c_rows"] == 0 \
            and prior_suppressed == 0:
        raise RuntimeError(
            f"{with_id4me} propert{'ies' if with_id4me != 1 else 'y'} carried ID4ME_Contact_Data "
            f"but produced 0 queue rows, and none were suppressed as prior occupants — "
            f"phone extraction is broken, not empty upstream.")
    if considered > 0 and not rows and stats["blocked_on_id4me"] == 0:
        raise RuntimeError(
            f"{considered} candidates were considered and 0 queue rows produced, with none blocked "
            f"on the ID4ME append — the selection pipeline gave us nothing.")

    # ── Rule 7b, applied to the intent JOIN ──────────────────────────────────
    # The join was MEASURED at 100% (all 202 ID4ME-append candidates resolve to a
    # lead_worklist row by address). A collapse below 50% is therefore a BROKEN JOIN
    # — address_slug drifting, the worklist changing its address format, or the
    # collection being read empty — never "these leads have no intent". Scoring
    # silently at zero would demote every hot lead back to reachability-only order
    # and look exactly like a normal run.
    addr_joined, addr_tried = intents.address_join_rate()
    if intents.n_docs == 0:
        raise RuntimeError(
            "IntentIndex read 0 non-test lead_worklist documents — the seller-intent "
            "layer is unreadable, not empty. Refusing to rank on reachability alone.")
    if addr_tried >= 20 and (addr_joined / addr_tried) < 0.50:
        raise RuntimeError(
            f"seller-intent address join collapsed: {addr_joined}/{addr_tried} "
            f"({addr_joined / addr_tried:.0%}) of lead_worklist-sourced candidates resolved "
            f"through the address index, against a measured baseline of 100%. That is a "
            f"broken join, not absent intent data (CLAUDE.md Rule 8 / 7b).")

    beat.metrics = {
        "candidates_considered": considered,
        "queue_rows": len(rows),
        "inserted": write["inserted"], "updated": write["updated"],
        "skipped_terminal": write["skipped_terminal"],
        "skipped_suppressed_phone": write["skipped_suppressed_phone"],
        "track_a": stats["track_a_rows"], "track_b": stats["track_b_rows"],
        "track_c": stats["track_c_rows"],
        "with_id4me": with_id4me, "blocked_on_id4me": stats["blocked_on_id4me"],
        "excluded_s21": ex.counts["s21_listing_expiry"],
        # ⛔ Counter only — the s21(3) exclusion itself is unchanged.
        "excluded_s21_on_market_expiring": ex.s21_labels["on_market_expiring"],
        "excluded_s21_by_label": dict(ex.s21_labels),
        # seller-intent join
        "intent_worklist_docs": intents.n_docs,
        "intent_joined": stats["intent_joined"],
        "intent_missed": stats["intent_missed"],
        "intent_address_join_rate": round(addr_joined / addr_tried, 4) if addr_tried else None,
        "intent_rows_with_moment": sum(
            1 for r in rows if (r.get("intent") or {}).get("moment")),
        "intent_rows_with_note": sum(1 for r in rows if r.get("intent_note")),
        "excluded_currently_listed": ex.counts["currently_listed"],
        "excluded_investor": ex.counts["tenanted_investor"],
        # occupancy_evidence — people, not rows, except where named otherwise
        "people_assessed": stats["people_assessed"],
        "occ_current_likely": occ_counts["current_likely"],
        "occ_unknown": occ_counts["unknown"],
        "occ_prior_occupant_people": occ_counts["prior_occupant_people"],
        "occ_prior_rows_suppressed": prior_suppressed,
        "occ_addresses_all_prior": stats["all_people_prior_occupants"],
        "rows_capped_by_max_per_address": occ_counts["rows_capped_by_max_per_address"],
        "addresses_with_our_contact": stats["addresses_with_our_contact"],
        "include_prior": bool(args.include_prior),
        "max_per_address": max_per_address,
        "dry_run": bool(args.dry_run),
    }
    beat.detail = (f"{len(rows)} row(s) queued ({write['inserted']} new); "
                   f"{stats['blocked_on_id4me']} candidates blocked on ID4ME append; "
                   f"{prior_suppressed} number(s) suppressed as prior occupants")

    print(f"\nBuild — {now_aest_str()}{'  [DRY RUN]' if args.dry_run else ''}")
    print(f"  candidates considered : {considered}")
    print(f"  queue rows produced   : {len(rows)}   [pre-limit by track: "
          f"A {stats['track_a_rows']} / B {stats['track_b_rows']} / C {stats['track_c_rows']}]")
    print(f"  written               : {write['inserted']} inserted, {write['updated']} updated, "
          f"{write['skipped_terminal']} left alone (terminal status)")
    if write["skipped_suppressed_phone"]:
        print(f"  ⛔ suppressed persons  : {write['skipped_suppressed_phone']} row(s) NOT queued — "
              f"the number is do_not_contact at another address or on another track")
    print(f"  blocked on ID4ME      : {stats['blocked_on_id4me']}  "
          f"(run --needs-id4me for the human-paced append list)")
    print(f"\nOccupancy evidence (occupancy_evidence.py — dated against the last SALE)"
          f"{'  [--include-prior: prior occupants KEPT]' if args.include_prior else ''}")
    print(f"  people assessed       : {stats['people_assessed']}   "
          f"(on {stats['sale_known']} propert{'y' if stats['sale_known'] == 1 else 'ies'} "
          f"with a recorded sale, {stats['no_sale_recorded']} without — no sale means no "
          f"verdict is possible, only 'unknown')")
    print(f"  current_likely        : {occ_counts['current_likely']}  "
          f"⚠ 'not excluded', NEVER 'confirmed owner' — the weak direction of the inference")
    print(f"  unknown               : {occ_counts['unknown']}")
    print(f"  prior_occupant        : "
          f"{occ_counts['prior_occupant_people'] + occ_counts['prior_occupant']} people → "
          f"{prior_suppressed} dialable number(s) "
          f"{'KEPT (--include-prior)' if args.include_prior else 'SUPPRESSED'} — "
          f"{prior_suppressed} DNC wash credit(s) not spent")
    print(f"  addresses fully prior : {stats['all_people_prior_occupants']}  "
          f"(had ID4ME data; every dialable person predates the last sale — NOT the same "
          f"as 'no data')")
    print(f"  rows capped           : {occ_counts['rows_capped_by_max_per_address']} "
          f"(--max-per-address {max_per_address})")
    print(f"  our own contact known : {stats['addresses_with_our_contact']} address(es)")
    print("  our_contacts sources loaded:")
    for line in contacts.report():
        print(line)
    # ── Seller intent (system_monitor.lead_worklist.seller_intent) ──────────
    print(f"\nSeller intent (joined from lead_worklist — READ ONLY, never written)")
    print(f"  worklist docs indexed : {intents.n_docs} non-test")
    print(f"  candidates joined     : {stats['intent_joined']} joined / "
          f"{stats['intent_missed']} missed "
          f"[by key: {dict(intents.lookups)}]")
    print(f"  address-path join rate: "
          + (f"{addr_joined}/{addr_tried} ({addr_joined / addr_tried:.0%}) "
             f"— baseline 100%; <50% raises" if addr_tried else "n/a (no probes)"))
    lbl = Counter((r.get("intent") or {}).get("label") for r in rows)
    for k, n in lbl.most_common():
        flag = "  ⚠ committed to a competitor — scored NEGATIVE" if k == "on_market_fresh" else ""
        print(f"    {n:>6}  {k or '(no intent joined)'}{flag}")
    live_moments = [r for r in rows if (r.get("score_parts") or {}).get("intent_detail", {})
                    .get("intent_moment")]
    print(f"  rows with a LIVE moment: {len(live_moments)} "
          f"(decays to nothing at {int(MOMENT_DEAD_DAYS)} days from the signal, not from "
          f"the last enrichment run)")
    print(f"  rows with an intent_note: {sum(1 for r in rows if r.get('intent_note'))} "
          f"(separate field — the property hook is never overwritten)")

    print("\nExclusions (named, never silent):")
    for line in ex.report():
        print(line)
    if ex.s21_labels:
        # ⛔ Visibility only. The exclusion is unchanged and no scheduling is built.
        print(f"    of the {ex.counts['s21_listing_expiry']} excluded under s21(3), by "
              f"seller-intent label — OPEN QUESTION for Will, not a change:")
        for k, n in ex.s21_labels.most_common():
            mark = "  ← appointment IS IN FORCE and nearing expiry" if k == "on_market_expiring" else ""
            print(f"      {n:>6}  {k}{mark}")

    if rows:
        print("\nTop rows (masked):")
        for r in rows[:10]:
            sp = r.get("score_parts") or {}
            det = sp.get("intent_detail") or {}
            it = r.get("intent") or {}
            print(f"  {r['score']:.3f}  {r['track']:<12} {r['suburb'] or '-':<16} "
                  f"{mask_name(r.get('person_name'))!s:<10} {mask_phone(r['phone'])} "
                  f"({r['phone_type']}, age {r.get('record_age_years')}, "
                  f"occ {(r.get('occupancy') or {}).get('verdict', 'not assessed')})")
            print(f"          intent {sp.get('intent', 0.0):+.3f}  "
                  f"[raw {det.get('raw_total', 0.0):+.3f} "
                  f"{'×' if det.get('reach_applied') else '(reach not applied — negative/zero:'} "
                  f"reach {det.get('reach_factor', 1.0):.2f}"
                  f"{']' if det.get('reach_applied') else ')]'} "
                  f"label={it.get('label') or '-'} hot={it.get('hotness')} "
                  f"beh={it.get('behavioral_score')} moment={it.get('moment') or '-'} "
                  f"age={it.get('signal_age_days')}d via={it.get('joined_from') or '-'}")
            if r.get("intent_note"):
                print(f"          why now: {r['intent_note']}")
            print(f"          hook: {r['hook']['line'][:150]}")
    return {"rows": rows, "needs_id4me": needs_id4me, "excluded": ex, "stats": stats}


def do_stats(sm_db):
    coll = sm_db[QUEUE_COLL]
    total = coll.count_documents({})
    print(f"\ncall_queue composition — {now_aest_str()}")
    print(f"  total rows: {total}")
    if not total:
        print("  (queue is empty — run --build)")
        return
    for field, label in (("track", "By track"), ("status", "By status"),
                         ("suburb", "By suburb"), ("phone_type", "By phone type"),
                         ("dnc.status", "By DNC wash status"),
                         ("dnc.id4me_advisory", "By ID4ME DNC advisory (NOT a legal defence)")):
        agg = list(coll.aggregate([{"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
                                   {"$sort": {"n": -1}}]))
        print(f"\n  {label}:")
        for a in agg:
            print(f"    {a['n']:>6}  {a['_id']}")
    blocked = coll.count_documents({"dnc.status": {"$ne": "washed"}})
    print(f"\n  BLOCKED ON DNC WASH : {blocked} of {total} rows are unwashed and MUST NOT be "
          f"dialled (DNCR Act 2006 s11(3)(a); ACMA IS 157 — an externally supplied flag is no defence)")
    advisory_blocked = coll.count_documents({"dnc.id4me_advisory": "blocked"})
    print(f"  ID4ME advisory 'blocked': {advisory_blocked} (deprioritised, not dropped — "
          f"dnc_wash.py decides)")
    ages = [d["record_age_years"] for d in coll.find({"record_age_years": {"$ne": None}},
                                                     {"record_age_years": 1})]
    if ages:
        ages.sort()
        print(f"  ID4ME record age: median {ages[len(ages)//2]:.2f}y over {len(ages)} rows "
              f"(sample baseline was 3.12y median, 38.9% fresh)")
    # Blocked on the ID4ME append. Read from the last build's heartbeat rather than
    # recomputed — the count requires resolving every lead address to a property doc
    # and --stats must stay cheap. If it is missing, say so; never print a fake zero.
    hb = sm_db["job_runs"].find_one({"job": "build_call_list"})
    m = (hb or {}).get("metrics") or {}
    if hb and "blocked_on_id4me" in m:
        print(f"\n  BLOCKED ON ID4ME APPEND: {m['blocked_on_id4me']} candidate addresses had no "
              f"ID4ME_Contact_Data at the last build ({hb.get('run_at')}), out of "
              f"{m.get('candidates_considered')} considered — run --needs-id4me for the "
              f"ranked, human-paced append list. This script never calls ID4ME.")
    else:
        print("\n  BLOCKED ON ID4ME APPEND: unknown — build_call_list has no heartbeat yet "
              "(run --build). Not reported as zero.")

    # ── Occupancy split (occupancy_evidence.py) ─────────────────────────────────
    # Two halves that must never be conflated: what IS in the queue, read from the
    # queue; and what was KEPT OUT as a prior occupant, which by definition has no
    # row and can only come from the last build's heartbeat.
    print("\n  Occupancy (is this person still at the address?):")
    agg = list(coll.aggregate([{"$group": {"_id": "$occupancy.verdict", "n": {"$sum": 1}}},
                               {"$sort": {"n": -1}}]))
    label = {"current_likely": "current_likely  (⚠ 'not excluded', not 'confirmed owner')",
             "unknown": "unknown", "prior_occupant": "prior_occupant  (⚠ kept via --include-prior)",
             None: "not assessed  (Track A / pre-occupancy rows — no ID4ME person to date)"}
    for a in agg:
        print(f"    {a['n']:>6}  {label.get(a['_id'], a['_id'])}")
    if hb and "occ_prior_rows_suppressed" in m:
        print(f"    {m['occ_prior_rows_suppressed']:>6}  prior_occupant EXCLUDED at the last "
              f"build ({hb.get('run_at')}) — {m['occ_prior_rows_suppressed']} dialable number(s) "
              f"across {m.get('occ_prior_occupant_people')} people never became rows, from "
              f"{m.get('people_assessed')} people assessed. {m.get('occ_addresses_all_prior')} "
              f"address(es) lost EVERY person that way — which is a result, not an empty run.")
        print(f"    {m.get('rows_capped_by_max_per_address', 0):>6}  rows dropped by "
              f"--max-per-address {m.get('max_per_address')} (one household, one call)")
    else:
        print("         ?  prior_occupant exclusions: unknown — no build heartbeat carries "
              "them yet (run --build). Not reported as zero.")

    # ── Seller intent in the queue ───────────────────────────────────────────
    # Read from the queue itself, not recomputed — these are the values the ranking
    # actually used. A row with `intent: null` means the join found nothing for that
    # candidate; it is reported as "no intent joined", never folded into a bucket.
    print("\n  Seller intent (joined from lead_worklist.seller_intent at build time):")
    agg = list(coll.aggregate([{"$group": {"_id": "$intent.label", "n": {"$sum": 1}}},
                               {"$sort": {"n": -1}}]))
    for a in agg:
        k = a["_id"]
        flag = ("   ⚠ COMMITTED TO A COMPETITOR — scored negative, never a positive"
                if k == "on_market_fresh" else "")
        print(f"    {a['n']:>6}  {k or '(no intent joined)'}{flag}")
    buckets = [("hotness >= 7", {"intent.hotness": {"$gte": 7}}),
               ("hotness 4-6", {"intent.hotness": {"$gte": 4, "$lte": 6}}),
               ("hotness 1-3", {"intent.hotness": {"$gte": 1, "$lte": 3}}),
               ("hotness <= 0", {"intent.hotness": {"$lte": 0}}),
               ("behavioral_score > 0", {"intent.behavioral_score": {"$gt": 0}}),
               ("has a `moment`", {"intent.moment": {"$nin": [None, ""]}}),
               ("has an intent_note", {"intent_note": {"$nin": [None, ""]}})]
    print("\n    Intent strength:")
    for label, q in buckets:
        print(f"      {coll.count_documents(q):>6}  {label}")
    agg = list(coll.aggregate([{"$group": {"_id": "$intent.joined_from", "n": {"$sum": 1}}},
                               {"$sort": {"n": -1}}]))
    print("    Joined via:")
    for a in agg:
        print(f"      {a['n']:>6}  {a['_id'] or '(not joined)'}")
    if hb and "intent_address_join_rate" in m:
        print(f"    address-path join rate at the last build: "
              f"{m['intent_address_join_rate']} (measured baseline 1.0; below 0.5 raises)")
    else:
        print("    address-path join rate: unknown — no build heartbeat carries it yet. "
              "Not reported as a fake 1.0.")

    # ── ⛔ s21(3): the SIZE of the open question, not a change to the exclusion ──
    # The exclusion in collect_track_b_leads is untouched. This counts how many of the
    # leads it drops carry the `on_market_expiring` label — the cohort seller_intent
    # scores highest (listing_bonus +22) and whose Form 6 appointment is exactly what
    # s21(3) turns on. Whether they should be SCHEDULED for after expiry rather than
    # excluded is Will's legal call. No scheduling is built here.
    s21 = list(sm_db.lead_worklist.aggregate([
        {"$match": {"sources": "listing_expiry", "is_test": {"$ne": True}}},
        {"$group": {"_id": "$seller_intent.label", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}]))
    tot = sum(a["n"] for a in s21)
    print(f"\n  ⛔ EXCLUDED under POA Reg 2014 s21(3) — {tot} lead(s) carry source "
          f"'listing_expiry' and are dropped before scoring. UNCHANGED. By seller-intent label:")
    for a in s21:
        mark = ("  ← another agent's appointment IS IN FORCE and nearing expiry; whether "
                "to SCHEDULE these for after expiry is Will's decision, not this script's"
                if a["_id"] == "on_market_expiring" else "")
        print(f"    {a['n']:>6}  {a['_id'] or '(no seller_intent)'}{mark}")

    no_hook = coll.count_documents({"hook.line": ""})
    if no_hook:
        print(f"  ⚠ {no_hook} rows have NO hook — every candidate line failed the editorial guard")


def do_needs_id4me(gc_db, sm_db, args):
    """Ranked list of addresses that are good call candidates but carry NO ID4ME
    data yet. This is the input to a HUMAN-PACED append run — this script never
    calls ID4ME (ToS forbids automated extraction; 800/day cap; can_use_api false)."""
    ctx = HookContext(gc_db)
    ex = Excluded()
    stats = Counter()
    intents = IntentIndex(sm_db)
    addresses = collect_track_b_leads(sm_db, ex)
    if args.suburb:
        addresses = [a for a in addresses if a["suburb"] == args.suburb]
    # populates _needs_id4me AND _intent
    property_rows(gc_db, ctx, "B_intent", addresses, ex, stats, intents=intents)
    pending = [a for a in addresses if a.get("_needs_id4me")]

    # ⚠ THIS ORDERING IS THE HIGHEST-VALUE PART OF THE INTENT WIRING. The append is
    # human-paced at ~50/day over ~5 days, so this rank decides who we are even ABLE
    # to call in week 1. Ranking it on reachability alone spent the first day on the
    # freshest ID4ME records rather than on the people who told us they are thinking
    # about selling. It uses the identical score_candidate() as --build so the two
    # can never drift apart.
    #
    # `phone_type="mobile"` and `record_age_years=None` are placeholders — neither is
    # knowable before the append, and both are constant across every pending row, so
    # they cannot change the ORDER. record_age_years=None means reach_factor is 0.70
    # for everyone here: intent is scaled uniformly, not discounted unevenly on a
    # number we do not have yet.
    def rank(a):
        facts = a.get("_facts") or {}
        s, _ = score_candidate("B_intent", a["suburb"], "mobile", None,
                               facts.get("years_held"), a.get("_occupancy"), "unknown",
                               None, a.get("_intent"))
        return s

    pending.sort(key=rank, reverse=True)
    if args.limit:
        pending = pending[: args.limit]

    # Rule 7b on the read: a collapsed join here would silently restore the old
    # reachability-only ordering and look like a normal run.
    addr_joined, addr_tried = intents.address_join_rate()
    if intents.n_docs == 0:
        raise RuntimeError("IntentIndex read 0 non-test lead_worklist documents — the "
                           "seller-intent layer is unreadable, not empty.")
    if addr_tried >= 20 and (addr_joined / addr_tried) < 0.50:
        raise RuntimeError(
            f"seller-intent address join collapsed: {addr_joined}/{addr_tried} "
            f"({addr_joined / addr_tried:.0%}) against a measured 100% baseline — a broken "
            f"join, not absent intent data. Refusing to emit a reachability-only append order.")

    print(f"\nAddresses needing an ID4ME append — {now_aest_str()}")
    print(f"  {len(pending)} ranked candidates (Track B intent leads, exclusions already applied)")
    print(f"  Ranked by score_candidate() — reachability AND seller intent, the same "
          f"function --build uses.")
    print(f"  ⚠ Append these BY HAND. ID4ME ToS forbids automated extraction; cap 800/day; "
          f"can_use_api is false on our subscription.")
    print(f"\n  Seller intent across the pending list "
          f"(join: {addr_joined}/{addr_tried} by address, {dict(intents.lookups)}):")
    lbl = Counter((a.get("_intent") or {}).get("label") for a in pending)
    for k, n in lbl.most_common():
        flag = "  ⚠ scored NEGATIVE — committed to a competitor" if k == "on_market_fresh" else ""
        print(f"    {n:>6}  {k or '(no intent joined)'}{flag}")
    hot = [a for a in pending if ((a.get("_intent") or {}).get("hotness") or 0) >= 7]
    hot_first50 = [a for a in pending[:50] if ((a.get("_intent") or {}).get("hotness") or 0) >= 7]
    print(f"    hotness >= 7: {len(hot)} in the list, {len(hot_first50)} inside the first 50 "
          f"(= day 1 of the append run)")
    moments = [a for a in pending if (a.get("_intent") or {}).get("moment")]
    print(f"    live/recent `moment`: {len(moments)}  "
          f"(decays to nothing {int(MOMENT_DEAD_DAYS)} days after the signal)")
    print("\nExclusions applied:")
    for line in ex.report():
        print(line)
    if ex.s21_labels:
        # ⛔ Counter only — the s21(3) exclusion is unchanged and no scheduling is built.
        print(f"    of the {ex.counts['s21_listing_expiry']} excluded under s21(3), by "
              f"seller-intent label (OPEN QUESTION for Will — not a change):")
        for k, n in ex.s21_labels.most_common():
            mark = "  ← appointment IS IN FORCE and nearing expiry" if k == "on_market_expiring" else ""
            print(f"      {n:>6}  {k}{mark}")
    by_suburb = Counter(a["suburb"] for a in pending)
    print("\n  By suburb (ID4ME freshness measured: Robina 66.7%, Burleigh Waters 41.7%, "
          "Varsity Lakes 8.3%):")
    for s, n in by_suburb.most_common():
        print(f"    {n:>6}  {SUBURB_LABEL.get(s, s)}")

    if args.out:
        with open(args.out, "w", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["rank", "address", "suburb", "postcode", "years_held",
                        "occupancy", "lead_signals", "score_proxy",
                        "intent_label", "hotness", "behavioral_score", "moment",
                        "intent_note"])
            for i, a in enumerate(pending, 1):
                facts = a.get("_facts") or {}
                it = a.get("_intent") or {}
                w.writerow([i, a["address"], SUBURB_LABEL.get(a["suburb"], a["suburb"]),
                            SUBURB_POSTCODE.get(a["suburb"], ""), facts.get("years_held") or "",
                            a.get("_occupancy") or "unknown",
                            "|".join(a.get("lead_signals") or []), f"{rank(a):.4f}",
                            it.get("label") or "", it.get("hotness") if it else "",
                            it.get("behavioral_score") if it else "",
                            it.get("moment") or "", intent_note(a.get("_intent"))])
        print(f"\n  Written: {args.out}")
    else:
        print("\n  (addresses withheld from stdout — pass --out FILE to write the list)")
    return pending


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true", help="select, score and queue candidates")
    ap.add_argument("--stats", action="store_true", help="queue composition + what is blocked")
    ap.add_argument("--needs-id4me", action="store_true",
                    help="ranked addresses awaiting a HUMAN-PACED ID4ME append")
    ap.add_argument("--track", choices=["A", "B", "C"])
    ap.add_argument("--suburb", choices=CORE_SUBURBS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", help="--needs-id4me: TSV output path")
    ap.add_argument("--dry-run", action="store_true", help="--build: compute but never write")
    ap.add_argument("--include-prior", action="store_true",
                    help="--build: KEEP people occupancy_evidence dates to before the last "
                         "sale. Off by default: each one is a paid DNC wash credit and a "
                         "stranger on the phone. For testing/analysis only.")
    ap.add_argument("--max-per-address", type=int, default=None,
                    help="--build: cap queue rows per address (default 2). ID4ME lists up to "
                         "12 people at one house; dialling five of them is what gets us "
                         "complained about. 0 disables the cap.")
    args = ap.parse_args()

    if not (args.build or args.stats or args.needs_id4me):
        ap.error("one of --build / --stats / --needs-id4me is required")

    set_env_from_file()
    from shared.db import get_client, get_gold_coast_db
    from job_status import job_run

    client = get_client()
    gc_db = get_gold_coast_db()
    sm_db = client[QUEUE_DB]

    if args.stats:
        do_stats(sm_db)
    if args.needs_id4me:
        do_needs_id4me(gc_db, sm_db, args)
    if args.build:
        with job_run("build_call_list", cadence_hours=24,
                     title="Direct-call list builder") as beat:
            do_build(gc_db, sm_db, args, beat)


if __name__ == "__main__":
    main()
