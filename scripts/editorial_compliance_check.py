#!/usr/bin/env python3
"""
Standing compliance + staleness check over LIVE published property editorial.

Why this exists
---------------
On 2026-08-23 the articles RL cycle, acting on a directive from the seo domain,
found the live corpus carrying: single-property valuation figures (two of them in
headline fields), buyer advice, 43 abbreviated currency figures, our own data
sources named in reader-facing copy, and — the root defect — editorial generated
2026-07-20/21 that had never been revalidated. Prices had moved and valuations
had been recomputed underneath it, so four listings were publishing an argument
built on a valuation the engine had since SUPPRESSED or dropped.

Every one of those was invisible because nothing ever re-read published copy. A
generate-time gate cannot catch them: the copy was compliant and true when
written, and drifted afterwards. This runs against what is live NOW.

Rule 7b — the assertion
-----------------------
A run that scans zero documents is a failure, not a clean corpus: it means the
query is wrong (Rule 8 — a zero is a fact about the field name you typed). The
job raises on that. Breaches found are reported in `beat.metrics`, not raised,
so the heartbeat distinguishes "the checker broke" from "the corpus has drift".

Usage
-----
    python3 scripts/editorial_compliance_check.py            # heartbeat run
    python3 scripts/editorial_compliance_check.py --verbose  # print every hit

Not yet on a schedule — adding cron lines is outside this domain's authority.
Suggested: daily, after the nightly pipeline recomputes valuations.
"""
import argparse
import re
import sys

sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.env import load_env  # noqa: E402

load_env()
from shared.db import get_client  # noqa: E402
from job_status import job_run  # noqa: E402

READER_FIELDS = ('headline', 'sub_headline', 'verdict', 'meta_title',
                 'meta_description')

# Comparable RANGES are what Rule 5 permits, so they are stripped before the
# single-figure test — otherwise every compliant range trips it.
MONEY_RANGE = re.compile(
    r'\$\d{1,3}(?:,\d{3})+\s*(?:–|—|-|to)\s*\$?\d{1,3}(?:,\d{3})+')
MONEY = re.compile(r'\$\d{1,3}(?:,\d{3})+')

# A figure presented as the CURRENT asking price. Deliberately excludes past
# tense ("asked", "was listed at") and sale language ("sold for"), which are
# historical facts and stay true as the guide moves.
ASKING_PRICE = re.compile(
    r'(?:asking|listed at|guided at|priced at|offers over|offers above|'
    r'offers from|price guide of|now at|is asking|asks)\D{0,12}'
    r'(\$\d{1,3}(?:,\d{3})+)', re.I)

# KNOWN PRECISION LIMIT — `stale_price` is a cue match, not a parse, so treat its
# count as an upper bound and read the hits before acting. Measured 2026-08-23:
# 6 flagged, 4 verified genuinely stale (6 Notre Dame Court, 26 Mojave Drive,
# 22 Bluejay Street, 31 Galeen Drive), 2 not — "Why Isn't 38 Roundelay Priced at
# $1,600,000?" is a counterfactual, and 1 Seahawk Crescent quotes the top of the
# current guide range. A negative lookbehind does not fix the first case because
# the negation sits several words back. Sentence-level parsing would; the cue
# match was kept because it is legible and the volume is reviewable by hand.

CHECKS = {
    # Rule 5: no single-property valuation stated as the home's worth.
    'single_valuation': re.compile(
        r"(reconciled valuation|fields valuation|fields[- ]assessed|"
        r"comps average|valuation model (?:places|says|that says)|our valuation|"
        r"valued at|this site's reconciled model)", re.I),
    # Rule 5: no advice — never tell the reader what to do.
    'advice': re.compile(
        r"(you should|buyers? should|worth putting forward|do not accept|"
        r"do not dismiss|room to negotiate|before you commit|"
        r"reasons to walk away|shouldn't expect|suggest room|"
        r"now is a good time|consider (?:offering|buying|selling))", re.I),
    # Rule 5: no predictions.
    'prediction': re.compile(
        r"(prices will|will (?:rise|fall|climb|drop)|is likely to sell|"
        r"expect(?:ed)? to (?:sell|fetch|achieve)|realistic expectation)", re.I),
    # memory: editorial_never_name_scrape_sources
    'named_source': re.compile(
        r'\b(Domain(?:\.com\.au)?|onthehouse|On The House|CoreLogic|'
        r'realestate\.com\.au|PropRadar|Pricefinder)\b'),
    # Rule 5 number format: $1,250,000 — never $1.25m.
    'abbreviated_currency': re.compile(
        r'\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[mMkK]\b'),
    'forbidden_word': re.compile(
        r'\b(stunning|nestled|boasting|rare opportunity|robust market)\b', re.I),
}


