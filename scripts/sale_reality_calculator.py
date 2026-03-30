#!/usr/bin/env python3
"""
Sale Reality Calculator
=======================
Estimates net proceeds for a property seller on the Gold Coast.

Given a property (by address or ID), produces:
  - Estimated sale range (from valuation data or comparable sales)
  - Agent commission range (2.0–2.5% typical QLD)
  - Marketing cost range ($3,000–$8,000)
  - Conveyancing / legal range ($1,500–$3,000)
  - Capital gains tax guidance (not advice — ranges only)
  - Net proceeds range
  - CTA to request a custom review

GUARDRAILS (per spec):
  - NO personalised tax advice language
  - Use ranges, not definitive tax liabilities
  - Disclaimer that final tax position depends on the seller's accountant

Collections:
  - Gold_Coast.<suburb>         (read — property + valuation_data)
  - system_monitor.sale_reality_submissions  (write — review requests)

Usage:
    # By address
    python3 scripts/sale_reality_calculator.py --address "15 Example St, Robina"

    # By property ID
    python3 scripts/sale_reality_calculator.py --property-id 660a1234abcd5678ef901234

    # Manual inputs (no DB lookup)
    python3 scripts/sale_reality_calculator.py --manual \
        --estimated-value 850000 \
        --purchase-price 620000 \
        --hold-years 5

    # Save a review request
    python3 scripts/sale_reality_calculator.py --request-review \
        --email seller@example.com --address "15 Example St, Robina"

    # Show recent submissions
    python3 scripts/sale_reality_calculator.py --stats

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from bson import ObjectId

sys.path.insert(0, '/home/fields/Fields_Orchestrator')

from shared.env import load_env
from shared.db import get_client, get_db
from shared.ru_guard import cosmos_retry

load_env()

DATABASE_NAME = 'Gold_Coast'
SYSTEM_DB = 'system_monitor'

# ---------------------------------------------------------------------------
# QLD Selling Cost Constants (2025-26 ranges)
# ---------------------------------------------------------------------------

# Agent commission: negotiable, typically 2.0%–2.5% on Gold Coast
COMMISSION_LOW_PCT = 0.020
COMMISSION_HIGH_PCT = 0.025

# Marketing/advertising: varies by campaign
MARKETING_LOW = 3_000
MARKETING_HIGH = 8_000

# Conveyancing / solicitor
CONVEYANCING_LOW = 1_500
CONVEYANCING_HIGH = 3_000

# Auctioneer fee (if applicable)
AUCTIONEER_FEE = 800

# Miscellaneous (building/pest reports, styling, etc.)
MISC_LOW = 500
MISC_HIGH = 2_000

# CGT discount for assets held > 12 months (individual)
CGT_DISCOUNT_12M = 0.50

# Marginal tax rate brackets (2025-26 indicative — NOT financial advice)
TAX_BRACKETS = [
    (18_200, 0.0),
    (45_000, 0.19),
    (120_000, 0.325),
    (180_000, 0.37),
    (float('inf'), 0.45),
]

DISCLAIMER = (
    "This estimate is for general guidance only and does not constitute financial, "
    "tax, or legal advice. Your actual tax position depends on your individual "
    "circumstances. Consult a qualified accountant or tax advisor before making "
    "any decisions based on these figures."
)


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def calculate_sale_reality(
    estimated_value_low: float,
    estimated_value_high: float,
    purchase_price: float = None,
    hold_years: float = None,
    ownership_type: str = 'individual',
) -> dict:
    """
    Calculate estimated net proceeds from selling.

    Returns a dict with all ranges and guidance.
    """
    mid_value = (estimated_value_low + estimated_value_high) / 2

    # --- Selling costs ---
    commission_low = estimated_value_low * COMMISSION_LOW_PCT
    commission_high = estimated_value_high * COMMISSION_HIGH_PCT

    total_costs_low = commission_low + MARKETING_LOW + CONVEYANCING_LOW + MISC_LOW
    total_costs_high = commission_high + MARKETING_HIGH + CONVEYANCING_HIGH + MISC_HIGH

    # --- Net before tax ---
    net_before_tax_low = estimated_value_low - total_costs_high  # worst case
    net_before_tax_high = estimated_value_high - total_costs_low  # best case

    # --- Capital gains guidance ---
    cgt_guidance = None
    if purchase_price and purchase_price > 0:
        gain_low = estimated_value_low - purchase_price
        gain_high = estimated_value_high - purchase_price

        if gain_high <= 0:
            cgt_guidance = {
                'scenario': 'no_gain',
                'message': 'Based on these estimates, there may be no capital gain.',
                'estimated_gain_range': {'low': gain_low, 'high': gain_high},
            }
        else:
            # 50% CGT discount if held > 12 months (individual)
            discount_eligible = hold_years and hold_years > 1 and ownership_type == 'individual'

            taxable_gain_low = max(0, gain_low)
            taxable_gain_high = max(0, gain_high)

            if discount_eligible:
                taxable_gain_low *= (1 - CGT_DISCOUNT_12M)
                taxable_gain_high *= (1 - CGT_DISCOUNT_12M)

            # Indicative tax (at marginal rates — simplified, not a tax return)
            tax_low = _indicative_tax_on_gain(taxable_gain_low)
            tax_high = _indicative_tax_on_gain(taxable_gain_high)

            cgt_guidance = {
                'scenario': 'gain',
                'estimated_gain_range': {'low': gain_low, 'high': gain_high},
                'discount_eligible': discount_eligible,
                'discount_reason': '50% CGT discount (asset held > 12 months, individual)' if discount_eligible else None,
                'taxable_gain_range': {'low': taxable_gain_low, 'high': taxable_gain_high},
                'indicative_tax_range': {'low': tax_low, 'high': tax_high},
                'message': (
                    f"Estimated capital gain: ${gain_low:,.0f}–${gain_high:,.0f}. "
                    + (f"With 50% CGT discount, taxable portion: ${taxable_gain_low:,.0f}–${taxable_gain_high:,.0f}. "
                       if discount_eligible else "")
                    + f"Indicative tax (at marginal rates): ${tax_low:,.0f}–${tax_high:,.0f}. "
                    + "This is a rough guide — your accountant will determine the actual liability."
                ),
            }

    # --- Net after estimated tax ---
    tax_low = cgt_guidance['indicative_tax_range']['low'] if cgt_guidance and 'indicative_tax_range' in cgt_guidance else 0
    tax_high = cgt_guidance['indicative_tax_range']['high'] if cgt_guidance and 'indicative_tax_range' in cgt_guidance else 0

    net_after_tax_low = net_before_tax_low - tax_high  # worst case
    net_after_tax_high = net_before_tax_high - tax_low  # best case

    return {
        'estimated_sale_range': {
            'low': estimated_value_low,
            'high': estimated_value_high,
        },
        'selling_costs': {
            'commission': {
                'low': commission_low,
                'high': commission_high,
                'rate': f"{COMMISSION_LOW_PCT*100:.1f}%–{COMMISSION_HIGH_PCT*100:.1f}%",
            },
            'marketing': {'low': MARKETING_LOW, 'high': MARKETING_HIGH},
            'conveyancing': {'low': CONVEYANCING_LOW, 'high': CONVEYANCING_HIGH},
            'miscellaneous': {'low': MISC_LOW, 'high': MISC_HIGH},
            'total': {'low': total_costs_low, 'high': total_costs_high},
        },
        'net_before_tax': {
            'low': net_before_tax_low,
            'high': net_before_tax_high,
        },
        'cgt_guidance': cgt_guidance,
        'net_after_estimated_tax': {
            'low': net_after_tax_low,
            'high': net_after_tax_high,
        },
        'disclaimer': DISCLAIMER,
        'computed_at': datetime.utcnow().isoformat(),
    }


def _indicative_tax_on_gain(taxable_gain):
    """
    Simplified marginal tax on a capital gain.
    Assumes the gain is the ONLY income (worst-case bracket estimate).
    NOT financial advice.
    """
    if taxable_gain <= 0:
        return 0

    tax = 0
    remaining = taxable_gain
    prev_threshold = 0

    for threshold, rate in TAX_BRACKETS:
        band = min(remaining, threshold - prev_threshold)
        if band <= 0:
            break
        tax += band * rate
        remaining -= band
        prev_threshold = threshold

    return round(tax)


# ---------------------------------------------------------------------------
# Property lookup
# ---------------------------------------------------------------------------

def lookup_property(client, address=None, property_id=None):
    """Find a property and extract valuation + sale history for the calculator."""
    gc = client[DATABASE_NAME]

    doc = None
    coll_name = None

    if property_id:
        pid = ObjectId(property_id) if isinstance(property_id, str) else property_id
        for cn in gc.list_collection_names():
            if cn.startswith('system.') or cn in {
                'suburb_median_prices', 'suburb_statistics',
                'change_detection_snapshots', 'address_search_index'
            }:
                continue
            doc = gc[cn].find_one({'_id': pid})
            if doc:
                coll_name = cn
                break

    elif address:
        import re
        pattern = re.compile(re.escape(address), re.IGNORECASE)
        for cn in gc.list_collection_names():
            if cn.startswith('system.') or cn in {
                'suburb_median_prices', 'suburb_statistics',
                'change_detection_snapshots', 'address_search_index'
            }:
                continue
            doc = gc[cn].find_one({
                '$or': [
                    {'complete_address': pattern},
                    {'address': pattern},
                ]
            })
            if doc:
                coll_name = cn
                break

    if not doc:
        return None

    # Extract valuation
    val_data = doc.get('valuation_data', {})
    confidence = val_data.get('confidence', {})
    reconciled = confidence.get('reconciled_valuation')
    val_range = confidence.get('range', {})

    # Extract sale history (for CGT inputs)
    timeline = (doc.get('scraped_data') or {}).get('property_timeline', [])
    purchase_price = None
    hold_years = None

    if timeline:
        # Find the most recent purchase (is_sold = true entries)
        sold_entries = [e for e in timeline if e.get('is_sold')]
        if len(sold_entries) >= 1:
            # Current owner bought at the last sold entry
            last_sale = sold_entries[-1]
            purchase_price = last_sale.get('price')
            sale_date_str = last_sale.get('date')
            if sale_date_str:
                try:
                    from dateutil.parser import parse as parse_date
                    sale_date = parse_date(sale_date_str)
                    hold_years = (datetime.now() - sale_date).days / 365.25
                except Exception:
                    pass

    return {
        'property_id': str(doc['_id']),
        'address': doc.get('complete_address') or doc.get('address', 'Unknown'),
        'suburb': coll_name,
        'listing_status': doc.get('listing_status'),
        'current_price': doc.get('price'),
        'reconciled_valuation': reconciled,
        'valuation_range_low': val_range.get('low'),
        'valuation_range_high': val_range.get('high'),
        'purchase_price': purchase_price,
        'hold_years': round(hold_years, 1) if hold_years else None,
    }


# ---------------------------------------------------------------------------
# Review request
# ---------------------------------------------------------------------------

def save_review_request(client, email, address, result=None, notes=None):
    """Save a 'Request a custom sale reality review' submission."""
    sm = client[SYSTEM_DB]
    coll = sm['sale_reality_submissions']

    doc = {
        'email': email,
        'address': address,
        'result_snapshot': result,
        'notes': notes,
        'status': 'new',
        'created_at': datetime.utcnow(),
    }

    cosmos_retry(lambda: coll.insert_one(doc), "save_review_request")
    print(f"Review request saved: {email} → {address}")
    return str(doc['_id'])


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_result(result, prop_info=None):
    """Format the calculation result for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("SALE REALITY ESTIMATE")
    lines.append("=" * 60)

    if prop_info:
        lines.append(f"Property: {prop_info.get('address', 'N/A')}")
        lines.append(f"Suburb:   {(prop_info.get('suburb', '')).replace('_', ' ').title()}")
        if prop_info.get('current_price'):
            lines.append(f"Listed:   {prop_info['current_price']}")
        lines.append("")

    sr = result['estimated_sale_range']
    lines.append(f"Estimated sale range:   ${sr['low']:>12,.0f} – ${sr['high']:>12,.0f}")
    lines.append("")

    sc = result['selling_costs']
    lines.append("Selling costs:")
    lines.append(f"  Agent commission ({sc['commission']['rate']}): "
                 f"${sc['commission']['low']:>10,.0f} – ${sc['commission']['high']:>10,.0f}")
    lines.append(f"  Marketing:         ${sc['marketing']['low']:>10,.0f} – ${sc['marketing']['high']:>10,.0f}")
    lines.append(f"  Conveyancing:      ${sc['conveyancing']['low']:>10,.0f} – ${sc['conveyancing']['high']:>10,.0f}")
    lines.append(f"  Miscellaneous:     ${sc['miscellaneous']['low']:>10,.0f} – ${sc['miscellaneous']['high']:>10,.0f}")
    lines.append(f"  ─────────────────────────────────────────────")
    lines.append(f"  Total costs:       ${sc['total']['low']:>10,.0f} – ${sc['total']['high']:>10,.0f}")
    lines.append("")

    nb = result['net_before_tax']
    lines.append(f"Net before tax:        ${nb['low']:>12,.0f} – ${nb['high']:>12,.0f}")
    lines.append("")

    cgt = result.get('cgt_guidance')
    if cgt:
        lines.append("Capital gains guidance:")
        lines.append(f"  {cgt['message']}")
        lines.append("")

    na = result['net_after_estimated_tax']
    lines.append(f"Net after est. tax:    ${na['low']:>12,.0f} – ${na['high']:>12,.0f}")
    lines.append("")
    lines.append("─" * 60)
    lines.append(result['disclaimer'])
    lines.append("─" * 60)

    return "\n".join(lines)


