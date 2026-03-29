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
            "description": "Conversational reply to the user. For 'direct' mode, this IS the final response. For 'converse'/'email', set to 'CONVERSE' (will be replaced). For 'task', this is the acknowledgment.",
        },
        "mode": {
            "type": "string",
            "enum": ["direct", "converse", "task", "email"],
            "description": "direct = Haiku already answered. converse = needs Opus-level thinking (no tools). email = email operations handled conversationally by Opus with tools. task = spawn background worker.",
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

MODE: "email" (Opus handles email conversationally — synchronous, with tools):
- ANY email-related request: "check my inbox", "search for emails from X", "read that email",
  "what did Y say about Z", "draft a reply", "reply to that", "send an email to Z"
- This mode gives Opus direct access to email tools so Will can discuss, review, edit, and approve replies inline
- Set reply to "CONVERSE" — Opus will handle the full interaction with email tools
- spawn_task must be null for this mode
- Opus uses python3 scripts/fields-email.py for all email operations
- Replies/sends always go through dry-run first, Will approves, then live send

MODE: "task" (spawn background Opus worker — minutes, full VM access):
- Code changes, bug fixes, script repairs
- Writing drafts, reports, articles
- Running commands, checking logs, investigating issues
- Database queries, data analysis
- Any work requiring file reads/writes on the VM
- **Knowledge base searches** — "what do our strategy docs say about X", "find meeting notes about Y", "what books cover Z"
- Set reply to a natural acknowledgment: "On it — I'll search the knowledge base for that."
- Set spawn_task.prompt to detailed self-contained instructions for the worker.
- For KB searches, tell the worker to run: python3 scripts/search-kb.py "query" [--type TYPE]

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
            if mode not in ("direct", "converse", "task", "email"):
                mode = "direct"
            if mode == "task" and spawn:
                if not isinstance(spawn, dict) or "title" not in spawn or "prompt" not in spawn:
                    log.warning(f"Invalid spawn_task: {spawn}")
                    spawn = None
                    mode = "direct"
            if mode not in ("task",):
                spawn = None

            # Email mode: synchronous Opus with email tools
            if mode == "email" and not force_direct:
                reply = await _opus_email(user_text, history)
            elif mode == "email" and force_direct:
                mode = "direct"  # can't do email in haiku-lock

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


async def _opus_email(user_text: str, history: list[dict]) -> str:
    """
    Email-focused Opus conversation with full tools.
    Handles inbox, read, draft, reply, send — all inline in the chat.
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
    prompt_parts.append(
        "\nHandle this email request conversationally. Use the email tools, "
        "show results clearly, and if drafting a reply, present it for Will's "
        "approval before sending."
    )

    full_prompt = "\n\n".join(prompt_parts)
    context = _load_full_context()

    # Load Will's email voice profile
    voice_profile = ""
    voice_path = Path(ORCHESTRATOR_DIR) / "config" / "email_voice_profile.md"
    if voice_path.exists():
        voice_profile = voice_path.read_text()

    system_prompt = (
        f"You are the Fields Estate operations agent handling email for Will Simpson (founder). "
        f"You have full VM access and email tools.\n\n"
        f"EMAIL TOOLS (all via python3 scripts/fields-email.py):\n"
        f"  inbox [--limit N --days N]         — List unread emails from Graph API\n"
        f"  search \"query\" [--from-addr X]      — Search local email archive (FTS5)\n"
        f"  search-live \"query\"                 — Search via Graph API\n"
        f"  read <message_id>                   — Read full email content\n"
        f"  thread <message_id_or_email>        — Conversation history with contact\n"
        f"  recipient-profile <id_or_email>     — Style analysis + memory for recipient\n"
        f"  draft-reply <message_id> [--instructions \"text\"] — AI-drafted reply in Will's voice\n"
        f"  reply <message_id> --body \"text\" --dry-run — Preview a reply\n"
        f"  reply <message_id> --body \"text\"    — Send reply (LIVE — only after Will approves)\n"
        f"  send --to addr --subject \"X\" --body \"Y\" --dry-run — Preview new email\n"
        f"  send --to addr --subject \"X\" --body \"Y\" — Send new email (LIVE — only after approval)\n"
        f"  memory-show                         — View email memory/preferences\n"
        f"  memory-set-recipient --email X --style-profile Y — Update recipient preferences\n"
        f"  stats                               — Archive statistics\n\n"
        f"WORKFLOW FOR REPLIES:\n"
        f"1. Read the email: fields-email.py read <id>\n"
        f"2. Check recipient context: fields-email.py recipient-profile <id>\n"
        f"3. Draft the reply: fields-email.py draft-reply <id> [--instructions \"...\"]\n"
        f"4. Show the draft to Will clearly (subject, body, any cautions)\n"
        f"5. If Will approves: fields-email.py reply <id> --body \"approved text\"\n"
        f"   If Will wants changes: revise and show again\n"
        f"   NEVER send without explicit approval from Will.\n\n"
        f"WILL'S EMAIL VOICE:\n{voice_profile}\n\n"
        f"IMPORTANT: If Will's message is simple (thanks, done, etc.), append [SWITCH_HAIKU] "
        f"at the end to switch back to fast routing.\n\n"
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
            log.warning(f"Opus email returned empty. stderr: {stderr.decode()[:500]}")
            return "I wasn't able to process that email request. Could you try again?"

        log.info(f"Opus email: {len(response)} chars")
        return response

    except asyncio.TimeoutError:
        log.error(f"Opus email timed out after {OPUS_FULL_TIMEOUT}s")
        return "That email operation took too long. Could you try a simpler request?"
    except Exception as e:
        log.error(f"Opus email error: {e}")
        return f"I hit an error with the email tools: {str(e)[:200]}"


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
        f"Commands:\n"
        f"  inbox [--limit N --days N]         — List unread emails\n"
        f"  search \"query\" [--from-addr X]     — Search local archive\n"
        f"  search-live \"query\"                — Search via Graph API\n"
        f"  read <message_id>                  — Read full email\n"
        f"  thread <id_or_email>               — Conversation history\n"
        f"  recipient-profile <id_or_email>    — Style analysis for recipient\n"
        f"  draft-reply <id> [--instructions \"text\"] — AI-drafted reply in Will's voice\n"
        f"  reply <id> --body \"text\" --dry-run — Preview reply\n"
        f"  reply <id> --body \"text\"           — Send reply (LIVE — only after Will approves)\n"
        f"  send --to X --subject \"Y\" --body \"Z\" --dry-run — Preview new email\n"
        f"  send --to X --subject \"Y\" --body \"Z\" — Send (LIVE — only after approval)\n"
        f"  memory-show / memory-set-recipient — Email memory management\n"
        f"WORKFLOW: read → recipient-profile → draft-reply → show draft → Will approves → send live\n"
        f"IMPORTANT: NEVER send without explicit approval from Will.\n\n"
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
