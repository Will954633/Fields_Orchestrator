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
  4. OSM `waterfront_premium_eligible` — the pre-computed eligibility flag
     (backfill_osm_water_features.py, canal/lake/river 30 m, coastline 50 m).
  5. OSM geometric fallback (added 2026-08-20): measured distance to a genuine
     water body within WATERFRONT_GEOMETRIC_FALLBACK_M when signal 4's flag is
     absent/stale/False and Signals 1-3 are silent. This closes the blind spot
     where a cadastral/sold/timeline-only lakefront home — no text, no vision,
     and a `waterfront_premium_eligible` flag left False because the 2026-08-07
     lakefront backfill never re-processed it — was scored dry despite sitting
     ~20 m from a lake, leaking a ~$5.1M-class canal/lake home into the DRY
     comparable pool. Drains/streams/ditches are excluded. See _osm_distance_signal.

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

# ── Geometric fallback (Signal 5, added 2026-08-20). ──────────────────────────
# Distance (metres) within which a parcel sitting beside a GENUINE water body is
# treated as waterfront when no other signal fired and the pre-computed
# `waterfront_premium_eligible` flag is not already True. See the block in
# detect_waterfront() for the full rationale. 35 m, not the backfill's 30 m: the
# stored distance is measured from the parcel CENTROID, so true frontage distance
# is systematically shorter — a 5 m margin absorbs that plus geometry rounding.
# This gate feeds a conservative SUPPRESSION decision (a false positive only
# keeps us quiet about a home), so erring slightly generous is the safe side.
WATERFRONT_GEOMETRIC_FALLBACK_M = 35

