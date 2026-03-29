"""
GPT Agent for the Fields Voice Agent.

Provides GPT-5.4 and GPT-5.4-mini with full tool access equivalent to
what Opus gets via the Claude CLI: bash, file read/write/edit, glob, grep,
plus memory read/write.

Uses OpenAI function calling in a loop until the model produces a final response.
"""

import asyncio
import glob as glob_module
import json
import logging
import os
import subprocess
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("voice-agent.gpt")

ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
MEMORY_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory"
AEST = timezone(timedelta(hours=10))

# Model IDs
GPT54_MODEL = "gpt-5.4-2026-03-05"
GPT54_MINI_MODEL = "gpt-5.4-mini-2026-03-17"

MAX_TOOL_ROUNDS = 25  # Safety limit on agent loop iterations
BASH_TIMEOUT = 120  # seconds per bash command
GPT_MAX_COMPLETION_TOKENS = 4096
GPT_CONVERSE_MAX_COMPLETION_TOKENS = 1200


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a bash command on the VM. Use for running scripts, git, "
                "systemctl, python, database queries, and any system operations. "
                "Working directory is /home/fields/Fields_Orchestrator."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120, max 600)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file from the filesystem. Returns the file contents. "
                "Use absolute paths. Can read text files, Python, JS, YAML, MD, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-based)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of lines to read (default: 2000)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file (creates or overwrites). Use absolute paths. "
                "Use this for creating new files or complete rewrites. "
                "For small changes to existing files, prefer edit_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a file by replacing an exact string with a new string. "
                "The old_string must match exactly (including whitespace/indentation). "
                "Use for surgical edits to existing files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": (
                "Find files matching a glob pattern. "
                "Returns a list of matching file paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '**/*.py', 'src/*.ts')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory to search in (default: /home/fields/Fields_Orchestrator)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": (
                "Search file contents using ripgrep (regex supported). "
                "Returns matching lines with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in (default: /home/fields/Fields_Orchestrator)",
                    },
                    "glob": {
                        "type": "string",
                        "description": "File glob filter (e.g. '*.py', '*.ts')",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case insensitive search (default: false)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _execute_bash(command: str, timeout: int = BASH_TIMEOUT) -> str:
    """Execute a bash command and return stdout+stderr."""
    timeout = min(timeout, 600)
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ORCHESTRATOR_DIR,
            env={
                **os.environ,
                "PATH": "/home/fields/venv/bin:" + os.environ.get("PATH", ""),
            },
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if result.stdout else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output[:50000] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[Command timed out after {timeout}s]"
    except Exception as e:
        return f"[Error executing command: {e}]"


def _execute_read_file(path: str, offset: int = None, limit: int = None) -> str:
    """Read a file, optionally with offset and limit."""
    try:
        p = Path(path)
        if not p.exists():
            return f"[File not found: {path}]"
        if not p.is_file():
            return f"[Not a file: {path}]"

        lines = p.read_text(errors="replace").splitlines(keepends=True)
        start = (offset - 1) if offset and offset > 0 else 0
        end = (start + limit) if limit else len(lines)
        selected = lines[start:end]

        # Format with line numbers
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i}\t{line.rstrip()}")
        return "\n".join(numbered)[:50000] or "(empty file)"
    except Exception as e:
        return f"[Error reading file: {e}]"


def _execute_write_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"[Error writing file: {e}]"


def _execute_edit_file(path: str, old_string: str, new_string: str) -> str:
    """Edit a file by replacing old_string with new_string."""
    try:
        p = Path(path)
        if not p.exists():
            return f"[File not found: {path}]"

        content = p.read_text()
        count = content.count(old_string)
        if count == 0:
            return f"[old_string not found in {path}]"
        if count > 1:
            return f"[old_string found {count} times — must be unique. Provide more context.]"

        new_content = content.replace(old_string, new_string, 1)
        p.write_text(new_content)
        return f"Edited {path} — replaced 1 occurrence"
    except Exception as e:
        return f"[Error editing file: {e}]"


def _execute_glob(pattern: str, path: str = None) -> str:
    """Find files matching a glob pattern."""
    try:
        base = Path(path) if path else Path(ORCHESTRATOR_DIR)
        matches = sorted(base.glob(pattern))[:200]
        if not matches:
            return "(no matches)"
        return "\n".join(str(m) for m in matches)
    except Exception as e:
        return f"[Error: {e}]"


def _execute_grep(pattern: str, path: str = None, file_glob: str = None,
                  case_insensitive: bool = False) -> str:
    """Search file contents using ripgrep."""
    try:
        cmd = ["rg", "--no-heading", "-n", "--max-count=100"]
        if case_insensitive:
            cmd.append("-i")
        if file_glob:
            cmd.extend(["--glob", file_glob])
        cmd.append(pattern)
        cmd.append(path or ORCHESTRATOR_DIR)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=ORCHESTRATOR_DIR,
        )
        output = result.stdout[:50000]
        return output or "(no matches)"
    except subprocess.TimeoutExpired:
        return "[Search timed out]"
    except FileNotFoundError:
        # Fallback to grep if rg not installed
        cmd = ["grep", "-rn"]
        if case_insensitive:
            cmd.append("-i")
        if file_glob:
            cmd.extend(["--include", file_glob])
        cmd.append(pattern)
        cmd.append(path or ORCHESTRATOR_DIR)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout[:50000] or "(no matches)"
        except Exception as e:
            return f"[Error: {e}]"
    except Exception as e:
        return f"[Error: {e}]"


