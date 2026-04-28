"""
System Router - Schema refresh and system utilities.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from services.schema_catalog import schema_catalog
from services.schema_embeddings import schema_embedder

router = APIRouter(prefix="/system", tags=["system"])


class RefreshResponse(BaseModel):
    status: str
    collections: int
    added: int = 0
    updated: int = 0
    message: str = ""


@router.post("/schema/refresh")
async def refresh_schema(force: bool = False, rebuild_embeddings: bool = True) -> RefreshResponse:
    """
    Refresh schema catalog and rebuild embeddings.
    Use force=true to refresh even if recently updated.
    
    Endpoints:
    - POST /system/schema/refresh - Normal refresh + embeddings rebuild
    - POST /system/schema/refresh?force=true - Force refresh
    - POST /system/schema/refresh?rebuild_embeddings=false - Skip embeddings
    """
    result = await schema_catalog.refresh(force=force)
    
    if rebuild_embeddings and result.get("status") == "success":
        # Rebuild embeddings with new schema
        from services.schema_embeddings import schema_embedder
        await schema_embedder.refresh(schema_catalog)
    
    return RefreshResponse(**result)


@router.get("/schema/status")
async def get_schema_status() -> dict:
    """Get schema catalog status."""
    return {
        "initialized": schema_catalog.initialized,
        "collections": len(schema_catalog.catalog),
        "last_refresh": schema_catalog.last_refresh.isoformat() if schema_catalog.last_refresh else None,
        "collections_list": schema_catalog.get_all_collections()
    }


@router.get("/schema/{collection}")
async def get_collection_schema(collection: str) -> dict:
    """Get schema for a specific collection."""
    fields = schema_catalog.get_collection_fields(collection)
    if not fields:
        return {"error": f"Collection '{collection}' not found", "available": schema_catalog.get_all_collections()}
    return {
        "collection": collection,
        "fields": fields
    }


@router.get("/schema/search/{query}")
async def search_schema(query: str, n_results: int = 3) -> dict:
    """
    Semantic search for collections using embeddings.
    Example: /system/schema/search/grades -> ["grades", "semester_results"]
    """
    results = schema_embedder.find_collections(query, n_results)
    return {
        "query": query,
        "results": results
    }