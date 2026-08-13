#!/usr/bin/env python3
"""test_onthehouse_match.py — the matcher's regression suite.

Every case here is one that has actually occurred in the sitemap or our own address data.
Run this before any --apply. No network, no database.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onthehouse_match import key_of, slug_keys, norm_street      # noqa: E402

FAIL = []


def eq(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"          got  {got}\n          want {want}")
        FAIL.append(label)


def match(label, ours, slug, sub, should):
    k = key_of(ours, sub)
    ks = slug_keys(slug, sub)
    got = k in ks
    ok = got == should
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"          ours {k}\n          slug {ks}\n          matched={got} expected={should}")
        FAIL.append(label)


print("=== the collision that corrupted an early sampler ===")
match("building must NOT match its apartment",
      "4608/61 Investigator Dr", "61-investigator-drive-robina", "robina", False)
match("apartment matches its own slug",
      "4608/61 Investigator Dr", "4608-61-investigator-drive-robina", "robina", True)

print("\n=== verified positive ===")
match("plain unit", "1/1 ACACIA COURT ROBINA QLD 4226", "1-1-acacia-ct-robina", "robina", True)
match("plain house", "37 Kidman St, Robina", "37-kidman-st-robina", "robina", True)

print("\n=== ranged street numbers ===")
match("unit at a ranged number",
      "112/2-4 Riverwalk Ave, Robina", "112-2-4-riverwalk-ave-robina", "robina", True)
match("double-dash range (unit 7 at 8-14)",
      "7/8-14 St Ives Dr, Robina", "7-8--14-st-ives-dr-robina", "robina", True)
match("double-dash range, glenferrie",
      "1/34-38 Glenferrie Dr, Robina", "1-34--38-glenferrie-dr-robina", "robina", True)
match("ranged number, no unit",
      "2-4 Riverwalk Ave, Robina", "2-4-riverwalk-ave-robina", "robina", True)
match("unit 2 at number 4 also reads that slug (ambiguous; page decides)",
      "2/4 Riverwalk Ave, Robina", "2-4-riverwalk-ave-robina", "robina", True)

print("\n=== saint / st ===")
eq("SAINT IVES DRIVE == ST IVES DR",
   norm_street("SAINT IVES DRIVE"), norm_street("St Ives Dr"))
match("ours 'ST IVES', theirs 'saint-ives'",
      "30 ST IVES DRIVE ROBINA QLD 4226", "30-saint-ives-dr-robina", "robina", True)
match("ours 'ST JOHN', theirs 'saint-john'",
      "15 St John Court, Robina", "15-saint-john-ct-robina", "robina", True)
eq("trailing 'St' still means Street, not Saint",
   norm_street("Ives St"), "ives-st")

print("\n=== street-type spelling ===")
for a, b in [("Brooklyn Crescent", "brooklyn-cres"), ("Brooklyn Cr", "brooklyn-cres"),
             ("Sunrise Trail", "sunrise-trl"), ("Robina Parkway", "robina-pkwy"),
             ("The Quay", "the-qy"), ("Serenity Point", "serenity-pnt"),
             ("Laurel Oak Drive", "laurel-oak-dr"), ("Highgate Lane", "highgate-ln")]:
    eq(f"{a!r} -> {b}", norm_street(a), b)
match("Cr vs Cres end to end",
      "32 Brooklyn Cr, Robina", "32-brooklyn-cres-robina", "robina", True)

print("\n=== must NOT match ===")
match("different street type is a different street",
      "12 Ives St, Robina", "12-ives-dr-robina", "robina", False)
match("different street number",
      "13 Kidman St, Robina", "37-kidman-st-robina", "robina", False)
match("unit vs no-unit never collide",
      "2 Georgia St, Varsity Lakes", "2-2-georgia-st-varsity-lakes", "varsity_lakes", False)

print("\n=== unaddressable slugs yield no key ===")
eq("lot-880 has no street number", slug_keys("lot-880-ron-penhaligon-way-robina", "robina"), [])
eq("street-only stub", slug_keys("heights-dr-robina", "robina"), [])

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): " + ", ".join(FAIL))
    sys.exit(1)
print("all matcher tests passed")
