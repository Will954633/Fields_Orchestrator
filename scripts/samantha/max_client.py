#!/usr/bin/env python3
"""
Shared Claude MAX client for the Brain pipeline — a drop-in replacement for
openrouter_client.py. Routes every brain LLM call through the Anthropic **Max
subscription** via the `claude -p` CLI (zero marginal cost), instead of the metered
OpenRouter API that ran dry (HTTP 402 on every call → all brains dead, 2026-07-30).

Model policy (Will, 2026-07-31):
  • QUERY & deep-synthesis  -> Opus on Max  (OPUS / SONNET5 constants -> claude-opus-4-8)
  • annotation / decompose / judge -> Haiku on Max  (HAIKU constant)

MAX-ONLY, NEVER SILENT: on Max weekly/5-hour quota exhaustion this raises
`MaxQuotaExhausted` (after a Telegram alert) so callers PAUSE cleanly and resume next
window — it does NOT fall through to a metered API and does NOT silent-skip like the 402
loop did. Callers that loop over items should catch MaxQuotaExhausted and break.

Same call signature as openrouter_client.call(prompt, model, timeout, max_tokens, retries)
+ the same HAIKU / SONNET5 module constants, so swapping a caller is one line:
    import openrouter_client as orc   ->   import max_client as orc

Auth: runs as user `projects`, whose interactive Max login lives at
/home/projects/.claude/.credentials.json — no token/API key needed. The child env strips
CLAUDECODE/ANTHROPIC_API_KEY so the CLI (a) doesn't refuse as a "nested session" and
(b) is guaranteed to bill Max, not pay-as-you-go.
"""
import os, sys, json, time, subprocess, urllib.request

# Full model ids — this Max account resolves full ids correctly; a bare "opus" alias
# collapses to a stale tier (see CLAUDE.md [EDITORIAL-MAX-OPUS48]).
HAIKU = "claude-haiku-4-5-20251001"
OPUS = "claude-opus-4-8"
SONNET5 = OPUS  # back-compat: the query tier is now Opus on Max (Will 2026-07-31), not sonnet-5

# stderr markers that mean the Max limit was hit — pause + alert, don't retry/skip-loop.
_QUOTA_MARKERS = ("usage limit", "weekly limit", "5-hour limit", "limit reached",
                  "rate limit", "quota", "resets at", "reset at", "too many requests",
                  "upgrade to", "out of usage")


class MaxQuotaExhausted(RuntimeError):
    """Raised when the Anthropic Max subscription quota is exhausted. Callers should stop
    and resume in the next window — NOT skip the item and NOT fall back to a metered API."""


def _alias(model):
    return HAIKU if "haiku" in (model or "").lower() else OPUS


def _child_env():
    drop = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT", "ANTHROPIC_API_KEY")
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.setdefault("CI", "true")
    return env


def _alert_quota(model, detail):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    text = ("\U0001F9E0⏸ *Brain paused — Max quota exhausted*\n"
            f"model `{model}`\n\n`{str(detail)[:180]}`\n\n"
            "Jobs pause cleanly and resume automatically next Max window. "
            "No metered fallback (Max-only, by design).")
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "Markdown"}).encode(),
            headers={"Content-Type": "application/json"}), timeout=20)
    except Exception:
        pass


def call(prompt, model, timeout=300, max_tokens=8000, retries=3):
    """Run one completion on Max via `claude -p`; return the assistant text.

    `max_tokens` is accepted for signature-compatibility with openrouter_client (the CLI
    manages its own output budget). Raises MaxQuotaExhausted on Max limit exhaustion,
    RuntimeError on other persistent failure.
    """
    alias = _alias(model)
    last = None
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["claude", "-p", "--model", alias,
                 "--settings", '{"alwaysThinkingEnabled":false}'],
                input=prompt, capture_output=True, text=True,
                timeout=timeout, env=_child_env(),
            )
        except subprocess.TimeoutExpired:
            last = f"timeout after {timeout}s"
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f"max {alias}: {last}")

        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()

        if r.returncode != 0:
            errl = (err + " " + out).lower()
            if any(m in errl for m in _QUOTA_MARKERS):
                _alert_quota(alias, err or out)
                raise MaxQuotaExhausted(f"max {alias}: quota exhausted — {(err or out)[:180]}")
            last = f"exit {r.returncode}: {err[:200]}"
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f"max {alias}: {last}")

        if not out:
            last = "empty output"
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f"max {alias}: {last}")
        return out
    raise RuntimeError(f"max {alias}: {last}")


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else HAIKU
    print(call("Reply with exactly: OK", m, timeout=60))
