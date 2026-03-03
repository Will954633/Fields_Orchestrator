"""
Configuration for Production Valuation System
==============================================

This configuration file contains all settings for the production property
valuation system using Iteration 08 model.

Author: Property Valuation Production System
Date: 20th November 2025
"""

import os
from pathlib import Path

# ============================================================================
# PATHS
# ============================================================================

# Base directories
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

# Model paths
MODEL_DIR = PROJECT_ROOT / "03_Model_Development/Iteration_04/Iteration_08/models"
MODEL_FILE = "catboost_iteration_08_phase1_20251119_135151.cbm"  # Latest model

# Script dependencies
OSM_FEATURES_SCRIPT = PROJECT_ROOT / "03_Model_Development/Iteration_04/scripts/osm_feature_definitions.py"
GPT_SYSTEM_DIR = PROJECT_ROOT / "02_House_Plan_Data/src"

# Output directories
LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "results"

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# OPENAI CONFIGURATION
# ============================================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# GPT Model Configuration
GPT_MODEL = "gpt-5-nano-2025-08-07"
MAX_TOKENS = 16000  # Maximum tokens for response (increased for full property analysis)
TEMPERATURE = 0.1  # Low temperature for consistent, factual responses
MAX_RETRIES = 3  # Maximum retries for API calls
RETRY_DELAY = 5  # Delay between retries in seconds
REQUEST_TIMEOUT = 120  # Request timeout in seconds

# Image Processing
MAX_IMAGES_PER_PROPERTY = 50
IMAGE_DOWNLOAD_TIMEOUT = 30
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".webp"]

# Processing Modes
TEST_MODE = False  # Set to True for testing
STOP_AT_FIRST_HOUSE_PLAN = False
SAVE_PROCESSED_DATA = True
DATA_EXPORT_DIR = str(RESULTS_DIR)
TEMP_DIR = str(BASE_DIR / "temp")
OUTPUT_DIR = str(RESULTS_DIR)
LOG_DIR = str(LOGS_DIR)

# ============================================================================
# MONGODB CONFIGURATION
# ============================================================================

MONGODB_URI = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI") or "mongodb://127.0.0.1:27017/"

# Database for properties to value
PRODUCTION_DB = "Gold_Coast_Currently_For_Sale"
PRODUCTION_COLLECTION = "properties_for_sale"  # unused - script iterates suburb collections
DATABASE_NAME = "Gold_Coast_Currently_For_Sale"

# Database for historical sales (comparable sales)
GOLD_COAST_DB = "Gold_Coast_Currently_For_Sale"

# Database for recent sold properties (last 12 months, complete)
DB_RECENT_SOLD = "Target_Market_Sold_Last_12_Months"

# ============================================================================
# ENRICHMENT CONFIGURATION
# ============================================================================

# GPT Analysis
GPT_REQUIRED_FIELDS = [
    'gpt_floor_area_sqm',
    'gpt_floor_area_confidence', 
    'gpt_number_of_levels',
    'exterior_condition_score',
    'roof_condition_score',
    'cladding_condition_score',
    'paint_quality_score',
    'interior_condition_score',
    'flooring_quality_score',
    'kitchen_quality_score',
    'bathroom_quality_score',
    'natural_light_score',
    'property_presentation_score',
    'market_appeal_score',
    'modern_features_score',
    'landscaping_quality_score',
    'outdoor_entertainment_score'
]

# OSM Features
OSM_REQUIRED_FIELDS = [
    'osm_nearest_road_type',
    'osm_distance_to_nearest_road_m',
    'osm_faces_major_road',
    'osm_distance_to_primary_road_m',
    'osm_distance_to_secondary_road_m',
    'osm_distance_to_motorway_m',
    'osm_is_corner_lot',
    'osm_is_cul_de_sac',
    'osm_traffic_exposure_score',
    'osm_nearby_road_count',
    'osm_distance_to_water_m',
    'osm_nearest_water_type',
    'osm_canal_frontage',
    'osm_canal_adjacent',
    'osm_waterfront_type',
    'osm_waterfront_premium_eligible',
    'osm_distance_to_canal_m'
]

# ============================================================================
# FEATURE CALCULATION SETTINGS
# ============================================================================

