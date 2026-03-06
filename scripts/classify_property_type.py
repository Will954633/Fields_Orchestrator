#!/usr/bin/env python3
"""
Classify property dwelling type from photos using GPT nano vision.

Writes `classified_property_type` and `classification_confidence` fields
to each property document. Downstream systems (FB posts, website, articles)
should read `classified_property_type` instead of Domain's `property_type`.

Usage:
    python3 scripts/classify_property_type.py                # Process all unclassified
    python3 scripts/classify_property_type.py --force         # Re-classify everything
    python3 scripts/classify_property_type.py --dry-run       # Preview without writing
    python3 scripts/classify_property_type.py --limit 5       # Process N properties
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv("/home/fields/Fields_Orchestrator/.env")
load_dotenv("/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = "gpt-4o-mini"  # Cheapest vision model, sufficient for classification

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]

VALID_TYPES = [
    "House",
    "Townhouse",
    "Unit/Apartment",
    "Duplex/Semi-Detached",
    "Villa",
    "Retirement Living",
    "Vacant Land",
]

CLASSIFICATION_PROMPT = """You are a property type classifier for Australian real estate.

Look at this property photo and classify the dwelling type into exactly ONE of these categories:
- House (standalone detached dwelling on its own lot)
- Townhouse (attached dwelling, usually 2+ storeys, shared walls)
- Unit/Apartment (part of a larger complex/building, typically with common areas)
- Duplex/Semi-Detached (two dwellings sharing a common wall)
- Villa (single-storey attached dwelling, often in a small complex)
- Retirement Living (purpose-built retirement village unit)
- Vacant Land (empty lot, no dwelling)

Also consider these clues:
- Unit numbers in the address (e.g. "3/45") suggest Unit/Apartment or Townhouse
- Driveways shared with identical buildings suggest Townhouse or Duplex
- Large front yards with no adjoining structures suggest House
- Multi-storey buildings with balconies and common entry suggest Unit/Apartment

Respond with ONLY a JSON object (no markdown):
{"type": "<category>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}"""


def query_with_retry(collection, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return collection.find(*args, **kwargs)
        except OperationFailure as e:
            if "TooManyRequests" in str(e) or "16500" in str(e):
                wait = (attempt + 1) * 2
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    return collection.find(*args, **kwargs)


def download_and_encode_image(url):
    """Download image and return base64 data URI. Handles Domain CDN redirects."""
    try:
        resp = requests.get(url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        b64 = base64.b64encode(resp.content).decode("utf-8")
        return f"data:{content_type};base64,{b64}"
    except requests.RequestException as e:
        return None


def classify_image(image_url, address=""):
    """Send image to GPT vision and get classification."""
    prompt = CLASSIFICATION_PROMPT
    if address:
        prompt += f"\n\nThe property address is: {address}"

    # Download and encode image to avoid CDN access issues
    data_uri = download_and_encode_image(image_url)
    if not data_uri:
        return None, 0, f"Could not download image: {image_url[:80]}"

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_uri, "detail": "low"},
                            },
                        ],
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.1,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON from response (handle markdown wrapping)
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(content)
        prop_type = result.get("type", "").strip()
        confidence = float(result.get("confidence", 0))
        reasoning = result.get("reasoning", "")

        # Validate type
        if prop_type not in VALID_TYPES:
            # Try fuzzy match
            for vt in VALID_TYPES:
                if prop_type.lower() in vt.lower() or vt.lower() in prop_type.lower():
                    prop_type = vt
                    break
            else:
                return None, 0, f"Unknown type: {prop_type}"

        return prop_type, confidence, reasoning

    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        return None, 0, f"Error: {e}"


def get_image_urls(doc, max_images=3):
    """Get up to max_images URLs for classification. First image is the hero shot."""
    images = doc.get("property_images", [])
    urls = []
    for img in images[:max_images]:
        url = img.get("url", "") if isinstance(img, dict) else img
        if url:
            urls.append(url)
    return urls


