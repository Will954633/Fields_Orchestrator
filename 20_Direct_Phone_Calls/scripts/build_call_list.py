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
  python3 build_call_list.py --needs-id4me [--out addresses.tsv] [--limit 200]

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
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

AEST = ZoneInfo("Australia/Brisbane")

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
SUBURB_LABEL = {"robina": "Robina", "varsity_lakes": "Varsity Lakes",
                "burleigh_waters": "Burleigh Waters"}
SUBURB_POSTCODE = {"robina": "4226", "varsity_lakes": "4227", "burleigh_waters": "4220"}

QUEUE_DB = "system_monitor"
QUEUE_COLL = "call_queue"

TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au"}
TEST_SLUGS = {"7-huntingdale-crescent-robina", "5-fulham-place-robina"}

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
def id4me_people(gc_doc: dict) -> list[dict]:
    """Every (person, phone) pair carried on a property doc's ID4ME_Contact_Data.

    Verified against the ONE document in Gold_Coast that currently has this object
    (20 Chantilly Place, Robina — 12 people, 47 raw records). Written defensively
    because n=1: any missing key degrades to None rather than raising."""
    blob = gc_doc.get("ID4ME_Contact_Data") or {}
    if blob.get("ID4ME_Status") != "ok":
        return []
    retrieved_at = blob.get("ID4ME_Retrieved_At")
    gnaf = blob.get("ID4ME_GNAF_PID")
    out = []
    for person in blob.get("ID4ME_People") or []:
        blocked = {re.sub(r"\D", "", str(b)) for b in (person.get("ID4ME_DNCR_Blocked") or [])}
        has_dncr_detail = bool(person.get("ID4ME_DNCR_Detail"))
        source_date = person.get("ID4ME_Source_Date_Latest") or blob.get("ID4ME_Most_Recent_Source_Date")
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
    # de-duplicate identical numbers across people on the same address
    seen, uniq = set(), []
    for p in out:
        if p["phone"] in seen:
            continue
        seen.add(p["phone"])
        uniq.append(p)
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


def score_candidate(track: str, suburb: str, phone_type: str, record_age_years: float | None,
                    years_held: float | None, occupancy_type: str | None,
                    advisory: str) -> tuple[float, dict]:
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
    # ID4ME's DNC flag buys us no legal defence (ACMA IS 157) but it is still the
    # best available signal that a wash will reject the number — deprioritise, do
    # not drop, because dnc_wash.py is the only thing entitled to decide.
    parts["dnc_advisory"] = -0.20 if advisory == "blocked" else 0.0
    return round(sum(parts.values()), 4), parts


# ─────────────────────────────────────────────────────────────────────────────
# candidate assembly
# ─────────────────────────────────────────────────────────────────────────────
class Excluded:
    """Named, counted exclusions — never a silent omission."""

    def __init__(self):
        self.counts = Counter()
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


