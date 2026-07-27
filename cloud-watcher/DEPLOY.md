# Off-VM VM Watchdog — Deploy Runbook

**Purpose:** detect when `fields-orchestrator-vm` wedges (OOM hang) from *outside* the
VM and alert Will, with an optional one-tap reset. This is the safety net that removes
"reset from my laptop" from the loop. See `main.py` for design.

**Who runs this:** you (Will), or any session authenticated as
`will.simpson@blueoceans.com.au` — the VM's own service account is read-only and
**cannot** deploy Cloud Functions or grant IAM, so this can't run from the VM itself.

Run from your laptop where `gcloud auth list` shows `will.simpson@blueoceans.com.au`.

```bash
gcloud config set project fields-estate
gcloud config set account will.simpson@blueoceans.com.au
```

Everything is **alert-first**: nothing power-cycles the VM automatically. Tier A alerts
you with a copy-paste reset command. Tier B adds a phone button that resets on your tap.

---

## Tier A — detection + alert (required, ~10 min, no new bot, no reset permission)

### 1. Enable APIs
```bash
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

### 2. Store secrets (Cosmos string + the existing @WillFieldsBot token)
Get the values from the VM's `/home/fields/Fields_Orchestrator/.env`
(`COSMOS_CONNECTION_STRING`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
```bash
printf '%s' 'PASTE_COSMOS_CONNECTION_STRING' | gcloud secrets create cosmos-conn --data-file=-
printf '%s' 'PASTE_TELEGRAM_BOT_TOKEN'      | gcloud secrets create tg-bot-token --data-file=-
```

### 3. Deploy the watcher function (Python 3.12, gen2, HTTP, auth required)
```bash
cd cloud-watcher
gcloud functions deploy vm-watcher \
  --gen2 --runtime=python312 --region=australia-southeast1 \
  --source=. --entry-point=vm_watcher --trigger-http --no-allow-unauthenticated \
  --memory=256Mi --timeout=30s \
  --set-secrets='COSMOS_CONNECTION_STRING=cosmos-conn:latest,TELEGRAM_BOT_TOKEN=tg-bot-token:latest' \
  --set-env-vars='TELEGRAM_CHAT_ID=PASTE_CHAT_ID,VM_IP=34.40.230.132,VM_INSTANCE=fields-orchestrator-vm,VM_ZONE=australia-southeast1-b,VM_PROJECT=fields-estate,STALE_MIN=8'
```
Grab the URL:
```bash
URL=$(gcloud functions describe vm-watcher --region=australia-southeast1 --gen2 --format='value(serviceConfig.uri)')
echo "$URL"
```

### 4. Scheduler job — ping every 3 minutes (with OIDC auth)
```bash
# a dedicated invoker service account
gcloud iam service-accounts create vm-watcher-invoker --display-name="VM watcher scheduler invoker"
INVOKER="vm-watcher-invoker@fields-estate.iam.gserviceaccount.com"
gcloud run services add-iam-policy-binding vm-watcher \
  --region=australia-southeast1 --member="serviceAccount:${INVOKER}" --role=roles/run.invoker

gcloud scheduler jobs create http vm-watcher-ping \
  --location=australia-southeast1 --schedule='*/3 * * * *' \
  --uri="$URL" --http-method=GET \
  --oidc-service-account-email="$INVOKER" --oidc-token-audience="$URL"
