#!/usr/bin/env python3
"""Automate ID4ME address lookups.

Commands
--------
  login                     One-time interactive login; the session then persists.
  status                    Report whether the stored session is still valid.
  discover dom              Dump the dashboard's DOM so selectors can be written.
  discover watch [-s SECS]  Record network traffic while you search by hand.
  search "<address>"        Look up a single address and print/save the result.
  batch <addresses.csv>     Look up every address in a CSV and write results.

Run `login` once. Everything after that can run headless and unattended.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

import config
import discover
from browser import browser_context, first_page

SELECTORS = json.loads(config.SELECTORS_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# selector helpers
# --------------------------------------------------------------------------

def find_first(page, key: str, timeout_ms: int = 8000):
    """Return the first visible element matching any candidate selector for `key`.

    Candidates are tried in order and the whole set is retried until the timeout,
    which handles client-side rendering without hard-coding a sleep.
    """
    candidates = [s for s in SELECTORS.get(key, []) if not s.startswith("_")]
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for selector in candidates:
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible():
                    return loc, selector
            except Exception:
                continue
        page.wait_for_timeout(250)
    return None, None


def any_visible(page, key: str) -> bool:
    loc, _ = find_first(page, key, timeout_ms=1500)
    return loc is not None


# --------------------------------------------------------------------------
# session
# --------------------------------------------------------------------------

def is_logged_in(page) -> bool:
    """Logged in == landed back on id4me.me with no login affordance showing.

    Deliberately does not require the search box to be found: that selector is
    inferred, and a miss there would masquerade as an auth failure. Auth0 always
    parks an unauthenticated user on id4me.au.auth0.com, so the host plus the
    absence of a password field is the reliable signal.
    """
    url = page.url.lower()
    if "auth0.com" in url or "/login" in url or "signin" in url:
        return False
    if "id4me.me" not in url:
        return False
    return not any_visible(page, "logged_out_markers")


def load_credentials() -> tuple[str | None, str | None]:
    """Read ID4ME credentials from the environment or an adjacent .env file.

    Optional: without them, `login` still works interactively. With them, an
    expired Auth0 session can be renewed unattended mid-run.
    """
    email = os.environ.get("ID4ME_EMAIL")
    password = os.environ.get("ID4ME_PASSWORD")
    env_file = config.ROOT / ".env"
    if (not email or not password) and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip("'\"")
            if key.strip() == "ID4ME_EMAIL" and not email:
                email = value
            elif key.strip() == "ID4ME_PASSWORD" and not password:
                password = value
    return email, password


def auto_login(page) -> bool:
    """Sign in using stored credentials. Returns False if none are configured."""
    email, password = load_credentials()
    if not (email and password):
        return False

    print("  session expired - re-authenticating with stored credentials...")
    page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    email_box, _ = find_first(page, "login_email", timeout_ms=15000)
    pw_box, _ = find_first(page, "login_password", timeout_ms=5000)
    submit, _ = find_first(page, "login_submit", timeout_ms=5000)
    if not (email_box and pw_box and submit):
        print("  could not locate the login form")
        return False

    email_box.fill(email)
    pw_box.fill(password)
    submit.click()

    # Auth0 bounces back to the dashboard via an OAuth redirect chain.
    deadline = time.time() + 60
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        if is_logged_in(page):
            print("  re-authenticated")
            return True
    print("  re-authentication did not complete (MFA or changed password?)")
    return False


def ensure_session(page) -> bool:
    """Guarantee a usable session, renewing it automatically when possible."""
    if is_logged_in(page):
        return True
    if auto_login(page):
        return True
    print("Not logged in. Run: python id4me_bot.py login")
    return False


def cmd_login(args) -> int:
    """Open a real browser window and wait for the user to sign in."""
    with browser_context(headless=False) as ctx:
        page = first_page(ctx)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")

        print("\n" + "=" * 72)
        print("  A Chrome window has opened on ID4ME.")
        print("  Sign in with your subscription account, and land on the dashboard.")
        print("  This is a ONE-TIME step: the session is saved to")
        print(f"    {config.PROFILE_DIR}")
        print("  and reused by every later run.")
        print(f"\n  Waiting up to {args.wait}s for a successful login...")
        print("=" * 72 + "\n")

        deadline = time.time() + args.wait
        while time.time() < deadline:
            if is_logged_in(page):
                print(f"\n  Login detected. Session saved. Current URL: {page.url}")
                page.wait_for_timeout(3000)  # let Chrome flush cookies to disk
                return 0
            page.wait_for_timeout(2000)

        print("\n  Timed out without detecting a login.")
        print("  If you DID log in, the detector may need tuning - run:")
        print("      python id4me_bot.py discover dom")
        return 1


def cmd_status(args) -> int:
    with browser_context(headless=args.headless) as ctx:
        page = first_page(ctx)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        ok = is_logged_in(page)
        print(f"URL:       {page.url}")
        print(f"Logged in: {ok}")
        return 0 if ok else 1


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def search_address(page, address: str, capture_api: bool = True) -> dict:
    """Run one address through the dashboard search and return a result record."""
    record = {
        "address": address,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "status": "unknown",
        "url": None,
        "text": None,
        "api_responses": [],
        "error": None,
    }

    api_hits: list[dict] = []

    def on_response(response):
        req = response.request
        if req.resource_type not in {"xhr", "fetch"}:
            return
        try:
            body = response.text()
        except Exception:
            return
        if not body.strip().startswith(("{", "[")):
            return
        try:
            api_hits.append({"url": req.url, "status": response.status,
                             "json": json.loads(body)})
        except json.JSONDecodeError:
            pass

    if capture_api:
        page.on("response", on_response)

    try:
        if config.DASHBOARD_URL.rstrip("/") not in page.url:
            page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

        box, used = find_first(page, "search_input")
        if box is None:
            record["status"] = "error"
            record["error"] = "search input not found - re-run `discover dom`"
            return record

        box.click()
        box.fill("")
        box.type(address, delay=45)          # typed, so autocomplete fires
        page.wait_for_timeout(1500)

        # Prefer an autocomplete suggestion when the site offers one, since the
        # site's own canonical address beats our free-text string.
        suggestion, _ = find_first(page, "suggestion_option", timeout_ms=2500)
        if suggestion is not None:
            suggestion.click()
        else:
            button, _ = find_first(page, "search_button", timeout_ms=2500)
            if button is not None:
                button.click()
            else:
                box.press("Enter")

        page.wait_for_load_state("networkidle", timeout=config.DEFAULT_TIMEOUT_MS)
        page.wait_for_timeout(2000)

        record["url"] = page.url
        if any_visible(page, "no_results_markers"):
            record["status"] = "no_results"
        else:
            container, _ = find_first(page, "results_container", timeout_ms=5000)
            record["text"] = (container.inner_text() if container
                              else page.locator("body").inner_text())[:20000]
            record["status"] = "ok"

        record["api_responses"] = api_hits

    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if capture_api:
            page.remove_listener("response", on_response)

    return record


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:60].strip("_")


def cmd_search(args) -> int:
    with browser_context(headless=args.headless) as ctx:
        page = first_page(ctx)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        if not ensure_session(page):
            return 1

        result = search_address(page, args.address)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = config.OUTPUT_DIR / f"{_slug(args.address)}_{stamp}.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")

        if args.screenshot:
            page.screenshot(path=str(out.with_suffix(".png")), full_page=True)

        print(f"\nstatus: {result['status']}")
        if result["error"]:
            print(f"error:  {result['error']}")
        if result["text"]:
            print("\n--- result text ---")
            print(result["text"][:3000])
        print(f"\nsaved: {out}")
        return 0 if result["status"] == "ok" else 1


# --------------------------------------------------------------------------
# batch
# --------------------------------------------------------------------------

def read_addresses(path) -> list[str]:
    """Read addresses from a CSV: uses an 'address' column, else the first column."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    if "address" in header:
        idx = header.index("address")
        body = rows[1:]
    else:
        idx = 0
        # Treat row 0 as data unless it looks like a header.
        body = rows if not header[0].startswith("address") else rows[1:]
    return [r[idx].strip() for r in body if r and len(r) > idx and r[idx].strip()]


