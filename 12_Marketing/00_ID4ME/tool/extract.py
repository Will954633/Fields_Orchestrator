"""Turn raw ID4ME hits into deduplicated, spreadsheet-ready rows.

ID4ME returns one row per source record, not per person, so a single address
commonly yields the same individual several times with different contact
fragments attached (one row has their mobile, another their email). We merge
those into one row per person and union their contact details.

Merging is deliberately conservative: the key is (name, date of birth), so two
different spellings of one person stay separate rather than risk collapsing two
genuinely different people who happen to share a birthday.
"""

import re

CSV_COLUMNS = [
    "address_searched", "matched_address", "result_count",
    "full_name", "first_name", "middle_name", "surname", "title",
    "date_of_birth", "gender",
    "mobiles", "landlines", "emails",
    "dncr_blocked", "dncr_detail", "emails_marketable",
    "suburb", "state", "postcode",
    "gnaf_pid", "latitude", "longitude",
    "source_date_latest", "record_ids",
]


def _strip_highlight(text: str | None) -> str:
    """ID4ME wraps search-term matches in <em> tags in full_address."""
    return re.sub(r"</?em>", "", text or "").strip()


def _date(value: str | None) -> str:
    return (value or "")[:10]


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def _person_key(rec: dict) -> tuple[str, str]:
    name = re.sub(r"\s+", " ", (rec.get("full_name") or "").strip().lower())
    return name, _date(rec.get("dateofbirth_1_dt"))


def merge_records(records: list[dict]) -> list[dict]:
    """Collapse raw hits into one entry per (name, dob), newest data winning."""
    people: dict[tuple[str, str], dict] = {}

    for rec in records:
        key = _person_key(rec)
        person = people.setdefault(key, {
            "full_name": (rec.get("full_name") or "").strip(),
            "first_name": rec.get("gn_1_1") or "",
            "middle_name": rec.get("gn_1_2") or "",
            "surname": rec.get("sn_1_1") or "",
            "title": rec.get("t_1_1") or "",
            "date_of_birth": _date(rec.get("dateofbirth_1_dt")),
            "gender": rec.get("gender") or "",
            "mobiles": set(), "landlines": set(), "emails": set(),
            "matched_address": "", "suburb": "", "state": "", "postcode": "",
            "gnaf_pid": "", "latitude": "", "longitude": "",
            "source_date_latest": "", "record_ids": [],
        })

        if mobile := _digits(rec.get("phone2_mobile")):
            person["mobiles"].add(mobile)
        if landline := _digits(rec.get("phone1_landline")):
            person["landlines"].add(landline)
        if email := (rec.get("emailaddress") or "").strip().lower():
            person["emails"].add(email)

        # Fill blanks from whichever row happens to carry the value.
        for field, value in (
            ("matched_address", _strip_highlight(rec.get("full_address"))),
            ("suburb", rec.get("suburb")),
            ("state", rec.get("state")),
            ("postcode", rec.get("postcode")),
            ("gnaf_pid", rec.get("gnaf_pid")),
            ("gender", rec.get("gender")),
            ("title", rec.get("t_1_1")),
            ("first_name", rec.get("gn_1_1")),
            ("middle_name", rec.get("gn_1_2")),
            ("surname", rec.get("sn_1_1")),
        ):
            if not person[field] and value:
                person[field] = str(value)

        if not person["latitude"] and (loc := rec.get("location")):
            lat, _, lon = str(loc).partition(",")
            person["latitude"], person["longitude"] = lat.strip(), lon.strip()

        source = _date(rec.get("source_date_dt"))
        if source > person["source_date_latest"]:
            person["source_date_latest"] = source
        if rec_id := rec.get("id"):
            person["record_ids"].append(rec_id)

    # Freshest contacts first - most useful ordering for calling down a list.
    return sorted(people.values(),
                  key=lambda p: p["source_date_latest"], reverse=True)


def all_phones(people: list[dict]) -> list[str]:
    out: set[str] = set()
    for p in people:
        out |= p["mobiles"] | p["landlines"]
    return sorted(out)


def all_emails(people: list[dict]) -> list[str]:
    out: set[str] = set()
    for p in people:
        out |= p["emails"]
    return sorted(out)


def apply_compliance(people: list[dict], dncr: dict, marketable: dict) -> None:
    """Annotate each person with DNCR and email-marketability flags in place."""
    for person in people:
        blocked, detail = [], []
        for phone in sorted(person["mobiles"] | person["landlines"]):
            row = dncr.get(phone) or {}
            if str(row.get("dncr_status", "")).upper() == "Y":
                blocked.append(phone)
                detail.append(f"{phone}: {row.get('Message', 'on DNCR')}")
        person["dncr_blocked"] = "; ".join(blocked)
        person["dncr_detail"] = "; ".join(detail)
        person["emails_marketable"] = "; ".join(
            f"{e}={'yes' if marketable.get(e) else 'no'}"
            for e in sorted(person["emails"])
        )


def to_rows(people: list[dict], address_searched: str,
            matched_address: str, result_count: int) -> list[dict]:
    """Flatten to plain dicts matching CSV_COLUMNS."""
    rows = []
    for person in people:
        row = dict(person)
        row["address_searched"] = address_searched
        row["matched_address"] = person.get("matched_address") or matched_address
        row["result_count"] = result_count
        for field in ("mobiles", "landlines", "emails"):
            row[field] = "; ".join(sorted(person[field]))
        row["record_ids"] = "; ".join(person["record_ids"])
        rows.append({col: row.get(col, "") for col in CSV_COLUMNS})
    return rows
