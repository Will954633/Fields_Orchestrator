#!/usr/bin/env python3
"""
Marketing Executor — picks up approved marketing actions and executes them.

Polls system_monitor.marketing_actions for status='approved',
executes each action, and updates the status to 'executed' or 'failed'.

Usage:
    python3 scripts/marketing-executor.py              # Execute all approved actions
    python3 scripts/marketing-executor.py --dry-run     # Show what would execute
"""

import os
import sys
import json
import uuid
import subprocess
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
ADS_TOKEN = os.environ.get("FACEBOOK_ADS_TOKEN", "")
AD_ACCOUNT_ID = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "").replace("act_", "")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
FB_BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "")
SCRIPTS_DIR = "/home/fields/Fields_Orchestrator/scripts"
VENV_PYTHON = "/home/fields/venv/bin/python3"


def get_approved_actions():
    """Fetch all approved actions from the queue."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    actions = list(sm["marketing_actions"].find(
        {"status": "approved"}
    ))
    actions.sort(key=lambda x: x.get("priority", 2))  # priority 1 first, in-memory sort
    client.close()
    return actions


def update_action_status(action_id, status, result=None):
    """Update action status in MongoDB."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    update = {
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if result:
        update["execution_result"] = result
    sm["marketing_actions"].update_one(
        {"_id": action_id},
        {"$set": update}
    )
    client.close()


