#!/usr/bin/env python3
"""
vertex_quota_watch.py
=====================
Polls whether the Vertex AI Claude Sonnet 5 quota has been approved (i.e. a real
call succeeds instead of 429). The moment it's live, sends ONE Telegram alert
with the launch command and drops a sentinel file so it never alerts again.

Intended for a ~30-minute cron. Silent while the quota is still pending.
Delete the sentinel (/home/fields/.vertex-quota-ready) to re-arm.
"""
import os
import sys
from pathlib import Path

SENTINEL = Path("/home/fields/.vertex-quota-ready")
sys.path.insert(0, str(Path(__file__).resolve().parent))

LAUNCH = (
    "✅ Vertex Claude Sonnet 5 quota is LIVE — the editorial batch can run.\n\n"
    "Meter one property first:\n"
    "cd /home/fields/Fields_Orchestrator && source /home/fields/venv/bin/activate && "
    "set -a && source .env && set +a\n"
    "python3 scripts/backend_enrichment/process_viewed_for_sale.py --vertex --process --limit 1\n\n"
    "Then Tranche A (56): same command with --limit 56.\n"
    "(Or just tell your Claude Code agent — it'll meter #1 and run the rest.)"
)


def alert(text):
    try:
        from telegram_notify import send_message
        send_message(text, parse_mode=None)  # plain text — command lines have underscores
    except Exception as e:
        print(f"(telegram alert failed: {e})", file=sys.stderr)


def main():
    if SENTINEL.exists():
        return  # already alerted — self-disabled

    os.environ["ANTHROPIC_BACKEND"] = "vertex"
    os.environ["USE_CLAUDE_MAX"] = "0"
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "/home/fields/.gcp-vertex-key.json")
    os.environ.setdefault("VERTEX_PROJECT_ID", "fields-estate")
    os.environ.setdefault("VERTEX_REGION", "global")
    model = os.environ.get("EDITORIAL_MODEL", "claude-sonnet-5")

    try:
        from anthropic import AnthropicVertex
        client = AnthropicVertex(
            project_id=os.environ["VERTEX_PROJECT_ID"],
            region=os.environ["VERTEX_REGION"],
        )
        client.messages.create(
            model=model, max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
    except Exception as e:
        msg = str(e)
        if any(t in msg for t in ("429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
            print("vertex quota still pending (429)")
        else:
            # Unexpected error (auth/model/etc.) — surface once, don't spam or self-disable.
            print(f"vertex preflight unexpected error: {msg[:200]}", file=sys.stderr)
        return

    # Success — quota is live.
    SENTINEL.write_text("ready\n")
    alert(LAUNCH)
    print("VERTEX READY — Telegram alert sent, sentinel written.")


if __name__ == "__main__":
    main()
