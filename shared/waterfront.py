#!/usr/bin/env python3
"""
Canonical waterfront detection — single source of truth for the whole platform.

WHY THIS EXISTS (strategic, 2026-07-26)
────────────────────────────────────────────────────────────────────────────
Waterfront property is deliberately treated as OUT OF SCOPE for Fields right now.
Two reasons, both from Will:

  1. Waterfront is its own market that needs a dedicated arm of the business.
     Pricing a canal/lake/riverfront home well requires genuine expertise in that
     segment (aspect, water depth, navigability, frontage width, flood/erosion,
     body-corp canal levies, jetty/pontoon value). We do not have that yet, and a
     confident-but-wrong take on a waterfront home damages trust more than saying
     nothing.

  2. Our valuation system is not ready for it. The comparable-sales model compares a
     subject only to same-cohort sales, but a waterfront home priced against dry
     (no-frontage) blocks produces a materially wrong range — which is exactly the
     failure that surfaced on 46 Mornington Terrace, Robina (a lakefront home valued
     off dry comps). Until we have run waterfront analysis across the whole southern
     Gold Coast waterfront stock and can guarantee waterfront-only comp cohorts, we
     do not publish valuations or editorial for these homes.

Consequences of `detect_waterfront(doc)['is_waterfront'] == True`:
  • Editorial generators SKIP the property (no ai_analysis produced/published).
  • Any already-published editorial is suppressed (status → 'suppressed_waterfront').
  • The property page ships <meta robots="noindex"> and is dropped from the sitemap
    (for-sale AND sold), so it does not enter Google's index.
  • The valuation figure/range is withheld on the property page.
  • The valuation comp filter keeps waterfront subjects and waterfront comps together
    (it already did — see precompute_valuations.py:is_waterfront), so a correct flag
    also stops waterfront homes leaking in as dry comps.

This module is the ONE place that decides "is this waterfront?". Both the orchestrator
(editorial gate, backfill, removal sweep) and — via the persisted `is_waterfront`
boolean it writes — the website (utils.mjs isWaterfront honours doc.is_waterfront)
key off it. When we ARE ready for waterfront, this is where the policy is unwound.

DETECTION SIGNALS (any one is sufficient)
────────────────────────────────────────────────────────────────────────────
  0. Explicit flags already on the doc: is_waterfront / waterfront_premium_eligible.
  1. GPT-4 Vision photo analysis: property_valuation_data.outdoor.water_views == True.
  2. Listing text: a waterfront keyword in description / agents_description.
  3. Satellite analysis (the signal that was previously ignored, causing the
     46 Mornington miss): the vision pass's structured adjacency/amenity fields —
       • categories.adjacency.backs_onto contains a water type, OR
       • categories.amenity_premiums.water_proximity is an explicit *frontage* value.
     Guarded by pin_confirmed (an EXPLICIT False means the vision pass could not
     confirm which lot is the subject, so its adjacency call may describe the wider
     frame, not this lot — same guard detect_golf_course_backing uses). A MISSING
     pin_confirmed key (older captures) is treated as proceed-as-before.

IMPORTANT — water_proximity is matched against an explicit allowlist, NOT a substring.
A naive `'front' in water_proximity` test wrongly flags the literal value
"not_waterfront" (it contains "front"). "3 Massachusetts Court, Varsity Lakes" is a
real dry home whose satellite water_proximity is exactly "not_waterfront"; the
allowlist is what keeps it out.
"""

# ── Listing-text keywords (kept identical to the website's utils.mjs / shared-utils.mjs
#    WATERFRONT_KEYWORDS and the valuation script's list, so all three agree). ──
WATERFRONT_KEYWORDS = (
    'waterfront', 'water front', 'canal front', 'canal frontage', 'canalfrontage',
    'lakefront', 'lake front', 'riverfront', 'river front',
    'beachfront', 'beach front', 'oceanfront', 'ocean front',
    'water frontage', 'waterfrontage', 'absolute waterfront',
)

