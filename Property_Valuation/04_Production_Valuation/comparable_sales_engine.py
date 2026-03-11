"""
Comparable Sales Engine for Production Valuation System
========================================================

This module implements a comprehensive comparable sales engine that calculates
multiple tiers of comparable sales features for the Iteration 08 model:

1. Standard Comparables (15 features) - 2km radius, 90 days
2. Relaxed Comparables (6 features) - 5km radius, 180 days, for outlier-prone properties
3. Waterfront Comparables (7 features) - Waterfront-specific matching
4. Time-Adjusted Comparables (4 features) - Time-decay adjusted prices

Author: Property Valuation Production System
Date: 20th November 2025
"""

import time
import pymongo
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Optional, Tuple
import logging

from cosmos_retry import cosmos_retry_call

logger = logging.getLogger(__name__)


def _parse_sale_price(raw):
    """Parse sale price string like '$1,580,000' to int."""
    try:
        return int(str(raw).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


class ComparableSalesEngine:
    """
    Comprehensive comparable sales engine for property valuation
    """
    
    def __init__(self, mongo_client: pymongo.MongoClient, config):
        """
        Initialize comparable sales engine
        
        Args:
            mongo_client: MongoDB client connection
            config: Configuration module with settings
        """
        self.mongo_client = mongo_client
        self.config = config
        self.gold_coast_db = mongo_client[config.GOLD_COAST_DB]
        self.recent_db = mongo_client[config.DB_RECENT_SOLD]

        # Cache for historical sales
        self.sales_cache = {}
        self.cache_valid_until = None

        # Growth rates cache
        self.suburb_growth_rates = {}

        # Cache collection names to avoid repeated list_collection_names() calls (RU-expensive on Cosmos DB)
        self._gold_coast_collection_names_cache = cosmos_retry_call(self.gold_coast_db.list_collection_names)
        self._recent_collection_names_cache = cosmos_retry_call(self.recent_db.list_collection_names)
        
    def haversine_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points in kilometers
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return 6371 * c
    
    def get_recent_sales(self, days: int = 365) -> pd.DataFrame:
        """
        Get all recent sales from Gold Coast database
        
        Args:
            days: Number of days to look back
            
        Returns:
            DataFrame of recent sales with all relevant fields
        """
        # Check cache
        if (self.cache_valid_until and 
            datetime.now() < self.cache_valid_until and
            days in self.sales_cache):
            logger.debug(f"Using cached sales data for {days} days")
            return self.sales_cache[days]
        
        logger.info(f"Loading sales from last {days} days from MongoDB...")
        cutoff_date = datetime.now() - timedelta(days=days)
        all_sales = []
        
        # Get all collections (suburbs) from cache
        collections = [c for c in self._gold_coast_collection_names_cache
                      if not c.startswith('system.')]

        logger.info(f"Querying {len(collections)} suburb collections...")

        for coll_name in collections:
            collection = self.gold_coast_db[coll_name]

            # Query for properties with sales in timeline
            # Based on extract_all_enriched_properties.py
            query = {
                'scraped_data.property_timeline': {'$exists': True, '$ne': []},
                'scraped_data.property_timeline.category': 'Sale',
                'scraped_data.property_timeline.is_sold': True,
                'LATITUDE': {'$exists': True, '$ne': None},
                'LONGITUDE': {'$exists': True, '$ne': None}
            }

            properties = cosmos_retry_call(collection.find, query)
            
            for prop in properties:
                # Extract sale data from property_timeline
                timeline = prop.get('scraped_data', {}).get('property_timeline', [])
                
                # Get all sales (not just recent - we'll filter by date later)
                sales = [e for e in timeline 
                        if e.get('category') == 'Sale' 
                        and e.get('is_sold') == True]
                
                if not sales:
                    continue
                
                # Get most recent sale
                most_recent_sale = sales[0]
                sale_price = most_recent_sale.get('price')  # Note: 'price' not 'value'
                sale_date = most_recent_sale.get('date')
                
                if not sale_price or not sale_date:
                    continue
                
                # Convert date if needed
                if isinstance(sale_date, str):
                    sale_date = pd.to_datetime(sale_date)
                
                # Filter by date
                if sale_date < cutoff_date:
                    continue
                
                # Get property features
                features_dict = prop.get('scraped_data', {}).get('features', {})
                house_plan = prop.get('house_plan', {})
                
                # Get GPT data if available
                gpt_data = prop.get('gpt_valuation_data', {})
                if not gpt_data:
                    # Try alternative location
                    gpt_data = prop.get('property_valuation_data', {})
                
                # Get OSM data if available
                osm_data = prop.get('osm_location_features', {})
                
                sale_data = {
                    'suburb': prop.get('LOCALITY', coll_name.upper().replace('_', ' ')),
                    'latitude': prop.get('LATITUDE'),
                    'longitude': prop.get('LONGITUDE'),
                    'sale_price': sale_price,
                    'sale_date': sale_date,
                    'bedrooms': features_dict.get('bedrooms'),
                    'bathrooms': features_dict.get('bathrooms'),
                    'car_spaces': features_dict.get('car_spaces'),
                    'lot_size_sqm': prop.get('lot_size_sqm'),
                    'property_type': features_dict.get('property_type'),
                    'gpt_floor_area_sqm': house_plan.get('floor_area_sqm') or gpt_data.get('gpt_floor_area_sqm'),
                    'osm_canal_frontage': osm_data.get('osm_canal_frontage', False),
                    'osm_waterfront_type': osm_data.get('osm_waterfront_type', 'None'),
                    'quality_score_avg': self._calculate_avg_quality_score(gpt_data)
                }
                
                all_sales.append(sale_data)

        # --- Merge recent sold data from Target_Market_Sold_Last_12_Months ---
        seen = set()
        for s in all_sales:
            d = s['sale_date']
            date_key = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
            seen.add((date_key, int(s['sale_price']) if s['sale_price'] else 0))

        recent_collections = [c for c in self._recent_collection_names_cache
                              if not c.startswith('system.')]
        added_from_recent = 0

        for coll_name in recent_collections:
            collection = self.recent_db[coll_name]
            for prop in cosmos_retry_call(collection.find, {}):
                raw_price = prop.get('sale_price')
                raw_date = prop.get('sale_date')
                if not raw_price or not raw_date:
                    continue

                price = _parse_sale_price(raw_price)
                if not price:
                    continue

                try:
                    sale_date = pd.to_datetime(str(raw_date)[:10])
                except (ValueError, TypeError):
                    continue

                if sale_date < cutoff_date:
                    continue

                date_key = sale_date.strftime('%Y-%m-%d')
                if (date_key, price) in seen:
                    continue
                seen.add((date_key, price))

                # Floor area from processing_status or floor_plan_analysis
                floor_area = None
                ps = prop.get('processing_status', {}) or {}
                floor_area = ps.get('total_floor_area_sqm') or ps.get('internal_floor_area_sqm')
                if not floor_area:
                    fpa = prop.get('floor_plan_analysis', {}) or {}
                    floor_area = fpa.get('total_floor_area') or fpa.get('internal_floor_area')

                # GPT quality data
                gpt_data = prop.get('property_valuation_data', {}) or {}

                sale_data = {
                    'suburb': prop.get('suburb_scraped', coll_name.upper().replace('_', ' ')),
                    'latitude': None,   # Not available in Target_Market
                    'longitude': None,
                    'sale_price': price,
                    'sale_date': sale_date,
                    'bedrooms': prop.get('bedrooms'),
                    'bathrooms': prop.get('bathrooms'),
                    'car_spaces': prop.get('carspaces'),
                    'lot_size_sqm': prop.get('land_size_sqm'),
                    'property_type': prop.get('property_type'),
                    'gpt_floor_area_sqm': floor_area,
                    'osm_canal_frontage': False,
                    'osm_waterfront_type': 'None',
                    'quality_score_avg': self._calculate_avg_quality_score(gpt_data)
                }
                all_sales.append(sale_data)
                added_from_recent += 1

        if added_from_recent > 0:
            logger.info(f"Merged {added_from_recent} additional sales from Target_Market_Sold_Last_12_Months")

        # Convert to DataFrame
        df = pd.DataFrame(all_sales)

        if len(df) > 0:
            logger.info(f"Loaded {len(df)} sales from {len(collections)} suburbs (+ {len(recent_collections)} recent-sold suburbs)")
            logger.info(f"Date range: {df['sale_date'].min()} to {df['sale_date'].max()}")
        else:
            logger.warning(f"No sales found in the last {days} days")
        
        # Cache it
        self.sales_cache[days] = df
        self.cache_valid_until = datetime.now() + timedelta(hours=1)
        
        return df
    
    def _calculate_avg_quality_score(self, gpt_data: dict) -> Optional[float]:
        """Calculate average GPT quality score"""
        quality_fields = [
            'exterior_condition_score', 'roof_condition_score', 
            'cladding_condition_score', 'paint_quality_score',
            'interior_condition_score', 'flooring_quality_score',
            'kitchen_quality_score', 'bathroom_quality_score',
            'natural_light_score', 'property_presentation_score',
            'market_appeal_score', 'modern_features_score',
            'landscaping_quality_score', 'outdoor_entertainment_score'
        ]
        
        scores = [gpt_data.get(field) for field in quality_fields 
                 if gpt_data.get(field) is not None]
        
        if scores:
            return np.mean(scores)
        return None
    
    def calculate_all_comparable_features(self, property_doc: dict, 
                                         base_features: dict) -> dict:
        """
        Calculate all comparable sales features
        
        Args:
            property_doc: Full property document from MongoDB
            base_features: Base features dictionary with coordinates, etc.
            
        Returns:
            Dictionary with all comparable features
        """
        features = {}
        
        # Get recent sales (up to 1 year for flexibility)
        recent_sales = self.get_recent_sales(days=365)
        
        if len(recent_sales) == 0:
            logger.warning("No recent sales found - returning null comparable features")
            return self._get_all_null_features()
        
        # Calculate distances to all sales
        lat = base_features.get('latitude')
        lon = base_features.get('longitude')
        
        if not lat or not lon:
            logger.warning("Missing coordinates - cannot calculate comparables")
            return self._get_all_null_features()
        
        recent_sales['distance_km'] = recent_sales.apply(
            lambda r: self.haversine_distance(lat, lon, 
                                              r['latitude'], r['longitude']),
            axis=1
        )
        
        # Calculate days since sale
        recent_sales['days_since_sale'] = recent_sales['sale_date'].apply(
            lambda d: (datetime.now() - d).days
        )
        
        # 1. Standard Comparables (2km, 90 days) - 15 features
        standard_features = self._calculate_standard_comparables(
            recent_sales, base_features, property_doc
        )
        features.update(standard_features)
        
        # 2. Determine if property is outlier-prone
        is_outlier_prone = self._is_outlier_prone(base_features, standard_features)
        
        # 3. Relaxed Comparables (5km, 180 days) - 6 features
        if is_outlier_prone:
            relaxed_features = self._calculate_relaxed_comparables(
                recent_sales, base_features
            )
            features.update(relaxed_features)
        else:
            features.update(self._get_null_relaxed_features())
        
        # 4. Waterfront Comparables (if applicable) - 7 features
        osm_data = property_doc.get('osm_location_features', {})
        is_waterfront = osm_data.get('osm_canal_frontage', False)
        
        if is_waterfront:
            waterfront_features = self._calculate_waterfront_comparables(
                recent_sales, base_features, osm_data
            )
            features.update(waterfront_features)
        else:
            features.update(self._get_null_waterfront_features())
        
        # 5. Time-Adjusted Comparables - 4 features
        time_adjusted_features = self._calculate_time_adjusted_comparables(
            recent_sales, base_features
        )
        features.update(time_adjusted_features)
        
        return features
    
    def _calculate_standard_comparables(self, sales_df: pd.DataFrame, 
                                       base_features: dict,
                                       property_doc: dict) -> dict:
        """
        Calculate standard comparable sales features (2km, 90 days)
        
        Returns 15 features:
        1. comparable_count_90d
        2. comparable_median_price_90d
        3. comparable_mean_price_90d
        4. comparable_avg_price_per_sqm_90d
        5. comparable_price_range_90d
        6. comparable_std_dev_90d
        7. similar_features_median_price_90d
        8. similar_features_count_90d
        9. comparable_min_distance_km
        10. comparable_max_distance_km
        11. comparable_avg_age_days
        12. comparable_price_per_sqm_std
        13. comparable_lot_size_median
        14. comparable_floor_area_median
        15. comparable_quality_score_avg
        """
        features = {}
        
        # Filter by time and distance
        comps = sales_df[
            (sales_df['distance_km'] <= self.config.COMPARABLE_RADIUS_KM) &
            (sales_df['days_since_sale'] <= self.config.COMPARABLE_DAYS)
        ].copy()
        
        # Basic count
        features['comparable_count_90d'] = len(comps)
        
        if len(comps) == 0:
            return self._get_null_standard_features()
        
        # Price statistics
        features['comparable_median_price_90d'] = comps['sale_price'].median()
        features['comparable_mean_price_90d'] = comps['sale_price'].mean()
        features['comparable_price_range_90d'] = (
            comps['sale_price'].max() - comps['sale_price'].min()
        )
        features['comparable_std_dev_90d'] = comps['sale_price'].std()
        
        # Price per sqm (using floor area if available)
        comps_with_area = comps[
            comps['gpt_floor_area_sqm'].notna() & 
            (comps['gpt_floor_area_sqm'] > 0)
        ]
        
        if len(comps_with_area) > 0:
            price_per_sqm = comps_with_area['sale_price'] / comps_with_area['gpt_floor_area_sqm']
            features['comparable_avg_price_per_sqm_90d'] = price_per_sqm.mean()
            features['comparable_price_per_sqm_std'] = price_per_sqm.std()
        else:
            features['comparable_avg_price_per_sqm_90d'] = None
            features['comparable_price_per_sqm_std'] = None
        
        # Similar features comparables (same bed/bath)
        target_beds = base_features.get('bedrooms')
        target_baths = base_features.get('bathrooms')
        
        similar = comps[
            (comps['bedrooms'] == target_beds) &
            (comps['bathrooms'] == target_baths)
        ]
        
        features['similar_features_count_90d'] = len(similar)
        if len(similar) > 0:
            features['similar_features_median_price_90d'] = similar['sale_price'].median()
        else:
            features['similar_features_median_price_90d'] = None
        
        # Distance metrics
        features['comparable_min_distance_km'] = comps['distance_km'].min()
        features['comparable_max_distance_km'] = comps['distance_km'].max()
        
        # Age metrics
        features['comparable_avg_age_days'] = comps['days_since_sale'].mean()
        
        # Lot size median
        lot_sizes = comps[comps['lot_size_sqm'].notna() & (comps['lot_size_sqm'] > 0)]
        if len(lot_sizes) > 0:
            features['comparable_lot_size_median'] = lot_sizes['lot_size_sqm'].median()
        else:
            features['comparable_lot_size_median'] = None
        
        # Floor area median
        if len(comps_with_area) > 0:
            features['comparable_floor_area_median'] = comps_with_area['gpt_floor_area_sqm'].median()
        else:
            features['comparable_floor_area_median'] = None
        
        # Quality score average
        quality_comps = comps[comps['quality_score_avg'].notna()]
        if len(quality_comps) > 0:
            features['comparable_quality_score_avg'] = quality_comps['quality_score_avg'].mean()
        else:
            features['comparable_quality_score_avg'] = None
        
        return features
    
    def _is_outlier_prone(self, base_features: dict, 
                         standard_comp: dict) -> bool:
        """
        Determine if property is outlier-prone
        
        Criteria:
        - Large lot (>800 sqm)
        - Waterfront suburb
        - Low comparable coverage (<3 sales)
        """
        # Large lot
        lot_size = base_features.get('lot_size_sqm', 0) or 0
        is_large_lot = lot_size > 800
        
        # Waterfront suburb
        suburb = base_features.get('suburb', '')
        is_waterfront_suburb = suburb in self.config.WATERFRONT_SUBURBS
        
        # Low comparable coverage
        comp_count = standard_comp.get('comparable_count_90d', 0) or 0
        has_low_coverage = comp_count < self.config.COMPARABLE_MIN_COUNT
        
        return is_large_lot or is_waterfront_suburb or has_low_coverage
    
    def _calculate_relaxed_comparables(self, sales_df: pd.DataFrame,
                                      base_features: dict) -> dict:
        """
        Calculate relaxed comparable features (5km, 180 days, ±30% lot, ±1 bed/bath)
        
        Returns 6 features:
        1. relaxed_comparable_count
        2. relaxed_comparable_median_price
        3. relaxed_comparable_mean_price
        4. relaxed_comparable_price_per_sqm
        5. relaxed_comparable_min_distance
        6. relaxed_comparable_avg_distance
        """
        features = {}
        
        # Filter by relaxed criteria
        comps = sales_df[
            (sales_df['distance_km'] <= self.config.RELAXED_RADIUS_KM) &
            (sales_df['days_since_sale'] <= self.config.RELAXED_DAYS)
        ].copy()
        
        # Relaxed lot size matching (±30%)
        target_lot = base_features.get('lot_size_sqm')
        if target_lot and target_lot > 0:
            lot_lower = target_lot * (1 - self.config.RELAXED_LOT_SIZE_VARIANCE)
            lot_upper = target_lot * (1 + self.config.RELAXED_LOT_SIZE_VARIANCE)
            comps = comps[
                (comps['lot_size_sqm'].notna()) &
                (comps['lot_size_sqm'] >= lot_lower) &
                (comps['lot_size_sqm'] <= lot_upper)
            ]
        
        # Relaxed bed/bath matching (±1)
        target_beds = base_features.get('bedrooms')
        target_baths = base_features.get('bathrooms')
        
        if target_beds:
            comps = comps[
                (comps['bedrooms'].notna()) &
                (comps['bedrooms'] >= target_beds - 1) &
                (comps['bedrooms'] <= target_beds + 1)
            ]
        
        if target_baths:
            comps = comps[
                (comps['bathrooms'].notna()) &
                (comps['bathrooms'] >= target_baths - 1) &
                (comps['bathrooms'] <= target_baths + 1)
            ]
        
        features['relaxed_comparable_count'] = len(comps)
        
        if len(comps) == 0:
            return self._get_null_relaxed_features()
        
        # Calculate metrics
        features['relaxed_comparable_median_price'] = comps['sale_price'].median()
        features['relaxed_comparable_mean_price'] = comps['sale_price'].mean()
        features['relaxed_comparable_min_distance'] = comps['distance_km'].min()
        features['relaxed_comparable_avg_distance'] = comps['distance_km'].mean()
        
        # Price per sqm (lot-based)
        if target_lot and target_lot > 0:
            price_per_sqm_lot = comps['sale_price'] / comps['lot_size_sqm']
            features['relaxed_comparable_price_per_sqm'] = price_per_sqm_lot.median()
        else:
            features['relaxed_comparable_price_per_sqm'] = None
        
        return features
    
    def _calculate_waterfront_comparables(self, sales_df: pd.DataFrame,
                                         base_features: dict,
                                         osm_data: dict) -> dict:
        """
        Calculate waterfront-specific comparable features
        
        Returns 7 features:
        1. waterfront_comp_count
        2. waterfront_comp_median_price
        3. waterfront_comp_mean_price
        4. waterfront_comp_price_per_sqm
        5. waterfront_comp_avg_similarity
        6. waterfront_match_type
        7. waterfront_search_radius
        """
        features = {}
        
        # Get waterfront type
        waterfront_type = osm_data.get('osm_waterfront_type', 'None')
        
        # Start with nearby properties (3km, 180 days)
        comps = sales_df[
            (sales_df['distance_km'] <= 3.0) &
            (sales_df['days_since_sale'] <= 180)
        ].copy()
        
        # Try to match waterfront type exactly
        same_type = comps[comps['osm_waterfront_type'] == waterfront_type]
        
        if len(same_type) >= 3:
            # Use exact match
            comps = same_type
            match_type = 'exact'
            radius = 3.0
        elif len(same_type) > 0:
            # Use any waterfront
            comps = comps[comps['osm_canal_frontage'] == True]
            match_type = 'waterfront'
            radius = 3.0
        else:
            # Expand search to 5km
            comps = sales_df[
                (sales_df['distance_km'] <= 5.0) &
                (sales_df['days_since_sale'] <= 180) &
                (sales_df['osm_canal_frontage'] == True)
            ]
            match_type = 'expanded'
            radius = 5.0
        
        features['waterfront_match_type'] = match_type
        features['waterfront_search_radius'] = radius
        features['waterfront_comp_count'] = len(comps)
        
        if len(comps) == 0:
            return self._get_null_waterfront_features()
        
        # Calculate similarity scores
        target_beds = base_features.get('bedrooms', 3)
        target_baths = base_features.get('bathrooms', 2)
        target_lot = base_features.get('lot_size_sqm', 500)
        
        comps['similarity'] = (
            abs(comps['bedrooms'].fillna(target_beds) - target_beds) * 50000 +
            abs(comps['bathrooms'].fillna(target_baths) - target_baths) * 30000 +
            abs((comps['lot_size_sqm'].fillna(target_lot) - target_lot) / max(target_lot, 1)) * 20000 +
            comps['distance_km'] * 10000
        )
        
        # Get top comparables
        top_comps = comps.nsmallest(min(10, len(comps)), 'similarity')
        
        # Calculate features
        features['waterfront_comp_median_price'] = top_comps['sale_price'].median()
        features['waterfront_comp_mean_price'] = top_comps['sale_price'].mean()
        features['waterfront_comp_avg_similarity'] = top_comps['similarity'].mean()
        
        # Price per sqm
        comps_with_area = top_comps[
            top_comps['gpt_floor_area_sqm'].notna() &
            (top_comps['gpt_floor_area_sqm'] > 0)
        ]
        
        if len(comps_with_area) > 0:
            price_per_sqm = comps_with_area['sale_price'] / comps_with_area['gpt_floor_area_sqm']
            features['waterfront_comp_price_per_sqm'] = price_per_sqm.median()
        else:
            features['waterfront_comp_price_per_sqm'] = None
        
        return features
    
    def _calculate_time_adjusted_comparables(self, sales_df: pd.DataFrame,
                                            base_features: dict) -> dict:
        """
        Calculate time-adjusted comparable features
        
        Returns 4 features:
        1. time_adjusted_comparable_count
        2. time_adjusted_comparable_median
        3. time_adjusted_comparable_mean
        4. adjustment_applied_count
        """
        features = {}
        
        # Get suburb growth rate
        suburb = base_features.get('suburb', '')
        growth_rate = self._get_suburb_growth_rate(suburb)
        
        # Filter comparables (2km, 90 days)
        comps = sales_df[
            (sales_df['distance_km'] <= self.config.COMPARABLE_RADIUS_KM) &
            (sales_df['days_since_sale'] <= self.config.COMPARABLE_DAYS)
        ].copy()
        
        features['time_adjusted_comparable_count'] = len(comps)
        
        if len(comps) == 0:
            features['time_adjusted_comparable_median'] = None
            features['time_adjusted_comparable_mean'] = None
            features['adjustment_applied_count'] = 0
            return features
        
        # Adjust prices to current date
        comps['months_ago'] = comps['days_since_sale'] / 30.0
        comps['adjustment_factor'] = (1 + growth_rate) ** comps['months_ago']
        comps['adjusted_price'] = comps['sale_price'] * comps['adjustment_factor']
        
        features['time_adjusted_comparable_median'] = comps['adjusted_price'].median()
        features['time_adjusted_comparable_mean'] = comps['adjusted_price'].mean()
        features['adjustment_applied_count'] = len(comps[comps['months_ago'] > 1])
        
        return features
    
    def _get_suburb_growth_rate(self, suburb: str) -> float:
        """
        Get monthly growth rate for suburb
        
        Simple implementation - returns default or calculated rate
        """
        if suburb in self.suburb_growth_rates:
            return self.suburb_growth_rates[suburb]
        
        # Default growth rate: 0.5% per month
        return 0.005
    
    # Null feature generators
    
    def _get_null_standard_features(self) -> dict:
        """Return null values for standard comparable features"""
        return {
            'comparable_count_90d': 0,
            'comparable_median_price_90d': None,
            'comparable_mean_price_90d': None,
            'comparable_avg_price_per_sqm_90d': None,
            'comparable_price_range_90d': None,
            'comparable_std_dev_90d': None,
            'similar_features_median_price_90d': None,
            'similar_features_count_90d': 0,
            'comparable_min_distance_km': None,
            'comparable_max_distance_km': None,
            'comparable_avg_age_days': None,
            'comparable_price_per_sqm_std': None,
            'comparable_lot_size_median': None,
            'comparable_floor_area_median': None,
            'comparable_quality_score_avg': None
        }
    
    def _get_null_relaxed_features(self) -> dict:
        """Return null values for relaxed comparable features"""
        return {
            'relaxed_comparable_count': 0,
            'relaxed_comparable_median_price': None,
            'relaxed_comparable_mean_price': None,
            'relaxed_comparable_price_per_sqm': None,
            'relaxed_comparable_min_distance': None,
            'relaxed_comparable_avg_distance': None
        }
    
    def _get_null_waterfront_features(self) -> dict:
        """Return null values for waterfront comparable features"""
        return {
            'waterfront_comp_count': 0,
            'waterfront_comp_median_price': None,
            'waterfront_comp_mean_price': None,
            'waterfront_comp_price_per_sqm': None,
            'waterfront_comp_avg_similarity': None,
            'waterfront_match_type': 'none',
            'waterfront_search_radius': 0.0
        }
    
    def _get_all_null_features(self) -> dict:
        """Return null values for all comparable features"""
        features = {}
        features.update(self._get_null_standard_features())
        features.update(self._get_null_relaxed_features())
        features.update(self._get_null_waterfront_features())
        features.update({
            'time_adjusted_comparable_count': 0,
            'time_adjusted_comparable_median': None,
            'time_adjusted_comparable_mean': None,
            'adjustment_applied_count': 0
        })
        return features
