"""
report_link.py — the `?k=` link key for /your-home report URLs.

`/your-home/<slug>` is gated server-side: the report holds our valuation of a
home, our commercial read on selling it, and (via print_appraisal) whether we
believe it is tenanted. Slugs are derived deterministically from street
addresses, so the URL is guessable and cannot itself be the secret.

`k` is an HMAC of the slug under REPORT_LINK_SECRET. Stateless by design — every
generator recomputes it from the slug, so there is nothing to store and nothing
to reconcile across the existing report documents.

⚠ THIS MUST STAY BYTE-IDENTICAL TO `reportLinkKey()` IN
`01_Website/netlify/functions/db.mjs`. Same secret, same HMAC-SHA256, same
base64url, same 16-char truncation. If the two drift, printed QR codes silently
stop working and nobody finds out until a recipient reports a 404.

Verified parity 2026-08-19: both produce `AZLSMkAUjAwQ_Qfs` for
`21-royal-links-drive-robina`.
"""
import base64
import hashlib
import hmac
import os

_KEY_LEN = 16


def report_link_key(slug: str) -> str:
    """HMAC link key for a report slug.

    Raises rather than returning empty: a mailer that prints a QR code with no
    key produces artwork that is already wrong by the time anyone can check it.
    Callers that can legitimately proceed without a key should catch this.
    """
    secret = os.environ.get("REPORT_LINK_SECRET", "")
    if not secret:
        raise RuntimeError(
            "REPORT_LINK_SECRET is not set — refusing to generate a report link "
            "without its key. A link without `k` lands the recipient on a 404."
        )
    digest = hmac.new(secret.encode(), str(slug).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:_KEY_LEN]


def report_url(slug: str, base: str = "https://fieldsestate.com.au",
               extra_query: str = "", fragment: str = "") -> str:
    """Full, key-bearing report URL. Prefer this over hand-assembling one."""
    q = f"k={report_link_key(slug)}"
    if extra_query:
        q = f"{extra_query.lstrip('?&')}&{q}"
    return f"{base}/your-home/{slug}?{q}{fragment}"
