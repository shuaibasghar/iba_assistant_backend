"""
Schema Catalog - Auto-discovers MongoDB schemas at startup for SaaS multi-tenant architecture.
Dynamically scans all collections and extracts field schemas.
Supports refresh without app restart in production.
"""

import asyncio
from typing import Any
from datetime import datetime, timedelta
from utils.db import mongodb_connector


class SchemaCatalog:
    """Auto-discovers MongoDB schemas at startup with refresh support."""
    
    def __init__(self):
        self.catalog: dict[str, dict] = {}
        self.initialized: bool = False
        self.last_refresh: datetime | None = None
        self._refresh_task: asyncio.Task | None = None
    
    async def initialize(self) -> None:
        """Scan all collections and build schema catalog."""
        if self.initialized:
            return
        
        print("[SchemaCatalog] Starting schema discovery...")
        
        collections = await mongodb_connector.list_collections()
        print(f"[SchemaCatalog] Found {len(collections)} collections")
        
        for coll_name in collections:
            try:
                schema = await mongodb_connector.get_collection_schema(coll_name)
                self.catalog[coll_name] = {
                    "collection_name": coll_name,
                    "document_count": schema.get("total_documents", 0),
                    "fields": schema.get("fields", {}),
                }
                print(f"[SchemaCatalog] {coll_name}: {len(schema.get('fields', {}))} fields")
            except Exception as e:
                print(f"[SchemaCatalog] Error scanning {coll_name}: {e}")
        
        self.initialized = True
        self.last_refresh = datetime.now()
        print(f"[SchemaCatalog] Initialized with {len(self.catalog)} collections")
    
    async def refresh(self, force: bool = False) -> dict:
        """Refresh schema catalog. Optional: force refresh even if recently updated."""
        
        # Check if refresh needed
        if not force and self.last_refresh:
            time_since_refresh = datetime.now() - self.last_refresh
            if time_since_refresh < timedelta(minutes=5):
                return {
                    "status": "skipped",
                    "message": f"Recently refreshed ({time_since_refresh.total_seconds():.0f}s ago)",
                    "collections": len(self.catalog)
                }
        
        print("[SchemaCatalog] Refreshing schema catalog...")
        
        new_collections = await mongodb_connector.list_collections()
        added = 0
        updated = 0
        
        for coll_name in new_collections:
            try:
                schema = await mongodb_connector.get_collection_schema(coll_name)
                is_new = coll_name not in self.catalog
                self.catalog[coll_name] = {
                    "collection_name": coll_name,
                    "document_count": schema.get("total_documents", 0),
                    "fields": schema.get("fields", {}),
                }
                if is_new:
                    added += 1
                    print(f"[SchemaCatalog] NEW: {coll_name}")
                else:
                    updated += 1
            except Exception as e:
                print(f"[SchemaCatalog] Error refreshing {coll_name}: {e}")
        
        self.last_refresh = datetime.now()
        
        result = {
            "status": "success",
            "collections": len(self.catalog),
            "added": added,
            "updated": updated,
            "timestamp": self.last_refresh.isoformat()
        }
        print(f"[SchemaCatalog] Refresh complete: {added} new, {updated} updated")
        
        return result
    
    async def check_and_refresh(self) -> None:
        """Lazy refresh - check if collection exists before query."""
        if not self.initialized:
            await self.initialize()
    
    def start_background_refresh(self, interval_minutes: int = 30) -> None:
        """Start background refresh task (for production)."""
        if self._refresh_task and not self._refresh_task.done():
            return
        
        async def periodic_refresh():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                try:
                    await self.refresh()
                except Exception as e:
                    print(f"[SchemaCatalog] Background refresh error: {e}")
        
        self._refresh_task = asyncio.create_task(periodic_refresh())
        print(f"[SchemaCatalog] Background refresh enabled every {interval_minutes} minutes")
    
    def stop_background_refresh(self) -> None:
        """Stop background refresh."""
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
            print("[SchemaCatalog] Background refresh stopped")
    
    def get_catalog_for_llm(self) -> str:
        """Format catalog for LLM system prompt."""
        lines = ["Available Database Collections:\n"]
        for coll_name, info in self.catalog.items():
            field_list = ", ".join(list(info["fields"].keys())[:10])
            doc_count = info.get("document_count", 0)
            lines.append(f"- {coll_name} ({doc_count} docs): {field_list}")
        return "\n".join(lines)
    
    def get_collection_fields(self, collection: str) -> dict[str, str]:
        """Get fields for a specific collection."""
        return self.catalog.get(collection, {}).get("fields", {})
    
    def get_all_collections(self) -> list[str]:
        """Get list of all collection names."""
        return list(self.catalog.keys())


schema_catalog = SchemaCatalog()


async def initialize_schema_catalog() -> SchemaCatalog:
    """Initialize schema catalog at app startup."""
    await schema_catalog.initialize()
    return schema_catalog