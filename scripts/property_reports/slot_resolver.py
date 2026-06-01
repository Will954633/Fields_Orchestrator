"""
SlotResolver — produces the per-property data for a mini-site.

One method per slot. Each method is independent — if it raises or
returns None, the field is left null and the frontend hides the
relevant block. We never half-fill a field with garbage.

Queries hit four collections in `Gold_Coast`:
  - <suburb> (e.g. merrimac) — the property + sold cohort
  - precomputed_market_charts — per-suburb market state series
  - precomputed_indexed_prices — per-suburb growth index
  - address_search_index — fallback lookup if property_id is missing

All listing queries MUST filter on `listing_status` (per project rule —
without it, queries hit ~40K cadastral records).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from scripts.property_reports.hero_photo import score_and_pick_hero
from scripts.property_reports.walking_distances import resolve_pois
from scripts.property_reports.market_narrative import resolve_market_narrative
from scripts.property_reports.scarcity_features import resolve_scarcity_features
from scripts.property_reports.competitor_matcher import resolve_competitor_map
from scripts.property_reports.comparable_feed import (
    comparables_from_slots,
    comparable_events_from_slots,
)
from scripts.property_reports.cohort_premiums import compute_cohort_premiums
from scripts.property_reports.scarcity_narrative import (
    resolve_scarcity_narrative, cohort_premiums_to_sold_cohort_premiums,
)
from scripts.property_reports.positioning_narrative import resolve_positioning_narrative
from scripts.property_reports.personas_narrative import resolve_personas_narrative
from scripts.property_reports.buyers_narrative import resolve_buyers_narrative
from scripts.property_reports.build_events import NullEmitter
from scripts.property_reports.inline_features import derive_features_basic
from scripts.property_reports.inline_scrape import needs_refresh, recover_photos
from scripts.property_reports.inline_floor_plan import resolve_floor_plan
from scripts.property_reports.inline_satellite import resolve_satellite
from scripts.property_reports.inline_street_view import resolve_street_view

logger = logging.getLogger(__name__)


class SlotResolver:
    """
    Builds the slot dictionary for one property_reports doc.

    Usage:
        resolver = SlotResolver(report_doc, gold_coast_db)
        slots = resolver.resolve_all()
        # → returns a dict ready to $set into property_reports
    """

    def __init__(self, report_doc: Dict[str, Any], db: Database, emitter: Any = None):
        self.report = report_doc
        self.db = db
        self.suburb_key = report_doc.get("suburb_key", "").lower()
        self.suburb_display = report_doc.get("suburb", "")
        self.address = report_doc.get("address", "")
        self.property_id = report_doc.get("property_id")
        # Live progress emitter — defaults to no-op for tests / dry-runs
        self.emit = emitter or NullEmitter()

        # Will be populated by _load_subject_property()
        self._subject: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def resolve_all(self) -> Dict[str, Any]:
        """
        Resolve every slot. Returns a dict of $set updates for property_reports.

        Schema mirrors property_reports.* — top-level keys: property, valuation,
        market, slots, activity (additive), data_pull_date.
        """
        self.emit.start("cadastral", "Pulling your land + floor area")
        self._load_subject_property()

        updates: Dict[str, Any] = {
            "slots.data_pull_date": datetime.utcnow(),
        }

        # Photo refresh — sold/off-market properties typically have only the
        # most-recent sale's hero in `property_images_original`. Domain's CDN
        # still holds full-res copies of the older listing photos under
        # `b.domainstatic.com.au/<path>`, and the path is embedded in the
        # rimh2 thumbnail URLs we already scraped. Lift them on-demand.
        # No HTTP cost — pure URL transformation.
        if self._subject and needs_refresh(self._subject):
            try:
                coll = self.db[self.suburb_key] if self.suburb_key else None
                recovered = recover_photos(self._subject, coll=coll)
                if recovered:
                    # Mirror into the in-memory subject so property_facts uses them
                    self._subject["property_images_refreshed"] = recovered
                    logger.info(
                        f"  photo refresh: recovered {len(recovered)} full-res URLs "
                        f"for {self.address}"
                    )
            except Exception as e:
                logger.warning(f"  photo refresh threw: {e}")

        # Subject property facts
        prop = self.property_facts()
        if prop:
            updates["property"] = prop
            self.emit.done(
                "cadastral",
                "Land + floor area captured",
                bed=prop.get("bed"),
                bath=prop.get("bath"),
                land_area_sqm=prop.get("land_area_sqm"),
                internal_area_sqm=prop.get("internal_area_sqm"),
                property_type=prop.get("property_type"),
            )

            # Floor plan — identify + analyse on-demand. Off-market submissions
            # frequently lack the nightly batch's `floor_plans_v2_extracted`,
            # so the resolver must classify candidates itself. Once identified,
            # run GPT-4o vision on the highest-res variant to extract rooms,
            # dimensions, level count. Surface result at property.floor_plan
            # so the frontend can render a layout section.
            self.emit.start("floor_plan", "Reading your floor plan")
            try:
                candidate_urls = [p["url"] for p in prop.get("photos") or [] if p.get("url")]
                existing_extracted = (self._subject or {}).get("floor_plans_v2_extracted") or []
                fp = resolve_floor_plan(
                    candidate_urls,
                    existing_extracted=existing_extracted if existing_extracted else None,
                )
                if fp:
                    # Embed inside the property dict we already wrote — MongoDB
                    # rejects $set of both "property" and "property.floor_plan"
                    # at once.
                    prop["floor_plan"] = fp
                    updates["property"] = prop
                    rooms = (fp.get("layout") or {}).get("rooms") or []
                    self.emit.done(
                        "floor_plan",
                        f"Floor plan analysed — {len(rooms)} rooms" if rooms
                        else "Floor plan identified",
                        room_count=len(rooms),
                        url=fp.get("url"),
                    )
                else:
                    self.emit.done("floor_plan", "No floor plan in the photo set")
            except Exception as e:
                logger.warning(f"  floor plan resolver threw: {e}")
                self.emit.fail("floor_plan", str(e))

            # Satellite / aerial view — same intent as floor_plan but a different
            # input. Reuses the existing satellite_analysis on the doc when the
            # nightly batch has visited; otherwise fetches a Google Maps tile and
            # runs the structured GPT vision pass on-demand. Surface result at
            # property.satellite so the frontend can render an "Aerial view"
            # section with the image + the structured findings.
            self.emit.start("satellite", "Reading the aerial view")
            try:
                coll = self.db[self.suburb_key] if self.suburb_key else None
                sat = resolve_satellite(
                    self._subject or {},
                    suburb_key=self.suburb_key,
                    db_subject_coll=coll,
                )
                if sat:
                    prop["satellite"] = sat
                    updates["property"] = prop
                    # Mirror onto the in-memory subject so downstream resolvers
                    # (inline_features.derive_features_basic, scarcity_features)
                    # see the new pool_visible / water_proximity signals this
                    # same run, not on the next visit.
                    if self._subject is not None:
                        self._subject["satellite_analysis"] = sat
                    cats = sat.get("categories") or {}
                    self.emit.done(
                        "satellite",
                        f"Aerial view read — {len(cats)} category buckets",
                        bucket_count=len(cats),
                        pool_visible=(cats.get("amenity_premiums") or {}).get("pool_visible"),
                        url=sat.get("satellite_image_url"),
                    )
                else:
                    self.emit.done("satellite", "Aerial view pending — no coordinates / API unavailable")
            except Exception as e:
                logger.warning(f"  satellite resolver threw: {e}")
                self.emit.fail("satellite", str(e))

            # Street View — kerb-level companion to the satellite. Fetches a
            # Google Static Street View image at the lat/lng and runs GPT-4o
            # vision for storeys / style / cladding / garage / front-yard
            # signals. Universal baseline asset for every address.
            self.emit.start("street_view", "Capturing the street-level view")
            try:
                coll = self.db[self.suburb_key] if self.suburb_key else None
                sv = resolve_street_view(
                    self._subject or {},
                    suburb_key=self.suburb_key,
                    db_subject_coll=coll,
                )
                if sv and sv.get("street_view_image_url"):
                    prop["street_view"] = sv
                    updates["property"] = prop
                    # Mirror onto the in-memory subject so derive_features_basic
                    # picks up storeys / car_spaces / cladding fallbacks this
                    # same run.
                    if self._subject is not None:
                        self._subject["street_view_analysis"] = sv
                    cats = sv.get("categories") or {}
                    storeys = (cats.get("dwelling") or {}).get("storeys")
                    style = (cats.get("dwelling") or {}).get("style")
                    self.emit.done(
                        "street_view",
                        f"Street view read — {style or 'home'}, {storeys or '?'} storey",
                        storeys=storeys,
                        style=style,
                        url=sv.get("street_view_image_url"),
                    )

                    # Hero fallback — if the photo gallery's hero is missing or
                    # is a 150px rimh2 thumbnail (renders blank at hero-section
                    # width), swap in the Street View image. The Google Street
                    # View shot is full-resolution and always shows the actual
                    # home — best fallback we have for sparse-photo addresses.
                    photos = prop.get("photos") or []
                    hero = next((p for p in photos if p.get("role") == "hero"), None)
                    hero_url = (hero or {}).get("url") or ""
                    hero_is_thumbnail = (
                        "rimh2.domainstatic.com.au" in hero_url
                        and "/fit-in/" not in hero_url
                    )
                    if not hero or hero_is_thumbnail:
                        new_hero = {
                            "url": sv["street_view_image_url"],
                            "role": "hero",
                            "meta": {"picked_by": "street_view_fallback"},
                        }
                        # Drop any existing hero, prepend the Street View hero.
                        photos = [p for p in photos if p.get("role") != "hero"]
                        photos.insert(0, new_hero)
                        prop["photos"] = photos
                        updates["property"] = prop
                        logger.info(
                            f"  hero fallback: swapped {'thumbnail' if hero_is_thumbnail else 'missing'} "
                            f"hero for street view image"
                        )
                else:
                    self.emit.done("street_view", "No street view imagery available at this address")
            except Exception as e:
                logger.warning(f"  street_view resolver threw: {e}")
                self.emit.fail("street_view", str(e))
        else:
            self.emit.fail("cadastral", "Subject property not found")

        # Valuation model range (a working range, not the human-reviewed final)
        self.emit.start("valuation", "Computing your working valuation range")
        model_range = self.valuation_model_range()
        if model_range:
            updates["valuation.model_range"] = model_range
            self.emit.done(
                "valuation",
                f"Working range ${model_range.get('low', 0):,}–${model_range.get('high', 0):,}",
                low=model_range.get("low"),
                high=model_range.get("high"),
                comp_count=model_range.get("comp_count"),
            )
        else:
            self.emit.done("valuation", "Working range pending — consultant will finalise")

        # Valuation comps from the engine output (Path A — produced by
        # process 301 + the nightly precompute job). When the subject has
        # `valuation_data.recent_sales[]` we surface the per-comp adjustments
        # the engine computed. Auto-promote slot_status.comps once the comps
        # are populated — this is interim until the analyst-review gate
        # lands on Day 14, at which point the promotion moves to the ops
        # dashboard sign-off step.
        self.emit.start("comps", "Finding comparable sales nearby")
        eng_comps = self.valuation_comps_from_engine()
        if eng_comps is not None:
            updates["valuation.comps"] = eng_comps
            if eng_comps:
                # Engine produced usable comps → expose to mini-site
                updates["slot_status.comps"] = "approved"
                updates["valuation.comps_resolved_at"] = datetime.utcnow()
                self.emit.done(
                    "comps",
                    f"{len(eng_comps)} comparable sales found",
                    count=len(eng_comps),
                )
            else:
                # Engine ran but excluded the subject (no floor_area, etc.)
                # Leave slot pending — placeholder shows on the page.
                updates["slot_status.comps"] = "pending"
                self.emit.done("comps", "Comparable sales pending — consultant will refine")
        else:
            self.emit.done("comps", "Comparable sales pending — consultant will refine")

        # Market state for the suburb
        self.emit.start("market_position", "Writing your market position")
        market = self.market_state()
        if market:
            updates["market"] = market

            # Market narrative — Opus 4.7 explains what the numbers mean for
            # this seller (Day 5). First narrative LLM in the chain. Retries
            # 3x with validation guardrails; failures set slot_status.error.
            bed_band = _to_int((self._subject or {}).get("bedrooms"))
            try:
                narrative = resolve_market_narrative(
                    market, self.suburb_display, bed_band,
                    address=self.address,
                )
                if narrative and narrative.get("text"):
                    updates["market_narrative"] = narrative
                    updates["slot_status.market_narrative"] = "approved"
                    logger.info(f"  market_narrative generated ({len(narrative['text'])} chars)")
                    self.emit.done(
                        "market_position",
                        "Market position drafted",
                        chars=len(narrative["text"]),
                    )
                elif narrative and narrative.get("error"):
                    updates["market_narrative_error"] = narrative
                    updates["slot_status.market_narrative"] = "error"
                    logger.warning(f"  market_narrative failed: {narrative.get('error')}")
                    self.emit.fail("market_position", narrative.get("error") or "narrative failed")
                else:
                    updates["slot_status.market_narrative"] = "pending"
                    self.emit.done("market_position", "Market position pending")
            except Exception as e:
                logger.warning(f"  market_narrative resolver threw: {e}")
                updates["slot_status.market_narrative"] = "error"
                updates["market_narrative_error"] = {"error": str(e), "attempts": 0}
                self.emit.fail("market_position", str(e))
        else:
            self.emit.done("market_position", "Market position pending")

        # Comps — top-N recent sold matches
        comps = self.recent_comparable_sales(n=6)
        if comps:
            updates["slots.recent_comps"] = comps
            # First comp is the "best" anchor for the activity feed
            updates["slots.best_comp"] = comps[0]

        # Scarcity / competition counts
        competition = self.competition_count()
        if competition is not None:
            updates["slots.n_competitors"] = competition

        # Lat/lng if we have them
        latlng = self.subject_latlng()
        if latlng:
            updates["lat"] = latlng[0]
            updates["lng"] = latlng[1]

        # Scarcity features (Day 7) — identifies the subject's notable feature
        # stack from valuation_data.subject_property.features.basic and counts
        # how many other active listings in the catchment carry the same stack.
        # Day 8 adds cohort_premiums: per-feature median sale-price delta from
        # the sold cohort. Both write to property_reports.scarcity_features as
        # structured data; the Day 9 Opus narrative reads from here. Slot
        # doesn't auto-promote yet — scarcity slot stays pending until the
        # narrative resolver runs.
        if self._subject:
            self.emit.start("scarcity", "Counting how rare your home is")
            try:
                scarcity = resolve_scarcity_features(self._subject, self.db)
                if scarcity:
                    # Day 8: enrich with cohort premiums per notable feature
                    try:
                        premiums = compute_cohort_premiums(
                            scarcity.get("notable_features", []),
                            self.db,
                            scarcity.get("catchment_suburbs") or [],
                        )
                        if premiums:
                            scarcity["cohort_premiums"] = premiums
                            reliable_count = sum(1 for p in premiums if p.get("reliable"))
                            logger.info(f"  cohort premiums: {len(premiums)} features, {reliable_count} reliable")
                    except Exception as e:
                        logger.warning(f"  cohort_premiums failed: {e}")

                    updates["scarcity_features"] = scarcity
                    notable_count = len(scarcity.get("notable_features", []))
                    matching = scarcity.get("active_matching_full_stack")
                    total = scarcity.get("active_listings_total")
                    logger.info(
                        f"  scarcity features: {notable_count} notable | "
                        f"{matching}/{total} active in catchment match full stack"
                    )
                    self.emit.done(
                        "scarcity",
                        f"{notable_count} notable features, {matching} of {total} actives match",
                        notable_count=notable_count,
                        matching_full_stack=matching,
                        active_listings_total=total,
                    )
                else:
                    self.emit.done("scarcity", "Scarcity profile pending")
            except Exception as e:
                logger.warning(f"  scarcity_features resolver threw: {e}")
                self.emit.fail("scarcity", str(e))

        # Competitor map — the live "substitute homes" set for the Market tab.
        # Substitutes = homes a buyer actually chooses between (budget + beds +
        # type), NOT feature-twins (that's the scarcity count above). Uses an
        # adaptive aperture: a common home finds a tight same-suburb set; a
        # unique home widens the price/bedroom/suburb net until the floor is
        # met — and the ring it lands on becomes a scarcity narrative asset.
        # Auto-approves on resolve so the map is live the moment the seller's
        # mini-site first loads (no nightly wait, no manual gate).
        if self._subject:
            self.emit.start("competitor_map", "Finding the homes yours competes with")
            try:
                # Price anchor: prefer the valuation working-range midpoint
                # (right for off-market submissions with no listing price),
                # fall back to the subject's own price string.
                model_range = self.valuation_model_range()
                price_anchor = None
                if model_range and model_range.get("low") and model_range.get("high"):
                    price_anchor = int((model_range["low"] + model_range["high"]) / 2)

                features_basic = derive_features_basic(self._subject)
                comp_map = resolve_competitor_map(
                    self._subject, self.db, features_basic, price_anchor=price_anchor,
                )
                if comp_map and comp_map.get("competitors"):
                    updates["slots.competitor_map"] = comp_map
                    updates["slot_status.competitor_matches"] = "approved"
                    n = len(comp_map["competitors"])
                    n_close = sum(1 for c in comp_map["competitors"] if c.get("combinatorialMatch"))
                    logger.info(
                        f"  competitor map: {n} substitutes ({n_close} closest tier), "
                        f"ring {comp_map['aperture_ring']}, {comp_map['active_in_band']} in band"
                    )
                    self.emit.done(
                        "competitor_map",
                        f"{n} competing homes mapped ({n_close} direct matches)",
                        n_competitors=n,
                        n_close=n_close,
                        aperture_ring=comp_map["aperture_ring"],
                    )
                else:
                    # No substitutes anywhere — leave the slot pending so the
                    # frontend shows the placeholder rather than an empty map.
                    self.emit.done("competitor_map", "No close competitors on the market")
            except Exception as e:
                logger.warning(f"  competitor_matcher resolver threw: {e}")
                updates["slot_status.competitor_matches"] = "error"
                self.emit.fail("competitor_map", str(e))

        # Walking distances to nearest POIs (Day 4). Requires lat/lng — skip
        # for subjects we can't geolocate (vacant cadastral lots etc.).
        resolved_pois: List[Dict[str, Any]] = []
        if latlng:
            self.emit.start("walking_distances", "Measuring walks to schools, parks, the beach")
            try:
                resolved_pois = resolve_pois(latlng[0], latlng[1])
                if resolved_pois:
                    updates["pois"] = resolved_pois
                    updates["slot_status.walking_distance"] = "approved"
                    logger.info(f"  walking distances resolved for {len(resolved_pois)} POIs")
                    self.emit.done(
                        "walking_distances",
                        f"{len(resolved_pois)} walks measured",
                        count=len(resolved_pois),
                    )
                else:
                    updates["slot_status.walking_distance"] = "pending"
                    self.emit.done("walking_distances", "Walks pending")
            except Exception as e:
                logger.warning(f"  walking distance resolver threw: {e}")
                updates["slot_status.walking_distance"] = "error"
                self.emit.fail("walking_distances", str(e))

        # Scarcity narrative (Day 9) — Opus 4.7 turns scarcity_features +
        # cohort_premiums + pois into the three user-facing strings the
        # mini-site renders: headline, combinatorialMatch, walkingDistanceMonopoly.
        # Deterministic mapping of cohort_premiums → soldCohortPremiums also
        # happens here (only reliable premiums surface). Auto-promotes slot
        # on narrative success; analyst review gate lands on Day 14.
        scarcity_struct = updates.get("scarcity_features")
        if scarcity_struct and scarcity_struct.get("notable_features"):
            self.emit.start("scarcity_story", "Writing your scarcity story")
            try:
                narrative = resolve_scarcity_narrative(
                    scarcity_struct, resolved_pois, self.suburb_display, self.address,
                )
                if narrative and narrative.get("headline"):
                    sold_cohort_premiums = cohort_premiums_to_sold_cohort_premiums(
                        scarcity_struct.get("cohort_premiums") or []
                    )
                    updates["scarcity"] = {
                        "headline": narrative["headline"],
                        "combinatorialMatch": narrative["combinatorialMatch"],
                        "walkingDistanceMonopoly": narrative["walkingDistanceMonopoly"],
                        "soldCohortPremiums": sold_cohort_premiums,
                        "generated_at": narrative["generated_at"],
                        "model": narrative["model"],
                        "attempt": narrative["attempt"],
                    }
                    updates["slot_status.scarcity"] = "approved"
                    logger.info(
                        f"  scarcity narrative generated (attempt {narrative['attempt']}): "
                        f"{len(narrative['headline'])} chars headline · {len(sold_cohort_premiums)} reliable premiums"
                    )
                    self.emit.done(
                        "scarcity_story",
                        "Scarcity story drafted",
                        attempt=narrative["attempt"],
                    )
                elif narrative and narrative.get("error"):
                    updates["scarcity_narrative_error"] = narrative
                    updates["slot_status.scarcity"] = "error"
                    logger.warning(f"  scarcity narrative failed: {narrative.get('error')}")
                    self.emit.fail("scarcity_story", narrative.get("error") or "narrative failed")
                else:
                    updates["slot_status.scarcity"] = "pending"
                    self.emit.done("scarcity_story", "Scarcity story pending")
            except Exception as e:
                logger.warning(f"  scarcity narrative resolver threw: {e}")
                updates["slot_status.scarcity"] = "error"
                updates["scarcity_narrative_error"] = {"error": str(e), "attempts": 0}
                self.emit.fail("scarcity_story", str(e))

        # Positioning narrative (Day 10) — Opus 4.7 produces the five
        # positioning fields (frame, vocabulary, tradeOffs, photography,
        # sampleParagraph) grounded in the same structured scarcity + cohort
        # data the scarcity narrative used. Reads `valuation_data.subject_property
        # .features.basic` for the property's full engine-feature dict.
        if scarcity_struct and scarcity_struct.get("notable_features") and self._subject:
            self.emit.start("positioning", "Building your positioning frame")
            try:
                # Prefer the precompute engine output if present; otherwise
                # derive features.basic on-demand from the doc's scrape data.
                # The product target is off-market homes, so most submissions
                # won't have the precompute_valuations.py output.
                features_basic = (
                    (self._subject.get("valuation_data") or {})
                    .get("subject_property", {})
                    .get("features", {})
                    .get("basic", {})
                ) or (derive_features_basic(self._subject) or {})
                pos = resolve_positioning_narrative(
                    address=self.address,
                    suburb=self.suburb_display,
                    features_basic=features_basic,
                    notable_features=scarcity_struct.get("notable_features", []),
                    matching_full_stack=scarcity_struct.get("active_matching_full_stack", 0),
                    active_listings_total=scarcity_struct.get("active_listings_total", 0),
                    cohort_premiums=scarcity_struct.get("cohort_premiums", []),
                    pois=resolved_pois,
                    valuation_range=updates.get("valuation.model_range"),
                )
                if pos and pos.get("frame"):
                    self.emit.done(
                        "positioning",
                        "Positioning frame drafted",
                        attempt=pos["attempt"],
                    )
                    # Day 11: personas resolver — generates the 3 buyer profiles
                    # used by both PositioningTab and BuyersTab. Reads the same
                    # scarcity_struct + features + pois as the positioning
                    # narrative for context coherence.
                    self.emit.start("personas", "Building your buyer personas")
                    personas: List[Dict[str, Any]] = []
                    try:
                        personas_result = resolve_personas_narrative(
                            address=self.address,
                            suburb=self.suburb_display,
                            features_basic=features_basic,
                            notable_features=scarcity_struct.get("notable_features", []),
                            matching_full_stack=scarcity_struct.get("active_matching_full_stack", 0),
                            active_listings_total=scarcity_struct.get("active_listings_total", 0),
                            cohort_premiums=scarcity_struct.get("cohort_premiums", []),
                            pois=resolved_pois,
                            valuation_range=updates.get("valuation.model_range"),
                        )
                        if personas_result and personas_result.get("personas"):
                            personas = personas_result["personas"]
                            logger.info(
                                f"  personas generated (attempt {personas_result['attempt']}): "
                                f"{[p['label'] for p in personas]}"
                            )
                            self.emit.done(
                                "personas",
                                f"{len(personas)} buyer personas drafted",
                                count=len(personas),
                                labels=[p.get("label") for p in personas],
                            )
                        elif personas_result and personas_result.get("error"):
                            updates["personas_narrative_error"] = personas_result
                            logger.warning(f"  personas failed: {personas_result.get('error')}")
                            self.emit.fail("personas", personas_result.get("error") or "personas failed")
                        else:
                            self.emit.done("personas", "Buyer personas pending")
                    except Exception as e:
                        logger.warning(f"  personas resolver threw: {e}")
                        self.emit.fail("personas", str(e))

                    updates["positioning"] = {
                        "frame": pos["frame"],
                        "vocabulary": pos["vocabulary"],
                        "tradeOffs": pos["tradeOffs"],
                        "photography": pos["photography"],
                        "sampleParagraph": pos["sampleParagraph"],
                        "personas": personas,
                        "generated_at": pos["generated_at"],
                        "model": pos["model"],
                        "attempt": pos["attempt"],
                    }
                    updates["slot_status.positioning"] = "approved"
                    logger.info(
                        f"  positioning narrative generated (attempt {pos['attempt']}): "
                        f"{len(pos['vocabulary']['use'])} use-terms, {len(pos['tradeOffs'])} trade-offs, "
                        f"{len(pos['sampleParagraph'].split())} word sample · {len(personas)} personas"
                    )

                    # Buyers narrative (Day 12-13) — thesis + catchment + campaign math.
                    # Requires the 3 personas we just generated. Catchment locations
                    # align 1:1 to the personas so the two sections cohere.
                    if personas and len(personas) >= 3:
                        self.emit.start("buyers", "Drafting your buyer thesis")
                        try:
                            buyers_result = resolve_buyers_narrative(
                                address=self.address,
                                suburb=self.suburb_display,
                                features_basic=features_basic,
                                notable_features=scarcity_struct.get("notable_features", []),
                                matching_full_stack=scarcity_struct.get("active_matching_full_stack", 0),
                                active_listings_total=scarcity_struct.get("active_listings_total", 0),
                                cohort_premiums=scarcity_struct.get("cohort_premiums", []),
                                personas=personas,
                                pois=resolved_pois,
                                valuation_range=updates.get("valuation.model_range"),
                            )
                            if buyers_result and buyers_result.get("thesis"):
                                updates["buyers"] = {
                                    "thesis": buyers_result["thesis"],
                                    "catchment": buyers_result["catchment"],
                                    "campaignMath": buyers_result["campaignMath"],
                                    "generated_at": buyers_result["generated_at"],
                                    "model": buyers_result["model"],
                                    "attempt": buyers_result["attempt"],
                                }
                                updates["slot_status.buyers"] = "approved"
                                logger.info(
                                    f"  buyers narrative generated (attempt {buyers_result['attempt']}): "
                                    f"thesis + {len(buyers_result['catchment']['locations'])} catchment + campaign math"
                                )
                                self.emit.done(
                                    "buyers",
                                    "Buyer thesis drafted",
                                    attempt=buyers_result["attempt"],
                                    catchment_count=len(buyers_result["catchment"].get("locations") or []),
                                )
                            elif buyers_result and buyers_result.get("error"):
                                updates["buyers_narrative_error"] = buyers_result
                                updates["slot_status.buyers"] = "error"
                                logger.warning(f"  buyers narrative failed: {buyers_result.get('error')}")
                                self.emit.fail("buyers", buyers_result.get("error") or "buyers failed")
                            else:
                                updates["slot_status.buyers"] = "pending"
                                self.emit.done("buyers", "Buyer thesis pending")
                        except Exception as e:
                            logger.warning(f"  buyers narrative resolver threw: {e}")
                            updates["slot_status.buyers"] = "error"
                            updates["buyers_narrative_error"] = {"error": str(e), "attempts": 0}
                            self.emit.fail("buyers", str(e))
                elif pos and pos.get("error"):
                    updates["positioning_narrative_error"] = pos
                    updates["slot_status.positioning"] = "error"
                    logger.warning(f"  positioning narrative failed: {pos.get('error')}")
                    self.emit.fail("positioning", pos.get("error") or "positioning failed")
                else:
                    updates["slot_status.positioning"] = "pending"
                    self.emit.done("positioning", "Positioning frame pending")
            except Exception as e:
                logger.warning(f"  positioning narrative resolver threw: {e}")
                updates["slot_status.positioning"] = "error"
                updates["positioning_narrative_error"] = {"error": str(e), "attempts": 0}
                self.emit.fail("positioning", str(e))

        # "Your Home" activity feed — first-visit comparable baseline + the
        # durable "what changed since you last logged in" change log. Computed
        # inline (not only by the nightly refresh) so the feed is live within
        # seconds of submission.
        self._resolve_comparable_feed(updates)

        return updates

    def _resolve_comparable_feed(self, updates: Dict[str, Any]) -> None:
        """Build the first-visit comparable baseline + durable change log from
        the competitor map + comps just resolved into `updates` (overlaid on any
        prior slots), and stamp them onto `updates`. Diffs against the doc's
        previous snapshot. Extracted for direct testability."""
        try:
            slots_now = dict(self.report.get("slots") or {})
            for key in ("slots.competitor_map", "slots.best_comp", "slots.recent_comps"):
                if key in updates:
                    slots_now[key.split(".", 1)[1]] = updates[key]
            comparables = comparables_from_slots(slots_now)
            if not comparables:
                return
            events, state = comparable_events_from_slots(slots_now, self.report)
            updates["comparables"] = comparables
            updates["comparable_events"] = events
            updates["comparable_state"] = state
            updates["comparables_refreshed_at"] = datetime.utcnow()
            logger.info(
                f"  comparable feed: {len(comparables['closest_active'])} active, "
                f"{len(comparables['closest_sold'])} sold, {len(events)} events"
            )
        except Exception as e:
            logger.warning(f"  comparable feed resolver threw: {e}")

    def refresh_competitor_slots(self) -> Dict[str, Any]:
        """Lightweight nightly refresh: re-run ONLY the competitor matcher +
        recent comps against the current listing data (NO vision / Opus /
        scraping), then recompute the comparable feed. Returns a dict of $set
        updates (dotted keys, ready to apply to property_reports).

        Cheap — pure DB work — so it runs for every active report each night to
        keep the "what changed since you last logged in" change log growing:
        the matcher sees that night's freshly-scraped prices / methods / sales
        and `_resolve_comparable_feed` diffs them against last night's snapshot.
        """
        self._load_subject_property()
        if not self._subject:
            return {}

        updates: Dict[str, Any] = {"slots.data_pull_date": datetime.utcnow()}

        comps = self.recent_comparable_sales(n=6)
        if comps:
            updates["slots.recent_comps"] = comps
            updates["slots.best_comp"] = comps[0]

        competition = self.competition_count()
        if competition is not None:
            updates["slots.n_competitors"] = competition

        latlng = self.subject_latlng()
        if latlng:
            updates["lat"] = latlng[0]
            updates["lng"] = latlng[1]

        try:
            model_range = self.valuation_model_range()
            price_anchor = None
            if model_range and model_range.get("low") and model_range.get("high"):
                price_anchor = int((model_range["low"] + model_range["high"]) / 2)
            features_basic = derive_features_basic(self._subject)
            comp_map = resolve_competitor_map(
                self._subject, self.db, features_basic, price_anchor=price_anchor,
            )
            if comp_map and comp_map.get("competitors"):
                updates["slots.competitor_map"] = comp_map
                updates["slot_status.competitor_matches"] = "approved"
        except Exception as e:
            logger.warning(f"  competitor refresh threw: {e}")

        # Diff the freshly-recomputed slots against the doc's prior snapshot.
        self._resolve_comparable_feed(updates)
        return updates

    # ------------------------------------------------------------------ #
    # Subject lookup
    # ------------------------------------------------------------------ #

    def _load_subject_property(self) -> Optional[Dict[str, Any]]:
        """
        Find the Gold_Coast record for this property. Try property_id first
        (the source_id from AddressSearch maps to the suburb-collection _id),
        then fall back to address-string matching.
        """
        if self._subject is not None:
            return self._subject

        if not self.suburb_key:
            logger.warning("No suburb_key on report — cannot load subject property")
            return None

        try:
            coll = self.db[self.suburb_key]
        except Exception as e:
            logger.warning(f"Suburb collection {self.suburb_key} unavailable: {e}")
            return None

        # 1) Lookup by property_id (= source_id = _id of Gold_Coast suburb doc)
        if self.property_id:
            try:
                oid = ObjectId(self.property_id)
                doc = coll.find_one({"_id": oid})
                if doc:
                    self._subject = doc
                    return doc
            except Exception as e:
                logger.debug(f"property_id ObjectId lookup failed: {e}")

        # 2) Fallback: address string match (case-insensitive)
        try:
            # Normalise the address — strip "QLD 4226" trailing bits + collapse spaces
            normalised = re.sub(r"\s+QLD\s+\d{4}.*$", "", self.address, flags=re.I).strip()
            normalised = re.sub(r"\s+", r"\\s+", re.escape(normalised))
            doc = coll.find_one({"address": {"$regex": f"^{normalised}", "$options": "i"}})
            if doc:
                self._subject = doc
                return doc
        except Exception as e:
            logger.debug(f"Address fallback lookup failed: {e}")

        logger.info(f"Subject property not found in {self.suburb_key} for {self.address}")
        return None

    # ------------------------------------------------------------------ #
    # Slot methods
    # ------------------------------------------------------------------ #

    def property_facts(self) -> Optional[Dict[str, Any]]:
        """Property inventory + photos from the Gold_Coast doc.

        Photo selection (Day 4 update):
          1. Collect all candidate URLs from `property_images` / `domain_image_urls`.
          2. Score with GPT-4o-mini to find the best hero shot.
          3. Promote the AI-picked photo to role=hero, rest become gallery.
          4. If AI scoring fails (no key, API error), fall back to the scraper's
             `domain_hero_image_url` so we always produce *something*.
        """
        s = self._subject
        if not s:
            return None

        scraper_hero = s.get("domain_hero_image_url")
        # Photo source priority:
        #   1. property_images_refreshed — full-res `b.domainstatic.com.au` URLs
        #                                  reconstructed inline from rimh2 thumbnail
        #                                  paths. Most reliable for off-market
        #                                  homes where Apollo state only carries
        #                                  the most-recent sale's hero.
        #   2. property_images_original  — raw bucket URLs (bucket-api.domain.com.au).
        #                                  Full-res JPEGs, present for currently-listed homes.
        #   3. scraped_property_images   — same shape as #2.
        #   4. domain_image_urls         — signed rimh2 URLs at fixed 150px thumbnail size.
        #                                  Avoid for display — used by the inline_scrape
        #                                  module as the URL-path source.
        #   5. property_images           — Azure Blob mirror, returns 403 publicly. Last resort.
        #
        # Merge order: refreshed first, then originals appended (deduped by URL).
        # An owner whose home is currently-listed will get the bucket-api URLs
        # appended too — refreshed is a superset for off-market only.
        refreshed = s.get("property_images_refreshed") or []
        originals = (
            s.get("property_images_original")
            or s.get("scraped_property_images")
            or []
        )
        merged: List[str] = []
        seen_paths: set = set()
        for url in list(refreshed) + list(originals):
            if not isinstance(url, str):
                continue
            url = url.rstrip("\\").strip()
            if not url:
                continue
            # Dedupe by image-path stem so a refreshed b.domainstatic URL and the
            # equivalent bucket-api URL don't both appear.
            path_stem = url.split("/")[-1].split("?")[0]
            if path_stem in seen_paths:
                continue
            seen_paths.add(path_stem)
            merged.append(url)
        if not merged:
            merged = s.get("domain_image_urls") or s.get("property_images") or []
        candidates = merged
        # Deduplicate, keep order. Only prepend the scraper_hero when we have
        # nothing else — `domain_hero_image_url` is a signed rimh2 URL that
        # serves a 150px thumbnail, so it's only a usable hero when there's
        # genuinely no full-res alternative.
        seen = set()
        clean_candidates: List[str] = []
        scraper_hero_is_thumbnail = (
            isinstance(scraper_hero, str)
            and "rimh2.domainstatic.com.au" in scraper_hero
            and "/fit-in/" not in scraper_hero
        )
        if scraper_hero and (not merged or not scraper_hero_is_thumbnail):
            clean_candidates.append(scraper_hero)
            seen.add(scraper_hero)
        for url in candidates:
            if isinstance(url, str) and url not in seen:
                clean_candidates.append(url)
                seen.add(url)

        # AI hero pick (Day 4) — falls back to the first clean candidate on
        # failure. Don't default back to the scraper_hero when it's the known
        # 150px rimh2 thumbnail — that just produces a broken hero image.
        hero_url = (
            scraper_hero if (scraper_hero and not scraper_hero_is_thumbnail)
            else (clean_candidates[0] if clean_candidates else scraper_hero)
        )
        hero_pick_meta = None
        if clean_candidates:
            self.emit.start("gallery", f"Selecting your hero shot from {len(clean_candidates)} photos")
            try:
                pick = score_and_pick_hero(clean_candidates[:8])
                if pick and pick.get("hero_url"):
                    hero_url = pick["hero_url"]
                    hero_pick_meta = {
                        "score": pick.get("hero_score"),
                        "reason": pick.get("hero_reason"),
                        "model": pick.get("model"),
                        "picked_by": "ai",
                    }
                    logger.info(
                        f"  hero AI-picked (score={pick.get('hero_score')}): {hero_url[:80]}"
                    )
                self.emit.done(
                    "gallery",
                    f"Hero shot picked from {len(clean_candidates)} photos",
                    photo_count=len(clean_candidates),
                    hero_url=hero_url,
                    picked_by="ai" if hero_pick_meta else "scraper",
                )
            except Exception as e:
                logger.warning(f"  hero photo scoring threw: {e}")
                self.emit.done(
                    "gallery",
                    f"Photos selected ({len(clean_candidates)})",
                    photo_count=len(clean_candidates),
                    hero_url=hero_url,
                    picked_by="scraper_fallback",
                )

        if not hero_url and clean_candidates:
            hero_url = clean_candidates[0]

        photos = []
        if hero_url:
            entry = {"url": hero_url, "role": "hero"}
            if hero_pick_meta:
                entry["meta"] = hero_pick_meta
            photos.append(entry)
        # Up to 6 gallery photos, excluding the hero
        for url in clean_candidates:
            if url == hero_url:
                continue
            if len([p for p in photos if p["role"] == "gallery"]) >= 6:
                break
            photos.append({"url": url, "role": "gallery"})

        return {
            "bed": _to_int(s.get("bedrooms")),
            "bath": _to_int(s.get("bathrooms")),
            "car": _to_int(s.get("carspaces") or s.get("car_spaces")),
            "land_area_sqm": _to_int(s.get("land_size_sqm") or s.get("lot_size_sqm")),
            "internal_area_sqm": _to_int(s.get("total_floor_area")),
            "property_type": s.get("property_type"),
            "year_built": _to_int(s.get("year_built")),
            "photos": photos,
            "cadastral": {
                "lot": s.get("LOT"),
                "plan": s.get("PLAN"),
                "council": s.get("LOCAL_AUTHORITY"),
            },
            "is_sold_record": s.get("listing_status") == "sold",
            "is_for_sale_record": s.get("listing_status") == "for_sale",
        }

    def subject_latlng(self) -> Optional[tuple]:
        s = self._subject
        if not s:
            return None
        lat = s.get("LATITUDE") or s.get("latitude") or s.get("lat")
        lng = s.get("LONGITUDE") or s.get("longitude") or s.get("lng")
        if lat is None or lng is None:
            return None
        try:
            return (float(lat), float(lng))
        except (TypeError, ValueError):
            return None

    def valuation_model_range(self) -> Optional[Dict[str, int]]:
        """
        Working valuation range based on the subject + a few comps.

        Phase 3 Slice 1: simple median-of-comps approach, adjusted for
        bedroom-count match. The full CatBoost / hedonic pipeline lives
        elsewhere; this is the lightweight indicative range that shows
        in the under-review state until the consultant finalises.
        """
        s = self._subject
        if not s:
            return None

        bed = _to_int(s.get("bedrooms"))
        if not bed:
            return None

        try:
            cursor = self.db[self.suburb_key].find(
                {
                    "listing_status": "sold",
                    "bedrooms": bed,
                    "sale_price": {"$exists": True, "$ne": None},
                },
                {"sale_price": 1, "sale_date": 1, "bedrooms": 1},
            ).sort("sale_date", -1).limit(20)
            comps = list(cursor)
        except Exception as e:
            logger.warning(f"valuation_model_range query failed: {e}")
            return None

        prices = []
        for c in comps:
            p = _parse_price(c.get("sale_price"))
            if p:
                prices.append(p)
        if len(prices) < 3:
            return None

        prices.sort()
        median = prices[len(prices) // 2]
        # Wide range: median +/- 10% as the indicative working window
        return {
            "low": int(median * 0.90),
            "high": int(median * 1.10),
            "method": "median_of_recent_bedroom_matched_sales",
            "comp_count": len(prices),
            "note": "Working range only — final figure follows the consultant review.",
        }

    def market_state(self) -> Optional[Dict[str, Any]]:
        """Per-suburb market state from precomputed collections."""
        if not self.suburb_display:
            return None
        out: Dict[str, Any] = {}

        # Days on market
        try:
            dom = self.db["precomputed_market_charts"].find_one(
                {"suburb": self.suburb_display, "chart_type": "days_on_market"},
                {"_id": 0, "latest_quarter_median": 1, "historical_median": 1, "yoy_change_days": 1},
            )
            if dom:
                out["median_dom"] = _to_int(dom.get("latest_quarter_median"))
                out["median_dom_historical"] = _to_int(dom.get("historical_median"))
                out["dom_yoy_change"] = dom.get("yoy_change_days")
        except Exception as e:
            logger.debug(f"DOM lookup failed: {e}")

        # Indexed price growth
        try:
            ip = self.db["precomputed_indexed_prices"].find_one(
                {"suburb": self.suburb_display},
                {
                    "_id": 0, "latest_price": 1, "total_growth_pct": 1,
                    "rolling_12m_yoy_pct": 1, "rolling_12m_median_price": 1,
                    "baseline_period": 1, "transaction_count": 1,
                },
            )
            if ip:
                out["latest_median_price"] = _to_int(ip.get("latest_price"))
                out["rolling_12m_median"] = _to_int(ip.get("rolling_12m_median_price"))
                out["rolling_12m_yoy_pct"] = ip.get("rolling_12m_yoy_pct")
                out["growth_since_baseline_pct"] = ip.get("total_growth_pct")
                out["baseline_period"] = ip.get("baseline_period")
                out["sold_transaction_count"] = _to_int(ip.get("transaction_count"))
        except Exception as e:
            logger.debug(f"Indexed price lookup failed: {e}")

        # Active listings count
        try:
            out["active_listings_count"] = self.db[self.suburb_key].count_documents(
                {"listing_status": "for_sale"}
            )
        except Exception as e:
            logger.debug(f"Active count failed: {e}")

        return out or None

    def valuation_comps_from_engine(self) -> Optional[List[Dict[str, Any]]]:
        """
        Comps from the precompute_valuations engine output, shaped for the
        mini-site ValuationTab. Reads `valuation_data.recent_sales[]` where
        `included_in_valuation == True` (the comps the engine actually used
        to compute the reconciled range) and maps engine field names to the
        frontend Comp schema.

        Schema produced (each item, matching `homeFixture.ts` `Comp` type):
          { address, soldPrice, soldDate, land, internal, bedrooms,
            bathrooms, condition, notes, adjustedToSubject, weight_pct }

        Engine schema mapping:
          - original_sale_price → soldPrice (raw $)
          - sale_date (epoch ms or ISO) → soldDate
          - features.basic.land_size_sqm → land
          - features.basic.floor_area_sqm → internal
          - features.basic.bedrooms / bathrooms → bedrooms / bathrooms
          - adjustment_result.adjusted_price → adjustedToSubject
          - weight.normalized OR weight.raw_weight * 100 → weight_pct
          - narrative → notes (one-line summary)
          - condition: derived from features.basic.condition or left as ""

        Returns None if the subject has no valuation_data yet (engine
        hasn't run, or engine excluded the subject due to missing data).
        Returns empty list if the engine ran but no comps were included.
        """
        s = self._subject
        if not s:
            return None
        val = s.get("valuation_data") or {}
        recent_sales = val.get("recent_sales") or []
        if not recent_sales:
            # Engine ran but produced no comps (e.g. exclusion_reason).
            # Return empty list rather than None so the resolver clears any
            # stale comps from a previous run.
            return []

        included = [c for c in recent_sales if c.get("included_in_valuation")]
        # Sort by normalised weight desc so top-N is most-influential first
        def _w(c: Dict[str, Any]) -> float:
            w = c.get("weight")
            if isinstance(w, dict):
                try:
                    return float(w.get("normalized") or w.get("raw_weight") or 0)
                except (TypeError, ValueError):
                    return 0.0
            try:
                return float(w or 0)
            except (TypeError, ValueError):
                return 0.0
        included.sort(key=_w, reverse=True)

        out: List[Dict[str, Any]] = []
        for c in included:
            adj = c.get("adjustment_result") or {}
            features = (c.get("features") or {}).get("basic") or {}
            sale_date_raw = c.get("sale_date")
            sale_date_str = None
            if isinstance(sale_date_raw, (int, float)):
                try:
                    sale_date_str = datetime.utcfromtimestamp(sale_date_raw / 1000.0).strftime("%Y-%m-%d")
                except (OSError, ValueError):
                    sale_date_str = None
            elif isinstance(sale_date_raw, str):
                sale_date_str = sale_date_raw[:10]
            elif isinstance(sale_date_raw, datetime):
                sale_date_str = sale_date_raw.strftime("%Y-%m-%d")

            # Normalise address — strip ", QLD 4226" tail + collapse double spaces
            addr = (c.get("address") or "").strip()
            addr = re.sub(r",?\s*(QLD|VIC|NSW|ACT|NT|SA|TAS|WA)\s*\d{4}\s*$", "", addr, flags=re.I)
            addr = re.sub(r"\s{2,}", " ", addr).rstrip(",").strip()

            out.append({
                "address": addr or "Unknown",
                "soldPrice": _to_int(c.get("original_sale_price")) or _to_int(c.get("price")),
                "soldDate": sale_date_str,
                "land": _to_int(features.get("land_size_sqm")),
                "internal": _to_int(features.get("floor_area_sqm")),
                "bedrooms": _to_int(features.get("bedrooms")),
                "bathrooms": _to_int(features.get("bathrooms")),
                "condition": features.get("condition_label") or "",
                "notes": (c.get("narrative") or "")[:280],  # keep notes terse
                "adjustedToSubject": _to_int(adj.get("adjusted_price")),
                "weight_pct": round(_w(c) * 100),
            })
        return out

    def recent_comparable_sales(self, n: int = 6) -> List[Dict[str, Any]]:
        """
        Top-N most-similar recent sales. Sorted by recency + bedroom match.
        Each comp gets: address, sale_date, sale_price (int), bedrooms,
        bathrooms, land_size_sqm, total_floor_area, photo URL if available.
        """
        s = self._subject
        if not s:
            return []

        bed = _to_int(s.get("bedrooms"))
        bath = _to_int(s.get("bathrooms"))

        query: Dict[str, Any] = {
            "listing_status": "sold",
            "sale_price": {"$exists": True, "$ne": None},
        }
        if bed:
            # Allow +/- 1 bedroom for soft matching
            query["bedrooms"] = {"$in": [bed - 1, bed, bed + 1]}

        try:
            cursor = self.db[self.suburb_key].find(
                query,
                {
                    "address": 1, "street_address": 1, "sale_price": 1,
                    "sale_date": 1, "bedrooms": 1, "bathrooms": 1,
                    "carspaces": 1, "land_size_sqm": 1, "total_floor_area": 1,
                    "property_type": 1, "domain_hero_image_url": 1,
                    "listing_url": 1,
                },
            ).sort("sale_date", -1).limit(n * 3)  # Over-fetch so we can rank
            candidates = list(cursor)
        except Exception as e:
            logger.warning(f"recent_comparable_sales query failed: {e}")
            return []

        # Skip the subject itself
        subj_id = s.get("_id")
        candidates = [c for c in candidates if c.get("_id") != subj_id]

        def score(c):
            cbed = _to_int(c.get("bedrooms")) or 0
            cbath = _to_int(c.get("bathrooms")) or 0
            bed_match = 0 if (bed and cbed == bed) else 2 if (bed and abs(cbed - bed) == 1) else 4
            bath_match = 0 if (bath and cbath == bath) else 1 if (bath and abs(cbath - bath) == 1) else 2
            return bed_match + bath_match

        candidates.sort(key=score)
        chosen = candidates[:n]

        out = []
        for c in chosen:
            price = _parse_price(c.get("sale_price"))
            out.append({
                "address": c.get("address") or c.get("street_address"),
                "sale_price": price,
                "sale_date": _stringify_date(c.get("sale_date")),
                "bedrooms": _to_int(c.get("bedrooms")),
                "bathrooms": _to_int(c.get("bathrooms")),
                "carspaces": _to_int(c.get("carspaces")),
                "land_size_sqm": _to_int(c.get("land_size_sqm")),
                "total_floor_area": _to_int(c.get("total_floor_area")),
                "property_type": c.get("property_type"),
                "photo_url": c.get("domain_hero_image_url"),
                "listing_url": c.get("listing_url"),
            })
        return out

    def competition_count(self) -> Optional[int]:
        """
        How many active listings sit in the same bedroom band right now.
        This is the "you have N direct competitors" number for the
        share-moment card.
        """
        s = self._subject
        if not s:
            return None
        bed = _to_int(s.get("bedrooms"))
        if not bed:
            return None
        try:
            return self.db[self.suburb_key].count_documents({
                "listing_status": "for_sale",
                "bedrooms": {"$in": [bed - 1, bed, bed + 1]},
            })
        except Exception as e:
            logger.debug(f"competition_count failed: {e}")
            return None


# ---------------------------------------------------------------------- #
# Small helpers
# ---------------------------------------------------------------------- #

def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_price(v: Any) -> Optional[int]:
    """Parse '$1,420,000' or 1420000 into int dollars."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        digits = re.sub(r"[^\d]", "", v)
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _stringify_date(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str):
        return v[:10]
    return None