# ── Satellite backs_onto values that mean a water body forms a boundary. ──
WATER_BACK_TYPES = frozenset({
    'lake', 'waterway', 'canal', 'river', 'ocean', 'estuary',
    'broadwater', 'marina', 'inlet', 'lagoon',
})

# ── Satellite water_proximity values that mean actual water FRONTAGE (allowlist,
#    never substring). Anything not in here — 'not_waterfront', 'none',
#    'lake_adjacent', 'water_adjacent', 'near_water', 'water_glimpse',
#    'reserve_front' — does NOT by itself flag waterfront. ──
WATER_PROXIMITY_FRONT = frozenset({
    'waterfront', 'absolute_waterfront', 'main_river_front',
    'lake_front', 'lakefront', 'canal_front', 'canalfront',
    'river_front', 'riverfront', 'ocean_front', 'oceanfront',
    'beach_front', 'beachfront', 'broadwater_front',
})


def _listing_text_signal(doc):
    text = f"{doc.get('description', '') or ''} {doc.get('agents_description', '') or ''}".lower()
    for kw in WATERFRONT_KEYWORDS:
        if kw in text:
            return kw
    return None


def _satellite_signal(doc):
    """Return (reason, borderline, detail) or (None, False, None).

    borderline=True flags a home whose rear boundary is water (backs_onto) but whose
    water_proximity says 'adjacent' rather than a frontage value — i.e. there may be a
    reserve/path strip between the lot and the water. Still treated as waterfront
    (conservative: we would rather exclude a borderline home than mis-value it), but
    surfaced so a human can eyeball it.
    """
    sa = doc.get('satellite_analysis')
    if not isinstance(sa, dict):
        return None, False, None
    # An EXPLICIT False means the vision pass could not tie its adjacency call to the
    # subject lot — do not trust it. A missing key (older capture) proceeds as before.
    if sa.get('pin_confirmed') is False:
        return None, False, None

    cats = sa.get('categories') or {}
    backs_onto = ((cats.get('adjacency') or {}).get('backs_onto')) or []
    water_prox = (cats.get('amenity_premiums') or {}).get('water_proximity')

    prox_hit = isinstance(water_prox, str) and water_prox.strip().lower() in WATER_PROXIMITY_FRONT
    back_hit = isinstance(backs_onto, list) and any(
        isinstance(b, str) and b.strip().lower() in WATER_BACK_TYPES for b in backs_onto
    )

    if prox_hit:
        return 'satellite_water_proximity', False, {'water_proximity': water_prox, 'backs_onto': backs_onto}
    if back_hit:
        # backs onto water but proximity is not a frontage value → borderline.
        borderline = isinstance(water_prox, str) and 'adjacent' in water_prox.strip().lower()
        return 'satellite_backs_onto', borderline, {'water_proximity': water_prox, 'backs_onto': backs_onto}
    return None, False, None


