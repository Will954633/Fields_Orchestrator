#!/usr/bin/env python3
"""Pull ID4ME occupant/contact records for an address and write them onto that
property's document in the Gold_Coast database.

Every field written carries "ID4ME" in its label, so provenance is visible at a
glance anywhere the document is read and nothing can be mistaken for our own
data.

    python3 id4me_to_mongo.py --address "20 Chantilly Place, Robina, QLD 4226"
    python3 id4me_to_mongo.py --address "..." --dry-run

The lookup itself is the unmodified tool in unzipped_20260813/01_ID4ME - this
script only orchestrates it and shapes the result for Mongo.

PRIVACY: the payload holds names, dates of birth, phone numbers and email
addresses of real people. Australian Privacy Act obligations apply. Check
ID4ME_DNCR_Blocked before any phone contact.
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ID4ME_DIR = Path(__file__).resolve().parent / "unzipped_20260813" / "01_ID4ME"
sys.path.insert(0, str(ID4ME_DIR))

import lookup as id4me_lookup          # noqa: E402
from api import AuthError, Id4meClient  # noqa: E402

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db  # noqa: E402

ROOT_FIELD = "ID4ME_Contact_Data"

# person key in the tool's output -> the ID4ME-labelled name we store
PERSON_FIELDS = {
    "full_name": "ID4ME_Full_Name",
    "first_name": "ID4ME_First_Name",
    "middle_name": "ID4ME_Middle_Name",
    "surname": "ID4ME_Surname",
    "title": "ID4ME_Title",
    "date_of_birth": "ID4ME_Date_Of_Birth",
    "gender": "ID4ME_Gender",
    "matched_address": "ID4ME_Matched_Address",
    "suburb": "ID4ME_Suburb",
    "state": "ID4ME_State",
    "postcode": "ID4ME_Postcode",
    "gnaf_pid": "ID4ME_GNAF_PID",
    "latitude": "ID4ME_Latitude",
    "longitude": "ID4ME_Longitude",
    "source_date_latest": "ID4ME_Source_Date_Latest",
    "dncr_detail": "ID4ME_DNCR_Detail",
    "emails_marketable": "ID4ME_Emails_Marketable",
}
SET_FIELDS = {                      # sets -> sorted lists
    "mobiles": "ID4ME_Mobiles",
    "landlines": "ID4ME_Landlines",
    "emails": "ID4ME_Emails",
}


def _suburb_collection(suburb: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (suburb or "").strip().lower()).strip("_")


def find_property(db, address: str, suburb: str | None = None):
    """Locate the property document for a free-text address.

    Matches on `address` case-insensitively and anchored, so "20 Chantilly
    Place" cannot pick up "120 Chantilly Place".
    """
    pattern = re.compile(r"^\s*" + re.escape(address.strip()) + r"\s*$", re.I)
    names = [_suburb_collection(suburb)] if suburb else db.list_collection_names()
    for name in names:
        if not name:
            continue
        doc = db[name].find_one({"address": pattern})
        if doc:
            return name, doc
    return None, None


def shape_for_mongo(result: dict) -> dict:
    """Turn a lookup() result into an all-ID4ME-labelled payload.

    Sets become sorted lists (the tool's own JSON writer stringifies them as
    "set()", which is unusable downstream), and raw records keep every original
    key under an ID4ME_Raw_ prefix so nothing in the document is unlabelled.
    """
    people = []
    for person in result["people"]:
        out = {label: (person.get(key) or "") for key, label in PERSON_FIELDS.items()}
        for key, label in SET_FIELDS.items():
            out[label] = sorted(person.get(key) or [])
        blocked = person.get("dncr_blocked") or ""
        out["ID4ME_DNCR_Blocked"] = [p for p in blocked.split("; ") if p]
        out["ID4ME_Record_IDs"] = list(person.get("record_ids") or [])
        people.append(out)

    raw = [{f"ID4ME_Raw_{k}": v for k, v in rec.items()} for rec in result.get("raw") or []]

    first = result["people"][0] if result["people"] else {}
    payload = {
        "ID4ME_Status": result["status"],
        "ID4ME_Address_Searched": result["address"],
        "ID4ME_Matched_Address": result.get("matched_address") or "",
        "ID4ME_Raw_Record_Count": result.get("result_count", 0),
        "ID4ME_People_Count": len(people),
        "ID4ME_Retrieved_At": datetime.now(timezone.utc).isoformat(),
        "ID4ME_Source": "id4me.me search API (values/explain)",
        "ID4ME_GNAF_PID": first.get("gnaf_pid", ""),
        "ID4ME_Latitude": first.get("latitude", ""),
        "ID4ME_Longitude": first.get("longitude", ""),
        "ID4ME_Most_Recent_Source_Date": max(
            (p["ID4ME_Source_Date_Latest"] for p in people if p["ID4ME_Source_Date_Latest"]),
            default=""),
        "ID4ME_Has_Callable_Phone": any(
            set(p["ID4ME_Mobiles"] + p["ID4ME_Landlines"]) - set(p["ID4ME_DNCR_Blocked"])
            for p in people),
        "ID4ME_Has_Email": any(p["ID4ME_Emails"] for p in people),
        "ID4ME_People": people,
        "ID4ME_Raw_Records": raw,
    }
    if result.get("error"):
        payload["ID4ME_Error"] = result["error"]
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address", required=True, help="address as stored in Mongo")
    ap.add_argument("--suburb", help="restrict the document search to one suburb collection")
    ap.add_argument("--dry-run", action="store_true", help="print the payload, write nothing")
    args = ap.parse_args()

    db = get_gold_coast_db()
    collection, doc = find_property(db, args.address, args.suburb)
    if not doc:
        print(f"No property document found for: {args.address}")
        return 1
    print(f"property : Gold_Coast.{collection}  _id={doc['_id']}")

    try:
        client = Id4meClient()
    except AuthError as exc:
        print(f"ID4ME authentication failed: {exc}")
        return 2

    result = id4me_lookup.lookup(client, args.address, compliance=True)
    print(f"ID4ME    : {result['status']}  matched={result.get('matched_address')}  "
          f"{len(result['people'])} people from {result['result_count']} raw records")

    if result["status"] != "ok":
        # A miss must not overwrite a good earlier pull with an empty one.
        print("Not 'ok' - nothing written.")
        return 1

    payload = shape_for_mongo(result)

    if args.dry_run:
        import json
        print(json.dumps(payload, indent=2, default=str)[:4000])
        return 0

    res = db[collection].update_one({"_id": doc["_id"]}, {"$set": {ROOT_FIELD: payload}})
    print(f"written  : matched={res.matched_count} modified={res.modified_count} "
          f"-> {ROOT_FIELD} ({payload['ID4ME_People_Count']} people, "
          f"{len(payload['ID4ME_Raw_Records'])} raw records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
