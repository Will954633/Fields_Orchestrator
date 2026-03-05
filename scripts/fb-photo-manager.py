#!/usr/bin/env python3
"""
Facebook Photo Manager — manages the Fields local photography library.

Syncs photo inventory from GitHub (Will954633/fields-local-photography),
tracks which photos have been posted, selects the next photo with theme
rotation, downloads photos for posting, and generates data-connected captions.

Usage:
    python3 scripts/fb-photo-manager.py sync              # Sync inventory from GitHub
    python3 scripts/fb-photo-manager.py status             # Show inventory stats
    python3 scripts/fb-photo-manager.py select             # Pick next photo to post
    python3 scripts/fb-photo-manager.py caption FILE_PATH  # Generate caption for a photo
    python3 scripts/fb-photo-manager.py post               # Select + caption + post to FB
    python3 scripts/fb-photo-manager.py post --dry-run     # Preview without posting
"""

import os
import sys
import json
import re
import subprocess
import argparse
import base64
import tempfile
from datetime import datetime, timezone, timedelta
from collections import Counter
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    try:
        for line in open("/etc/environment"):
            if line.startswith("ANTHROPIC_API_KEY="):
                ANTHROPIC_API_KEY = line.split("=", 1)[1].strip().strip('"')
                break
    except Exception:
        pass
GITHUB_REPO = "Will954633/fields-local-photography"
GH_CONFIG_DIR = "/home/projects/.config/gh"
VENV_PYTHON = "/home/fields/venv/bin/python3"
SCRIPTS_DIR = "/home/fields/Fields_Orchestrator/scripts"

# Theme keywords for auto-categorisation from filenames
THEME_RULES = [
    ("aerials",     ["arial", "aerial", "drone", "above", "directly_down"]),
    ("sunsets",     ["sunrise", "sunset", "golden"]),
    ("beaches",     ["beach", "sea_kiak", "sea_kayak", "surf", "currumbin", "sand"]),
    ("coastal",     ["headland", "boardwalk", "board_walk"]),
    ("waterways",   ["lake", "canal", "river", "creek"]),
    ("lifestyle",   ["cricket", "exercise", "morning", "fam", "family", "play", "cafe", "market"]),
    ("landmarks",   ["bond", "university", "town_centre", "robina_town", "school"]),
]

# Location keywords to map photos to suburbs
LOCATION_MAP = {
    "burleigh": "Burleigh",
    "robina": "Robina",
    "varsity": "Varsity Lakes",
    "bond": "Robina",  # Bond Uni is in Robina
    "currumbin": "Currumbin",
    "pippen": "Robina",  # Bill Pippen oval is in Robina
    "tallebudgera": "Tallebudgera",
    "miami": "Miami",
    "palm_beach": "Palm Beach",
}


def classify_photo(filename):
    """Extract theme and location from a filename like Location_Burleigh_Headland_Boardwalk_WEB.jpg"""
    name_lower = filename.lower().replace(".jpg", "").replace(".jpeg", "").replace(".png", "")

    # Strip common prefixes/suffixes
    name_clean = name_lower.replace("location_", "")
    for suffix in ["_web", "_bw", "_v2", "_v3", "_v4"]:
        name_clean = name_clean.replace(suffix, "")

    # Detect theme
    theme = "general"
    for theme_name, keywords in THEME_RULES:
        if any(kw in name_clean for kw in keywords):
            theme = theme_name
            break

    # Detect location
    location = "Gold Coast"
    for keyword, loc in LOCATION_MAP.items():
        if keyword in name_clean:
            location = loc
            break

    # Is this a web-optimised version?
    is_web = "_web" in name_lower

    # Is this black & white?
    is_bw = "_bw" in name_lower and "burleigh_waters" not in name_lower

    # Build a human-readable description from the filename
    desc_parts = name_clean.split("_")
    # Remove numbers and single chars
    desc_parts = [p for p in desc_parts if len(p) > 1 and not p.isdigit()]
    description = " ".join(desc_parts).title()

    return {
        "theme": theme,
        "location": location,
        "is_web_optimised": is_web,
        "is_bw": is_bw,
        "description": description,
    }


