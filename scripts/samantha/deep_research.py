#!/usr/bin/env python3
"""
deep_research.py — Samantha's fanned-out DEEP RESEARCH capability.

The conductor (Samantha) runs headless (`claude -p`), which has no Agent/Task tool — so she
cannot fan out parallel research subagents on her own. This tool gives her that: she calls it
via Bash with a question, and IT spawns several parallel research agents (each a `claude -p`
on Claude Max), each attacking a different ANGLE of the question with the web + the Brains,
then a synthesis pass fuses them into one report of signals + non-obvious levers + recommended bets.

  python3 scripts/samantha/deep_research.py "why are onsite hot-leads not leaving a phone number?"
  python3 scripts/samantha/deep_research.py "<q>" --n 5            # number of parallel angles (2-6, default 4)
  python3 scripts/samantha/deep_research.py "<q>" --angles "a||b||c"   # explicit angles, skip decomposition
  python3 scripts/samantha/deep_research.py "<q>" --dry-run        # show the plan (angles) without spawning agents
  python3 scripts/samantha/deep_research.py "<q>" --out PATH       # where to write the report (default logs/research/)

Design (first-principles framing → multi-modal sweep → synthesis):
  1. FRAME from FIRST PRINCIPLES — disaggregate the problem into its core components and state the CORE
     problem in DOMAIN-INDEPENDENT terms, so it can be matched to analogous cases in any industry.
  2. DECOMPOSE into N distinct first-principles angles (each targets a different component/force).
  3. FAN OUT — one agent per angle PLUS a dedicated CROSS-DOMAIN CASE-STUDY hunter (finds businesses in
     any industry that solved this same core problem and extracts the transferable mechanism). All run
     CONCURRENTLY (cap 3), each using WebSearch/WebFetch + the Brains via Bash.
  4. SYNTHESISE — a final agent fuses everything into: signals, cross-domain analogues, non-obvious
     levers, recommended bets (with how to test each), and what's still unknown.

Cost note: this is several Claude Max runs. It is for BIG strategic questions, not routine lookups.
All child agents run on Max (ANTHROPIC_API_KEY stripped), like the RL cycle runners.
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Brisbane")
ORCH = "/home/fields/Fields_Orchestrator"
RESEARCH_DIR = os.path.join(ORCH, "logs", "research")
MAX_CONCURRENCY = 3
DEFAULT_ANGLES = 4

BRAIN_TOOLBOX = (
    "Research tools available to you (call via Bash from /home/fields/Fields_Orchestrator):\n"
    "  • Web: use WebSearch / WebFetch for external market, competitor, channel and audience signals.\n"
    "  • Brain 1 (coaching/sales/seller-conversion expertise, 12.6M tokens):\n"
    "      python3 scripts/samantha/brain_search.py \"<q>\" --brain all    (fast, zero-cost recall)\n"
    "      python3 scripts/samantha/brain1_deep.py \"<question>\"          (deep synthesis, slower)\n"
    "  • Brain 2 (OUR OWN behaviour — FB Ads + PostHog): query HogQL via scripts/brain2/brain2_util.py (hog_retry).\n"
    "  • Brain 3 / KB (internal knowledge + 1,644 docs):\n"
    "      python3 scripts/samantha/brain_search.py \"<q>\" --brain 3\n"
    "      python3 scripts/search-kb.py \"<q>\"\n"
)


def _clean_env() -> dict:
    """Env for child `claude -p` runs: force Claude Max, allow nested headless claude, keep gh auth."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_SSE_PORT")}
    env.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")
    return env


def _run_claude(prompt: str, tools: str, max_turns: int, timeout: int) -> str:
    """One headless Claude Max invocation. Returns stdout (best-effort; never raises)."""
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", tools, "--max-turns", str(max_turns)],
            cwd=ORCH, env=_clean_env(), capture_output=True, text=True, timeout=timeout,
        )
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "[research agent timed out]"
    except Exception as e:  # noqa: BLE001
        return f"[research agent failed: {e}]"


