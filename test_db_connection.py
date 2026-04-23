"""
Test script to verify MongoDB connection and schema discovery.
Run: python test_db_connection.py
"""

import asyncio
import json
from utils.db import MongoDBConnector
from config import get_settings


async def test_connection():
    settings = get_settings()
    connector = MongoDBConnector()
    
    try:
        # Connect to MongoDB
        print("=" * 50)
        print("CONNECTING TO MONGODB")
        print("=" * 50)
        await connector.connect(settings.mongodb_url, settings.mongodb_database)
        
        # List all collections
        print("\n" + "=" * 50)
        print("COLLECTIONS IN DATABASE")
        print("=" * 50)
        collections = await connector.list_collections()
        
        if not collections:
            print("No collections found in database.")
            print("The database is empty or doesn't exist yet.")
        else:
            for idx, coll in enumerate(collections, 1):
                print(f"  {idx}. {coll}")
        
        # Discover full schema
        if collections:
            print("\n" + "=" * 50)
            print("FULL DATABASE SCHEMA")
            print("=" * 50)
            schema = await connector.discover_full_schema()
            print(json.dumps(schema, indent=2, default=str))
            
            # Fetch sample records from first collection
            print("\n" + "=" * 50)
            print(f"SAMPLE RECORDS FROM '{collections[0]}'")
            print("=" * 50)
            records = await connector.fetch_records(collections[0], limit=5)
            print(json.dumps(records, indent=2, default=str))
        
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
    finally:
        await connector.disconnect()


def test_connection_sync():
    """Sync version for testing."""
    settings = get_settings()
    connector = MongoDBConnector()
    
    try:
        print("=" * 50)
        print("CONNECTING TO MONGODB (SYNC)")
        print("=" * 50)
        connector.connect_sync(settings.mongodb_url, settings.mongodb_database)
        
        print("\n" + "=" * 50)
        print("COLLECTIONS IN DATABASE")
        print("=" * 50)
        collections = connector.list_collections_sync()
        
        if not collections:
            print("No collections found in database.")
            print("The database is empty or doesn't exist yet.")
        else:
            for idx, coll in enumerate(collections, 1):
                print(f"  {idx}. {coll}")
            
            print("\n" + "=" * 50)
            print("FULL DATABASE SCHEMA")
            print("=" * 50)
            schema = connector.discover_full_schema_sync()
            print(json.dumps(schema, indent=2, default=str))
        
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
    finally:
        connector.disconnect_sync()


if __name__ == "__main__":
    print("\n🔹 Testing ASYNC connection...\n")
    asyncio.run(test_connection())
    
    print("\n" + "=" * 60)
    print("\n🔹 Testing SYNC connection...\n")
    test_connection_sync()