def detect_waterfront(doc):
    """Decide whether a property document is waterfront.

    Returns a dict:
      {
        'is_waterfront': bool,
        'reason': str | None,     # strongest signal: explicit_flag | photo_vision |
                                  #   listing_text | satellite_water_proximity |
                                  #   satellite_backs_onto
        'borderline': bool,       # water boundary but 'adjacent' not 'front' (satellite)
        'signals': {...},         # every signal that fired, for auditing/meta storage
      }
    Pure/read-only — never mutates the doc. Callers persist the result as the
    `is_waterfront` boolean (+ `waterfront_meta`) so the website and the valuation
    comp filter can key off it.
    """
    signals = {}

    # Signal 1: GPT-4 Vision photo analysis (it actually saw water in the photos).
    pvd = doc.get('property_valuation_data') or {}
    if isinstance(pvd, dict) and (pvd.get('outdoor') or {}).get('water_views'):
        signals['photo_vision'] = True

    # Signal 2: listing text keyword.
    kw = _listing_text_signal(doc)
    if kw:
        signals['listing_text'] = kw

    # Signal 3: satellite structured adjacency/amenity (previously ignored).
    sat_reason, sat_borderline, sat_detail = _satellite_signal(doc)
    if sat_reason:
        signals[sat_reason] = sat_detail

    # Signal 0: explicit flag already present (manual override or a prior backfill).
    explicit = bool(doc.get('is_waterfront') or doc.get('waterfront_premium_eligible'))
    if explicit:
        signals['explicit_flag'] = True

    is_waterfront = explicit or bool(
        signals.get('photo_vision') or signals.get('listing_text') or sat_reason
    )

    # Strongest evidence-based reason first (more informative than the persisted flag).
    reason = None
    for candidate in ('photo_vision', 'listing_text',
                      'satellite_water_proximity', 'satellite_backs_onto'):
        if candidate in signals:
            reason = candidate
            break
    if reason is None and explicit:
        reason = 'explicit_flag'

    return {
        'is_waterfront': is_waterfront,
        'reason': reason,
        'borderline': bool(sat_borderline) and reason == 'satellite_backs_onto',
        'signals': signals,
    }


def is_waterfront(doc):
    """Boolean convenience wrapper."""
    return detect_waterfront(doc)['is_waterfront']


# ─────────────────────────────────────────────────────────────────────────────
# Water RELATIONSHIP classifier (added 2026-08-07)
# ─────────────────────────────────────────────────────────────────────────────
#
# `detect_waterfront()` above is deliberately BROAD because it drives a SUPPRESSION
# gate — skip editorial, noindex, withhold the valuation. There, a false positive is
# cheap: we stay quiet about a dry home. Keep it broad.
#
# The SAME flag is also read by precompute_valuations.py to pick the comparable
# cohort, and there a false positive is expensive. A lake-VIEW home flagged waterfront
# gets compared only to genuine water-frontage sales, which sell far higher.
#
# Measured 2026-08-07 over 625 backtested detached houses:
#   flagged waterfront ....... 59 homes, median error  +8.0%, MAE 13.5%, 73% over-valued
#   not flagged .............. 566 homes, median error -0.6%, MAE  9.4%, 48% over-valued
# Splitting that flagged group by GEOMETRY rather than photographs:
#   genuinely waterfront ..... 18 homes, median error  +1.6%, MAE 10.2%
#   MISCLASSIFIED ............ 41 homes, median error +10.4%, MAE 14.9%, 78% over-valued
#
# The method handles real waterfront acceptably. It is the false positives that break
# it — 69% of the flagged group. The cause is signal 1: `outdoor.water_views` is a
# GPT-4 Vision read of the PHOTOS, and it answers "can you see water from here?", not
# "does this parcel touch water?".
#
# 24 Brooklyn Crescent, Robina is the worked example. Its own OSM record already said
#   distance_to_water_m 21.5 | waterfront_type "none" | canal_frontage False
#   | waterfront_premium_eligible False | satellite backs_onto ["residential_only"]
# and we flagged it waterfront anyway, off the photo signal, then over-valued it 56%.
# The geometry was right there and was overridden.
#
# So: GEOMETRY decides frontage, PHOTOGRAPHS decide views.

_WATER_BACKS_ONTO = ('canal', 'lake', 'river', 'ocean', 'water', 'waterway',
                     'creek', 'lagoon', 'inlet', 'broadwater')

WATERFRONT = 'waterfront'      # canal / river / ocean frontage — SPECIALIST MARKET
LAKEFRONT = 'lakefront'        # on or beside a lake — a normal home with a premium
WATER_VIEW = 'water_view'
DRY = 'dry'

