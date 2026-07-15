#!/usr/bin/env python3
"""
Scrape real-estate agent contact details (name, mobile, agency, profile URL,
email) from Domain.com.au for-sale listings and append them to the "Agents"
Google Sheet — agent names hyperlinked through to their Domain profile.

Approach (reuses the existing listing-scrape stack):
  suburb /sale/ search page  ->  listing detail URLs
  listing detail page        ->  componentProps.rootGraphQuery.listingByIdV2.agents[]
                                  -> {fullName, mobileNumber, email, profileUrl, agentId}
                                  + listingByIdV2.agency.name / general phone

All page fetches route through shared.domain_fetch (Bright Data Web Unlocker —
the VM IP is Akamai-blocked, so direct curl_cffi 403s). Dedupe is by agentId,
and against agents already present in the sheet, so re-running to grow the list
from 5 -> 50 -> 100 never duplicates.

Suburbs are preferenced: southern Gold Coast first, then northern NSW (Tweed).

Usage:
  python3 scripts/scrape_agents_to_sheet.py --target 5            # first batch
  python3 scripts/scrape_agents_to_sheet.py --target 50           # grow to 50 total
  python3 scripts/scrape_agents_to_sheet.py --target 100          # grow to 100 total
  python3 scripts/scrape_agents_to_sheet.py --target 5 --dry-run  # don't touch the sheet
"""
from __future__ import annotations
import argparse, json, os, re, sys, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.domain_fetch import fetch_html
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---- config -------------------------------------------------------------------
SPREADSHEET_ID = "1hc_x2LRbOPIGgH4OIhOYQDu9TsRTsUKFEaLbsuhfAkg"
TAB = "Sheet1"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")
AEST = timezone(timedelta(hours=10))

HEADERS = ["Agent Name", "Mobile", "Agency", "Area found", "Email",
           "Agency phone", "Profile URL", "Date added"]

# Preference: southern Gold Coast (QLD) AND northern NSW (Tweed), interleaved so
# both regions get represented rather than the target filling from the first
# suburb alone. Palm Beach + Burleigh Heads are listed LAST because they were
# already mined in the first batch (their agents dedupe out).
SUBURBS = [
    # --- interleaved southern GC (QLD) + Tweed (NSW) ---
    ("Currumbin",         "currumbin-qld-4223"),
    ("Tweed Heads",       "tweed-heads-nsw-2485"),
    ("Tugun",             "tugun-qld-4224"),
    ("Kingscliff",        "kingscliff-nsw-2487"),
    ("Mermaid Beach",     "mermaid-beach-qld-4218"),
    ("Banora Point",      "banora-point-nsw-2486"),
    ("Coolangatta",       "coolangatta-qld-4225"),
    ("Casuarina",         "casuarina-nsw-2487"),
    ("Robina",            "robina-qld-4226"),
    ("Pottsville",        "pottsville-nsw-2489"),
    ("Varsity Lakes",     "varsity-lakes-qld-4227"),
    ("Murwillumbah",      "murwillumbah-nsw-2484"),
    ("Currumbin Waters",  "currumbin-waters-qld-4223"),
    ("Tweed Heads South", "tweed-heads-south-nsw-2486"),
    ("Elanora",           "elanora-qld-4221"),
    ("Cabarita Beach",    "cabarita-beach-nsw-2488"),
    ("Tallebudgera",      "tallebudgera-qld-4228"),
    ("Bilinga",           "bilinga-qld-4225"),
    ("Miami",             "miami-qld-4220"),
    ("Burleigh Waters",   "burleigh-waters-qld-4220"),
    # --- already mined in batch 1 (kept last; agents dedupe out) ---
    ("Palm Beach",        "palm-beach-qld-4221"),
    ("Burleigh Heads",    "burleigh-heads-qld-4220"),
]


# ---- google sheets ------------------------------------------------------------
def format_mobile(num):
    """Normalise to '04XX XXX XXX' — spaces keep Sheets from parsing it as an
    integer and dropping the leading zero."""
    d = re.sub(r"\D", "", num or "")
    if len(d) == 10 and d.startswith("04"):
        return f"{d[0:4]} {d[4:7]} {d[7:10]}"
    return num or ""


def get_sheets():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def read_existing(svc):
    """Return (set of profile-URL keys already in the sheet, current row count)."""
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1:H10000",
        valueRenderOption="FORMULA").execute()
    rows = resp.get("values", [])
    keys = set()
    for r in rows[1:]:
        # name cell is a HYPERLINK formula containing the profile URL; col G also has it
        blob = " ".join(str(c) for c in r)
        m = re.search(r"real-estate-agent/([a-z0-9-]+)", blob)
        if m:
            keys.add(m.group(1).rstrip("/"))
    return keys, len(rows)


