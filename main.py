from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from utils.db import mongodb_connector
from config import get_settings
from routers.chat import router as chat_router


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
    title="IBA Sukkur University Portal API",
    description="""
    AI-powered chatbot for university student queries.
    
    ## Features
    - Multi-agent system powered by CrewAI
    - Conversation memory with LangChain
    - Session management with Redis
    - Semantic search with ChromaDB
    
    ## Supported Queries
    - Assignment status, due dates, submissions
    - Fee status, payment history
    - Exam schedules, venues
    - Academic grades, CGPA
    - Document requests
    
    ## Languages
    Supports English and Roman Urdu (e.g., "meri fees ka status batao")
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router)


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
