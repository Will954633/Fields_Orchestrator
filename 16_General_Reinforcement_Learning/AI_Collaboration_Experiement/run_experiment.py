#!/usr/bin/env python3
"""
run_experiment.py — run one arm of one experiment.

Every arm gets the IDENTICAL brief (_contract.md + the experiment file) so the
head-to-head comparison is fair. The GPT arm runs here; the Claude arm runs through
Claude Code subagents with the same brief text.

    python3 run_experiment.py E1_cost --arm gpt --max-calls 45
"""
import argparse
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP / "lib"))


def build_brief(name: str, exclude_fixed: bool = True) -> str:
    """Contract + experiment body, plus the already-fixed exclusion list.

    Round 2 (2026-08-08) needs the exclusion list so the run measures INCREMENTAL
    discovery. Without it both arms re-report the round-1 findings and the
    complementarity number is meaningless — you cannot tell a new insight from a
    restatement of one already acted on.
    """
    parts = [(EXP / "experiments" / "_contract.md").read_text()]
    if exclude_fixed:
        fixed = EXP / "experiments" / "_already_fixed.md"
        if fixed.exists():
            parts.append(fixed.read_text())
    parts.append((EXP / "experiments" / f"{name}.md").read_text())
    return "\n\n---\n\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment")
    ap.add_argument("--arm", default="gpt", choices=["gpt"])
    ap.add_argument("--max-calls", type=int, default=45)
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--round", default="", help="suffix for the run dir, e.g. r2")
    ap.add_argument("--include-fixed", action="store_true",
                    help="omit the already-fixed exclusion list (round-1 behaviour)")
    a = ap.parse_args()

    brief = build_brief(a.experiment, exclude_fixed=not a.include_fixed)
    run_dir = EXP / "runs" / (f"{a.experiment}_{a.round}" if a.round else a.experiment)
    (run_dir).mkdir(parents=True, exist_ok=True)
    (run_dir / "BRIEF.md").write_text(brief)

    from vm_agent import VmAgent
    agent = VmAgent(run_dir, allow_http=a.http)
    print(f"=== {a.experiment} · arm={a.arm} · model={agent.model} ===", flush=True)
    res = agent.investigate(brief, max_calls=a.max_calls, label=f"{a.arm}_arm")
    print(f"\n=== DONE {a.experiment} · {res.calls} calls · "
          f"{res.tokens_in:,} in / {res.tokens_out:,} out · ~${res.cost_usd:.2f} ===")


if __name__ == "__main__":
    main()