def main():
    parser = argparse.ArgumentParser(description="Classify property types from photos")
    parser.add_argument("--force", action="store_true", help="Re-classify already-classified properties")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--limit", type=int, default=0, help="Max properties to process (0 = all)")
    parser.add_argument("--suburbs", nargs="*", default=TARGET_SUBURBS, help="Suburbs to process")
    parser.add_argument("--no-fail", action="store_true", help="Exit 0 even on errors (for pipeline use)")
    args = parser.parse_args()

    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]

    total_processed = 0
    total_classified = 0
    total_skipped = 0
    total_errors = 0
    changes = []  # Track type changes for summary

    for suburb in args.suburbs:
        coll = db[suburb]

        # Build query
        query = {"listing_status": "for_sale"}
        if not args.force:
            query["classified_property_type"] = {"$exists": False}

        try:
            docs = list(query_with_retry(coll, query, {
                "property_images": 1,
                "property_type": 1,
                "street_address": 1,
                "address": 1,
                "complete_address": 1,
            }))
        except Exception as e:
            print(f"  {suburb}: Error querying: {e}")
            continue

        if not docs:
            print(f"  {suburb}: No unclassified properties")
            continue

        if args.limit and total_processed + len(docs) > args.limit:
            docs = docs[: args.limit - total_processed]

        print(f"  {suburb}: {len(docs)} properties to classify")

        for doc in docs:
            image_urls = get_image_urls(doc, max_images=3)
            if not image_urls:
                total_skipped += 1
                continue

            address = doc.get("street_address") or doc.get("address") or doc.get("complete_address") or ""

            # Try first image (hero shot)
            prop_type, confidence, reasoning = classify_image(image_urls[0], address)

            # If low confidence and we have more images, retry with second image
            if prop_type and confidence < 0.85 and len(image_urls) > 1:
                prop_type2, confidence2, reasoning2 = classify_image(image_urls[1], address)
                if prop_type2 and confidence2 > confidence:
                    prop_type, confidence, reasoning = prop_type2, confidence2, reasoning2
                elif prop_type2 and prop_type2 == prop_type:
                    # Both agree — boost confidence
                    confidence = min(0.95, confidence + 0.1)

            if prop_type is None:
                print(f"    SKIP {address}: {reasoning}")
                total_errors += 1
                continue

            domain_type = doc.get("property_type", "Unknown")
            # Normalize Domain labels for comparison (they use different names)
            DOMAIN_TO_OUR_LABEL = {
                "Apartment / Unit / Flat": "Unit/Apartment",
                "Semi-Detached": "Duplex/Semi-Detached",
            }
            domain_normalized = DOMAIN_TO_OUR_LABEL.get(domain_type, domain_type)
            changed = prop_type != domain_normalized
            marker = " *CHANGED*" if changed else ""

            print(f"    {address}: {domain_type} -> {prop_type} ({confidence:.0%}){marker}")

            if changed:
                changes.append({
                    "address": address,
                    "suburb": suburb,
                    "domain_type": domain_type,
                    "classified_type": prop_type,
                    "confidence": confidence,
                    "reasoning": reasoning,
                })

            if not args.dry_run:
                try:
                    coll.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "classified_property_type": prop_type,
                            "classification_confidence": confidence,
                            "classification_reasoning": reasoning,
                            "classification_model": OPENAI_MODEL,
                            "classified_at": datetime.now(timezone.utc),
                        }},
                    )
                except OperationFailure as e:
                    if "TooManyRequests" in str(e):
                        time.sleep(3)
                        coll.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {
                                "classified_property_type": prop_type,
                                "classification_confidence": confidence,
                                "classification_reasoning": reasoning,
                                "classification_model": OPENAI_MODEL,
                                "classified_at": datetime.now(timezone.utc),
                            }},
                        )
                    else:
                        raise

            total_classified += 1
            total_processed += 1

            # Rate limit: ~2 requests/sec to stay within OpenAI limits
            time.sleep(0.5)

            if args.limit and total_processed >= args.limit:
                break

        if args.limit and total_processed >= args.limit:
            break

    # Summary
    print(f"\nDone: {total_classified} classified, {total_skipped} skipped (no images), {total_errors} errors")
    if changes:
        print(f"\n{len(changes)} properties where classification differs from Domain:")
        for c in changes:
            print(f"  {c['address']} ({c['suburb']}): {c['domain_type']} -> {c['classified_type']} ({c['confidence']:.0%}) — {c['reasoning']}")

    client.close()

    if total_errors > 0 and not args.no_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
