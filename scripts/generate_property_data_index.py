#!/usr/bin/env python3
"""
generate_property_data_index.py — the failsafe map of WHERE property data lives.

Why this exists
---------------
Finding where property *photos* (and other assets) are stored has burned us
repeatedly: the answer is spread across ~a dozen fields, several hosts, some
dead (retired Azure `fieldspropertyimages`), some external (Domain CDN, rotates),
some our own blob (`blobs.fieldsestate.com.au`), under different path roots
(`reports/`, `aerial/`, `cadastral/`, `gold_coast/`...). A hand-written note
rots the moment a field is added — exactly how SCHEMA_SNAPSHOT.md misled us.

So this is GENERATED from live data, never hand-maintained. It produces:

  PROPERTY_DATA_INDEX.md   — human-readable: photo/asset resolution order (parsed
                             from the live website code), a tagged asset catalog
                             with host + liveness + coverage, and the blob layout.
  PROPERTY_DATA_INDEX.tsv  — every schema path, semantically TAGGED, grep-able.

Retrieval procedure (READ THIS BEFORE claiming data is missing — cf. Rule 8):
  1. Need a value?  grep PROPERTY_DATA_INDEX.tsv for the tag, not a guessed name.
  2. Need photos?   Follow the "Photo resolution order" section verbatim. It is
                    the SAME order the live site uses (extractPhotos).
  3. Verify over HTTP, never the VM filesystem: this VM's /data/blobs is a
     PARTIAL mirror (aerials/livingmap are generated here; facades live on the
     blob host). A 404 on blobs.fieldsestate.com.au is truth; a missing local
     dir is not.

Self-monitors via job_run (Rule 7) with a zero-output assertion (Rule 7b):
if it finds no image fields, the scan is broken, not the data — it raises.
"""
import os, re, sys, json, socket
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

import requests
from shared.db import get_client
from job_status import job_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_TSV = os.path.join(ROOT, "SCHEMA_PATHS.tsv")
SHARED_UTILS = "/home/fields/Feilds_Website/01_Website/netlify/functions/shared-utils.mjs"
OUT_MD = os.path.join(ROOT, "PROPERTY_DATA_INDEX.md")
OUT_TSV = os.path.join(ROOT, "PROPERTY_DATA_INDEX.tsv")
BLOB_HTTP = "https://blobs.fieldsestate.com.au"
LOCAL_BLOB = "/data/blobs/property-images"

# Collections representative of Gold_Coast.* (image field SHAPES are uniform).
SAMPLE_COLLECTIONS = ["robina", "varsity_lakes", "burleigh_waters"]
SAMPLE_SIZE = 400

AEST = timezone(timedelta(hours=10))

# ---------------------------------------------------------------------------
# Host classification — the crux of the recurring confusion.
# ---------------------------------------------------------------------------
def classify_host(host: str) -> tuple[str, str]:
    """Return (status, note). status in DEAD/OWNED/DOMAIN/OTHER."""
    h = host.lower()
    if "fieldspropertyimages.blob.core.windows.net" in h:
        return "DEAD", "Azure account retired 2026-05-13 (NXDOMAIN). Never use."
    if "blobs.fieldsestate.com.au" in h:
        return "OWNED", "Our blob (nginx /data/blobs). Ours to publish. Durable."
    if any(x in h for x in ("domainstatic.com.au", "domain.com.au", "rimh2", "bucket-api.domain")):
        return "DOMAIN", "Domain CDN — external, live but ROTATES off; not licensed for paid ads. Mirror before reuse."
    if "blob.core.windows.net" in h:
        return "AZURE?", "Other Azure blob — verify liveness."
    return "OTHER", ""

# Asset type tag from a field path.
ASSET_RULES = [
    (r"aerial|boundary",                  "aerial"),
    (r"satellite",                        "satellite"),
    (r"cadastral",                        "cadastral_street"),
    (r"street_?view",                     "street_view"),
    (r"living_?map",                      "living_map"),
    (r"floor_?plan|house_plan",           "floor_plan"),
    (r"hero",                             "hero_facade"),
    (r"thumb",                            "thumbnail"),
    (r"photo|image|\.images",             "facade_gallery"),
]
def asset_type(path: str) -> str:
    p = path.lower()
    for rx, tag in ASSET_RULES:
        if re.search(rx, p):
            return tag
    return "image_other"

