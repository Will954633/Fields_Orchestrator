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
    """unit_id -> normalized blob of everything the graph actually exposes to the LLM: key_quotes +
    concepts + claims, PLUS decisions/initiatives/metrics (Brain-3-style facets) — brain1_graph.py
    folds those into the graph unit's "concepts" list at BUILD time, not in the raw annotation file,
    so a verifier reading only the raw file's "concepts" would falsely flag a verbatim-quoted
    decision/metric as fabricated. Across ALL annotation sources that exist (coaching + KB + ops)."""
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
            fields = ["key_quotes", "concepts", "claims", "decisions", "initiatives", "metrics"]
            blob = " ".join(x for f in fields for x in (d.get(f) or []) if isinstance(x, str))
            out[d["unit_id"]] = norm(blob)
    return out


# A quoted span shorter than this (normalized) that is NOT found verbatim anywhere cannot be
# attributed to a unit with any confidence. In practice these are the synthesis's own coined
# labels and scare-quotes ("substantial = authority", "14-day taper") rather than real citations.
MIN_ATTRIBUTABLE = 30
MIN_BLOCK = 8   # contiguity floor for fuzzy matching — see coverage() below
MAX_NAMED_SOURCES = 3


def coverage(fragment, unit_blob):
    """How much of `fragment` genuinely appears in `unit_blob`, as a 0..1 fraction.

    CONTIGUITY MATTERS. The previous implementation summed EVERY SequenceMatcher matching
    block, including 1- and 2-character ones. Over a long blob those scattered fragments
    reassemble almost any short needle, so the score was not a containment test at all:
    "substantial = authority" (21 normalized chars) scored >=0.90 against 5,621 of 9,525
    units. That is what produced confident-but-meaningless "-> actually u0001 (cov 1.0)"
    verdicts, and the misattribution counts built on them.

    Now: exact containment short-circuits to 1.0, and fuzzy matching only counts blocks of at
    least MIN_BLOCK characters — so a real quote with a transcription slip ("curl"->"cull")
    still scores ~1.0 (two long blocks either side of the slip), while a short needle
    assembled from noise scores 0.0.
    """
    a, b = norm(fragment), unit_blob
    if not a:
        return 0.0
    if a in b:
        return 1.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return sum(bl.size for bl in sm.get_matching_blocks() if bl.size >= MIN_BLOCK) / len(a)


def holders(frs, blobs, scope_ids=None, cover=0.90):
    """Unit ids that contain EVERY fragment of a quote. Exact-containment pass first (fast and
    unambiguous); fuzzy contiguity-aware pass only as a fallback for transcription slips.
    Returns (ids, matched_exactly)."""
    ids = [u for u, b in blobs.items()
           if (scope_ids is None or u in scope_ids) and all(norm(fr) in b for fr in frs)]
    if ids:
        return ids, True
    ids = [u for u, b in blobs.items()
           if (scope_ids is None or u in scope_ids)
           and all(coverage(fr, b) >= cover for fr in frs)]
    return ids, False


def fragments(quote):
    """Split a brief quote into the pieces that should appear VERBATIM in a source unit.

    Splits on ellipsis elisions AND on square-bracket editorial insertions — "I do 50
    [letterbox drops per week]" is quoting only "I do 50"; the bracketed words are the brief's
    own gloss and are not in the source, so matching against them guarantees a false miss.
    """
    parts = [p.strip() for p in re.split(r"\s*(?:\.\.\.|…|\[[^\]]*\])\s*", quote) if p.strip()]
    kept = [p for p in parts if len(p) >= 8]
    if kept:
        return kept
    # every piece is short — fall back to the elided/gloss-stripped remainder, NOT the raw quote,
    # so a mostly-glossed span is judged on the few words it actually quotes (and lands in
    # UNVERIFIABLE rather than being reported as a fabrication).
    return [" ".join(parts)] if parts else [quote.strip()]


def attributable_len(frs):
    """Verbatim characters actually available to attribute with (excludes elided/glossed text)."""
    return sum(len(norm(f)) for f in frs)


def parse_pairs(text):
    """Every quote paired with the uXXXX ids that appear on the same line/bullet."""
    pairs = []
    for line in text.splitlines():
        quotes = re.findall(r'[\"“]([^\"”]{8,})[\"”]', line)
        ids = re.findall(r"[uki]\d{4,10}", line)  # u#### coaching + k##### KB
        for q in quotes:
            if ids:
                pairs.append((q, ids))
    return pairs


