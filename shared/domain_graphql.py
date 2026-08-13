#!/usr/bin/env python3
"""
Domain.com.au GraphQL helper — queries Domain's own undocumented Apollo backend
at https://www.domain.com.au/graphql, routed through Bright Data Web Unlocker.

Why this exists (see also shared/domain_fetch.py):
    The HTML path costs one Web Unlocker request per search page PLUS one per
    listing, and Domain moved the sale-search page off __NEXT_DATA__ in 2026-07 so
    discovery now unions ld+json with anchor hrefs and re-fetches pages that
    under-render. The GraphQL endpoint returns the same data as structured JSON:
    `search_listings()` returns a whole suburb's listings in one request.

    It also exposes two things the HTML scrape does not surface cleanly:
      - property.valuation  → Domain's own APM home price estimate
      - property.timeline   → full sale + rental history with daysOnMarket

Access:
    No API key, no auth, no persisted-query allowlist — arbitrary query documents
    are accepted. Introspection is disabled. BUT the endpoint sits behind the same
    Akamai bot management as the rest of www.domain.com.au, so it still needs the
    Web Unlocker. Verified 2026-08-13: this VM (GCP) and a GitHub-hosted Actions
    runner (Azure) BOTH get 403 — Akamai blocks cloud ASNs wholesale. Do not spend
    a deploy testing Netlify/Lambda.

Env vars required:
    BRIGHTDATA_API_KEY  — Bright Data API token
    BRIGHTDATA_ZONE     — zone name (default: 'web_unlocker2')

Usage:
    from shared.domain_graphql import search_listings, get_property, get_listing

    res = search_listings('Robina', 'QLD', '4226', listing_type='Sale')
    print(res['totalResults'], len(res['results']))

    prop = get_property('XT-4979-MG')
    print(prop['valuation']['midPrice'], len(prop['timeline']))

Schema gotchas that will cost you an hour if you forget them:
    - IDs are base64 Relay global IDs: base64("property:XT-4979-MG"). A raw numeric
      id does NOT error — it silently resolves to `listing:0` and returns an empty
      object. encode_id() handles this.
    - landArea takes (unit: SQUARE_METERS) — American spelling. SQUARE_METRES fails.
    - Enums are unquoted: state: QLD, listingType: Sale (also Sold, Share).
    - searchListings.results is a union — needs `... on SearchListingsResultListing`.
    - bedrooms/bathrooms/timeline come back NULL on listing.property but populate
      when property(id:) is queried at the root. Query the property separately.
"""

import base64
import json
import os
import time
from typing import Optional, Dict, List, Any

from curl_cffi import requests as cffi_requests

BRIGHTDATA_ENDPOINT = 'https://api.brightdata.com/request'
GRAPHQL_URL = 'https://www.domain.com.au/graphql'

DEFAULT_TIMEOUT = 150
DEFAULT_RETRIES = 5

# Apollo rejects requests without a plausible browser origin.
_BROWSER_HEADERS = {
    'content-type': 'application/json',
    'accept': '*/*',
    'origin': 'https://www.domain.com.au',
    'referer': 'https://www.domain.com.au/',
}


def _api_key() -> Optional[str]:
    """Read env at call time (not import time) so callers can load_env() after import."""
    return os.environ.get('BRIGHTDATA_API_KEY')


def _zone() -> str:
    return os.environ.get('BRIGHTDATA_ZONE', 'web_unlocker2')


def encode_id(kind: str, raw_id: str) -> str:
    """Build a Relay global ID: encode_id('property', 'XT-4979-MG').

    Domain accepts ONLY the base64 form. Passing a bare id returns an empty object
    rather than an error, so this is not optional.
    """
    return base64.b64encode(f'{kind}:{raw_id}'.encode()).decode()


