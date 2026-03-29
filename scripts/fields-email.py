#!/usr/bin/env python3
"""Convenience wrapper around the email CLI with local compatibility fixes.

Usage from Claude Code / orchestrator context:
    python3 scripts/fields-email.py inbox
    python3 scripts/fields-email.py search "query"
    python3 scripts/fields-email.py read <id>
    python3 scripts/fields-email.py reply <id> --body "text"
    python3 scripts/fields-email.py send --to addr --subject "subj" --body "text"
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EMAIL_CLI = "/home/fields/samantha-email-agent/email_cli.py"
EMAIL_AGENT_DIR = "/home/fields/samantha-email-agent"
VENV_PYTHON = "/home/fields/venv/bin/python3"
ENV_FILE = "/home/fields/Fields_Orchestrator/.env"


def _load_env():
    env = os.environ.copy()
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env.setdefault(key, value)
    return env


def _load_graph_tools(env):
    import types

    agents_mock = types.ModuleType("agents")

    def function_tool(fn=None, **kwargs):
        if fn is None:
            return lambda f: f
        return fn

    agents_mock.function_tool = function_tool
    agents_mock.Agent = type("Agent", (), {})
    agents_mock.Runner = type("Runner", (), {})
    sys.modules["agents"] = agents_mock

    os.environ.update(env)
    os.environ.setdefault("EMAIL_AGENT_ROOT", EMAIL_AGENT_DIR)
    if EMAIL_AGENT_DIR not in sys.path:
        sys.path.insert(0, EMAIL_AGENT_DIR)

    import email_graph_tools as graph

    graph.ROOT_DIR = Path(EMAIL_AGENT_DIR)
    graph.TOOLS_DIR = Path(EMAIL_AGENT_DIR)
    return graph


def _format_read_result(payload):
    if payload.get("status") != "success":
        return payload, 1

    event = payload.get("event") or {}
    sender = event.get("sender") or {}
    to_recipients = event.get("to") or []
    cc_recipients = event.get("cc") or []
    attachments = event.get("attachments") or []

    formatted = {
        "status": "success",
        "source": payload.get("source") or payload.get("mode"),
        "email": {
            "id": event.get("message_id", ""),
            "from": sender.get("email", ""),
            "from_name": sender.get("name", ""),
            "to": [r.get("email", "") for r in to_recipients],
            "cc": [r.get("email", "") for r in cc_recipients],
            "subject": event.get("subject", ""),
            "date": event.get("received_at", ""),
            "body": event.get("body_text", "") or "",
            "attachments": [
                {
                    "name": a.get("filename", ""),
                    "id": a.get("id", ""),
                    "size_mb": a.get("size_mb", 0),
                    "content_type": a.get("content_type"),
                }
                for a in attachments
            ],
        },
    }
    return formatted, 0


def _cmd_read(env, message_id):
    graph = _load_graph_tools(env)
    payload = graph.get_email_with_attachments_core(message_id)
    output, rc = _format_read_result(payload)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return rc


def _cmd_dry_run_reply(env, message_id, body, cc, bcc):
    graph = _load_graph_tools(env)
    payload = graph.get_email_with_attachments_core(message_id)
    output, rc = _format_read_result(payload)
    if rc != 0:
        return rc
    email = output.get('email', {})
    preview = {
        'status': 'dry_run',
        'action': 'reply',
        'message_id': message_id,
        'to': email.get('from', ''),
        'subject': f"Re: {email.get('subject', '')}" if email.get('subject') else 'Re:',
        'cc': cc or [],
        'bcc': bcc or [],
        'body': body,
    }
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


def _cmd_dry_run_send(to, subject, body, cc, bcc):
    preview = {
        'status': 'dry_run',
        'action': 'send',
        'to': to,
        'subject': subject,
        'cc': cc or [],
        'bcc': bcc or [],
        'body': body,
    }
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


def _cmd_thread(env, identifier, limit):
    graph = _load_graph_tools(env)
    email_address = identifier

    if "@" not in identifier:
        payload = graph.get_email_with_attachments_core(identifier)
        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        email_address = sender.get("email", "").strip()
        if not email_address:
            print(json.dumps({
                "status": "error",
                "message": "Could not resolve an email address from that message ID.",
            }, indent=2))
            return 1

    result_json = graph.get_email_history_with_contact(
        email_address=email_address,
        max_results=limit,
    )
    print(result_json)
    return 0


def main():
    env = _load_env()

    if len(sys.argv) >= 3 and sys.argv[1] == "read":
        return _cmd_read(env, sys.argv[2])

    if len(sys.argv) >= 3 and sys.argv[1] == "thread":
        limit = 10
        if "--limit" in sys.argv:
            try:
                limit = int(sys.argv[sys.argv.index("--limit") + 1])
            except Exception:
                pass
        return _cmd_thread(env, sys.argv[2], limit)

    if len(sys.argv) >= 2 and sys.argv[1] == "reply" and "--dry-run" in sys.argv:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("message_id")
        parser.add_argument("--body", required=True)
        parser.add_argument("--cc")
        parser.add_argument("--bcc")
        parser.add_argument("--dry-run", action="store_true")
        args, _ = parser.parse_known_args(sys.argv[1:])
        cc = args.cc.split(",") if args.cc else None
        bcc = args.bcc.split(",") if args.bcc else None
        return _cmd_dry_run_reply(env, args.message_id, args.body, cc, bcc)

    if len(sys.argv) >= 2 and sys.argv[1] == "send" and "--dry-run" in sys.argv:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("--to", required=True)
        parser.add_argument("--subject", required=True)
        parser.add_argument("--body", required=True)
        parser.add_argument("--cc")
        parser.add_argument("--bcc")
        parser.add_argument("--dry-run", action="store_true")
        args, _ = parser.parse_known_args(sys.argv[1:])
        cc = args.cc.split(",") if args.cc else None
        bcc = args.bcc.split(",") if args.bcc else None
        return _cmd_dry_run_send(args.to.split(","), args.subject, args.body, cc, bcc)

    cmd = [VENV_PYTHON, EMAIL_CLI] + sys.argv[1:]

    result = subprocess.run(
        cmd,
        env=env,
        cwd=EMAIL_AGENT_DIR,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
