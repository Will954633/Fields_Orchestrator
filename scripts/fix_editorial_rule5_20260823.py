#!/usr/bin/env python3
"""
One-off remediation of live Rule 5 breaches in published property editorial.

Found 2026-08-23 by the articles RL cycle, acting on a directive from the seo
domain. Three separable classes, all on `ai_analysis` of live `for_sale`
listings whose editorial is `status: published` (i.e. rendered to readers):

  1. SINGLE-VALUATION FIGURES (4 listings)  — a lone $ figure stated as what the
     home is worth. CLAUDE.md Rule 5 permits comparable RANGES and gaps; it
     forbids the single figure, and forbids it absolutely in a headline.
     One of the four (7 Aruma Avenue) published a figure the valuation engine had
     itself SUPPRESSED for breaching the $1M-$2M design envelope — the document
     carries `reconciled_valuation: None, directional_only: True`.

  2. ADVICE (1 listing) — "a well-supported offer near or below the comparable
     cluster is worth putting forward" tells the reader what to do.

  3. ABBREVIATED CURRENCY (43 occurrences) — "$1.73M" where Rule 5 mandates
     "$1,730,000". Mechanical and deterministic, so converted rather than
     rewritten.

Class 1 and 2 are hand-written replacements, because the originals were also
STALE: all four editorials were generated 2026-07-20/21, and since then the
valuations were recomputed (bands measured 2026-08-08) and the asking prices
moved. Reusing the old prose with a patched number would have left the staleness
in place, so each replacement is rebuilt from the document's current values.

Idempotent: re-running finds nothing to change. --dry-run prints and writes
nothing.
"""
import argparse
import re
import sys

sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.env import load_env  # noqa: E402

load_env()
from shared.db import get_client  # noqa: E402

# ── Class 1 + 2: hand-written replacements ────────────────────────────────────
# Each keyed by (collection, address prefix). Values are the exact replacement
# text. Figures are taken from the document's CURRENT valuation_data.confidence
# and price fields, verified at authoring time on 2026-08-23.
REWRITES = {
    ('burleigh_waters', '7 Aruma Avenue'): {
        # RV suppressed (directional_only, above_design_ceiling); price now
        # $2,400,000, not the $2,470,000 the July copy quoted.
        'headline': (
            "Two Price Reductions Since June — and an Asking Price Above Where "
            "Our Comparable Model Can Answer"
        ),
        'sub_headline': (
            "At $2,400,000 this sits above the $2,000,000 ceiling of our "
            "comparable-sales method, so we publish no estimate for it. Here is "
            "what the comparable sales do show."
        ),
        'verdict': (
            "Listed at $2,400,000 after two price reductions since first "
            "appearing on 8 June 2026, this fully renovated four-bedroom, "
            "three-bathroom Burleigh Waters home sits above the $2,000,000 "
            "ceiling of our comparable-sales method. We publish no estimate for "
            "it: the method is a weighted mean of adjusted comparable sales, so "
            "it cannot exceed its priciest comparable and would understate a "
            "home at this level. The pool, single-level layout, dual ensuites "
            "and near-beach position are genuine strengths; the compact second "
            "bedroom, carport-only parking and a flood assessment requirement "
            "on the site are what sits on the other side. Compiled from public "
            "sale records to August 2026."
        ),
        'meta_title': '7 Aruma Ave — Above Our Model\'s Ceiling | Fields',
        'meta_description': (
            "At $2,400,000 after two reductions, this sits above the $2,000,000 "
            "ceiling of our comparable-sales method, so we publish no estimate. "
            "Here is what the comparable sales show."
        ),
    },
    ('burleigh_waters', '6 Moorhen Place'): {
        # Guide withdrawn 2026-08-01 — listing now reads "Contact Agent", so the
        # July headline's "$195K above asking" gap no longer has an asking price
        # to be above. Band: $1,696,124-$2,248,351 (low confidence, 8 verified).
        'headline': (
            "No Price Guide Since 1 August — Comparable Sales Land "
            "$1,696,124 to $2,248,351"
        ),
        'sub_headline': (
            "Eight verified sales nearby bracket this 778 sqm cul-de-sac block. "
            "No fourth bedroom and no pool; a gate into the school and a covered "
            "bar. Here is what the comparable sales show."
        ),
        'verdict': (
            "No fourth bedroom, no pool — just a fully-fenced 778 sqm "
            "cul-de-sac block, a gate to the school and a covered bar. That is "
            "the trade on the table. Listed on 16 July 2026 at $1,949,000, the "
            "guide was withdrawn on 1 August and the listing now reads 'Contact "
            "Agent'. Comparable sales in Burleigh Waters place it between "
            "$1,696,124 and $2,248,351 — eight verified comparables, low "
            "confidence, compiled from public sale records to August 2026."
        ),
        'meta_title': '6 Moorhen Pl — No Price Guide Since 1 Aug | Fields',
        'meta_description': (
            "The guide was withdrawn on 1 August. Eight verified sales nearby "
            "place this 778 sqm cul-de-sac block between $1,696,124 and "
            "$2,248,351."
        ),
    },
    ('robina', '89 Camberwell Circuit'): {
        # Verdict stated "a reconciled valuation of roughly $1,608,000"; the
        # stored figure is $1,624,668, so the published number was also wrong.
        # Now guided at $1,695,000 (from 2026-08-02), not "without a price guide".
        'headline': (
            "803 sqm on Camberwell Circuit — comparable sales say "
            "$1,426,458 to $1,822,876"
        ),
        'verdict': (
            "Relisted on 15 July 2026 and guided at $1,695,000 since 2 August, "
            "89 Camberwell Circuit backs a genuinely large 803 sqm block and a "
            "renovated master ensuite, with evidence from five or more "
            "Camberwell Circuit sales in the past year. Comparable sales place "
            "it between $1,426,458 and $1,822,876 — eight verified comparables, "
            "medium confidence, compiled from public sale records to August "
            "2026. The kitchen is the one room still waiting for its turn."
        ),
    },
    ('robina', '14 Elfin Street'): {
        # Published "a reconciled valuation of $1,726,668" — the figure the seo
        # domain found in the brand SERP. The stored valuation is now
        # $1,622,860, so the live number was $103,808 out of date. The closing
        # sentence was also advice, and "points to a motivated vendor" is an
        # adverse inference about the seller that the record does not support.
        'headline': (
            "Bought for $930,000 in 2023, Renovated, and Now "
            "'All Offers Considered'"
        ),
        'verdict': (
            "14 Elfin Street is a genuinely renovated four-bedroom, "
            "three-bathroom home in Robina Dales with a rare rear-parkland "
            "aspect, and four closely clustered comparable sales place it "
            "between $1,424,872 and $1,820,849 — eight verified comparables, "
            "medium confidence, compiled from public sale records to August "
            "2026. The listing has moved from 'Expressions of Interest' when it "
            "first appeared on 5 March 2026, to a $1,590,000-plus guide by 30 "
            "March, to 'all offers considered' by 8 May. That sequence is on "
            "the public record."
        ),
        # Was "$930K to $1.73M" — the $1.73M is the superseded valuation, so
        # expanding the abbreviation alone would have published a stale single
        # valuation figure in a more legible form.
        'meta_title': '14 Elfin St — Renovated, All Offers Considered',
        'meta_description': (
            "Four comparable sales cluster within $65,000 of each other, and the "
            "seller has since dropped the guide entirely. Comparable sales place "
            "it between $1,424,872 and $1,820,849."
        ),
    },
}

