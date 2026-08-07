#!/usr/bin/env python3
"""
vm_agent.py — give GPT-5.6-terra its own eyes on this VM.

Why this exists
---------------
GPT's critique of the first harness design was that a veto without access to the
underlying evidence is "power to delay, not power to govern" — it would be auditing a
narrated version of reality chosen by the agent who produced it. The countermeasures we
designed for that (evidence packets, omission logs, provenance labels) were all
compensation for GPT being blind. Giving it a read surface removes the need for most of
them: it inspects directly, so `DIRECTLY INSPECTED` becomes the default.

That was not theoretical. The first run of this module found that the owner article
posted to homeowners was computing its own Domain-only suburb median and calling it
"independently measured", understating Burleigh Waters by $125,000. See fix-history
[OWNER-ARTICLE-MEDIAN-BYPASS].

The privilege boundary
----------------------
Access is deliberately ASYMMETRIC even though inspection is symmetric:

  * READ is broad. Shell (allowlisted, no shell metacharacters by construction),
    MongoDB finds and aggregations, and public HTTP GET.
  * WRITE is absent. No mutation, no network POST, no git/gh, no deploys. When GPT
    wants something changed it returns a proposal and Claude executes it under the
    normal permission layer, with a human able to see it.

The reason is not distrust of the model, it is that this VM holds the Cosmos URI, a
GitHub PAT with write access, Facebook tokens and Google OAuth, and GPT's context
leaves the building to a third-party API. So credential file CONTENTS are blocked
(their paths and existence are not), and every tool result is scrubbed for
secret-shaped strings on the way back.

Resource guards exist because this box has been wedged before by a runaway recursive
grep: every command has a hard timeout, output is capped, and Mongo queries are
forced to carry a limit.

Usage
-----
    from vm_agent import VmAgent
    agent = VmAgent(run_dir, system="You are auditing X.")
    result = agent.investigate("Find the biggest correctness risk in Y", max_calls=40)
    print(result.answer, result.calls, result.cost_usd)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpt_peer import resolve_route  # noqa: E402

AEST = timezone(timedelta(hours=10))
REPO = Path("/home/fields/Fields_Orchestrator")

# Read-only commands. Note `python3` is deliberately ABSENT — it is arbitrary code
# execution, which would make every other restriction here decorative.
ALLOW = ("ls", "cat", "head", "tail", "wc", "find", "grep", "rg", "stat", "file",
         "du", "sed", "awk", "sort", "uniq", "cut", "tr", "basename", "dirname",
         "realpath", "diff", "date", "jq", "column")

SECRET_PAT = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,}"
    r"|sk-or-v1-[A-Za-z0-9]{12,}"
    r"|github_pat_[A-Za-z0-9_]{12,}"
    r"|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|mongodb(\+srv)?://[^\s\"'`]+"
    r"|EAA[A-Za-z0-9]{20,}"
    r"|AIza[A-Za-z0-9_\-]{20,}"
    r"|-----BEGIN[A-Z ]+PRIVATE KEY-----)"
)
# Files whose contents are secret even though their existence is not.
SECRET_FILES = re.compile(
    r"(\.env|credentials|\.pem$|id_rsa|\.key$|token|secret|\.npmrc|\.git-credentials"
    r"|settings\.ya?ml|\.gdrive|service[-_]account)", re.I)
READERS = ("cat", "head", "tail", "sed", "awk", "grep", "rg", "diff", "cut", "tr", "jq")

# Rough gpt-5.6-terra rates for cost reporting. Adjust if pricing moves — the point is
# to make a run's cost visible, not to be an invoice.
USD_PER_M_IN, USD_PER_M_OUT = 1.25, 10.0


def scrub(text: str) -> str:
    return SECRET_PAT.sub("<REDACTED-SECRET>", text)


@dataclass
class Result:
    answer: str
    calls: int = 0
    denied: list = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    transcript: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return self.tokens_in / 1e6 * USD_PER_M_IN + self.tokens_out / 1e6 * USD_PER_M_OUT


class VmAgent:
    """GPT-5.6-terra with a read-only view of this VM."""

    def __init__(self, run_dir: Path | str, system: str = "", cwd: Path = REPO,
                 allow_mongo: bool = True, allow_http: bool = False):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cwd = Path(cwd)
        self.allow_mongo = allow_mongo
        self.allow_http = allow_http
        self.system = system or (
            "You are gpt-5.6-terra investigating a live production system directly. "
            "Cite file:line for every claim. Separate what you VERIFIED from what you "
            "INFERRED. Say plainly what you could not establish rather than filling the "
            "gap with a plausible guess."
        )
        from openai import OpenAI
        self.route, key, self.model = resolve_route()
        self._client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1" if self.route == "openrouter" else None,
        )
        self._mongo = None

    # ---------------- tools ----------------

    def _tool_specs(self) -> list[dict]:
        specs = [{
            "type": "function",
            "name": "run_bash",
            "description": (
                f"Read-only shell, cwd={self.cwd}. Allowed: {', '.join(ALLOW)}. "
                "Executed WITHOUT a shell, so pipes, redirects and $() do not work — but a "
                "'|' inside a quoted grep -E pattern is fine. Chain by making several calls. "
                "Credential file contents are blocked; paths are visible. 30s timeout."
            ),
            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}},
                           "required": ["cmd"], "additionalProperties": False},
        }]
        if self.allow_mongo:
            specs.append({
                "type": "function",
                "name": "mongo_query",
                "description": (
                    "Read-only MongoDB against Azure Cosmos. op='find' (filter/projection/"
                    "sort/limit) or op='aggregate' (pipeline) or op='count' or "
                    "op='distinct' (field) or op='collections'. Databases: Gold_Coast "
                    "(property data; ALWAYS filter listing_status — 'for_sale' or 'sold' — "
                    "or you hit ~40k cadastral records), property_data, system_monitor. "
                    "limit is capped at 200. Cosmos is serverless with ~5000 RU/s, so keep "
                    "queries narrow. Read SCHEMA_SNAPSHOT.md first if unsure of fields."
                ),
                "parameters": {"type": "object", "properties": {
                    "db": {"type": "string"}, "collection": {"type": "string"},
                    "op": {"type": "string", "enum": ["find", "aggregate", "count", "distinct", "collections"]},
                    "filter": {"type": "object"}, "projection": {"type": "object"},
                    "pipeline": {"type": "array", "items": {"type": "object"}},
                    "sort": {"type": "array", "items": {"type": "array"}},
                    "field": {"type": "string"},
                    "limit": {"type": "integer"},
                }, "required": ["db", "op"], "additionalProperties": False},
            })
        if self.allow_http:
            specs.append({
                "type": "function",
                "name": "http_get",
                "description": ("HTTP GET a PUBLIC url (e.g. https://fieldsestate.com.au/...). "
                                "Returns status + first 6000 chars. No POST, no auth headers, "
                                "no localhost or private ranges."),
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                               "required": ["url"], "additionalProperties": False},
            })
        return specs

    def _run_bash(self, cmd: str) -> str:
        try:
            argv = shlex.split(cmd)
        except ValueError as e:
            return f"DENIED: unparseable command ({e})."
        if not argv:
            return "DENIED: empty command."
        if argv[0] not in ALLOW:
            return (f"DENIED: '{argv[0]}' is not in the read-only allowlist. "
                    f"Allowed: {', '.join(ALLOW)}. If you need something changed or executed, "
                    "return it as a PROPOSAL in your final answer instead.")
        if argv[0] in READERS and any(SECRET_FILES.search(a) for a in argv[1:]):
            return ("DENIED: that path holds credentials. Its existence and name are visible to "
                    "you; its contents are not. Describe what you needed from it instead.")
        # Recursive greps repeatedly burned tool calls on timeouts against node_modules,
        # .git and __pycache__. Inject the exclusions rather than making the model
        # remember them — it has a finite call budget and this wasted several per run.
        if argv[0] in ("grep", "rg") and any(f in argv for f in ("-r", "-R", "-rn", "-rln", "-rl")):
            for ex in ("node_modules", ".git", "__pycache__", ".venv", "dist", "build"):
                if not any(ex in a for a in argv):
                    argv.append(f"--exclude-dir={ex}")
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=60, cwd=self.cwd)
            out = (p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return ("TIMEOUT after 60s — narrow the path or pattern. A recursive grep from the repo "
                    "root is too broad; target a subdirectory such as scripts/ or src/.")
        except FileNotFoundError:
            return f"DENIED: '{argv[0]}' is not installed on this VM."
        if len(out) > 8000:
            out = out[:8000] + f"\n… [truncated, {len(out)} chars total — narrow the query]"
        return scrub(out) or "(empty)"

    def _run_mongo(self, a: dict) -> str:
        if self._mongo is None:
            sys.path.insert(0, str(REPO))
            from src.mongo_client_factory import get_mongo_client
            self._mongo = get_mongo_client()
        db = self._mongo[a["db"]]
        op = a["op"]
        try:
            if op == "collections":
                return json.dumps(sorted(db.list_collection_names())[:300], default=str)
            coll = db[a["collection"]]
            limit = min(int(a.get("limit") or 20), 200)
            if op == "count":
                return json.dumps({"count": coll.count_documents(a.get("filter") or {}, maxTimeMS=30000)})
            if op == "distinct":
                return json.dumps(coll.distinct(a["field"], a.get("filter") or {})[:200], default=str)
            if op == "aggregate":
                pipe = list(a.get("pipeline") or [])
                if not any("$limit" in s for s in pipe):
                    pipe.append({"$limit": limit})
                if any(k in json.dumps(pipe) for k in ("$out", "$merge")):
                    return "DENIED: $out/$merge are writes."
                docs = list(coll.aggregate(pipe, maxTimeMS=45000))
            else:
                # pymongo's find() takes snake_case max_time_ms; only count_documents and
                # aggregate take camelCase maxTimeMS. Passing maxTimeMS here raised
                # "Cursor.__init__() got an unexpected keyword argument" on every find and
                # silently cost three of the first four audits their database access.
                docs = list(coll.find(a.get("filter") or {}, a.get("projection") or None,
                                      sort=[tuple(s) for s in a["sort"]] if a.get("sort") else None,
                                      limit=limit, max_time_ms=45000))
            out = json.dumps(docs, default=str, indent=1)
            if len(out) > 8000:
                out = out[:8000] + f"\n… [truncated of {len(docs)} docs — use a projection]"
            return scrub(out)
        except Exception as e:
            return f"MONGO ERROR: {type(e).__name__}: {str(e)[:400]}"

    def _run_http(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "DENIED: must be http(s)."
        if re.search(r"(localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254|10\.|192\.168\.|::1)", url):
            return "DENIED: private/loopback address."
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FieldsBot/1.0 (audit)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(200_000).decode("utf-8", "replace")
                return scrub(f"HTTP {r.status}\n{body[:6000]}")
        except Exception as e:
            return f"HTTP ERROR: {type(e).__name__}: {str(e)[:300]}"

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "run_bash":
            return self._run_bash(args.get("cmd", ""))
        if name == "mongo_query":
            return self._run_mongo(args)
        if name == "http_get":
            return self._run_http(args.get("url", ""))
        return f"DENIED: unknown tool {name}"

    # ---------------- loop ----------------

    def _create(self, **kw):
        """
        Responses.create with backoff on 429.

        The org TPM ceiling is 500,000 tokens/min. A tool-using run resends its whole
        history each turn, so by call ~45 a single agent is pushing 60-70k tokens per
        request — four concurrent agents blew the ceiling and the SDK's default 2 retries
        were not enough. Hence explicit, patient backoff, and prefer serial runs.
        """
        import time
        from openai import RateLimitError, APIStatusError
        delay = 8.0
        for attempt in range(8):
            try:
                return self._client.responses.create(**kw)
            except RateLimitError as e:
                if "insufficient_quota" in str(e) or "credit" in str(e).lower():
                    raise  # out of money is not a wait-and-retry condition
                if attempt == 7:
                    raise
                print(f"    [rate-limited, sleeping {delay:.0f}s]", flush=True)
                time.sleep(delay)
                delay = min(delay * 1.6, 90)
            except APIStatusError as e:
                if e.status_code not in (500, 502, 503, 504, 529) or attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 1.6, 90)
        raise RuntimeError("unreachable")

    def finalize_from_transcript(self, task: str, jsonl: Path | str,
                                 label: str = "finalized") -> Result:
        """
        Recover a crashed run: replay its recorded tool calls as context and ask only for
        the final answer, no tools. Cheaper than re-running and keeps the work already paid
        for. Used after the TPM crash killed four runs at ~45 calls each.
        """
        rows = [json.loads(l) for l in Path(jsonl).read_text().splitlines() if l.strip()]
        steps = [r for r in rows if "call" in r]
        replay = "\n\n".join(
            f"### tool call {r['call']}: {r['tool']}({json.dumps(r['args'])[:300]})\n"
            f"```\n{r['out'][:2500]}\n```" for r in steps)
        prompt = (
            f"{task}\n\n---\n\nYou already carried out this investigation. Below is the complete "
            f"record of your {len(steps)} tool calls and their output. You have NO further tool "
            f"access, so work only from this evidence.\n\nWrite your final answer now, in the exact "
            f"format the brief specifies. Any claim you cannot support from the record below must be "
            f"dropped or marked INFERRED.\n\n{replay}")
        r = self._create(model=self.model,
                         input=[{"role": "system", "content": self.system},
                                {"role": "user", "content": prompt}],
                         max_output_tokens=16000, store=False)
        res = Result(answer=r.output_text, calls=len(steps),
                     tokens_in=r.usage.input_tokens, tokens_out=r.usage.output_tokens)
        (self.run_dir / f"{label}.md").write_text(
            f"# {label}\n\nModel `{self.model}` via {self.route} · recovered from "
            f"{len(steps)} recorded tool calls · {res.tokens_in:,} in / {res.tokens_out:,} out · "
            f"~${res.cost_usd:.2f}\n\n{res.answer}\n")
        return res

    def investigate(self, task: str, max_calls: int = 40, max_output_tokens: int = 12000,
                    label: str = "investigate", verbose: bool = True) -> Result:
        tools = self._tool_specs()
        items = [{"role": "system", "content": self.system},
                 {"role": "user", "content": task}]
        res = Result(answer="")
        log = (self.run_dir / f"{label}.jsonl").open("a")

        # Turn cap is generous but finite: each turn resends history, so cost grows
        # quadratically in tool calls. That is the real budget constraint, not thinking.
        for _ in range(max_calls + 12):
            r = self._create(model=self.model, input=items, tools=tools,
                             max_output_tokens=max_output_tokens, store=False)
            res.tokens_in += r.usage.input_tokens
            res.tokens_out += r.usage.output_tokens
            items = items + [o.model_dump(exclude_none=True) for o in r.output]
            fcs = [o for o in r.output if o.type == "function_call"]

            if not fcs:
                res.answer = r.output_text
                break
            if res.calls >= max_calls:
                # EVERY function_call must get a function_call_output or the next request
                # 400s with "No tool output found for function call". The first version of
                # this branch appended only the nudge and killed four runs at ~45 calls,
                # after all the expensive work was done.
                for fc in fcs:
                    items.append({"type": "function_call_output", "call_id": fc.call_id,
                                  "output": f"DENIED: tool budget of {max_calls} calls exhausted."})
                items.append({"role": "user", "content":
                              f"Tool budget of {max_calls} calls is exhausted. Give your final "
                              "answer now from what you have, and state explicitly what you "
                              "could not establish."})
                continue
            for fc in fcs:
                res.calls += 1
                try:
                    args = json.loads(fc.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = self._dispatch(fc.name, args)
                if out.startswith("DENIED"):
                    res.denied.append(f"{fc.name}: {args}")
                if verbose:
                    brief = (args.get("cmd") or args.get("url")
                             or json.dumps({k: v for k, v in args.items() if k != "projection"})[:150])
                    mark = "DENIED " if out.startswith("DENIED") else ""
                    print(f"  [{res.calls}] {mark}{fc.name}: {str(brief)[:150]}", flush=True)
                log.write(json.dumps({"ts": datetime.now(AEST).isoformat(), "call": res.calls,
                                      "tool": fc.name, "args": args, "out": out[:4000]}) + "\n")
                res.transcript.append({"tool": fc.name, "args": args, "out": out[:4000]})
                items.append({"type": "function_call_output", "call_id": fc.call_id, "output": out})
        else:
            res.answer = res.answer or "(no final answer — turn cap reached)"

        log.write(json.dumps({"ts": datetime.now(AEST).isoformat(), "final": res.answer,
                              "calls": res.calls, "tokens_in": res.tokens_in,
                              "tokens_out": res.tokens_out,
                              "cost_usd": round(res.cost_usd, 4)}) + "\n")
        log.close()
        (self.run_dir / f"{label}.md").write_text(
            f"# {label}\n\nModel `{self.model}` via {self.route} · "
            f"{res.calls} tool calls ({len(res.denied)} denied) · "
            f"{res.tokens_in:,} in / {res.tokens_out:,} out · ~${res.cost_usd:.2f}\n\n"
            f"## Task\n\n{task}\n\n## Answer\n\n{res.answer}\n")
        return res


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Point GPT at this VM with a read-only surface")
    ap.add_argument("task", nargs="?")
    ap.add_argument("--file", help="read task from file")
    ap.add_argument("--run", default=str(Path(__file__).resolve().parent.parent / "runs" / "adhoc"))
    ap.add_argument("--label", default="investigate")
    ap.add_argument("--max-calls", type=int, default=40)
    ap.add_argument("--http", action="store_true", help="allow public HTTP GET")
    ap.add_argument("--no-mongo", action="store_true")
    a = ap.parse_args()
    task = Path(a.file).read_text() if a.file else a.task
    if not task:
        ap.error("give a task or --file")
    agent = VmAgent(a.run, allow_mongo=not a.no_mongo, allow_http=a.http)
    res = agent.investigate(task, max_calls=a.max_calls, label=a.label)
    print("\n" + "=" * 70 + f"\n{res.answer}\n" + "=" * 70)
    print(f"{res.calls} calls · {res.tokens_in:,} in / {res.tokens_out:,} out · ~${res.cost_usd:.2f}")


if __name__ == "__main__":
    main()
