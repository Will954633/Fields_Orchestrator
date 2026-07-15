#!/usr/bin/env python3
"""
Sample ~5,000 residential addresses per city from G-NAF data.

Strategy:
- Load ADDRESS_DETAIL, STREET_LOCALITY, LOCALITY for QLD, NSW, VIC
- Filter to Brisbane, Sydney, Melbourne metro suburbs (by postcode ranges)
- Exclude units/flats (focus on houses — easier to match on Domain profiles)
- Sample evenly across suburbs for demographic diversity
- Output: addresses.json with 15,000 entries

Postcode ranges for metro areas:
- Brisbane: 4000-4209 (core metro + near suburbs)
- Sydney: 2000-2249 (core), 2555-2770 (western), 2085-2110 (north shore)
- Melbourne: 3000-3210 (core metro + near suburbs)
"""

import csv
import json
import random
import sys
from pathlib import Path
from collections import defaultdict

GNAF_DIR = Path(__file__).parent / "G-NAF" / "G-NAF FEBRUARY 2026"
STANDARD_DIR = GNAF_DIR / "Standard"
AUTH_DIR = GNAF_DIR / "Authority Code"
OUTPUT_FILE = Path(__file__).parent.parent / "laptop" / "addresses.json"

TARGET_PER_CITY = 5000

# Postcode ranges for metro areas (wide coverage of greater metro)
CITY_POSTCODES = {
    "brisbane": [
        (4000, 4179),  # Brisbane CBD, inner, middle, outer suburbs
        (4205, 4230),  # Gold Coast northern fringe / Logan
        (4300, 4340),  # Ipswich / Springfield
    ],
    "sydney": [
        (2000, 2234),  # CBD, East, Inner West, North Shore, Northern Beaches, Sutherland
        (2560, 2575),  # Campbelltown / Camden
        (2745, 2770),  # Penrith / Western Sydney
        (2100, 2126),  # Northern suburbs (Dee Why to Cherrybrook)
        (2140, 2200),  # Inner west to South Sydney
        (2204, 2234),  # Canterbury to Cronulla
    ],
    "melbourne": [
        (3000, 3207),  # CBD, inner suburbs
        (3011, 3060),  # Western + Northern inner suburbs
        (3070, 3135),  # Eastern suburbs (Northcote to Vermont)
        (3140, 3180),  # Outer east (Lilydale to Mulgrave)
        (3182, 3207),  # Bayside (St Kilda to Sandringham)
        (3335, 3340),  # Melton / western growth
        (3427, 3430),  # Sunbury
        (3750, 3756),  # South Morang / Mernda
        (3800, 3810),  # Dandenong / Berwick
    ],
}

STATE_FILES = {
    "brisbane": "QLD",
    "sydney": "NSW",
    "melbourne": "VIC",
}


def read_psv(filepath):
    """Read a pipe-separated file, return list of dicts."""
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            rows.append(row)
    return rows


def postcode_in_city(postcode_str, city):
    """Check if a postcode falls within a city's metro ranges."""
    try:
        pc = int(postcode_str)
    except (ValueError, TypeError):
        return False
    for low, high in CITY_POSTCODES[city]:
        if low <= pc <= high:
            return True
    return False


def load_street_type_lookup():
    """Load street type abbreviations (ST -> STREET, RD -> ROAD, etc.)."""
    path = AUTH_DIR / "Authority_Code_STREET_TYPE_AUT_psv.psv"
    lookup = {}
    if path.exists():
        for row in read_psv(path):
            code = row.get("CODE", "")
            name = row.get("NAME", "")
            if code:
                lookup[code] = name.title()
    return lookup


def build_address(addr_row, street_lookup, locality_lookup, street_types):
    """Build a full address string from G-NAF fields."""
    # Skip units/flats — we want houses only
    flat_type = addr_row.get("FLAT_TYPE_CODE", "").strip()
    flat_number = addr_row.get("FLAT_NUMBER", "").strip()
    if flat_type or flat_number:
        return None  # Skip units

    # Street number
    num = addr_row.get("NUMBER_FIRST", "").strip()
    if not num:
        return None  # No street number = not useful

    num_suffix = addr_row.get("NUMBER_FIRST_SUFFIX", "").strip()
    street_num = num + num_suffix

    # Street name from STREET_LOCALITY lookup
    street_pid = addr_row.get("STREET_LOCALITY_PID", "")
    street_info = street_lookup.get(street_pid, {})
    street_name = street_info.get("STREET_NAME", "").strip()
    street_type_code = street_info.get("STREET_TYPE_CODE", "").strip()

    if not street_name:
        return None

    # Resolve street type (ST -> Street, RD -> Road, etc.)
    street_type = street_types.get(street_type_code, street_type_code).title()

    # Locality (suburb)
    locality_pid = addr_row.get("LOCALITY_PID", "")
    loc_info = locality_lookup.get(locality_pid, {})
    suburb = loc_info.get("LOCALITY_NAME", "").strip().title()
    postcode = addr_row.get("POSTCODE", "").strip() or loc_info.get("PRIMARY_POSTCODE", "")

    if not suburb or not postcode:
        return None

    # Build the Domain-format address
    # Domain expects: "28 Federal Place, Robina, QLD 4226"
    state = loc_info.get("state_abbrev", "")
    address = f"{street_num} {street_name} {street_type}, {suburb}, {state} {postcode}"

    return {
        "address": address,
        "suburb": suburb,
        "postcode": postcode,
        "street_num": street_num,
        "street_name": f"{street_name} {street_type}",
    }


