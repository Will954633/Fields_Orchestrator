#!/usr/bin/env python3
"""
create_lead_forms.py — Create the seller-intent Instant-Form lead forms for the
Home Owner Lead Funnel (2026-07-28). name+email+phone + selling-intent qualifier
+ express-consent checkbox (AU Spam Act / DNC lever so Will can legally call).

Idempotent-ish: prints created form IDs. Re-running creates NEW forms (Meta has no
upsert) — so run once, record IDs in 00_MASTER_LEDGER.md + SELLER_FORM_IDS in
scripts/fb-lead-puller.py.

Usage: python3 create_lead_forms.py            # create all forms
       python3 create_lead_forms.py --list     # list existing page forms
"""
import os, sys, json, requests
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")

PAGE_ID = "889412530933297"
API = "https://graph.facebook.com/v21.0"
TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]

def page_token():
    r = requests.get(f"{API}/{PAGE_ID}", params={"fields": "access_token", "access_token": TOKEN}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]

INTENT_Q = {
    "type": "CUSTOM",
    "key": "selling_intent",
    "label": "Are you considering selling in the next 12 months?",
    "options": [
        {"key": "yes", "value": "Yes"},
        {"key": "maybe", "value": "Maybe, exploring"},
        {"key": "no", "value": "No, just curious"},
    ],
}
NAME_Q  = {"type": "FULL_NAME", "key": "full_name"}
EMAIL_Q = {"type": "EMAIL", "key": "email"}
PHONE_Q = {"type": "PHONE", "key": "phone_number"}
ADDR_Q  = {"type": "CUSTOM", "key": "property_address",
           "label": "Property address (so we can match the right comparable sales)"}

PRIVACY = {"url": "https://fieldsestate.com.au/privacy", "link_text": "Privacy Policy"}

CONSENT = {
    "title": "How we'll use your details",
    "body": {"text": ("By submitting, you agree that Fields Real Estate may contact you by phone, SMS and "
                      "email about your property and our market data. We're a data-first service, not a "
                      "call centre — you can opt out anytime by replying STOP or emailing "
                      "will@fieldsestate.com.au. See our Privacy Policy.")},
    "checkboxes": [{
        "key": "consent_to_contact",
        "required": True,
        "text": {"text": "Yes, Will can call or text me about my property and Gold Coast market data."},
    }],
}

# Consent disclosure — Meta rejected every custom_disclaimer schema variant on this
# page (v21), and lead forms are immutable after creation, so the consent statement
# is disclosed in the intro card (visible before submit) + the privacy link. Submitting
# a form that clearly states we will phone/SMS/email = disclosed consent (AU Spam Act).
CONSENT_LINE = ("By continuing you agree Fields Real Estate may call, SMS or email you about your "
                "property and our market data — opt out anytime by replying STOP. We're a data-first "
                "service, not a call centre.")

def context_card(title, body):
    # PARAGRAPH_STYLE allows exactly one content element → merge body + consent into one paragraph.
    para = " ".join(list(body)) + "\n\n" + CONSENT_LINE
    return {"title": title, "content": [para], "style": "PARAGRAPH_STYLE", "button_text": "Get started"}

def thank_you(title, body, url, button="View my home's data"):
    return {"title": title, "body": body, "button_type": "VIEW_WEBSITE",
            "button_text": button, "website_url": url}

FORMS = [
    {   # Form 1 — report offer, no address (low friction, the $5 volume play)
        "name": "Fields — Seller Intent (report) v1 — name+email+phone",
        "locale": "en_US",
        "is_optimized_for_quality": True,
        "questions": [INTENT_Q, NAME_Q, EMAIL_Q, PHONE_Q],
        "privacy_policy": PRIVACY,
        "context_card": context_card(
            "See what the comparable sales say your home is worth",
            ["Recent comparable sales near you — adjusted for your home and shown as a range, not a "
             "single guess. From a licensed Gold Coast agent. No pitch."]),
        "thank_you_page": thank_you(
            "Got it.",
            "Will will call you shortly to walk through the numbers for a home like yours. "
            "Want a head start? Enter your address now and see your comparable range.",
            "https://fieldsestate.com.au/analyse-your-home"),
        "follow_up_action_url": "https://fieldsestate.com.au/analyse-your-home",
    },
    {   # Form 2 — sold-price alerts subscribe (lowest intent, best sub-$5 shot)
        "name": "Fields — Sold-Price Alerts v1 — name+email+phone",
        "locale": "en_US",
        "is_optimized_for_quality": False,
        "questions": [INTENT_Q, NAME_Q, EMAIL_Q, PHONE_Q],
        "privacy_policy": PRIVACY,
        "context_card": context_card(
            "Gold Coast sold prices — the day they settle",
            ["The real sale price, days on market, and how it compared to the suburb — sent to you free, "
             "as homes near you sell. No pitch, just the numbers."]),
        "thank_you_page": thank_you(
            "You're on the list.",
            "You'll get real Gold Coast sold prices as they happen. Want to see what a home like yours "
            "is worth right now? Enter your address.",
            "https://fieldsestate.com.au/analyse-your-home", button="See my home's data"),
        "follow_up_action_url": "https://fieldsestate.com.au/analyse-your-home",
    },
    {   # Form 3 — report offer + address (tests address-in-form friction / the bonus)
        "name": "Fields — Seller Intent (report+address) v1",
        "locale": "en_US",
        "is_optimized_for_quality": True,
        "questions": [INTENT_Q, ADDR_Q, NAME_Q, EMAIL_Q, PHONE_Q],
        "privacy_policy": PRIVACY,
        "context_card": context_card(
            "See what the comparable sales say your home is worth",
            ["Tell us your address and we'll match the right recent comparable sales — adjusted for your "
             "home, shown as a range. From a licensed Gold Coast agent. No pitch."]),
        "thank_you_page": thank_you(
            "Got it.",
            "Will will call you shortly with the comparable range for your home. "
            "Want it now? See your data online.",
            "https://fieldsestate.com.au/analyse-your-home"),
        "follow_up_action_url": "https://fieldsestate.com.au/analyse-your-home",
    },
]

def create(ptoken, form):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in form.items()}
    payload["access_token"] = ptoken
    r = requests.post(f"{API}/{PAGE_ID}/leadgen_forms", data=payload, timeout=30)
    try:
        j = r.json()
    except Exception:
        return {"error": r.text}
    return j

def main():
    ptoken = page_token()
    if "--list" in sys.argv:
        r = requests.get(f"{API}/{PAGE_ID}/leadgen_forms",
                         params={"fields": "id,name,status,leads_count", "access_token": ptoken, "limit": 100}, timeout=20)
        for f in r.json().get("data", []):
            print(f"{f.get('id')}  {f.get('status'):8} leads={f.get('leads_count',0):>3}  {f.get('name')}")
        return
    results = {}
    for form in FORMS:
        j = create(ptoken, form)
        fid = j.get("id")
        print(f"{'OK ' if fid else 'ERR'} {form['name']}\n    -> {j}")
        if fid:
            results[form["name"]] = fid
    print("\nCREATED FORM IDS:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