def _dispatch_tool(name: str, args: dict) -> str:
    """Dispatch a tool call to the appropriate handler."""
    if name == "bash":
        return _execute_bash(args["command"], args.get("timeout", BASH_TIMEOUT))
    elif name == "read_file":
        return _execute_read_file(args["path"], args.get("offset"), args.get("limit"))
    elif name == "write_file":
        return _execute_write_file(args["path"], args["content"])
    elif name == "edit_file":
        return _execute_edit_file(args["path"], args["old_string"], args["new_string"])
    elif name == "glob_files":
        return _execute_glob(args["pattern"], args.get("path"))
    elif name == "grep_search":
        return _execute_grep(
            args["pattern"], args.get("path"), args.get("glob"),
            args.get("case_insensitive", False),
        )
    else:
        return f"[Unknown tool: {name}]"


# ---------------------------------------------------------------------------
# Context loading (same as router.py / task_manager.py)
# ---------------------------------------------------------------------------

def _load_full_context() -> str:
    """Load full project context for GPT system prompt."""
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


def _load_converse_context() -> str:
    """Load a compact context block for low-latency GPT chat replies."""
    sections = []

    ops = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops.exists():
        ops_text = ops.read_text()
        sections.append("=== LIVE OPS STATUS (TRUNCATED) ===\n" + ops_text[:6000])

    memory_md = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_md.exists():
        memory_text = memory_md.read_text()
        sections.append("=== MEMORY INDEX (TRUNCATED) ===\n" + memory_text[:3000])

    return "\n\n".join(sections)


