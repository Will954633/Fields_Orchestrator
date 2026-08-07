#!/usr/bin/env python3
"""
gpt_peer.py — the GPT half of the Claude+GPT editorial pair.

GPT has no tools and no filesystem. Everything it knows about a run arrives through
this module, which is therefore the ONLY channel between the two agents. That makes it
the right place to enforce the two invariants the experiment depends on:

  1. The editorial constitution is injected on EVERY turn. GPT cannot remember it
     between calls and will otherwise write advice we are not allowed to publish.
  2. Every exchange is appended to a transcript on disk before the caller sees it,
     so a run is auditable and re-runnable even if the session dies mid-way.

Usage (from Claude, or from a conductor script):
    from gpt_peer import GptPeer
    peer = GptPeer(run_dir)
    reply = peer.turn("phase1_research", prompt_text)

CLI (for quick manual turns):
    python3 lib/gpt_peer.py --run <run_dir> --phase phase1 --file prompt.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODEL = "gpt-5.6-terra"
AEST = timezone(timedelta(hours=10))
EXP_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = Path("/home/fields/Fields_Orchestrator/00_Run_Commands/gh-token-29Mar.txt")


def _from_token_file(pattern: str) -> str:
    if TOKEN_FILE.exists():
        m = re.search(pattern, TOKEN_FILE.read_text())
        if m:
            return m.group(1)
    return ""


def resolve_route() -> tuple[str, str, str]:
    """
    Pick the transport for gpt-5.6-terra.

    Direct OpenAI is the default; Will topped it up on 2026-08-07 and it is the cheaper path.
    OpenRouter is the fallback and serves the same model as `openai/gpt-5.6-terra`, but its
    balance was NEGATIVE as of 2026-08-07 ($13,748.48 credited / $13,748.62 used) so it will
    402 until topped up. Force either with GPT_ROUTE=openai|openrouter.

    Two credit gotchas worth knowing, both cost us time on 2026-08-07:

    - THE TOKEN FILE WINS OVER THE ENVIRONMENT. There are two different OpenAI keys on this
      VM: `OPENAI_API_KEY` in the shell environment (tail ...GQWLIA) is credit-exhausted,
      while the `GPT API:` entry in the token file (tail ...8LqCIA) is the one Will funds.
      Reading env first sent every call to the dead key and produced a 429 that looks
      exactly like "no credits" — we chased it as a billing problem for a while. Set
      GPT_KEY_SOURCE=env to deliberately override.
    - A credit-exhausted OpenAI account still answers TINY calls. The quota reservation
      scales with prompt + max_completion_tokens, so a "say OK" smoke test returns 200
      while any real prompt returns 429 insufficient_quota. Never treat a small probe as
      proof the route is usable — probe at realistic size (see health_check()).
    - The funded key is scoped to the "Personal" org, NOT the default "Fields Real Estate"
      org. Sending an explicit OpenAI-Organization header for the default org 401s. So we
      send no org header at all and let the key resolve itself.

    Returns (route_name, api_key, model_id).
    """
    forced = os.getenv("GPT_ROUTE", "").strip().lower()
    prefer_env = os.getenv("GPT_KEY_SOURCE", "").strip().lower() == "env"

    def pick(env_name: str, file_pattern: str) -> str:
        env_val = os.getenv(env_name, "").strip()
        file_val = _from_token_file(file_pattern)
        if prefer_env:
            return env_val or file_val
        return file_val or env_val

    openrouter = pick("OPENROUTER_API_KEY", r"Openrouter API key:\s*(\S+)")
    direct = pick("OPENAI_API_KEY", r"GPT API:\s*(sk-\S+)")

    if forced == "openai" and direct:
        return "openai", direct, MODEL
    if forced == "openrouter" and openrouter:
        return "openrouter", openrouter, f"openai/{MODEL}"
    if direct:
        return "openai", direct, MODEL
    if openrouter:
        return "openrouter", openrouter, f"openai/{MODEL}"
    raise SystemExit("No GPT credentials found (need OPENAI_API_KEY or OPENROUTER_API_KEY)")


def load_constitution() -> str:
    path = EXP_DIR / "prompts" / "constitution.md"
    if not path.exists():
        raise SystemExit(f"Missing constitution at {path} — refusing to run uncons­trained")
    return path.read_text()


class GptPeer:
    """One GPT collaborator, bound to one run directory."""

    def __init__(self, run_dir: Path | str, role_prompt: str | None = None):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.transcript = self.run_dir / "transcript.jsonl"
        self.constitution = load_constitution()
        self.role_prompt = role_prompt or (EXP_DIR / "prompts" / "gpt_role.md").read_text()
        from openai import OpenAI

        self.route, key, self.model = resolve_route()
        base_url = "https://openrouter.ai/api/v1" if self.route == "openrouter" else None
        self._client = OpenAI(api_key=key, base_url=base_url)

    def _system_prompt(self) -> str:
        return (
            f"{self.role_prompt}\n\n"
            f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
            "=== EDITORIAL CONSTITUTION (binding, re-read every turn) ===\n"
            f"{self.constitution}"
        )

    def turn(self, phase: str, prompt: str, max_tokens: int = 8000) -> str:
        """One GPT turn. Logged to disk before returning."""
        started = datetime.now(AEST)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=max_tokens,
        )
        reply = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        if not reply:
            raise RuntimeError(
                f"Empty reply from {self.model} via {self.route} — "
                f"finish_reason={resp.choices[0].finish_reason}. Treat as a failed turn, not a silent pass."
            )

        record = {
            "ts": started.isoformat(),
            "phase": phase,
            "speaker": "gpt",
            "model": self.model,
            "route": self.route,
            "prompt": prompt,
            "reply": reply,
            "tokens": {
                "prompt": getattr(usage, "prompt_tokens", None),
                "completion": getattr(usage, "completion_tokens", None),
            },
        }
        with self.transcript.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        return reply

    def log_claude(self, phase: str, text: str, note: str = "") -> None:
        """Record a Claude-side artifact into the same transcript, so the run reads as a dialogue."""
        with self.transcript.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(AEST).isoformat(),
                        "phase": phase,
                        "speaker": "claude",
                        "note": note,
                        "text": text,
                    }
                )
                + "\n"
            )


def health_check() -> None:
    """
    Probe the route at REALISTIC size, because a tiny probe passes on a dead account.
    Run this before starting a run — a mid-run credit failure wastes the turns already spent.
    """
    peer = GptPeer(EXP_DIR / "runs" / "_healthcheck")
    peer.constitution = "[health check — not a content turn]"
    filler = "context padding line.\n" * 400          # ~2k prompt tokens, like a real turn
    reply = peer.turn("health_check", filler + "\nReply with exactly: ROUTE HEALTHY", max_tokens=6000)
    print(f"route={peer.route} model={peer.model} -> {reply[:80]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Take one GPT turn in a collaboration run")
    ap.add_argument("--health-check", action="store_true",
                    help="Probe the route at realistic prompt size and exit")
    ap.add_argument("--run", help="Run directory")
    ap.add_argument("--phase")
    ap.add_argument("--file", help="Prompt file (else stdin)")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--no-constitution", action="store_true",
                    help="Design/meta turns only — never for content turns")
    args = ap.parse_args()

    if args.health_check:
        health_check()
        return
    if not args.run or not args.phase:
        ap.error("--run and --phase are required unless --health-check")

    prompt = Path(args.file).read_text() if args.file else sys.stdin.read()
    peer = GptPeer(args.run)
    if args.no_constitution:
        peer.constitution = ("[NOT A CONTENT TURN — constitution withheld deliberately. "
                             "Do not draft publishable copy in this turn.]")
    print(peer.turn(args.phase, prompt, max_tokens=args.max_tokens))


if __name__ == "__main__":
    main()