def execute_article_post(action):
    """Execute a suggest_article_post action — post insight with article link."""
    details = action.get("details", {})
    insight_text = details.get("insight_text", "")
    article_url = details.get("article_url", "")
    article_id = details.get("article_id", "")
    article_title = details.get("article_title", "")
    audience = details.get("audience", "")

    if not insight_text:
        return {"success": False, "error": "No insight_text in action details"}
    if not article_url:
        return {"success": False, "error": "No article_url in action details"}

    cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py",
           "--message", insight_text, "--link", article_url, "--post"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )
        if result.returncode == 0:
            post_id = None
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()
            return {
                "success": True,
                "post_id": post_id,
                "article_id": article_id,
                "article_title": article_title,
                "audience": audience,
                "output": result.stdout[-500:],
            }
        else:
            return {
                "success": False,
                "error": result.stderr[-500:],
                "output": result.stdout[-500:],
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timed out after 30s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_page_post(action):
    """Execute a suggest_page_post action."""
    details = action.get("details", {})
    message = details.get("message", "")
    link = details.get("link")

    if not message:
        return {"success": False, "error": "No message in action details"}

    # Call fb-page-post.py with the message
    cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py", "--message", message, "--post"]
    if link:
        cmd.extend(["--link", link])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )
        if result.returncode == 0:
            # Extract post ID from output
            post_id = None
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()
            return {
                "success": True,
                "post_id": post_id,
                "output": result.stdout[-500:],
            }
        else:
            return {
                "success": False,
                "error": result.stderr[-500:],
                "output": result.stdout[-500:],
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timed out after 30s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_pipeline_run(action):
    """Execute a suggest_pipeline_run action."""
    details = action.get("details", {})
    pipeline = details.get("pipeline", "")

    pipeline_map = {
        "how_it_sold": "run_how_it_sold.py",
        "watch_this_sale": "run_watch_this_sale.py",
        "is_now_good_time": "run_is_now_good_time.py",
        "light_rail": "run_light_rail.py",
        "update_pass": "run_update_pass.py",
    }

    script = pipeline_map.get(pipeline)
    if not script:
        return {"success": False, "error": f"Unknown pipeline: {pipeline}"}

    # Trigger via GitHub Actions dispatch
    try:
        workflow_name = f"{pipeline.replace('_', '-')}.yml"
        result = subprocess.run(
            ["gh", "api", f"repos/Will954633/fields-automation/actions/workflows/{workflow_name}/dispatches",
             "--method", "POST", "--field", "ref=main"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GH_CONFIG_DIR": "/home/projects/.config/gh"}
        )
        if result.returncode == 0:
            return {"success": True, "triggered": workflow_name}
        else:
            return {"success": False, "error": result.stderr[-300:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_insight(action):
    """Insights don't need execution — just mark as acknowledged."""
    return {"success": True, "note": "Insight acknowledged"}


def execute_photo_post(action):
    """Execute a suggest_photo_post action — select photo, generate caption, post."""
    details = action.get("details", {})
    advisor_caption = details.get("caption", "")
    preferred_theme = details.get("preferred_theme", "")
    preferred_location = details.get("preferred_location", "")

    try:
        # Use the photo manager to select + post
        cmd_args = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-photo-manager.py", "post"]
        if advisor_caption:
            cmd_args.extend(["--caption", advisor_caption])

        result = subprocess.run(
            cmd_args, capture_output=True, text=True, timeout=90,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )

        if result.returncode == 0:
            post_id = None
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()
            return {
                "success": True,
                "post_id": post_id,
                "preferred_theme": preferred_theme,
                "preferred_location": preferred_location,
                "output": result.stdout[-500:],
            }
        else:
            return {
                "success": False,
                "error": result.stderr[-500:],
                "output": result.stdout[-500:],
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Photo post timed out after 90s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_image_post(action):
    """Execute a suggest_image_post action — generate data card and post."""
    details = action.get("details", {})
    template = details.get("template", "suburb_snapshot")
    suburb = details.get("suburb", "")
    message = details.get("message", "")

    if not message:
        return {"success": False, "error": "No message in action details"}

    # Generate data card
    card_path = f"/tmp/data-card-{uuid.uuid4().hex[:8]}.png"
    gen_cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/generate-data-card.py",
               "--template", template, "--output", card_path]
    if suburb:
        gen_cmd.extend(["--suburb", suburb])

    try:
        result = subprocess.run(gen_cmd, capture_output=True, text=True, timeout=30,
                                env={**os.environ, "PATH": os.environ.get("PATH", "")})
        if result.returncode != 0:
            return {"success": False, "error": f"Card generation failed: {result.stderr[-300:]}"}

        # Post to Facebook with image
        post_cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py",
                    "--message", message, "--image", card_path, "--post"]
        result = subprocess.run(post_cmd, capture_output=True, text=True, timeout=30,
                                env={**os.environ, "PATH": os.environ.get("PATH", "")})

        # Clean up temp image
        if os.path.exists(card_path):
            os.remove(card_path)

        if result.returncode == 0:
            post_id = None
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()
            return {"success": True, "post_id": post_id, "template": template,
                    "output": result.stdout[-500:]}
        else:
            return {"success": False, "error": result.stderr[-500:],
                    "output": result.stdout[-500:]}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(card_path):
            os.remove(card_path)


def execute_ad_edit(action):
    """Execute a suggest_ad_edit action via Facebook Marketing API."""
    details = action.get("details", {})
    ad_id = details.get("ad_id", "")
    field = details.get("field", "")
    proposed_value = details.get("proposed_value", "")

    if not ad_id:
        return {
            "success": True,
            "note": "No ad_id provided. Ad edit logged for manual execution.",
            "manual_action_needed": True,
        }

    if not ADS_TOKEN or not AD_ACCOUNT_ID:
        return {"success": False, "error": "Facebook Ads credentials not configured"}

    try:
        # 1. Get current ad creative
        r = requests.get(f"{FB_BASE}/{ad_id}", params={
            "fields": "creative{id,body,title,link_data{link,message}}",
            "access_token": ADS_TOKEN,
        }, timeout=15)
        r.raise_for_status()
        ad_data = r.json()

        creative = ad_data.get("creative", {})
        old_creative_id = creative.get("id", "")

        # 2. Build new creative spec
        creative_spec = {}
        if field == "body":
            creative_spec["body"] = proposed_value
        elif field == "headline":
            creative_spec["title"] = proposed_value
        elif field == "cta":
            creative_spec["call_to_action_type"] = proposed_value

        # Copy link_data if it exists
        link_data = creative.get("link_data", {})
        if link_data:
            creative_spec["object_story_spec"] = {
                "link_data": {
                    "link": link_data.get("link", ""),
                    "message": proposed_value if field == "body" else link_data.get("message", ""),
                    "name": proposed_value if field == "headline" else creative.get("title", ""),
                }
            }

        # 3. Create new AdCreative
        r = requests.post(f"{FB_BASE}/act_{AD_ACCOUNT_ID}/adcreatives", data={
            "access_token": ADS_TOKEN,
            **{f"[{k}]": json.dumps(v) if isinstance(v, dict) else v
               for k, v in creative_spec.items()},
        }, timeout=15)
        r.raise_for_status()
        new_creative_id = r.json().get("id", "")

        # 4. Update ad to use new creative
        r = requests.post(f"{FB_BASE}/{ad_id}", data={
            "access_token": ADS_TOKEN,
            "creative": json.dumps({"creative_id": new_creative_id}),
        }, timeout=15)
        r.raise_for_status()

        # 5. Log to institutional memory
        client = MongoClient(COSMOS_URI)
        sm = client["system_monitor"]
        sm["fb_ad_tests"].insert_one({
            "type": "ad_edit",
            "ad_id": ad_id,
            "field": field,
            "old_creative_id": old_creative_id,
            "new_creative_id": new_creative_id,
            "proposed_value": proposed_value[:200],
            "campaign_name": details.get("campaign_name", ""),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()

        return {
            "success": True,
            "old_creative_id": old_creative_id,
            "new_creative_id": new_creative_id,
            "field": field,
        }

    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"FB API error: {str(e)[:300]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_ad_pause(action):
    """Execute a suggest_ad_pause action — pause an ad via Facebook Marketing API."""
    details = action.get("details", {})
    ad_id = details.get("ad_id", "")

    if not ad_id:
        return {"success": False, "error": "No ad_id in action details"}

    if not ADS_TOKEN:
        return {"success": False, "error": "Facebook Ads credentials not configured"}

    try:
        r = requests.post(f"{FB_BASE}/{ad_id}", data={
            "access_token": ADS_TOKEN,
            "status": "PAUSED",
        }, timeout=15)
        r.raise_for_status()

        # Log to institutional memory
        client = MongoClient(COSMOS_URI)
        sm = client["system_monitor"]
        sm["fb_ad_tests"].insert_one({
            "type": "ad_pause",
            "ad_id": ad_id,
            "ad_name": details.get("ad_name", ""),
            "campaign_name": details.get("campaign_name", ""),
            "metrics_cited": details.get("metrics_cited", ""),
            "reasoning": details.get("reasoning", ""),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()

        return {
            "success": True,
            "ad_id": ad_id,
            "new_status": "PAUSED",
            "ad_name": details.get("ad_name", ""),
        }

    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"FB API error: {str(e)[:300]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_ad_create(action):
    """Execute a suggest_ad_create action — create a new Facebook ad (always PAUSED)."""
    details = action.get("details", {})
    ad_name = details.get("ad_name", "")
    adset_id = details.get("adset_id", "")
    article_id = details.get("article_id", "")
    article_url = details.get("article_url", "")
    headline = details.get("headline", "")
    body = details.get("body", "")
    image_source = details.get("image_source", "article_feature_image")
    strategy = details.get("strategy", "explore")

    if not adset_id or not article_url or not body:
        return {"success": False, "error": "Missing required fields (adset_id, article_url, body)"}

    if not ADS_TOKEN or not AD_ACCOUNT_ID or not PAGE_ID:
        return {"success": False, "error": "Facebook Ads credentials not configured"}

    try:
        # 1. Get image hash
        image_hash = None
        if image_source == "article_feature_image" and COSMOS_URI:
            # Fetch article feature image from MongoDB
            from pymongo import MongoClient
            from bson import ObjectId
            mc = MongoClient(COSMOS_URI)
            adoc = mc["system_monitor"]["content_articles"].find_one(
                {"_id": ObjectId(article_id)}, {"feature_image": 1}
            ) if article_id and len(article_id) == 24 else None
            feature_image = (adoc or {}).get("feature_image", "")
            mc.close()

            if feature_image:
                # Upload image to FB ad account
                r = requests.post(
                    f"{FB_BASE}/act_{AD_ACCOUNT_ID}/adimages",
                    data={"access_token": ADS_TOKEN},
                    files={"filename": ("image.jpg", requests.get(feature_image, timeout=15).content)},
                    timeout=30,
                )
                r.raise_for_status()
                images_data = r.json().get("images", {})
                # Response format: {"images": {"image.jpg": {"hash": "abc123"}}}
                for key, val in images_data.items():
                    image_hash = val.get("hash")
                    break
        elif image_source and image_source != "article_feature_image":
            # Use provided image hash directly
            image_hash = image_source

        if not image_hash:
            return {"success": False, "error": "Could not obtain image hash for the ad"}

        # 2. Create AdCreative
        creative_spec = {
            "name": f"Creative: {ad_name[:60]}",
            "object_story_spec": json.dumps({
                "page_id": PAGE_ID,
                "link_data": {
                    "link": article_url,
                    "message": body,
                    "name": headline or ad_name,
                    "image_hash": image_hash,
                    "call_to_action": {"type": "LEARN_MORE"},
                },
            }),
            "access_token": ADS_TOKEN,
        }
        r = requests.post(f"{FB_BASE}/act_{AD_ACCOUNT_ID}/adcreatives",
                          data=creative_spec, timeout=15)
        r.raise_for_status()
        creative_id = r.json().get("id", "")

        # 3. Create Ad (always PAUSED)
        ad_data = {
            "name": ad_name,
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": "PAUSED",
            "access_token": ADS_TOKEN,
        }
        r = requests.post(f"{FB_BASE}/act_{AD_ACCOUNT_ID}/ads",
                          data=ad_data, timeout=15)
        r.raise_for_status()
        new_ad_id = r.json().get("id", "")

        # 4. Log to institutional memory
        client = MongoClient(COSMOS_URI)
        sm = client["system_monitor"]
        sm["fb_ad_tests"].insert_one({
            "type": "ad_create",
            "ad_id": new_ad_id,
            "ad_name": ad_name,
            "creative_id": creative_id,
            "image_hash": image_hash,
            "article_id": article_id,
            "article_url": article_url,
            "headline": headline[:200],
            "body": body[:300],
            "adset_id": adset_id,
            "strategy": strategy,
            "status": "PAUSED",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()

        return {
            "success": True,
            "ad_id": new_ad_id,
            "creative_id": creative_id,
            "image_hash": image_hash,
            "strategy": strategy,
            "status": "PAUSED",
            "note": f"Ad created in PAUSED state. Activate in Ads Manager when ready.",
        }

    except requests.exceptions.HTTPError as e:
        error_body = ""
        try:
            err = e.response.json().get("error", {})
            error_body = err.get("message", "")[:200]
            if err.get("error_user_msg"):
                error_body += f" — {err['error_user_msg']}"
        except Exception:
            error_body = str(e)[:300]
        return {"success": False, "error": f"FB API error: {error_body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


EXECUTORS = {
    "suggest_article_post": execute_article_post,
    "suggest_page_post": execute_page_post,
    "suggest_photo_post": execute_photo_post,
    "suggest_pipeline_run": execute_pipeline_run,
    "suggest_insight": execute_insight,
    "suggest_image_post": execute_image_post,
    "suggest_ad_pause": execute_ad_pause,
    "suggest_ad_edit": execute_ad_edit,
    "suggest_ad_create": execute_ad_create,
}


def main():
    parser = argparse.ArgumentParser(description="Execute approved marketing actions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would execute")
    args = parser.parse_args()

    actions = get_approved_actions()

    if not actions:
        print("No approved actions to execute.")
        return

    print(f"Found {len(actions)} approved action(s):")
    for action in actions:
        action_type = action.get("action_type", "unknown")
        summary = action.get("summary", "")
        priority = action.get("priority", "?")
        print(f"  [{priority}] {action_type}: {summary}")

        if args.dry_run:
            continue

        executor = EXECUTORS.get(action_type)
        if not executor:
            print(f"    -> No executor for {action_type}, skipping")
            update_action_status(action["_id"], "failed",
                                 {"error": f"No executor for {action_type}"})
            continue

        print(f"    -> Executing...")
        result = executor(action)

        if result.get("success"):
            update_action_status(action["_id"], "executed", result)
            print(f"    -> Done: {result.get('note', result.get('post_id', 'OK'))}")
        else:
            update_action_status(action["_id"], "failed", result)
            print(f"    -> FAILED: {result.get('error', 'Unknown error')}")

    if args.dry_run:
        print("\n(Dry run — nothing executed)")


if __name__ == "__main__":
    main()
