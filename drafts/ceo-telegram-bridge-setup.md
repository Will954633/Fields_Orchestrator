# CEO Telegram Bridge

Telegram chat bridge between the founder and the remote Codex CEO team.

## What it does

- Polls Telegram for new messages from approved chat IDs
- Stores chat sessions and message history in `system_monitor`
- Refreshes the CEO context snapshot before replies when needed
- SSHes to the remote Codex VM and runs a single CEO-team advisory response
- Sends the reply back into Telegram

## Files

- `scripts/ceo-telegram-bridge.py`
- `fields-ceo-telegram.service`
- `scripts/ceo-agent-launcher.py` (model default aligned with remote availability)

## Required `.env` values

Add these locally on the VM:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

Optional:

```bash
CEO_TELEGRAM_MODEL=gpt-5.4
CEO_TELEGRAM_REMOTE_HOST=fields-orchestrator-vm@35.201.6.222
CEO_TELEGRAM_REMOTE_CONTEXT_DIR=/home/fields-orchestrator-vm/ceo-agents/context
CEO_TELEGRAM_CONTEXT_SYNC_MINUTES=30
CEO_TELEGRAM_POLL_SECONDS=2
CEO_TELEGRAM_REMOTE_TIMEOUT_SECONDS=1200
CEO_TELEGRAM_HISTORY_LIMIT=12
```

## Find your Telegram chat ID

1. Start a chat with the bot and send any message.
2. Open:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

3. Read `message.chat.id` from the JSON and add it to `TELEGRAM_ALLOWED_CHAT_IDS`.

## Commands in Telegram

- `/start` — intro/help
- `/status` — bridge/session status
- `/reset` — start a fresh CEO chat session
- `/sync` — force a context refresh before the next reply

## Deploy on the VM

```bash
sudo cp /home/fields/Fields_Orchestrator/fields-ceo-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fields-ceo-telegram
sudo systemctl status fields-ceo-telegram
```

## MongoDB collections

All in `system_monitor`:

- `ceo_chat_sessions`
- `ceo_chat_messages`
- `ceo_chat_bridge_state`

## Notes

- The bot only accepts text messages for now.
- Unauthorized chat IDs are ignored.
- Replies are advisory only; the bridge does not run code changes on production.
