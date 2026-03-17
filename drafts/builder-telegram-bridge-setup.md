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
BUILDER_TELEGRAM_MODEL=gpt-5.1-codex
BUILDER_TELEGRAM_ROLE=builder
BUILDER_TELEGRAM_POLL_SECONDS=2
BUILDER_TELEGRAM_TIMEOUT_SECONDS=1800
BUILDER_TELEGRAM_HISTORY_LIMIT=12
```

## Commands in Telegram

- `/start` — intro/help
- `/status` — bridge/session status
- `/reset` — start a fresh builder session

Everything else is sent to local Codex as a task in this repository.

## MongoDB collections

All in `system_monitor`:

- `builder_chat_sessions`
- `builder_chat_messages`
- `builder_chat_bridge_state`

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
- Each inbound Telegram message triggers a fresh local `codex exec` run with recent conversation history included in the prompt.