def property_rows(gc_db, ctx, track, addresses, ex: Excluded, stats: Counter) -> list[dict]:
    """Turn address-level candidates (B or C) into (address, phone) rows.

    Every exclusion is counted so --stats can say honestly how many candidates are
    blocked on the ID4ME append versus genuinely unusable."""
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
        people = id4me_people(gc_doc)
        if not people:
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
                "occupancy_type": occ_res.get("type"),
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
    res = {"inserted": 0, "updated": 0, "skipped_terminal": 0}
    for r in rows:
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
            "occupancy_type": r.get("occupancy_type"),
            "lead_signals": r.get("lead_signals") or [],
            "source_ref": r.get("source_ref"),
            "updated_at": now_utc(),
        }
        if r.get("consent"):
            mutable["consent"] = r["consent"]
        if dry_run:
            res["inserted" if not existing else "updated"] += 1
            continue
        coll.update_one({"_id": _id}, {
            "$set": mutable,
            # dnc.status is seeded once and never touched again by this script.
            "$setOnInsert": {"created_at": now_utc(), "status": "queued",
                             "dnc": {"status": "unwashed",
                                     "id4me_advisory": r.get("id4me_advisory") or "unknown"}},
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
            rows.append(r)
        stats["track_a_rows"] = len(rows)

    b_addresses = []
    if "B_intent" in wanted or args.needs_id4me:
        b_addresses = collect_track_b_leads(sm_db, ex)
        if args.suburb:
            b_addresses = [a for a in b_addresses if a["suburb"] == args.suburb]
    if "B_intent" in wanted:
        b_rows = property_rows(gc_db, ctx, "B_intent", b_addresses, ex, stats)
        stats["track_b_rows"] = len(b_rows)
        rows += b_rows
        needs_id4me += [a for a in b_addresses if a.get("_needs_id4me")]

    if "C_openmarket" in wanted:
        known = {address_slug(a["address"]) for a in b_addresses}
        c_addresses = collect_track_c_addresses(gc_db, suburbs, known, args.limit or 0)
        c_rows = property_rows(gc_db, ctx, "C_openmarket", c_addresses, ex, stats)
        stats["track_c_rows"] = len(c_rows)
        rows += c_rows

    for r in rows:
        r["score"], r["score_parts"] = score_candidate(
            r["track"], r["suburb"], r["phone_type"], r.get("record_age_years"),
            (r.get("facts") or {}).get("years_held"), r.get("occupancy_type"),
            r.get("id4me_advisory") or "unknown")
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
    considered = stats["candidates_considered"]
    with_id4me = stats["with_id4me"]
    if with_id4me > 0 and stats["track_b_rows"] + stats["track_c_rows"] == 0:
        raise RuntimeError(
            f"{with_id4me} propert{'ies' if with_id4me != 1 else 'y'} carried ID4ME_Contact_Data "
            f"but produced 0 queue rows — phone extraction is broken, not empty upstream.")
    if considered > 0 and not rows and stats["blocked_on_id4me"] == 0:
        raise RuntimeError(
            f"{considered} candidates were considered and 0 queue rows produced, with none blocked "
            f"on the ID4ME append — the selection pipeline gave us nothing.")

    beat.metrics = {
        "candidates_considered": considered,
        "queue_rows": len(rows),
        "inserted": write["inserted"], "updated": write["updated"],
        "skipped_terminal": write["skipped_terminal"],
        "track_a": stats["track_a_rows"], "track_b": stats["track_b_rows"],
        "track_c": stats["track_c_rows"],
        "with_id4me": with_id4me, "blocked_on_id4me": stats["blocked_on_id4me"],
        "excluded_s21": ex.counts["s21_listing_expiry"],
        "excluded_currently_listed": ex.counts["currently_listed"],
        "excluded_investor": ex.counts["tenanted_investor"],
        "dry_run": bool(args.dry_run),
    }
    beat.detail = (f"{len(rows)} row(s) queued ({write['inserted']} new); "
                   f"{stats['blocked_on_id4me']} candidates blocked on ID4ME append")

    print(f"\nBuild — {now_aest_str()}{'  [DRY RUN]' if args.dry_run else ''}")
    print(f"  candidates considered : {considered}")
    print(f"  queue rows produced   : {len(rows)}  "
          f"(A {stats['track_a_rows']} / B {stats['track_b_rows']} / C {stats['track_c_rows']})")
    print(f"  written               : {write['inserted']} inserted, {write['updated']} updated, "
          f"{write['skipped_terminal']} left alone (terminal status)")
    print(f"  blocked on ID4ME      : {stats['blocked_on_id4me']}  "
          f"(run --needs-id4me for the human-paced append list)")
    print("\nExclusions (named, never silent):")
    for line in ex.report():
        print(line)
    if rows:
        print("\nTop rows (masked):")
        for r in rows[:10]:
            print(f"  {r['score']:.3f}  {r['track']:<12} {r['suburb'] or '-':<16} "
                  f"{mask_name(r.get('person_name'))!s:<10} {mask_phone(r['phone'])} "
                  f"({r['phone_type']}, age {r.get('record_age_years')})")
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
    addresses = collect_track_b_leads(sm_db, ex)
    if args.suburb:
        addresses = [a for a in addresses if a["suburb"] == args.suburb]
    property_rows(gc_db, ctx, "B_intent", addresses, ex, stats)  # populates _needs_id4me
    pending = [a for a in addresses if a.get("_needs_id4me")]

    def rank(a):
        facts = a.get("_facts") or {}
        s, _ = score_candidate("B_intent", a["suburb"], "mobile", None,
                               facts.get("years_held"), a.get("_occupancy"), "unknown")
        return s

    pending.sort(key=rank, reverse=True)
    if args.limit:
        pending = pending[: args.limit]

    print(f"\nAddresses needing an ID4ME append — {now_aest_str()}")
    print(f"  {len(pending)} ranked candidates (Track B intent leads, exclusions already applied)")
    print(f"  ⚠ Append these BY HAND. ID4ME ToS forbids automated extraction; cap 800/day; "
          f"can_use_api is false on our subscription.")
    print("\nExclusions applied:")
    for line in ex.report():
        print(line)
    by_suburb = Counter(a["suburb"] for a in pending)
    print("\n  By suburb (ID4ME freshness measured: Robina 66.7%, Burleigh Waters 41.7%, "
          "Varsity Lakes 8.3%):")
    for s, n in by_suburb.most_common():
        print(f"    {n:>6}  {SUBURB_LABEL.get(s, s)}")

    if args.out:
        with open(args.out, "w", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["rank", "address", "suburb", "postcode", "years_held",
                        "occupancy", "lead_signals", "score_proxy"])
            for i, a in enumerate(pending, 1):
                facts = a.get("_facts") or {}
                w.writerow([i, a["address"], SUBURB_LABEL.get(a["suburb"], a["suburb"]),
                            SUBURB_POSTCODE.get(a["suburb"], ""), facts.get("years_held") or "",
                            a.get("_occupancy") or "unknown",
                            "|".join(a.get("lead_signals") or []), f"{rank(a):.4f}"])
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
