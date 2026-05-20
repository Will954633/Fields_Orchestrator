"""
Domain.com.au image URL helpers.

The Domain CDN (rimh2.domainstatic.com.au) serves images via a signed-hash
URL. The hash encodes a resize transform — so two URLs with the same filename
can return different resolutions (one full-res, one thumbnail). Floor plans
in particular have been observed to silently return a 150x107 thumbnail even
when the filename implies 3277x2338.

The bucket-api endpoint (bucket-api.domain.com.au) bypasses the signed-hash
layer entirely and always serves the original file at full resolution. No
auth, no signing — public.

Canonical helper used by:
  - scripts/extract_floor_plans_from_v2_images.py (write path)
  - scripts/reanalyze_floor_plans_gpt54.py        (read path)
  - scripts/property_reports/inline_floor_plan.py (on-demand resolver)
"""

from __future__ import annotations

import re

# Match: rimh2.domainstatic.com.au/<hash>/[any combination of filters:... and fit-in/WxH segments, in any order]/<filename>
#
# Domain serves URLs in several variants:
#   /<hash>/<filename>
#   /<hash>/filters:format(...)/<filename>
#   /<hash>/fit-in/WxH/<filename>
#   /<hash>/fit-in/WxH/filters:format(...)/<filename>     ← most common for floor plans
#   /<hash>/filters:format(...)/fit-in/WxH/<filename>     ← rarer but seen
#
# The transform segments can appear in ANY order before the filename. Use
# a repeated non-capturing group rather than a fixed order to handle all
# variants safely.
_DOMAIN_CDN_RE = re.compile(
    r"rimh2\.domainstatic\.com\.au"                    # host
    r"/[^/]+"                                           # signed hash segment
    r"(?:/(?:filters:[^/]+|fit-in/[^/]+))*"             # zero+ transform segments, any order
    r"/(?P<filename>[^/?#]+)"                           # filename (final path segment)
)


def to_bucket_api_url(url: str) -> str:
    """Convert a Domain CDN URL to its bucket-api equivalent (full res).

    No-op for URLs that aren't Domain CDN (e.g. already bucket-api, S3,
    blob storage, etc.). Safe to call on any string.
    """
    if not isinstance(url, str) or not url:
        return url
    m = _DOMAIN_CDN_RE.search(url)
    if not m:
        return url
    return f"https://bucket-api.domain.com.au/v1/bucket/image/{m.group('filename')}"


def is_domain_cdn(url: str) -> bool:
    """True if the URL is a rimh2.domainstatic.com.au CDN URL."""
    return isinstance(url, str) and "rimh2.domainstatic.com.au" in url


def is_bucket_api(url: str) -> bool:
    """True if the URL is a bucket-api.domain.com.au URL (already full-res)."""
    return isinstance(url, str) and "bucket-api.domain.com.au" in url