# nearest_water_type values that carry a genuine waterfront character for the
# geometric fallback. Deliberately EXCLUDES 'drain', 'stream', 'ditch',
# 'waterway' — stormwater/drainage lines that a parcel can sit metres from while
# being entirely dry stock (67 such homes in Burleigh Waters alone sit <=8 m from
# a drain/stream/ditch). Only these premium bodies may trip the distance rule.
GEOMETRIC_FALLBACK_WATER_TYPES = frozenset({
    'canal', 'river', 'coastline', 'water_body', 'lake',
    'estuary', 'broadwater', 'lagoon', 'marina', 'inlet',
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


def _osm_distance_signal(doc):
    """Geometric fallback (Signal 5): parcel measured within
    WATERFRONT_GEOMETRIC_FALLBACK_M of a genuine water body.

    Returns a detail dict when it fires, else None.

    WHY THIS EXISTS (2026-08-20) — the stale-OSM blind spot
    ────────────────────────────────────────────────────────────────────────────
    Signal 4 above consumes the pre-computed `waterfront_premium_eligible`
    boolean. That flag is only as good as the last time `backfill_osm_water_features.py`
    ran over the document. The LAKEFRONT branch of that backfill (water bodies
    within 30 m → `waterfront_type: 'lakefront'`, eligible True) was ADDED on
    2026-08-07, after many documents already carried a `water_features` block. On
    every such stale document the nearest feature is a lake — `nearest_water_type:
    'water_body'`, a real measured `distance_to_water_m` — yet `waterfront_type`
    is still `'none'` and `waterfront_premium_eligible` is `False`, because that
    branch never re-processed it (`osm_location_features.metadata.water_backfilled_at`
    is null). Cadastral / sold / timeline-only documents are the worst hit: they
    carry no listing text and no vision pass, so Signals 1-3 are all silent, and
    Signal 4 reads a stale False — the detector had NOTHING to work from and
    returned dry for a home sitting 20 m from a lake.

    Measured 2026-08-20 across the three core suburbs: 365 documents (88 Burleigh
    Waters, 236 Robina, 41 Varsity Lakes) sit within 35 m of a `water_body` with a
    stale not-eligible flag and were classified dry — every one of them a home a
    fresh OSM pass would already flag. That is precisely how a ~$5.1M-class
    canal/lake home leaks into the DRY comparable pool and drags a dry subject's
    valuation upward, the exact failure the out-of-scope policy exists to prevent.

    This signal recovers those homes WITHOUT depending on the backfill having run,
    by reading the raw measured geometry that is already on the document:
      • a canal within the fallback distance (`distance_to_canal_m`), or
      • the nearest overall water body being one of GEOMETRIC_FALLBACK_WATER_TYPES
        (drains/streams/ditches excluded) within `distance_to_water_m`.
    It is skipped when `waterfront_premium_eligible` is already True (Signal 4
    owns that case and outranks this one).
    """
    wf = (doc.get('osm_location_features') or {}).get('water_features') or {}
    if not isinstance(wf, dict):
        return None
    # Signal 4 already handles a positively-eligible parcel; do not double-report.
    if wf.get('waterfront_premium_eligible') is True:
        return None

    # A measured canal within range is the strongest geometric case (canal
    # frontage is the specialist market the policy most wants to exclude).
    canal_d = wf.get('distance_to_canal_m')
    if isinstance(canal_d, (int, float)) and canal_d <= WATERFRONT_GEOMETRIC_FALLBACK_M:
        return {'nearest_water_type': 'canal', 'distance_to_water_m': canal_d,
                'via': 'distance_to_canal_m', 'threshold_m': WATERFRONT_GEOMETRIC_FALLBACK_M}

    dist = wf.get('distance_to_water_m')
    ntype = wf.get('nearest_water_type')
    if not isinstance(dist, (int, float)) or dist > WATERFRONT_GEOMETRIC_FALLBACK_M:
        return None
    if isinstance(ntype, str) and ntype.strip().lower() in GEOMETRIC_FALLBACK_WATER_TYPES:
        return {'nearest_water_type': ntype, 'distance_to_water_m': dist,
                'via': 'distance_to_water_m', 'threshold_m': WATERFRONT_GEOMETRIC_FALLBACK_M}
    return None


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

    # Signal 4: OSM measured water geometry.
    #
    # ⚠ THIS IS THE STRONGEST SIGNAL WE HAVE AND IT WAS BEING MISSED. The line
    # below used to read `doc.get('waterfront_premium_eligible')` at the TOP
    # level — the field has always lived nested under
    # `osm_location_features.water_features`. So the detector was written to
    # consume exactly this evidence and looked for it at the wrong depth,
    # silently finding nothing. The OSM block was backfilled on 2026-08-08,
    # after this module was written on 2026-07-26, and lake homes were the
    # documented blind spot the backfill existed to close.
    #
    # Measured on 2026-08-13 across the three core suburbs: 2,011 properties
    # carry OSM waterfront geometry, only 63 were flagged — 1,948 missed, of
    # which 252 had a published valuation range built from dry comparables,
    # precisely the failure the out-of-scope policy exists to prevent.
    #
    # `waterfront_premium_eligible` already encodes conservative thresholds set
    # in backfill_osm_water_features.py (lake/river/canal front 30 m, coastline
    # 50 m), so it is used as-is rather than re-deriving a distance rule here.
    osm_water = ((doc.get('osm_location_features') or {}).get('water_features') or {})
    if osm_water.get('waterfront_premium_eligible') is True:
        signals['osm_water_frontage'] = {
            'waterfront_type': osm_water.get('waterfront_type'),
            'distance_to_water_m': osm_water.get('distance_to_water_m'),
            'nearest_water_type': osm_water.get('nearest_water_type'),
        }

    # Signal 5: geometric fallback — measured proximity to a genuine water body
    # when the eligibility flag is absent/stale/False and no other signal fired.
    # See _osm_distance_signal() for the stale-backfill rationale. This is an
    # ADDITIVE positive signal: it can only turn a dry result waterfront, never
    # the reverse (this function carries no 'confident dry' signal to override),
    # so it never contradicts a text/vision/eligible-flag call — those still win
    # the `reason`. It ranks LAST because it is a derived, threshold-based rescue
    # rather than an explicit assertion of frontage.
    geo_detail = _osm_distance_signal(doc)
    if geo_detail:
        signals['osm_water_distance'] = geo_detail

    # Signal 0: explicit flag already present (manual override or a prior backfill).
    explicit = bool(doc.get('is_waterfront') or doc.get('waterfront_premium_eligible'))
    if explicit:
        signals['explicit_flag'] = True

    is_waterfront = explicit or bool(
        signals.get('photo_vision') or signals.get('listing_text') or sat_reason
        or signals.get('osm_water_frontage') or signals.get('osm_water_distance')
    )

    # Strongest evidence-based reason first (more informative than the persisted
    # flag). Measured eligibility geometry outranks vision and text — it is the
    # only signal with a metre distance AND a calibrated eligibility decision
    # behind it. The geometric-distance fallback ranks LAST: it is a derived
    # rescue for stale/missing eligibility, weaker than an explicit assertion.
    reason = None
    for candidate in ('osm_water_frontage', 'photo_vision', 'listing_text',
                      'satellite_water_proximity', 'satellite_backs_onto',
                      'osm_water_distance'):
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
