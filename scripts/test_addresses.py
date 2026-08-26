#!/usr/bin/env python3
"""
test_addresses.py — the single registry of Will's own test addresses.

Will exercises the full lead + report + activity workflow end-to-end against a
handful of real addresses. Anything keyed to one of them is OUR OWN QA, never a
real lead, and must never reach the Live Leads Tracker ("All Leads" or "Activity"
tabs), the scored `lead_worklist`, or the direct-call list.

Block on the ADDRESS, not on a PostHog / device id: Will tests from several
devices (different distinct_ids, different mobile IPs), so ids rotate but the
address is the one stable key. `is_test_address()` normalises any address string
OR url-slug to the same slug form (state + postcode dropped, matching the
`url_slug` convention already used across Gold_Coast) and checks membership.

To add another test address: add its slug here. Every generator imports this set,
so there is exactly one place to edit.
"""
from __future__ import annotations
import re

# url-slug form: "<number> <street> <suburb>", state + postcode dropped.
TEST_ADDRESS_SLUGS = {
    "7-huntingdale-crescent-robina",
    "27-huntingdale-crescent-robina",   # Will's primary test address (2026-08-26)
    "5-fulham-place-robina",
}


def address_to_slug(text: str | None) -> str:
    """Normalise an address string OR an existing slug to the canonical slug.

    "27 Huntingdale Crescent, Robina QLD 4226" -> "27-huntingdale-crescent-robina"
    "27-huntingdale-crescent-robina"           -> "27-huntingdale-crescent-robina"
    """
    if not text:
        return ""
    t = text.strip().lower()
    # drop a trailing state / postcode tail ("... , robina qld 4226")
    t = re.sub(r"[,\s]+(qld|queensland|nsw|vic|act|sa|wa|nt|tas)\b.*$", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t


def is_test_address(*texts: str | None) -> bool:
    """True if ANY of the given address strings / slugs is one of Will's test
    addresses. Accepts several so a caller can pass (slug, address) together."""
    return any(address_to_slug(t) in TEST_ADDRESS_SLUGS for t in texts if t)
