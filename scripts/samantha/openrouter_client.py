#!/usr/bin/env python3
"""
Shared OpenRouter client for the Brain pipeline — replaces the Max `claude -p` CLI shim so
Brain 1/3 development runs on the OpenRouter API instead of the weekly Max budget.

Model policy (Will, 2026-07-19): OPUS usage -> claude-sonnet-5; Haiku stays Haiku (cheap
annotation/judge). Slugs verified on OpenRouter:
  SONNET5 = "anthropic/claude-sonnet-5"      # was: Opus on Max
  HAIKU   = "anthropic/claude-haiku-4.5"     # annotation / decompose / relevance-judge

Key: OPENROUTER_API_KEY (in .env — never committed). Same call signature as the old
call_haiku/call_opus so swapping is a one-line change per caller.
"""
import os, json, time, urllib.request, urllib.error

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SONNET5 = "anthropic/claude-sonnet-5"
HAIKU = "anthropic/claude-haiku-4.5"


def _key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        # fall back to .env so cron/child processes don't need it exported
        envp = "/home/fields/Fields_Orchestrator/.env"
        if os.path.exists(envp):
            for line in open(envp):
                if line.startswith("OPENROUTER_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set (env or .env)")
    return k


def call(prompt, model, timeout=300, max_tokens=8000, retries=3):
    """Send a single-user-message completion; return the assistant text. Retries on 429/5xx."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    headers = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
               "HTTP-Referer": "https://fieldsestate.com.au", "X-Title": "Fields Brain"}
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            return d["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:200].decode(errors='ignore')}"
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f"openrouter {model}: {last}")
        except Exception as e:
            last = str(e)[:200]
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            raise RuntimeError(f"openrouter {model}: {last}")


if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else HAIKU
    print(call("Reply with exactly: OK", m, timeout=60))
