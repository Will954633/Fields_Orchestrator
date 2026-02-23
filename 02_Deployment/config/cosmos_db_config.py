#!/usr/bin/env python3
"""
Cosmos DB Connection Configuration Helper
Last Edit: 07/02/2026, 6:29 PM (Wednesday) - Brisbane Time

Provides a drop-in replacement for local MongoDB connections.
Import this module instead of creating MongoClient directly to get
Cosmos DB-compatible connections with proper settings.

Usage:
    from cosmos_db_config import get_mongo_client, get_connection_uri

    # Get a configured client
    client = get_mongo_client()
    db = client["property_data"]

    # Or just get the URI for existing code
    uri = get_connection_uri()
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Try to load .env from deployment directory
_env_locations = [
    Path(__file__).parent.parent / ".env",  # 02_Deployment/.env
    Path(__file__).parent / ".env",          # config/.env
    Path.home() / ".fields_orchestrator" / ".env",  # Home directory
]

for env_path in _env_locations:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip('"').strip("'")
                    os.environ.setdefault(key.strip(), value)
        break


def get_connection_uri() -> str:
    """
    Get the MongoDB/Cosmos DB connection URI.
    
    Priority:
    1. COSMOS_CONNECTION_STRING environment variable
    2. MONGODB_URI environment variable
    3. Default local MongoDB URI
    
    Returns:
        Connection URI string
    """
    # Check for Cosmos DB connection string first
    cosmos_uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if cosmos_uri:
        return cosmos_uri
    
    # Fall back to MongoDB URI
    mongo_uri = os.environ.get("MONGODB_URI", "")
    if mongo_uri:
        return mongo_uri
    
    # Default to local MongoDB
    return "mongodb://127.0.0.1:27017/"


def is_cosmos_db() -> bool:
    """Check if we're connecting to Cosmos DB (vs local MongoDB)."""
    uri = get_connection_uri()
    return "cosmos.azure.com" in uri or "cosmos.azure.cn" in uri


def get_mongo_client(
    uri: Optional[str] = None,
    server_selection_timeout_ms: int = 30000,
    socket_timeout_ms: int = 60000,
    connect_timeout_ms: int = 30000,
):
    """
    Get a configured MongoClient that works with both local MongoDB and Cosmos DB.
    
    Args:
        uri: Optional connection URI (uses environment if not provided)
        server_selection_timeout_ms: Server selection timeout
        socket_timeout_ms: Socket timeout
        connect_timeout_ms: Connection timeout
    
    Returns:
        Configured MongoClient instance
    """
    from pymongo import MongoClient
    
    if uri is None:
        uri = get_connection_uri()
    
    # Base kwargs that work for both local and Cosmos DB
    kwargs = {
        "serverSelectionTimeoutMS": server_selection_timeout_ms,
        "socketTimeoutMS": socket_timeout_ms,
        "connectTimeoutMS": connect_timeout_ms,
    }
    
    # Cosmos DB specific settings
    if "cosmos.azure.com" in uri:
        kwargs["retryWrites"] = False
        kwargs["maxIdleTimeMS"] = 120000
        # Cosmos DB benefits from connection pooling
        kwargs["maxPoolSize"] = 10
        kwargs["minPoolSize"] = 1
    
    return MongoClient(uri, **kwargs)


def get_client_kwargs() -> dict:
    """
    Get kwargs dict for MongoClient that works with Cosmos DB.
    Useful when you need to pass kwargs to existing code.
    
    Returns:
        Dict of kwargs for MongoClient constructor
    """
    uri = get_connection_uri()
    
    kwargs = {
        "serverSelectionTimeoutMS": 30000,
        "socketTimeoutMS": 60000,
        "connectTimeoutMS": 30000,
    }
    
    if "cosmos.azure.com" in uri:
        kwargs["retryWrites"] = False
        kwargs["maxIdleTimeMS"] = 120000
    
    return kwargs


# Convenience: print connection info when run directly
if __name__ == "__main__":
    uri = get_connection_uri()
    is_cosmos = is_cosmos_db()
    
    print(f"Connection Type: {'Azure Cosmos DB' if is_cosmos else 'Local MongoDB'}")
    
    if "@" in uri:
        # Mask credentials
        parts = uri.split("@")
        masked = parts[0][:20] + "...@" + parts[1][:50] + "..."
    else:
        masked = uri
    
    print(f"URI: {masked}")
    print(f"Cosmos DB Settings: {'Enabled' if is_cosmos else 'Not needed'}")
