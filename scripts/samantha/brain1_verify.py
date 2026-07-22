#!/usr/bin/env python3
"""
Brain 1 — QUOTE-LEVEL verifier.

The id-in-shortlist check in brain1_deep.py catches invented ids, but NOT misattribution:
a real quote tagged to the wrong (but in-shortlist) unit passes it. This closes that gap.

For every "quoted passage" (uXXXX) pair in a brief:
  1. Fuzzy-match the quote against the CITED unit's own annotation text (tolerates light
     transcription normalization, e.g. "curl"->"cull", and "..." elision joins).
  2. VERIFIED    — quote found in a cited unit.
  3. MISATTRIBUTED — not in any cited unit, but found elsewhere in the corpus -> report the
     unit it ACTUALLY belongs to (this is the u2520-vs-u2774 class of bug).
  4. NOT_FOUND   — not in any unit at all -> fabricated / paraphrased beyond recognition.

Exits nonzero if any MISATTRIBUTED or NOT_FOUND -> use as a publish gate.

Usage:
  python3 scripts/samantha/brain1_verify.py --file brief.md [--cover 0.85 --min-len 12 --show-ok]
"""
import os, re, sys, json, argparse
from difflib import SequenceMatcher

PACKAGE = "/home/fields/brain1_build/package.json"
# All annotation sources feeding the unified external brain — coaching (u####) + KB (k####).
# Without the KB files, KB-quote citations would falsely verify as fabricated.
ANN_FILES = [
    "/home/fields/brain1_build/annotations.jsonl",
    "/home/fields/brain3_build/annotations_public.jsonl",
    "/home/fields/brain3_build/annotations_private.jsonl",
    "/home/fields/brain3_ops/annotations_ops.jsonl",  # Brain 3 internal ops (i##### units)
]
_norm_re = re.compile(r"[^a-z0-9 ]+")
_ws = re.compile(r"\s+")


def norm(s):
    return _ws.sub(" ", _norm_re.sub(" ", (s or "").lower())).strip()


def unit_texts(ann_files=None):
    """unit_id -> normalized blob of its key_quotes + concepts + claims, across ALL annotation
    sources that exist (coaching + KB public/private)."""
    out = {}
    for path in (ann_files or ANN_FILES):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            blob = " ".join(d.get("key_quotes", []) + d.get("concepts", []) + d.get("claims", []))
            out[d["unit_id"]] = norm(blob)
    return out


def coverage(fragment, unit_blob):
    """Fraction of the (normalized) fragment's chars found in-order in unit_blob. Robust to a
    substring-with-small-edits (single-char transcription slips barely dent the score)."""
    a, b = norm(fragment), unit_blob
    if not a:
        return 0.0
    if len(a) < 12:
        return 1.0 if a in b else 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return sum(bl.size for bl in sm.get_matching_blocks()) / len(a)


def fragments(quote):
    """Split a brief quote on ellipsis elisions; keep substantial pieces."""
    parts = re.split(r"\s*(?:\.\.\.|…)\s*", quote)
    return [p.strip() for p in parts if len(p.strip()) >= 8] or [quote.strip()]


def parse_pairs(text):
    """Every quote paired with the uXXXX ids that appear on the same line/bullet."""
    pairs = []
    for line in text.splitlines():
        quotes = re.findall(r'[\"“]([^\"”]{8,})[\"”]', line)
        ids = re.findall(r"[uki]\d{4,5}", line)  # u#### coaching + k##### KB
        for q in quotes:
            if ids:
                pairs.append((q, ids))
    return pairs