def execute(query: str, variables: Optional[Dict] = None,
            retries: int = DEFAULT_RETRIES, timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """Run a GraphQL document and return the parsed `data` object.

    Returns None on transport failure. GraphQL *validation* errors are surfaced by
    raising ValueError — they mean the query is wrong and retrying cannot help.
    """
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            'BRIGHTDATA_API_KEY is not set. www.domain.com.au/graphql is behind Akamai '
            'and is unreachable from any cloud IP — there is no direct fallback.'
        )

    body = {'query': query}
    if variables:
        body['variables'] = variables
    debug = os.environ.get('DOMAIN_FETCH_DEBUG')

    for attempt in range(retries):
        payload = {
            'zone': _zone(),
            'url': GRAPHQL_URL,
            'format': 'raw',
            'method': 'POST',
            # NOTE: Bright Data's field is 'body', not 'data'. Sending 'data'
            # fails validation with a confusing "not allowed" error.
            'body': json.dumps(body),
            'headers': _BROWSER_HEADERS,
        }
        try:
            resp = cffi_requests.post(
                BRIGHTDATA_ENDPOINT,
                headers={'Content-Type': 'application/json',
                         'Authorization': f'Bearer {api_key}'},
                json=payload, timeout=timeout)
            text = resp.text or ''
            if not text.strip():
                if debug:
                    print(f'      [domain_graphql] empty body (unlocker 502), attempt {attempt}')
                raise ValueError('empty')

            parsed = json.loads(text)
            if parsed.get('errors'):
                messages = [e.get('message', '') for e in parsed['errors']]
                # A null `data` with errors means the document failed validation —
                # deterministic, so fail loudly instead of burning retries on it.
                if parsed.get('data') is None:
                    raise ValueError(f'GraphQL query rejected: {messages}')
                if debug:
                    print(f'      [domain_graphql] partial errors: {messages}')
            return parsed.get('data')

        except ValueError as e:
            if 'GraphQL query rejected' in str(e):
                raise
        except Exception as e:
            if debug:
                print(f'      [domain_graphql] {type(e).__name__}: {e}')
        if attempt < retries - 1:
            time.sleep(min(3 * (attempt + 1), 15))
    return None


_SEARCH_QUERY = '''
query Search($params: SearchListingsParametersInput!) {
  searchListings(searchParams: $params) {
    totalResults
    page
    results {
      ... on SearchListingsResultListing {
        id
        listingId
        propertyType
        bedrooms
        bathrooms
        carspaces
        dateListed
        tags
        displayableAddress { unitNumber streetNumber street suburb { name } postcode state }
        priceDetails { displayPrice }
        agency { name }
      }
    }
  }
}
'''


def search_listings(suburb: str, state: str, postcode: str,
                    listing_type: str = 'Sale', page: int = 1, page_size: int = 200,
                    include_surrounding: bool = False, **kw) -> Optional[Dict]:
    """One request → a page of listings for a suburb.

    listing_type: 'Sale' or 'Sold' (also 'Share'). Note Robina returns 121 for Sale
    and 5,837 for Sold, so always paginate deliberately rather than assuming one page.

    page_size caps at 200 — 200 returns a whole suburb's for-sale set in one request,
    but 500 silently returns zero results rather than erroring. Do not raise it.

    Returns {'totalResults': int, 'page': int, 'results': [...]} or None.
    """
    params = {
        'locations': [{
            'suburb': suburb,
            'state': state,
            'postcode': postcode,
            'includeSurroundingSuburbs': include_surrounding,
        }],
        'listingType': listing_type,
        'page': page,
        'pageSize': page_size,
    }
    data = execute(_SEARCH_QUERY, {'params': params}, **kw)
    return data.get('searchListings') if data else None


_PROPERTY_QUERY = '''
query Prop($id: ID!) {
  property(id: $id) {
    id
    propertyId
    hpgSlug
    bedrooms
    bathrooms
    marketStatus
    landArea(unit: SQUARE_METERS)
    address { unitNumber streetNumber street suburb { name } postcode state }
    valuation { midPrice lowerPrice priceConfidence source }
    timeline { eventDate eventPrice daysOnMarket category }
  }
}
'''


def get_property(property_id: str, **kw) -> Optional[Dict]:
    """Fetch a property by its Domain property id (e.g. 'XT-4979-MG').

    This is the call that carries `valuation` (Domain's APM estimate) and the full
    `timeline` of sale/rental events. Accepts either the raw id or an already-encoded
    Relay global id.
    """
    gid = property_id if property_id.endswith('==') or property_id.endswith('=') \
        else encode_id('property', property_id)
    data = execute(_PROPERTY_QUERY, {'id': gid}, **kw)
    return data.get('property') if data else None


_LISTING_QUERY = '''
query Lst($id: ID!) {
  listing(id: $id) {
    id
    status
    bedrooms
    bathrooms
    features
    description
    seoUrl
    landArea(unit: SQUARE_METERS)
    address { unitNumber streetNumber street postcode state }
    property { propertyId hpgSlug }
  }
}
'''


def get_listing(listing_id: Any, **kw) -> Optional[Dict]:
    """Fetch a listing by its numeric Domain listing id (e.g. 2020833972).

    Returns the full advertisement copy, features and status. Use the returned
    `property.propertyId` with get_property() for valuation + timeline — those
    fields are null when reached via listing.property.
    """
    gid = encode_id('listing', str(listing_id))
    data = execute(_LISTING_QUERY, {'id': gid}, **kw)
    return data.get('listing') if data else None