# Semantic domain tags for the FULL field dictionary (ordered; first match wins).
DOMAIN_RULES = [
    (r"^_id$|address|suburb|postcode|^lat$|^lng$|latitude|longitude|geo|gnaf|property_id|slug", "identity_location"),
    (r"bedroom|bathroom|car|parking|land_?(size|area)|floor_?area|building_area|property_type|attributes|parsed_rooms|room", "physical_attributes"),
    (r"valuation|reconciled|comparable|comps|catboost|npui|confidence|adjust|price_estimate", "valuation"),
    (r"aerial|satellite|cadastral|street_?view|living_?map|floor_?plan|hero|thumb|photo|image|\.images|blob", "images_assets"),
    (r"ai_analysis|editorial|narrative|reflection|fact_?check|insight|positioning", "editorial_ai"),
    (r"market|absorption|median|days_on_market|dom|trend|pulse|seasonal", "market_metrics"),
    (r"transaction|sold|sale_price|sold_date|price_history|last_sold", "transactions_history"),
    (r"listing_status|list_price|agent|domain_|scraped_data|onthehouse|withdrawn|under_contract", "listing_scrape"),
    (r"offmarket|off_market|scarcity|rarity|ladder|report|minisite|owner|occupancy", "offmarket_report"),
    (r"processing_status|_updated_at|_uploaded|backfill|job|pipeline|_source|provenance|schema_version", "pipeline_meta"),
]
def domain_tag(path: str) -> str:
    p = path.lower()
    for rx, tag in DOMAIN_RULES:
        if re.search(rx, p):
            return tag
    return "other"

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")

def walk(o, prefix=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(o, list):
        for v in o[:3]:
            yield from walk(v, f"{prefix}[]")
    elif isinstance(o, str):
        yield prefix, o

def is_image_url(s: str) -> bool:
    if not isinstance(s, str) or not s.startswith("http"):
        return False
    low = s.lower().split("?")[0]
    return low.endswith(IMG_EXT) or "image" in low or "photo" in low or "/bucket/" in low

# ---------------------------------------------------------------------------
def parse_resolution_order(func_name: str) -> list[str]:
    """Pull the numbered 'Order of preference' list from a shared-utils fn docstring."""
    try:
        txt = open(SHARED_UTILS).read()
    except Exception:
        return []
    idx = txt.find(f"export function {func_name}")
    if idx == -1:
        return []
    doc = txt[max(0, idx - 2500):idx]
    m = re.search(r"Order of preference:(.*?)\*/", doc, re.S)
    if not m:
        return []
    lines = []
    for ln in m.group(1).splitlines():
        s = ln.strip().lstrip("*").strip()
        mm = re.match(r"\d+\.\s*(.+)", s)
        if mm:
            lines.append(mm.group(1).strip())
        elif lines and s and not s.startswith(("—", "-")):
            lines[-1] += " " + s  # continuation
    return lines

def http_status(url: str, timeout=7) -> int:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, timeout=timeout, stream=True)
        return r.status_code
    except Exception:
        return 0