def ensure_header(svc):
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1:H1").execute()
    if not resp.get("values"):
        svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED", body={"values": [HEADERS]}).execute()
    return 1


def force_text_columns(svc, sheet_id=0):
    """Force the Mobile (B) and Agency phone (F) columns to plain-text format so
    Sheets never parses a phone number as an integer and drops its leading zero."""
    reqs = [{
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startColumnIndex": c, "endColumnIndex": c + 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
            "fields": "userEnteredFormat.numberFormat",
        }} for c in (1, 5)]
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": reqs}).execute()


def append_agents(svc, agents, start_row):
    rows = []
    for a in agents:
        url = a["profileUrl"]
        name_cell = f'=HYPERLINK("{url}","{a["fullName"]}")'
        rows.append([name_cell, format_mobile(a.get("mobile", "")), a.get("agency", ""),
                     a.get("area", ""), a.get("email", ""), a.get("agency_phone", ""),
                     url, datetime.now(AEST).strftime("%Y-%m-%d")])
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A{start_row}",
        valueInputOption="USER_ENTERED", body={"values": rows}).execute()


# ---- domain scraping ----------------------------------------------------------
def get_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def listing_urls_for_suburb(slug, pages=1):
    """Fetch /sale/<slug>/ search page(s) and return listing detail URLs."""
    urls = []
    for page in range(1, pages + 1):
        suffix = f"?page={page}" if page > 1 else ""
        search_url = f"https://www.domain.com.au/sale/{slug}/{suffix}"
        html = fetch_html(search_url, retries=10)  # search pages are heavy + captcha-prone
        if not html:
            print(f"    ! search fetch failed: {slug} page {page}")
            continue
        found = re.findall(r'href="(https://www\.domain\.com\.au/[a-z0-9-]+-\d{6,12})"', html)
        for u in found:
            if u not in urls:
                urls.append(u)
        time.sleep(2)
    return urls


def agents_from_listing(url):
    """Return list of agent dicts extracted from a listing detail page."""
    html = fetch_html(url, retries=8)
    if not html:
        return []
    nd = get_next_data(html)
    if not nd:
        return []
    cp = nd.get("props", {}).get("pageProps", {}).get("componentProps", {})
    lst = cp.get("rootGraphQuery", {}).get("listingByIdV2", {}) or {}
    agency = lst.get("agency", {}) or {}
    agency_name = agency.get("name", "")
    agency_phone = (agency.get("contactDetails", {}) or {}).get("general", {}).get("phone", "")
    out = []
    for ag in lst.get("agents", []) or []:
        prof = (ag.get("profileUrl") or "").rstrip("/")
        if not prof or not ag.get("fullName"):
            continue
        out.append({
            "fullName": ag.get("fullName", "").strip(),
            "mobile": (ag.get("mobileNumber") or "").strip(),
            "email": (ag.get("email") or "").strip(),
            "agency": agency_name,
            "agency_phone": agency_phone,
            "profileUrl": prof,
            "agentId": ag.get("agentId") or prof.split("-")[-1],
        })
    # Fallback path (older shape) if rootGraphQuery missing
    if not out:
        for ag in cp.get("agents", []) or []:
            prof = (ag.get("agentProfileUrl") or "").rstrip("/")
            if not prof or not ag.get("name"):
                continue
            out.append({
                "fullName": ag.get("name", "").strip(),
                "mobile": (ag.get("mobile") or "").strip(),
                "email": (ag.get("email") or "").strip(),
                "agency": agency_name,
                "agency_phone": agency_phone,
                "profileUrl": prof,
                "agentId": prof.split("-")[-1],
            })
    return out


def prof_key(url):
    m = re.search(r"real-estate-agent/([a-z0-9-]+)", url)
    return m.group(1).rstrip("/") if m else url


# Non-human "contacts" that appear in project/developer listings (CRM bots,
# software integrations, generic team/office inboxes) — never real agents.
_JUNK_RE = re.compile(
    r"\b(crm|integration|enquir\w*|reception|admin|office|projects?|"
    r"display|gallery|rentals?|leasing|property\s+management|holiday|"
    r"info|sales\s+team|new\s+homes|land\s+sales|team)\b", re.I)


def is_au_mobile(num):
    """True only for a genuine AU mobile (04xx xxx xxx) — rejects 1300/1800/
    landline numbers that project listings put in the mobile field."""
    digits = re.sub(r"\D", "", num or "")
    return len(digits) == 10 and digits.startswith("04")


