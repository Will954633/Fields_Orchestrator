#!/usr/bin/env python3
# Last Edit: 11/02/2026, 2:59 PM (Tuesday) - Brisbane Time
# Description: Test MongoDB connection using MONGODB_URI environment variable

import os
import sys
from pymongo import MongoClient

def test_connection():
    """Test MongoDB connection using environment variable"""
    
    # Get connection string from environment
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
    
    print(f"Testing MongoDB connection...")
    print(f"URI starts with: {mongodb_uri[:30]}...")
    
    try:
        # Attempt connection
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10000)
        
        # Test the connection
        client.admin.command('ping')
        
        # Get database info
        db = client['property_data']
        collections = db.list_collection_names()
        
        print(f"✅ Successfully connected to MongoDB!")
        print(f"Database: property_data")
        print(f"Collections: {len(collections)}")
        print(f"Collection names: {', '.join(collections[:5])}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
