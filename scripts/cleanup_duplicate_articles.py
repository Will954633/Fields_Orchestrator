#!/usr/bin/env python3
"""
cleanup_duplicate_articles.py — Delete duplicate articles from Article Manager.

For each title, keeps the best version (published+charts > published > draft)
and deletes all others.
"""

import os
import sys
from collections import defaultdict
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")

client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                     serverSelectionTimeoutMS=10000, retryWrites=False)
coll = client.system_monitor.content_articles

dry_run = "--dry-run" in sys.argv


def score_article(doc):
    """Higher score = better version to keep."""
    s = 0
    if doc.get("status") == "published":
        s += 100
    html = doc.get("html", "")
    if "data:image/png;base64" in html:
        s += 50
    if "<img" in html:
        s += 10
    return s


# Get all articles
articles = list(coll.find({}, {"title": 1, "status": 1, "html": 1, "slug": 1}))
print(f"Total articles: {len(articles)}")

by_title = defaultdict(list)
for a in articles:
    by_title[a["title"]].append(a)

to_delete = []
for title, arts in by_title.items():
    if len(arts) <= 1:
        continue
    # Sort by score descending — keep the first (best)
    arts.sort(key=score_article, reverse=True)
    keeper = arts[0]
    for dupe in arts[1:]:
        to_delete.append(dupe)

print(f"Articles to delete: {len(to_delete)}")
print(f"Articles to keep: {len(articles) - len(to_delete)}")
print()

if dry_run:
    print("=== DRY RUN ===")
    for d in sorted(to_delete, key=lambda x: x["title"]):
        print(f"  DELETE {d['_id']} | {d.get('status','?'):10} | {d['title'][:65]}")
else:
    deleted = 0
    for d in to_delete:
        coll.delete_one({"_id": d["_id"]})
        deleted += 1
    print(f"Deleted {deleted} duplicate articles.")

    # Verify
    remaining = coll.count_documents({})
    print(f"Remaining articles: {remaining}")