def process_city(city):
    """Load G-NAF data for one city and return all eligible addresses."""
    state_prefix = STATE_FILES[city]
    print(f"\n=== Processing {city.upper()} ({state_prefix}) ===")

    # Load street types
    print("  Loading street type lookup...")
    street_types = load_street_type_lookup()

    # Load locality (suburb) data
    print(f"  Loading {state_prefix} localities...")
    localities_raw = read_psv(STANDARD_DIR / f"{state_prefix}_LOCALITY_psv.psv")

    # Load state for abbreviation
    state_raw = read_psv(STANDARD_DIR / f"{state_prefix}_STATE_psv.psv")
    state_abbrev = ""
    if state_raw:
        state_abbrev = state_raw[0].get("STATE_ABBREVIATION", state_prefix)

    locality_lookup = {}
    for loc in localities_raw:
        pid = loc["LOCALITY_PID"]
        loc["state_abbrev"] = state_abbrev
        locality_lookup[pid] = loc

    print(f"  Total localities loaded: {len(locality_lookup)}")

    # Load street locality data
    print(f"  Loading {state_prefix} streets...")
    streets_raw = read_psv(STANDARD_DIR / f"{state_prefix}_STREET_LOCALITY_psv.psv")
    street_lookup = {}
    for st in streets_raw:
        street_lookup[st["STREET_LOCALITY_PID"]] = st

    # Load and filter addresses
    print(f"  Loading {state_prefix} addresses (this may take a minute)...")
    addr_file = STANDARD_DIR / f"{state_prefix}_ADDRESS_DETAIL_psv.psv"

    eligible = []
    total_read = 0
    skipped_non_metro = 0
    skipped_not_principal = 0
    skipped_no_address = 0
    skipped_units = 0

    with open(addr_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            total_read += 1

            # Only principal addresses (not aliases)
            if row.get("ALIAS_PRINCIPAL", "P") != "P":
                skipped_not_principal += 1
                continue

            # Only metro postcodes (check at address level, not locality level)
            addr_postcode = row.get("POSTCODE", "").strip()
            if not postcode_in_city(addr_postcode, city):
                skipped_non_metro += 1
                continue

            # Build address
            result = build_address(row, street_lookup, locality_lookup, street_types)
            if result is None:
                if row.get("FLAT_TYPE_CODE", "").strip() or row.get("FLAT_NUMBER", "").strip():
                    skipped_units += 1
                else:
                    skipped_no_address += 1
                continue

            result["city"] = city
            eligible.append(result)

            if total_read % 500000 == 0:
                print(f"    ...read {total_read:,} rows, {len(eligible):,} eligible so far")

    print(f"  Total rows read: {total_read:,}")
    print(f"  Skipped (non-metro): {skipped_non_metro:,}")
    print(f"  Skipped (alias): {skipped_not_principal:,}")
    print(f"  Skipped (units/flats): {skipped_units:,}")
    print(f"  Skipped (no address): {skipped_no_address:,}")
    print(f"  Eligible houses: {len(eligible):,}")

    return eligible


def sample_diverse(eligible, target_count):
    """
    Sample addresses ensuring suburb diversity.
    Take equal numbers from each suburb, then fill remaining randomly.
    """
    by_suburb = defaultdict(list)
    for addr in eligible:
        by_suburb[addr["suburb"]].append(addr)

    suburbs = list(by_suburb.keys())
    random.shuffle(suburbs)

    # Calculate addresses per suburb (round robin)
    per_suburb = max(1, target_count // len(suburbs))
    sampled = []

    for suburb in suburbs:
        pool = by_suburb[suburb]
        take = min(per_suburb, len(pool))
        sampled.extend(random.sample(pool, take))

    # If we need more, random fill from remaining
    if len(sampled) < target_count:
        used = set(a["address"] for a in sampled)
        remaining = [a for a in eligible if a["address"] not in used]
        random.shuffle(remaining)
        sampled.extend(remaining[: target_count - len(sampled)])

    # If we have too many, trim
    if len(sampled) > target_count:
        sampled = random.sample(sampled, target_count)

    return sampled


def main():
    random.seed(42)  # Reproducible sampling

    all_sampled = []

    for city in ["brisbane", "sydney", "melbourne"]:
        eligible = process_city(city)

        if len(eligible) < TARGET_PER_CITY:
            print(f"\n  WARNING: Only {len(eligible)} eligible addresses for {city}")
            print(f"  Will use all of them.")
            sampled = eligible
        else:
            sampled = sample_diverse(eligible, TARGET_PER_CITY)

        # Report suburb diversity
        suburbs = set(a["suburb"] for a in sampled)
        print(f"\n  Sampled: {len(sampled)} addresses across {len(suburbs)} suburbs")

        all_sampled.extend(sampled)

    # Shuffle the final list (mix cities together for capture)
    random.shuffle(all_sampled)

    # Slim down the output (only fields needed by capture script)
    output = [
        {"address": a["address"], "suburb": a["suburb"], "city": a["city"]}
        for a in all_sampled
    ]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n=== DONE ===")
    print(f"Total sampled: {len(output)}")
    print(f"Output: {OUTPUT_FILE}")

    # Per-city breakdown
    from collections import Counter
    city_counts = Counter(a["city"] for a in output)
    for city, count in sorted(city_counts.items()):
        print(f"  {city}: {count}")


if __name__ == "__main__":
    main()
