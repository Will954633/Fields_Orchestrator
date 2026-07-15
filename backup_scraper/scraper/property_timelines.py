"""
property_timelines.py — Build property event timelines keyed on verified_address.

Logic:
- Scan all JSON files across all suburbs
- Group events by verified_address (the actual page address, not the GIS search address)
- For each property, sort events by discovered_at
- Compute current_status = highest-priority status seen
- Output summary + optionally full timeline JSON

STATUS_PRIORITY: sold > leased > for_sale > unknown > page_unavailable > None
"""
import json, glob, re, argparse
from collections import defaultdict
from datetime import datetime

STATUS_PRIORITY = {
    'sold': 5,
    'leased': 4,
    'for_sale': 3,
    'unknown': 2,
    'page_unavailable': 1,
    None: 0,
}

BASE = '/home/projects/scraper/discovered_urls'
SUBURBS = ['robina', 'varsity_lakes', 'burleigh_waters']

def normalise_address(addr: str) -> str:
    """Normalise to uppercase, strip trailing suburb/state/postcode variants for grouping."""
    if not addr:
        return ''
    # Uppercase, strip double spaces
    a = re.sub(r'\s+', ' ', addr.strip().upper())
    # Strip trailing ", QLD 4226" / "QLD 4226" / "ROBINA QLD 4226" etc
    a = re.sub(r',?\s*(ROBINA|VARSITY LAKES|BURLEIGH WATERS)?,?\s*QLD\s*\d{4}\s*$', '', a).strip()
    a = re.sub(r',?\s*QLD\s*\d{4}\s*$', '', a).strip()
    return a

def parse_dt(s):
    if not s:
        return datetime.min
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(s)[:26], fmt)
        except:
            pass
    return datetime.min

def load_all_events():
    """Load all JSON files and return list of event dicts."""
    events = []
    for suburb in SUBURBS:
        for fpath in glob.glob(f'{BASE}/{suburb}/*.json'):
            try:
                doc = json.load(open(fpath))
            except:
                continue

            di = doc.get('discovery_info') or {}
            ed = doc.get('extracted_data') or {}

            verified_addr = di.get('verified_address') or di.get('address') or ''
            gis_addr      = di.get('address') or ''
            address_match = di.get('address_match', True)
            url           = di.get('new_url') or ''
            discovered_at = di.get('discovered_at') or ''
            agency        = di.get('agency_keyword') or ''

            status     = ed.get('listing_status')
            sale_price = ed.get('sale_price')
            sold_date  = ed.get('sold_date')
            bedrooms   = ed.get('bedrooms')
            bathrooms  = ed.get('bathrooms')
            prop_type  = ed.get('property_type')
            images     = ed.get('property_images') or []

            norm_addr = normalise_address(verified_addr)
            if not norm_addr:
                norm_addr = normalise_address(gis_addr)

            events.append({
                'verified_address': verified_addr,
                'norm_address':     norm_addr,
                'gis_address':      gis_addr,
                'address_match':    address_match,
                'suburb':           suburb,
                'url':              url,
                'agency':           agency,
                'discovered_at':    discovered_at,
                'dt':               parse_dt(discovered_at),
                'listing_status':   status,
                'sale_price':       sale_price,
                'sold_date':        sold_date,
                'bedrooms':         bedrooms,
                'bathrooms':        bathrooms,
                'property_type':    prop_type,
                'image_count':      len(images),
                'file':             fpath,
            })
    return events

