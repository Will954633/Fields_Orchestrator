#!/usr/bin/env python3
"""
Market Forecasting — combination model (demand/rate-cycle house-price regime predictor).

Predicts Australian capital-city house-price REGIMES ~6 months ahead from four
macro inputs. See README.md for the full story, caveats, and how it was de-risked.

Inputs (both live beside this script):
  abs_panel.csv      8-capital-city quarterly panel (ABS): price_index, lending,
                     retail, unemployment, cpi   (built by build_panel.py)
  national_macro.csv national ASX All Ords + cash rate, quarterly

Model:
  features (all growth-rate / change form, cross-city comparable):
    L = new housing lending  : YoY% , QoQ%
    S = retail turnover       : YoY% , QoQ%
    A = ASX All Ordinaries    : YoY%
    C = cash rate             : level , 4q change
  target : house-price index YoY momentum at +2 quarters (6 months)
  estimator : ridge regression (alpha=8), expanding walk-forward, standardised on train

Key result: point-forecasting the *level* barely beats persistence, BUT classifying
the *tails* (declines / dramatic upswings) 6 months out works well (AUC ~0.90).
Two warning signals fall out of that — see the printed report.

Run:  python3 market_forecasting_model.py
"""
import csv, os, warnings
from collections import defaultdict
import numpy as np
from numpy.linalg import pinv
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
LEAD_Q = 2          # forecast horizon in quarters (2 = 6 months)
RIDGE_ALPHA = 8.0
TRAIN_FRAC = 0.40   # walk-forward: first 40% of quarters seed the model

# ---------- load panel + national macro ----------
panel = list(csv.DictReader(open(os.path.join(HERE, "abs_panel.csv"))))
by = defaultdict(dict)
for r in panel:
    by[r["city"]][r["quarter"]] = r
cities = sorted(by)
quarters = sorted({r["quarter"] for r in panel})
qi = {q: i for i, q in enumerate(quarters)}

nat = {r["quarter"]: r for r in csv.DictReader(open(os.path.join(HERE, "national_macro.csv")))}
def natval(q, col):
    r = nat.get(q)
    try: return float(r[col])
    except: return None

def g(c, q, f):
    d = by[c].get(q)
    try: return float(d[f])
    except: return None
def yoy(c, q, f):
    i = qi[q]
    if i < 4: return None
    a, b = g(c, q, f), g(c, quarters[i-4], f)
    return 100*(a/b - 1) if (a and b) else None
def qoq(c, q, f):
    i = qi[q]
    if i < 1: return None
    a, b = g(c, q, f), g(c, quarters[i-1], f)
    return 100*(a/b - 1) if (a and b) else None
def asx_yoy(q):
    i = qi[q]
    if i < 4: return None
    a, b = natval(q, "asx_allords"), natval(quarters[i-4], "asx_allords")
    return 100*(a/b - 1) if (a and b) else None
def price_momentum(c, q):
    return yoy(c, q, "price_index")

def features(c, q, keys):
    """keys is any subset of 'LSAC'. Returns list of feature values or None if incomplete."""
    out = []
    if "L" in keys: out += [yoy(c, q, "lending"), qoq(c, q, "lending")]
    if "S" in keys: out += [yoy(c, q, "retail"),  qoq(c, q, "retail")]
    if "A" in keys: out += [asx_yoy(q)]
    if "C" in keys: out += [natval(q, "cash_rate"), natval(q, "cash_rate_chg4q")]
    return out

def walk_forward(keys, lead=LEAD_Q, alpha=RIDGE_ALPHA):
    """Expanding-window ridge. Returns (actual, predicted) arrays, out-of-sample."""
    rows = []
    for c in cities:
        for q in quarters:
            i = qi[q]
            if i + lead >= len(quarters): continue
            X = features(c, q, keys)
            y = price_momentum(c, quarters[i+lead])
            if not X or any(v is None for v in X) or y is None: continue
            rows.append((i+lead, np.array(X), y))
    tq = sorted({r[0] for r in rows})
    start = tq[int(len(tq)*TRAIN_FRAC)]
    A, P = [], []
    for cut in tq:
        if cut < start: continue
        tr = [r for r in rows if r[0] < cut]
        te = [r for r in rows if r[0] == cut]
        if len(tr) < 40 or not te: continue
        Xtr = np.array([r[1] for r in tr]); ytr = np.array([r[2] for r in tr])
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        w = pinv(((Xtr-mu)/sd).T @ ((Xtr-mu)/sd) + alpha*np.eye(Xtr.shape[1])) @ ((Xtr-mu)/sd).T @ (ytr - ytr.mean())
        for r in te:
            A.append(r[2]); P.append(((r[1]-mu)/sd) @ w + ytr.mean())
    return np.array(A), np.array(P)

