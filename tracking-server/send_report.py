#!/usr/bin/env python3
"""
Fields Estate — Send Tracked Property Report

Usage:
    python3 send_report.py \
        --to "dee@example.com" \
        --name "Dee" \
        --address "13 Terrace Court" \
        --report /home/fields/Fields_Orchestrator/output/seller_reports/2026-04-10_13-terrace-court_dee_v2.pdf \
        [--subject "Your Property Appraisal — 13 Terrace Court"] \
        [--send]        # Without --send, just creates tracking record + prints email HTML

Creates a tracking record in MongoDB, generates email HTML with tracking pixel,
and optionally sends via Microsoft Graph API.
"""

import argparse
import os
import sys
import uuid
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent dir for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

AEST = timezone(timedelta(hours=10))
BASE_URL = "https://vm.fieldsestate.com.au/track"


def get_db():
    env_path = Path("/home/fields/Fields_Orchestrator/.env")
    conn = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not conn and env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("COSMOS_CONNECTION_STRING="):
                conn = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    client = MongoClient(conn)
    return client["system_monitor"]


def count_pdf_pages(pdf_path):
    """Count pages in PDF without heavy dependencies."""
    try:
        result = subprocess.run(
            ["python3", "-c", f"""
import fitz
doc = fitz.open("{pdf_path}")
print(doc.page_count)
"""],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    # Fallback: count /Page objects in PDF
    try:
        data = Path(pdf_path).read_bytes()
        return data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    except Exception:
        return 0


def create_tracking_record(db, recipient_email, recipient_name, property_address,
                           report_path, subject, total_pages):
    tracking_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc)

    doc = {
        "tracking_id": tracking_id,
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "property_address": property_address,
        "subject": subject,
        "report_path": str(report_path),
        "report_filename": Path(report_path).name,
        "total_pages": total_pages,
        "created_at": now,
        "sent_at": None,
        "events": [],
        "summary": {
            "total_opens": 0,
            "total_viewer_opens": 0,
            "total_time_seconds": 0,
            "pages_viewed": [],
            "time_per_page": {},
            "last_interaction": None,
            "last_session_duration": 0,
        },
    }

    db["email_tracking"].insert_one(doc)
    return tracking_id


def generate_email_html(tracking_id, recipient_name, property_address, subject):
    """Generate the email HTML with tracking pixel and viewer link."""
    viewer_url = f"{BASE_URL}/view/{tracking_id}"
    pixel_url = f"{BASE_URL}/pixel/{tracking_id}.gif"

    first_name = recipient_name.split()[0] if recipient_name else ""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background:#E6DDD2; font-family:Verdana,Poppins,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#E6DDD2; padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:2px; overflow:hidden;">

    <!-- Header -->
    <tr>
        <td style="background:#22382C; padding:24px 32px; text-align:center;">
            <img src="https://vm.fieldsestate.com.au/track/logo/white" alt="Fields" width="140" height="47" style="display:inline-block; height:47px; width:auto;">
        </td>
    </tr>

    <!-- Body -->
    <tr>
        <td style="padding:40px 32px;">
            <p style="font-size:15px; color:#22382C; line-height:1.7; margin-bottom:20px; font-family:Verdana,sans-serif;">
                Hi {first_name},
            </p>
            <p style="font-size:15px; color:#22382C; line-height:1.7; margin-bottom:20px; font-family:Verdana,sans-serif;">
                It's Will here, I'm a property analyst at Fields Real Estate. First of all, thank you so much for giving me the opportunity to appraise your property. You have a fantastic asset here that will attract strong demand in the market.
            </p>
            <p style="font-size:15px; color:#22382C; line-height:1.7; margin-bottom:20px; font-family:Verdana,sans-serif;">
                A few factors in particular work in your favour. A 3&#8211;6 month selling window puts your sale in some of the best selling months of the year for Merrimac, particularly toward the later end. Secondly, your home's proximity to All Saints is a standout feature &#8212; many families dream of being able to walk their children to school. Thirdly, scarcity &#8212; there are really very few homes with 5 bedrooms plus a study in a dual living zone arrangement. Those factors will work strongly for you.
            </p>
            <p style="font-size:15px; color:#22382C; line-height:1.7; margin-bottom:20px; font-family:Verdana,sans-serif;">
                I've included a number of suggestions in the report of how the unique attributes of your home should drive selling strategy as a guide, and I'd welcome the opportunity to discuss these in person.
            </p>
            <p style="font-size:15px; color:#22382C; line-height:1.7; margin-bottom:32px; font-family:Verdana,sans-serif;">
                Please take your time to read the report, I'm here to answer your questions any time.
            </p>

            <!-- CTA Button -->
            <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center">
                <a href="{viewer_url}"
                   style="display:inline-block; background:#B76749; color:#ffffff; padding:14px 40px;
                          font-size:14px; letter-spacing:0.5px; text-decoration:none;
                          font-family:Verdana,sans-serif; font-weight:bold; border-radius:2px;">
                    VIEW YOUR REPORT
                </a>
            </td></tr>
            </table>
        </td>
    </tr>

    <!-- Footer -->
    <tr>
        <td style="background:#E6DDD2; padding:24px 32px; border-top:1px solid #d4cbbf;">
            <p style="font-size:13px; color:#7a7a6e; margin:0; font-family:Verdana,sans-serif;">
                <strong style="color:#22382C;">Will Simpson</strong><br>
                Fields &mdash; Smarter with data<br>
                <a href="https://fieldsestate.com.au" style="color:#B76749; text-decoration:none;">fieldsestate.com.au</a>
            </p>
        </td>
    </tr>