def _build_system_prompt(mode: str = "full") -> str:
    """Build system prompt for GPT agent."""
    context = _load_converse_context() if mode == "converse" else _load_full_context()
    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")

    base = (
        f"You are the Fields Estate operations agent running on the VM (fields-orchestrator-vm). "
        f"You are talking with Will Simpson (founder, Fields Real Estate, Gold Coast). "
        f"Current time: {now}\n\n"
    )

    if mode == "full":
        base += (
            "You have FULL VM access via tools: bash commands, file read/write/edit, glob, grep. "
            "You can run scripts, query databases, edit code, deploy to GitHub, and do anything "
            "the Claude Opus agent can do on this VM.\n\n"
            "MEMORY SYSTEM: You can read and write persistent memory files in "
            f"{MEMORY_DIR}/. Read MEMORY.md for the index, read individual .md files "
            "for details, and write new memory files using write_file.\n\n"
            "KNOWLEDGE BASE: Search with: bash command 'python3 scripts/search-kb.py \"query\" [--type TYPE]'\n"
            "EMAIL: Use 'python3 scripts/fields-email.py <command>' (inbox, search, read, reply, send).\n"
            "IMPORTANT for email: always use --dry-run first for replies/sends.\n\n"
            "GITHUB PUSH (git push hangs — use gh api):\n"
            "  SHA=$(gh api 'repos/Will954633/REPO/contents/PATH' --jq '.sha')\n"
            "  CONTENT=$(base64 -w0 < /local/path)\n"
            "  gh api 'repos/Will954633/REPO/contents/PATH' --method PUT "
            "--field message=\"desc\" --field content=\"$CONTENT\" --field sha=\"$SHA\"\n\n"
            "Be conversational but thorough. If a task requires running commands or editing files, do it.\n\n"
        )
    else:
        # Converse mode — no tools, just thinking
        base += (
            "You are in conversation mode — think deeply, provide substantive analysis, "
            "challenge assumptions, and propose concrete next steps. "
            "Be direct and specific, not generic.\n\n"
        )

    base += context
    return base


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def _get_openai_client():
    """Get OpenAI client."""
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


async def gpt_converse(
    user_text: str,
    history: list[dict],
    model: str = GPT54_MODEL,
) -> str:
    """
    GPT conversation mode — no tools, just deep thinking.
    Like _opus_converse but using GPT.
    """
    client = _get_openai_client()
    system_prompt = _build_system_prompt(mode="converse")

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in history[-8:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:400]
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=messages,
            max_completion_tokens=GPT_CONVERSE_MAX_COMPLETION_TOKENS,
            temperature=0.7,
        )
        reply = response.choices[0].message.content or ""
        log.info(f"GPT converse ({model}): {len(reply)} chars")
        return reply.strip()
    except Exception as e:
        log.error(f"GPT converse error: {e}")
        return f"GPT error: {str(e)[:200]}"


async def gpt_full(
    user_text: str,
    history: list[dict],
    model: str = GPT54_MODEL,
) -> str:
    """
    Full GPT agent with tools — equivalent to opus_full().
    Runs an agentic loop: GPT calls tools, we execute them, feed results back.
    """
    client = _get_openai_client()
    system_prompt = _build_system_prompt(mode="full")

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in history[-20:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:1000]
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    final_text_parts = []

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                tools=TOOLS,
                max_completion_tokens=GPT_MAX_COMPLETION_TOKENS,
                temperature=0.3,
            )
        except Exception as e:
            log.error(f"GPT agent error (round {round_num}): {e}")
            if final_text_parts:
                return "\n".join(final_text_parts) + f"\n\n(GPT error on round {round_num}: {str(e)[:100]})"
            return f"GPT error: {str(e)[:200]}"

        choice = response.choices[0]
        msg = choice.message

        # Add assistant message to history
        messages.append(msg)

        # Collect any text content
        if msg.content:
            final_text_parts.append(msg.content)

        # If no tool calls, we're done
        if not msg.tool_calls:
            break

        # Execute tool calls
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            log.info(f"GPT tool call: {fn_name}({json.dumps(fn_args)[:200]})")

            # Run tool in thread to avoid blocking
            result = await asyncio.to_thread(_dispatch_tool, fn_name, fn_args)

            # Truncate very large results
            if len(result) > 50000:
                result = result[:50000] + "\n...(truncated)"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        # Check finish reason
        if choice.finish_reason == "stop":
            break

    result = "\n".join(final_text_parts).strip()
    log.info(f"GPT full ({model}): {len(result)} chars, {round_num + 1} rounds")
    return result or "(GPT produced no response)"


async def gpt_worker(prompt: str, model: str = GPT54_MODEL) -> str:
    """
    GPT background worker — equivalent to a Claude CLI task worker.
    Full tools, no conversation history needed.
    """
    return await gpt_full(prompt, history=[], model=model)
