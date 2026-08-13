"""Direct client for the ID4ME search API.

The dashboard is a React front end over a plain JSON API at
id4me-search-prod-api.azurewebsites.net, authenticated with an Auth0 bearer
token. Talking to it directly is far faster than driving the UI and does not
break when the site is restyled.

Auth strategy, cheapest first:
  1. Reuse the cached access token while it is still valid.
  2. Refresh it over HTTP with the Auth0 refresh token (offline_access).
  3. Fall back to a headless browser login, then harvest the token from
     localStorage.
"""

import json
import time

import requests

import config
import normalize

API_ROOT = "https://id4me-search-prod-api.azurewebsites.net/api"
AUTH0_TOKEN_URL = "https://id4me.au.auth0.com/oauth/token"
CLIENT_ID = "bX1SwoGPtCO0WdrnpR4w0xXnDD97s3HE"
# The audience really does carry a leading space in the tenant config.
AUDIENCE = " Id4me-search-v2"
SCOPE = "openid profile email offline_access"
AUTH0_LS_PREFIX = "@@auth0spajs@@"
INDEX = "search-au"

TOKEN_CACHE = config.ROOT / ".token.json"
_EXPIRY_SKEW = 120  # refresh a little early rather than racing the clock


class AuthError(RuntimeError):
    pass


class SessionError(RuntimeError):
    """The bearer token is fine but ID4ME has invalidated our sessionid.

    Separate from AuthError because the remedy differs: re-authenticating does
    not help, since the account allows only one live session and something else
    has claimed it.
    """


# --------------------------------------------------------------------------
# token handling
# --------------------------------------------------------------------------

def _load_cache() -> dict | None:
    if not TOKEN_CACHE.exists():
        return None
    try:
        return json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_cache(bundle: dict) -> None:
    TOKEN_CACHE.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    TOKEN_CACHE.chmod(0o600)  # holds a live bearer token


def _valid(bundle: dict | None) -> bool:
    return bool(bundle and bundle.get("access_token")
                and bundle.get("expires_at", 0) - _EXPIRY_SKEW > time.time())


def _refresh(bundle: dict) -> dict | None:
    """Mint a new access token from the stored refresh token, without a browser."""
    token = bundle.get("refresh_token")
    if not token:
        return None
    try:
        resp = requests.post(AUTH0_TOKEN_URL, timeout=30, json={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": token,
            "audience": AUDIENCE,
            "scope": SCOPE,
        })
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    fresh = {
        "access_token": data["access_token"],
        # Auth0 only returns a new refresh token when rotation is enabled.
        "refresh_token": data.get("refresh_token", token),
        "expires_at": time.time() + data.get("expires_in", 7200),
        # sessionid is issued by the app, not Auth0, so carry it across refreshes.
        "session_id": bundle.get("session_id"),
    }
    _save_cache(fresh)
    return fresh


def _harvest_from_browser() -> dict:
    """Log in headlessly and lift the token bundle out of localStorage."""
    from browser import browser_context, first_page
    import id4me_bot

    with browser_context(headless=True) as ctx:
        page = first_page(ctx)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        if not id4me_bot.is_logged_in(page):
            if not id4me_bot.auto_login(page):
                raise AuthError(
                    "Could not log in. Check credentials in .env, or run "
                    "`python3 id4me_bot.py login` to sign in by hand."
                )
            page.wait_for_timeout(4000)

        entries = page.evaluate(
            "()=>{const o=[];for(let i=0;i<localStorage.length;i++){"
            "const k=localStorage.key(i);"
            f"if(k.startsWith('{AUTH0_LS_PREFIX}')) o.push([k,localStorage.getItem(k)]);"
            "}return o;}"
        )
        session_id = _read_session_id(page, ctx)

    for _key, raw in entries:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        body = parsed.get("body")
        if not body or "access_token" not in body:
            continue  # the @@user@@ entry holds only an id_token
        fresh = {
            "access_token": body["access_token"],
            "refresh_token": body.get("refresh_token"),
            "expires_at": parsed.get("expiresAt")
                          or time.time() + body.get("expires_in", 7200),
            "session_id": session_id,
        }
        _save_cache(fresh)
        return fresh

    raise AuthError("Logged in but found no Auth0 access token in localStorage.")


