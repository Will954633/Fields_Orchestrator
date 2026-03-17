# Last Edit: 01/02/2026, Saturday, 8:50 am (Brisbane Time)
# MongoDB client for floor plan analysis operations
# Handles querying properties with floor plans and updating with analysis results

"""
MongoDB client module for floor plan analysis operations.
"""
import re
import time

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from datetime import datetime
from config import MONGODB_URI, DATABASE_NAME, TARGET_SUBURBS
from logger import logger

class MongoDBFloorPlanClient:
    """MongoDB client for managing floor plan analysis operations."""
    
    def __init__(self):
        """Initialize MongoDB client."""
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Establish connection to MongoDB."""
        try:
            logger.info(f"Connecting to MongoDB at {MONGODB_URI}")
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, retryWrites=False)
            
            # Test connection
            self.client.admin.command('ping')
            
            self.db = self.client[DATABASE_NAME]
            
            logger.info(f"Connected to MongoDB: {DATABASE_NAME}")
            logger.info(f"Target suburbs (collections): {', '.join(TARGET_SUBURBS)}")
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def _build_suburb_query(self):
        """
        Build MongoDB query to filter by target suburbs.
        
        Returns:
            Dictionary with suburb filter query
        """
        return {
            "$or": [
                {"suburb": {"$in": TARGET_SUBURBS}},
                {"address.suburb": {"$in": TARGET_SUBURBS}},
                {"property_details.suburb": {"$in": TARGET_SUBURBS}},
                {"scraped_data.suburb": {"$in": TARGET_SUBURBS}}
            ]
        }

    def _with_cosmos_retry(self, operation, label, max_attempts=4):
        """Retry Cosmos reads/writes on 16500 throttling before surfacing failure."""
        for attempt in range(max_attempts):
            try:
                return operation()
            except OperationFailure as e:
                is_throttled = getattr(e, "code", None) == 16500 or "TooManyRequests" in str(e) or "429" in str(e)
                if not is_throttled or attempt == max_attempts - 1:
                    logger.error(f"{label} failed: {e}")
                    raise
                details = str(getattr(e, "details", "") or e)
                match = re.search(r"RetryAfterMs[\":]?\s*(\d+)", details)
                retry_ms = int(match.group(1)) if match else 500
                wait_seconds = min(retry_ms / 1000.0 + 0.25, 5.0)
                logger.warning(
                    f"{label} throttled by Cosmos (attempt {attempt + 1}/{max_attempts}), retrying in {wait_seconds:.2f}s"
                )
                time.sleep(wait_seconds)
    
    def get_properties_needing_floor_plan_analysis(self):
        """
        Get properties that have been analyzed by Ollama but don't have floor plan analysis yet.
        
        Returns:
            List of property documents needing floor plan analysis
        """
        try:
            suburb_query = self._build_suburb_query()
            
            # Query for properties that:
            # 1. Have been analyzed by Ollama (have ollama_image_analysis)
            # 2. Don't have floor plan analysis yet
            # 3. Have images
            query = {
                "$and": [
                    {
                        "ollama_image_analysis": {
                            "$exists": True,
                            "$type": "array",
                            "$ne": []
                        }
                    },
                    {
                        "$or": [
                            {"ollama_floor_plan_analysis": {"$exists": False}},
                            {"ollama_floor_plan_analysis.has_floor_plan": {"$ne": True}}
                        ]
                    },
                    {
                        "$or": [
                            {
                                "scraped_data.images": {
                                    "$exists": True,
                                    "$type": "array",
                                    "$ne": []
                                }
                            },
                            {
                                "property_images": {
                                    "$exists": True,
                                    "$type": "array",
                                    "$ne": []
                                }
                            },
                            {
                                "images": {
                                    "$exists": True,
                                    "$type": "array",
                                    "$ne": []
                                }
                            }
                        ]
                    }
                ]
            }
            
            # Get all matching properties from all suburb collections
            all_properties = []
            
            for suburb in TARGET_SUBURBS:
                collection = self.db[suburb]
                properties = self._with_cosmos_retry(
                    lambda coll=collection: list(coll.find(query)),
                    f"get_properties_needing_floor_plan_analysis[{suburb}]",
                )
                
                if properties:
                    logger.info(f"Found {len(properties)} properties needing floor plan analysis in {suburb}")
                    all_properties.extend(properties)
            
            logger.info(f"Total properties needing floor plan analysis: {len(all_properties)}")
            
            return all_properties
            
        except OperationFailure:
            raise
    
    def count_properties_needing_floor_plan_analysis(self):
        """
        Count properties that need floor plan analysis.
        
        Returns:
            Count of properties needing analysis
        """
        try:
            suburb_query = self._build_suburb_query()
            
            query = {
                "$and": [
                    {
                        "ollama_image_analysis": {
                            "$exists": True,
                            "$type": "array",
                            "$ne": []
                        }
                    },
                    {
                        "$or": [
                            {"ollama_floor_plan_analysis": {"$exists": False}},
                            {"ollama_floor_plan_analysis.has_floor_plan": {"$ne": True}}
                        ]
                    }
                ]
            }
            
            total_count = 0
            
            for suburb in TARGET_SUBURBS:
                collection = self.db[suburb]
                count = self._with_cosmos_retry(
                    lambda coll=collection: coll.count_documents(query),
                    f"count_properties_needing_floor_plan_analysis[{suburb}]",
                )
                total_count += count
            
            logger.info(f"Properties needing floor plan analysis: {total_count}")
            
            return total_count
            
        except OperationFailure:
            raise
    
    def update_with_floor_plan_analysis(self, document_id, suburb, floor_plan_analysis, processing_time=None):
        """
        Update document with floor plan analysis results.
        
        Args:
            document_id: Document _id
            suburb: Suburb collection name (will try both lowercase and original case)
            floor_plan_analysis: Floor plan analysis results
            processing_time: Processing duration in seconds (optional)
            
        Returns:
            UpdateResult
        """
        try:
            # Try lowercase first (standard format)
            suburb_lower = suburb.lower()
            collection = self.db[suburb_lower]
            
            # Check if document exists in lowercase collection
            if self._with_cosmos_retry(
                lambda coll=collection: coll.count_documents({"_id": document_id}),
                f"update_with_floor_plan_analysis.lookup[{suburb_lower}]",
            ) == 0:
                # Try original case
                collection = self.db[suburb]
                logger.info(f"Using collection name: {suburb} (original case)")
            else:
                logger.info(f"Using collection name: {suburb_lower} (lowercase)")
            
            # Add processing metadata
            floor_plan_analysis["processed_at"] = datetime.utcnow()
            
            if processing_time is not None:
                floor_plan_analysis["processing_duration_seconds"] = processing_time
            
            update_operation = {
                "$set": {
                    "ollama_floor_plan_analysis": floor_plan_analysis
                }
            }
            
            result = self._with_cosmos_retry(
                lambda coll=collection: coll.update_one(
                    {"_id": document_id},
                    update_operation
                ),
                f"update_with_floor_plan_analysis[{suburb}]",
            )
            
            logger.info(f"Updated document {document_id} in {suburb} with floor plan analysis")
            return result
            
        except OperationFailure as e:
            logger.error(f"Failed to update document with floor plan analysis: {e}")
            raise
    
    def get_floor_plan_stats(self):
        """
        Get floor plan analysis statistics.
        
        Returns:
            Dictionary with statistics
        """
        try:
            suburb_query = self._build_suburb_query()
            
            stats = {
                "by_suburb": {},
                "total_with_floor_plans": 0,
                "total_analyzed": 0,
                "total_needing_analysis": 0
            }
            
            for suburb in TARGET_SUBURBS:
                collection = self.db[suburb]
                
                # Total properties in suburb
                total = self._with_cosmos_retry(
                    lambda coll=collection: coll.count_documents(suburb_query),
                    f"get_floor_plan_stats.total[{suburb}]",
                )
                
                # Properties with floor plan analysis
                with_analysis = self._with_cosmos_retry(
                    lambda coll=collection: coll.count_documents({
                        "$and": [
                            suburb_query,
                            {"ollama_floor_plan_analysis.has_floor_plan": True}
                        ]
                    }),
                    f"get_floor_plan_stats.with_analysis[{suburb}]",
                )
                
                # Properties needing analysis (have ollama_image_analysis but no floor plan analysis)
                needing_analysis = self._with_cosmos_retry(
                    lambda coll=collection: coll.count_documents({
                        "$and": [
                            {"ollama_image_analysis": {"$exists": True, "$ne": []}},
                            {
                                "$or": [
                                    {"ollama_floor_plan_analysis": {"$exists": False}},
                                    {"ollama_floor_plan_analysis.has_floor_plan": {"$ne": True}}
                                ]
                            }
                        ]
                    }),
                    f"get_floor_plan_stats.needing_analysis[{suburb}]",
                )
                
                stats["by_suburb"][suburb] = {
                    "total": total,
                    "with_floor_plan_analysis": with_analysis,
                    "needing_analysis": needing_analysis
                }
                
                stats["total_with_floor_plans"] += with_analysis
                stats["total_needing_analysis"] += needing_analysis
            
            stats["total_analyzed"] = stats["total_with_floor_plans"]
            
            return stats
            
        except OperationFailure:
            raise
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
