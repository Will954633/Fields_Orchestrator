#!/usr/bin/env python3
"""ID4ME address lookup - the day-to-day tool.

Talks to the ID4ME JSON API directly, so a lookup takes about a second instead
of the ~20 seconds it takes to drive the dashboard UI.

  python3 lookup.py "27 huntingdale crescent, robina, qld 4226"
  python3 lookup.py --batch addresses.csv
  python3 lookup.py --batch addresses.csv --out today.csv

Authentication is handled automatically: a cached token is reused, refreshed
over HTTP when stale, and only as a last resort is a headless browser used to
sign in again. See README.md for the one-time setup.
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone

import config
import extract
from api import AuthError, Id4meClient


def lookup(client: Id4meClient, address: str, compliance: bool = True) -> dict:
    """Resolve one address and return its deduplicated people plus metadata."""
    result = {
        "address": address,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "status": "unknown",
        "matched_address": None,
        "result_count": 0,
        "people": [],
        "raw": [],
        "error": None,
    }

    try:
        canonical = client.resolve_address(address)
        if not canonical:
            result["status"] = "address_not_found"
            return result
        result["matched_address"] = canonical

        response = client.search(canonical)
        records = response.get("data") or []
        result["raw"] = records
        result["result_count"] = response.get("Total", len(records))

        if not records:
            result["status"] = "no_results"
            return result

        people = extract.merge_records(records)

        if compliance:
            phones = extract.all_phones(people)
            emails = extract.all_emails(people)
            try:
                extract.apply_compliance(people, client.dncr(phones),
                                         client.emails_can_market(emails))
            except Exception as exc:
                # Contact data is the point; compliance is a bonus. Never let
                # an enrichment failure discard a good result.
                result["error"] = f"compliance lookup failed: {exc}"

        result["people"] = people
        result["status"] = "ok"

    except AuthError as exc:
        result["status"] = "auth_error"
        result["error"] = str(exc)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def read_addresses(path: str) -> list[str]:
    """Read addresses from a CSV, tolerating unquoted commas.

    Addresses contain commas, and a hand-maintained one-per-line list rarely
    quotes them. In a single-column file the CSV reader would shred
    "27 Huntingdale Crescent, Robina, QLD 4226" into four fields and we would
    search only the first - which silently returns a wrong-but-plausible result
    rather than an error. So for single-column input we rejoin the whole line.

    Multi-column files (address plus notes, say) are properly quoted by whatever
    produced them, so there we honour the 'address' column.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if r and any(c.strip() for c in r)]
    if not rows:
        return []

    header = [c.strip().lower() for c in rows[0]]
    has_header = header[0] in {"address", "addresses", "full_address"}
    body = rows[1:] if has_header else rows

    if has_header and len(header) > 1 and "address" in header:
        idx = header.index("address")
        return [r[idx].strip() for r in body if len(r) > idx and r[idx].strip()]

    # Single column (or headerless): the row IS the address, commas included.
    return [line for r in body if (line := ",".join(r).strip())]


def write_outputs(results: list[dict], stem: str, out_path: str | None):
    csv_path = out_path or str(config.OUTPUT_DIR / f"{stem}.csv")
    json_path = str(config.OUTPUT_DIR / f"{stem}.json")

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=extract.CSV_COLUMNS)
        writer.writeheader()
        for res in results:
            rows = extract.to_rows(res["people"], res["address"],
                                   res["matched_address"] or "",
                                   res["result_count"])
            if rows:
                writer.writerows(rows)
            else:
                # Keep a placeholder so a miss is visible in the spreadsheet.
                writer.writerow({"address_searched": res["address"],
                                 "matched_address": res["status"]})

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    return csv_path, json_path


def print_result(res: dict) -> None:
    print(f"\naddress : {res['address']}")
    print(f"matched : {res['matched_address']}")
    print(f"status  : {res['status']}"
          + (f"  ({res['error']})" if res["error"] else ""))
    if not res["people"]:
        return
    print(f"people  : {len(res['people'])} unique "
          f"(from {res['result_count']} raw records)\n")
    for p in res["people"]:
        bits = [p["full_name"]]
        if p["date_of_birth"]:
            bits.append(f"b.{p['date_of_birth']}")
        print("  " + "  ".join(bits))
        for label, key in (("mobile", "mobiles"), ("landline", "landlines"),
                           ("email", "emails")):
            if p[key]:
                print(f"      {label:9}: {', '.join(sorted(p[key]))}")
        if p.get("dncr_blocked"):
            print(f"      {'DNCR':9}: DO NOT CALL {p['dncr_blocked']}")
        if p["source_date_latest"]:
            print(f"      {'seen':9}: {p['source_date_latest']}")


def show_status() -> int:
    """Report who we are authenticated as and how healthy the subscription is."""
    try:
        profile = Id4meClient().profile()
    except AuthError as exc:
        print(f"Authentication failed: {exc}")
        return 2
    except Exception as exc:
        print(f"Could not read profile: {type(exc).__name__}: {exc}")
        return 2

    meta = profile.get("user_metadata") or {}
    for label, value in (
        ("account", profile.get("email")),
        ("name", profile.get("name")),
        ("subscription", meta.get("subscription_status")),
        ("plan", meta.get("subscription_plan")),
        ("smart search", profile.get("smart_search_enabled")),
        ("blocked", profile.get("blocked")),
        ("last login", profile.get("last_login")),
        ("expires", meta.get("financial_expiry")),
    ):
        if value is not None:
            print(f"  {label:14}: {value}")

    expiry = str(meta.get("financial_expiry") or "")[:10]
    if expiry:
        try:
            days = (datetime.fromisoformat(expiry).date()
                    - datetime.now(timezone.utc).date()).days
            if days <= 14:
                print(f"\n  WARNING: subscription expires in {days} day(s) "
                      f"({expiry}). Lookups will start failing after that.")
        except ValueError:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("address", nargs="?", help="a single address to look up")
    ap.add_argument("--batch", metavar="CSV", help="CSV of addresses to look up")
    ap.add_argument("--out", help="explicit output CSV path")
    ap.add_argument("--no-compliance", action="store_true",
                    help="skip the DNCR and email-marketability lookups")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds between batch lookups (default 1.0)")
    ap.add_argument("--status", action="store_true",
                    help="show account and subscription status, then exit")
    args = ap.parse_args()

    if args.status:
        return show_status()

    if not args.address and not args.batch:
        ap.error("give an address, or --batch a CSV of them")

    addresses = read_addresses(args.batch) if args.batch else [args.address]
    if not addresses:
        print(f"No addresses found in {args.batch}")
        return 1

    try:
        client = Id4meClient()
    except AuthError as exc:
        print(f"Authentication failed: {exc}")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results = []
    for i, address in enumerate(addresses, 1):
        if len(addresses) > 1:
            print(f"[{i}/{len(addresses)}] {address}", flush=True)
        res = lookup(client, address, compliance=not args.no_compliance)
        results.append(res)
        if len(addresses) > 1:
            print(f"    -> {res['status']}: {len(res['people'])} people")
        else:
            print_result(res)
        if i < len(addresses):
            time.sleep(args.delay)

    csv_path, json_path = write_outputs(
        results, f"lookup_{stamp}" if len(addresses) == 1 else f"batch_{stamp}",
        args.out)

    ok = sum(1 for r in results if r["status"] == "ok")
    people = sum(len(r["people"]) for r in results)
    print(f"\n{ok}/{len(results)} addresses resolved, {people} people total")
    print(f"  {csv_path}\n  {json_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