def looks_like_real_agent(a):
    """Filter out non-human contacts. Real agent = personal name (>=2 words),
    no CRM/integration/team keywords, with a genuine AU mobile number."""
    name = a.get("fullName", "").strip()
    if not name or not is_au_mobile(a.get("mobile")):
        return False
    if _JUNK_RE.search(name) or _JUNK_RE.search(prof_key(a["profileUrl"])):
        return False
    if len(name.split()) < 2:        # require first + last name
        return False
    if not re.search(r"[A-Za-z]", name):
        return False
    # reject "place-name" style listings (e.g. "La Belle Palm Beach"): a real
    # agent's profile slug ends in a numeric agent id.
    if not re.search(r"-\d{4,}$", prof_key(a["profileUrl"])):
        return False
    return True


# ---- main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=5, help="total unique agents desired in the sheet")
    ap.add_argument("--require-mobile", action="store_true", default=True,
                    help="only keep agents that have a mobile number")
    ap.add_argument("--workers", type=int, default=10, help="concurrent page fetches")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    svc = None
    existing = set()
    next_row = 2
    if not args.dry_run:
        svc = get_sheets()
        ensure_header(svc)
        force_text_columns(svc)
        existing, nrows = read_existing(svc)
        next_row = max(2, nrows + 1)
        print(f"Sheet already has {len(existing)} agents (next row {next_row}). Target total: {args.target}")
    need = args.target - len(existing)
    if need <= 0:
        print(f"Already at/above target ({len(existing)} >= {args.target}). Nothing to do.")
        return

    # --- Phase 1: gather listing URLs from all suburbs concurrently --------------
    print(f"\nPhase 1: fetching search pages for {len(SUBURBS)} suburbs ({args.workers} workers)...")
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(listing_urls_for_suburb, slug): (area, slug) for area, slug in SUBURBS}
        for fut in as_completed(futs):
            area, slug = futs[fut]
            try:
                results[slug] = fut.result()
            except Exception as e:
                results[slug] = []
                print(f"  ! {slug} search error: {e}")
            print(f"  {area:<18} {len(results.get(slug, []))} listings")
    # Retry suburbs whose single concurrent search fetch failed (captcha under
    # load) — sequentially, so the explicitly-wanted Tweed suburbs aren't lost.
    failed = [(area, slug) for area, slug in SUBURBS if not results.get(slug)]
    if failed:
        print(f"  retrying {len(failed)} failed search pages sequentially...")
        for area, slug in failed:
            try:
                results[slug] = listing_urls_for_suburb(slug)
            except Exception:
                results[slug] = []
            print(f"    retry {area:<18} {len(results.get(slug, []))} listings")
    # flatten in preference order, dedupe listing URLs
    ordered = []
    seen_urls = set()
    for area, slug in SUBURBS:
        for u in results.get(slug, []):
            if u not in seen_urls:
                seen_urls.add(u)
                ordered.append((area, u))
    print(f"  total unique listings: {len(ordered)}")

    # --- Phase 2: fetch listing detail pages concurrently, in preference order ---
    print(f"\nPhase 2: extracting agents (need {need})...")
    seen = set(existing)
    collected = []
    for i in range(0, len(ordered), args.workers):
        if len(collected) >= need:
            break
        batch = ordered[i:i + args.workers]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(agents_from_listing, u): (area, u) for area, u in batch}
            for fut in as_completed(futs):
                area, u = futs[fut]
                try:
                    agents = fut.result()
                except Exception:
                    agents = []
                for a in agents:
                    key = prof_key(a["profileUrl"])
                    if key in seen or not looks_like_real_agent(a):
                        continue
                    a["area"] = area
                    seen.add(key)
                    collected.append(a)
                    print(f"    + {a['fullName']:<26} {format_mobile(a['mobile']):<14} {a['agency'][:38]}")
        print(f"  [{min(i+args.workers, len(ordered))}/{len(ordered)} listings scanned, {len(collected)}/{need} agents]")

    collected = collected[:need]
    print(f"\nCollected {len(collected)} new agents.")
    if not collected:
        return
    if args.dry_run:
        print(json.dumps(collected, indent=2))
        return
    append_agents(svc, collected, next_row)
    print(f"Appended {len(collected)} agents to the sheet (rows {next_row}-{next_row+len(collected)-1}).")
    print(f"Sheet now has ~{len(existing)+len(collected)} agents total.")


if __name__ == "__main__":
    main()
