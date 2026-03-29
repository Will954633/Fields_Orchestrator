"""
Router for the Fields Voice Agent.

Fast triage layer: reads user message and decides one of three paths:
  1. "direct"   — Haiku answers simple queries instantly
  2. "converse" — Opus handles deep conversation (no tools, ~10-30s)
  3. "task"     — Opus background worker (full tools, minutes)

All calls go through claude CLI → Max subscription billing.
"""

import asyncio
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("voice-agent.router")

CLAUDE_BIN = "/usr/bin/claude"
ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
MEMORY_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory"
AEST = timezone(timedelta(hours=10))

ROUTER_TIMEOUT = 300  # seconds
CONVERSE_TIMEOUT = 300  # seconds — Opus thinking time for deep conversation
OPUS_FULL_TIMEOUT = 1200  # seconds — Opus with full tools, real dev work


def _cli_env() -> dict:
    """Build env for Claude CLI subprocesses — strip ANTHROPIC_API_KEY so CLI
    uses the Max subscription (OAuth) instead of per-token API billing."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    return env

# JSON schema for structured router output
ROUTER_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "reply": {
            "type": "string",
            "description": "Conversational reply to the user. For 'direct' mode, this IS the final response. For 'converse', set to 'CONVERSE' (will be replaced). For 'task', this is the acknowledgment.",
        },
        "mode": {
            "type": "string",
            "enum": ["direct", "converse", "task"],
            "description": "direct = Haiku already answered. converse = needs Opus-level thinking (no tools). task = spawn background worker.",
        },
        "spawn_task": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short task title, under 60 chars",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Detailed instructions for the Opus worker agent with full VM access.",
                        },
                    },
                    "required": ["title", "prompt"],
                },
                {"type": "null"},
            ],
            "description": "Only set when mode is 'task'. null otherwise.",
        },
    },
    "required": ["reply", "mode", "spawn_task"],
})


def _load_context_summary() -> str:
    """Load compact context for the router."""
    sections = []

    ops = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops.exists():
        sections.append(f"=== LIVE OPS STATUS ===\n{ops.read_text()}")

    memory_md = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_md.exists():
        sections.append(f"=== MEMORY INDEX ===\n{memory_md.read_text()}")

    return "\n\n".join(sections)


def _load_full_context() -> str:
    """Load full context for Opus conversation mode."""
    sections = []

    claude_md = Path(ORCHESTRATOR_DIR) / "CLAUDE.md"
    if claude_md.exists():
        sections.append(claude_md.read_text())

    ops = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops.exists():
        sections.append(f"=== LIVE OPS STATUS ===\n{ops.read_text()}")

    memory_md = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_md.exists():
        sections.append(f"=== PERSISTENT MEMORY ===\n{memory_md.read_text()}")

    memory_dir = Path(MEMORY_DIR)
    if memory_dir.exists():
        parts = []
        for f in sorted(memory_dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            content = f.read_text().strip()
            if content:
                parts.append(f"### {f.stem}\n{content}")
        if parts:
            sections.append(f"=== MEMORY FILES ===\n" + "\n\n".join(parts))

    return "\n\n".join(sections)


def _build_router_system_prompt(
    active_tasks: list[dict],
    completed_tasks: list[dict],
) -> str:
    """Build the system prompt that tells the router how to decide."""

    if active_tasks:
        active_lines = []
        for t in active_tasks:
            elapsed = ""
            if t.get("started_at"):
                try:
                    start = datetime.fromisoformat(t["started_at"])
                    secs = (datetime.now(AEST) - start).total_seconds()
                    elapsed = f" ({int(secs)}s elapsed)"
                except Exception:
                    pass
            active_lines.append(f"  - [{t['status']}] {t['title']}{elapsed} (id: {t['_id']})")
        active_block = "\n".join(active_lines)
    else:
        active_block = "  (none)"

    if completed_tasks:
        completed_lines = []
        for t in completed_tasks:
            summary = (t.get("result_summary") or "")[:150]
            completed_lines.append(f"  - {t['title']}: {summary}")
        completed_block = "\n".join(completed_lines)
    else:
        completed_block = "  (none)"

    context = _load_context_summary()

    return f"""You are the Fields Agent router for Will Simpson (founder, Fields Real Estate).