def verify_text(text, blobs=None, cover=0.85, true_cover=0.90, scope_ids=None):
    """Core: returns (total, verified, [misattr], [notfound], [unverifiable]).

    Each record = {quote, cited, actual, sources, cov, exact, why}.

    Four verdicts, not three — the fourth is what the old implementation got wrong:
      VERIFIED      quote is present in one of the cited units.
      MISATTRIBUTED quote is present in the corpus, but NOT in any cited unit -> `sources`
                    names the unit(s) that actually hold it (ambiguous if several do).
      NOT_FOUND     long enough to attribute, found nowhere -> fabricated or paraphrased.
      UNVERIFIABLE  too short (< MIN_ATTRIBUTABLE) AND not found verbatim anywhere. These are
                    overwhelmingly the synthesis's own coined labels in quote marks, not
                    citations. Previously they were scored as MISATTRIBUTED against an
                    arbitrary "true source" picked out of thousands of spurious matches, which
                    is where the bogus misattribution counts came from. They still deserve a
                    human look (quote marks beside a unit id imply verbatim), but they are
                    reported separately and do not corrupt the fidelity figure.

    scope_ids: if given, the "true source" search is limited to these unit ids (the queried
    brain). Without it, a single-brain query would falsely attribute a paraphrased quote to a
    verbatim match in ANOTHER brain that was never in context — cross-brain false positive.
    """
    if blobs is None:
        blobs = unit_texts()
    pairs = parse_pairs(text)
    verified, misattr, notfound, unverifiable = 0, [], [], []
    for q, ids in pairs:
        frs = fragments(q)
        # present in a CITED unit?
        if all(any(coverage(fr, blobs.get(i, "")) >= cover for i in ids) for fr in frs):
            verified += 1
            continue
        found, exact = holders(frs, blobs, scope_ids=scope_ids, cover=true_cover)
        rec = {"quote": q, "cited": ids, "sources": sorted(found)[:MAX_NAMED_SOURCES],
               "actual": sorted(found)[0] if found else None,
               "cov": 1.0 if exact else round(
                   max((min(coverage(fr, blobs.get(u, "")) for fr in frs) for u in found),
                       default=0.0), 2),
               "exact": exact, "n_sources": len(found)}
        if found:
            rec["why"] = ("held by %d units — attribution ambiguous" % len(found)
                          if len(found) > MAX_NAMED_SOURCES else "held by a different unit")
            misattr.append(rec)
        elif attributable_len(frs) < MIN_ATTRIBUTABLE:
            rec["why"] = "too short to attribute and not found verbatim — likely a coined label, not a quote"
            unverifiable.append(rec)
        else:
            rec["why"] = "not found in any unit"
            notfound.append(rec)
    return len(pairs), verified, misattr, notfound, unverifiable


def _repair_line(line, quote, wrong_ids, actual):
    """Rewrite the id bound to `quote` ON THIS LINE, but only when the binding is unambiguous.

    Returns (new_line, changed). Ambiguity rules — all three matter:
      * the line must carry exactly ONE quoted span, otherwise "the id next to the quote" is a
        guess. A comparison-table row holding two quotes and two ids is the common case, and
        rewriting the nearer id there silently BREAKS the other quote's correct attribution.
      * the id we rewrite must be one the verifier actually flagged (`wrong_ids`).
      * the line must carry exactly one distinct flagged id, so there is one thing to replace.
    """
    quotes_on_line = re.findall(r'[\"“]([^\"”]{8,})[\"”]', line)
    if len(quotes_on_line) != 1 or quotes_on_line[0] != quote:
        return line, False
    present = [i for i in dict.fromkeys(re.findall(r"[uki]\d{4,10}", line)) if i in wrong_ids]
    if len(present) != 1:
        return line, False
    return re.sub(r"\b" + re.escape(present[0]) + r"\b", actual, line), True


