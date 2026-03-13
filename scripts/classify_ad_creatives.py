#!/usr/bin/env python3
"""
Classify Ad Creatives — uses Claude vision to analyze Facebook ad images.

For each ad, downloads the creative image and asks Claude to classify:
  - image_category: property_photo, data_chart, lifestyle_photo, aerial, infographic, text_overlay, mixed
  - image_subject: what's actually in the image (1-2 sentences)
  - text_in_image: any text visible in the image
  - visual_style: professional_photo, screenshot, designed_graphic, stock_photo, user_generated
  - color_dominant: primary color palette
  - emotional_tone: analytical, aspirational, urgent, informational, storytelling

Writes results back to ad_profiles.creative.image_analysis field.

Usage:
    python3 scripts/classify_ad_creatives.py              # Classify unanalyzed ads
    python3 scripts/classify_ad_creatives.py --force       # Re-classify all
    python3 scripts/classify_ad_creatives.py --id <AD_ID>  # Single ad
    python3 scripts/classify_ad_creatives.py --dry-run     # Preview without saving
    python3 scripts/classify_ad_creatives.py --limit 5     # Process N ads
"""

import os
import sys
import json
import time
import base64
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

# Fallback to OpenAI if no Anthropic key
OPENAI_API_KEY = ""
try:
    load_dotenv("/home/fields/Property_Data_Scraping/03_Gold_Coast/"
                "Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/"
                "Ollama_Property_Analysis/.env", override=True)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
except Exception:
    pass


def classify_with_claude(image_url, ad_name, ad_body, timeout=30):
    """Send image to Claude for classification."""
    # Download image
    try:
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("content-type", "image/jpeg")
    except Exception as e:
        return {"error": f"Failed to download image: {e}"}

    prompt = f"""Analyze this Facebook ad image. The ad is named "{ad_name}".
Ad text (if any): "{ad_body[:300] if ad_body else '[no text]'}"

Classify the image with these fields (respond with JSON only, no markdown):
{{
  "image_category": one of: "property_photo", "data_chart", "lifestyle_photo", "aerial_photo", "infographic", "text_overlay", "designed_graphic", "mixed",
  "image_subject": 1-2 sentence description of what's in the image,
  "text_in_image": any text visible in the image (empty string if none),
  "visual_style": one of: "professional_photo", "screenshot", "designed_graphic", "stock_photo", "data_visualization", "map",
  "color_dominant": primary 1-2 colors (e.g. "blue, white"),
  "emotional_tone": one of: "analytical", "aspirational", "urgent", "informational", "storytelling", "curiosity"
}}"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 500,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        },
        timeout=timeout,
    )

    if resp.status_code != 200:
        return {"error": f"Claude API {resp.status_code}: {resp.text[:200]}"}

    data = resp.json()
    text = data.get("content", [{}])[0].get("text", "")

    # Parse JSON from response
    try:
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": f"Failed to parse JSON: {text[:200]}", "raw": text}


def classify_with_openai(image_url, ad_name, ad_body, timeout=30):
    """Fallback: use GPT-4o-mini for classification."""
    # Download image first — FB CDN URLs have temp auth tokens that OpenAI can't access
    try:
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("content-type", "image/jpeg")
        data_url = f"data:{media_type};base64,{img_b64}"
    except Exception as e:
        return {"error": f"Failed to download image: {e}"}

    prompt = f"""Analyze this Facebook ad image. The ad is named "{ad_name}".
Ad text (if any): "{ad_body[:300] if ad_body else '[no text]'}"