def build_timelines(events):
    """Group events by normalised verified_address → sorted timeline."""
    by_addr = defaultdict(list)
    for e in events:
        by_addr[e['norm_address']].append(e)

    timelines = {}
    for addr, evts in by_addr.items():
        # Sort by discovered_at ascending
        evts_sorted = sorted(evts, key=lambda x: x['dt'])

        # Current status = highest priority status across all events
        current_status = max(
            (e['listing_status'] for e in evts_sorted),
            key=lambda s: STATUS_PRIORITY.get(s, 0),
            default=None,
        )

        # Best sale price (from a sold event)
        sale_price = next(
            (e['sale_price'] for e in evts_sorted
             if e['listing_status'] == 'sold' and e['sale_price']),
            None
        )

        # Bedrooms/bathrooms from most recent event that has them
        bedrooms = next(
            (e['bedrooms'] for e in reversed(evts_sorted) if e['bedrooms']),
            None
        )
        bathrooms = next(
            (e['bathrooms'] for e in reversed(evts_sorted) if e['bathrooms']),
            None
        )
        prop_type = next(
            (e['property_type'] for e in reversed(evts_sorted) if e['property_type']),
            None
        )
        image_count = max((e['image_count'] for e in evts_sorted), default=0)

        # Address match quality
        n_match = sum(1 for e in evts_sorted if e['address_match'])
        n_total = len(evts_sorted)

        timelines[addr] = {
            'verified_address':  addr,
            'display_address':   evts_sorted[-1]['verified_address'],  # latest
            'suburb':            evts_sorted[-1]['suburb'],
            'current_status':    current_status,
            'event_count':       n_total,
            'address_match_pct': round(n_match / n_total * 100) if n_total else 0,
            'sale_price':        sale_price,
            'bedrooms':          bedrooms,
            'bathrooms':         bathrooms,
            'property_type':     prop_type,
            'image_count':       image_count,
            'first_seen':        evts_sorted[0]['discovered_at'],
            'last_seen':         evts_sorted[-1]['discovered_at'],
            'events':            evts_sorted,
        }
    return timelines

def print_summary(timelines, suburb_filter=None):
    from collections import Counter
    tl = list(timelines.values())
    if suburb_filter:
        tl = [t for t in tl if suburb_filter.lower().replace(' ','_') in t['suburb']]

    status_counts = Counter(t['current_status'] for t in tl)
    print(f"\n{'='*60}")
    print(f"PROPERTY TIMELINES — {suburb_filter or 'ALL SUBURBS'}")
    print(f"{'='*60}")
    print(f"Unique properties (by verified_address): {len(tl)}")
    print(f"\nCurrent status breakdown:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        pct = count / len(tl) * 100 if tl else 0
        print(f"  {count:5d} ({pct:5.1f}%)  {status}")

    # For-sale properties (currently active)
    for_sale = [t for t in tl if t['current_status'] == 'for_sale']
    print(f"\nCurrently FOR SALE: {len(for_sale)}")
    for t in sorted(for_sale, key=lambda x: x['last_seen'], reverse=True)[:10]:
        beds = f"{t['bedrooms']}bd" if t['bedrooms'] else "?bd"
        baths = f"{t['bathrooms']}ba" if t['bathrooms'] else "?ba"
        print(f"  {t['display_address'][:45]:<45} {beds} {baths}  imgs={t['image_count']}  seen={t['last_seen'][:10]}")

    # Sold properties with prices
    sold = [t for t in tl if t['current_status'] == 'sold' and t['sale_price']]
    print(f"\nSOLD with price data: {len(sold)} of {status_counts.get('sold',0)}")

    # Properties with rich timelines (3+ events)
    rich = [t for t in tl if t['event_count'] >= 3]
    print(f"\nProperties with 3+ events (timeline-ready): {len(rich)}")
    if rich:
        # Show a for_sale → sold transition example
        transitions = [t for t in rich if t['current_status'] == 'sold']
        if transitions:
            ex = transitions[0]
            print(f"\n  Example timeline: {ex['display_address']}")
            for e in ex['events']:
                print(f"    {e['discovered_at'][:16]}  {str(e['listing_status']):<15}  {e['url'][:60]}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suburb', default=None, help='Filter by suburb')
    parser.add_argument('--save', default=None, help='Save full timeline JSON to file')
    parser.add_argument('--for-sale-only', action='store_true')
    args = parser.parse_args()

    print("Loading all events...")
    events = load_all_events()
    print(f"  {len(events)} total event records across all suburbs")

    print("Building timelines...")
    timelines = build_timelines(events)

    print_summary(timelines, suburb_filter=args.suburb)

    if args.save:
        # Save without the per-event file paths for cleaner JSON
        out = {}
        for k, v in timelines.items():
            row = {kk: vv for kk, vv in v.items() if kk != 'events'}
            row['events'] = [
                {ek: ev for ek, ev in e.items() if ek not in ('dt', 'file', 'norm_address')}
                for e in v['events']
            ]
            out[k] = row
        with open(args.save, 'w') as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nTimeline JSON saved to {args.save}")

if __name__ == '__main__':
    main()
