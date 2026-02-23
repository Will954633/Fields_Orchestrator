#!/usr/bin/env python3
"""
Address Format Analysis Script
Last Updated: 12/02/2026, 10:19 AM (Wednesday) - Brisbane Time

Description: Analyzes address formats in both databases to understand differences
and design a robust address matching algorithm.
"""

import os
from pymongo import MongoClient
from collections import Counter
import re

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')

def analyze_addresses():
    """Analyze address formats from both databases"""
    
    client = MongoClient(MONGODB_URI, retryWrites=False)
    
    print("=" * 80)
    print("ADDRESS FORMAT ANALYSIS")
    print("=" * 80)
    print()
    
    # Sample suburbs to analyze
    suburbs = ['varsity_lakes', 'mudgeeraba', 'robina', 'carrara']
    
    for suburb in suburbs:
        print(f"\n{'='*80}")
        print(f"SUBURB: {suburb.upper()}")
        print(f"{'='*80}\n")
        
        # Get samples from for-sale database
        for_sale_db = client['Gold_Coast_Currently_For_Sale']
        for_sale_coll = for_sale_db[suburb]
        
        print(f"FOR-SALE DATABASE (Gold_Coast_Currently_For_Sale.{suburb}):")
        print("-" * 80)
        for_sale_samples = list(for_sale_coll.find({}, {'address': 1, '_id': 0}).limit(5))
        for i, doc in enumerate(for_sale_samples, 1):
            addr = doc.get('address', 'N/A')
            print(f"  {i}. {addr}")
        
        # Get samples from master database
        master_db = client['Gold_Coast']
        master_coll = master_db[suburb]
        
        print(f"\nMASTER DATABASE (Gold_Coast.{suburb}):")
        print("-" * 80)
        master_samples = list(master_coll.find({}, {'complete_address': 1, '_id': 0}).limit(5))
        for i, doc in enumerate(master_samples, 1):
            addr = doc.get('complete_address', 'N/A')
            print(f"  {i}. {addr}")
        
        # Analyze patterns
        print(f"\nPATTERN ANALYSIS:")
        print("-" * 80)
        
        # Check for common issues
        for_sale_addrs = [doc.get('address', '') for doc in for_sale_coll.find({}, {'address': 1}).limit(100)]
        master_addrs = [doc.get('complete_address', '') for doc in master_coll.find({}, {'complete_address': 1}).limit(100)]
        
        # Check for comma issues
        for_sale_comma_count = sum(1 for addr in for_sale_addrs if ', ' in addr.split(',')[0])
        master_comma_count = sum(1 for addr in master_addrs if ', ' in addr.split(',')[0])
        
        print(f"  For-Sale addresses with extra commas: {for_sale_comma_count}/{len(for_sale_addrs)}")
        print(f"  Master addresses with extra commas: {master_comma_count}/{len(master_addrs)}")
        
        # Check for unit numbers
        for_sale_units = sum(1 for addr in for_sale_addrs if re.match(r'^\d+\s+\d+\s+', addr))
        master_units = sum(1 for addr in master_addrs if re.match(r'^\d+\s+\d+\s+', addr))
        
        print(f"  For-Sale addresses with unit numbers: {for_sale_units}/{len(for_sale_addrs)}")
        print(f"  Master addresses with unit numbers: {master_units}/{len(master_addrs)}")
    
    client.close()
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    analyze_addresses()
