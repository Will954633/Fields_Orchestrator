#!/usr/bin/env python3
"""
GPT-based property listing verifier.

Called as a fallback when rule-based address verification cannot determine
whether a scraped page is actually about the target property. Parses the
visible page text with an LLM and returns the page's real address and
listing status.
"""

import os
import json
from openai import AsyncOpenAI

MODEL = "gpt-5-nano-2025-08-07"

_client = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def gpt_verify_listing(
    gis_address: str,
    page_title: str,
    visible_text: str,
) -> dict | None:
    """
    Ask GPT to identify the property address and listing status from page content.

    Args:
        gis_address:  The address we are trying to confirm (GIS source).
        page_title:   The HTML page title.
        visible_text: Scraped visible text from the page.

    Returns:
        Dict with keys:
            'page_address'   – the specific address the page is about, or None
                               if the page is a generic search/agency page.
            'listing_status' – one of: for_sale | sold | leased | unknown
        Or None if the API call fails.
    """
    # Trim content to keep costs low — title + first 3000 chars is enough
    content_snippet = visible_text[:3000].strip()

    prompt = (
        f"You are analysing a real estate website page.\n\n"
        f"I am looking for information about: {gis_address}\n\n"
        f"Page title: {page_title}\n\n"
        f"Page content:\n{content_snippet}\n\n"
        f"Answer with JSON only, no explanation:\n"
        f'{{\n'
        f'  "page_address": "the specific property address this page is listing, '
        f'or null if this is a search results or generic agency page",\n'
        f'  "listing_status": "for_sale or sold or leased or unknown"\n'
        f'}}'
    )

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,
        )
        raw = response.choices[0].message.content or ""
        # Extract JSON block from response (reasoning models may include preamble)
        json_start = raw.find('{')
        json_end = raw.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError(f"No JSON in response: {raw[:100]}")
        result = json.loads(raw[json_start:json_end])
        # Normalise
        page_address = (result.get("page_address") or "").strip() or None
        listing_status = (result.get("listing_status") or "unknown").strip().lower()
        if listing_status not in ("for_sale", "sold", "leased", "unknown"):
            listing_status = "unknown"
        return {"page_address": page_address, "listing_status": listing_status}
    except Exception as e:
        print(f"      [GPT error: {str(e)[:80]}]")
        return None


async def gpt_extract_listing(
    page_title: str,
    visible_text: str,
    target_suburb: str = "Robina",
) -> dict | None:
    """
    Ask GPT to extract full property details from a listing page.
    Used as a fallback when rule-based extraction fails to determine
    address, suburb, or listing status.

    Returns:
        Dict with keys: page_address, suburb, listing_status, bedrooms,
        bathrooms, carspaces, sale_price, property_type
        Or None if the API call fails.
    """
    content_snippet = visible_text[:3000].strip()

    prompt = (
        f"You are analysing a real estate listing page.\n"
        f"I need to know if this is a property in {target_suburb}.\n\n"
        f"Page title: {page_title}\n\n"
        f"Page content:\n{content_snippet}\n\n"
        f"Extract the property details. Answer with JSON only, no explanation:\n"
        f'{{\n'
        f'  "page_address": "full street address of the property, or null if '
        f'this is a search results page or not a single property listing",\n'
        f'  "suburb": "the suburb name, or null if unclear",\n'
        f'  "listing_status": "for_sale or sold or leased or unknown",\n'
        f'  "bedrooms": number or null,\n'
        f'  "bathrooms": number or null,\n'
        f'  "carspaces": number or null,\n'
        f'  "sale_price": "price string like $1,200,000 or null if not shown",\n'
        f'  "property_type": "house or apartment or townhouse or duplex or land or null"\n'
        f'}}'
    )

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,
        )
        raw = response.choices[0].message.content or ""
        json_start = raw.find('{')
        json_end = raw.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError(f"No JSON in response: {raw[:100]}")
        result = json.loads(raw[json_start:json_end])

        # Normalise
        page_address = (result.get("page_address") or "").strip() or None
        suburb = (result.get("suburb") or "").strip() or None
        listing_status = (result.get("listing_status") or "unknown").strip().lower()
        if listing_status not in ("for_sale", "sold", "leased", "unknown"):
            listing_status = "unknown"

        # Normalise numeric fields
        bedrooms = result.get("bedrooms")
        bathrooms = result.get("bathrooms")
        carspaces = result.get("carspaces")
        if isinstance(bedrooms, str):
            bedrooms = int(bedrooms) if bedrooms.isdigit() else None
        if isinstance(bathrooms, str):
            bathrooms = int(bathrooms) if bathrooms.isdigit() else None
        if isinstance(carspaces, str):
            carspaces = int(carspaces) if carspaces.isdigit() else None

        return {
            "page_address": page_address,
            "suburb": suburb,
            "listing_status": listing_status,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "carspaces": carspaces,
            "sale_price": (result.get("sale_price") or "").strip() or None,
            "property_type": (result.get("property_type") or "").strip().lower() or None,
        }
    except Exception as e:
        print(f"      [GPT extract error: {str(e)[:80]}]")
        return None