def _read_session_id(page, ctx) -> str | None:
    """The API rejects queries without the app's own sessionid header.

    Without it every search silently returns zero results rather than an error,
    so it has to travel with the token.
    """
    for cookie in ctx.cookies():
        if cookie.get("name") == "id4me_session_id" and cookie.get("value"):
            return cookie["value"]
    try:
        traits = page.evaluate("()=>localStorage.getItem('ajs_user_traits')")
        if traits:
            return json.loads(traits).get("sessionId")
    except Exception:
        pass
    return None


def get_bundle(force: bool = False) -> dict:
    """Return a usable {access_token, session_id, ...} bundle."""
    bundle = None if force else _load_cache()
    if _valid(bundle) and bundle.get("session_id"):
        return bundle
    if bundle and bundle.get("session_id") and (refreshed := _refresh(bundle)):
        return refreshed
    # No cache, no session_id, or refresh declined - go get both from a browser.
    return _harvest_from_browser()


# --------------------------------------------------------------------------
# client
# --------------------------------------------------------------------------

class Id4meClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self._apply(get_bundle())

    def _apply(self, bundle: dict) -> None:
        self._bundle = bundle
        self.session.headers.update({
            "Authorization": f"Bearer {bundle['access_token']}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://id4me.me",
            "Referer": "https://id4me.me/",
            # Mandatory: without it the API returns empty results, not an error.
            "sessionid": bundle.get("session_id") or "",
        })

    def _request(self, method: str, path: str, **kwargs):
        url = f"{API_ROOT}/{path.lstrip('/')}"
        resp = self.session.request(method, url, timeout=60, **kwargs)
        if resp.status_code == 401:
            # Token died mid-run; mint a new one and retry exactly once.
            self._apply(get_bundle(force=True))
            resp = self.session.request(method, url, timeout=60, **kwargs)
        resp.raise_for_status()
        data = resp.json()

        # ID4ME signals session-level failures INSIDE a 200 response, e.g.
        #   {"isValid": false, "errorCode": 23,
        #    "errorMessage": "Multiple sessions detected. User ... was kicked out."}
        # The account permits one live session, so logging in anywhere else
        # invalidates ours. Callers read `data` -> [] and report
        # "address_not_found", so a dead session looks exactly like an address
        # with no records: every lookup fails identically and a batch run
        # reports 0% coverage as though it were a finding. Raise instead.
        if isinstance(data, dict) and data.get("isValid") is False:
            raise SessionError(
                f"ID4ME rejected the session (errorCode {data.get('errorCode')}): "
                f"{data.get('errorMessage')}"
            )
        return data

    def profile(self) -> dict:
        """Account profile, including subscription status and expiry."""
        return self._request("GET", "account/profile")

    def autocomplete(self, term: str) -> list[dict]:
        data = self._request("GET", "values/autocomplete",
                             params={"term": term, "indexToUse": INDEX})
        return data.get("data") or []

    def resolve_address(self, address: str) -> str | None:
        """Turn a free-text address into ID4ME's canonical form.

        Searching the canonical string is what the UI does when you pick an
        autocomplete suggestion, and it matches far more reliably than raw text.
        """
        for variant in normalize.variants(address):
            for hit in self.autocomplete(variant):
                if hit.get("type") == "address" and hit.get("value"):
                    return hit["value"]
        return None

    def search(self, query: str, page: int = 0, size: int = 50) -> dict:
        return self._request("POST", "values/explain", json={
            "page": page,
            "size": size,
            "request": [
                {"id": 0, "command": "index", "arg": "AU"},
                {"id": 1, "command": "query", "arg": query},
            ],
            "indexToUse": INDEX,
        })

    def dncr(self, phones: list[str]) -> dict[str, dict]:
        """Do Not Call Register status, keyed by phone number."""
        if not phones:
            return {}
        rows = self._request("POST", "Australia/getAuDncrList", json=phones)
        return {r.get("phone"): r for r in rows or []}

    def emails_can_market(self, emails: list[str]) -> dict[str, bool]:
        if not emails:
            return {}
        rows = self._request("POST", "Australia/getEmailsCanMarket", json=emails)
        return {r.get("email"): bool(r.get("canMarket")) for r in rows or []}
