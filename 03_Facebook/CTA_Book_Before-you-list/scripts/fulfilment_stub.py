#!/usr/bin/env python3
"""
fulfilment_stub.py — ready-to-wire branch for the "Before You List" printed-book offer.

This is NOT run standalone. It shows exactly what to add to scripts/fb-lead-puller.py
(the existing live poller that already: polls active lead forms -> dedupes into
system_monitor.fb_leads -> Telegram -> CRM). The offer is PHYSICAL-ONLY: a printed
hardcover is posted; there is no digital PDF.

Wire it once the Instant Form exists in Ads Manager:
  1) Put the new form's ID in BEFORE_YOU_LIST_FORM_IDS.
  2) In fb-lead-puller.py, after a new lead is written, call fulfil_before_you_list(lead).
  3) The lead's field answers arrive as a name->value dict (Meta field names).
"""

BEFORE_YOU_LIST_FORM_IDS = {
    # "REPLACE_WITH_META_FORM_ID": "before_you_list",
}
CORE_POSTCODES = {"4220", "4226", "4227"}  # Burleigh Waters, Robina, Varsity Lakes


def fulfil_before_you_list(lead, *, sm_db, telegram, adset_arm):
    """
    lead:       dict of the lead's field answers (name, email, mobile, address) + ad_id/adset_id.
    sm_db:      system_monitor database handle (already open in fb-lead-puller).
    telegram:   the existing notify helper.
    adset_arm:  callable(adset_id) -> "A" | "B" | "C" (for measurement tagging).
    Returns the queue doc written (or None if not a BYL form).
    """
    form_id = str(lead.get("form_id") or "")
    if form_id not in BEFORE_YOU_LIST_FORM_IDS:
        return None

    name    = (lead.get("full_name") or lead.get("name") or "").strip()
    email   = (lead.get("email") or "").strip()
    mobile  = (lead.get("mobile") or lead.get("phone_number") or "").strip()
    address = (lead.get("street_address") or lead.get("address") or "").strip()
    arm     = adset_arm(lead.get("adset_id"))

    # Address sanity check — a mailed hardcover has a real per-unit cost, so junk
    # addresses should NOT auto-dispatch. Flag anything without a plausible postcode.
    postcode = next((m for m in __import__("re").findall(r"\b(\d{4})\b", address)), None)
    needs_review = (not address) or (postcode not in CORE_POSTCODES and postcode is not None and False) or (postcode is None)

    doc = {
        "book": "before_you_list",
        "campaign": "before_you_list",
        "arm": arm,                       # A | B | C  (winner analysis)
        "name": name, "email": email, "mobile": mobile, "address": address,
        "status": "needs_review" if needs_review else "queued_for_post",
        "source_form_id": form_id,
        # "created_at": <ISO ts>,        # stamp with your existing time helper
    }
    sm_db["print_post_queue"].insert_one(doc)

    # Dispatch confirmation to the lead (sets postal-timing expectation). Reuse the
    # existing AYH fulfilment email path; physical-only, so no PDF link.
    # send_confirmation_email(email, name)   # <- wire to existing mailer

    flag = " ⚠ REVIEW ADDRESS" if needs_review else ""
    telegram(f"📕 Before You List lead (arm {arm}): {name} — {address or 'NO ADDRESS'}{flag}")
    return doc