def gh_api(endpoint, method="GET", **kwargs):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint]
    if method != "GET":
        cmd.extend(["--method", method])
    for key, val in kwargs.items():
        if key == "jq":
            cmd.extend(["--jq", val])
        elif key == "field":
            for f in val if isinstance(val, list) else [val]:
                cmd.extend(["--field", f])

    env = {**os.environ, "GH_CONFIG_DIR": GH_CONFIG_DIR}
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr[:300]}")
    return result.stdout.strip()


def sync_inventory():
    """Pull file list from GitHub repo and update MongoDB inventory."""
    print("Syncing photo inventory from GitHub...")

    # Get repo tree recursively
    try:
        tree_json = gh_api(
            f"repos/{GITHUB_REPO}/git/trees/main?recursive=1",
            jq=".tree"
        )
        tree = json.loads(tree_json)
    except Exception as e:
        # Fallback: list contents of root
        print(f"Tree API failed ({e}), trying contents API...")
        tree = []
        _scan_directory(tree, "")

    # Filter to image files only
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photos = []
    for item in tree:
        path = item.get("path", "")
        ext = os.path.splitext(path)[1].lower()
        if item.get("type") in ("blob", "file") and ext in image_extensions:
            filename = os.path.basename(path)
            folder = os.path.dirname(path)

            # Theme from folder name if in a themed folder, otherwise auto-classify
            if folder and folder.lower() not in ("", ".", "high"):
                theme = folder.lower().split("/")[-1]
                meta = classify_photo(filename)
                meta["theme"] = theme
            else:
                meta = classify_photo(filename)

            photos.append({
                "path": path,
                "filename": filename,
                "folder": folder,
                "theme": meta["theme"],
                "location": meta["location"],
                "description": meta["description"],
                "is_web_optimised": meta["is_web_optimised"],
                "is_bw": meta["is_bw"],
                "size": item.get("size", 0),
                "sha": item.get("sha", ""),
            })

    if not photos:
        print("No photos found in repository.")
        return

    # Update MongoDB
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    col = sm["photo_inventory"]

    # Upsert each photo
    new_count = 0
    updated_count = 0
    for photo in photos:
        existing = col.find_one({"path": photo["path"]})
        if existing:
            # Update metadata but preserve posted status
            col.update_one(
                {"path": photo["path"]},
                {"$set": {
                    "filename": photo["filename"],
                    "folder": photo["folder"],
                    "theme": photo["theme"],
                    "location": photo["location"],
                    "description": photo["description"],
                    "is_web_optimised": photo["is_web_optimised"],
                    "is_bw": photo["is_bw"],
                    "size": photo["size"],
                    "sha": photo["sha"],
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            updated_count += 1
        else:
            col.insert_one({
                **photo,
                "posted": False,
                "posted_at": None,
                "post_id": None,
                "caption_used": None,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            })
            new_count += 1

    # Remove photos that no longer exist in repo
    repo_paths = {p["path"] for p in photos}
    all_db = col.find({}, {"path": 1})
    removed = 0
    for doc in all_db:
        if doc["path"] not in repo_paths:
            col.delete_one({"_id": doc["_id"]})
            removed += 1

    client.close()
    print(f"Sync complete: {new_count} new, {updated_count} updated, {removed} removed")
    print(f"Total photos in inventory: {len(photos)}")


def _scan_directory(tree, path):
    """Recursively scan GitHub directory contents."""
    endpoint = f"repos/{GITHUB_REPO}/contents/{path}" if path else f"repos/{GITHUB_REPO}/contents"
    try:
        raw = gh_api(endpoint)
        items = json.loads(raw)
        if not isinstance(items, list):
            return
        for item in items:
            if item.get("type") == "file":
                tree.append({
                    "path": item["path"],
                    "type": "blob",
                    "size": item.get("size", 0),
                    "sha": item.get("sha", ""),
                })
            elif item.get("type") == "dir" and item["name"] not in (".git", "node_modules"):
                _scan_directory(tree, item["path"])
    except Exception as e:
        print(f"  Warning: could not scan {path}: {e}")


def show_status():
    """Show inventory statistics."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    col = sm["photo_inventory"]

    total = col.count_documents({})
    posted = col.count_documents({"posted": True})
    available = col.count_documents({"posted": {"$ne": True}})

    print(f"\n--- Photo Inventory ---")
    print(f"Total:     {total}")
    print(f"Posted:    {posted}")
    print(f"Available: {available}")

    if total == 0:
        print("\nNo photos in inventory. Run 'sync' first.")
        client.close()
        return

    # Days of content remaining
    if available > 0:
        print(f"Days of daily content: ~{available} days")

    # Theme breakdown
    pipeline = [
        {"$group": {"_id": "$theme", "total": {"$sum": 1},
                     "available": {"$sum": {"$cond": [{"$ne": ["$posted", True]}, 1, 0]}}}},
        {"$sort": {"total": -1}}
    ]
    themes = list(col.aggregate(pipeline))
    if themes:
        print(f"\nBy theme:")
        for t in themes:
            print(f"  {t['_id']:15s} — {t['available']}/{t['total']} available")

    # Location breakdown
    pipeline = [
        {"$group": {"_id": "$location", "total": {"$sum": 1},
                     "available": {"$sum": {"$cond": [{"$ne": ["$posted", True]}, 1, 0]}}}},
        {"$sort": {"total": -1}}
    ]
    locations = list(col.aggregate(pipeline))
    if locations:
        print(f"\nBy location:")
        for loc in locations:
            print(f"  {loc['_id']:20s} — {loc['available']}/{loc['total']} available")

    # Recently posted
    recent = list(col.find({"posted": True}).sort("_id", -1).limit(5))
    if recent:
        print(f"\nRecently posted:")
        for p in recent:
            print(f"  {p.get('posted_at', 'N/A')[:10]} — {p['filename']} ({p['theme']})")

    client.close()


def select_next_photo():
    """Select the next photo to post, rotating themes."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    col = sm["photo_inventory"]

    available = list(col.find({"posted": {"$ne": True}}))
    if not available:
        print("No unposted photos available!")
        client.close()
        return None

    # Get recently posted themes to avoid repeating
    recent_posted = list(col.find(
        {"posted": True}
    ).sort("_id", -1).limit(5))
    recent_themes = [p.get("theme") for p in recent_posted]

    # Score each photo: prefer themes not recently used
    scored = []
    for photo in available:
        score = 0
        theme = photo.get("theme", "general")

        # Prefer web-optimised versions
        if photo.get("is_web_optimised"):
            score += 2

        # Prefer colour over B&W (B&W should be occasional)
        if not photo.get("is_bw"):
            score += 1

        # Theme rotation: penalty for recently used themes
        if theme in recent_themes:
            idx = recent_themes.index(theme)
            score -= (5 - idx)  # More recent = bigger penalty
        else:
            score += 3  # Bonus for unused theme

        scored.append((score, photo))

    # Sort by score descending, then add some randomness within top tier
    scored.sort(key=lambda x: -x[0])

    # Pick from top 3 candidates (slight randomness)
    import random
    top_n = min(3, len(scored))
    selected = random.choice(scored[:top_n])[1]

    client.close()
    return selected


def download_photo(photo_path):
    """Download a photo from GitHub to a temp file. Returns local path."""
    print(f"Downloading {photo_path} from GitHub...")

    # URL-encode the path for the API
    encoded_path = photo_path.replace(" ", "%20")
    raw = gh_api(f"repos/{GITHUB_REPO}/contents/{encoded_path}", jq=".content")

    # Decode base64 content
    content = base64.b64decode(raw)

    ext = os.path.splitext(photo_path)[1].lower() or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, prefix="fields_photo_", delete=False,
                                       dir="/tmp")
    tmp.write(content)
    tmp.close()
    print(f"Downloaded to {tmp.name} ({len(content):,} bytes)")
    return tmp.name


def get_live_data_context():
    """Pull live listing data for caption generation."""
    client = MongoClient(COSMOS_URI)
    fs_db = client["Gold_Coast_Currently_For_Sale"]

    context = {}
    target_suburbs = ["robina", "burleigh_waters", "varsity_lakes"]

    for suburb in target_suburbs:
        try:
            listings = list(fs_db[suburb].find({}, {
                "price": 1, "bedrooms": 1, "property_type": 1, "address": 1,
            }))
            if not listings:
                continue

            prices = []
            for l in listings:
                p = l.get("price", "")
                if isinstance(p, str):
                    match = re.search(r'\$[\d,]+(?:\.\d+)?', p)
                    if match:
                        num_str = match.group().replace("$", "").replace(",", "")
                        try:
                            val = int(float(num_str))
                            if 100000 < val < 20000000:
                                prices.append(val)
                        except (ValueError, TypeError):
                            pass

            display = {"robina": "Robina", "burleigh_waters": "Burleigh Waters",
                       "varsity_lakes": "Varsity Lakes"}

            context[suburb] = {
                "name": display.get(suburb, suburb),
                "total_listings": len(listings),
                "median_price": sorted(prices)[len(prices) // 2] if prices else None,
                "price_range": f"${min(prices):,} to ${max(prices):,}" if prices else "N/A",
            }
        except Exception:
            pass

    # Suburb statistics if available
    stats = fs_db["suburb_statistics"]
    for doc in stats.find({}, {"_id": 0, "suburb": 1, "median_price": 1,
                                "avg_days_on_market": 1, "total_listings": 1}):
        sub = doc.get("suburb", "")
        if sub in context:
            context[sub]["avg_days_on_market"] = doc.get("avg_days_on_market")
            if doc.get("median_price"):
                context[sub]["median_price"] = doc["median_price"]

    client.close()
    return context


def generate_caption(photo, market_data=None):
    """Generate a data-connected caption for a photo using Claude."""
    if not ANTHROPIC_API_KEY:
        # Fallback: simple caption without AI
        return _fallback_caption(photo, market_data)

    import anthropic

    if market_data is None:
        market_data = get_live_data_context()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = """You write short, compelling Facebook photo captions for Fields Estate, a property intelligence platform on the Gold Coast, Australia.

Rules:
- 2-3 sentences maximum. Short and punchy.
- First sentence: describe the scene/moment in the photo (based on filename clues).
- Second sentence: connect it to WHY people live here or what it means for buyers/sellers. Include ONE specific data point from the market data if relevant.
- Optional third sentence: a subtle call to explore (link to fieldsestate.com.au, never pushy).
- Tone: authentic, local, data-informed. Like a knowledgeable neighbour, not an agent.
- NEVER use: "stunning", "nestled", "boasting", "rare opportunity", "robust market", "dream home"
- Numbers: $1,250,000 not "$1.25m", suburbs always capitalised
- End with a location pin: e.g. "📍 Burleigh Headland"
- No hashtags. No emojis except the 📍 pin.
- Brand: "Know your ground" — Fields Estate"""

    user_msg = f"""Photo details:
- Filename: {photo['filename']}
- Theme: {photo['theme']}
- Location: {photo['location']}
- Description: {photo['description']}
- Black & white: {photo.get('is_bw', False)}

Live market data:
{json.dumps(market_data, indent=2, default=str)}

Write a caption for this photo."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    caption = response.content[0].text.strip()
    # Remove any wrapping quotes
    if caption.startswith('"') and caption.endswith('"'):
        caption = caption[1:-1]

    return caption


def _fallback_caption(photo, market_data):
    """Simple caption without AI."""
    location = photo.get("location", "Gold Coast")
    theme = photo.get("theme", "general")
    desc = photo.get("description", "")

    # Find closest suburb data
    suburb_data = None
    for key, data in (market_data or {}).items():
        if location.lower().replace(" ", "_") in key or location.lower() in data.get("name", "").lower():
            suburb_data = data
            break

    caption = f"{desc}."
    if suburb_data:
        total = suburb_data.get("total_listings", "")
        caption += f" {suburb_data['name']} has {total} properties currently for sale."
    caption += f"\n\n📍 {location}\nfieldsestate.com.au"
    return caption


def post_photo(photo, caption, dry_run=False):
    """Post photo to Facebook page and update tracking."""
    if dry_run:
        print(f"\n--- DRY RUN ---")
        print(f"Photo: {photo['filename']}")
        print(f"Theme: {photo['theme']}")
        print(f"Location: {photo['location']}")
        print(f"\nCaption:\n{caption}")
        print(f"\n(Add --post to publish)")
        return None

    # Download photo
    local_path = download_photo(photo["path"])

    try:
        # Post via fb-page-post.py
        cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py",
               "--message", caption, "--image", local_path, "--post"]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )

        post_id = None
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()

            # Mark photo as posted
            client = MongoClient(COSMOS_URI)
            sm = client["system_monitor"]
            sm["photo_inventory"].update_one(
                {"path": photo["path"]},
                {"$set": {
                    "posted": True,
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                    "post_id": post_id,
                    "caption_used": caption[:500],
                }}
            )
            client.close()

            print(f"Posted! Post ID: {post_id}")
            return post_id
        else:
            print(f"FAILED: {result.stderr[:300]}")
            return None
    finally:
        # Clean up temp file
        if os.path.exists(local_path):
            os.remove(local_path)


def main():
    parser = argparse.ArgumentParser(description="Fields Photo Manager")
    parser.add_argument("command", choices=["sync", "status", "select", "caption", "post"],
                        help="Command to run")
    parser.add_argument("file_path", nargs="?", help="Photo path (for caption command)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--caption", type=str, help="Override auto-generated caption")
    args = parser.parse_args()

    if args.command == "sync":
        sync_inventory()

    elif args.command == "status":
        show_status()

    elif args.command == "select":
        photo = select_next_photo()
        if photo:
            print(f"\nSelected: {photo['filename']}")
            print(f"  Theme:    {photo['theme']}")
            print(f"  Location: {photo['location']}")
            print(f"  Path:     {photo['path']}")
            print(f"  Desc:     {photo['description']}")

    elif args.command == "caption":
        if not args.file_path:
            print("ERROR: caption command requires a file path")
            sys.exit(1)
        # Look up photo in inventory
        client = MongoClient(COSMOS_URI)
        sm = client["system_monitor"]
        photo = sm["photo_inventory"].find_one({"path": args.file_path})
        client.close()
        if not photo:
            print(f"Photo not found in inventory: {args.file_path}")
            sys.exit(1)
        market_data = get_live_data_context()
        caption = generate_caption(photo, market_data)
        print(f"\nCaption for {photo['filename']}:\n")
        print(caption)

    elif args.command == "post":
        # Full flow: select + caption + post
        photo = select_next_photo()
        if not photo:
            print("No photos available to post.")
            sys.exit(1)

        print(f"Selected: {photo['filename']} ({photo['theme']}, {photo['location']})")

        if args.caption:
            caption = args.caption
        else:
            print("Generating caption...")
            market_data = get_live_data_context()
            caption = generate_caption(photo, market_data)

        post_photo(photo, caption, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
