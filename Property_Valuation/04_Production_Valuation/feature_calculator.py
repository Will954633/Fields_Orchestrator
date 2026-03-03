"""
Comprehensive Feature Calculator for Iteration 08 Model
========================================================

This module calculates all 179 features required by the Iteration 08 valuation model.
It handles:
- Base property features
- GPT analysis features  
- OSM location features
- Comparable sales features (standard and relaxed)
- Waterfront-aware comparables
- Time-adjusted comparables
- Suburb statistics and market velocity
- Location-based features (schools, POIs, distance calculations)
- Location-aware lot size features (Iteration 08)

Author: Property Valuation Production System
Date: 20th November 2025
"""

import pymongo
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Optional, Tuple
import config


def _parse_sale_price(raw):
    """Parse sale price string like '$1,580,000' to int."""
    try:
        return int(str(raw).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


class FeatureCalculator:
    """Calculate all features required for Iteration 08 model"""
    
    def __init__(self, mongo_client: pymongo.MongoClient):
        """
        Initialize feature calculator
        
        Args:
            mongo_client: MongoDB client connection
        """
        self.mongo_client = mongo_client
        self.gold_coast_db = mongo_client[config.GOLD_COAST_DB]
        self.recent_db = mongo_client[config.DB_RECENT_SOLD]

        # Cache for historical sales by suburb
        self.sales_cache = {}
        self.cache_valid_until = None
        
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
    
    def get_all_recent_sales(self, days: int = 365) -> pd.DataFrame:
        """
        Get all recent sales from Gold Coast database
        
        Args:
            days: Number of days to look back
            
        Returns:
            DataFrame of recent sales
        """
        # Check cache
        if (self.cache_valid_until and 
            datetime.now() < self.cache_valid_until and
            days in self.sales_cache):
            return self.sales_cache[days]
        
        cutoff_date = datetime.now() - timedelta(days=days)
        all_sales = []
        
        # Get all collections (suburbs)
        collections = [c for c in self.gold_coast_db.list_collection_names() 
                      if not c.startswith('system.')]
        
        for coll_name in collections:
            collection = self.gold_coast_db[coll_name]
            
            # Query for sales in time period
            query = {
                'scraped_data.property_timeline': {
                    '$elemMatch': {
                        'category': 'Sale',
                        'is_sold': True,
                        'date': {'$gte': cutoff_date}
                    }
                },
                'LATITUDE': {'$exists': True, '$ne': None},
                'LONGITUDE': {'$exists': True, '$ne': None}
            }
            
            properties = collection.find(query)
            
            for prop in properties:
                # Extract sale data
                timeline = prop.get('scraped_data', {}).get('property_timeline', [])
                sales = [e for e in timeline if e.get('category') == 'Sale' 
                        and e.get('is_sold') and e.get('date') >= cutoff_date]
                
                for sale in sales:
                    sale_data = {
                        'suburb': coll_name.upper().replace('_', ' '),
                        'latitude': prop.get('LATITUDE'),
                        'longitude': prop.get('LONGITUDE'),
                        'sale_price': sale.get('value'),
                        'sale_date': sale.get('date'),
                        'bedrooms': prop.get('bedrooms'),
                        'bathrooms': prop.get('bathrooms'),
                        'car_spaces': prop.get('car_spaces'),
                        'lot_size_sqm': prop.get('lot_size_sqm'),
                        'property_type': prop.get('property_type')
                    }
                    
                    # Add GPT data if available
                    gpt_data = prop.get('gpt_valuation_data', {})
                    sale_data['gpt_floor_area_sqm'] = gpt_data.get('gpt_floor_area_sqm')
                    
                    # Add OSM data if available
                    osm_data = prop.get('osm_location_features', {})
                    sale_data['osm_canal_frontage'] = osm_data.get('osm_canal_frontage', False)
                    sale_data['osm_waterfront_type'] = osm_data.get('osm_waterfront_type', 'None')
                    
                    all_sales.append(sale_data)

        # --- Merge recent sold data from Target_Market_Sold_Last_12_Months ---
        # Build dedup set from existing sales: (date_str, price_int)
        seen = set()
        for s in all_sales:
            d = s['sale_date']
            date_key = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
            seen.add((date_key, int(s['sale_price']) if s['sale_price'] else 0))

        recent_collections = [c for c in self.recent_db.list_collection_names()
                              if not c.startswith('system.')]

        for coll_name in recent_collections:
            collection = self.recent_db[coll_name]
            for prop in collection.find({}):
                raw_price = prop.get('sale_price')
                raw_date = prop.get('sale_date')
                if not raw_price or not raw_date:
                    continue

                price = _parse_sale_price(raw_price)
                if not price:
                    continue

                try:
                    sale_date = datetime.strptime(str(raw_date)[:10], '%Y-%m-%d')
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

                sale_data = {
                    'suburb': coll_name.upper().replace('_', ' '),
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
                }
                all_sales.append(sale_data)

        # Convert to DataFrame
        df = pd.DataFrame(all_sales)
        
        # Cache it
        self.sales_cache[days] = df
        self.cache_valid_until = datetime.now() + timedelta(hours=1)
        
        return df
    
    def calculate_base_features(self, property_doc: dict) -> dict:
        """Extract base property features from document"""
        features = {}
        
        # Core property attributes
        features['bedrooms'] = property_doc.get('bedrooms')
        features['bathrooms'] = property_doc.get('bathrooms')
        features['car_spaces'] = property_doc.get('car_spaces')
        features['lot_size_sqm'] = property_doc.get('lot_size_sqm')
        
        # Get suburb (standardize format)
        suburb = property_doc.get('suburb', '')
        if not suburb:
            # Try to extract from address
            address = property_doc.get('complete_address', '')
            # Simple extraction - this might need refinement
            parts = address.split(',')
            if len(parts) >= 2:
                suburb = parts[-2].strip()
        features['suburb'] = suburb.upper()
        
        # Coordinates
        features['latitude'] = property_doc.get('LATITUDE')
        features['longitude'] = property_doc.get('LONGITUDE')
        
        return features
    
    def calculate_comparable_sales_features(self, property_doc: dict, 
                                           base_features: dict) -> dict:
        """
        Calculate comparable sales features
        
        This includes:
        - Standard comparables (2km, 90 days)
        - Relaxed comparables (5km, 180 days) for outlier-prone properties
        - Waterfront-aware comparables
        - Time-adjusted comparables
        """
        features = {}
        
        # Get recent sales
        recent_sales = self.get_all_recent_sales(days=365)
        
        if len(recent_sales) == 0:
            # Return nulls for all comparable features
            return self._get_null_comparable_features()
        
        # Calculate distances to all sales
        lat = base_features['latitude']
        lon = base_features['longitude']
        
        recent_sales['distance_km'] = recent_sales.apply(
            lambda r: self.haversine_distance(lat, lon, 
                                              r['latitude'], r['longitude']),
            axis=1
        )
        
        # Standard comparables (2km, 90 days)
        standard_comp = self._calculate_standard_comparables(
            recent_sales, base_features
        )
        features.update(standard_comp)
        
        # Relaxed comparables for outlier-prone properties
        is_outlier_prone = self._is_outlier_prone(base_features, standard_comp)
        features['is_outlier_prone'] = is_outlier_prone
        
        if is_outlier_prone:
            relaxed_comp = self._calculate_relaxed_comparables(
                recent_sales, base_features
            )
            features.update(relaxed_comp)
        else:
            # Add null relaxed features
            features.update(self._get_null_relaxed_features())
        
        # Waterfront comparables if applicable
        is_waterfront = base_features.get('osm_canal_frontage', False)
        if is_waterfront:
            waterfront_comp = self._calculate_waterfront_comparables(
                recent_sales, base_features
            )
            features.update(waterfront_comp)
        else:
            features.update(self._get_null_waterfront_features())
        
        # Time-adjusted comparables
        time_adjusted = self._calculate_time_adjusted_comparables(
            recent_sales, base_features
        )
        features.update(time_adjusted)
        
        return features
    
    def _calculate_standard_comparables(self, sales_df: pd.DataFrame, 
                                       base_features: dict) -> dict:
        """Calculate standard comparable sales features (2km, 90 days)"""
        features = {}
        
        cutoff_date = datetime.now() - timedelta(days=90)
        
        # Filter by time and distance
        comps = sales_df[
            (sales_df['distance_km'] <= config.COMPARABLE_RADIUS_KM) &
            (sales_df['sale_date'] >= cutoff_date)
        ].copy()
        
        if len(comps) == 0:
            return {
                'comparable_count_90d': 0,
                'comparable_median_price_90d': None,
                'comparable_avg_price_per_sqm_90d': None,
                'comparable_price_range_90d': None,
                'similar_features_median_price_90d': None
            }
        
        # Calculate features
        features['comparable_count_90d'] = len(comps)
        features['comparable_median_price_90d'] = comps['sale_price'].median()
        features['comparable_price_range_90d'] = (
            comps['sale_price'].max() - comps['sale_price'].min()
        )
        
        # Price per sqm (if floor area available)
        comps_with_area =comps[comps['gpt_floor_area_sqm'].notna() & 
                                (comps['gpt_floor_area_sqm'] > 0)]
        if len(comps_with_area) > 0:
            price_per_sqm = comps_with_area['sale_price'] / comps_with_area['gpt_floor_area_sqm']
            features['comparable_avg_price_per_sqm_90d'] = price_per_sqm.mean()
        else:
            features['comparable_avg_price_per_sqm_90d'] = None
        
        # Similar features (same bed/bath)
        target_beds = base_features.get('bedrooms')
        target_baths = base_features.get('bathrooms')
        
        similar = comps[
            (comps['bedrooms'] == target_beds) &
            (comps['bathrooms'] == target_baths)
        ]
        
        if len(similar) > 0:
            features['similar_features_median_price_90d'] = similar['sale_price'].median()
        else:
            features['similar_features_median_price_90d'] = None
        
        return features
    
    def _is_outlier_prone(self, base_features: dict, 
                         standard_comp: dict) -> bool:
        """Check if property is outlier-prone"""
        # Large lot
        lot_size = base_features.get('lot_size_sqm', 0)
        is_large_lot = lot_size > 800
        
        # Waterfront suburb
        suburb = base_features.get('suburb', '')
        is_waterfront_suburb = suburb in config.WATERFRONT_SUBURBS
        
        # Low comparable coverage
        comp_count = standard_comp.get('comparable_count_90d', 0)
        has_low_coverage = comp_count < config.COMPARABLE_MIN_COUNT
        
        return is_large_lot or is_waterfront_suburb or has_low_coverage
    
    def _calculate_relaxed_comparables(self, sales_df: pd.DataFrame,
                                      base_features: dict) -> dict:
        """Calculate relaxed comparable features (5km, 180 days, ±30% lot)"""
        features = {}
        
        cutoff_date = datetime.now() - timedelta(days=config.RELAXED_DAYS)
        
        # Filter by relaxed criteria
        comps = sales_df[
            (sales_df['distance_km'] <= config.RELAXED_RADIUS_KM) &
            (sales_df['sale_date'] >= cutoff_date)
        ].copy()
        
        # Relaxed lot size matching (±30%)
        target_lot = base_features.get('lot_size_sqm')
        if target_lot:
            lot_lower = target_lot * (1 - config.RELAXED_LOT_SIZE_VARIANCE)
            lot_upper = target_lot * (1 + config.RELAXED_LOT_SIZE_VARIANCE)
            comps = comps[
                (comps['lot_size_sqm'] >= lot_lower) &
                (comps['lot_size_sqm'] <= lot_upper)
            ]
        
        # Relaxed bed/bath matching (±1)
        target_beds = base_features.get('bedrooms')
        target_baths = base_features.get('bathrooms')
        
        if target_beds:
            comps = comps[
                (comps['bedrooms'] >= target_beds - 1) &
                (comps['bedrooms'] <= target_beds + 1)
            ]
        
        if target_baths:
            comps = comps[
                (comps['bathrooms'] >= target_baths - 1) &
                (comps['bathrooms'] <= target_baths + 1)
            ]
        
        if len(comps) == 0:
            return self._get_null_relaxed_features()
        
        # Calculate metrics
        features['relaxed_comparable_count'] = len(comps)
        features['relaxed_comparable_median_price'] = comps['sale_price'].median()
        features['relaxed_comparable_mean_price'] = comps['sale_price'].mean()
        features['relaxed_comparable_min_distance'] = comps['distance_km'].min()
        features['relaxed_comparable_avg_distance'] = comps['distance_km'].mean()
        
        # Price per sqm
        if target_lot and target_lot > 0:
            price_per_sqm = comps['sale_price'] / comps['lot_size_sqm']
            features['relaxed_comparable_price_per_sqm'] = price_per_sqm.median()
        else:
            features['relaxed_comparable_price_per_sqm'] = None
        
        return features
    
    def _calculate_waterfront_comparables(self, sales_df: pd.DataFrame,
                                         base_features: dict) -> dict:
        """Calculate waterfront-specific comparable features"""
        features = {}
        
        # Get waterfront type
        waterfront_type = base_features.get('osm_waterfront_type', 'None')
        
        cutoff_date = datetime.now() - timedelta(days=180)
        
        # Start with nearby properties
        comps = sales_df[
            (sales_df['distance_km'] <= 3.0) &
            (sales_df['sale_date'] >= cutoff_date)
        ].copy()
        
        # Try to match waterfront type
        same_type = comps[comps['osm_waterfront_type'] == waterfront_type]
        
        if len(same_type) >= 3:
            comps = same_type
            match_type = 'exact'
            radius = 3.0
        elif len(same_type) > 0:
            # Use any waterfront
            comps = comps[comps['osm_canal_frontage'] == True]
            match_type = 'waterfront'
            radius = 3.0
        else:
            # Expand search
            comps = sales_df[
                (sales_df['distance_km'] <= 5.0) &
                (sales_df['sale_date'] >= cutoff_date) &
                (sales_df['osm_canal_frontage'] == True)
            ]
            match_type = 'expanded'
            radius = 5.0
        
        if len(comps) == 0:
            return self._get_null_waterfront_features()
        
        # Calculate similarity scores
        target_beds = base_features.get('bedrooms', 3)
        target_baths = base_features.get('bathrooms', 2)
        target_lot = base_features.get('lot_size_sqm', 500)
        
        comps['similarity'] = (
            abs(comps['bedrooms'].fillna(target_beds) - target_beds) * 50000 +
            abs(comps['bathrooms'].fillna(target_baths) - target_baths) * 30000 +
            abs((comps['lot_size_sqm'].fillna(target_lot) - target_lot) / target_lot) * 20000 +
            comps['distance_km'] * 10000
        )
        
        # Get top comparables
        top_comps = comps.nsmallest(min(10, len(comps)), 'similarity')
        
        features['waterfront_comp_count'] = len(top_comps)
        features['waterfront_comp_median_price'] = top_comps['sale_price'].median()
        features['waterfront_comp_mean_price'] = top_comps['sale_price'].mean()
        features['waterfront_comp_avg_similarity'] = top_comps['similarity'].mean()
        features['waterfront_match_type'] = match_type
        features['waterfront_search_radius'] = radius
        
        # Price per sqm
        comps_with_area = top_comps[top_comps['gpt_floor_area_sqm'].notna() &
                                     (top_comps['gpt_floor_area_sqm'] > 0)]
        if len(comps_with_area) > 0:
            price_per_sqm = comps_with_area['sale_price'] / comps_with_area['gpt_floor_area_sqm']
            features['waterfront_comp_price_per_sqm'] = price_per_sqm.median()
        else:
            features['waterfront_comp_price_per_sqm'] = None
        
        return features
    
    def _calculate_time_adjusted_comparables(self, sales_df: pd.DataFrame,
                                            base_features: dict) -> dict:
        """Calculate time-adjusted comparable features"""
        # Simplified version - assumes monthly growth rates
        # In production, you'd load actual growth rates from your data
        
        features = {}
        monthly_growth_rate = 0.005  # 0.5% monthly (placeholder)
        
        cutoff_date = datetime.now() - timedelta(days=90)
        comps = sales_df[
            (sales_df['distance_km'] <= config.COMPARABLE_RADIUS_KM) &
            (sales_df['sale_date'] >= cutoff_date)
        ].copy()
        
        if len(comps) == 0:
            return {
                'time_adjusted_comparable_count': 0,
                'time_adjusted_comparable_median': None,
                'time_adjusted_comparable_mean': None,
                'adjustment_applied_count': 0
            }
        
        # Adjust prices to current date
        comps['months_ago'] = (
            (datetime.now() - comps['sale_date']).dt.days / 30
        )
        comps['adjustment_factor'] = (1 + monthly_growth_rate) ** comps['months_ago']
        comps['adjusted_price'] = comps['sale_price'] * comps['adjustment_factor']
        
        features['time_adjusted_comparable_count'] = len(comps)
        features['time_adjusted_comparable_median'] = comps['adjusted_price'].median()
        features['time_adjusted_comparable_mean'] = comps['adjusted_price'].mean()
        features['adjustment_applied_count'] = len(comps[comps['months_ago'] > 1])
        
        return features
    
    def _get_null_comparable_features(self) -> dict:
        """Return null values for all comparable features"""
        return {
            'comparable_count_90d': 0,
            'comparable_median_price_90d': None,
            'comparable_avg_price_per_sqm_90d': None,
            'comparable_price_range_90d': None,
            'similar_features_median_price_90d': None
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
    
    # Continued in next message due to length...
