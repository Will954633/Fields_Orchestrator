"""
Additional Feature Engines for Production Valuation
====================================================

This module contains feature calculation engines for:
- Suburb Statistics (Task 1B)
- Location Distances (Task 1C)
- Waterfront/Suburb Indicators (Task 1D)
- Property Age Features (Task 1E)
- School Catchment Features (Task 1F)
- Location-Aware Lot Features (Task 1G)
- Log Transformations (Task 1H)

Author: Property Valuation Production System
Date: 20th November 2025
"""

import pymongo
import numpy as np
from datetime import datetime, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def _parse_sale_price(raw):
    """Parse sale price string like '$1,580,000' to int."""
    try:
        return int(str(raw).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


class SuburbStatisticsEngine:
    """Calculate suburb-level market statistics (12 features)"""
    
    def __init__(self, mongo_client: pymongo.MongoClient, config):
        self.mongo_client = mongo_client
        self.config = config
        self.gold_coast_db = mongo_client[config.GOLD_COAST_DB]
        self.recent_db = mongo_client[config.DB_RECENT_SOLD]
        self.cache = {}
        
    def calculate_suburb_statistics(self, suburb: str) -> dict:
        """Calculate 12 suburb statistics features"""
        
        if suburb in self.cache:
            return self.cache[suburb]
        
        features = {}
        
        try:
            # Get suburb collection
            collection_name = suburb.lower().replace(' ', '_')
            if collection_name not in self.gold_coast_db.list_collection_names():
                return self._get_null_suburb_stats()
            
            collection = self.gold_coast_db[collection_name]
            
            # Query sales from last 12 months
            cutoff_12m = datetime.now() - timedelta(days=365)
            cutoff_6m = datetime.now() - timedelta(days=182)
            cutoff_3m = datetime.now() - timedelta(days=90)
            
            # Get all properties with sales (don't filter by date in query as dates are strings)
            properties = list(collection.find({
                'scraped_data.property_timeline': {
                    '$elemMatch': {
                        'category': 'Sale',
                        'is_sold': True,
                        'price': {'$exists': True, '$ne': None}
                    }
                }
            }))
            
            sales_12m = []
            sales_6m = []
            sales_3m = []
            
            for prop in properties:
                timeline = prop.get('scraped_data', {}).get('property_timeline', [])
                for event in timeline:
                    if event.get('category') == 'Sale' and event.get('is_sold'):
                        sale_date_str = event.get('date')
                        sale_price = event.get('price')
                        
                        if not sale_date_str or not sale_price:
                            continue
                        
                        # Convert string date to datetime for comparison
                        try:
                            from datetime import datetime as dt
                            sale_date = dt.strptime(sale_date_str, '%Y-%m-%d')
                        except:
                            continue
                        
                        if sale_date >= cutoff_12m:
                            # Get GPT data from multiple possible locations
                            gpt_data = prop.get('gpt_valuation_data', {})
                            if not gpt_data:
                                gpt_data = prop.get('property_valuation_data', {})
                            
                            # Get floor area from house_plan or gpt_data
                            house_plan = prop.get('house_plan', {})
                            floor_area = house_plan.get('floor_area_sqm') or gpt_data.get('gpt_floor_area_sqm')
                            
                            sale_info = {
                                'price': sale_price,
                                'date': sale_date,
                                'floor_area': floor_area,
                                'lot_size': prop.get('lot_size_sqm'),
                                'quality_score': self._get_avg_quality(gpt_data)
                            }
                            sales_12m.append(sale_info)
                            
                            if sale_date >= cutoff_6m:
                                sales_6m.append(sale_info)
                            if sale_date >= cutoff_3m:
                                sales_3m.append(sale_info)

            # --- Merge recent sold data from Target_Market_Sold_Last_12_Months ---
            seen = set()
            for s in sales_12m:
                d = s['date']
                date_key = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
                seen.add((date_key, int(s['price']) if s['price'] else 0))

            if collection_name in (self.recent_db.list_collection_names() or []):
                recent_coll = self.recent_db[collection_name]
                for prop in recent_coll.find({}):
                    raw_price = prop.get('sale_price')
                    raw_date = prop.get('sale_date')
                    if not raw_price or not raw_date:
                        continue

                    price = _parse_sale_price(raw_price)
                    if not price:
                        continue

                    try:
                        from datetime import datetime as dt
                        sale_date = dt.strptime(str(raw_date)[:10], '%Y-%m-%d')
                    except (ValueError, TypeError):
                        continue

                    if sale_date < cutoff_12m:
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

                    # GPT quality data from property_valuation_data
                    gpt_data = prop.get('property_valuation_data', {}) or {}

                    sale_info = {
                        'price': price,
                        'date': sale_date,
                        'floor_area': floor_area,
                        'lot_size': prop.get('land_size_sqm'),
                        'quality_score': self._get_avg_quality(gpt_data)
                    }
                    sales_12m.append(sale_info)

                    if sale_date >= cutoff_6m:
                        sales_6m.append(sale_info)
                    if sale_date >= cutoff_3m:
                        sales_3m.append(sale_info)

            # Calculate features
            if len(sales_12m) > 0:
                prices_12m = [s['price'] for s in sales_12m]
                prices_6m = [s['price'] for s in sales_6m] if sales_6m else []
                
                # 1-2: Median prices
                features['suburb_median_price_12m'] = np.median(prices_12m)
                features['suburb_median_price_6m'] = np.median(prices_6m) if prices_6m else None
                
                # 3-4: Sales volume
                features['suburb_sales_volume_12m'] = len(sales_12m)
                features['suburb_sales_volume_3m'] = len(sales_3m)
                
                # 5: Market velocity (sales per month)
                features['suburb_market_velocity'] = len(sales_12m) / 12.0
                
                # 6: Price growth rate
                if len(sales_6m) > 0 and len(prices_12m) > 3:
                    median_6m = np.median(prices_6m)
                    median_12m = np.median(prices_12m)
                    growth = ((median_6m / median_12m) - 1) * 100 if median_12m > 0 else 0
                    features['suburb_price_growth_rate'] = growth
                else:
                    features['suburb_price_growth_rate'] = None
                
                # 7: Days on market (placeholder - would need listing data)
                features['suburb_avg_days_on_market'] = None
                
                # 8: Price volatility
                features['suburb_price_volatility'] = np.std(prices_12m)
                
                # 9-10: Floor area and lot size medians
                floor_areas = [s['floor_area'] for s in sales_12m if s['floor_area']]
                lot_sizes = [s['lot_size'] for s in sales_12m if s['lot_size']]
                
                features['suburb_floor_area_median'] = np.median(floor_areas) if floor_areas else None
                features['suburb_lot_size_median'] = np.median(lot_sizes) if lot_sizes else None
                
                # 11: Quality score average
                qualities = [s['quality_score'] for s in sales_12m if s['quality_score']]
                features['suburb_quality_score_avg'] = np.mean(qualities) if qualities else None
                
                # 12: Sold ratio (placeholder - would need all listings)
                features['suburb_sold_ratio'] = None
            else:
                features = self._get_null_suburb_stats()
            
            self.cache[suburb] = features
            return features
            
        except Exception as e:
            logger.warning(f"Error calculating suburb stats for {suburb}: {e}")
            return self._get_null_suburb_stats()
    
    def _get_avg_quality(self, gpt_data: dict) -> Optional[float]:
        """Calculate average quality score from GPT data"""
        quality_fields = [
            'exterior_condition_score', 'roof_condition_score',
            'interior_condition_score', 'kitchen_quality_score',
            'bathroom_quality_score', 'property_presentation_score'
        ]
        scores = [gpt_data.get(f) for f in quality_fields if gpt_data.get(f)]
        return np.mean(scores) if scores else None
    
    def _get_null_suburb_stats(self) -> dict:
        """Return null suburb statistics"""
        return {
            'suburb_median_price_12m': None,
            'suburb_median_price_6m': None,
            'suburb_sales_volume_12m': 0,
            'suburb_sales_volume_3m': 0,
            'suburb_market_velocity': None,
            'suburb_price_growth_rate': None,
            'suburb_avg_days_on_market': None,
            'suburb_price_volatility': None,
            'suburb_floor_area_median': None,
            'suburb_lot_size_median': None,
            'suburb_quality_score_avg': None,
            'suburb_sold_ratio': None
        }


class LocationDistanceEngine:
    """Calculate distances to key locations (15 features)"""
    
    def __init__(self, config):
        self.config = config
    
    def haversine_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """Calculate distance in kilometers"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return 6371 * c
    
    def calculate_distance_features(self, latitude: float, longitude: float) -> dict:
        """Calculate 15 distance features"""
        features = {}
        
        # Distances to key locations
        features['distance_to_cbd_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['cbd']
        )
        
        features['distance_to_robina_tc_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['robina_town_centre']
        )
        
        features['distance_to_burleigh_beach_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['burleigh_beach']
        )
        
        features['distance_to_surfers_beach_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['surfers_beach']
        )
        
        features['distance_to_broadbeach_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['broadbeach']
        )
        
        features['distance_to_main_beach_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['main_beach']
        )
        
        # Distances to schools
        features['distance_to_robina_state_high_km'] = self.haversine_distance(
            latitude, longitude, *self.config.PREMIUM_SCHOOLS['robina_state_high']
        )
        
        features['distance_to_somerset_college_km'] = self.haversine_distance(
            latitude, longitude, *self.config.PREMIUM_SCHOOLS['somerset_college']
        )
        
        features['distance_to_all_saints_anglican_km'] = self.haversine_distance(
            latitude, longitude, *self.config.PREMIUM_SCHOOLS['all_saints_anglican']
        )
        
        features['distance_to_varsity_college_km'] = self.haversine_distance(
            latitude, longitude, *self.config.PREMIUM_SCHOOLS['varsity_college']
        )
        
        # Distances to universities
        features['distance_to_griffith_uni_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['griffith_uni']
        )
        
        features['distance_to_bond_uni_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['bond_uni']
        )
        
        # Distances to amenities
        features['distance_to_pacific_fair_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['pacific_fair']
        )
        
        features['distance_to_robina_hospital_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['robina_hospital']
        )
        
        features['distance_to_gold_coast_airport_km'] = self.haversine_distance(
            latitude, longitude, *self.config.KEY_LOCATIONS['gold_coast_airport']
        )
        
        return features


class SuburbIndicatorsEngine:
    """Calculate suburb indicator features (4 features)"""
    
    def __init__(self, config):
        self.config = config
    
    def calculate_suburb_indicators(self, suburb: str) -> dict:
        """Calculate 4 suburb indicator features"""
        suburb_upper = suburb.upper()
        
        return {
            'is_waterfront_suburb': int(suburb_upper in self.config.WATERFRONT_SUBURBS),
            'is_canal_suburb': int(suburb_upper in self.config.CANAL_SUBURBS),
            'is_beachside_suburb': int(suburb_upper in self.config.BEACHSIDE_SUBURBS),
            'is_hinterland_suburb': int(suburb_upper in self.config.HINTERLAND_SUBURBS)
        }


class PropertyAgeEngine:
    """Calculate property age features (5 features)"""
    
    @staticmethod
    def calculate_age_features(property_doc: dict) -> dict:
        """Calculate 5 property age features"""
        features = {}
        
        # Try to get build year from property data
        build_year = property_doc.get('build_year') or property_doc.get('year_built')
        current_year = datetime.now().year
        
        if build_year:
            age = current_year - build_year
            features['property_age_years'] = age
            
            # Age depreciation factor (assumed 1% per year, capped at 50%)
            depreciation = min(age * 0.01, 0.50)
            features['age_depreciation_factor'] = depreciation
            
            # Boolean indicators
            features['is_new_construction'] = int(age < 5)
            features['is_heritage_character'] = int(age > 50)
            
            # Renovation assumed (if property is old but has high condition scores)
            gpt_data = property_doc.get('gpt_valuation_data', {})
            avg_condition = np.mean([
                gpt_data.get('exterior_condition_score', 0),
                gpt_data.get('interior_condition_score', 0)
            ])
            features['renovation_assumed'] = int(age > 20 and avg_condition > 7)
        else:
            # Null values if no build year
            features['property_age_years'] = None
            features['age_depreciation_factor'] = None
            features['is_new_construction'] = 0
            features['is_heritage_character'] = 0
            features['renovation_assumed'] = 0
        
        return features


class SchoolCatchmentEngine:
    """Calculate school catchment features (9 features)"""
    
    def __init__(self, config):
        self.config = config
    
    def haversine_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """Calculate distance in kilometers"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return 6371 * c
    
    def calculate_catchment_features(self, latitude: float, longitude: float) -> dict:
        """Calculate 9 school catchment features"""
        features = {}
        premium_count = 0
        
        # For each premium school
        for school_name, (school_lat, school_lon) in self.config.PREMIUM_SCHOOLS.items():
            distance = self.haversine_distance(latitude, longitude, school_lat, school_lon)
            
            # In catchment if within 3km
            in_catchment = distance <= self.config.SCHOOL_CATCHMENT_RADIUS_KM
            features[f'in_{school_name}_catchment'] = int(in_catchment)
            
            # Catchment premium (estimated)
            if in_catchment:
                premium_count += 1
                # Closer = higher premium, max $50k per school
                premium = max(0, 50000 * (1 - distance / 3.0))
                features[f'{school_name}_catchment_premium'] = premium
            else:
                features[f'{school_name}_catchment_premium'] = 0
        
        # Count of premium schools within 3km
        features['premium_school_count_3km'] = premium_count
        
        return features


class LocationAwareLotEngine:
    """Calculate location-aware lot features (3 features - Iteration 08)"""
    
    def __init__(self, config):
        self.config = config
    
    def calculate_lot_features(self, property_doc: dict, suburb: str, 
                               lot_size_sqm: Optional[float]) -> dict:
        """Calculate 3 location-aware lot features"""
        features = {}
        
        if not lot_size_sqm or lot_size_sqm <= 0:
            return {
                'waterfront_lot_premium_estimate': 0,
                'suburb_lot_size_percentile': None,
                'lot_size_value_segment': 'unknown'
            }
        
        # 1. Waterfront lot premium estimate
        osm_data = property_doc.get('osm_location_features', {})
        is_waterfront = osm_data.get('osm_canal_frontage', False)
        waterfront_type = osm_data.get('osm_waterfront_type', 'None')
        
        if is_waterfront:
            # Base premium per sqm for waterfront
            base_premium = {
                'canal': 500,
                'river': 600,
                'lake': 550,
                'ocean': 800
            }.get(waterfront_type.lower(), 500)
            
            # Premium scales with lot size (larger=more valuable)
            premium = base_premium * lot_size_sqm * min(1.0, lot_size_sqm / 500)
            features['waterfront_lot_premium_estimate'] = premium
        else:
            features['waterfront_lot_premium_estimate'] = 0
        
        # 2. Suburb lot size percentile (simplified - would need suburb data)
        # Using typical Gold Coast lot sizes: 400-600 sqm = 50th percentile
        if lot_size_sqm < 400:
            percentile = max(0, lot_size_sqm / 400 * 50)
        elif lot_size_sqm < 600:
            percentile = 50 + (lot_size_sqm - 400) / 200 * 25
        elif lot_size_sqm < 1000:
            percentile = 75 + (lot_size_sqm - 600) / 400 * 15
        else:
            percentile = min(100, 90 + (lot_size_sqm - 1000) / 1000 * 10)
        
        features['suburb_lot_size_percentile'] = percentile
        
        # 3. Lot size value segment
        if lot_size_sqm < 350:
            segment = 'small'
        elif lot_size_sqm < 650:
            segment = 'medium'
        elif lot_size_sqm < 1000:
            segment = 'large'
        else:
            segment = 'premium'
        
        features['lot_size_value_segment'] = segment
        
        return features


class LogTransformationEngine:
    """Calculate log transformations and derived features"""
    
    @staticmethod
    def calculate_log_features(features: dict) -> dict:
        """Calculate log-transformed features with robust type checking"""
        log_features = {}
        
        try:
            # Log of floor area (if available) - with type checking
            gpt_floor_area = features.get('gpt_floor_area_sqm')
            if isinstance(gpt_floor_area, (int, float)) and gpt_floor_area > 0:
                try:
                    log_features['log_gpt_floor_area_sqm'] = np.log(gpt_floor_area)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Error calculating log of floor area: {e}, value: {gpt_floor_area}")
                    log_features['log_gpt_floor_area_sqm'] = None
            else:
                log_features['log_gpt_floor_area_sqm'] = None
            
            # Log of lot size - with type checking
            lot_size = features.get('lot_size_sqm')
            if isinstance(lot_size, (int, float)) and lot_size > 0:
                try:
                    log_features['log_lot_size_sqm'] = np.log(lot_size)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Error calculating log of lot size: {e}, value: {lot_size}")
                    log_features['log_lot_size_sqm'] = None
            else:
                log_features['log_lot_size_sqm'] = None
            
            # Log of comparable median price - with type checking
            comp_median = features.get('comparable_median_price_90d')
            if isinstance(comp_median, (int, float)) and comp_median > 0:
                try:
                    log_features['log_comparable_median_price'] = np.log(comp_median)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Error calculating log of comparable median: {e}, value: {comp_median}")
                    log_features['log_comparable_median_price'] = None
            else:
                log_features['log_comparable_median_price'] = None
            
            # Has floor plan (binary) - with type checking
            if isinstance(gpt_floor_area, (int, float)) and gpt_floor_area > 0:
                log_features['has_floor_plan'] = 1
            else:
                log_features['has_floor_plan'] = 0
                
        except Exception as e:
            logger.error(f"Unexpected error in log transformation: {e}")
            # Return safe defaults
            log_features = {
                'log_gpt_floor_area_sqm': None,
                'log_lot_size_sqm': None,
                'log_comparable_median_price': None,
                'has_floor_plan': 0
            }
        
        return log_features
