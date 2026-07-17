#!/usr/bin/env python3
"""
claude_max_client.py
====================
Drop-in, Anthropic-SDK-compatible client that routes text generation through
the Claude Code CLI (`claude -p`) so it bills against the **Claude Max
subscription** instead of the pay-as-you-go Anthropic API.

Why: the article workflows kept failing with HTTP 400 "credit balance too low"
whenever the console API account ran dry. The VM already carries a Claude Max
subscription (used by the voice agent, KB, etc.). Routing generation through the
`claude` CLI removes the marginal-cost / credit-exhaustion failure mode.

Usage — swap one line at each call site:

    # from:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    # to:
    from claude_max_client import make_client
    client = make_client(api_key=ANTHROPIC_API_KEY)

The returned object exposes the same surface the pipeline uses:
    resp = client.messages.create(model=..., max_tokens=..., system=..., messages=[...])
    text = resp.content[0].text

Routing / safety:
  * Max path is used when env USE_CLAUDE_MAX is truthy ("1"/"true"/"yes").
    Otherwise make_client() returns a real anthropic.Anthropic — a no-op swap.
  * The Max path AUTOMATICALLY falls back to the real Anthropic API when:
      - the request uses features the CLI shim can't express faithfully
        (server tools like web_search, or non-string / image message content), or
      - the `claude` CLI errors / returns is_error after retries.
    Fallback needs a usable ANTHROPIC_API_KEY; without one, the original error
    is raised so the failure is visible rather than silent.
  * When invoking the CLI we strip ANTHROPIC_API_KEY (and CLAUDECODE) from the
    child environment so the CLI authenticates via CLAUDE_CODE_OAUTH_TOKEN and
    bills Max — never the API key.

Auth on the runner: set CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) as a
GitHub secret and expose it in the workflow env. The token is user-agnostic, so
it works even though the self-hosted runner runs as a user without ~/.claude.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Optional

# How long to allow a single generation before giving up and (maybe) falling back.
_CLI_TIMEOUT_S = int(os.environ.get("CLAUDE_MAX_CLI_TIMEOUT", "300"))
_CLI_RETRIES = int(os.environ.get("CLAUDE_MAX_CLI_RETRIES", "2"))
_CLI_BIN = os.environ.get("CLAUDE_BIN", "claude")


def _use_max() -> bool:
    return os.environ.get("USE_CLAUDE_MAX", "").strip().lower() in {"1", "true", "yes", "on"}


def _model_alias(model: str) -> str:
    """Map an Anthropic model id to a CLI alias the Max subscription honours."""
    m = (model or "").lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"


# ── Response shim (mimics the bits of the SDK response the pipeline reads) ──────

class _TextBlock:
    __slots__ = ("type", "text")

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Usage:
    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self, input_tokens: int = 0, output_tokens: int = 0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    __slots__ = ("content", "usage", "stop_reason", "model", "role", "id")

    def __init__(self, text: str, usage: _Usage, model: str, stop_reason: str = "end_turn"):
        self.content = [_TextBlock(text)]
        self.usage = usage
        self.stop_reason = stop_reason
        self.model = model
        self.role = "assistant"
        self.id = None


# ── The CLI-backed client ──────────────────────────────────────────────────────

class _CliUnsupported(Exception):
    """Raised when a request can't be faithfully served by the CLI shim."""


def _flatten_messages(messages: list[dict]) -> str:
    """Turn a messages[] array into a single prompt string.

    The common pipeline case is a single user turn with string content. Multi-turn
    or non-string (image/tool) content is treated as unsupported so the caller can
    fall back to the real API rather than silently dropping data.
    """
    if not messages:
        raise _CliUnsupported("empty messages")

    parts: list[str] = []
    single_user = len(messages) == 1 and messages[0].get("role") == "user"
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, str):
            # list-of-blocks → images / tool_result / tool_use: not shimmable
            raise _CliUnsupported("non-string message content")
        role = msg.get("role", "user")
        if single_user:
            return content
        prefix = "Human" if role == "user" else "Assistant"
        parts.append(f"{prefix}: {content}")
    return "\n\n".join(parts)