# ⚠ LAKEFRONT IS NOT "WATERFRONT". Learned the hard way 2026-08-08.
#
# The out-of-scope policy in detect_waterfront() is about markets that need
# specialist expertise to price — canal frontage with a pontoon, river frontage,
# absolute oceanfront. Water depth, navigability, jetty value, canal levies.
#
# A house 22 m from the edge of a Varsity Lakes lake is not that. It is an
# ordinary detached house carrying a location premium, and the premium is
# measurable and stable: +13.6% at 10-20 m, +12.4% at 20-30 m, gone by 30 m
# (n=807 sold houses).
#
# Folding lake proximity into WATERFRONT reclassified **1,083 of 13,434 houses
# (8.1%)** as out-of-scope in one change — including 11 Placid Court, which lost
# its valuation entirely and returned `insufficient_comparables` with zero comps.
# Robina 5.7%, Varsity Lakes 4.8%, Burleigh Waters 13.7%.
#
# So lakefront gets its own cohort: kept separate from dry stock for comparison
# purposes (which is what fixed the over-valuation), but still VALUED.


def classify_water_relationship(doc, view_distance_m=150):
    """Return (class, reason) where class is waterfront | water_view | dry.

    Use this for COMPARABLE COHORT SELECTION. Use `detect_waterfront()` for the
    publish/suppress gate — the two answer different questions and a home can
    legitimately be `water_view` here while still being suppressed there.

    Frontage is decided by measurement, never by photographs:
      1. OSM `water_features` — canal_frontage / waterfront_premium_eligible /
         waterfront_type, the fields already computed per property.
      2. Satellite structured adjacency — backs_onto naming a water body.
      3. distance_to_water_m within 5 m (a parcel effectively touching water).
    Only then do photographs get a say, and only to mark the VIEW class.

    ⚠ Coverage: 332 of 625 backtested homes (53%) had no OSM `water_features` block
    at all. Where geometry is absent this falls back to the photo signal and returns
    reason='photo_view_no_geometry' — treat that as provisional, not as evidence of
    dryness, and backfill the OSM pass rather than trusting the fallback.
    """
    wf = (doc.get('osm_location_features') or {}).get('water_features') or {}
    adjacency = ((doc.get('satellite_analysis') or {}).get('categories') or {}).get('adjacency') or {}
    backs = ' '.join(adjacency.get('backs_onto') or []).lower()

    wtype = wf.get('waterfront_type')

    # Lake proximity first — it is the most common water relationship we have and
    # it must NOT fall through into the specialist-frontage class below.
    if wtype == 'lakefront':
        return LAKEFRONT, 'osm_waterfront_type:lakefront'

    if wf.get('canal_frontage'):
        return WATERFRONT, 'osm_canal_frontage'
    if wtype and wtype != 'none':
        return WATERFRONT, f'osm_waterfront_type:{wtype}'
    if wf.get('waterfront_premium_eligible'):
        return WATERFRONT, 'osm_waterfront_premium_eligible'
    if any(w in backs for w in _WATER_BACKS_ONTO):
        # A lake at the rear boundary is lakefront, not canal/ocean frontage.
        if any(w in backs for w in ('lake', 'lagoon')):
            return LAKEFRONT, 'satellite_backs_onto_lake'
        return WATERFRONT, 'satellite_backs_onto_water'

    dist = wf.get('distance_to_water_m')
    if dist is not None and dist <= 5:
        if (wf.get('nearest_water_type') or '') in ('water_body', 'wetland'):
            return LAKEFRONT, 'osm_distance_to_lake<=5m'
        return WATERFRONT, 'osm_distance_to_water<=5m'

    photo_view = bool(((doc.get('property_valuation_data') or {}).get('outdoor') or {}).get('water_views'))
    if dist is not None:
        if dist <= view_distance_m:
            return WATER_VIEW, f'osm_distance_to_water:{dist:.0f}m'
        return DRY, f'osm_distance_to_water:{dist:.0f}m'
    if photo_view:
        return WATER_VIEW, 'photo_view_no_geometry'
    return DRY, 'no_water_signal'
