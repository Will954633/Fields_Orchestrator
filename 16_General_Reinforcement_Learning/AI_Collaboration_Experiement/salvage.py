#!/usr/bin/env python3
"""Recover crashed experiment runs from their recorded tool transcripts. Serial by design."""
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP / "lib"))
from vm_agent import VmAgent  # noqa: E402

total = 0.0
for name in sys.argv[1:]:
    run_dir = EXP / "runs" / name
    jsonl = run_dir / "gpt_arm.jsonl"
    if not jsonl.exists():
        print(f"{name}: no transcript, skipping")
        continue
    brief = (run_dir / "BRIEF.md").read_text()
    agent = VmAgent(run_dir)
    print(f"=== finalizing {name} ===", flush=True)
    res = agent.finalize_from_transcript(brief, jsonl, label="gpt_arm_final")
    total += res.cost_usd
    print(f"  {len(res.answer):,} chars · {res.tokens_in:,} in / {res.tokens_out:,} out "
          f"· ~${res.cost_usd:.2f}", flush=True)
print(f"\ntotal salvage cost ~${total:.2f}")
