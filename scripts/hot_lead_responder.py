#!/usr/bin/env python3
"""
hot_lead_responder.py — AI drafts a personal reply when a lead CLICKS a property.

A click on a /property/ link is the strongest engagement signal we have. This
scans email_events for new property-clicks by real leads, pulls that property's
Fields analysis + the lead's brief, has Opus (on Max via `claude -p`) draft a
warm, data-backed reply from Will, and Telegrams the draft to Will for review.

You-in-the-loop by design: it DRAFTS and sends to Will — it never emails the
lead. Dedupes per (lead_email, property_slug) via system_monitor.hot_lead_drafts.

Usage:
  python3 scripts/hot_lead_responder.py            # process new clicks
  python3 scripts/hot_lead_responder.py --dry-run  # generate + print, no telegram/record
Schedule (suggested): every 10 min via cron.
"""
import os, sys, re, json, argparse, subprocess, requests
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client

MODEL = "claude-opus-4-8"
SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]

RULES = """You draft a short, warm 1:1 email from Will (Fields Real Estate, Gold Coast) to a buyer
who just clicked a specific property in our weekly shortlist. Rules (strict):
- NO advice ("you should offer/buy") — data + a light view only; the reader concludes.
- Valuation as a RANGE, never a single figure. Cite it as our comparable-sales estimate.
- Exact comp prices; suburbs capitalised. No words: stunning, nestled, boasting, rare opportunity, robust market.
- Ask 2-3 short questions to sharpen their brief (budget, must-haves/deal-breakers).
- If they own a Gold Coast home, add ONE soft line offering to show where their current home sits (sell-to-buy) — not a hard pitch.
- Warm, concise, human. Sign "Will · Fields Real Estate". Plain language.
Return ONLY JSON: {"subject": "...", "body": "plain text with line breaks"}."""


def claude(prompt, timeout=200):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(["claude", "-p", "--model", MODEL, "--effort", "high",
                        "--settings", '{"alwaysThinkingEnabled":false}'],
                       input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:200]}")
    return r.stdout.strip()


def find_property(slug):
    gc = get_client()["Gold_Coast"]
    for s in SUBURBS:
        d = gc[s].find_one({"url_slug": slug})
        if d:
            return d, s
    return None, None


def property_brief(d):
    vd = d.get("valuation_data", {}) or {}
    conf = vd.get("confidence", {}) or {}
    comps = [(c.get("address"), c.get("sale_price"))
             for c in (vd.get("valuation_breakdown", {}) or {}).get("comparable_sales", [])[:3]]
    rng = conf.get("range") or {}
    return {
        "address": d.get("address"), "price_text": d.get("price"),
        "beds": d.get("bedrooms"), "baths": d.get("bathrooms"),
        "features": (d.get("property_features") or d.get("features") or [])[:8],
        "our_range": [rng.get("low"), rng.get("high")],
        "confidence": conf.get("confidence"),
        "positioning": (vd.get("summary", {}) or {}).get("positioning"),
        "recent_comps": comps,
    }


def telegram(text):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text[:4000]}, timeout=20)
    except Exception as e:
        print(f"telegram failed: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sm = get_client()["system_monitor"]
    sends = {s["send_id"]: s for s in sm["email_sends"].find()}
    seen = set()
    processed = 0
    for e in sm["email_events"].find({"kind": "click"}):
        target = e.get("target") or ""
        m = re.search(r"/property/([a-z0-9-]+)", target)
        if not m:
            continue
        slug = m.group(1)
        s = sends.get(e.get("send_id"))
        email = (s.get("to") if s else "").strip().lower()
        if not email or email == "will@fieldsestate.com.au":
            continue
        key = f"{email}|{slug}"
        if key in seen or sm["hot_lead_drafts"].find_one({"_id": key}):
            continue
        seen.add(key)

        prop, _ = find_property(slug)
        if not prop:
            print(f"  property not found: {slug}"); continue
        lead = sm["fb_leads"].find_one({"fields.email": email})
        brief = (lead or {}).get("fields", {})
        pbrief = property_brief(prop)
        prompt = (RULES + "\n\n===== LEAD BRIEF =====\n" + json.dumps(brief) +
                  "\n\n===== PROPERTY THEY CLICKED =====\n" + json.dumps(pbrief, default=str))
        try:
            out = claude(prompt)
            a, b = out.find("{"), out.rfind("}")
            draft = json.loads(out[a:b + 1])
        except Exception as ex:
            print(f"  draft failed for {email}: {ex}"); continue

        msg = (f"✍️ AI DRAFT — hot lead {email}\nClicked: {pbrief['address']}\n"
               f"(Owns GC home: {brief.get('owns_gc_home','?')} · timeframe: {brief.get('timeframe','?')})\n\n"
               f"SUBJECT: {draft.get('subject')}\n\n{draft.get('body')}\n\n"
               f"— reply here to approve/edit; I'll send on your go.")
        if args.dry_run:
            print(msg); continue
        telegram(msg)
        sm["hot_lead_drafts"].insert_one({"_id": key, "email": email, "slug": slug,
                                          "property": pbrief["address"], "draft": draft,
                                          "created_at": datetime.now(timezone.utc).isoformat(),
                                          "status": "drafted_pending_review"})
        processed += 1
        print(f"  drafted for {email} re {slug}")
    print(f"done — {processed} new draft(s)")


if __name__ == "__main__":
    main()
