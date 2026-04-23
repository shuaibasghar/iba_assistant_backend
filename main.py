from fastapi import FastAPI
from contextlib import asynccontextmanager
from utils.db import mongodb_connector
from config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    settings = get_settings()
    
    # Startup: Connect to MongoDB
    await mongodb_connector.connect(settings.mongodb_url, settings.mongodb_database)
    
    yield
    
    # Shutdown: Disconnect from MongoDB
    await mongodb_connector.disconnect()


app = FastAPI(
    title="University Data Analysis API",
    description="AI-powered chatbot for university student queries",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {"message": "University Data Analysis API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}


@app.get("/schema")
async def get_database_schema():
    """Discover and return the complete database schema."""
    schema = await mongodb_connector.discover_full_schema()
    return schema


@app.get("/collections")
async def list_collections():
    """List all collections in the database."""
    collections = await mongodb_connector.list_collections()
    return {"collections": collections, "count": len(collections)}


@app.get("/collections/{collection_name}")
async def get_collection_info(collection_name: str):
    """Get schema information for a specific collection."""
    schema = await mongodb_connector.get_collection_schema(collection_name)
    return schema


@app.get("/collections/{collection_name}/records")
async def get_collection_records(
    collection_name: str, 
    limit: int = 10, 
    skip: int = 0
):
    """Fetch records from a specific collection."""
    records = await mongodb_connector.fetch_records(
        collection_name, 
        limit=limit, 
        skip=skip
    )
    return {"collection": collection_name, "records": records, "count": len(records)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