def check_text(field, text):
    """Return the list of check names this string trips."""
    hits = []
    stripped = MONEY_RANGE.sub('', text)
    for name, rx in CHECKS.items():
        if name == 'single_valuation':
            if rx.search(stripped) and MONEY.search(stripped):
                hits.append(name)
        elif rx.search(text):
            hits.append(name)
    return hits


def check_staleness(doc, ai):
    """
    The root defect: copy that was true when generated and no longer is.

    Two forms, both measurable against the document's own current state:
      - withdrawn_valuation: the copy argues from a reconciled valuation the
        engine has since suppressed (design-envelope breach) or dropped.
      - stale_price: the copy quotes a dollar asking price that is not the
        current one.
    """
    problems = []
    conf = (doc.get('valuation_data') or {}).get('confidence') or {}
    rv = conf.get('reconciled_valuation')
    suppressed = conf.get('directional_only') is True or rv is None

    body = ' '.join(str(ai.get(f) or '') for f in READER_FIELDS)

    if suppressed and CHECKS['single_valuation'].search(
            MONEY_RANGE.sub('', body)):
        problems.append('withdrawn_valuation')

    price = doc.get('price')
    if isinstance(price, str):
        current = set(MONEY.findall(price))
        # Only figures presented AS THE ASKING PRICE count. A first cut compared
        # every dollar figure in the copy against the current guide and reported
        # 17 stale listings; spot-checking four showed two were comparable SALE
        # prices ("Same Street Sold for $1,420,000") and one a correctly
        # past-tensed price ("Asked $3,200,000 in May"). Those are facts, not
        # drift. Requiring an asking-price cue immediately before the figure cuts
        # the false positives without needing to parse the sentence.
        asking = set(m.group(1) for m in ASKING_PRICE.finditer(body))
        if current and asking and not (current & asking):
            problems.append('stale_price')

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    with job_run('editorial_compliance_check', cadence_hours=24,
                 title='Editorial Rule 5 + staleness check') as beat:
        db = get_client()['Gold_Coast']
        scanned = 0
        findings = []

        for coll_name in db.list_collection_names():
            try:
                cur = db[coll_name].find(
                    {'listing_status': 'for_sale',
                     'ai_analysis.status': 'published'},
                    {'address': 1, 'ai_analysis': 1, 'price': 1,
                     'valuation_data.confidence': 1},
                )
            except Exception:
                continue

            for doc in cur:
                ai = doc.get('ai_analysis') or {}
                scanned += 1
                addr = doc.get('address')

                for field in READER_FIELDS:
                    text = ai.get(field)
                    if not isinstance(text, str):
                        continue
                    for name in check_text(field, text):
                        findings.append((addr, field, name, text[:120]))

                for name in check_staleness(doc, ai):
                    findings.append((addr, '-', name, ''))

                # Internal working fields must never reach a reader. property.mjs
                # strips them at serve time as of 2026-08-23; this asserts the
                # gate is still there rather than trusting it.
                internals = [k for k in ai if k.startswith('_')]
                if internals and args.verbose:
                    findings.append(
                        (addr, 'ai_analysis', 'internal_fields_present',
                         ','.join(sorted(internals))))

        by_check = {}
        for _, _, name, _ in findings:
            by_check[name] = by_check.get(name, 0) + 1

        beat.metrics = {'scanned': scanned, 'findings': len(findings),
                        **{f'check_{k}': v for k, v in by_check.items()}}
        beat.detail = (f'{scanned} live published editorials scanned, '
                       f'{len(findings)} findings: {by_check or "clean"}')

        print(beat.detail)
        if args.verbose:
            for addr, field, name, snippet in sorted(findings):
                print(f'  [{name}] {addr} :: {field}\n      {snippet}')

        # Rule 7b: the zero-output path. An empty scan means the query is wrong
        # — there are ~70 live published editorials at all times — not that
        # everything is compliant. Findings themselves are reported, not raised:
        # drift is expected and actionable, a broken query is neither.
        if scanned == 0:
            raise RuntimeError(
                'scanned 0 published editorials — the query is wrong, not the '
                'corpus clean (check listing_status / ai_analysis.status)')


if __name__ == '__main__':
    main()