Your job: read the user's message and classify it into one of three modes.

Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

MODE: "direct" (you answer now, via Haiku — fast, ~2s):
- Greetings, small talk, thanks
- "What's running?" / task status — use the active tasks list below
- Simple factual questions answerable from ops status or memory
- Brief acknowledgments or clarifications
- Reporting completed task results (summaries are below)

MODE: "converse" (escalate to Opus for deep thinking — ~10-30s, no VM tools):
- Strategy discussions, business planning, complex analysis
- Brainstorming, weighing trade-offs, debating approaches
- Lengthy back-and-forth conversation requiring nuanced reasoning
- Anything where the user wants to THINK DEEPLY, not DO something
- When the user asks to "discuss", "talk through", "think about", "help me decide"
- Set reply to "CONVERSE" — it will be replaced by the Opus response.

MODE: "task" (spawn background Opus worker — minutes, full VM access):
- Code changes, bug fixes, script repairs
- Writing drafts, reports, articles
- Running commands, checking logs, investigating issues
- Database queries, data analysis
- Any work requiring file reads/writes on the VM
- **Knowledge base searches** — "what do our strategy docs say about X", "find meeting notes about Y", "what books cover Z"
- **Email operations** — "check my inbox", "search for emails from X", "read that email", "draft a reply", "send an email"
- Set reply to a natural acknowledgment: "On it — I'll search the knowledge base for that." / "Checking your inbox now."
- Set spawn_task.prompt to detailed self-contained instructions for the worker.
- For KB searches, tell the worker to run: python3 scripts/search-kb.py "query" [--type TYPE]
- For email operations, tell the worker to run: python3 scripts/fields-email.py <command>
  Available email commands: inbox, search "query", search-live "query", read <id>, thread <id>, reply <id> --body "text", send --to addr --subject "subj" --body "text", stats
  IMPORTANT for replies/sends: always use --dry-run first and show Will the draft. Only send without --dry-run after explicit approval.

When there are recently completed tasks, naturally mention them in your reply.

ACTIVE TASKS:
{active_block}

RECENTLY COMPLETED (not yet reported):
{completed_block}

