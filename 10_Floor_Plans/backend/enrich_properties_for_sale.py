#!/usr/bin/env python3
"""
Property Enrichment Pipeline

Last Updated: 30/01/2026, 4:26 PM (Brisbane Time)

This script enriches properties in the properties_for_sale collection with:
1. Floor area from floor_plan_analysis.internal_floor_area.value
2. Lot size from Gold_Coast.[suburb].lot_size_sqm
3. Transaction history from Gold_Coast.[suburb].scraped_data.property_timeline
4. Pre-calculated capital gain metrics

The enriched data is stored in the 'enriched_data' field of each property document,
allowing the API to return pre-calculated values without runtime overhead.

Usage:
    # Enrich all properties
    python3 enrich_properties_for_sale.py --all
    
    # Enrich only properties without enriched_data
    python3 enrich_properties_for_sale.py --new-only
    
    # Enrich specific property by ID
    python3 enrich_properties_for_sale.py --id 693e8ea2ee434af1738b8f89
    
    # Dry run (show what would be enriched without saving)
    python3 enrich_properties_for_sale.py --all --dry-run
"""

import argparse
import logging
import re
import sys
import time as _time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from bson import ObjectId


def _cosmos_retry(func, *args, max_retries=5, **kwargs):
    """Execute a MongoDB operation with Cosmos DB 429 retry logic.
    Matches shared/ru_guard.py: 5 attempts, broad error detection, exponential backoff.
    """
    import re as _re
    _RETRY_AFTER_RE = _re.compile(r"RetryAfterMs[\":]?\s*(\d+)", _re.IGNORECASE)
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except OperationFailure as e:
            msg = str(e).lower()
            is_throttled = (
                getattr(e, 'code', None) == 16500
                or "toomanyrequests" in msg
                or "requestratetoolarge" in msg
                or "429" in msg
            )
            if is_throttled and attempt < max_retries - 1:
                details_str = str(getattr(e, 'details', ''))
                match = _RETRY_AFTER_RE.search(details_str) or _RETRY_AFTER_RE.search(str(e))
                wait_ms = int(match.group(1)) if match else 500
                sleep_s = min(max(0.3, wait_ms / 1000.0 + 0.25), 5.0)
                _time.sleep(sleep_s)
                continue
            raise

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PropertyEnricher:
    """Enriches properties with floor area, lot size, transactions, and capital gain."""
    
    def __init__(self):
        """Initialize MongoDB connection."""
        import os

        # Use environment variable for MongoDB URI (Azure Cosmos DB on VM, local on dev)
        mongodb_uri = os.environ.get('COSMOS_CONNECTION_STRING') or os.environ.get('MONGODB_URI') or "mongodb://127.0.0.1:27017/"

        self.client = MongoClient(mongodb_uri, retryWrites=False)
        self.db = self.client["Gold_Coast"]
        self.gold_coast_db = self.client["Gold_Coast"]  # Master property data DB (has lot_size_sqm, complete_address, property_timeline)

        logger.info(f"✓ Connected to MongoDB (using {'environment variable' if 'COSMOS' in mongodb_uri or 'fieldspropertydataserverless' in mongodb_uri else 'localhost'})")
    
    def extract_suburb_from_address(self, address: str) -> str:
        """Extract suburb from address string."""
        if not address:
            return ""
        
        # Common pattern: "123 Street Name, Suburb QLD 4000"
        parts = address.split(',')
        if len(parts) >= 2:
            suburb_part = parts[-1].strip()
            # Remove state and postcode
            suburb_part = re.sub(
                r'\s+(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s*\d*$',
                '',
                suburb_part,
                flags=re.IGNORECASE
            )
            return suburb_part.strip()
        
        return ""
    
    def get_floor_area(self, property_doc: dict) -> Optional[float]:
        """Extract floor area from floor_plan_analysis or ollama_floor_plan_analysis."""
        # Try new field first (ollama_floor_plan_analysis from GPT Vision analysis)
        ollama_fp = property_doc.get('ollama_floor_plan_analysis', {})
        if isinstance(ollama_fp, dict) and ollama_fp.get('has_floor_plan'):
            fp_data = ollama_fp.get('floor_plan_data', {})
            if not isinstance(fp_data, dict):
                fp_data = {}
            internal = fp_data.get('internal_floor_area', {})
            if isinstance(internal, dict):
                value = internal.get('value')
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass
            # Fall back to total_floor_area if no internal
            total = fp_data.get('total_floor_area', {})
            if isinstance(total, dict):
                value = total.get('value')
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass

        # Fall back to old field (floor_plan_analysis)
        floor_plan_analysis = property_doc.get('floor_plan_analysis', {})
        internal_floor_area = floor_plan_analysis.get('internal_floor_area', {})
        if isinstance(internal_floor_area, dict):
            value = internal_floor_area.get('value')
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass
        # Also check total_floor_area in legacy field
        total_floor_area = floor_plan_analysis.get('total_floor_area', {})
        if isinstance(total_floor_area, dict):
            value = total_floor_area.get('value')
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass

        # Final fallback: root-level total_floor_area (written by step 11 parse_room_dimensions)
        root_tfa = property_doc.get('total_floor_area')
        if root_tfa is not None:
            try:
                return float(root_tfa)
            except (ValueError, TypeError):
                pass

        return None
    
    def normalize_address_for_matching(self, address: str) -> str:
        """
        Normalize address for matching between databases.
        
        Gold_Coast DB format: "16 CHELTENHAM DRIVE ROBINA QLD 4226"
        properties_for_sale format: "31 Nuthatch Street Burleigh, Waters, QLD 4220"
        
        Returns normalized format: "16 CHELTENHAM DRIVE ROBINA"
        """
        if not address:
            return ""
        
        # Remove commas and extra spaces
        normalized = address.replace(",", " ")
        normalized = " ".join(normalized.split())
        
        # Convert to uppercase
        normalized = normalized.upper()
        
        # Remove state and postcode (QLD, NSW, etc. and 4-digit postcodes)
        normalized = re.sub(r'\s+(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s*\d{4}$', '', normalized)
        normalized = re.sub(r'\s+\d{4}$', '', normalized)  # Remove postcode if state was already removed
        
        return normalized.strip()
    
    def _query_with_retry(self, collection, query, max_retries=3):
        """Execute a find_one query with retry on Cosmos DB 429 rate limits."""
        import time as _time
        for attempt in range(max_retries):
            try:
                return collection.find_one(query)
            except Exception as e:
                if '16500' in str(e) and attempt < max_retries - 1:
                    wait = float(2 ** attempt)
                    logger.debug(f"Rate limited (attempt {attempt+1}), waiting {wait}s...")
                    _time.sleep(wait)
                    continue
                raise
        return None

    def get_lot_size(self, address: str, suburb: str, property_doc: dict = None) -> Optional[float]:
        """Extract lot size from Gold_Coast.[suburb] collection, with floor_plan_analysis fallback."""
        if not suburb:
            return None

        # Normalize suburb name for collection lookup
        suburb_collection_name = suburb.lower().replace(" ", "_")

        try:
            suburb_collection = self.gold_coast_db[suburb_collection_name]

            # Normalize the search address
            normalized_search = self.normalize_address_for_matching(address)

            # Try exact match on complete_address field first
            gc_doc = self._query_with_retry(suburb_collection, {"complete_address": address.upper()})

            # If no exact match, try normalized matching on complete_address
            if not gc_doc and normalized_search:
                gc_doc = self._query_with_retry(suburb_collection, {
                    "complete_address": {"$regex": f"^{re.escape(normalized_search)}", "$options": "i"}
                })

            if gc_doc:
                lot_size = gc_doc.get('lot_size_sqm')
                if lot_size is not None:
                    try:
                        return float(lot_size)
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            logger.warning(f"Could not get lot size for {address} from Gold_Coast DB: {e}")

        # Fallback: floor_plan_analysis.total_land_area.value (from GPT Vision analysis)
        if property_doc:
            for fpa_field in ('ollama_floor_plan_analysis', 'floor_plan_analysis'):
                fpa = property_doc.get(fpa_field, {})
                if not isinstance(fpa, dict):
                    continue
                # ollama path: ollama_floor_plan_analysis.floor_plan_data.total_land_area.value
                if fpa_field == 'ollama_floor_plan_analysis':
                    fpa = fpa.get('floor_plan_data', {})
                    if not isinstance(fpa, dict):
                        continue
                land_area = fpa.get('total_land_area', {})
                if isinstance(land_area, dict):
                    value = land_area.get('value')
                    if value is not None:
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            pass

        return None
    
    def get_transactions(self, address: str, suburb: str) -> List[Dict[str, Any]]:
        """Extract transaction history from Gold_Coast.[suburb].scraped_data.property_timeline."""
        if not suburb:
            return []
        
        transactions = []
        suburb_collection_name = suburb.lower().replace(" ", "_")
        
        try:
            suburb_collection = self.gold_coast_db[suburb_collection_name]
            
            # Normalize the search address
            normalized_search = self.normalize_address_for_matching(address)
            
            # Try exact match on complete_address field first
            gc_doc = suburb_collection.find_one({"complete_address": address.upper()})
            
            # If no exact match, try normalized matching on complete_address
            if not gc_doc and normalized_search:
                gc_doc = suburb_collection.find_one({
                    "complete_address": {"$regex": f"^{re.escape(normalized_search)}", "$options": "i"}
                })
            
            if gc_doc:
                scraped_data = gc_doc.get("scraped_data", {})
                timeline = scraped_data.get("property_timeline", [])
                
                for event in timeline:
                    if not isinstance(event, dict):
                        continue
                    
                    # Check if this is a sale event
                    is_sale = bool(event.get("is_sold")) or (event.get("category") == "Sale")
                    if not is_sale:
                        continue
                    
                    # Extract transaction details
                    date = event.get("date")
                    price = event.get("price")
                    
                    if date and price:
                        try:
                            # Normalize date to ISO format
                            if isinstance(date, str):
                                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                                date_str = date_obj.strftime('%Y-%m-%d')
                            else:
                                date_str = str(date)
                            
                            # Normalize price to float
                            if isinstance(price, str):
                                # Remove currency symbols and commas
                                price_clean = re.sub(r'[^\d.]', '', price)
                                price_float = float(price_clean)
                            else:
                                price_float = float(price)
                            
                            transactions.append({
                                "date": date_str,
                                "price": price_float,
                                "type": "Sale"
                            })
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Could not parse transaction: {e}")
                            continue
        
        except Exception as e:
            logger.debug(f"Could not get transactions for {address}: {e}")
        
        # Sort by date (oldest first)
        transactions.sort(key=lambda x: x['date'])
        
        return transactions
    
    def calculate_capital_gain(
        self,
        transactions: List[Dict[str, Any]],
        suburb: str
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate capital gain metrics from transaction history.
        
        Uses the same logic as frontend calculateCapitalGain utility:
        1. Find transaction closest to 10 years ago
        2. Look up suburb median prices at sale date and today
        3. Index the sale price to today using median growth
        4. Calculate annualized return
        """
        if not transactions or not suburb:
            return None
        
        # Find transaction closest to 10 years ago
        today = datetime.now()
        ten_years_ago = datetime(today.year - 10, today.month, today.day)
        
        best_tx = None
        best_diff = float('inf')
        
        for tx in transactions:
            try:
                tx_date = datetime.fromisoformat(tx['date'])
                diff = abs((tx_date - ten_years_ago).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    best_tx = tx
            except (ValueError, TypeError):
                continue
        
        if not best_tx:
            return None
        
        # Calculate years held
        try:
            sale_date = datetime.fromisoformat(best_tx['date'])
            years_held = (today - sale_date).days / 365.25
            
            # Require at least 2 years for meaningful calculation
            if years_held < 2:
                return None
        except (ValueError, TypeError):
            return None
        
        # TODO: Look up suburb median prices and calculate growth
        # For now, return basic transaction info
        # This will be enhanced when historical price data is integrated
        
        return {
            "has_data": True,
            "oldest_transaction_date": best_tx['date'],
            "oldest_transaction_price": best_tx['price'],
            "years_held": round(years_held, 1),
            "note": "Capital gain calculation requires historical median price data"
        }
    
    def enrich_property(self, property_doc: dict, dry_run: bool = False) -> Dict[str, Any]:
        """
        Enrich a single property with all available data.
        
        Returns enriched_data dict to be stored in the property document.
        """
        address = property_doc.get('address', '')
        suburb = property_doc.get('suburb', '') or self.extract_suburb_from_address(address)
        
        logger.info(f"Enriching: {address}")
        
        # Extract enrichment data
        floor_area = self.get_floor_area(property_doc)
        lot_size = self.get_lot_size(address, suburb, property_doc)
        transactions = self.get_transactions(address, suburb)
        capital_gain = self.calculate_capital_gain(transactions, suburb)
        
        # Build enriched data
        enriched_data = {
            "floor_area_sqm": floor_area,
            "lot_size_sqm": lot_size,
            "transactions": transactions,
            "capital_gain": capital_gain,
            "last_enriched": datetime.now().isoformat()
        }
        
        # Log what was found
        logger.info(f"  Floor Area: {floor_area or 'N/A'} sqm")
        logger.info(f"  Lot Size: {lot_size or 'N/A'} sqm")
        logger.info(f"  Transactions: {len(transactions)} found")
        logger.info(f"  Capital Gain: {'Available' if capital_gain else 'N/A'}")
        
        # Update database (unless dry run)
        if not dry_run:
            col_name = property_doc.get('_collection') or suburb.lower().replace(' ', '_')
            _cosmos_retry(
                self.db[col_name].update_one,
                {"_id": property_doc["_id"]},
                {"$set": {"enriched_data": enriched_data}}
            )
            logger.info(f"  ✓ Saved to database")
        else:
            logger.info(f"  (Dry run - not saved)")
        
        return enriched_data
    
    def enrich_all(self, new_only: bool = False, dry_run: bool = False):
        """Enrich all properties across target suburb collections."""
        TARGET_SUBURBS = ['robina', 'varsity_lakes', 'burleigh_waters']
        all_cols = set(self.db.list_collection_names())
        suburb_cols = [s for s in TARGET_SUBURBS if s in all_cols]

        # Only enrich active listings (excludes ~40K cadastral records without listing_status)
        base_filter = {"listing_status": "for_sale"}
        # new_only: skip properties that already have enriched_data with a non-null floor_area_sqm
        # This ensures properties with null enriched_data get re-enriched (e.g., after floor plan analysis runs)
        if new_only:
            query = {**base_filter, "$or": [{"enriched_data": {"$exists": False}}, {"enriched_data.floor_area_sqm": None}]}
        else:
            query = base_filter

        properties = []
        for col_name in suburb_cols:
            for doc in self.db[col_name].find(query):
                doc['_collection'] = col_name
                properties.append(doc)
        total = len(properties)
        
        logger.info(f"Found {total} properties to enrich")
        logger.info("=" * 80)
        
        enriched_count = 0
        error_count = 0
        
        import time as _time
        for i, prop in enumerate(properties, 1):
            try:
                logger.info(f"\n[{i}/{total}]")
                self.enrich_property(prop, dry_run=dry_run)
                enriched_count += 1
                _time.sleep(0.5)  # Throttle to avoid Cosmos DB 429 rate limits
            except Exception as e:
                logger.error(f"Error enriching property {prop.get('address')}: {e}")
                error_count += 1
        
        logger.info("\n" + "=" * 80)
        logger.info(f"Enrichment complete!")
        logger.info(f"  Enriched: {enriched_count}")
        logger.info(f"  Errors: {error_count}")
        logger.info(f"  Total: {total}")
    
    def enrich_by_id(self, property_id: str, dry_run: bool = False):
        """Enrich a specific property by ID."""
        try:
            suburb_cols = [c for c in self.db.list_collection_names() if c not in ('suburb_statistics', 'suburb_median_prices')]
            prop = None
            for col_name in suburb_cols:
                prop = self.db[col_name].find_one({"_id": ObjectId(property_id)})
                if prop:
                    prop['_collection'] = col_name
                    break
            
            if not prop:
                logger.error(f"Property {property_id} not found")
                return
            
            self.enrich_property(prop, dry_run=dry_run)
            logger.info("✓ Enrichment complete")
            
        except Exception as e:
            logger.error(f"Error enriching property {property_id}: {e}")
    
    def close(self):
        """Close MongoDB connection."""
        self.client.close()


def main():
    """Main entry point."""
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="16", process_name="Enrich Properties For Sale"
    ) if _MONITOR_AVAILABLE else None
    if monitor: monitor.start()

    parser = argparse.ArgumentParser(
        description="Enrich properties in properties_for_sale collection"
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Enrich all properties'
    )
    parser.add_argument(
        '--new-only',
        action='store_true',
        help='Only enrich properties without enriched_data'
    )
    parser.add_argument(
        '--id',
        type=str,
        help='Enrich specific property by ID'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be enriched without saving to database'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not (args.all or args.new_only or args.id):
        parser.error("Must specify --all, --new-only, or --id")
    
    # Run enrichment
    enricher = PropertyEnricher()

    try:
        if args.id:
            enricher.enrich_by_id(args.id, dry_run=args.dry_run)
        else:
            enricher.enrich_all(new_only=args.new_only, dry_run=args.dry_run)
        if monitor: monitor.finish(status="success")
    except Exception as e:
        if monitor:
            monitor.log_error(str(e), file=__file__)
            monitor.finish(status="failed")
        raise
    finally:
        enricher.close()


if __name__ == "__main__":
    main()