def auc(score, label):
    pos, neg = score[label], score[~label]
    if not len(pos) or not len(neg): return float("nan")
    return sum((1 if p>n else .5 if p==n else 0) for p in pos for n in neg) / (len(pos)*len(neg))

def warning_table(A, P, positive, direction):
    order = np.argsort(P) if direction == "low" else np.argsort(-P)
    base = positive.mean()
    out = []
    for pct in (10, 20, 25, 33):
        k = int(len(P)*pct/100)
        fired = np.zeros(len(P), bool); fired[order[:k]] = True
        prec = positive[fired].mean() if fired.any() else 0
        rec  = fired[positive].mean() if positive.any() else 0
        thr  = P[order[k-1]]
        out.append((pct, thr, prec, rec, prec/base if base else 0))
    return base, out

# ---------- report ----------
print("="*70)
print("MARKET FORECASTING — combination model report")
print(f"panel: {len(cities)} cities x {len(quarters)} quarters ({quarters[0]}..{quarters[-1]})")
print(f"horizon: {LEAD_Q} quarters ({LEAD_Q*3} months) | estimator: ridge(alpha={RIDGE_ALPHA}) walk-forward")
print("="*70)

DECLINE = "LSC"      # best decline combo
UPSWING = "LSAC"     # best upswing combo

for label, keys, direction in [("DECLINE (future momentum <= 0%)", DECLINE, "low"),
                               ("DRAMATIC UPSWING (future momentum >= 85th pct)", UPSWING, "high")]:
    A, P = walk_forward(keys)
    if direction == "low":
        pos = A <= 0.0
        aroc = auc(-P, pos)
    else:
        pos = A >= np.percentile(A, 85)
        aroc = auc(P, pos)
    base, tbl = warning_table(A, P, pos, direction)
    print(f"\n### {label}")
    print(f"   model: {keys} @ {LEAD_Q*3}mo | n_oos={len(A)} | base rate={base:.0%} | AUC={aroc:.3f}")
    print(f"   {'fire when':22s} fires  precision  recall  lift")
    for pct, thr, prec, rec, lift in tbl:
        cond = f"pred {'<=' if direction=='low' else '>='} {thr:+.1f}%"
        print(f"   {cond:22s} {pct:3d}%    {prec:5.0%}    {rec:5.0%}   {lift:.1f}x")

# overall point-forecast R2 vs persistence (shows why we use regimes, not levels)
def r2_vs_persistence(keys, lead):
    A, P = walk_forward(keys, lead)
    # persistence = current momentum; recompute aligned
    PE = []
    idx = 0
    rows = []
    for c in cities:
        for q in quarters:
            i = qi[q]
            if i + lead >= len(quarters): continue
            X = features(c, q, keys); y = price_momentum(c, quarters[i+lead]); pe = price_momentum(c, q)
            if not X or any(v is None for v in X) or y is None or pe is None: continue
            rows.append((i+lead, y, pe))
    tq = sorted({r[0] for r in rows}); start = tq[int(len(tq)*TRAIN_FRAC)]
    A2, PE2 = [], []
    for cut in tq:
        if cut < start: continue
        te = [r for r in rows if r[0] == cut]
        if len([r for r in rows if r[0] < cut]) < 40 or not te: continue
        for r in te: A2.append(r[1]); PE2.append(r[2])
    A2, PE2 = np.array(A2), np.array(PE2)
    return 1 - ((A - P)**2).sum() / ((A2 - PE2)**2).sum()

print("\n### point-forecast R2 vs persistence (context — weak; use regimes above, not this)")
for h in (2, 3, 4):
    print(f"   LSAC @ {h*3}mo: R2 = {r2_vs_persistence('LSAC', h):+.2f}")
print("\n(See README.md for full method, de-risking, and caveats.)")
