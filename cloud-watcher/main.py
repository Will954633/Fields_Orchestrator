"""
cloud-watcher / main.py — OFF-VM watchdog for fields-orchestrator-vm.

Why this exists (2026-07-27):
  The VM OOM-wedged so hard that sshd and every service (including the on-VM
  watchdog.py) died. Nothing on the box could detect or recover it — Will had to
  `gcloud compute instances reset` from his laptop. An on-VM watchdog cannot save
  a wedged VM; it goes down with the ship. This runs on GCP, entirely off the VM.

Heartbeat over GCS (not Cosmos):
  Cosmos (Azure) refuses connections from GCP Cloud Function egress (its own IP
  firewall), so the safety net must not depend on it. Instead the VM re-uploads a
  tiny object gs://<bucket>/vm-heartbeat.txt every minute (write_heartbeat.sh via
  cron). The function reads that object's last-updated time — always reachable
  from GCP. A wedged VM stops re-uploading, so the object goes stale within minutes.
  Watcher state (alert/reset cooldowns) also lives in a GCS object, so the whole
  function has zero dependency on the VM or Cosmos being reachable.

Design (alert-first, human-in-the-loop — Will's choice):
  * Cloud Scheduler pings `vm_watcher` every ~3 min.
  * Two independent signals:
      1. Heartbeat: age of gs://<bucket>/vm-heartbeat.txt (stale => VM not writing).
      2. Reachability: TCP probe of the VM public IP on ports 22 and 443.
  * WEDGED   = heartbeat stale > STALE_MIN AND at least one port dead -> Telegram alert.
  * DEGRADED = heartbeat stale but ports open (cron/write issue, VM alive) -> soft note.
  * Never resets automatically. If VM_WATCHDOG_BOT_TOKEN is set, the WEDGED alert
    carries a one-tap "Reset VM now" button handled by vm_reset_callback (Tier B);
    otherwise the alert contains the copy-paste gcloud reset command (Tier A).

Two HTTP entry points (deploy each as its own function):
  vm_watcher(request)         <- Cloud Scheduler target
  vm_reset_callback(request)  <- Telegram webhook target for the watchdog bot (Tier B)
"""

import os
import json
import socket
import urllib.request
from datetime import datetime, timezone, timedelta

# --- config (set via function env vars) ------------------------------------ #
PROJECT = os.environ.get("VM_PROJECT", "fields-estate")
ZONE = os.environ.get("VM_ZONE", "australia-southeast1-b")
INSTANCE = os.environ.get("VM_INSTANCE", "fields-orchestrator-vm")
VM_IP = os.environ.get("VM_IP", "34.40.230.132")
PORTS = [22, 443]

HEARTBEAT_BUCKET = os.environ.get("HEARTBEAT_BUCKET", "fields-blob-backup")
HEARTBEAT_OBJECT = os.environ.get("HEARTBEAT_OBJECT", "vm-heartbeat.txt")
STATE_OBJECT = os.environ.get("STATE_OBJECT", "vm-watchdog-state.json")

STALE_MIN = int(os.environ.get("STALE_MIN", "8"))          # heartbeat age -> stale
ALERT_COOLDOWN_MIN = int(os.environ.get("ALERT_COOLDOWN_MIN", "20"))
RESET_COOLDOWN_MIN = int(os.environ.get("RESET_COOLDOWN_MIN", "30"))

# Alerts: reuse Will's existing bot for sending (sendMessage does NOT conflict with
# the on-VM polling bridges). Button/callback needs a SEPARATE bot (webhook), Tier B.
ALERT_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WATCHDOG_BOT_TOKEN = os.environ.get("VM_WATCHDOG_BOT_TOKEN", "")   # optional (Tier B)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
RESET_SECRET = os.environ.get("RESET_SECRET", "fields-reset")      # guards the callback


# --- GCS helpers (heartbeat + state) --------------------------------------- #
def _bucket():
    from google.cloud import storage
    return storage.Client().bucket(HEARTBEAT_BUCKET)


def heartbeat_age_min():
    """Minutes since the heartbeat object was last written. None if unreadable."""
    try:
        blob = _bucket().get_blob(HEARTBEAT_OBJECT)
        if blob is None or blob.updated is None:
            return None
        updated = blob.updated
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - updated).total_seconds() / 60.0
    except Exception:
        return None


def _state_get():
    try:
        blob = _bucket().get_blob(STATE_OBJECT)
        if blob is None:
            return {}
        return json.loads(blob.download_as_text())
    except Exception:
        return {}


def _state_set(**fields):
    try:
        state = _state_get()
        state.update(fields)
        blob = _bucket().blob(STATE_OBJECT)
        blob.upload_from_string(json.dumps(state), content_type="application/json")
    except Exception:
        pass


