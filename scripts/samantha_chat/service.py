#!/usr/bin/env python3
"""
Samantha chat service — the customer-facing assistant behind the break-glass.

WHY THE BROWSER TALKS TO THIS DIRECTLY (not via a Netlify function)
------------------------------------------------------------------
Measured 2026-08-04: a turn through the Claude Max CLI takes 5.5s for one
sentence and 10.6s for three. `claude -p` does not usefully stream — even with
--output-format stream-json the assistant message arrives as ONE chunk when it
is finished, so there is no first-token trick available.

Netlify's synchronous function timeout is 10s. A three-sentence answer would
time out in production. So the browser calls this service directly over the
existing vm.fieldsestate.com.au TLS, and Netlify is not in the path.

WHY MAX, KNOWING THE RISK
-------------------------
Will's call (2026-08-04), and the reasoning is sound: the open question is
whether anyone engages at all. If they do not, the quota risk is hypothetical.
Max has a HARD five-hour window with overage REJECTED — so this service:
  * warns by Telegram as it approaches the cap, and
  * degrades to an explicit "at capacity" reply rather than failing silently.

A public endpoint that spends a subscription quota needs real abuse controls,
so there is a per-IP limit, a global daily cap, and an origin check.

Run:  systemd unit fields-samantha-chat.service  ->  127.0.0.1:3062
      nginx proxies /samantha/ to it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

sys.path.insert(0, str(Path(__file__).parent))
from facts import facts_block   # noqa: E402

HERE = Path(__file__).parent
SYSTEM_PROMPT = (HERE / "system_prompt.md").read_text()

PORT = int(os.environ.get("SAMANTHA_PORT", "3062"))
MODEL = os.environ.get("SAMANTHA_MODEL", "claude-opus-5")

# ── abuse + quota controls ────────────────────────────────────────────────
# A public endpoint spending a subscription quota. Without these, one bored
# visitor with a loop empties the five-hour window for everyone.
MAX_TURNS_PER_CONVO = 20
PER_IP_PER_HOUR = 25
GLOBAL_PER_DAY = 400          # generous for a test, far under the Max cap
MAX_CHARS = 1200              # a chat turn, not a pasted document
WARN_AT = int(GLOBAL_PER_DAY * 0.75)

ALLOWED_ORIGINS = {
    "https://fieldsestate.com.au",
    "https://www.fieldsestate.com.au",
    "https://vm.fieldsestate.com.au",
}

_ip_hits: dict[str, deque] = defaultdict(deque)
_day = {"date": None, "count": 0, "warned": False}
_lock = threading.Lock()


def _load_env() -> None:
    """Read .env directly rather than trusting the inherited environment.

    This service runs via `sudo -u projects`, and the switch drops the parent's
    exported vars — so the first run sent ZERO Telegram messages while looking
    perfectly healthy. Reading the file removes the dependency entirely.
    """
    envfile = Path("/home/fields/Fields_Orchestrator/.env")
    if not envfile.exists():
        return
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        # do not clobber anything explicitly set for this process
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_env()

_TELEGRAM_WARNED = False


def _telegram(text: str) -> None:
    """Best-effort delivery, but NEVER a silent no-op."""
    global _TELEGRAM_WARNED
    try:
        import urllib.parse
        import urllib.request

        tok = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = os.environ.get("TELEGRAM_CHAT_ID")
        if not (tok and chat):
            # Was a bare `return`. Every engagement notification vanished with
            # no symptom at all — the one failure mode Will explicitly asked to
            # avoid. Missing credentials must be loud.
            if not _TELEGRAM_WARNED:
                _TELEGRAM_WARNED = True
                print("[telegram] NO CREDENTIALS — engagement alerts are NOT being sent",
                      file=sys.stderr, flush=True)
            return
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML",
             "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=8) as r:
            ok = json.loads(r.read()).get("ok")
        # Log both outcomes. Delivery was previously inferred from the absence
        # of an error, which is exactly how six engagements went unnoticed.
        print(f"[telegram] {'sent' if ok else 'API returned ok=false'}",
              file=sys.stderr, flush=True)
    except Exception as exc:                       # noqa: BLE001
        print(f"[telegram] failed: {exc}", file=sys.stderr, flush=True)


def _start_heartbeat() -> None:
    """CLAUDE.md rule 7 — an ongoing process must report its own health.

    A daemon has no natural 'run' to wrap, so it beats on a timer instead. The
    Process Registry flags STALE at cadence x 1.5, so a half-hour beat means a
    dead or crash-looping service shows up on the health sheet within ~45
    minutes rather than whenever someone next breaks the glass and gets nothing.
    """
    def beat() -> None:
        while True:
            try:
                from job_status import record_job_result
                with _lock:
                    served = _day["count"]
                record_job_result(
                    "samantha_chat", "success",
                    detail=f"listening on :{PORT}, {served} turns today",
                    cadence_hours=0.5, title="Samantha Chat (break-glass)",
                    metrics={"turns_today": served, "daily_cap": GLOBAL_PER_DAY,
                             "model": MODEL})
            except Exception as exc:                   # noqa: BLE001
                print(f"[heartbeat] {exc}", file=sys.stderr, flush=True)
            time.sleep(1800)

    threading.Thread(target=beat, daemon=True, name="heartbeat").start()


def _quota_check() -> tuple[bool, str]:
    """(allowed, reason). Also fires the near-capacity warning once per day."""
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, count=0, warned=False)
        if _day["count"] >= GLOBAL_PER_DAY:
            return False, "daily"
        _day["count"] += 1
        n = _day["count"]
        warn = (not _day["warned"]) and n >= WARN_AT
        if warn:
            _day["warned"] = True
    if warn:
        _telegram(
            f"⚠️ <b>Samantha near capacity</b>\n{n}/{GLOBAL_PER_DAY} turns today.\n"
            f"Max has a hard 5-hour window with overage rejected — at the cap she "
            f"replies 'at capacity' rather than failing silently.")
    return True, ""


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _lock:
        q = _ip_hits[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= PER_IP_PER_HOUR:
            return False
        q.append(now)
        return True


def _unsourced_figures(reply: str, quotable: list[str]) -> list[str]:
    """Figures in the reply that did not come from the FACTS block.

    The backstop behind facts.py. Prompting alone produced invented numbers
    roughly half the time, so a reply that states a figure we did not supply is
    treated as a defect rather than trusted.

    Only meaningful quantities are checked. Bare small integers ("two or three
    bedrooms", "one of the three suburbs") and years are ordinary language, not
    claims about the market.
    """
    # Pull EVERY number out of each supplied value. Some facts are composite —
    # the confidence interval arrives as "$1,450,000 to $1,550,000" — and
    # stripping non-digits from the whole string produced one nonsense blob,
    # so quoting the range correctly was flagged as fabrication.
    allowed = set()
    for q in quotable:
        for num in re.findall(r"\d[\d,]*(?:\.\d+)?", str(q)):
            digits = num.replace(",", "").rstrip(".")
            allowed.add(digits)
            allowed.add(digits.replace(".0", ""))

    # Three alternatives, deliberately not one. A single pattern ending in \b
    # silently dropped every percentage: "12%" is followed by a space, and % to
    # space is not a word boundary, so the branch never matched and the guard
    # passed invented growth figures straight through.
    figure = (
        r"\$[\d,]+(?:\.\d+)?"                                    # money
        r"|\b\d[\d,]*(?:\.\d+)?\s*%"                             # percentage
        r"|\b\d[\d,]*(?:\.\d+)?\s+(?:\w+\s+)?"                   # count, allowing
        r"(?:per cent|days?|weeks?|months?|years?|sold|sales?|"  # one adjective:
        r"listings?|properties|transactions?|homes?|houses?)\b"  # "274 sold listings"
    )
    bad = []
    for m in re.finditer(figure, reply, re.I):
        tok = m.group(0)
        digits = re.sub(r"[^\d.]", "", tok).rstrip(".")
        if not digits:
            continue
        if digits in allowed or digits.replace(".0", "") in allowed:
            continue
        # a plain year, or a small count used conversationally
        if re.fullmatch(r"(19|20)\d\d", digits):
            continue
        if "." not in digits and len(digits) <= 2 and int(digits) <= 12 \
           and not re.search(r"%|per cent", tok, re.I):
            continue
        bad.append(tok.strip())
    return bad


# Suppliers behind the Fields database. The visitor-facing attribution is
# always "the Fields internal database" and never one of these, in any context
# — including when the visitor names one first and asks for confirmation.
_VENDORS = re.compile(
    r"\b(domain(?:\.com(?:\.au)?)?|onthehouse(?:\.com(?:\.au)?)?|on the house|"
    r"prop\s?radar|realestate\.com(?:\.au)?|rea\s?group|corelogic|core\s?logic|"
    r"pricefinder|price\s?finder|proptrack|prop\s?track|"
    r"valuer[- ]general|titles\s+queensland|qld\s+titles|abs|"
    r"australian\s+bureau\s+of\s+statistics)\b",
    re.I)

_DB = "the Fields internal database"


def _redact_sources(reply: str) -> tuple[str, list[str]]:
    """Strip supplier names from a reply. Deterministic, not advisory.

    Prompting is the wrong instrument for an absolute rule — the model complies
    most of the time, and "most of the time" is not what was asked for. This
    substitutes, so a leak cannot reach the visitor even if the model ignores
    every instruction it was given.
    """
    found = [m.group(0) for m in _VENDORS.finditer(reply)]
    if not found:
        return reply, []

    out = _VENDORS.sub(_DB, reply)
    # Substitution can leave "from X and Y combined" reading as the same phrase
    # twice, or a stray article before it. Tidy the predictable seams.
    db = re.escape(_DB)
    # Article collapse FIRST. _DB carries its own "the", so a preceding article
    # doubles up — and while it is there, the dedupe below cannot see two
    # adjacent phrases as adjacent, which left "the Fields internal database
    # and the Fields internal database" in the output.
    # Collapse the article ONLY: an earlier version matched "from" here too and
    # ate the preposition, leaving "drawn the Fields internal database".
    out = re.sub(r"\b(the|our|their|its)\s+the\s+Fields\s+internal\s+database",
                 lambda m: ("our" if m.group(1).lower() == "our" else "the")
                           + " Fields internal database", out, flags=re.I)
    # then "X and Y", both now the same phrase -> say it once
    out = re.sub(rf"(?:{db})(?:\s*(?:,|and|/|\+|\s)\s*(?:{db}))+", _DB, out, flags=re.I)
    # "...database sales combined" / "...database data" read as leftovers
    out = re.sub(rf"{db}\s+(?:sales\s+)?combined\b", _DB, out, flags=re.I)
    out = re.sub(rf"{db}\s+(listing\s+)?data\b", _DB, out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out, found


def _ask_max(messages: list[dict], context: dict) -> tuple[str, dict]:
    """One turn through the Max CLI. Returns (reply, meta)."""
    ctx_line = ""
    if context.get("readout") and context.get("key") != "home":
        # Deliberately careful wording. The earlier version said the readout was
        # "already loaded", and the model reasonably concluded it therefore HAD
        # that suburb's data — then produced it. Saying what is actually on
        # screen, and nothing more, removes the invitation.
        ctx_line = (f"\n\nPAGE CONTEXT: the visitor is on a {context.get('key')} page "
                    f"headed '{context['readout']}'. That heading is all you know from "
                    f"the page — it is a label, not data. Do not ask them to repeat it.")
    elif context.get("key") == "home":
        ctx_line = "\n\nPAGE CONTEXT: no property is loaded. If they want an analysis, ask which address."

    facts, quotable = facts_block(context)

    convo = "\n\n".join(
        f"{'VISITOR' if m['role'] == 'user' else 'SAMANTHA'}: {m['content']}"
        for m in messages[-MAX_TURNS_PER_CONVO:])
    prompt = (f"{SYSTEM_PROMPT}{ctx_line}{facts}\n\n---\n\n{convo}\n\n"
              f"Reply as Samantha. Give the reply text only — no name prefix, no label.")

    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
    t0 = time.time()
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", MODEL,
         "--output-format", "json"],
        capture_output=True, text=True, timeout=90, env=env)
    elapsed = time.time() - t0

    if proc.returncode != 0:
        err = (proc.stderr or "")[:400]
        low = err.lower()
        # The five-hour cap. Explicit, never silent — that is the whole point of
        # accepting Max in production.
        if any(m in low for m in ("usage limit", "rate limit", "quota",
                                  "limit reached", "resets at", "too many requests")):
            raise QuotaExhausted(err)
        raise RuntimeError(err or "claude cli failed")

    try:
        payload = json.loads(proc.stdout)
        reply = (payload.get("result") or "").strip()
        meta = {"elapsed": round(elapsed, 2),
                "api_ms": payload.get("duration_api_ms"),
                "model": MODEL}
    except json.JSONDecodeError:
        reply, meta = proc.stdout.strip(), {"elapsed": round(elapsed, 2)}

    if not reply:
        raise RuntimeError("empty reply")

    # The prompt is a transcript, so the model sometimes echoes the speaker
    # label back ("**SAMANTHA:**") as the first line of its own reply.
    reply = re.sub(r"^\s*\**\s*SAMANTHA\s*:\s*\**\s*", "", reply, flags=re.I).strip()

    reply, leaked = _redact_sources(reply)
    if leaked:
        print(f"[source-leak] redacted {leaked} from reply", file=sys.stderr, flush=True)
        _telegram("⚠️ <b>Samantha named a data supplier</b> (redacted before sending)\n"
                  f"Mentioned: {', '.join(sorted(set(leaked))[:6])}")
        meta["redacted_sources"] = sorted(set(leaked))

    unsourced = _unsourced_figures(reply, quotable)
    if unsourced:
        # Loud, and recorded — this is the failure mode that matters most on a
        # site whose whole proposition is that the numbers are real.
        print(f"[fabrication] unsourced figures {unsourced} in reply: {reply[:200]!r}",
              file=sys.stderr, flush=True)
        _telegram("⚠️ <b>Samantha stated an unsourced figure</b>\n"
                  f"Not in the supplied facts: {', '.join(unsourced[:6])}\n"
                  f"<i>{reply[:300]}</i>")
        meta["unsourced"] = unsourced
    return reply, meta


class QuotaExhausted(RuntimeError):
    pass


AT_CAPACITY = ("I am at capacity right now and cannot take another question. "
               "Please try again shortly — or call Will on 0416 529 481.")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):            # quieter journal
        print(f"[{self.address_string()}] {fmt % args}", file=sys.stderr)

    def _cors(self, origin: str | None):
        allow = origin if origin in ALLOWED_ORIGINS else "https://fieldsestate.com.au"
        self.send_header("Access-Control-Allow-Origin", allow)
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Vary", "Origin")

    def _json(self, code: int, obj: dict, origin: str | None = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors(origin)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):                          # noqa: N802
        self.send_response(204)
        self._cors(self.headers.get("Origin"))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):                              # noqa: N802
        if self.path.rstrip("/").endswith("/health"):
            with _lock:
                used = _day["count"]
            self._json(200, {"ok": True, "model": MODEL,
                             "today": used, "cap": GLOBAL_PER_DAY})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):                             # noqa: N802
        origin = self.headers.get("Origin")
        ip = (self.headers.get("X-Forwarded-For", "") or self.client_address[0]).split(",")[0].strip()

        if not self.path.rstrip("/").endswith("/chat"):
            return self._json(404, {"error": "not found"}, origin)
        if origin and origin not in ALLOWED_ORIGINS:
            return self._json(403, {"error": "origin not allowed"}, origin)
        if not _rate_ok(ip):
            return self._json(429, {"reply": "That is a lot of questions in a short time. "
                                             "Give it a minute and try again."}, origin)

        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or "{}")
        except Exception:                          # noqa: BLE001
            return self._json(400, {"error": "bad json"}, origin)

        messages = body.get("messages") or []
        context = body.get("context") or {}
        if not messages or messages[-1].get("role") != "user":
            return self._json(400, {"error": "no user message"}, origin)
        last = (messages[-1].get("content") or "").strip()
        if not last:
            return self._json(400, {"error": "empty message"}, origin)
        if len(last) > MAX_CHARS:
            return self._json(200, {"reply": "That is longer than I can take in one go. "
                                             "Could you put the key question in a sentence or two?"}, origin)

        ok, why = _quota_check()
        if not ok:
            _telegram(f"🛑 <b>Samantha hit the daily cap</b> ({GLOBAL_PER_DAY}). "
                      f"Replying 'at capacity'.")
            return self._json(200, {"reply": AT_CAPACITY, "capped": True}, origin)

        try:
            reply, meta = _ask_max(messages, context)
        except QuotaExhausted as exc:
            _telegram(f"🛑 <b>Samantha: Max quota exhausted</b>\n<code>{str(exc)[:300]}</code>")
            return self._json(200, {"reply": AT_CAPACITY, "capped": True}, origin)
        except Exception as exc:                   # noqa: BLE001
            print(f"[error] {exc}", file=sys.stderr)
            _telegram(f"❌ <b>Samantha error</b>\n<code>{str(exc)[:300]}</code>")
            return self._json(200, {"reply": "Something went wrong on my end. "
                                             "Try again, or call Will on 0416 529 481."}, origin)

        # Will wants to see EVERY engagement — the whole point of shipping this
        # is finding out whether anyone talks to her at all.
        turn = len([m for m in messages if m.get("role") == "user"])
        with _lock:
            used = _day["count"]
        _telegram(
            f"💬 <b>Samantha</b> · turn {turn} · {meta.get('elapsed')}s · {used}/{GLOBAL_PER_DAY} today\n"
            f"<b>Page:</b> {context.get('key','?')} {context.get('readout','') or ''}\n"
            f"<b>Them:</b> {last[:300]}\n"
            f"<b>Her:</b> {reply[:400]}")

        self._json(200, {"reply": reply, "meta": meta}, origin)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    _start_heartbeat()
    print(f"samantha chat on 127.0.0.1:{PORT} model={MODEL}", file=sys.stderr)
    srv.serve_forever()


if __name__ == "__main__":
    main()
