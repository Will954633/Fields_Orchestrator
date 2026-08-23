#!/usr/bin/env python3
"""
Second remediation pass, 2026-08-23 articles RL cycle.

The first pass (`fix_editorial_rule5_20260823.py`) cleared single-valuation
figures, advice and abbreviated currency. Re-verifying afterwards surfaced a
second, larger class the first detector had not looked for:

  A. NAMED DATA SOURCES in reader-facing copy (8 listings). Public content must
     never name where we scrape from — "Domain's own valuation says $2,300,000",
     "$205,000 under Domain's estimate", "52 sqm Domain Won't Show". Memory
     `editorial_never_name_scrape_sources`: say "compiled from public sale
     records", never the source.

  B. STALE EDITORIAL. Every one of these was generated 2026-07-20/21 and has not
     been revalidated since, while asking prices moved and valuations were
     recomputed (bands measured 2026-08-08). 21 Misty Court publishes a
     comparable range of "$1,023,000 to $1,173,000" against a current band of
     $1,283,080-$1,606,741. This is the root defect; the Rule 5 breaches are
     downstream of it.

  C. VALUATIONS THE ENGINE NO LONGER STANDS BEHIND (4 listings). 6 Avocet, 87
     Honeyeater and 24 Tropicana now carry `directional_only: True` — the
     comparable-sales method suppressed its own answer for breaching the
     $1M-$2M design envelope. 185 Easthill has `confidence: not_available`. All
     four still publish an argument built on that withdrawn number, one of them
     quoting it to the dollar ("this site's reconciled model ($1,205,403...)").

TREATMENT differs by whether an accurate replacement can be written from the
document's CURRENT values:

  - REWRITES: the five listings that still have a live reconciled valuation and
    an empirical band. Copy is rebuilt from those figures.
  - UNPUBLISH: the four in class C. Their entire argument rests on a valuation we
    have withdrawn, so there is no honest patch — the copy has to be regenerated
    by the editorial pipeline against the current data. Setting
    `ai_analysis.status = 'needs_review'` stops it rendering (property.mjs and
    decision-feed-v3.mjs both gate on `status === 'published'`) without deleting
    anything. Reversible, and it errs toward withholding rather than publishing.

Idempotent. --dry-run writes nothing.
"""
import argparse
import sys

sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.env import load_env  # noqa: E402

load_env()
from shared.db import get_client  # noqa: E402

REWRITES = {
    ('robina', '41 Camberwell Circuit'): {
        # Named the source in headline AND meta_title; verdict published a
        # single valuation ("places it around $1,504,000" — now $1,602,751) and
        # closed with negotiation advice. Guide is currently "Offers Above
        # $1.649m", not "removed" as the July copy said.
        'headline': (
            "The listing says 190 sqm. The floor plan says 242. "
            "That's $98,000 hiding in plain sight."
        ),
        'meta_title': "41 Camberwell Cct — 52 sqm the Listing Doesn't Show | Fields",
        'verdict': (
            "A well-located, generously sized family home on 805 sqm with 242 "
            "sqm of internal living and four-car parking, offered for the first "
            "time since 1991. The listing's own floor area is recorded as 190 "
            "sqm; the floor plan measures 242 sqm. Guided at 'Offers Above "
            "$1,649,000', with comparable sales placing it between $1,407,215 "
            "and $1,798,287 — eight verified comparables, medium confidence, "
            "compiled from public sale records to August 2026. The kitchen and "
            "ensuite are the two rooms still unrenovated relative to the "
            "comparable set."
        ),
    },
    ('robina', '10 Glen Eagles Drive'): {
        # "$205,000 under Domain's estimate" — names the source, and is no
        # longer true: the ask is $1,695,000 against our $1,703,977 valuation.
        'headline': (
            "Five beds, a private suite, no stairs — and an ask that sits "
            "inside the comparable range"
        ),
        'meta_title': '10 Glen Eagles Dr — 5 Beds, No Stairs | Fields',
        'meta_description': (
            "Guided at $1,695,000. Comparable sales place it between $1,496,092 "
            "and $1,911,861 — here is what the five-bedroom, single-level "
            "layout is doing in that range."
        ),
        'verdict': (
            "Five bedrooms, a private guest suite and a single-level layout, "
            "guided at $1,695,000 Plus. Comparable sales place it between "
            "$1,496,092 and $1,911,861 — eight verified comparables, medium "
            "confidence, compiled from public sale records to August 2026. The "
            "ask sits inside that range rather than at either end of it."
        ),
    },
    ('robina', '96 Thorngate Drive'): {
        'verdict': (
            "Listed on 10 August 2026 by expressions of interest closing 5pm on "
            "31 August, 96 Thorngate Drive is a single-level, three-bedroom home "
            "on a large 809 sqm block backing directly onto bushland with no "
            "rear neighbours. It presents in move-in condition — a 7/10 finish "
            "across kitchen, bedrooms and bathrooms, cosmetically updated in the "
            "last five to ten years, with a spread of covered outdoor living. "
            "With no published guide, comparable sales place it between "
            "$1,171,028 and $1,496,463 — eight verified comparables, medium "
            "confidence, compiled from public sale records to August 2026. What "
            "is on offer is land, privacy and a single-level layout rather than "
            "a fourth bedroom or a top-tier fit-out."
        ),
    },
    ('robina', '7 Nardoo Street'): {
        # Named the source; also said "no price guide" when the listing now
        # reads "Best and Final Offer Before August...".
        'verdict': (
            "On the market since 10 August 2026 and now calling for best and "
            "final offers, this single-level, four-bedroom home with a pool, "
            "double garage and dedicated caravan cage has been held since 2008 "
            "and presents move-in ready. Comparable sales place it between "
            "$1,210,088 and $1,546,376 — eight verified comparables, medium "
            "confidence, compiled from public sale records to August 2026. The "
            "trade-off is size: at 162 sqm the floor sits just below the "
            "suburb's typical 172 sqm, though two separate air-conditioned "
            "living zones make it live larger than the number suggests."
        ),
    },
    ('varsity_lakes', '21 Misty Court'): {
        # The worst of the staleness: published comps of "$1,023,000 to
        # $1,173,000" against a current band of $1,283,080-$1,606,741, an asking
        # price that has since moved to $1,249,000, a named source, and two
        # pieces of advice ("room to negotiate", "before you commit").
        'verdict': (
            "Listed on 20 July 2026 and now guided at 'Offers Over $1,249,000', "
            "this single-level, three-bedroom, two-bathroom home on a 403 sqm "
            "corner block at the head of Misty Court presents well — a "
            "partially renovated kitchen, consistent 7/10 condition scores "
            "throughout, and walkable access to Varsity Lakes' parkland and "
            "lake. Comparable sales place it between $1,283,080 and $1,606,741 "
            "— eight verified comparables, low confidence, compiled from public "
            "sale records to August 2026. The one genuine trade-off is the "
            "proximity of a busier arterial road beyond the rear boundary."
        ),
    },
}

