"""
ChromaDB Schema Store - Semantic search for MongoDB collections using sentence transformers.
Dynamically embeds collection schemas for intelligent query routing.
"""

import os
import asyncio
from typing import Any, Optional
from datetime import datetime
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from config import get_settings

# Global instances
_chroma_client: Optional[chromadb.PersistentClient] = None
_embedding_model: Optional[SentenceTransformer] = None
_collection_name = "schema_catalog"


def get_embedding_model() -> SentenceTransformer:
    """Get or create sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        print("[SchemaEmbeddings] Loading sentence transformer model...")
        # Use free HuggingFace model - no API key needed
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[SchemaEmbeddings] Model loaded: all-MiniLM-L6-v2")
    return _embedding_model


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        settings = get_settings()
        chroma_dir = settings.chroma_persist_directory or "./chroma_db"
        
        _chroma_client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )
        print(f"[SchemaEmbeddings] ChromaDB client initialized: {chroma_dir}")
    return _chroma_client


def get_or_create_collection() -> chromadb.Collection:
    """Get or create schema catalog collection."""
    client = get_chroma_client()
    
    try:
        collection = client.get_collection(name=_collection_name)
    except Exception:
        collection = client.create_collection(
            name=_collection_name,
            metadata={"description": "MongoDB collection schemas for semantic search"}
        )
    
    return collection


def embed_collections_text(collections_data: list[dict]) -> list[list[float]]:
    """Create embeddings for collection data."""
    model = get_embedding_model()
    
    # Create searchable text for each collection
    texts = []
    for coll in collections_data:
        fields = list(coll.get("fields", {}).keys())
        text = f"{coll['collection_name']}: {', '.join(fields)}. {coll.get('document_count', 0)} documents."
        texts.append(text)
    
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


async def rebuild_schema_embeddings(collections_data: list[dict]) -> dict:
    """
    Rebuild embeddings for all collections.
    Call this when schema is refreshed.
    """
    print("[SchemaEmbeddings] Rebuilding schema embeddings...")
    
    collection = get_or_create_collection()
    
    # Clear existing data
    try:
        collection.delete(delete_all=True)
    except Exception:
        pass
    
    if not collections_data:
        return {"status": "error", "message": "No collections data"}
    
    # Create embeddings
    embeddings = embed_collections_text(collections_data)
    
    # Add to ChromaDB
    ids = []
    documents = []
    metadatas = []
    
    for i, coll in enumerate(collections_data):
        coll_id = coll.get("collection_name", f"collection_{i}")
        fields = list(coll.get("fields", {}).keys())
        
        # Create searchable document
        doc = f"Collection: {coll_id}. Fields: {', '.join(fields)}. Count: {coll.get('document_count', 0)}."
        
        ids.append(coll_id)
        documents.append(doc)
        metadatas.append({
            "collection_name": coll_id,
            "document_count": coll.get("document_count", 0),
            "fields": ",".join(fields[:10]),  # First 10 fields
        })
    
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings
    )
    
    print(f"[SchemaEmbeddings] Added {len(ids)} collections to semantic index")
    
    return {
        "status": "success",
        "collections": len(ids),
        "timestamp": datetime.now().isoformat()
    }


def search_collections(query: str, n_results: int = 5) -> list[dict]:
    """
    Semantic search for collections based on query.
    Use this to find relevant collections for a user query.
    
    Example:
        search_collections("student grades") -> ["grades", "semester_results"]
        search_collections("fee payment") -> ["fees", "challans"]
    """
    model = get_embedding_model()
    collection = get_or_create_collection()
    
    # Embed query
    query_embedding = model.encode([query], show_progress_bar=False).tolist()[0]
    
    # Search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    if not results["ids"] or not results["ids"][0]:
        return []
    
    output = []
    for i, coll_id in enumerate(results["ids"][0]):
        output.append({
            "collection": coll_id,
            "distance": results["distances"][0][i] if results.get("distances") else 0,
            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {}
        })
    
    return output


class SchemaEmbedder:
    """Schema embedder with refresh support."""
    
    def __init__(self):
        self.initialized = False
    
    async def initialize(self, schema_catalog) -> None:
        """Initialize with schema catalog."""
        if self.initialized:
            return
        
        collections_data = []
        for coll_name, info in schema_catalog.catalog.items():
            collections_data.append({
                "collection_name": coll_name,
                "document_count": info.get("document_count", 0),
                "fields": info.get("fields", {}),
            })
        
        await rebuild_schema_embeddings(collections_data)
        self.initialized = True
        print("[SchemaEmbedder] Initialized")
    
    async def refresh(self, schema_catalog) -> dict:
        """Refresh embeddings when schema is updated."""
        collections_data = []
        for coll_name, info in schema_catalog.catalog.items():
            collections_data.append({
                "collection_name": coll_name,
                "document_count": info.get("document_count", 0),
                "fields": info.get("fields", {}),
            })
        
        return await rebuild_schema_embeddings(collections_data)
    
    def find_collections(self, query: str, n_results: int = 3) -> list[str]:
        """Find relevant collection names for a query."""
        results = search_collections(query, n_results)
        return [r["collection"] for r in results]


# Global instance
schema_embedder = SchemaEmbedder()


async def initialize_schema_embeddings(schema_catalog) -> SchemaEmbedder:
    """Initialize schema embeddings at startup."""
    await schema_embedder.initialize(schema_catalog)
    return schema_embedder