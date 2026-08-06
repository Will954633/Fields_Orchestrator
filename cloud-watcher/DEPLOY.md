# Off-VM VM Watchdog — Deploy / Operate Runbook

**Purpose:** detect when `fields-orchestrator-vm` wedges (OOM hang) from *outside* the
VM and alert Will, with an optional one-tap reset. Removes "reset from my laptop" from
the loop. See `main.py` for design.

## Status — Tier A is LIVE (deployed 2026-07-27, redeployed 2026-08-06)
> **2026-08-06 redeploy:** detection logic fixed (see below) + `HARD_STALE_MIN=20` added.
> Verified live: ports-up-but-stale now returns `wedged`. All other env vars and the
> `tg-bot-token` secret binding were preserved by using `--update-env-vars`.

Deployed by Claude while authenticated as `will.simpson@blueoceans.com.au` on the VM.
Everything below Tier A is already running; the commands are recorded for
reproduce/teardown. **Tier B (phone reset button) is not yet set up** — it needs a
Telegram bot only Will can create (see bottom).

**What's running now:**
- **Heartbeat:** VM cron `* * * * * scripts/write_heartbeat.sh` re-uploads
  `gs://fields-vm-watchdog/vm-heartbeat.txt` every minute.
- **Watcher:** Cloud Function (gen2) `vm-watcher`, region `australia-southeast1`,
  entry `vm_watcher`, run URL `https://vm-watcher-h3kmcnnsca-ts.a.run.app`.
- **Schedule:** Cloud Scheduler `vm-watcher-ping`, `*/3 * * * *`, OIDC via
  `vm-watcher-invoker@fields-estate.iam.gserviceaccount.com`.
- **State:** `gs://fields-vm-watchdog/vm-watchdog-state.json` (alert/reset cooldowns).
- **Alerts:** via the existing @WillFieldsBot (`tg-bot-token` secret). Verified live —
  a forced wedge sent the Telegram end-to-end.

> **Heartbeat is GCS, not Cosmos.** Cosmos (Azure) firewalls off GCP Cloud Function
> egress, so a Cosmos-based heartbeat returned null from the function. GCS is always
> reachable from GCP and decouples the safety net from both the VM and Cosmos.

### Detection logic (revised 2026-08-06 — the old rule missed a real wedge)
- `wedged` = heartbeat older than `STALE_MIN` (8) **AND** a port dead → Telegram alert
  (never auto-resets).
- `wedged` = heartbeat older than **`HARD_STALE_MIN` (20)**, *regardless of ports*.
- `degraded` = heartbeat stale 8–20 min but ports up → soft note, probably just the cron.

**Why the second rule exists.** On 2026-08-01 and 2026-08-06 a runaway `ugrep` drove the
box into disk thrash: the workbench was dead and SSH eventually unusable, but nginx/443
and sshd/22 kept accepting connections. The old "stale **AND** dead port" rule classified
that as merely `degraded` and sent a note saying *"likely a cron issue, NOT a hang"* — the
exact opposite of the truth — so no real alert ever fired and the box sat wedged for 9
hours. **Ports answering does not mean the guest is usable.** A healthy VM rewrites the
heartbeat every 60 s; 20 consecutive misses is not a blip.

**The heartbeat is now a liveness+usability signal.** `scripts/write_heartbeat.sh` probes
`/healthz` first and *withholds* the heartbeat if the workbench is not serving, so a
"ports up but wedged" box goes stale on purpose. Fail-safe direction: withholding can
only ever cause an alert, never a false all-clear.

⚠ **Probe `/healthz` with `curl -sL`, never bare `/`.** A bare `curl http://127.0.0.1:8080/`
returns 302 in ~27 ms even when completely wedged (that handler never touches the
extension host), and `systemctl is-active code-server` stays `active` throughout. Both
gave a false all-clear on 2026-08-06.