```

### 5. Smoke test
```bash
gcloud scheduler jobs run vm-watcher-ping --location=australia-southeast1
gcloud functions logs read vm-watcher --region=australia-southeast1 --gen2 --limit=20
```
A healthy VM returns `{"status":"ok",...}` and sends no message. To prove alerting works,
temporarily set `STALE_MIN=0` (redeploy `--update-env-vars STALE_MIN=0`), confirm you get
the Telegram, then set it back to 8.

**Tier A is complete.** When the VM wedges you'll get a Telegram with the exact
`gcloud compute instances reset ...` command to run.

---

## Tier B — one-tap reset button from your phone (optional, ~10 min)

Adds a button so you don't need a terminal. Requires a **separate** Telegram bot (the
existing bot is used by the on-VM polling bridges; a webhook would conflict) and grants
the reset function permission to power-cycle the VM.

### 1. Create the watchdog bot
In Telegram, message **@BotFather** → `/newbot` → name it e.g. `Fields VM Watchdog`.
Copy the token. Send the new bot any message once (so it can DM you). Store the token:
```bash
printf '%s' 'PASTE_WATCHDOG_BOT_TOKEN' | gcloud secrets create tg-watchdog-token --data-file=-
```

### 2. Deploy the callback function (public URL; secured by chat-id + shared secret)
```bash
cd cloud-watcher
SECRET=$(openssl rand -hex 8)      # save this; it goes in both functions
gcloud functions deploy vm-reset-callback \
  --gen2 --runtime=python312 --region=australia-southeast1 \
  --source=. --entry-point=vm_reset_callback --trigger-http --allow-unauthenticated \
  --memory=256Mi --timeout=60s \
  --set-secrets='COSMOS_CONNECTION_STRING=cosmos-conn:latest,VM_WATCHDOG_BOT_TOKEN=tg-watchdog-token:latest,TELEGRAM_BOT_TOKEN=tg-bot-token:latest' \
  --set-env-vars="TELEGRAM_CHAT_ID=PASTE_CHAT_ID,VM_INSTANCE=fields-orchestrator-vm,VM_ZONE=australia-southeast1-b,VM_PROJECT=fields-estate,RESET_SECRET=${SECRET}"
CB_URL=$(gcloud functions describe vm-reset-callback --region=australia-southeast1 --gen2 --format='value(serviceConfig.uri)')
```

### 3. Grant the callback function permission to reset the VM (narrow custom role)
```bash
# the function's runtime SA (default compute SA unless you set one)
FN_SA=$(gcloud functions describe vm-reset-callback --region=australia-southeast1 --gen2 \
  --format='value(serviceConfig.serviceAccountEmail)')

gcloud iam roles create vmReset --project=fields-estate \
  --title="VM reset only" --permissions=compute.instances.reset --stage=GA
gcloud compute instances add-iam-policy-binding fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --member="serviceAccount:${FN_SA}" --role="projects/fields-estate/roles/vmReset"
```

### 4. Point the watchdog bot's webhook at the callback function
```bash
curl -s "https://api.telegram.org/botPASTE_WATCHDOG_BOT_TOKEN/setWebhook?url=${CB_URL}"
```

### 5. Tell the watcher to use the button (redeploy vm-watcher with the extra vars)
```bash
gcloud functions deploy vm-watcher --gen2 --region=australia-southeast1 --source=. \
  --entry-point=vm_watcher --update-secrets='VM_WATCHDOG_BOT_TOKEN=tg-watchdog-token:latest' \
  --update-env-vars="RESET_SECRET=${SECRET}"
```

### 6. Test the button end-to-end
Redeploy vm-watcher with `STALE_MIN=0` briefly → you get an alert from the watchdog bot
with a **🔁 Reset VM now** button. Tapping it (only works from your chat id) issues the
reset and confirms back. A `RESET_COOLDOWN_MIN=30` guard prevents reset-loops. Set
`STALE_MIN` back to 8 when done.

---

## Cost & teardown
- Cloud Functions gen2 + Scheduler at 3-min cadence: effectively free (well within GCP
  free tier — ~14k invocations/mo).
- Teardown: `gcloud scheduler jobs delete vm-watcher-ping`, `gcloud functions delete vm-watcher`
  (and `vm-reset-callback`), `gcloud secrets delete ...`, `gcloud iam roles delete vmReset`.

## How it maps to the failure we had
- Heartbeat = `system_monitor.vm_metrics` (written every minute on the VM). When the VM
  wedged, writes stopped → heartbeat goes stale within minutes.
- Ports 22/443 both went dead in the incident → the second, independent confirmation.
- Requiring BOTH (stale AND a dead port) avoids false alarms from a transient Cosmos or
  network blip. A stale heartbeat with ports still up is reported as "degraded", not wedged.