</table>
</td></tr>
</table>

<!-- Tracking pixel -->
<img src="{pixel_url}" width="1" height="1" alt="" style="display:none;" />

</body>
</html>"""
    return html


def send_via_graph(recipient_email, subject, html_body):
    """Send email via Microsoft Graph using email CLI."""
    result = subprocess.run(
        [
            "python3", "/home/fields/Fields_Orchestrator/scripts/fields-email.py",
            "send",
            "--to", recipient_email,
            "--subject", subject,
            "--body", html_body,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd="/home/fields/Fields_Orchestrator",
    )
    return result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description="Send tracked property report")
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--name", required=True, help="Recipient name")
    parser.add_argument("--address", required=True, help="Property address")
    parser.add_argument("--report", required=True, help="Path to PDF report")
    parser.add_argument("--subject", help="Email subject line")
    parser.add_argument("--send", action="store_true", help="Actually send the email")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"Error: Report not found: {report_path}")
        sys.exit(1)

    subject = args.subject or f"Your Property Appraisal — {args.address}"
    total_pages = count_pdf_pages(str(report_path))

    print(f"Report: {report_path.name} ({total_pages} pages)")
    print(f"To: {args.name} <{args.to}>")
    print(f"Subject: {subject}")
    print()

    # Create tracking record
    db = get_db()
    tracking_id = create_tracking_record(
        db, args.to, args.name, args.address,
        report_path, subject, total_pages,
    )
    print(f"Tracking ID: {tracking_id}")
    print(f"Viewer URL:  {BASE_URL}/view/{tracking_id}")
    print(f"Status URL:  {BASE_URL}/status/{tracking_id}")
    print()

    # Generate email HTML
    email_html = generate_email_html(tracking_id, args.name, args.address, subject)

    # Save email HTML for reference
    output_dir = Path("/home/fields/Fields_Orchestrator/output/tracked_emails")
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{tracking_id}.html"
    html_path.write_text(email_html)
    print(f"Email HTML saved: {html_path}")

    if args.send:
        print("\nSending via Microsoft Graph...")
        ok, output = send_via_graph(args.to, subject, email_html)
        if ok:
            db["email_tracking"].update_one(
                {"tracking_id": tracking_id},
                {"$set": {"sent_at": datetime.now(timezone.utc)}},
            )
            print("Sent successfully!")
        else:
            print(f"Send failed:\n{output}")
            print("\nYou can manually send using the saved HTML file.")
    else:
        print("\n--- DRY RUN (use --send to actually send) ---")
        print(f"Email HTML ready at: {html_path}")
        print("You can copy-paste the HTML into your email client, or re-run with --send")

    print(f"\nMonitor engagement: {BASE_URL}/status/{tracking_id}")


if __name__ == "__main__":
    main()