def cmd_batch(args) -> int:
    addresses = read_addresses(args.csv)
    if not addresses:
        print(f"No addresses found in {args.csv}")
        return 1
    print(f"Loaded {len(addresses)} addresses from {args.csv}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_out = config.OUTPUT_DIR / f"batch_{stamp}.json"
    csv_out = config.OUTPUT_DIR / f"batch_{stamp}.csv"
    results: list[dict] = []

    with browser_context(headless=args.headless) as ctx:
        page = first_page(ctx)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        if not ensure_session(page):
            return 1

        for i, address in enumerate(addresses, 1):
            print(f"[{i}/{len(addresses)}] {address}")
            result = search_address(page, address)
            print(f"    -> {result['status']}"
                  + (f" ({result['error']})" if result["error"] else ""))
            results.append(result)

            # Write incrementally so a crash mid-run never loses finished work.
            json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")

            if i < len(addresses):
                time.sleep(config.BATCH_DELAY_SECONDS)

    with open(csv_out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["address", "status", "searched_at", "url", "error", "text"])
        for r in results:
            writer.writerow([r["address"], r["status"], r["searched_at"],
                             r["url"] or "", r["error"] or "",
                             (r["text"] or "").replace("\n", " | ")[:5000]])

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\nDone: {ok}/{len(results)} succeeded")
    print(f"  {json_out}\n  {csv_out}")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="one-time interactive login")
    p.add_argument("--wait", type=int, default=300, help="seconds to wait (default 300)")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("status", help="check whether the saved session is valid")
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("discover", help="inspect the site to build selectors")
    p.add_argument("mode", choices=["dom", "watch"])
    p.add_argument("-s", "--seconds", type=int, default=120)
    p.add_argument("--url", default=None)
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=lambda a: (
        discover.dump_dom(headless=a.headless, url=a.url) if a.mode == "dom"
        else discover.watch_network(seconds=a.seconds, headless=a.headless)) or 0)

    p = sub.add_parser("search", help="look up one address")
    p.add_argument("address")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--screenshot", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("batch", help="look up every address in a CSV")
    p.add_argument("csv")
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=cmd_batch)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