# ── Class 3: abbreviated currency ─────────────────────────────────────────────
# Note the comma group: "$1,100K" occurs live and a \d+ pattern misses it.
ABBR = re.compile(r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?([mMkK])\b')

# Reader-facing body copy only. `meta_title` / `meta_description` are the seo
# domain's to own (articles brief §1: "titles/metas coordinate with seo"), so
# this pass does not reformat 30-odd SERP titles unilaterally — a note goes to
# seo instead. The exception is the four hand-rewritten listings below, whose
# metas carry an actual Rule 5 valuation breach and cannot be left standing.
TEXT_FIELDS = ('headline', 'sub_headline', 'verdict')


def expand_abbr(text):
    """$1.73M -> $1,730,000 ; $930K -> $930,000. Rule 5 number format."""
    def sub(m):
        n = float(m.group(1).replace(',', ''))
        mult = 1_000_000 if m.group(2).lower() == 'm' else 1_000
        return '${:,}'.format(int(round(n * mult)))
    return ABBR.sub(sub, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    db = get_client()['Gold_Coast']
    changed_docs = 0
    changed_fields = 0

    for coll_name in db.list_collection_names():
        coll = db[coll_name]
        try:
            cur = coll.find(
                {'listing_status': 'for_sale', 'ai_analysis.status': 'published'},
                {'address': 1, 'ai_analysis': 1},
            )
        except Exception:
            continue

        for doc in cur:
            ai = doc.get('ai_analysis') or {}
            addr = doc.get('address') or ''
            updates = {}

            # Class 1 + 2 — hand-written replacements take precedence.
            for (c, prefix), fields in REWRITES.items():
                if c == coll_name and addr.startswith(prefix):
                    for f, new in fields.items():
                        if ai.get(f) != new:
                            updates[f'ai_analysis.{f}'] = new

            # Class 3 — abbreviated currency on everything not already replaced.
            for f in TEXT_FIELDS:
                key = f'ai_analysis.{f}'
                if key in updates:
                    continue
                old = ai.get(f)
                if not isinstance(old, str):
                    continue
                new = expand_abbr(old)
                if new != old:
                    updates[key] = new

            if not updates:
                continue

            changed_docs += 1
            changed_fields += len(updates)
            print(f'\n{coll_name} | {addr}')
            for k, v in updates.items():
                print(f'  {k}:')
                print(f'    - {str(ai.get(k.split(".", 1)[1]))[:150]}')
                print(f'    + {v[:150]}')

            if not args.dry_run:
                updates['ai_analysis.rule5_remediated_at'] = '2026-08-23'
                coll.update_one({'_id': doc['_id']}, {'$set': updates})

    verb = 'would change' if args.dry_run else 'changed'
    print(f'\n{verb}: {changed_fields} fields across {changed_docs} listings')

    # Rule 7b: this script exists because breaches were measured. Finding none on
    # the first run would mean the query is wrong, not that the corpus is clean.
    if changed_docs == 0 and args.dry_run:
        print('NOTE: zero matches — verify the query before concluding the '
              'corpus is clean.')


if __name__ == '__main__':
    main()