def frame(question: str) -> str:
    """First-principles framing: disaggregate the problem into its core components and state the
    CORE problem in DOMAIN-INDEPENDENT terms — so it can be matched to analogous cases in any industry."""
    prompt = (
        "Think from FIRST PRINCIPLES about this problem. Do two things, tightly:\n"
        f"  PROBLEM: \"{question}\"\n\n"
        "1. DISAGGREGATE it into its 3-5 core components / mechanisms (the underlying forces at work, not surface symptoms).\n"
        "2. State the CORE problem in ONE sentence, stripped of our industry — domain-independent, abstract enough that a "
        "business in a totally different field could recognise it as the same problem (e.g. not 'sellers won't leave a "
        "phone number' but 'users won't surrender a high-friction contact signal before they trust the value exchange').\n\n"
        "Output exactly:\nCORE: <one domain-independent sentence>\nCOMPONENTS: <c1; c2; c3; ...>"
    )
    out = _run_claude(prompt, tools="", max_turns=2, timeout=180)
    return out.strip() if out and not out.startswith("[") else f"CORE: {question}\nCOMPONENTS: (framing unavailable)"


def decompose(question: str, framing: str, n: int) -> list[str]:
    """Break the question into N distinct FIRST-PRINCIPLES research angles (one fast claude call; robust fallback)."""
    prompt = (
        f"Given this first-principles framing of a problem:\n{framing}\n\n"
        f"Original question: \"{question}\"\n\n"
        f"Propose exactly {n} DISTINCT, non-overlapping research angles — each targets a different COMPONENT or force "
        f"from the framing (e.g. our own data, buyer/seller psychology, channel mechanics, pricing, friction, trust). "
        f"Do NOT include a cross-industry case-study angle here — that is handled separately.\n\n"
        f"Output ONLY the {n} angles, one per line, no numbering, no preamble. Each ≤ 14 words."
    )
    out = _run_claude(prompt, tools="", max_turns=2, timeout=180)
    angles = [re.sub(r"^\s*[-*\d.)]+\s*", "", ln).strip()
              for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("[")]
    angles = [a for a in angles if 3 < len(a) < 160][:n]
    if len(angles) >= 2:
        return angles
    # fallback lenses if the model didn't return clean lines
    lenses = [
        f"What our own data (PostHog + FB Ads, Brain 2) reveals about: {question}",
        f"What sales/seller-conversion expertise (Brain 1 coaching corpus) says about: {question}",
        f"External market / competitor / channel signals relevant to: {question}",
        f"The specific friction points and psychology behind: {question}",
        f"Untapped levers or new channels that could address: {question}",
        f"How comparable businesses solve: {question}",
    ]
    return lenses[:n]


def research_angle(idx: int, angle: str, question: str, framing: str) -> dict:
    prompt = (
        f"You are research agent #{idx} in a parallel sweep. The overall question is:\n  \"{question}\"\n\n"
        f"First-principles framing (shared across the sweep):\n{framing}\n\n"
        f"Research ONLY this angle:\n  \"{angle}\"\n\n"
        f"{BRAIN_TOOLBOX}\n"
        "Do REAL research — query the brains and/or the web, don't reason from memory. Then return, concisely:\n"
        "  • 3-7 concrete FINDINGS (each with its source: which brain / which URL / which dataset)\n"
        "  • any NON-OBVIOUS lever or signal this angle surfaced\n"
        "  • confidence (high/med/low) and what would raise it.\n"
        "Be specific and cite. No preamble."
    )
    out = _run_claude(prompt, tools="Bash,Read,Grep,Glob,WebSearch,WebFetch", max_turns=18, timeout=600)
    return {"idx": idx, "angle": angle, "findings": out}


def analogue_agent(idx: int, question: str, framing: str) -> dict:
    """The cross-domain case-study hunter: match the ABSTRACT core problem to businesses in ANY industry
    that faced the same core problem, and extract how they solved it (the transferable mechanism)."""
    angle = "Cross-domain case studies — who else solved this core problem, and how"
    prompt = (
        "You are the CROSS-DOMAIN CASE-STUDY research agent. Businesses in completely different industries have often "
        "already solved this problem in its abstract form — your job is to find them and extract the transferable mechanism.\n\n"
        f"Original problem: \"{question}\"\n\n"
        f"First-principles framing (work from the CORE, domain-independent statement — NOT our industry):\n{framing}\n\n"
        "Method:\n"
        "1. Take the CORE problem as stated abstractly above.\n"
        "2. Use WebSearch/WebFetch to find 3-5 REAL businesses/products IN ANY DOMAIN (fintech, gaming, dating, SaaS, "
        "   retail, healthcare, marketplaces, etc.) that faced this SAME core problem — the more distant the industry, "
        "   the more valuable if the mechanism transfers.\n"
        "3. For each: name the company, what they actually did, the RESULT (numbers if available), and — most important — "
        "   the underlying MECHANISM, stated abstractly so it can be ported back to Fields.\n"
        "4. End with: which mechanism(s) most plausibly transfer to our problem, and the concrete experiment that would test it here.\n"
        "Cite every case (URL). Prefer documented cases over generic advice. No preamble."
    )
    out = _run_claude(prompt, tools="Bash,Read,Grep,WebSearch,WebFetch", max_turns=20, timeout=700)
    return {"idx": idx, "angle": angle, "findings": out}


