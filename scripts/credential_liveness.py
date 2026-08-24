#!/usr/bin/env python3
"""
credential_liveness.py — daily authenticated-liveness probe for every credential the
business depends on, reported into the Process Registry (Fields Systems Health sheet)
via job_status so a DYING secret surfaces BEFORE the jobs that use it start returning
zero output.

WHY (REC-ops-003, approved 2026-08-18). Fields has had six credential-expiry outages —
Gmail (x2), GitHub, a Google OAuth refresh token, a two-month Facebook Ads blackout, and
Bright Data (2026-08-11, which killed every Domain.com.au fetch for 2.5 days and took nine
health-board rows with it). Not one had a watcher. CLAUDE.md Rule 7 proves a job RAN;
nothing proved its secrets are still VALID. `credential_expiry.py` covers the credentials
whose expiry DATE we know (a calendar check). THIS script covers the harder half: does the
token still return 200 today?

THE CRITICAL NUANCE (REC-ops-004). A naive liveness probe runs in a fresh shell, reads the
GOOD key from .env, and reports GREEN — while a long-running daemon keeps serving a STALE,
DEAD key it loaded into its environment at start (systemd EnvironmentFile is read once).
That blind spot is exactly what kept Domain ingestion dead for 3 nights AFTER the Bright
Data key was rotated on 2026-08-13. So this probe does two things per credential:
  1. Probe the LIVE value read straight from the .env FILE (not os.environ — a stale
     value already in the environment must not mask the file's true value).
  2. Read /proc/<MainPID>/environ of every running fields-* daemon and compare what it
     ACTUALLY HOLDS against the .env file value. Any daemon holding a different value is
     flagged ERROR ("live key OK but daemon holds a stale value — restart it"), even when
     the .env probe is green. Where the stale value can be probed, it is, to prove dead
     vs merely-different.

Rule 7b: "credential valid" and "could not check it" are DIFFERENT outcomes. A missing
key, a network error, a rate-limit, or an unreadable daemon environ all record ERROR with
a could-not-check detail — never a silent success. The umbrella runner raises if it managed
to check ZERO credentials (its zero-output path).

Where a provider exposes an expiry timestamp (Facebook Ads), we alert at T-7 days rather
than waiting for the token to actually die.

Each credential self-registers its own job_runs row (cadence 24h) so it appears as its own
Process Registry line: "Cred liveness: <provider>".

Usage:
    python3 scripts/credential_liveness.py            # probe + write heartbeats
    python3 scripts/credential_liveness.py --dry-run  # probe + print, no heartbeats
    python3 scripts/credential_liveness.py --only brightdata,github
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import requests

REPO = "/home/fields/Fields_Orchestrator"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
if os.path.join(REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "scripts"))

# Rule 7 checklist item 3: load our OWN environment; do not trust the caller's shell.
from shared.env import load_env  # noqa: E402
load_env()

TIMEOUT = 15
ENV_FILE_PATH = os.path.join(REPO, ".env")

# Status vocabulary (mirrors api_health_monitor.py so the two read alike).
OK, OUT_OF_CREDIT, AUTH_ERROR, RATE_LIMITED, EXPIRING, ERROR, SKIP = (
    "OK", "OUT_OF_CREDIT", "AUTH_ERROR", "RATE_LIMITED", "EXPIRING", "ERROR", "SKIP")
# Outcomes that mean the credential is USABLE right now.
GOOD_STATES = {OK}
# Outcomes that mean "the credential is dead / dying" -> heartbeat error.
DEAD_STATES = {OUT_OF_CREDIT, AUTH_ERROR, EXPIRING}
# Outcomes that mean "we could not verify" -> heartbeat error (Rule 7b), distinct detail.
UNVERIFIED_STATES = {RATE_LIMITED, ERROR, SKIP}


# --------------------------------------------------------------------------- #
# .env FILE reader — the authoritative "live" values, independent of os.environ
# --------------------------------------------------------------------------- #

def read_env_file(path: str = ENV_FILE_PATH) -> dict:
    """Parse the .env FILE directly into {KEY: value}. We deliberately do NOT use
    os.environ here: a daemon-style stale value already exported into this process's
    environment would otherwise mask what the file actually says, defeating the whole
    point of the probe (REC-ops-004)."""
    out: dict = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip().strip("'\"")
    return out


ENV = read_env_file()


def ev(name: str) -> str:
    return (ENV.get(name) or "").strip()


# --------------------------------------------------------------------------- #
# Per-provider probes. Each takes the explicit credential value(s) so we can probe
# BOTH the .env value and a daemon-held stale value with the same code path.
# Returns (status, detail, metric).
# --------------------------------------------------------------------------- #

def probe_brightdata(key: str):
    if not key:
        return SKIP, "BRIGHTDATA_API_KEY not set in .env", ""
    r = requests.get("https://api.brightdata.com/status",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "api authed", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid/expired key", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_facebook(token: str):
    if not token:
        return SKIP, "FACEBOOK_ADS_TOKEN not set in .env", ""
    ver = ev("FACEBOOK_API_VERSION") or "v21.0"
    app_id, secret = ev("FACEBOOK_APP_ID"), ev("FACEBOOK_APP_SECRET")
    inspector = f"{app_id}|{secret}" if (app_id and secret) else token
    r = requests.get(f"https://graph.facebook.com/{ver}/debug_token",
                     params={"input_token": token, "access_token": inspector}, timeout=TIMEOUT)
    if r.status_code != 200:
        body = r.text.lower()
        if "expired" in body:
            return AUTH_ERROR, "token expired", "EXPIRED"
        if "session" in body or "validate" in body:
            return AUTH_ERROR, "token invalid — renew", ""
        return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""
    data = (r.json() or {}).get("data", {})
    if not data.get("is_valid"):
        return AUTH_ERROR, "token is_valid=false", ""
    exp = data.get("expires_at", 0)
    if not exp:  # 0 == never expires
        return OK, "valid, no expiry", "no expiry"
    days = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)).days
    if days <= 7:  # T-7 early warning rather than waiting for death
        return EXPIRING, f"token expires in {days}d — renew now", f"{days}d"
    return OK, "token valid", f"{days}d to expiry"


def probe_posthog(key: str):
    if not key:
        return SKIP, "POSTHOG_PERSONAL_API_KEY not set in .env", ""
    r = requests.get("https://us.posthog.com/api/projects/",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "projects api reachable", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_openrouter(key: str):
    if not key:
        return SKIP, "OPENROUTER_API_KEY not set in .env", ""
    # /key is a free metadata endpoint returning usage + limit for THIS key.
    r = requests.get("https://openrouter.ai/api/v1/key",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        d = (r.json() or {}).get("data", {})
        limit = d.get("limit")
        usage = d.get("usage")
        if limit is not None and usage is not None and usage >= limit:
            return OUT_OF_CREDIT, f"usage {usage} >= limit {limit}", ""
        return OK, f"key valid (usage={usage}, limit={limit})", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_github(token: str):
    if not token:
        return SKIP, "GITHUB_TOKEN not set in .env", ""
    r = requests.get("https://api.github.com/rate_limit",
                     headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        core = r.json().get("resources", {}).get("core", {})
        return OK, "authed", f"{core.get('remaining','?')}/{core.get('limit','?')} core left"
    if r.status_code == 401:
        return AUTH_ERROR, "401 invalid/revoked token", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_justcall(key: str):
    """JustCall v2.1 uses 'Authorization: <api_key>:<api_secret>'. Both come from .env;
    the key is the value we drift-check, the secret is read alongside."""
    if not key:
        return SKIP, "JUSTCALL_API_KEY not set in .env", ""
    secret = ev("JUSTCALL_API_SECRET")
    if not secret:
        return SKIP, "JUSTCALL_API_SECRET not set in .env", ""
    r = requests.get("https://api.justcall.io/v2.1/phone-numbers",
                     headers={"Authorization": f"{key}:{secret}", "Accept": "application/json"},
                     params={"per_page": 1}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "v2.1 api authed", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key/secret", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_propradar(key: str):
    """PropRadar key lives in a keyfile (pr_live_...), not an env var — so it has no
    daemon-drift dimension. Behind Cloudflare, so a browser UA is mandatory (else 403
    error 1010). Cheapest authenticated call: one sold record for one suburb."""
    if not key:
        return SKIP, "PropRadar key (pr_live_...) not found in keyfile", ""
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    r = requests.get("https://api.propradar.com.au/v1/suburbs/QLD/Robina/sold",
                     headers={"X-API-Key": key, "Accept": "application/json", "User-Agent": ua},
                     params={"months": 1, "limit": 1}, timeout=40)
    if r.status_code == 200:
        return OK, "data api authed", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key (or CF block)", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def _google_oauth_probe(refresh_token: str, client_id: str, client_secret: str,
                        label: str):
    """Common Google OAuth refresh-token liveness: mint an access token. A dead/revoked
    refresh token returns 400 invalid_grant."""
    if not refresh_token:
        return SKIP, f"{label} refresh token not set in .env", ""
    if not (client_id and client_secret):
        return SKIP, f"{label} client id/secret not set in .env", ""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=TIMEOUT)
    if r.status_code == 200 and (r.json() or {}).get("access_token"):
        return OK, "refresh token mints an access token", ""
    err = (r.json() or {}).get("error", f"http_{r.status_code}") if r.content else f"http_{r.status_code}"
    if err in ("invalid_grant", "invalid_client") or r.status_code in (400, 401):
        return AUTH_ERROR, f"refresh failed: {err}", ""
    return ERROR, f"HTTP {r.status_code}: {err}", ""


def probe_google_ads(refresh_token: str):
    return _google_oauth_probe(refresh_token, ev("GOOGLE_ADS_CLIENT_ID"),
                               ev("GOOGLE_ADS_CLIENT_SECRET"), "Google Ads")


def probe_google_indexing(refresh_token: str):
    # Indexing reuses the Google Ads OAuth client (see google_indexing.py).
    return _google_oauth_probe(refresh_token, ev("GOOGLE_ADS_CLIENT_ID"),
                               ev("GOOGLE_ADS_CLIENT_SECRET"), "Google Indexing")


def probe_gmail(refresh_token: str):
    if not refresh_token:
        return SKIP, "GMAIL_REFRESH_TOKEN not set in .env", ""
    secret_files = glob.glob(os.path.join(REPO, "client_secret_*.json"))
    if not secret_files:
        return SKIP, "client_secret_*.json not found on VM", ""
    cfg = json.load(open(secret_files[0]))
    c = cfg.get("installed") or cfg.get("web") or {}
    return _google_oauth_probe(refresh_token, c.get("client_id"), c.get("client_secret"),
                               "Gmail")


def _propradar_keyfile_value() -> str:
    """Extract the pr_live_ key the same way propradar_client does, so the probe uses
    the identical credential the pipeline uses."""
    import re
    keyfile = os.environ.get(
        "PROPRADAR_KEYFILE",
        os.path.join(REPO, "00_Run_Commands/gh-token-29Mar.txt"))
    try:
        with open(keyfile) as f:
            m = re.search(r"pr_live_[A-Za-z0-9]+", f.read())
        return m.group(0) if m else ""
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Provider registry.
#   slug, label, env_key (None if not an env var), probe(value)->..., daemon_held
# daemon_held=True means this key is loaded into long-running services and must be
# compared against /proc/<pid>/environ (the REC-ops-004 blind spot).
# --------------------------------------------------------------------------- #

PROVIDERS = [
    ("brightdata", "Bright Data", "BRIGHTDATA_API_KEY", probe_brightdata, True),
    ("facebook_ads", "Facebook Ads", "FACEBOOK_ADS_TOKEN", probe_facebook, True),
    ("posthog", "PostHog", "POSTHOG_PERSONAL_API_KEY", probe_posthog, True),
    ("openrouter", "OpenRouter", "OPENROUTER_API_KEY", probe_openrouter, True),
    ("justcall", "JustCall", "JUSTCALL_API_KEY", probe_justcall, True),
    ("github", "GitHub", "GITHUB_TOKEN", probe_github, True),
    ("google_ads", "Google Ads OAuth", "GOOGLE_ADS_REFRESH_TOKEN", probe_google_ads, True),
    ("google_indexing", "Google Indexing OAuth", "GOOGLE_INDEXING_REFRESH_TOKEN",
     probe_google_indexing, True),
    ("gmail", "Gmail OAuth", "GMAIL_REFRESH_TOKEN", probe_gmail, True),
    ("propradar", "PropRadar", None, probe_propradar, False),  # keyfile, not env
]


# --------------------------------------------------------------------------- #
# Daemon-held credential drift (REC-ops-004 mechanism).
# --------------------------------------------------------------------------- #

def _running_fields_services() -> list[str]:
    try:
        out = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-legend", "--plain", "fields-*.service"],
            capture_output=True, text=True, timeout=20).stdout
        return [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []


def _main_pid(svc: str) -> int:
    try:
        v = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", svc],
                           capture_output=True, text=True, timeout=10).stdout.strip()
        return int(v or "0")
    except Exception:
        return 0


def _read_proc_environ(pid: int) -> dict:
    """Read /proc/<pid>/environ (needs root for cross-user daemons -> sudo -n).
    Returns {} if unreadable — the caller treats that as could-not-check, not clean."""
    if pid <= 0:
        return {}
    try:
        raw = subprocess.run(["sudo", "-n", "cat", f"/proc/{pid}/environ"],
                             capture_output=True, timeout=10)
        if raw.returncode != 0 or not raw.stdout:
            # Fall back to a non-sudo read (same-user process).
            try:
                with open(f"/proc/{pid}/environ", "rb") as f:
                    data = f.read()
            except Exception:
                return {}
        else:
            data = raw.stdout
        env = {}
        for chunk in data.split(b"\0"):
            if b"=" in chunk:
                k, _, v = chunk.partition(b"=")
                env[k.decode(errors="replace")] = v.decode(errors="replace")
        return env
    except Exception:
        return {}


def collect_daemon_environs() -> tuple[dict, bool]:
    """Map svc -> environ dict for every running fields-* daemon.
    Returns (map, readable) — readable=False if we could read NONE (sudo denied),
    which is a could-not-check condition the drift step reports honestly."""
    svcs = _running_fields_services()
    result = {}
    any_read = False
    for svc in svcs:
        env = _read_proc_environ(_main_pid(svc))
        if env:
            any_read = True
        result[svc] = env
    return result, (any_read or not svcs)


def daemon_drift(env_key: str, live_value: str, daemon_map: dict) -> list[str]:
    """Return the list of services holding a value for env_key that DIFFERS from the
    live .env file value. An empty-but-expected key (daemon has it blank while .env has
    it) also counts as drift."""
    if not env_key or not live_value:
        return []
    stale = []
    for svc, env in daemon_map.items():
        if not env:
            continue  # unreadable — handled separately as could-not-check
        held = env.get(env_key)
        if held is None:
            continue  # daemon doesn't use this key
        if held.strip() != live_value.strip():
            stale.append(svc)
    return stale


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def classify_heartbeat(status: str, drift_svcs: list[str]) -> tuple[str, str]:
    """Map a probe result (+ any daemon drift) to a job_runs (status, note)."""
    if drift_svcs:
        return "error", (f"live .env key is fine but {len(drift_svcs)} daemon(s) hold a "
                         f"STALE value: {', '.join(drift_svcs)} — restart them")
    if status in GOOD_STATES:
        return "success", ""
    if status in DEAD_STATES:
        return "error", "credential dead/dying"
    # UNVERIFIED
    return "error", "could not verify credential"


def run(only=None, dry_run=False):
    daemon_map, daemon_readable = collect_daemon_environs()
    from job_status import record_job_result

    checked = 0
    n_error = 0
    rows = []

    for slug, label, env_key, probe, daemon_held in PROVIDERS:
        if only and slug not in only:
            continue

        if slug == "propradar":
            value = _propradar_keyfile_value()
        else:
            value = ev(env_key)

        try:
            status, detail, metric = probe(value)
        except Exception as e:
            status, detail, metric = ERROR, f"{type(e).__name__}: {str(e)[:120]}", ""

        drift = daemon_drift(env_key, value, daemon_map) if daemon_held else []
        hb_status, hb_note = classify_heartbeat(status, drift)

        # If the .env probe passed but we could not read ANY daemon env, we cannot
        # assert the daemon isn't stale — say so rather than claim green (Rule 7b).
        if daemon_held and hb_status == "success" and not daemon_readable:
            hb_status = "error"
            hb_note = "could not read daemon environs (sudo denied) — drift unverifiable"

        # Where a daemon holds a stale value, actively probe it to prove dead vs different.
        drift_detail = ""
        if drift and env_key and slug != "propradar":
            stale_val = daemon_map[drift[0]].get(env_key, "")
            try:
                s_status, s_detail, _ = probe(stale_val)
                drift_detail = f" | daemon-held value probes: {s_status} ({s_detail})"
            except Exception as e:
                drift_detail = f" | daemon-held value probe errored: {type(e).__name__}"

        full_detail = f"probe={status}: {detail}{(' | ' + hb_note) if hb_note else ''}{drift_detail}"
        if metric:
            full_detail = f"{full_detail} [{metric}]"

        checked += 1
        if hb_status == "error":
            n_error += 1
        rows.append((label, hb_status, full_detail))
        print(f"  {hb_status.upper():7} {label:24} {full_detail[:110]}")

        if not dry_run:
            record_job_result(
                f"cred_liveness_{slug}", hb_status,
                detail=full_detail[:250],
                cadence_hours=24, stale_hours=40,
                title=f"Cred liveness: {label}",
                metrics={"probe_status": status, "drift_services": drift})

    # Umbrella heartbeat + Rule 7b zero-output assertion for the runner itself.
    summary = f"{checked} credentials checked, {n_error} error/dying"
    if not dry_run:
        # Zero-output path: if we checked nothing (env failed to load), that is a
        # broken run, not a clean one — record error and raise.
        umbrella_status = "success" if (checked > 0 and n_error == 0) else "error"
        record_job_result(
            "credential_liveness", umbrella_status,
            detail=summary, cadence_hours=24, stale_hours=40,
            title="Credential liveness probe (umbrella)")
        if checked == 0:
            raise RuntimeError("credential_liveness checked 0 credentials — env not loaded")
    print(f"\n{summary}")
    return n_error


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="probe + print, no heartbeats")
    ap.add_argument("--only", help="comma-separated slugs (e.g. brightdata,github)")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    print(f"=== credential liveness — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} ===")
    run(only=only, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
