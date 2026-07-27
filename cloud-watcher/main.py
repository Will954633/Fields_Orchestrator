"""
cloud-watcher / main.py — OFF-VM watchdog for fields-orchestrator-vm.

Why this exists (2026-07-27):
  The VM OOM-wedged so hard that sshd and every service (including the on-VM
  watchdog.py) died. Nothing on the box could detect or recover it — Will had to
  `gcloud compute instances reset` from his laptop. An on-VM watchdog cannot save
  a wedged VM; it goes down with the ship. This runs on GCP, entirely off the VM.

Design (alert-first, human-in-the-loop — Will's choice):
  * Cloud Scheduler pings `vm_watcher` every ~3 min.
  * `vm_watcher` checks TWO independent signals:
      1. Heartbeat: the freshest system_monitor.vm_metrics.recorded_at in Cosmos
         (write_vm_metrics.py writes it every minute; a wedged VM stops writing).
      2. Reachability: TCP probe of the VM's public IP on ports 22 and 443.
  * WEDGED  = heartbeat stale > STALE_MIN AND at least one port is dead.
              -> Telegram alert. NEVER resets automatically.
  * DEGRADED = heartbeat stale but ports still open (cron/Mongo issue, VM alive).
              -> softer Telegram note, no reset offered.
  * If VM_WATCHDOG_BOT_TOKEN is set, the WEDGED alert carries a one-tap
    "Reset VM now" inline button handled by `vm_reset_callback` (Tier B).
    Otherwise the alert just contains the copy-paste gcloud reset command (Tier A).

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

STALE_MIN = int(os.environ.get("STALE_MIN", "8"))          # heartbeat age -> stale
ALERT_COOLDOWN_MIN = int(os.environ.get("ALERT_COOLDOWN_MIN", "20"))
RESET_COOLDOWN_MIN = int(os.environ.get("RESET_COOLDOWN_MIN", "30"))

COSMOS = os.environ.get("COSMOS_CONNECTION_STRING", "")
# Alerts: reuse Will's existing bot for sending (sendMessage does NOT conflict with
# the on-VM polling bridges). Button/callback needs a SEPARATE bot (webhook), see Tier B.
ALERT_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WATCHDOG_BOT_TOKEN = os.environ.get("VM_WATCHDOG_BOT_TOKEN", "")   # optional (Tier B)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
RESET_SECRET = os.environ.get("RESET_SECRET", "fields-reset")      # guards the callback


# --- helpers --------------------------------------------------------------- #
def _mongo():
    from pymongo import MongoClient
    return MongoClient(COSMOS, serverSelectionTimeoutMS=8000,
                       socketTimeoutMS=12000, retryWrites=False)


def heartbeat_age_min():
    """Minutes since the freshest vm_metrics doc. None if unreadable."""
    try:
        client = _mongo()
        doc = client["system_monitor"]["vm_metrics"].find_one(sort=[("_id", -1)])
        client.close()
        if not doc or "recorded_at" not in doc:
            return None
        ra = doc["recorded_at"]
        if ra.tzinfo is None:
            ra = ra.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ra).total_seconds() / 60.0
    except Exception:
        return None


def port_open(ip, port, timeout=6):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def _state_get():
    try:
        client = _mongo()
        doc = client["system_monitor"]["vm_watcher_state"].find_one({"_id": "watcher"})
        client.close()
        return doc or {}
    except Exception:
        return {}


def _state_set(**fields):
    try:
        client = _mongo()
        client["system_monitor"]["vm_watcher_state"].update_one(
            {"_id": "watcher"}, {"$set": fields}, upsert=True)
        client.close()
    except Exception:
        pass


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
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        # retry without parse_mode (entity errors)
        payload.pop("parse_mode", None)
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
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
            # Tier B: one-tap button via the dedicated watchdog bot (webhook -> vm_reset_callback)
            tg_send(WATCHDOG_BOT_TOKEN, {
                "text": header + "\n\nTap to power-cycle it:",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[
                    {"text": "\U0001F501 Reset VM now",
                     "callback_data": f"reset:{RESET_SECRET}"}]]},
            })
        else:
            # Tier A: alert with the copy-paste command
            tg_send(ALERT_BOT_TOKEN, {
                "text": header + f"\n\nReset it with:\n`{reset_command()}`",
                "parse_mode": "Markdown"})
        _state_set(last_alert=datetime.now(timezone.utc).isoformat(),
                   last_status="wedged")

    elif status == "degraded" and _cooldown_ok(state, "last_degraded_alert", 60):
        tg_send(ALERT_BOT_TOKEN, {
            "text": (f"⚠️ *VM monitoring degraded* — heartbeat {age_str} old but VM reachable "
                     f"({port_str}). Likely write_vm_metrics cron or Mongo, not a hang. "
                     f"No reset needed."),
            "parse_mode": "Markdown"})
        _state_set(last_degraded_alert=datetime.now(timezone.utc).isoformat(),
                   last_status="degraded")
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

    # authz: only Will's chat id, and the shared secret must match
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
