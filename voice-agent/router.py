"""
Router for the Fields Voice Agent.

Fast triage layer: reads user message and decides one of four paths:
  1. "direct"   — Haiku answers simple queries instantly
  2. "converse" — Opus handles deep conversation (no tools, ~10-30s)
  3. "email"    — Opus handles email conversationally (with tools)
  4. "task"     — Opus background worker (full tools, minutes)

Haiku router stays as subprocess (fast, stateless, structured output).
Opus paths use the Claude Agent SDK with session persistence.
"""

import asyncio
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    StreamEvent,
    UserMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from typing import Callable

# Global permission response channel — used for interactive approval (#2)
# Key: permission_id, Value: asyncio.Future that resolves to True (allow) or False (deny)
_permission_futures: dict[str, asyncio.Future] = {}
_permission_counter = 0


def create_permission_future(tool_name: str, tool_input: dict) -> tuple[str, asyncio.Future]:
    """Create a future that will be resolved when the user approves/denies."""
    global _permission_counter
    _permission_counter += 1
    perm_id = f"perm_{_permission_counter}"
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _permission_futures[perm_id] = future
    return perm_id, future


def resolve_permission(perm_id: str, allow: bool):
    """Called by the /api/permission-respond endpoint."""
    future = _permission_futures.pop(perm_id, None)
    if future and not future.done():
        future.set_result(allow)

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


def _sdk_env() -> dict:
    """Env overrides for Agent SDK calls — strip API key to force Max billing."""
    return {"ANTHROPIC_API_KEY": ""}


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


def _load_todo_summary() -> str:
    """Load pending todos for context injection."""
    import subprocess
    try:
        result = subprocess.run(
            ["python3", "scripts/todo-manager.py", "session-check"],
            capture_output=True, text=True, timeout=5,
            cwd=ORCHESTRATOR_DIR,
            env={**os.environ, "COSMOS_CONNECTION_STRING": os.environ.get("COSMOS_CONNECTION_STRING", "")},
        )
        output = result.stdout.strip()
        if output and "No pending todos" not in output:
            return output
    except Exception as e:
        log.warning(f"Todo session-check failed: {e}")
    return ""


def _load_context_summary() -> str:
    """Load compact context for the router."""
    sections = []

    todo_summary = _load_todo_summary()
    if todo_summary:
        sections.append(f"=== PENDING TODOS ===\n{todo_summary}")

    ops = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops.exists():
        sections.append(f"=== LIVE OPS STATUS ===\n{ops.read_text()}")

    memory_md = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_md.exists():
        sections.append(f"=== MEMORY INDEX ===\n{memory_md.read_text()}")

    return "\n\n".join(sections)


def _load_dynamic_context() -> str:
    """Load dynamic context for Opus modes.

    NOTE: CLAUDE.md is NOT loaded here — the Agent SDK handles it automatically
    via the claude_code system prompt preset when cwd is set to ORCHESTRATOR_DIR.
    We only load runtime-dynamic content here.
    """
    sections = []

    todo_summary = _load_todo_summary()
    if todo_summary:
        sections.append(f"=== PENDING TODOS ===\n{todo_summary}")

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
Your job: read the user's message and classify it into one of four modes.

Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

MODE: "direct" (you answer now, via Haiku — fast, ~2s):
- Greetings, small talk, thanks
- "What's running?" / task status — use the active tasks list below
- Simple factual questions answerable from ops status or memory
- Brief acknowledgments or clarifications
- Reporting completed task results (summaries are below)
- If PENDING TODOS exist in context, mention overdue/due-today items proactively when greeting or at session start

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


# ---------------------------------------------------------------------------
# SDK-based Opus functions (session-persistent)
# ---------------------------------------------------------------------------

