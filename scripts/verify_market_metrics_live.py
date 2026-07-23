#!/usr/bin/env python3
"""
verify_market_metrics_live.py — Live-page verification for /market-metrics.

Why: 2026-07-23 — a Market Pulse rewrite fixed the summary/verdict text and
data_snapshot fields, and both were independently confirmed live via the API.
But the live page ALSO renders a third, separate content structure
(market_pulse.narrative.pillars) that neither fix touched — it sat stale
since 2026-07-03, producing a page that showed three different absorption-
rate figures and contradicted itself across sections. The API-level checks
this session ran did not catch it because they checked the fields that were
written, not the full rendered page. Only opening the actual live page and
reading everything on it caught the problem.

This script is that check, made repeatable: it loads each suburb/category
page in a real headless browser (so client-fetched data — pulseData,
market-narrative charts — is included, not just the SSR shell), extracts all
visible text, and returns it for review. It does NOT try to auto-detect
inconsistencies — text analysis is exactly the kind of judgement a Claude
Code session should apply, not brittle regex. Its job is only to guarantee
the text actually gets pulled and read every cycle, not to replace judgement.

Usage:
    python3 scripts/verify_market_metrics_live.py
        Fetch text for all 3 core suburbs x 7 categories (21 pages), save
        each to a file, print a manifest. A Claude Code session reads the
        manifest + files and reviews for consistency.

    python3 scripts/verify_market_metrics_live.py --suburb robina --category sell-now
        Single page only (faster, for a targeted re-check after a fix).

    python3 scripts/verify_market_metrics_live.py --list
        Print paths from the most recent run without re-fetching.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SUBURBS = ["robina", "burleigh-waters", "varsity-lakes"]
CATEGORIES = ["sell-now", "buy", "crash-risk", "overview", "houses-vs-units", "direction", "suburb-compare"]
BASE_URL = "https://fieldsestate.com.au/market-metrics"

OUTPUT_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "artifacts", "market_metrics_verify"
)

_NODE_SCRIPT = r"""
const puppeteer = require('%(puppeteer_path)s');

(async () => {
  const url = process.argv[2];
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  try {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 45000 });
    // Client-fetched pulse/chart data lands after networkidle2 in some cases — small settle wait.
    await new Promise(r => setTimeout(r, 1500));
    const text = await page.evaluate(() => document.body.innerText);
    console.log(JSON.stringify({ ok: true, text, consoleErrors }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: String(err), consoleErrors }));
  } finally {
    await browser.close();
  }
})();
"""


def _puppeteer_path() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "..", "node_modules", "puppeteer-core")


def fetch_page_text(url: str, timeout: int = 60) -> dict:
    import tempfile
    script = _NODE_SCRIPT % {"puppeteer_path": _puppeteer_path()}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        proc = subprocess.run(
            ["node", script_path, url],
            capture_output=True, text=True, timeout=timeout,
        )
    finally:
        os.unlink(script_path)
    if proc.returncode != 0:
        return {"ok": False, "error": f"node exited {proc.returncode}: {proc.stderr[:500]}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        return {"ok": False, "error": f"bad node output: {e}: {proc.stdout[:300]}"}


def run(suburbs, categories):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = os.path.join(OUTPUT_ROOT, stamp)
    os.makedirs(out_dir, exist_ok=True)

    manifest = []
    for suburb in suburbs:
        for category in categories:
            url = f"{BASE_URL}/{suburb}/{category}"
            print(f"Fetching {url} ...")
            result = fetch_page_text(url)
            fname = f"{suburb}_{category}.txt"
            fpath = os.path.join(out_dir, fname)
            if result.get("ok"):
                with open(fpath, "w") as f:
                    f.write(result["text"])
                status = "OK"
                if result.get("consoleErrors"):
                    status = f"OK ({len(result['consoleErrors'])} console errors)"
            else:
                with open(fpath, "w") as f:
                    f.write(f"FETCH FAILED: {result.get('error')}")
                status = "FAILED"
            print(f"  -> {status} -> {fpath}")
            manifest.append({"suburb": suburb, "category": category, "url": url, "file": fpath, "status": status})

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print()
    print(f"Done. {len(manifest)} pages fetched -> {out_dir}/")
    print(f"Manifest: {manifest_path}")
    print()
    print("Next step: read each file and check for internal consistency (same stat")
    print("shown differently in different sections), staleness (dates/quarters that")
    print("don't match the latest data), and any 'FETCH FAILED' entries above.")
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch live /market-metrics page text for review")
    parser.add_argument("--suburb", type=str, help="Single suburb slug (e.g. robina)")
    parser.add_argument("--category", type=str, help="Single category (e.g. sell-now)")
    args = parser.parse_args()

    suburbs = [args.suburb] if args.suburb else SUBURBS
    categories = [args.category] if args.category else CATEGORIES
    run(suburbs, categories)
