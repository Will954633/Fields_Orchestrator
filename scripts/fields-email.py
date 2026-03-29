#!/usr/bin/env python3
"""Convenience wrapper around the email CLI with local compatibility fixes.

Usage from Claude Code / orchestrator context:
    python3 scripts/fields-email.py inbox
    python3 scripts/fields-email.py search "query"
    python3 scripts/fields-email.py read <id>
    python3 scripts/fields-email.py recipient-profile <id-or-email>
    python3 scripts/fields-email.py draft-reply <message_id> --instructions "text"
    python3 scripts/fields-email.py reply <id> --body "text"
    python3 scripts/fields-email.py send --to addr --subject "subj" --body "text"
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EMAIL_CLI = "/home/fields/samantha-email-agent/email_cli.py"
EMAIL_AGENT_DIR = "/home/fields/samantha-email-agent"
VENV_PYTHON = "/home/fields/venv/bin/python3"
ENV_FILE = "/home/fields/Fields_Orchestrator/.env"
EMAIL_MEMORY_PATH = Path("/home/fields/Fields_Orchestrator/config/email_memory.json")
EMAIL_MEMORY_DOC_PATH = Path("/home/fields/Fields_Orchestrator/config/email_memory.md")
EMAIL_REPLY_PROMPT_PATH = Path("/home/fields/samantha-email-agent/prompts/email_reply_prompt.md")
EMAIL_DRAFT_MODEL = "claude-sonnet-4-6"
EMAIL_VOICE_PROFILE_PATH = Path("/home/fields/Fields_Orchestrator/config/email_voice_profile.md")
UTC = timezone.utc


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_email_memory() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": _utc_now_iso(),
        "drafting_defaults": {
            "always_dry_run": True,
            "first_contact_style": "normal_polite_professional_brief",
            "default_signoff": "Thanks,\nWill",
            "tone_notes": [
                "Default to concise, natural business English.",
                "Sound human, not corporate or AI-generated.",
                "When there is no prior relationship history, be polite, professional, and brief.",
            ],
        },
        "relevance": {
            "message_ids": {},
            "senders": {},
            "domains": {},
        },
        "recipient_profiles": {},
    }


def _load_email_memory() -> dict[str, Any]:
    if not EMAIL_MEMORY_PATH.exists():
        memory = _default_email_memory()
        EMAIL_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        EMAIL_MEMORY_PATH.write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")
        return memory

    try:
        return json.loads(EMAIL_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        memory = _default_email_memory()
        EMAIL_MEMORY_PATH.write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")
        return memory


def _save_email_memory(memory: dict[str, Any]) -> None:
    memory["updated_at"] = _utc_now_iso()
    EMAIL_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_MEMORY_PATH.write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")


def _extract_domain(email_address: str) -> str:
    email_address = (email_address or "").strip().lower()
    if "@" not in email_address:
        return ""
    return email_address.split("@", 1)[1]


def _load_env():
    env = os.environ.copy()
    for env_file in [ENV_FILE, "/etc/environment"]:
        if os.path.exists(env_file):
            with open(env_file) as f:
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


def _get_anthropic_client(env):
    import anthropic

    return anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY", ""))


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


def _resolve_contact_email(env, identifier):
    identifier = (identifier or "").strip()
    if "@" in identifier:
        return identifier.lower()

    graph = _load_graph_tools(env)
    payload = graph.get_email_with_attachments_core(identifier)
    event = payload.get("event") or {}
    sender = event.get("sender") or {}
    return (sender.get("email") or "").strip().lower()


def _load_history_bundle(env, identifier, limit=10):
    graph = _load_graph_tools(env)
    email_address = _resolve_contact_email(env, identifier)
    if not email_address:
        return {
            "status": "error",
            "message": "Could not resolve a contact email address.",
            "email_address": "",
            "history": [],
            "style_analysis": {
                "status": "no_history",
                "fallback_style_profile": _load_email_memory()["drafting_defaults"]["first_contact_style"],
            },
        }

    raw = graph.get_email_history_with_contact(
        email_address=email_address,
        max_results=limit,
    )
    payload = json.loads(raw)
    history = payload.get("history") or []
    filtered_history = _filter_recent_history(history, window_days=365)
    style = _analyze_style_from_history(filtered_history)
    return {
        "status": payload.get("status", "error"),
        "mode": payload.get("mode"),
        "email_address": email_address,
        "history": filtered_history,
        "style_analysis": style,
    }


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _filter_recent_history(history, window_days):
    if not history or not window_days:
        return history or []
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    filtered = []
    for item in history:
        received_at = _parse_iso_datetime(item.get("received_at", ""))
        if received_at is None or received_at >= cutoff:
            filtered.append(item)
    return filtered


def _extract_greeting(body):
    for line in (body or "").splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith(("hi ", "hello ", "hey ", "dear ")):
            return stripped
    return None


def _extract_signoff(body):
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    for line in reversed(lines[-6:]):
        lowered = line.lower()
        if lowered.startswith(("thanks", "best", "regards", "kind regards", "cheers")):
            return line
    return None


def _analyze_style_from_history(history):
    memory = _load_email_memory()
    sent_messages = [
        item for item in history
        if item.get("direction") == "sent" and (item.get("body") or "").strip()
    ]
    samples = sent_messages or [
        item for item in history if (item.get("body") or "").strip()
    ]
    if not samples:
        return {
            "status": "no_history",
            "fallback_style_profile": memory["drafting_defaults"]["first_contact_style"],
            "recommended_length": "brief",
            "tone_profile": "normal_polite_professional_brief",
            "common_patterns": memory["drafting_defaults"]["tone_notes"],
        }

    word_counts = [len((item.get("body") or "").split()) for item in samples]
    avg_words = sum(word_counts) / max(1, len(word_counts))
    if avg_words < 60:
        length_category = "brief"
    elif avg_words < 180:
        length_category = "moderate"
    else:
        length_category = "detailed"

    greeting = _extract_greeting(samples[0].get("body") or "")
    signoff = _extract_signoff(samples[0].get("body") or "")
    uses_bullets = any(
        re.search(r"(^|\n)\s*([-*]|\d+\.)\s+", item.get("body") or "")
        for item in samples
    )

    tone_profile = "warm_professional"
    if greeting and greeting.lower().startswith("dear "):
        tone_profile = "formal_professional"
    elif greeting and greeting.lower().startswith("hey "):
        tone_profile = "casual_direct"

    patterns = []
    if greeting:
        patterns.append(f"Typical greeting: {greeting}")
    if signoff:
        patterns.append(f"Typical sign-off: {signoff}")
    if uses_bullets:
        patterns.append("Uses bullets when structure helps.")
    if length_category == "brief":
        patterns.append("Replies tend to be concise.")

    return {
        "status": "ok",
        "samples_considered": len(samples),
        "average_length_words": round(avg_words, 1),
        "length_category": length_category,
        "tone_profile": tone_profile,
        "typical_greeting": greeting,
        "typical_signoff": signoff,
        "uses_bullets_often": uses_bullets,
        "fallback_style_profile": memory["drafting_defaults"]["first_contact_style"],
        "common_patterns": patterns or memory["drafting_defaults"]["tone_notes"],
    }


def _message_to_original_email(read_result):
    email = (read_result or {}).get("email") or {}
    return {
        "message_id": email.get("id", ""),
        "subject": email.get("subject", ""),
        "body_text": email.get("body", ""),
        "sender": {
            "name": email.get("from_name", ""),
            "email": email.get("from", ""),
        },
        "to": [{"name": "", "email": addr} for addr in email.get("to", [])],
        "received_at": email.get("date", ""),
    }


def _recent_sent_examples(history, max_examples=3):
    examples = []
    for item in history:
        if item.get("direction") != "sent":
            continue
        body = (item.get("body") or "").strip()
        if not body:
            continue
        examples.append({
            "subject": item.get("subject", ""),
            "received_at": item.get("received_at", ""),
            "body": body[:1200],
        })
        if len(examples) >= max_examples:
            break
    return examples


def _build_reply_payload(env, message_id, instructions, style_profile):
    read_payload, rc = _format_read_result(_load_graph_tools(env).get_email_with_attachments_core(message_id))
    if rc != 0:
        return {"status": "error", "message": "Unable to load the original email."}, rc

    original_email = _message_to_original_email(read_payload)
    sender_email = original_email["sender"]["email"]
    history_bundle = _load_history_bundle(env, sender_email or message_id, limit=10)
    memory = _load_email_memory()
    recipient_profile = memory["recipient_profiles"].get(sender_email, {})
    sender_rule = memory["relevance"]["senders"].get(sender_email, {})
    domain_rule = memory["relevance"]["domains"].get(_extract_domain(sender_email), {})
    message_rule = memory["relevance"]["message_ids"].get(message_id, {})

    payload = {
        "original_email": original_email,
        "communication_history": history_bundle.get("history", []),
        "history_metadata": {
            "status": history_bundle.get("status"),
            "mode": history_bundle.get("mode"),
            "email_address": history_bundle.get("email_address"),
            "returned": len(history_bundle.get("history", [])),
        },
        "style_analysis": history_bundle.get("style_analysis", {}),
        "style_profile_override": style_profile or recipient_profile.get("style_profile_override"),
        "explicit_instructions_from_will": instructions,
        "recipient_profile_memory": recipient_profile,
        "relevance_memory": {
            "message": message_rule,
            "sender": sender_rule,
            "domain": domain_rule,
        },
        "first_contact_policy": memory["drafting_defaults"],
        "recent_sent_examples": _recent_sent_examples(history_bundle.get("history", [])),
    }
    return payload, 0


async def _generate_reply_draft(env, payload):
    client = _get_anthropic_client(env)
    system_prompt = EMAIL_REPLY_PROMPT_PATH.read_text(encoding="utf-8")

    # Inject Will's voice profile into the system prompt
    if EMAIL_VOICE_PROFILE_PATH.exists():
        voice_profile = EMAIL_VOICE_PROFILE_PATH.read_text(encoding="utf-8")
        system_prompt = f"{system_prompt}\n\n---\n## Will's Voice Profile\n\n{voice_profile}"

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=EMAIL_DRAFT_MODEL,
            max_tokens=1400,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": json.dumps(payload, indent=2)},
            ],
        )
        raw = (response.content[0].text or "").strip()
        # Strip markdown code fences if Claude wraps the JSON
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            cleaned = cleaned.strip()
        try:
            return {"status": "success", "draft": json.loads(cleaned), "raw_output": raw}
        except Exception:
            return {"status": "parse_error", "draft": None, "raw_output": raw}
    except Exception as e:
        return {"status": "error", "draft": None, "raw_output": "", "error": str(e)}


def _cmd_recipient_profile(env, identifier, limit):
    bundle = _load_history_bundle(env, identifier, limit=limit)
    memory = _load_email_memory()
    email_address = bundle.get("email_address", "")
    output = {
        "status": bundle.get("status", "error"),
        "email_address": email_address,
        "history_count": len(bundle.get("history", [])),
        "style_analysis": bundle.get("style_analysis", {}),
        "recipient_memory": memory["recipient_profiles"].get(email_address, {}),
        "relevance_memory": {
            "sender": memory["relevance"]["senders"].get(email_address, {}),
            "domain": memory["relevance"]["domains"].get(_extract_domain(email_address), {}),
        },
        "recent_sent_examples": _recent_sent_examples(bundle.get("history", [])),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["status"] == "success" else 1


def _cmd_draft_reply(env, message_id, instructions, style_profile):
    payload, rc = _build_reply_payload(env, message_id, instructions, style_profile)
    if rc != 0:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return rc

    result = asyncio.run(_generate_reply_draft(env, payload))
    output = {
        "status": result["status"],
        "action": "draft_reply",
        "message_id": message_id,
        "draft_only": True,
        "input": payload,
        "draft": result["draft"],
        "raw_output": None if result["draft"] else result.get("raw_output"),
        "error": result.get("error"),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "success" else 1


def _cmd_memory_show():
    print(json.dumps(_load_email_memory(), indent=2, ensure_ascii=False))
    return 0


def _cmd_memory_set_relevance(identifier, relevance, reason, kind):
    memory = _load_email_memory()
    entry = {
        "relevance": relevance,
        "reason": reason,
        "updated_at": _utc_now_iso(),
    }
    memory["relevance"][kind][identifier] = entry
    _save_email_memory(memory)
    print(json.dumps({
        "status": "success",
        "kind": kind,
        "identifier": identifier,
        "entry": entry,
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_memory_set_recipient(email_address, tone_notes, style_profile, preferred_length, greeting, signoff):
    memory = _load_email_memory()
    profile = memory["recipient_profiles"].setdefault(email_address, {})
    if tone_notes:
        profile["tone_notes"] = tone_notes
    if style_profile:
        profile["style_profile_override"] = style_profile
    if preferred_length:
        profile["preferred_length"] = preferred_length
    if greeting:
        profile["preferred_greeting"] = greeting
    if signoff:
        profile["preferred_signoff"] = signoff
    profile["updated_at"] = _utc_now_iso()
    _save_email_memory(memory)
    print(json.dumps({
        "status": "success",
        "email_address": email_address,
        "recipient_profile": profile,
    }, indent=2, ensure_ascii=False))
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

    if len(sys.argv) >= 3 and sys.argv[1] == "recipient-profile":
        limit = 10
        if "--limit" in sys.argv:
            try:
                limit = int(sys.argv[sys.argv.index("--limit") + 1])
            except Exception:
                pass
        return _cmd_recipient_profile(env, sys.argv[2], limit)

    if len(sys.argv) >= 3 and sys.argv[1] == "draft-reply":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("message_id")
        parser.add_argument("--instructions")
        parser.add_argument("--style-profile")
        args, _ = parser.parse_known_args(sys.argv[1:])
        return _cmd_draft_reply(env, args.message_id, args.instructions, args.style_profile)

    if len(sys.argv) >= 2 and sys.argv[1] == "memory-show":
        return _cmd_memory_show()

    if len(sys.argv) >= 2 and sys.argv[1] == "memory-set-relevance":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("--kind", choices=["message_ids", "senders", "domains"], required=True)
        parser.add_argument("--id", required=True)
        parser.add_argument("--relevance", choices=["relevant", "ignore"], required=True)
        parser.add_argument("--reason", required=True)
        args, _ = parser.parse_known_args(sys.argv[1:])
        return _cmd_memory_set_relevance(args.id.strip().lower(), args.relevance, args.reason, args.kind)

    if len(sys.argv) >= 2 and sys.argv[1] == "memory-set-recipient":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("--email", required=True)
        parser.add_argument("--tone-notes")
        parser.add_argument("--style-profile")
        parser.add_argument("--preferred-length")
        parser.add_argument("--greeting")
        parser.add_argument("--signoff")
        args, _ = parser.parse_known_args(sys.argv[1:])
        return _cmd_memory_set_recipient(
            args.email.strip().lower(),
            args.tone_notes,
            args.style_profile,
            args.preferred_length,
            args.greeting,
            args.signoff,
        )

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