def main():
    with job_run("property_data_index", cadence_hours=168,
                 title="Property Data & Asset Index") as beat:
        client = get_client()
        gc = client["Gold_Coast"]

        # ---- 1. Scan for asset fields across representative collections -----
        asset_paths = defaultdict(lambda: {"hosts": Counter(), "count": 0, "sample": None})
        total_docs = 0
        for coll in SAMPLE_COLLECTIONS:
            try:
                docs = list(gc[coll].aggregate([{"$sample": {"size": SAMPLE_SIZE}}]))
            except Exception:
                docs = list(gc[coll].find().limit(SAMPLE_SIZE))
            total_docs += len(docs)
            for d in docs:
                seen_paths = set()
                for path, val in walk(d):
                    if not is_image_url(val):
                        continue
                    host = val.split("/")[2] if "://" in val else "?"
                    rec = asset_paths[path]
                    rec["hosts"][host] += 1
                    if path not in seen_paths:
                        rec["count"] += 1
                        seen_paths.add(path)
                    if rec["sample"] is None:
                        rec["sample"] = val

        if not asset_paths:
            # Rule 7b: zero image fields means the SCAN is broken, not the data.
            raise RuntimeError(
                "found 0 image-URL fields across %d docs — walker or host list is broken"
                % total_docs)

        # ---- 2. Liveness probe, cached per host ----------------------------
        host_status = {}
        for rec in asset_paths.values():
            for host in rec["hosts"]:
                if host not in host_status and rec["sample"] and host in rec["sample"]:
                    host_status[host] = http_status(rec["sample"])
        # ensure every host gets one probe using any sample carrying it
        for path, rec in asset_paths.items():
            for host in rec["hosts"]:
                if host not in host_status:
                    host_status[host] = 0

        # ---- 3. Blob storage layout (local mirror + public HTTP) -----------
        blob_rows = []
        if os.path.isdir(LOCAL_BLOB):
            for root in sorted(os.listdir(LOCAL_BLOB)):
                p = os.path.join(LOCAL_BLOB, root)
                if not os.path.isdir(p):
                    continue
                try:
                    nfiles = sum(len(f) for _, _, f in os.walk(p) for f in [f])
                except Exception:
                    nfiles = -1
                blob_rows.append((root, nfiles))

        # ---- 4. Resolution orders parsed from live website code ------------
        photo_order = parse_resolution_order("extractPhotos")
        fp_order = parse_resolution_order("extractFloorPlans")

        # ---- 5. Tag the FULL field dictionary from SCHEMA_PATHS.tsv ---------
        tag_counts = Counter()
        tsv_lines = ["path\tdomain_tag\tasset_type\tfill\ttypes"]
        img_field_paths = 0
        if os.path.exists(SCHEMA_TSV):
            with open(SCHEMA_TSV) as f:
                next(f, None)
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 5:
                        continue
                    dbn, coll, path, fill, types = parts[:5]
                    if dbn != "Gold_Coast" or coll not in SAMPLE_COLLECTIONS:
                        continue
                    dtag = domain_tag(path)
                    atag = asset_type(path) if dtag == "images_assets" else ""
                    tag_counts[dtag] += 1
                    if dtag == "images_assets":
                        img_field_paths += 1
                    tsv_lines.append(f"{path}\t{dtag}\t{atag}\t{fill}\t{types}")

        # ---- 6. Emit -------------------------------------------------------
        stamp = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
        md = []
        md.append(f"# Property Data & Asset Index\n")
        md.append(f"> **Generated {stamp}** by `scripts/generate_property_data_index.py` "
                  f"(weekly). Do NOT hand-edit — regenerate. Companion: `PROPERTY_DATA_INDEX.tsv` "
                  f"(every field, tagged, grep-able).\n")
        md.append("## ⛑ Retrieval procedure (read before claiming data is missing — Rule 8)\n")
        md.append("1. **Any field:** `grep <tag> PROPERTY_DATA_INDEX.tsv` or "
                  "`python3 scripts/db_fields.py --find <word>` — never a guessed name.\n"
                  "2. **Photos:** follow *Photo resolution order* below verbatim — it is the "
                  "same order the live site uses (`extractPhotos`).\n"
                  "3. **Verify over HTTP, not the VM disk.** This VM's `/data/blobs` is a "
                  "PARTIAL mirror. A 404 on `blobs.fieldsestate.com.au` is truth; a missing "
                  "local dir is not.\n")

        md.append("\n## 📸 Photo resolution order (canonical — from `shared-utils.mjs`)\n")
        if photo_order:
            for i, s in enumerate(photo_order, 1):
                md.append(f"{i}. {s}")
        else:
            md.append("_(could not parse — check shared-utils.mjs extractPhotos)_")
        md.append("\n**Floor plans:**")
        for i, s in enumerate(fp_order, 1):
            md.append(f"{i}. {s}")
        md.append("\n> ⚠ The mini-site (`/yourhome`, `property_reports.property.photos[]`) "
                  "mirrors the chosen Domain photos to **our own blob** under "
                  "`property-images/reports/<suburb>/<id>/` at build time. That is where we "
                  "hold owned copies of off-market facades — not `gold_coast/` (that path's "
                  "URLs are dead Azure).\n")

        md.append("\n## 🗂 Asset field catalog (sampled, live)\n")
        md.append("| Field path | Asset type | Host(s) | Status | Coverage |")
        md.append("|---|---|---|---|---|")
        def cov(rec):
            return f"{rec['count']}/{total_docs} ({rec['count']/total_docs*100:.0f}%)"
        for path in sorted(asset_paths, key=lambda p: (-asset_paths[p]["count"], p)):
            rec = asset_paths[path]
            host_bits = []
            for host, n in rec["hosts"].most_common():
                st, _ = classify_host(host)
                code = host_status.get(host, 0)
                if st == "DEAD":
                    live = "🔴"  # NXDOMAIN probes as 0; it is dead, not unprobed
                else:
                    live = "🟢" if 200 <= code < 400 else ("🔴" if code else "⚪")
                host_bits.append(f"{live}{st}")
            statuses = " ".join(dict.fromkeys(host_bits))
            hosts = "<br>".join(f"`{h}`" for h in list(rec["hosts"])[:3])
            md.append(f"| `{path}` | {asset_type(path)} | {hosts} | {statuses} | {cov(rec)} |")
        md.append("\n_Status legend: 🟢 live · 🔴 dead · ⚪ unprobed · "
                  "DEAD=retired Azure · OWNED=our blob · DOMAIN=external CDN (rotates)._\n")

        md.append("\n## 💾 Blob storage layout (`/data/blobs/property-images/` on blob host)\n")
        md.append("| Root | Files (this VM's partial mirror) | Holds |")
        md.append("|---|---|---|")
        ROOT_NOTES = {
            "reports": "**Owned facade mirror per built mini-site** — the off-market photos we hold",
            "aerial": "Living-Map boundary aerials (generated here)",
            "cadastral": "Street-level cadastral photos",
            "livingmap": "Living-Map tiles (house/street/suburb)",
            "gold_coast": "Legacy listing-photo path — URLs in DB are DEAD Azure",
            "for_sale": "On-market listing photos (kept fresh)",
            "sold": "Sold listing photos",
            "all": "Satellite/aerial per property",
        }
        for root, n in blob_rows:
            md.append(f"| `{root}/` | {n:,} | {ROOT_NOTES.get(root, '')} |")
        md.append("\n> ⚠ Counts above are THIS VM's disk, a partial mirror. Truth = HTTP GET "
                  "`https://blobs.fieldsestate.com.au/property-images/<root>/...`.\n")

        md.append("\n## 🏷 Field dictionary — tag summary (Gold_Coast target suburbs)\n")
        md.append("| Domain tag | # field paths |")
        md.append("|---|---|")
        for tag, n in tag_counts.most_common():
            md.append(f"| {tag} | {n} |")
        md.append(f"\nFull tagged list: **`PROPERTY_DATA_INDEX.tsv`** ({len(tsv_lines)-1} paths). "
                  f"Example: `grep -P '\\timages_assets\\t' PROPERTY_DATA_INDEX.tsv`.\n")

        with open(OUT_MD, "w") as f:
            f.write("\n".join(md) + "\n")
        with open(OUT_TSV, "w") as f:
            f.write("\n".join(tsv_lines) + "\n")

        live_hosts = sum(1 for c in host_status.values() if 200 <= c < 400)
        beat.metrics = {
            "asset_fields": len(asset_paths),
            "hosts": len(host_status),
            "live_hosts": live_hosts,
            "tagged_paths": len(tsv_lines) - 1,
            "image_field_paths": img_field_paths,
            "blob_roots": len(blob_rows),
        }
        beat.detail = (f"{len(asset_paths)} asset fields across {len(host_status)} hosts "
                       f"({live_hosts} live); {len(tsv_lines)-1} paths tagged")
        print("Wrote", OUT_MD, "and", OUT_TSV)
        print(beat.detail)

if __name__ == "__main__":
    main()
