#!/usr/bin/env python3
import json, re, os

QA = "/home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process/qa"
ENGINE = "/home/fields/Feilds_Website/01_Website/src/components/MarketFlowProto/MarketFlowProto.engine.ts"

# ---- parse WALK_SEGMENTS ----
src = open(ENGINE).read()
m = re.search(r"var WALK_SEGMENTS=(\[\[.*?\]\]);", src, re.S)
arr_text = m.group(1)
# It's valid JSON (numbers + double-quoted strings)
SEGMENTS = json.loads(arr_text)
print(f"parsed {len(SEGMENTS)} segments")

# ---- load words ----
words = json.load(open(f"{QA}/words.json"))
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())
W = [(norm(w["w"]), w["start"], w["end"]) for w in words]
Wnorm = [x[0] for x in W]
Wstart = [x[1] for x in W]
N = len(W)
print(f"{N} words, audio ends {W[-1][2]:.1f}s")

def seg_tokens(text, k=6):
    toks = [norm(t) for t in re.findall(r"[A-Za-z0-9']+", text)]
    toks = [t for t in toks if t]
    return toks[:k]

# ---- monotonic-ish alignment ----
# For each segment find best window start matching its opening tokens.
# Score = token overlap (order-aware) minus proximity penalty to declared time.
results = []
prev_idx = 0
for si, (declared, text) in enumerate(SEGMENTS):
    toks = seg_tokens(text, 6)
    L = len(toks)
    best = None
    # search whole transcript but bias to proximity of declared time and forward progress
    for i in range(N):
        # order-aware overlap of toks against W[i:i+L+2]
        window = Wnorm[i:i+L+3]
        # greedy sequential match
        wi = 0; matched = 0; firstmatch_off = None
        for ti, t in enumerate(toks):
            while wi < len(window):
                if window[wi] == t:
                    if firstmatch_off is None: firstmatch_off = wi
                    matched += 1; wi += 1; break
                wi += 1
        if matched == 0:
            continue
        frac = matched / L
        tstart = Wstart[i]
        prox = abs(tstart - declared)
        # score: prioritise match fraction, then closeness to declared time
        score = frac * 100 - prox * 0.5
        # forward-progress bonus: prefer at/after previous matched word
        if i >= prev_idx: score += 3
        if best is None or score > best[0]:
            best = (score, i, tstart, matched, frac)
    if best is None:
        results.append({"i": si, "declared": declared, "text": text,
                        "actual": None, "drift": None, "match_frac": 0})
        continue
    _, idx, tstart, matched, frac = best
    prev_idx = idx
    drift = round(declared - tstart, 2)
    results.append({"i": si, "declared": declared, "actual": round(tstart, 2),
                    "drift": drift, "match_frac": round(frac, 2),
                    "matched_words": matched,
                    "text": text[:60]})

# ---- report ----
flagged = [r for r in results if r["drift"] is not None and abs(r["drift"]) > 0.6]
print(f"\n{len(flagged)} segments with |drift|>0.6s of {len(results)}")

worst = sorted([r for r in results if r["drift"] is not None],
               key=lambda r: -abs(r["drift"]))[:8]
print("\nWORST OFFENDERS:")
for r in worst:
    print(f"  seg{r['i']:>2} declared={r['declared']:>7.2f} actual={r['actual']:>7.2f} "
          f"drift={r['drift']:>+7.2f} frac={r['match_frac']} | {r['text']}")

drifts = [r["drift"] for r in results if r["drift"] is not None]
print(f"\nmean drift={sum(drifts)/len(drifts):+.2f}s  "
      f"min={min(drifts):+.2f}  max={max(drifts):+.2f}")

# low-confidence matches to review
lowconf = [r for r in results if r["match_frac"] < 0.6]
print(f"\nlow-confidence matches (frac<0.6): {len(lowconf)}")
for r in lowconf:
    print(f"  seg{r['i']} frac={r['match_frac']} declared={r['declared']} actual={r['actual']} | {r['text']}")

json.dump(results, open(f"{QA}/walk_segments_drift.json", "w"), indent=2)

# ---- corrected array ----
def esc(s): return s.replace("\\", "\\\\").replace('"', '\\"')
lines = ["  var WALK_SEGMENTS=["]
parts = []
for si, (declared, text) in enumerate(SEGMENTS):
    r = results[si]
    newt = r["actual"] if (r["actual"] is not None and r["match_frac"] >= 0.5) else declared
    parts.append(f'[{newt},"{esc(text)}"]')
lines.append(",".join(parts) + "];")
open(f"{QA}/walk_segments_corrected.txt", "w").write("\n".join(lines) + "\n")
print(f"\nwrote walk_segments_drift.json and walk_segments_corrected.txt")