async def _sdk_query(
    prompt: str,
    system_append: str,
    session_id: Optional[str] = None,
    tools: Optional[list] = None,
    timeout: int = CONVERSE_TIMEOUT,
    max_turns: int = 30,
    on_stream: Optional[Callable] = None,
) -> tuple[str, Optional[str]]:
    """Core SDK query helper. Returns (response_text, session_id).

    Uses the claude_code preset which auto-loads CLAUDE.md from cwd.
    Dynamic context goes in system_append.

    If on_stream is provided, it's called with (event_type, data_dict) for each
    stream event — enabling real-time SSE updates to the web UI.
    """
    # Use acceptEdits mode — auto-approves file edits and reads,
    # but the agent still sees all tools. For full interactive approval,
    # the SDK's can_use_tool requires AsyncIterable transport (future work).
    options = ClaudeAgentOptions(
        model="opus",
        cwd=ORCHESTRATOR_DIR,
        env=_sdk_env(),
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        include_partial_messages=bool(on_stream),
    )

    if tools is not None:
        options.tools = tools

    if session_id:
        options.resume = session_id

    if system_append:
        options.system_prompt = system_append

    response_text = ""
    new_session_id = None

    try:
        async def _run():
            nonlocal response_text, new_session_id
            async for msg in query(prompt=prompt, options=options):

                # Stream events — forward to SSE
                if isinstance(msg, StreamEvent) and on_stream:
                    event = msg.event or {}
                    event_type = event.get("type", "")
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    # Text being generated
                    if delta_type == "text_delta":
                        on_stream("agent_text", {"text": delta.get("text", "")})

                    # Tool call starting
                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            on_stream("agent_tool_start", {
                                "tool": block.get("name", ""),
                                "id": block.get("id", ""),
                            })

                # Completed tool calls (full blocks)
                elif isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_text = block.text
                        elif isinstance(block, ToolUseBlock) and on_stream:
                            on_stream("agent_tool_call", {
                                "tool": block.name,
                                "input": _summarize_tool_input(block.name, block.input),
                            })

                # Tool results
                elif isinstance(msg, UserMessage) and on_stream:
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            on_stream("agent_tool_result", {
                                "tool_use_id": getattr(block, "tool_use_id", ""),
                            })

                elif isinstance(msg, ResultMessage):
                    new_session_id = msg.session_id
                    if msg.result:
                        response_text = msg.result
                    if on_stream:
                        on_stream("agent_done", {
                            "turns": msg.num_turns,
                            "session_id": msg.session_id,
                        })

        await asyncio.wait_for(_run(), timeout=timeout)

    except asyncio.TimeoutError:
        log.error(f"SDK query timed out after {timeout}s")
        if on_stream:
            on_stream("agent_error", {"error": f"Timed out after {timeout}s"})
        if not response_text:
            response_text = ""
    except Exception as e:
        log.error(f"SDK query error: {e}")
        if on_stream:
            on_stream("agent_error", {"error": str(e)[:200]})
        if not response_text:
            response_text = ""

    return response_text, new_session_id


def _summarize_tool_input(tool_name: str, input_data: dict) -> str:
    """Produce a short human-readable summary of a tool call for the stream."""
    if tool_name == "Bash":
        return input_data.get("command", "")[:200]
    elif tool_name == "Read":
        path = input_data.get("file_path", "")
        return path.replace("/home/fields/Fields_Orchestrator/", "")
    elif tool_name in ("Edit", "Write"):
        path = input_data.get("file_path", "")
        return path.replace("/home/fields/Fields_Orchestrator/", "")
    elif tool_name in ("Grep", "Glob"):
        return input_data.get("pattern", "")[:100]
    else:
        return json.dumps(input_data)[:150]


async def _opus_converse(
    user_text: str,
    history: list[dict],
    session_id: Optional[str] = None,
    on_stream: Optional[Callable] = None,
) -> tuple[str, Optional[str]]:
    """Deep conversation with Opus (no tools — pure thinking).
    Returns (reply_text, new_session_id)."""

    context = _load_dynamic_context()

    system_append = (
        f"You are the Fields Estate agent, having a deep conversation with Will Simpson (founder). "
        f"You have full context on the business, systems, and current state. "
        f"Think carefully and provide substantive, specific advice — not generic strategy talk. "
        f"Be direct, challenge assumptions if warranted, and propose concrete next steps when relevant.\n\n"
        f"NOTE: You are in converse mode (no tools). If the user asks something that requires "
        f"searching the knowledge base, running commands, or accessing email, tell them you'll need to switch — "
        f"suggest they say 'switch to opus' for the full agent, or that this will be picked up as a task.\n\n"
        f"IMPORTANT: If the user's message is simple (a greeting, a quick factual question, a thank you, "
        f"or anything that clearly doesn't need deep reasoning), append the exact text [SWITCH_HAIKU] "
        f"at the very end of your response.\n\n"
        f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
        f"{context}"
    )

    response, sid = await _sdk_query(
        prompt=user_text,
        system_append=system_append,
        session_id=session_id,
        tools=[],  # no tools for converse
        timeout=CONVERSE_TIMEOUT,
        max_turns=1,
        on_stream=on_stream,
    )

    if not response:
        response = "I'm having trouble formulating a response. Could you rephrase?"

    log.info(f"Opus converse: {len(response)} chars, session={sid}")
    return response, sid