**Verifying the ports-up path without paging Will:** pre-set the state object to
`{"last_status":"wedged"}` (alerts only fire on *transitions*), redeploy with
`--update-env-vars=HARD_STALE_MIN=0`, invoke, and confirm the response is
`{"status": "wedged", ..., "ports": {"22": true, "443": true}}`. Then restore
`HARD_STALE_MIN=20` and reset the state to `{"last_status":"ok"}`. Done live 2026-08-06.

---

## Reproduce Tier A from scratch (if ever torn down)
```bash
gcloud config set project fields-estate
gcloud config set account will.simpson@blueoceans.com.au

# 1. APIs
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

# 2. Bot-token secret (value from the VM .env TELEGRAM_BOT_TOKEN)
printf '%s' 'PASTE_TELEGRAM_BOT_TOKEN' | gcloud secrets create tg-bot-token --data-file=-
RUNTIME_SA=419034603899-compute@developer.gserviceaccount.com
gcloud secrets add-iam-policy-binding tg-bot-token \
  --member="serviceAccount:${RUNTIME_SA}" --role=roles/secretmanager.secretAccessor

# 3. Dedicated heartbeat/state bucket + function SA access
gcloud storage buckets create gs://fields-vm-watchdog --location=australia-southeast1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding gs://fields-vm-watchdog \
  --member="serviceAccount:${RUNTIME_SA}" --role=roles/storage.objectAdmin

# 4. VM heartbeat cron (on the VM)
chmod +x scripts/write_heartbeat.sh
( crontab -l 2>/dev/null; echo '* * * * * /home/fields/Fields_Orchestrator/scripts/write_heartbeat.sh >> /tmp/vm-heartbeat.log 2>&1' ) | crontab -

# 5. Deploy the watcher
cd cloud-watcher
gcloud functions deploy vm-watcher --gen2 --runtime=python312 --region=australia-southeast1 \
  --source=. --entry-point=vm_watcher --trigger-http --no-allow-unauthenticated \
  --memory=256Mi --timeout=30s \
  --set-secrets='TELEGRAM_BOT_TOKEN=tg-bot-token:latest' \
  --set-env-vars='TELEGRAM_CHAT_ID=PASTE_CHAT_ID,VM_IP=34.40.230.132,VM_INSTANCE=fields-orchestrator-vm,VM_ZONE=australia-southeast1-b,VM_PROJECT=fields-estate,STALE_MIN=8,HARD_STALE_MIN=20,HEARTBEAT_BUCKET=fields-vm-watchdog,HEARTBEAT_OBJECT=vm-heartbeat.txt,STATE_OBJECT=vm-watchdog-state.json'
RUN_URL=$(gcloud functions describe vm-watcher --region=australia-southeast1 --gen2 --format='value(serviceConfig.uri)')

# 6. Scheduler every 3 min (OIDC)
gcloud iam service-accounts create vm-watcher-invoker --display-name="VM watcher scheduler invoker"
INVOKER=vm-watcher-invoker@fields-estate.iam.gserviceaccount.com
gcloud run services add-iam-policy-binding vm-watcher --region=australia-southeast1 \
  --member="serviceAccount:${INVOKER}" --role=roles/run.invoker
gcloud scheduler jobs create http vm-watcher-ping --location=australia-southeast1 \
  --schedule='*/3 * * * *' --uri="$RUN_URL" --http-method=GET \
  --oidc-service-account-email="$INVOKER" --oidc-token-audience="$RUN_URL"
```

### Test the alert without a real wedge
```bash
# point at an unreachable IP + stale=0 -> forces "wedged" -> real Telegram; then revert
gcloud functions deploy vm-watcher --gen2 --region=australia-southeast1 --source=. \
  --entry-point=vm_watcher --update-env-vars='VM_IP=192.0.2.1,STALE_MIN=0'
gcloud scheduler jobs run vm-watcher-ping --location=australia-southeast1   # sends the alert
gcloud functions deploy vm-watcher --gen2 --region=australia-southeast1 --source=. \
  --entry-point=vm_watcher --update-env-vars='VM_IP=34.40.230.132,STALE_MIN=8'
# clear the test cooldown:
printf '{"last_status":"ok"}' | gcloud storage cp - gs://fields-vm-watchdog/vm-watchdog-state.json
```