def synthesise(question: str, framing: str, results: list[dict]) -> str:
    blocks = "\n\n".join(f"### Angle {r['idx']}: {r['angle']}\n{r['findings']}" for r in results)
    prompt = (
        f"You are the synthesis pass for a deep-research sweep on:\n  \"{question}\"\n\n"
        f"First-principles framing:\n{framing}\n\n"
        f"Here is what each parallel research angle found (the last is a cross-domain case-study hunt):\n\n{blocks}\n\n"
        "Fuse these into ONE decision-useful report with these sections (markdown):\n"
        "  ## Signals found — the strongest evidence across angles (cite sources; flag agreements + contradictions)\n"
        "  ## Cross-domain analogues — the transferable mechanisms other industries used on this same core problem, "
        "and how each would port to Fields\n"
        "  ## Non-obvious levers — things the routine sub-processes would not have surfaced\n"
        "  ## Recommended bets — ranked; for each: the hypothesis, the milestone it should move, how to test it "
        "(flag-gated experiment vs needs-Will), and the kill/scale rule\n"
        "  ## Still unknown — what to research or ingest next\n"
        "Be honest about weak evidence. No filler."
    )
    return _run_claude(prompt, tools="Bash,Read,Grep,WebSearch,WebFetch", max_turns=12, timeout=600)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--n", type=int, default=DEFAULT_ANGLES, help="number of parallel angles (2-6)")
    ap.add_argument("--angles", default=None, help="explicit angles, '||'-separated (skips decomposition)")
    ap.add_argument("--out", default=None, help="report output path")
    ap.add_argument("--dry-run", action="store_true", help="show the plan (angles) without spawning agents")
    args = ap.parse_args()

    n = max(2, min(6, args.n))
    stamp = datetime.now(AEST).strftime("%Y%m%d_%H%M")

    print("[deep_research] framing the problem from first principles…", flush=True)
    framing = frame(args.question)
    print(f"[deep_research] {framing}", flush=True)

    if args.angles:
        angles = [a.strip() for a in args.angles.split("||") if a.strip()][:n]
    else:
        print(f"[deep_research] decomposing into {n} first-principles angles…", flush=True)
        angles = decompose(args.question, framing, n)

    print(f"[deep_research] question: {args.question}", flush=True)
    for i, a in enumerate(angles, 1):
        print(f"   angle {i}: {a}", flush=True)
    print(f"   angle {len(angles)+1}: [cross-domain case-study hunter]", flush=True)
    if args.dry_run:
        print("[deep_research] --dry-run: not spawning agents.", flush=True)
        return 0

    n_agents = len(angles) + 1  # + the cross-domain analogue agent
    print(f"[deep_research] fanning out {n_agents} agents (concurrency {MAX_CONCURRENCY})…", flush=True)
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as ex:
        futs = [ex.submit(research_angle, i, a, args.question, framing) for i, a in enumerate(angles, 1)]
        futs.append(ex.submit(analogue_agent, len(angles) + 1, args.question, framing))
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            print(f"[deep_research] angle {r['idx']} done ({len(r['findings'])} chars)", flush=True)
    results.sort(key=lambda r: r["idx"])

    print("[deep_research] synthesising…", flush=True)
    report_body = synthesise(args.question, framing, results)

    os.makedirs(RESEARCH_DIR, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.question.lower())[:48].strip("-")
    out_path = args.out or os.path.join(RESEARCH_DIR, f"{stamp}_{slug}.md")
    header = (f"# Deep research — {args.question}\n\n"
              f"_Generated {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')} · {len(angles)} angles_\n\n")
    appendix = "\n\n---\n## Appendix — raw angle findings\n\n" + \
               "\n\n".join(f"### Angle {r['idx']}: {r['angle']}\n{r['findings']}" for r in results)
    with open(out_path, "w") as f:
        f.write(header + report_body + appendix)

    print(f"\n[deep_research] REPORT → {out_path}\n", flush=True)
    print(report_body, flush=True)  # so the calling conductor reads the synthesis directly
    return 0


if __name__ == "__main__":
    sys.exit(main())