Classify the image with these fields (respond with JSON only, no markdown):
{{
  "image_category": one of: "property_photo", "data_chart", "lifestyle_photo", "aerial_photo", "infographic", "text_overlay", "designed_graphic", "mixed",
  "image_subject": 1-2 sentence description of what's in the image,
  "text_in_image": any text visible in the image (empty string if none),
  "visual_style": one of: "professional_photo", "screenshot", "designed_graphic", "stock_photo", "data_visualization", "map",
  "color_dominant": primary 1-2 colors (e.g. "blue, white"),
  "emotional_tone": one of: "analytical", "aspirational", "urgent", "informational", "storytelling", "curiosity"
}}"""

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 500,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
        },
        timeout=timeout,
    )

    if resp.status_code != 200:
        return {"error": f"OpenAI API {resp.status_code}: {resp.text[:200]}"}

    data = resp.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": f"Failed to parse JSON: {text[:200]}", "raw": text}


def classify_image(image_url, ad_name, ad_body):
    """Classify an image using available API (Claude preferred, OpenAI fallback)."""
    if ANTHROPIC_API_KEY:
        result = classify_with_claude(image_url, ad_name, ad_body)
        if not result.get("error"):
            result["model"] = "claude-haiku-4-5"
            return result
        print(f"    Claude failed: {result['error'][:80]}, trying OpenAI...")

    if OPENAI_API_KEY:
        result = classify_with_openai(image_url, ad_name, ad_body)
        if not result.get("error"):
            result["model"] = "gpt-4o-mini"
            return result
        print(f"    OpenAI failed: {result['error'][:80]}")

    return {"error": "No working vision API available"}


def main():
    parser = argparse.ArgumentParser(description="Classify Ad Creatives")
    parser.add_argument("--force", action="store_true", help="Re-classify all ads")
    parser.add_argument("--id", type=str, help="Classify single ad")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--limit", type=int, default=0, help="Process N ads")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY and not OPENAI_API_KEY:
        print("ERROR: No ANTHROPIC_API_KEY or OPENAI_API_KEY found")
        sys.exit(1)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Ad Creative Classifier starting...")
    print(f"  Using: {'Claude Haiku' if ANTHROPIC_API_KEY else 'GPT-4o-mini'}")

    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]

    # Get ads to classify
    if args.id:
        profiles = [sm["ad_profiles"].find_one({"_id": args.id})]
        if not profiles[0]:
            print(f"Ad {args.id} not found")
            return
    elif args.force:
        profiles = list(sm["ad_profiles"].find())
    else:
        # Only ads without image_analysis
        profiles = list(sm["ad_profiles"].find({
            "creative.image_analysis": {"$exists": False}
        }))
        # Also include ads where image_analysis has an error
        error_profiles = list(sm["ad_profiles"].find({
            "creative.image_analysis.error": {"$exists": True}
        }))
        profiles.extend(error_profiles)

    if args.limit > 0:
        profiles = profiles[:args.limit]

    print(f"  {len(profiles)} ads to classify")

    classified = 0
    errors = 0

    for i, p in enumerate(profiles):
        ad_id = p["_id"]
        name = p.get("name", "?")[:55]
        creative = p.get("creative", {})
        image_url = creative.get("image_url", "")
        body = creative.get("body", "")

        if not image_url:
            print(f"  [{i+1}/{len(profiles)}] {name} — no image URL, skipping")
            continue

        print(f"  [{i+1}/{len(profiles)}] {name}...")

        result = classify_image(image_url, name, body)

        if result.get("error"):
            print(f"    ERROR: {result['error'][:80]}")
            errors += 1
        else:
            print(f"    Category: {result.get('image_category', '?')} | "
                  f"Style: {result.get('visual_style', '?')} | "
                  f"Tone: {result.get('emotional_tone', '?')}")
            print(f"    Subject: {result.get('image_subject', '?')[:80]}")
            classified += 1

        result["classified_at"] = datetime.now(timezone.utc).isoformat()

        if not args.dry_run:
            sm["ad_profiles"].update_one(
                {"_id": ad_id},
                {"$set": {"creative.image_analysis": result}}
            )
            time.sleep(0.5)  # Rate limit

    print(f"\nDone. Classified: {classified}, Errors: {errors}")
    client.close()


if __name__ == "__main__":
    main()