# Comparable sales settings
COMPARABLE_RADIUS_KM = 2.0
COMPARABLE_DAYS = 90
COMPARABLE_MIN_COUNT = 3

# Relaxed comparable settings (for outlier-prone properties)
RELAXED_RADIUS_KM = 5.0
RELAXED_DAYS = 180
RELAXED_LOT_SIZE_VARIANCE = 0.3  # ±30%

# Waterfront suburbs
WATERFRONT_SUBURBS = [
    'HOPE ISLAND', 'BROADBEACH WATERS', 'MERMAID WATERS',
    'BROADBEACH', 'MAIN BEACH', 'SURFERS PARADISE',
    'RUNAWAY BAY', 'SANCTUARY COVE', 'PARADISE POINT'
]

# Premium school catchments (with 3km catchment radius)
PREMIUM_SCHOOLS = {
    'robina_state_high': (-28.0799, 153.3871),
    'somerset_college': (-28.0412, 153.3102),
    'all_saints_anglican': (-28.0267, 153.3928),
    'varsity_college': (-28.0567, 153.3889)
}
SCHOOL_CATCHMENT_RADIUS_KM = 3.0

# Hinterland suburbs
HINTERLAND_SUBURBS = [
    'TAMBORINE MOUNTAIN', 'MOUNT TAMBORINE', 'NERANG', 
    'ADVANCETOWN', 'BONOGIN', 'GILSTON'
]

# Beachside suburbs (within 2km of beach)
BEACHSIDE_SUBURBS = [
    'SURFERS PARADISE', 'BROADBEACH', 'MAIN BEACH', 'MERMAID BEACH',
    'NOBBY BEACH', 'MIAMI', 'BURLEIGH HEADS', 'PALM BEACH',
    'CURRUMBIN', 'TUGUN', 'BILINGA', 'KIRRA', 'COOLANGATTA'
]

# Canal suburbs
CANAL_SUBURBS = [
    'HOPE ISLAND', 'BROADBEACH WATERS', 'MERMAID WATERS',
    'CLEAR ISLAND WATERS', 'PARADISE POINT'
]

# Key locations
KEY_LOCATIONS = {
    'cbd': (-28.0167, 153.4000),  # Southport
    'robina_town_centre': (-28.0799, 153.3871),
    'burleigh_beach': (-28.0908, 153.4506),
    'surfers_beach': (-28.0023, 153.4295),
    'broadbeach': (-28.0267, 153.4295),
    'main_beach': (-27.9667, 153.4300),
    'griffith_uni': (-28.0736, 153.3806),
    'bond_uni': (-28.0764, 153.4197),
    'pacific_fair': (-28.0344, 153.4295),
    'robina_hospital': (-28.0819, 153.3806),
    'gold_coast_airport': (-28.1644, 153.5047)
}

# ============================================================================
# PROCESSING SETTINGS
# ============================================================================

# Batch processing
BATCH_SIZE = 34  # Process all properties_for_sale properties
MAX_RETRIES = 3  # Retry failed enrichments

# GPT API settings
RUN_GPT_ENRICHMENT_AUTOMATICALLY = True  # Re-enabled for testing with FeatureAligner
SKIP_GPT_IF_EXISTS = True  # Don't re-enrich if GPT data already exists
SKIP_OSM_IF_EXISTS = True  # Don't re-enrich if OSM data already exists

# ============================================================================
# VALUATION QUERY
# ============================================================================

# Query for properties that need valuation
# Properties must NOT have an existing valuation in the last 7 days
VALUATION_QUERY = {
    '$or': [
        {'iteration_08_valuation': {'$exists': False}},
        {
            'iteration_08_valuation.valuation_date': {
                '$lt': {'$dateSubtract': {'startDate': '$$NOW', 'unit': 'day', 'amount': 7}}
            }
        }
    ],
    'LATITUDE': {'$exists': True, '$ne': None},
    'LONGITUDE': {'$exists': True, '$ne': None}
}

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = str(LOGS_DIR / "valuation.log")  # Log file path for GPT system

# ============================================================================
# MODEL FEATURES (179 features for Iteration 08)
# ============================================================================

# This will be constructed dynamically in the feature calculator
# based on the exact feature set used in training
