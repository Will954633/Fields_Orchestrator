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
from scripts.property_reports.cohort_premiums import compute_cohort_premiums
from scripts.property_reports.scarcity_narrative import (
    resolve_scarcity_narrative, cohort_premiums_to_sold_cohort_premiums,
)

logger = logging.getLogger(__name__)


class SlotResolver:
    """
    Builds the slot dictionary for one property_reports doc.

    Usage:
        resolver = SlotResolver(report_doc, gold_coast_db)
        slots = resolver.resolve_all()
        # → returns a dict ready to $set into property_reports
    """

    def __init__(self, report_doc: Dict[str, Any], db: Database):
        self.report = report_doc
        self.db = db
        self.suburb_key = report_doc.get("suburb_key", "").lower()
        self.suburb_display = report_doc.get("suburb", "")
        self.address = report_doc.get("address", "")
        self.property_id = report_doc.get("property_id")

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
        self._load_subject_property()

        updates: Dict[str, Any] = {
            "slots.data_pull_date": datetime.utcnow(),
        }

        # Subject property facts
        prop = self.property_facts()
        if prop:
            updates["property"] = prop

        # Valuation model range (a working range, not the human-reviewed final)
        model_range = self.valuation_model_range()
        if model_range:
            updates["valuation.model_range"] = model_range

        # Valuation comps from the engine output (Path A — produced by
        # process 301 + the nightly precompute job). When the subject has
        # `valuation_data.recent_sales[]` we surface the per-comp adjustments
        # the engine computed. Auto-promote slot_status.comps once the comps
        # are populated — this is interim until the analyst-review gate
        # lands on Day 14, at which point the promotion moves to the ops
        # dashboard sign-off step.
        eng_comps = self.valuation_comps_from_engine()
        if eng_comps is not None:
            updates["valuation.comps"] = eng_comps
            if eng_comps:
                # Engine produced usable comps → expose to mini-site
                updates["slot_status.comps"] = "approved"
                updates["valuation.comps_resolved_at"] = datetime.utcnow()
            else:
                # Engine ran but excluded the subject (no floor_area, etc.)
                # Leave slot pending — placeholder shows on the page.
                updates["slot_status.comps"] = "pending"

        # Market state for the suburb
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
                elif narrative and narrative.get("error"):
                    updates["market_narrative_error"] = narrative
                    updates["slot_status.market_narrative"] = "error"
                    logger.warning(f"  market_narrative failed: {narrative.get('error')}")
                else:
                    updates["slot_status.market_narrative"] = "pending"
            except Exception as e:
                logger.warning(f"  market_narrative resolver threw: {e}")
                updates["slot_status.market_narrative"] = "error"
                updates["market_narrative_error"] = {"error": str(e), "attempts": 0}

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
                    logger.info(
                        f"  scarcity features: {len(scarcity.get('notable_features', []))} notable | "
                        f"{scarcity.get('active_matching_full_stack')}/{scarcity.get('active_listings_total')} active in catchment match full stack"
                    )
            except Exception as e:
                logger.warning(f"  scarcity_features resolver threw: {e}")

        # Walking distances to nearest POIs (Day 4). Requires lat/lng — skip
        # for subjects we can't geolocate (vacant cadastral lots etc.).
        resolved_pois: List[Dict[str, Any]] = []
        if latlng:
            try:
                resolved_pois = resolve_pois(latlng[0], latlng[1])
                if resolved_pois:
                    updates["pois"] = resolved_pois
                    updates["slot_status.walking_distance"] = "approved"
                    logger.info(f"  walking distances resolved for {len(resolved_pois)} POIs")
                else:
                    updates["slot_status.walking_distance"] = "pending"
            except Exception as e:
                logger.warning(f"  walking distance resolver threw: {e}")
                updates["slot_status.walking_distance"] = "error"

        # Scarcity narrative (Day 9) — Opus 4.7 turns scarcity_features +
        # cohort_premiums + pois into the three user-facing strings the
        # mini-site renders: headline, combinatorialMatch, walkingDistanceMonopoly.
        # Deterministic mapping of cohort_premiums → soldCohortPremiums also
        # happens here (only reliable premiums surface). Auto-promotes slot
        # on narrative success; analyst review gate lands on Day 14.
        scarcity_struct = updates.get("scarcity_features")
        if scarcity_struct and scarcity_struct.get("notable_features"):
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
                elif narrative and narrative.get("error"):
                    updates["scarcity_narrative_error"] = narrative
                    updates["slot_status.scarcity"] = "error"
                    logger.warning(f"  scarcity narrative failed: {narrative.get('error')}")
                else:
                    updates["slot_status.scarcity"] = "pending"
            except Exception as e:
                logger.warning(f"  scarcity narrative resolver threw: {e}")
                updates["slot_status.scarcity"] = "error"
                updates["scarcity_narrative_error"] = {"error": str(e), "attempts": 0}

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
        candidates = s.get("property_images") or s.get("domain_image_urls") or []
        # Deduplicate, keep order
        seen = set()
        clean_candidates: List[str] = []
        if scraper_hero:
            clean_candidates.append(scraper_hero)
            seen.add(scraper_hero)
        for url in candidates:
            if isinstance(url, str) and url not in seen:
                clean_candidates.append(url)
                seen.add(url)

        # AI hero pick (Day 4) — falls back to scraper hero on failure
        hero_url = scraper_hero
        hero_pick_meta = None
        if clean_candidates:
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
            except Exception as e:
                logger.warning(f"  hero photo scoring threw: {e}")

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