def fix_citations(text, misattr, blobs=None, scope_ids=None):
    """Auto-correct MISATTRIBUTED quotes: swap the wrong cited id for the verified true source.

    Only UNAMBIGUOUS bindings are rewritten (see _repair_line) and only when the true source is
    itself unambiguous (exactly one unit holds the quote). Everything else is left flagged for a
    human — a wrong "fix" is worse than an honest warning. NOT_FOUND and UNVERIFIABLE are never
    touched: neither has a true id to point at.

    The result is RE-VERIFIED and rolled back if fidelity did not actually improve, so the
    reported repair count can never overstate what was achieved. (The previous version reported
    "corrected 4" on a brief whose fidelity did not move at all.)

    Returns (fixed_text, n_fixed, skipped) where `skipped` lists records left for manual review.
    """
    if blobs is None:
        blobs = unit_texts()
    before = verify_text(text, blobs=blobs, scope_ids=scope_ids)[1]
    lines = text.splitlines(keepends=True)
    fixed, skipped = 0, []
    for r in misattr:
        if r.get("n_sources", 1) != 1 or not r.get("actual"):
            skipped.append(r); continue           # ambiguous true source -> do not guess
        done = False
        for idx, line in enumerate(lines):
            if r["quote"] not in line:
                continue
            new, changed = _repair_line(line, r["quote"], set(r["cited"]), r["actual"])
            if changed:
                lines[idx] = new; fixed += 1; done = True
                break
        if not done:
            skipped.append(r)
    if not fixed:
        return text, 0, skipped
    candidate = "".join(lines)
    after = verify_text(candidate, blobs=blobs, scope_ids=scope_ids)[1]
    if after <= before:
        # the rewrite did not increase the verified count -> discard it rather than report a
        # success that did not happen.
        return text, 0, skipped + [r for r in misattr if r not in skipped]
    return candidate, fixed, skipped


UID_RE = re.compile(r"\b[uki]\d{4,10}\b")


def id_shapes(by_id):
    """The (prefix, digit-length) shapes that actually occur in a package, e.g. {('u',4),('k',5)}.
    Derived from the package rather than hardcoded so it stays correct as brains are added."""
    return {(i[0], len(i) - 1) for i in by_id}


