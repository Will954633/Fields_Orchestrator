#!/usr/bin/env python3
"""
Fields Estate — Email Tracking Server
Tracks email opens, PDF viewer engagement (page views, time per page, total time).
Sends Telegram notifications on every interaction.
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from io import BytesIO

from flask import Flask, request, send_file, render_template, jsonify, abort
from flask_cors import CORS
from pymongo import MongoClient
import requests
import fitz  # PyMuPDF — server-side PDF rendering (correct ICC color handling)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPORTS_DIR = Path("/home/fields/Fields_Orchestrator/output/seller_reports")
STATIC_DIR = Path(__file__).parent / "static"
AEST = timezone(timedelta(hours=10))

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/tracking-server.log"),
    ],
)
log = logging.getLogger("tracking")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        conn = os.environ.get("COSMOS_CONNECTION_STRING", "")
        if not conn:
            # Try loading from .env
            env_path = Path("/home/fields/Fields_Orchestrator/.env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("COSMOS_CONNECTION_STRING="):
                        conn = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        _client = MongoClient(conn)
        _db = _client["system_monitor"]
    return _db


def tracking_col():
    return get_db()["email_tracking"]


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def _load_env_var(name):
    val = os.environ.get(name, "")
    if val:
        return val
    env_path = Path("/home/fields/Fields_Orchestrator/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def notify_telegram(message):
    token = _load_env_var("TELEGRAM_BOT_TOKEN")
    chat_id = _load_env_var("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram credentials not found, skipping notification")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Telegram notification failed: {e}")


# ---------------------------------------------------------------------------
# Event recording
# ---------------------------------------------------------------------------
def record_event(tracking_id, event_type, req, extra_data=None):
    """Record a tracking event and send Telegram notification."""
    now = datetime.now(timezone.utc)
    event = {
        "type": event_type,
        "timestamp": now,
        "ip": req.headers.get("X-Real-IP", req.remote_addr),
        "user_agent": req.headers.get("User-Agent", ""),
        "data": extra_data or {},
    }

    doc = tracking_col().find_one({"tracking_id": tracking_id})
    if not doc:
        log.warning(f"Unknown tracking_id: {tracking_id}")
        return

    # Append event
    tracking_col().update_one(
        {"tracking_id": tracking_id},
        {
            "$push": {"events": event},
            "$set": {"summary.last_interaction": now},
        },
    )

    # Update summary counters
    if event_type == "email_opened":
        tracking_col().update_one(
            {"tracking_id": tracking_id},
            {"$inc": {"summary.total_opens": 1}},
        )
    elif event_type == "viewer_opened":
        tracking_col().update_one(
            {"tracking_id": tracking_id},
            {"$inc": {"summary.total_viewer_opens": 1}},
        )
    elif event_type == "page_view":
        page = (extra_data or {}).get("page")
        if page is not None:
            tracking_col().update_one(
                {"tracking_id": tracking_id},
                {"$addToSet": {"summary.pages_viewed": page}},
            )
    elif event_type == "heartbeat":
        time_delta = (extra_data or {}).get("interval_seconds", 5)
        tracking_col().update_one(
            {"tracking_id": tracking_id},
            {"$inc": {"summary.total_time_seconds": time_delta}},
        )
        # Update per-page time
        page = (extra_data or {}).get("current_page")
        if page is not None:
            tracking_col().update_one(
                {"tracking_id": tracking_id},
                {"$inc": {f"summary.time_per_page.{page}": time_delta}},
            )
    elif event_type == "session_end":
        total = (extra_data or {}).get("total_time_seconds", 0)
        tracking_col().update_one(
            {"tracking_id": tracking_id},
            {"$set": {"summary.last_session_duration": total}},
        )

    # Telegram notification (skip heartbeats to avoid spam)
    if event_type != "heartbeat":
        name = doc.get("recipient_name", "Unknown")
        addr = doc.get("property_address", "Unknown property")
        aest_now = now.astimezone(AEST).strftime("%H:%M AEST")

        messages = {
            "email_opened": f"*Email opened* by {name}\n{addr}\n{aest_now}",
            "viewer_opened": f"*Report opened* by {name}\n{addr}\n{aest_now}",
            "page_view": f"*Viewing page {(extra_data or {}).get('page', '?')}* — {name}\n{addr}",
            "pdf_downloaded": f"*PDF downloaded* by {name}\n{addr}\n{aest_now}",
            "session_end": f"*Session ended* — {name} spent {(extra_data or {}).get('total_time_seconds', 0):.0f}s on report\n{addr}",
        }
        msg = messages.get(event_type, f"*{event_type}* — {name}\n{addr}")
        notify_telegram(msg)

    log.info(f"Event: {event_type} for {tracking_id} from {event['ip']}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# 1x1 transparent tracking pixel
@app.route("/pixel/<tracking_id>.gif")
def pixel(tracking_id):
    record_event(tracking_id, "email_opened", request)
    pixel_path = STATIC_DIR / "pixel.gif"
    return send_file(
        pixel_path,
        mimetype="image/gif",
        max_age=0,
        conditional=False,
    )


# PDF Viewer page
@app.route("/view/<tracking_id>")
def viewer(tracking_id):
    doc = tracking_col().find_one({"tracking_id": tracking_id})
    if not doc:
        abort(404)
    record_event(tracking_id, "viewer_opened", request)
    return render_template(
        "viewer.html",
        tracking_id=tracking_id,
        property_address=doc.get("property_address", ""),
        recipient_name=doc.get("recipient_name", ""),
        total_pages=doc.get("total_pages", 0),
    )


# Serve rendered page as PNG (server-side rendering via PyMuPDF)
@app.route("/page/<tracking_id>/<int:page_num>")
def serve_page(tracking_id, page_num):
    doc_record = tracking_col().find_one({"tracking_id": tracking_id})
    if not doc_record:
        abort(404)
    report_path = doc_record.get("report_path", "")
    if not report_path or not Path(report_path).exists():
        abort(404)

    try:
        pdf = fitz.open(report_path)
        if page_num < 1 or page_num > pdf.page_count:
            pdf.close()
            abort(404)
        page = pdf[page_num - 1]
        # Render at 2x for crisp display (144 DPI)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        pdf.close()

        buf = BytesIO(img_bytes)
        buf.seek(0)
        return send_file(buf, mimetype="image/png", max_age=3600)
    except Exception as e:
        log.error(f"Page render error: {e}")
        abort(500)


# Serve logo image
@app.route("/logo/<variant>")
def serve_logo(variant):
    logos = {
        "white": STATIC_DIR / "logo-white.png",
        "dark": STATIC_DIR / "logo-dark.png",
    }
    path = logos.get(variant)
    if not path or not path.exists():
        abort(404)
    return send_file(path, mimetype="image/png", max_age=86400)


# PDF download (tracked separately from viewing)
@app.route("/download/<tracking_id>")
def download_pdf(tracking_id):
    doc = tracking_col().find_one({"tracking_id": tracking_id})
    if not doc:
        abort(404)
    report_path = doc.get("report_path", "")
    if not report_path or not Path(report_path).exists():
        abort(404)
    record_event(tracking_id, "pdf_downloaded", request)
    filename = doc.get("report_filename", "report.pdf")
    return send_file(
        report_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# JS tracking events (page views, heartbeats, session end)
@app.route("/event", methods=["POST"])
def track_event():
    data = request.json or {}
    tracking_id = data.get("tracking_id")
    event_type = data.get("type")
    if not tracking_id or not event_type:
        return jsonify({"error": "missing tracking_id or type"}), 400
    record_event(tracking_id, event_type, request, data.get("data", {}))
    return jsonify({"ok": True})


# Status endpoint — view all tracking data for a report
@app.route("/status/<tracking_id>")
def status(tracking_id):
    doc = tracking_col().find_one({"tracking_id": tracking_id}, {"_id": 0})
    if not doc:
        abort(404)
    # Convert datetimes to strings for JSON
    def serialize(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    return app.response_class(
        json.dumps(doc, default=serialize, indent=2),
        mimetype="application/json",
    )


# List all tracked reports
@app.route("/list")
def list_tracked():
    docs = list(
        tracking_col().find(
            {},
            {
                "_id": 0,
                "tracking_id": 1,
                "recipient_name": 1,
                "recipient_email": 1,
                "property_address": 1,
                "sent_at": 1,
                "summary": 1,
            },
        ).sort("sent_at", -1).limit(50)
    )
    return app.response_class(
        json.dumps(docs, default=str, indent=2),
        mimetype="application/json",
    )


# Health check
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "fields-tracking-server"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3051, debug=False)
