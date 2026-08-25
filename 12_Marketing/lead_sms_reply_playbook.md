# Lead SMS — Reply Playbook (JustCall)

**First touch is automated** (`scripts/lead_sms_responder.py`, per-narrative, drives a reply).
**You handle the conversation** in the JustCall inbox. Structure: value first, one ask at a time.

## The 3-beat arc
1. **Deliver** — give the promised thing (auto first SMS does this).
2. **Understand** — one question at a time across the thread: suburbs · hard budget · sell-first? · timeframe · ready to inspect.
3. **Advance** — next concrete step: send matched homes · book an inspection · introduce to the appointed agent (conjunction).

## Snippets for common inbounds (compliance-safe — no advice, no "buyer's agent")
- **"YES / send it"** (Value Gap): *"Great. The eight comparable sales sit roughly $1.55M–$1.65M; it's asking $1,389,000. Full like-for-like here: [link]. What suburbs are you looking across?"*
- **"Is it good value?"** *"The comparable sales point higher than the asking — I'll show you the like-for-like and you can judge. Want it?"* (never "yes, buy it")
- **"What's your fee?"** *"Nothing to you as the buyer — we're paid by the selling side under a conjunction arrangement, so our read stays independent."*
- **"Are you the agent?"** *"No — we're not the appointed selling agent. We analyse the whole market for buyers."*
- **"Not right now"** *"No worries — want me to flag homes that genuinely fit as they come up? I'll only message on a real match."*
- **STOP** — JustCall honours opt-out automatically; don't re-contact.

## Guardrails (every message)
No advice / no predictions · never "buyer's agent" · data-only framing · no-buyer-fee / conjunction line where relevant · identify Fields · business hours.

## Operating the responder
- `python3 scripts/lead_sms_responder.py` → dry-run (prints, sends nothing)
- `python3 scripts/lead_sms_responder.py --send` → sends first-touch to new narrative leads
- `python3 scripts/lead_sms_responder.py --test +61…` → one test SMS
- Suggested schedule: every 15 min, a few min **after** `fb-lead-puller.py` (which captures leads → `fb_leads`). Self-reports to the Systems Health board when run with `--send`.
