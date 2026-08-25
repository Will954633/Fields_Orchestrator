#!/usr/bin/env python3
"""Generate + publish per-address off-market V5 artifacts to blob storage.

Two kinds, both deterministic (no AI), reusing the existing generators:
  market-update    -> owner-subject article HTML + cards.json + resized aerial
  valuation-report -> comparable-sales assessment HTML + cover JPG

Blob (local nginx, /data/blobs, served at https://blobs.fieldsestate.com.au):
  market-update/<slug>.html
  market-update/<slug>.cards.json
  market-update/aerials/<slug>.jpg
  valuation-report/<slug>.html
  valuation-report/covers/<slug>.jpg

Served same-origin to the website via a status=200 proxy redirect in
netlify.toml (/market-update/* and /valuation-report/* -> blobs host), so the
V5 modals can iframe them. Reused by the on-demand poller and the pre-warm
batch. See 15_Off-Market/Page_Redesign_V5/ENDPOINT_SPEC.md.

CLI:
  python3 scripts/publish_offmarket_artifacts.py --slug <slug> --kind market-update|valuation-report|both
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WEBSITE_NODE_MODULES = "/home/fields/Feilds_Website/01_Website/node_modules"

REPO = Path("/home/fields/Fields_Orchestrator")
VENV_PY = "/home/fields/venv/bin/python3"
OWNER_GEN = REPO / "17_Direct_Letterbox" / "Owner_Subject_Article" / "build_owner_article.py"
VAL_GEN = REPO / "16_Valuation" / "report_page" / "build_report_page.py"
COVER_RENDER = REPO / "scripts" / "render_html_cover.cjs"
BLOB_BASE = "https://blobs.fieldsestate.com.au"
BLOB_ROOT = Path("/data/blobs")  # nginx serves this as blobs.fieldsestate.com.au
SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "merrimac"]
GEN_TIMEOUT = 300

sys.path.insert(0, str(REPO))


def _gen_sources(kind: str) -> list[Path]:
    """The files the artifact is COMPOSED from — its staleness inputs.

    ⚠ For market-update this is an EXPLICIT list, not a dir glob: the article
    generator shares its directory with unrelated sibling scripts (the mailer,
    the builders, tests, backtests), and an earlier dir-glob made editing
    build_owner_mailer.py falsely invalidate every article and trigger a mass
    rebuild. So list exactly what build_owner_article.py imports + the context
    JSONs it reads. **If it gains a new local import or context file, ADD IT
    HERE** — otherwise a change to that input will not be seen as staleness
    (the original 2026-08-25 stale-content bug). report_page/ holds only its
    generator, so it is globbed (auto-includes any helper added there)."""
    if kind == "market-update":
        d = OWNER_GEN.parent
        return [d / n for n in (
            "build_owner_article.py", "charts.py", "factbook.py", "guardrails.py",
            "variants.py", "subject_trajectory.py",
            "macro_context.json", "labour_context.json", "fundamentals_context.json",
            "arbitrage_context.json", "comparison_examples.json",
        )]
    if kind == "valuation-report":
        d = VAL_GEN.parent
        return sorted(d.glob("*.py")) + sorted(d.glob("*.json"))
    return []


def source_mtime(kind: str) -> float:
    """Newest mtime among this kind's composed source files. Deliberately NOT
    cached: the on-demand poller is a long-lived daemon and must notice a
    generator change WITHOUT a restart. Statting ~11 files is microseconds."""
    mtimes = [p.stat().st_mtime for p in _gen_sources(kind) if p.is_file()]
    return max(mtimes) if mtimes else 0.0


def blob_path(slug: str, kind: str) -> Path:
    sub = "market-update" if kind == "market-update" else "valuation-report"
    return BLOB_ROOT / sub / f"{slug}.html"


def artifact_fresh(slug: str, kind: str) -> bool:
    """True iff the blob exists AND is at least as new as the generator sources.
    A missing or stale (pre-change) blob returns False so it is (re)built."""
    try:
        return blob_path(slug, kind).stat().st_mtime >= source_mtime(kind)
    except FileNotFoundError:
        return False


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except Exception:
        pass


def resolve_subject(slug: str):
    """slug -> (doc, suburb_collection) across the measured suburbs, or (None, None)."""
    from shared.db import get_gold_coast_db

    db = get_gold_coast_db()
    for suburb in SUBURBS:
        doc = db[suburb].find_one({"url_slug": slug})
        if doc:
            return doc, suburb
    return None, None


def _resize_jpg(png_bytes: bytes, max_w: int = 1200) -> bytes:
    """Shrink the article's 1.6 MB aerial PNG to a web JPEG (~150 KB) so the
    market-update HTML can reference it instead of inlining it."""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        return png_bytes


def publish_market_update(slug: str, verbose: bool = True) -> dict:
    from shared.blob_storage import upload

    doc, suburb = resolve_subject(slug)
    if not doc:
        return {"ok": False, "kind": "market-update", "slug": slug, "error": f"slug not found: {slug}"}
    addr = doc.get("complete_address") or doc.get("address")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        proc = subprocess.run(
            [VENV_PY, str(OWNER_GEN), "--address", addr, "--suburb", suburb,
             "--skip-market-check", "--out-dir", str(tdp)],
            capture_output=True, text=True, timeout=GEN_TIMEOUT, cwd=str(OWNER_GEN.parent),
        )
        if proc.returncode != 0:
            return {"ok": False, "kind": "market-update", "slug": slug,
                    "error": f"generator rc={proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}"}
        htmls = [p for p in tdp.glob("*.html")]
        cards = [p for p in tdp.glob("*.cards.json")]
        aerials = [p for p in tdp.glob("*-aerial-sun.png")]
        if not htmls:
            return {"ok": False, "kind": "market-update", "slug": slug, "error": "no html produced"}
        html = htmls[0].read_text(encoding="utf-8")

        aerial_url = None
        if aerials:
            data = _resize_jpg(aerials[0].read_bytes(), max_w=1200)
            aerial_url = upload("market-update", f"aerials/{slug}.jpg", data, content_type="image/jpeg")
            if aerial_url:
                # article references it by relative filename; point to the blob JPEG
                html = re.sub(r'src="[^"]*-aerial-sun\.png"', f'src="{aerial_url}"', html)

        html_url = upload("market-update", f"{slug}.html", html.encode("utf-8"), content_type="text/html")
        cards_url = None
        if cards:
            cards_url = upload("market-update", f"{slug}.cards.json", cards[0].read_bytes(),
                               content_type="application/json")
        ok = bool(html_url)
        if verbose:
            print(f"[market-update] {slug}: html={html_url} cards={cards_url} aerial={aerial_url}")
        return {"ok": ok, "kind": "market-update", "slug": slug,
                "html_url": html_url, "cards_url": cards_url, "aerial_url": aerial_url}


def _wrap_valuation_html(fragment: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n</head>\n<body>\n'
        + fragment + '\n</body>\n</html>\n'
    )


def publish_valuation_report(slug: str, verbose: bool = True) -> dict:
    from shared.blob_storage import upload

    doc, suburb = resolve_subject(slug)
    if not doc:
        return {"ok": False, "kind": "valuation-report", "slug": slug, "error": f"slug not found: {slug}"}
    addr = doc.get("complete_address") or doc.get("address")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        frag_path = tdp / f"{slug}.frag.html"
        proc = subprocess.run(
            [VENV_PY, str(VAL_GEN), "--address", addr, "--collection", suburb, "--out", str(frag_path)],
            capture_output=True, text=True, timeout=GEN_TIMEOUT, cwd=str(VAL_GEN.parent),
        )
        if proc.returncode != 0 or not frag_path.exists():
            # the generator refuses directional-only / no-reconciled valuations
            return {"ok": False, "kind": "valuation-report", "slug": slug, "declined": True,
                    "error": f"generator rc={proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}"}
        full = _wrap_valuation_html(frag_path.read_text(encoding="utf-8"))
        full_path = tdp / f"{slug}.html"
        full_path.write_text(full, encoding="utf-8")
        html_url = upload("valuation-report", f"{slug}.html", full.encode("utf-8"), content_type="text/html")

        cover_url = None
        cover_path = tdp / f"{slug}.cover.jpg"
        cover_env = {**os.environ, "NODE_PATH": WEBSITE_NODE_MODULES}
        cover_proc = subprocess.run(
            ["node", str(COVER_RENDER), str(full_path), str(cover_path)],
            capture_output=True, text=True, timeout=120, cwd=str(REPO), env=cover_env,
        )
        if cover_path.exists():
            cover_url = upload("valuation-report", f"covers/{slug}.jpg", cover_path.read_bytes(),
                               content_type="image/jpeg")
        elif verbose:
            print(f"  cover render failed: {(cover_proc.stderr or cover_proc.stdout)[-300:]}")

        ok = bool(html_url)
        if verbose:
            print(f"[valuation-report] {slug}: html={html_url} cover={cover_url}")
        return {"ok": ok, "kind": "valuation-report", "slug": slug,
                "html_url": html_url, "cover_url": cover_url}


def publish(slug: str, kind: str, verbose: bool = True) -> list[dict]:
    out = []
    if kind in ("market-update", "both"):
        out.append(publish_market_update(slug, verbose=verbose))
    if kind in ("valuation-report", "both"):
        out.append(publish_valuation_report(slug, verbose=verbose))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--kind", default="both", choices=["market-update", "valuation-report", "both"])
    args = ap.parse_args()
    _load_env()
    results = publish(args.slug, args.kind)
    failed = [r for r in results if not r.get("ok")]
    for r in failed:
        print(f"FAIL {r.get('kind')}: {r.get('error')}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