def verify_text(text, blobs=None, cover=0.85, true_cover=0.90, scope_ids=None):
    """Core: returns (total, verified, [misattr], [notfound]). Reusable by brain1_deep.
    misattr/notfound entries = {quote, cited, actual, cov}.
    scope_ids: if given, the "true source" search is limited to these unit ids (the queried
    brain). Without it, a single-brain query would falsely attribute a paraphrased quote to a
    verbatim match in ANOTHER brain that was never in context — cross-brain false positive."""
    if blobs is None:
        blobs = unit_texts()
    pairs = parse_pairs(text)
    verified, misattr, notfound = 0, [], []
    for q, ids in pairs:
        frs = fragments(q)
        if all(any(coverage(fr, blobs.get(i, "")) >= cover for i in ids) for fr in frs):
            verified += 1
            continue
        best_id, best = None, 0.0
        for uid, blob in blobs.items():
            if scope_ids is not None and uid not in scope_ids:
                continue
            c = min(coverage(fr, blob) for fr in frs)  # all fragments in the SAME unit
            if c > best:
                best, best_id = c, uid
        rec = {"quote": q, "cited": ids, "actual": best_id, "cov": round(best, 2)}
        (misattr if best >= true_cover else notfound).append(rec)
    return len(pairs), verified, misattr, notfound


def fix_citations(text, misattr):
    """Auto-correct MISATTRIBUTED quotes: swap the wrong cited id for the verified true source,
    anchored to the id token immediately AFTER each quote occurrence (handles multi-quote lines).
    Returns (fixed_text, n_fixed). NOT_FOUND is never touched — a fabricated quote has no true id."""
    fixed = 0
    for r in misattr:
        actual = r["actual"]
        # match the exact quote, then up to 60 chars, then the FIRST uXXXX -> replace that id
        pat = re.compile(r"(" + re.escape(r["quote"]) + r".{0,60}?)([uki]\d{4,5})", re.S)
        new, n = pat.subn(lambda m: m.group(1) + actual, text, count=1)
        if n:
            text, fixed = new, fixed + n
    return text, fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--cover", type=float, default=0.85, help="coverage to count a quote as present")
    ap.add_argument("--true-cover", type=float, default=0.90, help="stricter bar to claim the TRUE source")
    ap.add_argument("--fix-citations", action="store_true", help="auto-correct misattributed ids -> --out")
    ap.add_argument("--out", help="where to write the fixed brief (default: <file>.fixed.md)")
    ap.add_argument("--show-ok", action="store_true")
    args = ap.parse_args()

    text = open(args.file, encoding="utf-8").read()
    blobs = unit_texts()
    total, verified, misattr, notfound = verify_text(
        text, blobs=blobs, cover=args.cover, true_cover=args.true_cover)
    if not total:
        print("No (quote, id) pairs found — nothing to verify."); return

    if args.fix_citations:
        fixed_text, n = fix_citations(text, misattr)
        out = args.out or (args.file.rsplit(".", 1)[0] + ".fixed.md")
        open(out, "w", encoding="utf-8").write(fixed_text)
        print(f"[fix] corrected {n} misattributed citation(s) -> {out}")
        if notfound:
            print(f"[fix] ⚠ {len(notfound)} NOT_FOUND (fabricated) quotes left untouched — need manual review:")
            for r in notfound:
                print(f"      \"{r['quote'][:70]}\" (cited {','.join(r['cited'])})")
        # re-verify the fixed file to confirm
        t2, v2, m2, nf2 = verify_text(fixed_text, blobs=blobs, cover=args.cover, true_cover=args.true_cover)
        print(f"[fix] re-verify: {v2}/{t2} verified | {len(m2)} MISATTRIBUTED | {len(nf2)} NOT_FOUND")
        sys.exit(0 if (not m2 and not nf2) else 1)

    for r in misattr:
        print(f"  ✗ MISATTRIBUTED: cited {','.join(r['cited'])} but quote is actually {r['actual']} "
              f"(cov {r['cov']}) — \"{r['quote'][:70]}\"")
    for r in notfound:
        print(f"  ✗ NOT_FOUND (best {r['actual']} cov {r['cov']}): cited {','.join(r['cited'])} — "
              f"\"{r['quote'][:70]}\"")
    print(f"\n[quote-verify] {total} quotes | {verified} verified | {len(misattr)} MISATTRIBUTED | "
          f"{len(notfound)} NOT_FOUND")
    print(f"[quote-verify] fidelity {100*verified/total:.1f}%")
    sys.exit(0 if (not misattr and not notfound) else 1)


if __name__ == "__main__":
    main()