async def _opus_email(
    user_text: str,
    history: list[dict],
    session_id: Optional[str] = None,
    on_stream: Optional[Callable] = None,
) -> tuple[str, Optional[str]]:
    """Email-focused Opus conversation with full tools.
    Returns (reply_text, new_session_id)."""

    context = _load_dynamic_context()

    voice_profile = ""
    voice_path = Path(ORCHESTRATOR_DIR) / "config" / "email_voice_profile.md"
    if voice_path.exists():
        voice_profile = voice_path.read_text()

    system_append = (
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
        f"  memory-show / memory-set-recipient  — Email memory management\n"
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

    response, sid = await _sdk_query(
        prompt=user_text,
        system_append=system_append,
        session_id=session_id,
        timeout=OPUS_FULL_TIMEOUT,
        max_turns=30,
        on_stream=on_stream,
    )

    if not response:
        response = "I wasn't able to process that email request. Could you try again?"

    log.info(f"Opus email: {len(response)} chars, session={sid}")
    return response, sid


async def opus_full(
    user_text: str,
    history: list[dict],
    session_id: Optional[str] = None,
    on_stream: Optional[Callable] = None,
) -> tuple[str, Optional[str]]:
    """Full Opus agent with all tools — same as the terminal experience.
    Returns (reply_text, new_session_id)."""

    context = _load_dynamic_context()

    system_append = (
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
        f"TOOLS: You have full access to all tools including TodoWrite, Task (sub-agents), "
        f"WebSearch, WebFetch, and all file/code tools. Use them freely when they help accomplish the task. "
        f"The restriction on TodoWrite/Agent in commit workflows does NOT apply to general conversation.\n\n"
        f"IMPORTANT: If the user's message is simple (a greeting, a quick factual question, a thank you, "
        f"or anything that clearly doesn't need deep reasoning or tools), append the exact text [SWITCH_HAIKU] "
        f"at the very end of your response.\n\n"
        f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
        f"{context}"
    )

    response, sid = await _sdk_query(
        prompt=user_text,
        system_append=system_append,
        session_id=session_id,
        timeout=OPUS_FULL_TIMEOUT,
        max_turns=30,
        on_stream=on_stream,
    )

    if not response:
        response = "I wasn't able to process that. Could you try again?"

    log.info(f"Opus full: {len(response)} chars, session={sid}")
    return response, sid


# ---------------------------------------------------------------------------
# Router (stays as Haiku subprocess — fast, stateless)
# ---------------------------------------------------------------------------

async def route_message(
    user_text: str,
    history: list[dict],
    active_tasks: list[dict],
    completed_tasks: list[dict],
    force_direct: bool = False,
    session_id: Optional[str] = None,
    on_stream: Optional[Callable] = None,
) -> dict:
    """
    Route a user message. Returns:
        {"reply": str, "mode": str, "spawn_task": dict|None, "session_id": str|None}
    """
    # Build conversation context for the router (lightweight, no SDK needed)
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
            return {"reply": "I didn't catch that. Could you say it again?", "mode": "direct", "spawn_task": None, "session_id": session_id}

        try:
            parsed = json.loads(raw)

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
            new_session_id = session_id

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

            # Email mode: synchronous Opus with email tools + session persistence
            if mode == "email" and not force_direct:
                reply, new_session_id = await _opus_email(user_text, history, session_id, on_stream=on_stream)
            elif mode == "email" and force_direct:
                mode = "direct"

            # Converse mode: Opus thinking + session persistence
            if mode == "converse" and not force_direct:
                reply, new_session_id = await _opus_converse(user_text, history, session_id, on_stream=on_stream)
            elif mode == "converse" and force_direct:
                mode = "direct"

            log.info(f"Router: mode={mode}, reply={len(reply)} chars, spawn={'yes: ' + spawn['title'] if spawn else 'no'}")
            return {"reply": reply, "mode": mode, "spawn_task": spawn, "session_id": new_session_id}

        except json.JSONDecodeError:
            log.warning(f"Router JSON parse failed, using raw output")
            return {"reply": raw, "mode": "direct", "spawn_task": None, "session_id": session_id}

    except asyncio.TimeoutError:
        log.error(f"Router timed out after {ROUTER_TIMEOUT}s")
        return {"reply": "Give me a moment, I'm having trouble processing that.", "mode": "direct", "spawn_task": None, "session_id": session_id}
    except Exception as e:
        log.error(f"Router error: {e}")
        return {"reply": f"I hit an error: {str(e)[:200]}", "mode": "direct", "spawn_task": None, "session_id": session_id}
