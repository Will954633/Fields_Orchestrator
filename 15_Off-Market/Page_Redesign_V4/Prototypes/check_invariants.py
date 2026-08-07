#!/usr/bin/env python3
"""check_invariants.py — structural assertions a passing render cannot make.

WHY (Will, 2026-08-07): "successful render is necessary but no longer
sufficient." Twice in one day the generator produced valid HTML that was wrong:
functions silently deleted by a slice edit (recovered from GitHub), duplicate
definitions Python happily accepted, and forward cues asking questions the next
section did not answer.

    python3 check_invariants.py            # after any render
"""
import ast
import glob
import re
import sys
from collections import Counter

SRC = "render_prototype_a.py"
OUT = "/home/fields/Fields_Orchestrator/15_Off-Market/Concepts/V4_Private_Report"

fails = []

# 1 · no duplicate top-level definitions. Python takes the last silently.
tree = ast.parse(open(SRC).read())
names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
for name, n in Counter(names).items():
    if n > 1:
        fails.append(f"duplicate definition: {name} defined {n} times")

# 2 · every function the renderer calls exists exactly once.
REQUIRED = ["render", "evidence_cards", "differences_in_words", "_phrase", "excluded_sale",
            "market_insights", "median_chart", "median_block", "seasonality_strip",
            "timing_answer", "hero_image", "scarcity_map", "report_qr", "build_index"]
for r in REQUIRED:
    if names.count(r) != 1:
        fails.append(f"expected exactly one `{r}`, found {names.count(r)}")

# 3 · every forward cue resolves to the section that ACTUALLY follows it, so the
#     question it asks is the one the next section answers.
for f in sorted(glob.glob(f"{OUT}/*.html")):
    if f.endswith("index.html") or re.search(r"--v\d+\.html$", f):
        continue
    h = open(f).read()
    order = re.findall(r'<section id="([^"]+)"', h)
    ids = set(order)
    for href in set(re.findall(r'href="#([^"]+)"', h)):
        if href not in ids:
            fails.append(f"{f.split('/')[-1]}: dead anchor #{href}")
    for i, (sid, body) in enumerate(re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>',
                                               h, re.S)):
        m = re.search(r'<a class="cue" href="#([^"]+)"', body)
        if not m:
            continue
        nxt = order[i + 1] if i + 1 < len(order) else None
        if m.group(1) != nxt:
            fails.append(f"{f.split('/')[-1]}: cue in #{sid} points at #{m.group(1)}, "
                         f"but #{nxt} follows")

print("\n".join(f"  ✗ {x}" for x in fails) if fails else "  ✓ all invariants hold")
sys.exit(1 if fails else 0)