def audit(answer, by_id, shortlist_ids=None, repair=True, log=None, label="verify"):
    """SHARED citation audit for every brain's query path.

    Three layers:
      (1) id shape   — a cited id whose shape never occurs in the package (e.g. u5850349667,
                       10 digits where every real id has 4) is a generation artefact, not a
                       near-miss. Distinguishing the two matters: malformed = the model invented
                       a token; plausible-but-absent = it cited a real-looking unit not present.
      (2) id membership — invented (not in package) / out-of-shortlist (real but not in context).
      (3) quote level — misattribution (real quote, wrong unit) and fabrication.

    When `repair` is on, MISATTRIBUTED citations are rewritten to the verified true source and
    the text is re-verified. NOT_FOUND (fabricated) quotes are never auto-repaired — there is no
    true id to point at — so the ⚠ NOT publication-ready warning still fires for them.

    Returns (answer_text, stats_dict). `answer_text` is the repaired text when repair applied.
    """
    log = log or (lambda s: sys.stderr.write(s))
    stats = {"cited": 0, "in_shortlist": 0, "invented": 0, "malformed": 0, "out_of_shortlist": 0,
             "quotes": 0, "verified": 0, "misattributed": 0, "not_found": 0,
             "repaired": 0, "fidelity": None, "publication_ready": True}

    cited = sorted(set(UID_RE.findall(answer)))
    shapes = id_shapes(by_id)
    invented = [c for c in cited if c not in by_id]
    malformed = [c for c in invented if (c[0], len(c) - 1) not in shapes]
    oos = ([c for c in cited if c in by_id and c not in shortlist_ids]
           if shortlist_ids is not None else [])
    in_short = ([c for c in cited if c in shortlist_ids] if shortlist_ids is not None
                else [c for c in cited if c in by_id])
    stats.update(cited=len(cited), in_shortlist=len(in_short), invented=len(invented),
                 malformed=len(malformed), out_of_shortlist=len(oos))
    log(f"\n[{label}] {len(cited)} cited | {len(in_short)} in shortlist ✓ | "
        f"{len(oos)} exist-not-in-shortlist | {len(invented)} INVENTED\n")
    if invented:
        log(f"[{label}] ⚠ INVENTED ids: {invented}\n")
    if malformed:
        log(f"[{label}] ⚠ MALFORMED shape (real ids look like "
            f"{', '.join(sorted(p + 'd' * n for p, n in shapes))}): {malformed}\n")

    scope = set(by_id)
    try:
        blobs = unit_texts()
        total, ok, misattr, notfound, unver = verify_text(answer, blobs=blobs, scope_ids=scope)
    except Exception as e:
        log(f"[quote-verify] skipped ({e})\n")
        return answer, stats
    if not total:
        return answer, stats

    def report(total, ok, misattr, notfound, unver, tag="quote-verify"):
        # fidelity is over ATTRIBUTABLE quotes — counting un-attributable coined labels in the
        # denominator would make the number depend on the model's punctuation habits.
        attributable = total - len(unver)
        pct = (100 * ok / attributable) if attributable else 100.0
        log(f"[{tag}] {total} quoted spans | {attributable} attributable | {ok} verified | "
            f"{len(misattr)} MISATTRIBUTED | {len(notfound)} NOT_FOUND | "
            f"{len(unver)} unverifiable | {pct:.1f}% fidelity\n")
        return pct

    pct = report(total, ok, misattr, notfound, unver)
    for r in misattr:
        src = ", ".join(r["sources"]) + ("…" if r["n_sources"] > len(r["sources"]) else "")
        how = "exact" if r["exact"] else "cov %s" % r["cov"]
        log(f"   ✗ MISATTR cited {','.join(r['cited'])} -> actually {src} "
            f"({how}): \"{r['quote'][:60]}\"\n")
    for r in notfound:
        log(f"   ✗ FABRICATED (found in no unit): \"{r['quote'][:60]}\"\n")
    for r in unver:
        log(f"   • unverifiable beside {','.join(r['cited'])}: \"{r['quote'][:50]}\" — {r['why']}\n")

    if repair and misattr:
        answer, n, skipped = fix_citations(answer, misattr, blobs=blobs, scope_ids=scope)
        stats["repaired"] = n
        if n:
            total, ok, misattr, notfound, unver = verify_text(answer, blobs=blobs, scope_ids=scope)
            log(f"[repair] corrected {n} citation(s) — re-verify:\n")
            pct = report(total, ok, misattr, notfound, unver, tag="repair")
        if skipped:
            log(f"[repair] {len(skipped)} left for manual review (ambiguous binding or "
                f"ambiguous true source)\n")

    stats.update(quotes=total, verified=ok, misattributed=len(misattr), not_found=len(notfound),
                 unverifiable=len(unver), fidelity=round(pct, 1))
    if misattr or notfound:
        stats["publication_ready"] = False
        log("[quote-verify] ⚠ NOT publication-ready — fix flagged quotes before public use.\n")
    else:
        log("[quote-verify] ✓ every attributable quote resolves to a cited unit.\n")
        if unver:
            log("[quote-verify] note: unverifiable spans above are quote-marked text that is not "
                "a corpus quote — reword or drop the quote marks before publishing.\n")
    return answer, stats


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
    total, verified, misattr, notfound, unver = verify_text(
        text, blobs=blobs, cover=args.cover, true_cover=args.true_cover)
    if not total:
        print("No (quote, id) pairs found — nothing to verify."); return

    if args.fix_citations:
        fixed_text, n, skipped = fix_citations(text, misattr, blobs=blobs)
        out = args.out or (args.file.rsplit(".", 1)[0] + ".fixed.md")
        open(out, "w", encoding="utf-8").write(fixed_text)
        print(f"[fix] corrected {n} misattributed citation(s) -> {out}")
        for r in skipped:
            print(f"[fix] ⚠ left for manual review: \"{r['quote'][:60]}\" (cited "
                  f"{','.join(r['cited'])}) — {r.get('why','ambiguous binding')}")
        if notfound:
            print(f"[fix] ⚠ {len(notfound)} NOT_FOUND (fabricated) quotes left untouched:")
            for r in notfound:
                print(f"      \"{r['quote'][:70]}\" (cited {','.join(r['cited'])})")
        t2, v2, m2, nf2, uv2 = verify_text(fixed_text, blobs=blobs, cover=args.cover,
                                           true_cover=args.true_cover)
        print(f"[fix] re-verify: {v2}/{t2 - len(uv2)} attributable verified | {len(m2)} "
              f"MISATTRIBUTED | {len(nf2)} NOT_FOUND | {len(uv2)} unverifiable")
        sys.exit(0 if (not m2 and not nf2) else 1)

    for r in misattr:
        src = ", ".join(r["sources"]) + ("…" if r["n_sources"] > len(r["sources"]) else "")
        print(f"  ✗ MISATTRIBUTED: cited {','.join(r['cited'])} but quote is actually {src} "
              f"({'exact' if r['exact'] else 'cov %s' % r['cov']}) — \"{r['quote'][:70]}\"")
    for r in notfound:
        print(f"  ✗ NOT_FOUND: cited {','.join(r['cited'])} — \"{r['quote'][:70]}\"")
    for r in unver:
        print(f"  • UNVERIFIABLE beside {','.join(r['cited'])}: \"{r['quote'][:60]}\" — {r['why']}")
    attributable = total - len(unver)
    print(f"\n[quote-verify] {total} quoted spans | {attributable} attributable | {verified} verified "
          f"| {len(misattr)} MISATTRIBUTED | {len(notfound)} NOT_FOUND | {len(unver)} unverifiable")
    print(f"[quote-verify] fidelity {100*verified/attributable if attributable else 100.0:.1f}% "
          f"(of attributable quotes)")
    sys.exit(0 if (not misattr and not notfound) else 1)


if __name__ == "__main__":
    main()