{context}"""


async def route_message(
    user_text: str,
    history: list[dict],
    active_tasks: list[dict],
    completed_tasks: list[dict],
    force_direct: bool = False,
) -> dict:
    """
    Route a user message. Returns:
        {{"reply": str, "mode": "direct"|"converse"|"task",
          "spawn_task": None | {{"title": str, "prompt": str}}}}

    If force_direct=True (haiku lock), the router will never escalate to converse
    but can still spawn tasks.
    """
    # Build conversation context
    context_lines = []
    for msg in history[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:500]
        context_lines.append(f"{role}: {content}")

    prompt_parts = []
    if context_lines:
        prompt_parts.append("Recent conversation:\n" + "\n".join(context_lines))
    prompt_parts.append(f"User: {user_text}")

    full_prompt = "\n\n".join(prompt_parts)
    system_prompt = _build_router_system_prompt(active_tasks, completed_tasks)

    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p", full_prompt,
            "--model", "haiku",
            "--tools", "",
            "--effort", "low",
            "--output-format", "json",
            "--json-schema", ROUTER_SCHEMA,
            "--append-system-prompt", system_prompt,
            "--no-session-persistence",
            "--max-budget-usd", "0.05",
            cwd=ORCHESTRATOR_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_cli_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=ROUTER_TIMEOUT)
        raw = stdout.decode().strip()

        if not raw:
            log.warning(f"Router returned empty. stderr: {stderr.decode()[:500]}")
            return {"reply": "I didn't catch that. Could you say it again?", "mode": "direct", "spawn_task": None}

        try:
            parsed = json.loads(raw)

            # Claude CLI --output-format json wraps result in a JSON envelope
            # The actual structured output is in parsed["result"] (text) or parsed["structured_output"]
            if "structured_output" in parsed:
                result = parsed["structured_output"]
            elif "result" in parsed and isinstance(parsed["result"], str):
                try:
                    result = json.loads(parsed["result"])
                except (json.JSONDecodeError, TypeError):
                    result = parsed
            else:
                result = parsed

            mode = result.get("mode", "direct")
            reply = result.get("reply", raw)
            spawn = result.get("spawn_task", None)

            # Validate
            if mode not in ("direct", "converse", "task"):
                mode = "direct"
            if mode == "task" and spawn:
                if not isinstance(spawn, dict) or "title" not in spawn or "prompt" not in spawn:
                    log.warning(f"Invalid spawn_task: {spawn}")
                    spawn = None
                    mode = "direct"
            if mode != "task":
                spawn = None

            # If converse mode, do the Opus conversation call now
            # (unless force_direct is set — haiku lock keeps converse disabled)
            if mode == "converse" and not force_direct:
                reply = await _opus_converse(user_text, history)
            elif mode == "converse" and force_direct:
                mode = "direct"  # downgrade to direct

            log.info(f"Router: mode={mode}, reply={len(reply)} chars, spawn={'yes: ' + spawn['title'] if spawn else 'no'}")
            return {"reply": reply, "mode": mode, "spawn_task": spawn}

        except json.JSONDecodeError:
            log.warning(f"Router JSON parse failed, using raw output")
            return {"reply": raw, "mode": "direct", "spawn_task": None}

    except asyncio.TimeoutError:
        log.error(f"Router timed out after {ROUTER_TIMEOUT}s")
        return {"reply": "Give me a moment, I'm having trouble processing that.", "mode": "direct", "spawn_task": None}
    except Exception as e:
        log.error(f"Router error: {e}")
        return {"reply": f"I hit an error: {str(e)[:200]}", "mode": "direct", "spawn_task": None}


async def _opus_converse(user_text: str, history: list[dict]) -> str:
    """
    Deep conversation with Opus (no tools — pure thinking).
    Used for strategy, brainstorming, complex discussions.
    ~10-30s response time. CLI = Max subscription.
    """
    context_lines = []
    for msg in history[-20:]:  # More history for deep conversation
        role = msg.get("role", "user")
        content = msg.get("content", "")[:1000]  # More content per message
        context_lines.append(f"{role}: {content}")

    prompt_parts = []
    if context_lines:
        prompt_parts.append("Conversation history:\n" + "\n".join(context_lines))
    prompt_parts.append(f"User: {user_text}")
    prompt_parts.append("\nRespond thoughtfully. This is a voice/chat interface so be conversational, but give substantive depth. Don't be artificially brief — match the depth the user is looking for.")

    full_prompt = "\n\n".join(prompt_parts)
    context = _load_full_context()

    system_prompt = (
        f"You are the Fields Estate agent, having a deep conversation with Will Simpson (founder). "
        f"You have full context on the business, systems, and current state. "
        f"Think carefully and provide substantive, specific advice — not generic strategy talk. "
        f"Be direct, challenge assumptions if warranted, and propose concrete next steps when relevant.\n\n"
        f"NOTE: You are in converse mode (no tools). If the user asks something that requires "
        f"searching the knowledge base, running commands, or accessing email, tell them you'll need to switch — "
        f"suggest they say 'switch to opus' for the full agent, or that this will be picked up as a task.\n\n"
        f"IMPORTANT: If the user's message is simple (a greeting, a quick factual question, a thank you, "
        f"or anything that clearly doesn't need deep reasoning), append the exact text [SWITCH_HAIKU] "
        f"at the very end of your response. This signals the system to switch back to fast Haiku routing. "
        f"Only do this when the conversation has clearly become simple — not during active deep discussion.\n\n"
        f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
        f"{context}"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p", full_prompt,
            "--model", "opus",
            "--tools", "",
            "--output-format", "text",
            "--append-system-prompt", system_prompt,
            "--no-session-persistence",
            cwd=ORCHESTRATOR_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_cli_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CONVERSE_TIMEOUT)
        response = stdout.decode().strip()

        if not response:
            log.warning(f"Opus converse returned empty. stderr: {stderr.decode()[:500]}")
            return "I'm having trouble formulating a response. Could you rephrase?"

        log.info(f"Opus converse: {len(response)} chars")
        return response

    except asyncio.TimeoutError:
        log.error(f"Opus converse timed out after {CONVERSE_TIMEOUT}s")
        return "That's a deep question — I ran out of thinking time. Could you break it into a more specific question?"
    except Exception as e:
        log.error(f"Opus converse error: {e}")
        return f"I hit an error: {str(e)[:200]}"


async def opus_full(user_text: str, history: list[dict]) -> str:
    """
    Full Opus agent with all tools — same as the terminal experience.
    Used when user explicitly locks to Opus mode.
    CLI = Max subscription.
    """
    context_lines = []
    for msg in history[-20:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:1000]
        context_lines.append(f"{role}: {content}")

    prompt_parts = []
    if context_lines:
        prompt_parts.append("Conversation history:\n" + "\n".join(context_lines))
    prompt_parts.append(f"User: {user_text}")
    prompt_parts.append("\nThis is a voice/chat interface — be conversational but thorough. "
                        "If the task requires running commands or editing files, do it and report results.")

    full_prompt = "\n\n".join(prompt_parts)
    context = _load_full_context()

    system_prompt = (
        f"You are the Fields Estate operations agent with full VM access, "
        f"talking directly with Will Simpson (founder). "
        f"You can read files, run commands, edit code, query databases — do whatever is needed. "
        f"Be conversational but substantive.\n\n"
        f"KNOWLEDGE BASE: You have access to a 1,644-document knowledge base with 7,000+ chunks "
        f"covering books, strategy docs, marketing plans, meeting notes, code, financials, and operations. "
        f"Search it with: python3 scripts/search-kb.py \"query\" [--type TYPE] [--max N] [--tag TAG]\n"
        f"Categories: book, strategy, marketing, code, financial, operational, meeting_notes, general, project, conversations\n"
        f"Get full chunk: python3 scripts/search-kb.py --chunk CHUNK_ID --file path/to/index.json\n"
        f"List categories: python3 scripts/search-kb.py --list-categories\n"
        f"Use the KB when the user asks about strategy, books, past decisions, marketing plans, meeting notes, or anything that might be in the knowledge base.\n\n"
        f"EMAIL: You can read, search, and send emails via Microsoft Graph (will@fieldsestate.com.au).\n"
        f"CLI: python3 scripts/fields-email.py <command>\n"
        f"Commands: inbox [--limit N --days N], search \"query\", search-live \"query\", read <message_id>, "
        f"thread <id_or_email>, reply <message_id> --body \"text\" [--dry-run], "
        f"send --to addr --subject \"subj\" --body \"text\" [--dry-run], stats\n"
        f"IMPORTANT: For replies and sends, ALWAYS use --dry-run first and show Will the draft. "
        f"Only send live (without --dry-run) after Will explicitly approves.\n\n"
        f"IMPORTANT: If the user's message is simple (a greeting, a quick factual question, a thank you, "
        f"or anything that clearly doesn't need deep reasoning or tools), append the exact text [SWITCH_HAIKU] "
        f"at the very end of your response. This signals the system to switch back to fast Haiku routing. "
        f"Only do this when the conversation has clearly become simple.\n\n"
        f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
        f"{context}"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p", full_prompt,
            "--model", "opus",
            "--output-format", "text",
            "--append-system-prompt", system_prompt,
            "--dangerously-skip-permissions",
            cwd=ORCHESTRATOR_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_cli_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=OPUS_FULL_TIMEOUT)
        response = stdout.decode().strip()

        if not response:
            log.warning(f"Opus full returned empty. stderr: {stderr.decode()[:500]}")
            return "I wasn't able to process that. Could you try again?"

        log.info(f"Opus full: {len(response)} chars")
        return response

    except asyncio.TimeoutError:
        log.error("Opus full timed out after 300s")
        return "That's taking too long. I've timed out after five minutes."
    except Exception as e:
        log.error(f"Opus full error: {e}")
        return f"I hit an error: {str(e)[:200]}"