class _Messages:
    def __init__(self, parent: "MaxClient"):
        self._parent = parent

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 2048,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        stop_sequences: Optional[list] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[Any] = None,
        **_ignored: Any,
    ) -> _Response:
        # Server tools (web_search, etc.) and tool loops aren't expressible via the
        # one-shot CLI shim — route these to the real API.
        if tools:
            return self._parent._fallback(
                "tools requested",
                model=model, max_tokens=max_tokens, messages=messages, system=system,
                temperature=temperature, stop_sequences=stop_sequences,
                tools=tools, tool_choice=tool_choice,
            )
        try:
            prompt = _flatten_messages(messages)
        except _CliUnsupported as e:
            return self._parent._fallback(
                str(e),
                model=model, max_tokens=max_tokens, messages=messages, system=system,
                temperature=temperature, stop_sequences=stop_sequences,
            )

        try:
            return self._parent._run_cli(prompt=prompt, system=system, model=model)
        except Exception as e:  # noqa: BLE001 — any CLI failure → try the API
            return self._parent._fallback(
                f"cli error: {e}",
                model=model, max_tokens=max_tokens, messages=messages, system=system,
                temperature=temperature, stop_sequences=stop_sequences,
            )


class MaxClient:
    """Anthropic-compatible client backed by the Claude Code CLI (Max billing)."""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or ""
        self._fallback_client = None  # lazily built real anthropic.Anthropic
        self.messages = _Messages(self)

    # -- CLI invocation --------------------------------------------------------

    def _child_env(self) -> dict:
        env = dict(os.environ)
        # Force Max billing: the CLI must NOT see the API key, and must not think
        # it's nested inside another Claude Code session.
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        env.pop("CLAUDECODE", None)
        env.setdefault("CI", "true")
        return env

    def _run_cli(self, *, prompt: str, system: Optional[str], model: str) -> _Response:
        cmd = [
            _CLI_BIN, "-p",
            "--model", _model_alias(model),
            "--output-format", "json",
            "--max-turns", "1",
            "--no-session-persistence",
        ]
        if system:
            cmd += ["--system-prompt", system]

        last_err: Optional[Exception] = None
        for attempt in range(1, _CLI_RETRIES + 1):
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=_CLI_TIMEOUT_S,
                    env=self._child_env(),
                )
            except subprocess.TimeoutExpired as e:
                last_err = e
                continue

            if proc.returncode != 0:
                last_err = RuntimeError(
                    f"claude exited {proc.returncode}: {(proc.stderr or '')[:300]}"
                )
                continue

            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                last_err = RuntimeError(f"non-JSON CLI output: {e}: {proc.stdout[:200]}")
                continue

            if data.get("is_error") or data.get("subtype") != "success":
                last_err = RuntimeError(
                    f"CLI returned error: {data.get('subtype')}: "
                    f"{str(data.get('result'))[:300]}"
                )
                continue

            text = data.get("result", "")
            usage_raw = data.get("usage") or {}
            usage = _Usage(
                input_tokens=int(usage_raw.get("input_tokens", 0) or 0),
                output_tokens=int(usage_raw.get("output_tokens", 0) or 0),
            )
            return _Response(text=text, usage=usage, model=data.get("model") or model)

        raise last_err or RuntimeError("claude CLI failed with no diagnostic")

    # -- Fallback to the real API ---------------------------------------------

    def _fallback(self, reason: str, **create_kwargs: Any) -> _Response:
        if not self._api_key:
            raise RuntimeError(
                f"Claude Max CLI path unavailable ({reason}) and no ANTHROPIC_API_KEY "
                f"set for fallback"
            )
        if self._fallback_client is None:
            import anthropic  # local import so the module loads without the SDK present
            self._fallback_client = anthropic.Anthropic(api_key=self._api_key)
        # Drop None values so we don't override SDK defaults.
        kwargs = {k: v for k, v in create_kwargs.items() if v is not None}
        print(f"  ⚠️  claude_max_client: falling back to Anthropic API ({reason})")
        return self._fallback_client.messages.create(**kwargs)


# ── Factory ────────────────────────────────────────────────────────────────────

def make_client(api_key: str = "", use_max: Optional[bool] = None):
    """Return a Max-backed client when enabled, else a real anthropic.Anthropic.

    Enable the Max path with env USE_CLAUDE_MAX=1 (or pass use_max=True). When
    disabled this is a transparent drop-in for anthropic.Anthropic(api_key=...).
    """
    enabled = _use_max() if use_max is None else use_max
    if enabled:
        return MaxClient(api_key=api_key)
    import anthropic
    return anthropic.Anthropic(api_key=api_key)
