#!/usr/bin/env python3
"""
email-attachment-to-kb.py — Download email attachments and save them to the Knowledge Base.

Downloads attachments from an email via Microsoft Graph, then ingests each
supported file (PDF, DOCX, TXT, MD, XLSX) into the KB with AI classification.

Usage:
    # Save all attachments from an email to KB
    python3 scripts/email-attachment-to-kb.py <message_id>

    # Save to specific category
    python3 scripts/email-attachment-to-kb.py <message_id> --category strategy

    # Add custom tags
    python3 scripts/email-attachment-to-kb.py <message_id> --tags "contract,legal"

    # Dry run (download + classify but don't save to KB)
    python3 scripts/email-attachment-to-kb.py <message_id> --dry-run

    # Skip AI (fast, just chunk and save)
    python3 scripts/email-attachment-to-kb.py <message_id> --skip-ai --category financial
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls", ".csv"}
DOWNLOAD_HELPER = "/home/fields/samantha-email-agent/download_email_attachments_helper.py"
SAVE_TO_KB = "/home/fields/Fields_Orchestrator/scripts/save-to-kb.py"


def download_attachments(message_id: str, output_dir: str) -> dict:
    """Download attachments using the email helper."""
    result = subprocess.run(
        [sys.executable, DOWNLOAD_HELPER, message_id, "--output-dir", output_dir],
        capture_output=True, text=True,
        env={**os.environ},
        cwd="/home/fields/samantha-email-agent",
    )
    if result.returncode != 0:
        return {"status": "error", "errors": [result.stderr[:500]], "downloaded": []}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "errors": [f"Bad JSON: {result.stdout[:200]}"], "downloaded": []}


def save_file_to_kb(filepath: str, category: str = None, tags: str = None,
                     skip_ai: bool = False, dry_run: bool = False) -> dict:
    """Save a single file to the KB."""
    cmd = [sys.executable, SAVE_TO_KB, "--file", filepath]
    if category:
        cmd += ["--category", category]
    if tags:
        cmd += ["--tags", tags]
    if skip_ai:
        cmd.append("--skip-ai")
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env={**os.environ},
        cwd="/home/fields/Fields_Orchestrator",
    )
    return {
        "file": filepath,
        "success": result.returncode == 0,
        "output": result.stdout.strip(),
        "log": result.stderr.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Download email attachments → save to KB")
    parser.add_argument("message_id", help="Microsoft Graph message ID")
    parser.add_argument("--category", help="Force KB category (book, strategy, financial, etc.)")
    parser.add_argument("--tags", help="Comma-separated custom tags")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI classification")
    parser.add_argument("--dry-run", action="store_true", help="Download + classify but don't save")
    args = parser.parse_args()

    # Download to temp dir
    tmp_dir = tempfile.mkdtemp(prefix="email_attach_")
    print(f"Downloading attachments from email {args.message_id[:20]}...", file=sys.stderr)

    dl_result = download_attachments(args.message_id, tmp_dir)

    if dl_result["status"] == "error":
        print(f"Download failed: {dl_result['errors']}", file=sys.stderr)
        sys.exit(1)

    downloaded = dl_result.get("downloaded", [])
    if not downloaded:
        print("No attachments found in this email.", file=sys.stderr)
        sys.exit(0)

    print(f"Downloaded {len(downloaded)} attachment(s)", file=sys.stderr)

    # Process each supported file
    results = []
    for filepath in downloaded:
        p = Path(filepath)
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"  Skipping unsupported: {p.name} ({p.suffix})", file=sys.stderr)
            results.append({"file": p.name, "status": "skipped", "reason": f"Unsupported type: {p.suffix}"})
            continue

        print(f"  Saving to KB: {p.name}...", file=sys.stderr)
        save_result = save_file_to_kb(
            filepath, category=args.category, tags=args.tags,
            skip_ai=args.skip_ai, dry_run=args.dry_run,
        )
        results.append({
            "file": p.name,
            "status": "saved" if save_result["success"] else "failed",
            "kb_path": save_result["output"] if save_result["success"] else None,
            "log": save_result["log"][:200],
        })

    # Summary
    saved = sum(1 for r in results if r["status"] == "saved")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nResults: {saved} saved, {skipped} skipped, {failed} failed", file=sys.stderr)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