# Class C — the valuation the copy argues from has been withdrawn.
UNPUBLISH = [
    ('burleigh_waters', '6 Avocet Avenue',
     'directional_only: valuation suppressed (above design envelope); copy '
     'argues from a withdrawn estimate and names a data source'),
    ('burleigh_waters', '87 Honeyeater Drive',
     'directional_only: valuation suppressed; copy states the home sits "on" '
     'that withdrawn valuation, names a data source, and predicts scarcity'),
    ('burleigh_waters', '24 Tropicana Circuit',
     'directional_only: valuation suppressed; copy presents a converged range '
     'built partly on a named third-party model'),
    ('robina', '185 Easthill Drive',
     'confidence: not_available — copy quotes a reconciled model figure to the '
     'dollar ($1,205,403) that the document no longer holds'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    db = get_client()['Gold_Coast']
    n_rewritten = n_fields = n_unpublished = 0

    for (coll, prefix), fields in REWRITES.items():
        doc = db[coll].find_one(
            {'address': {'$regex': '^' + prefix}, 'listing_status': 'for_sale'},
            {'address': 1, 'ai_analysis': 1},
        )
        if not doc:
            print(f'MISS (rewrite): {coll} / {prefix}')
            continue
        ai = doc.get('ai_analysis') or {}
        updates = {f'ai_analysis.{f}': v for f, v in fields.items()
                   if ai.get(f) != v}
        if not updates:
            continue
        n_rewritten += 1
        n_fields += len(updates)
        print(f'\nREWRITE  {doc["address"]}')
        for k in updates:
            print(f'   {k}')
        if not args.dry_run:
            updates['ai_analysis.rule5_remediated_at'] = '2026-08-23'
            db[coll].update_one({'_id': doc['_id']}, {'$set': updates})

    for coll, prefix, reason in UNPUBLISH:
        doc = db[coll].find_one(
            {'address': {'$regex': '^' + prefix}, 'listing_status': 'for_sale'},
            {'address': 1, 'ai_analysis.status': 1},
        )
        if not doc:
            print(f'MISS (unpublish): {coll} / {prefix}')
            continue
        if (doc.get('ai_analysis') or {}).get('status') != 'published':
            continue
        n_unpublished += 1
        print(f'\nUNPUBLISH  {doc["address"]}\n   {reason}')
        if not args.dry_run:
            db[coll].update_one({'_id': doc['_id']}, {'$set': {
                'ai_analysis.status': 'needs_review',
                'ai_analysis.unpublished_at': '2026-08-23',
                'ai_analysis.unpublished_reason': reason,
            }})

    verb = 'would apply' if args.dry_run else 'applied'
    print(f'\n{verb}: {n_fields} fields across {n_rewritten} rewritten listings; '
          f'{n_unpublished} unpublished')

    # Rule 7b: zero on the first run would mean the query is wrong, not that the
    # corpus is clean — these breaches were measured before this file was written.
    if args.dry_run and n_rewritten == 0 and n_unpublished == 0:
        print('NOTE: zero matches — verify the address queries before '
              'concluding the corpus is clean.')


if __name__ == '__main__':
    main()
