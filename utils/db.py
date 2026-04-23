from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from typing import Any
import asyncio


class MongoDBConnector:
    """
    MongoDB connector with schema discovery capabilities.
    Connects to any MongoDB database and discovers its structure dynamically.
    """
    
    def __init__(self):
        self.async_client: AsyncIOMotorClient | None = None
        self.sync_client: MongoClient | None = None
        self.database: AsyncIOMotorDatabase | None = None
        self.db_name: str | None = None
    
    async def connect(self, connection_string: str, database_name: str) -> None:
        """Establish async connection to MongoDB."""
        self.async_client = AsyncIOMotorClient(connection_string)
        self.database = self.async_client[database_name]
        self.db_name = database_name
        
        # Verify connection
        await self.async_client.admin.command('ping')
        print(f"Connected to MongoDB database: {database_name}")
    
    def connect_sync(self, connection_string: str, database_name: str) -> None:
        """Establish sync connection to MongoDB."""
        self.sync_client = MongoClient(connection_string)
        self.database = self.sync_client[database_name]
        self.db_name = database_name
        
        # Verify connection
        self.sync_client.admin.command('ping')
        print(f"Connected to MongoDB database: {database_name}")
    
    async def disconnect(self) -> None:
        """Close the database connection."""
        if self.async_client:
            self.async_client.close()
            self.async_client = None
            self.database = None
            self.db_name = None
            print("MongoDB connection closed")
    
    async def reconnect(self, connection_string: str, database_name: str) -> None:
        """Disconnect and connect with new credentials (runtime reconfiguration)."""
        await self.disconnect()
        await self.connect(connection_string, database_name)
    
    def disconnect_sync(self) -> None:
        """Close the sync database connection."""
        if self.sync_client:
            self.sync_client.close()
            print("MongoDB connection closed")
    
    async def list_collections(self) -> list[str]:
        """Get all collection names in the database."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collections = await self.database.list_collection_names()
        return collections
    
    def list_collections_sync(self) -> list[str]:
        """Get all collection names (sync version)."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        return self.database.list_collection_names()
    
    async def get_collection_schema(self, collection_name: str, sample_size: int = 100) -> dict[str, Any]:
        """
        Analyze a collection and infer its schema from sample documents.
        Returns field names, types, and sample values.
        """
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collection = self.database[collection_name]
        
        # Get document count
        total_count = await collection.count_documents({})
        
        # Sample documents to infer schema
        cursor = collection.find().limit(sample_size)
        documents = await cursor.to_list(length=sample_size)
        
        # Analyze fields across all sampled documents
        field_info = {}
        for doc in documents:
            self._analyze_document(doc, field_info)
        
        return {
            "collection_name": collection_name,
            "total_documents": total_count,
            "sampled_documents": len(documents),
            "fields": field_info
        }
    
    def get_collection_schema_sync(self, collection_name: str, sample_size: int = 100) -> dict[str, Any]:
        """Analyze a collection schema (sync version)."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collection = self.database[collection_name]
        
        total_count = collection.count_documents({})
        documents = list(collection.find().limit(sample_size))
        
        field_info = {}
        for doc in documents:
            self._analyze_document(doc, field_info)
        
        return {
            "collection_name": collection_name,
            "total_documents": total_count,
            "sampled_documents": len(documents),
            "fields": field_info
        }
    
    def _analyze_document(self, doc: dict, field_info: dict, prefix: str = "") -> None:
        """Recursively analyze document fields and their types."""
        for key, value in doc.items():
            field_path = f"{prefix}.{key}" if prefix else key
            
            if field_path not in field_info:
                field_info[field_path] = {
                    "types": set(),
                    "sample_values": [],
                    "is_nested": False
                }
            
            value_type = type(value).__name__
            field_info[field_path]["types"].add(value_type)
            
            # Store sample values (limit to 3)
            if len(field_info[field_path]["sample_values"]) < 3:
                if value_type not in ["dict", "list"]:
                    field_info[field_path]["sample_values"].append(value)
            
            # Recurse into nested documents
            if isinstance(value, dict):
                field_info[field_path]["is_nested"] = True
                self._analyze_document(value, field_info, field_path)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                field_info[field_path]["is_nested"] = True
                self._analyze_document(value[0], field_info, f"{field_path}[]")
    
    async def fetch_records(
        self, 
        collection_name: str, 
        query: dict = None, 
        limit: int = 10,
        skip: int = 0
    ) -> list[dict]:
        """Fetch records from a collection with optional filtering."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collection = self.database[collection_name]
        query = query or {}
        
        cursor = collection.find(query).skip(skip).limit(limit)
        documents = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for doc in documents:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
        
        return documents
    
    def fetch_records_sync(
        self, 
        collection_name: str, 
        query: dict = None, 
        limit: int = 10,
        skip: int = 0
    ) -> list[dict]:
        """Fetch records (sync version)."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collection = self.database[collection_name]
        query = query or {}
        
        documents = list(collection.find(query).skip(skip).limit(limit))
        
        for doc in documents:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
        
        return documents
    
    async def discover_full_schema(self) -> dict[str, Any]:
        """
        Discover the complete database schema.
        Returns all collections with their structures.
        """
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collections = await self.list_collections()
        
        schema = {
            "database": self.db_name,
            "total_collections": len(collections),
            "collections": {}
        }
        
        for collection_name in collections:
            schema["collections"][collection_name] = await self.get_collection_schema(collection_name)
        
        # Convert sets to lists for JSON serialization
        for coll_name, coll_info in schema["collections"].items():
            for field_name, field_data in coll_info["fields"].items():
                field_data["types"] = list(field_data["types"])
        
        return schema
    
    def discover_full_schema_sync(self) -> dict[str, Any]:
        """Discover complete database schema (sync version)."""
        if self.database is None:
            raise ConnectionError("Not connected to database")
        
        collections = self.list_collections_sync()
        
        schema = {
            "database": self.db_name,
            "total_collections": len(collections),
            "collections": {}
        }
        
        for collection_name in collections:
            schema["collections"][collection_name] = self.get_collection_schema_sync(collection_name)
        
        for coll_name, coll_info in schema["collections"].items():
            for field_name, field_data in coll_info["fields"].items():
                field_data["types"] = list(field_data["types"])
        
        return schema


# Singleton instance for easy import
mongodb_connector = MongoDBConnector()


# Convenience functions
async def get_database() -> AsyncIOMotorDatabase:
    """Get the current database instance."""
    if mongodb_connector.database is None:
        raise ConnectionError("Database not connected. Call connect() first.")
    return mongodb_connector.database