def show_stats(client):
    """Show recent sale reality submissions."""
    sm = client[SYSTEM_DB]
    coll = sm['sale_reality_submissions']
    total = coll.count_documents({})
    new = coll.count_documents({'status': 'new'})
    print(f"Sale reality submissions: {total} total ({new} new)")

    recent = list(coll.find().sort('created_at', -1).limit(5))
    if recent:
        print("\nRecent:")
        for r in recent:
            print(f"  {r.get('created_at', '?')} | {r.get('email')} | {r.get('address')} | {r.get('status')}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Sale Reality Calculator')
    parser.add_argument('--address', type=str, help='Property address to look up')
    parser.add_argument('--property-id', type=str, help='Property ObjectId')
    parser.add_argument('--manual', action='store_true', help='Use manual inputs (no DB lookup)')
    parser.add_argument('--estimated-value', type=float, help='Estimated sale price (manual mode)')
    parser.add_argument('--purchase-price', type=float, help='Original purchase price')
    parser.add_argument('--hold-years', type=float, help='Years held')
    parser.add_argument('--ownership-type', type=str, default='individual',
                        choices=['individual', 'company', 'trust'],
                        help='Ownership type (default: individual)')
    parser.add_argument('--request-review', action='store_true',
                        help='Save a custom review request')
    parser.add_argument('--email', type=str, help='Email for review request')
    parser.add_argument('--notes', type=str, help='Notes for review request')
    parser.add_argument('--stats', action='store_true', help='Show submission stats')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()
    client = get_client()

    if args.stats:
        show_stats(client)
        return

    prop_info = None

    if args.manual:
        if not args.estimated_value:
            parser.error("--manual requires --estimated-value")
        # Use ±5% range around the estimate
        val = args.estimated_value
        est_low = val * 0.95
        est_high = val * 1.05
    elif args.address or args.property_id:
        prop_info = lookup_property(client, address=args.address, property_id=args.property_id)
        if not prop_info:
            print(f"Property not found: {args.address or args.property_id}")
            sys.exit(1)

        # Use valuation range if available, else current price ±5%
        if prop_info.get('valuation_range_low') and prop_info.get('valuation_range_high'):
            est_low = prop_info['valuation_range_low']
            est_high = prop_info['valuation_range_high']
        elif prop_info.get('reconciled_valuation'):
            v = prop_info['reconciled_valuation']
            est_low = v * 0.95
            est_high = v * 1.05
        else:
            print("No valuation data available for this property.")
            print("Use --manual --estimated-value to provide your own estimate.")
            sys.exit(1)

        # Override purchase price / hold years from args if given
        if not args.purchase_price and prop_info.get('purchase_price'):
            args.purchase_price = prop_info['purchase_price']
        if not args.hold_years and prop_info.get('hold_years'):
            args.hold_years = prop_info['hold_years']
    else:
        parser.error("Provide --address, --property-id, or --manual")
        return

    result = calculate_sale_reality(
        estimated_value_low=est_low,
        estimated_value_high=est_high,
        purchase_price=args.purchase_price,
        hold_years=args.hold_years,
        ownership_type=args.ownership_type,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_result(result, prop_info))

    # Save review request if asked
    if args.request_review:
        if not args.email:
            parser.error("--request-review requires --email")
        addr = args.address or (prop_info or {}).get('address', 'Manual estimate')
        save_review_request(client, args.email, addr, result=result, notes=args.notes)


if __name__ == '__main__':
    main()