---

## Tier B — one-tap reset button from your phone (optional, ~10 min, needs Will)
Adds a button so a wedge can be fixed from your phone with no terminal. Requires a
**separate** Telegram bot (the existing bot is used by the on-VM polling bridges; a
webhook would conflict) — **only Will can create it** — plus a narrow reset grant.

1. **Will:** message **@BotFather** → `/newbot` → e.g. `Fields VM Watchdog`; copy the
   token; send the new bot one message. Then hand Claude the token (or run):
   ```bash
   printf '%s' 'PASTE_WATCHDOG_BOT_TOKEN' | gcloud secrets create tg-watchdog-token --data-file=-
   gcloud secrets add-iam-policy-binding tg-watchdog-token \
     --member="serviceAccount:419034603899-compute@developer.gserviceaccount.com" \
     --role=roles/secretmanager.secretAccessor
   ```
2. Deploy the callback function + grant it reset-only permission:
   ```bash
   cd cloud-watcher
   SECRET=$(openssl rand -hex 8)
   gcloud functions deploy vm-reset-callback --gen2 --runtime=python312 \
     --region=australia-southeast1 --source=. --entry-point=vm_reset_callback \
     --trigger-http --allow-unauthenticated --memory=256Mi --timeout=60s \
     --set-secrets='VM_WATCHDOG_BOT_TOKEN=tg-watchdog-token:latest,TELEGRAM_BOT_TOKEN=tg-bot-token:latest' \
     --set-env-vars="TELEGRAM_CHAT_ID=PASTE_CHAT_ID,VM_INSTANCE=fields-orchestrator-vm,VM_ZONE=australia-southeast1-b,VM_PROJECT=fields-estate,RESET_SECRET=${SECRET}"
   CB_URL=$(gcloud functions describe vm-reset-callback --region=australia-southeast1 --gen2 --format='value(serviceConfig.uri)')
   FN_SA=$(gcloud functions describe vm-reset-callback --region=australia-southeast1 --gen2 --format='value(serviceConfig.serviceAccountEmail)')
   gcloud iam roles create vmReset --project=fields-estate --title="VM reset only" \
     --permissions=compute.instances.reset --stage=GA
   gcloud compute instances add-iam-policy-binding fields-orchestrator-vm \
     --zone=australia-southeast1-b --member="serviceAccount:${FN_SA}" \
     --role="projects/fields-estate/roles/vmReset"
   curl -s "https://api.telegram.org/botPASTE_WATCHDOG_BOT_TOKEN/setWebhook?url=${CB_URL}"
   ```
3. Tell the watcher to use the button:
   ```bash
   gcloud functions deploy vm-watcher --gen2 --region=australia-southeast1 --source=. \
     --entry-point=vm_watcher --update-secrets='VM_WATCHDOG_BOT_TOKEN=tg-watchdog-token:latest' \
     --update-env-vars="RESET_SECRET=${SECRET}"
   ```
Tapping **🔁 Reset VM now** (only from Will's chat id) issues the reset; a 30-min
cooldown prevents reset-loops.

---

## Cost & teardown
Functions gen2 + Scheduler at 3-min cadence: effectively free (~14k invocations/mo).
Teardown: `gcloud scheduler jobs delete vm-watcher-ping --location=australia-southeast1`;
`gcloud functions delete vm-watcher --region=australia-southeast1 --gen2` (and
`vm-reset-callback`); `gcloud storage rm -r gs://fields-vm-watchdog`;
`gcloud secrets delete tg-bot-token` (and `tg-watchdog-token`); remove the VM cron.