# --- misc helpers ---------------------------------------------------------- #
def port_open(ip, port, timeout=6):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def _cooldown_ok(state, key, minutes):
    last = state.get(key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return datetime.now(timezone.utc) - last_dt >= timedelta(minutes=minutes)


def tg_send(token, payload):
    if not token or not CHAT_ID:
        return
    payload["chat_id"] = CHAT_ID
    def _post(p):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    try:
        _post(payload)
    except Exception:
        payload.pop("parse_mode", None)  # retry plain on entity errors
        try:
            _post(payload)
        except Exception:
            pass


def reset_command():
    return (f"gcloud compute instances reset {INSTANCE} "
            f"--zone={ZONE} --project={PROJECT}")


# --- entry point 1: the watcher (Cloud Scheduler target) ------------------- #
def vm_watcher(request):
    age = heartbeat_age_min()
    ports = {p: port_open(VM_IP, p) for p in PORTS}
    any_port_up = any(ports.values())
    stale = (age is None) or (age >= STALE_MIN)

    status = "ok"
    if stale and not any_port_up:
        status = "wedged"
    elif stale and any_port_up:
        status = "degraded"

    state = _state_get()
    age_str = "unreadable" if age is None else f"{age:.1f} min"
    port_str = ", ".join(f"{p}:{'up' if up else 'DOWN'}" for p, up in ports.items())

    if status == "wedged" and _cooldown_ok(state, "last_alert", ALERT_COOLDOWN_MIN):
        header = ("\U0001F6A8 *fields-orchestrator-vm looks WEDGED*\n"
                  f"Heartbeat: {age_str} old · Ports: {port_str}\n"
                  "The guest is unresponsive (this mirrors the OOM hang). "
                  "It will NOT reset by itself.")
        if WATCHDOG_BOT_TOKEN:
            tg_send(WATCHDOG_BOT_TOKEN, {
                "text": header + "\n\nTap to power-cycle it:",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[
                    {"text": "\U0001F501 Reset VM now",
                     "callback_data": f"reset:{RESET_SECRET}"}]]},
            })
        else:
            tg_send(ALERT_BOT_TOKEN, {
                "text": header + f"\n\nReset it with:\n`{reset_command()}`",
                "parse_mode": "Markdown"})
        _state_set(last_alert=datetime.now(timezone.utc).isoformat(), last_status="wedged")

    elif status == "degraded" and _cooldown_ok(state, "last_degraded_alert", 60):
        tg_send(ALERT_BOT_TOKEN, {
            "text": (f"⚠️ *VM monitoring degraded* — heartbeat {age_str} old but VM "
                     f"reachable ({port_str}). Likely write_heartbeat cron, not a hang. "
                     f"No reset needed."),
            "parse_mode": "Markdown"})
        _state_set(last_degraded_alert=datetime.now(timezone.utc).isoformat(), last_status="degraded")
    else:
        _state_set(last_status=status)

    return (json.dumps({"status": status, "heartbeat_age_min": age, "ports": ports}), 200,
            {"Content-Type": "application/json"})


# --- entry point 2: reset button callback (Telegram webhook, Tier B) ------- #
def vm_reset_callback(request):
    """Telegram webhook for the watchdog bot. Verifies the tap is Will's, then resets."""
    try:
        update = request.get_json(silent=True) or {}
    except Exception:
        update = {}
    cq = update.get("callback_query")
    if not cq:
        return ("ignored", 200)

    from_id = str(cq.get("from", {}).get("id", ""))
    data = cq.get("data", "")
    cq_id = cq.get("id")

    def answer(text):
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{WATCHDOG_BOT_TOKEN}/answerCallbackQuery",
                data=json.dumps({"callback_query_id": cq_id, "text": text, "show_alert": True}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass

    if CHAT_ID and from_id != str(CHAT_ID):
        answer("Not authorised.")
        return ("unauthorized", 200)
    if data != f"reset:{RESET_SECRET}":
        answer("Bad request.")
        return ("bad", 200)

    state = _state_get()
    if not _cooldown_ok(state, "last_reset", RESET_COOLDOWN_MIN):
        answer(f"A reset was issued in the last {RESET_COOLDOWN_MIN} min. Waiting.")
        return ("cooldown", 200)

    try:
        from google.cloud import compute_v1
        compute_v1.InstancesClient().reset(project=PROJECT, zone=ZONE, instance=INSTANCE)
        _state_set(last_reset=datetime.now(timezone.utc).isoformat())
        answer("Reset issued. VM will be back in ~1-2 min.")
        tg_send(ALERT_BOT_TOKEN, {
            "text": f"\U0001F501 VM reset issued by Will via watchdog button at "
                    f"{datetime.now(timezone.utc).strftime('%H:%M UTC')}. Booting..."})
        return ("reset-issued", 200)
    except Exception as e:
        answer(f"Reset FAILED: {e}")
        return (f"error: {e}", 500)
