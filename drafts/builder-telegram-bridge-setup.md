# Builder Telegram Bridge

Telegram bridge between the founder and the local Codex builder instance on this VM.

## What it does

- Polls Telegram for new messages from approved chat IDs
- Stores chat sessions and message history in `system_monitor`
- Runs local `codex exec` inside `/home/fields/Fields_Orchestrator`
- Sends the result back into Telegram

## Files

- `scripts/builder-telegram-bridge.py`
- `fields-builder-telegram.service`

## Required `.env` values

```bash
BUILDER_TELEGRAM_BOT_TOKEN=...
BUILDER_TELEGRAM_ALLOWED_CHAT_IDS=7827588865
```

Optional:

```bash
BUILDER_TELEGRAM_MODEL=gpt-5.4
BUILDER_TELEGRAM_ROLE=builder
BUILDER_TELEGRAM_POLL_SECONDS=2
BUILDER_TELEGRAM_TIMEOUT_SECONDS=1800
BUILDER_TELEGRAM_HISTORY_LIMIT=12
```

## Commands in Telegram

- `/start` — intro/help
- `/status` — bridge/session status
- `/reset` — start a fresh builder session

## Implementation Workflow

The Implementor bridge now supports an approval gate for CEO-team-driven work.

### 1. Review only

Send a message like:

```text
review ceo team's recommendations for today
```

This triggers a local Codex review pass that:
- reads the latest CEO run artifacts
- reads founder request threads and CEO responses
- validates or invalidates CEO suggestions
- returns a proposed implementation plan to Telegram

No code changes are allowed in this step.
Any error, missing dependency, or blocked step encountered during review should be turned into an explicit TODO item in the proposed plan.

### 2. Revise the plan

If you want to amend the plan before implementation:

```text
revise plan: do telemetry first, defer API work
```

This updates the pending plan and returns a revised review. No code changes are made here either.

### 3. Approve implementation

Only after a plan is in place:

```text
approve plan
```

Or:

```text
implement items 1 and 3
```

This triggers execution against the approved scope only.
Any execution error or blocked step should be turned into an explicit TODO item in the final implementation response.

### 4. Cancel

```text
cancel plan
```

This clears the pending plan. No code changes are made.

## Runtime Behavior

- Builder jobs now run asynchronously in the background instead of blocking the Telegram poll loop.
- While a review, revise, execute, or direct builder run is active, the bridge continues responding to Telegram messages.
- Founder check-ins like `status`, `update`, `how are you going`, or `are you stuck` return the live job state from MongoDB, including elapsed time, the latest heartbeat, and the recent Codex log tail.
- Only one active builder job is allowed per chat session. New work requests are rejected until the active job finishes.

## Artifacts

Implementation review and execution runs are written under:

```text
artifacts/implementation-runs/YYYY-MM-DD/
```

Each run stores the founder request, generated prompt, result, and metadata.

## Error TODOs

The Implementor session now keeps a small persistent list of error TODOs in session state.

- Bridge-level failures are added automatically.
- Review and execution prompts also instruct Codex to convert encountered errors into explicit TODO items.
- `/status` shows whether the session currently has pending error TODOs.

## MongoDB collections

All in `system_monitor`:

- `builder_chat_sessions`
- `builder_chat_messages`
- `builder_chat_bridge_state`
- `builder_chat_jobs`

## Deploy on the VM

```bash
sudo cp /home/fields/Fields_Orchestrator/fields-builder-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fields-builder-telegram
sudo systemctl status fields-builder-telegram
```

## Notes

- The bot accepts text messages only.
- Unauthorized chat IDs are ignored.
- Each builder run is started as a tracked background job with recent conversation history included in the prompt.
- `/status` and plain-English status check-ins read the active job state instead of waiting for the job to finish.
