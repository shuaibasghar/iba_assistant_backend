"""
Vector Store with ChromaDB
===========================
Semantic search capabilities for university data.

Use cases:
- Find assignments by topic/description
- Search courses by content
- Find relevant documents
"""

import os
from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import get_settings
from pymongo import MongoClient


class VectorStoreManager:
    """
    Manages ChromaDB vector store for semantic search.
    
    Collections:
    - courses: Course descriptions and content
    - assignments: Assignment titles and descriptions
    - documents: Any documents that need semantic search
    
    Usage:
        manager = VectorStoreManager()
        
        # Index data
        manager.index_courses()
        
        # Search
        results = manager.search_courses("machine learning")
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Set API key
        os.environ["OPENAI_API_KEY"] = self.settings.openai_api_key
        
        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small"
        )
        
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(
            path=self.settings.chroma_persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False
            )
        )
        
        # MongoDB for fetching data
        self.mongo_client = MongoClient(self.settings.mongodb_url)
        self.db = self.mongo_client[self.settings.mongodb_database]
        
        # LangChain Chroma wrapper
        self._vector_stores = {}
    
    def _get_vector_store(self, collection_name: str) -> Chroma:
        """Get or create a vector store for a collection."""
        if collection_name not in self._vector_stores:
            self._vector_stores[collection_name] = Chroma(
                client=self.chroma_client,
                collection_name=collection_name,
                embedding_function=self.embeddings,
            )
        return self._vector_stores[collection_name]
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Indexing Functions
    # ═══════════════════════════════════════════════════════════════════════════
    
    def index_courses(self) -> int:
        """Index all courses for semantic search."""
        courses = list(self.db["courses"].find())
        
        if not courses:
            return 0
        
        documents = []
        for course in courses:
            doc = Document(
                page_content=f"{course.get('course_name', '')}. {course.get('course_code', '')}. Semester {course.get('semester', '')}. {course.get('department', '')} department. {course.get('credit_hours', '')} credit hours.",
                metadata={
                    "course_id": str(course["_id"]),
                    "course_code": course.get("course_code", ""),
                    "course_name": course.get("course_name", ""),
                    "semester": course.get("semester", 0),
                    "department": course.get("department", ""),
                    "type": "course"
                }
            )
            documents.append(doc)
        
        vector_store = self._get_vector_store("courses")
        vector_store.add_documents(documents)
        
        return len(documents)
    
    def index_assignments(self) -> int:
        """Index all assignments for semantic search."""
        assignments = list(self.db["assignments"].find())
        
        if not assignments:
            return 0
        
        # Get course info for context
        courses = {str(c["_id"]): c for c in self.db["courses"].find()}
        
        documents = []
        for assignment in assignments:
            course = courses.get(str(assignment.get("course_id", "")), {})
            
            doc = Document(
                page_content=f"{assignment.get('title', '')}. {assignment.get('description', '')}. Course: {course.get('course_name', '')} ({assignment.get('course_code', '')}).",
                metadata={
                    "assignment_id": str(assignment["_id"]),
                    "title": assignment.get("title", ""),
                    "course_code": assignment.get("course_code", ""),
                    "course_name": course.get("course_name", ""),
                    "total_marks": assignment.get("total_marks", 0),
                    "type": "assignment"
                }
            )
            documents.append(doc)
        
        vector_store = self._get_vector_store("assignments")
        vector_store.add_documents(documents)
        
        return len(documents)
    
    def index_all(self) -> dict:
        """Index all data for semantic search."""
        return {
            "courses_indexed": self.index_courses(),
            "assignments_indexed": self.index_assignments(),
        }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Search Functions
    # ═══════════════════════════════════════════════════════════════════════════
    
    def search_courses(
        self, 
        query: str, 
        k: int = 5,
        semester: int = None,
        department: str = None
    ) -> List[dict]:
        """
        Semantic search over courses.
        
        Args:
            query: Search query (e.g., "machine learning", "database")
            k: Number of results
            semester: Filter by semester
            department: Filter by department
        
        Returns:
            List of matching courses with scores
        """
        vector_store = self._get_vector_store("courses")
        
        # Build filter
        filter_dict = {"type": "course"}
        if semester:
            filter_dict["semester"] = semester
        if department:
            filter_dict["department"] = department
        
        results = vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=filter_dict if len(filter_dict) > 1 else None
        )
        
        return [
            {
                "course_code": doc.metadata.get("course_code"),
                "course_name": doc.metadata.get("course_name"),
                "semester": doc.metadata.get("semester"),
                "department": doc.metadata.get("department"),
                "relevance_score": 1 - score,  # Convert distance to similarity
            }
            for doc, score in results
        ]
    
    def search_assignments(
        self,
        query: str,
        k: int = 5,
        course_code: str = None
    ) -> List[dict]:
        """
        Semantic search over assignments.
        
        Args:
            query: Search query (e.g., "NLP preprocessing", "database design")
            k: Number of results
            course_code: Filter by course
        
        Returns:
            List of matching assignments with scores
        """
        vector_store = self._get_vector_store("assignments")
        
        # Build filter
        filter_dict = {"type": "assignment"}
        if course_code:
            filter_dict["course_code"] = course_code
        
        results = vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=filter_dict if len(filter_dict) > 1 else None
        )
        
        return [
            {
                "assignment_id": doc.metadata.get("assignment_id"),
                "title": doc.metadata.get("title"),
                "course_code": doc.metadata.get("course_code"),
                "course_name": doc.metadata.get("course_name"),
                "total_marks": doc.metadata.get("total_marks"),
                "relevance_score": 1 - score,
            }
            for doc, score in results
        ]
    
    def semantic_search(
        self,
        query: str,
        collection: str = "courses",
        k: int = 5
    ) -> List[dict]:
        """
        General semantic search.
        
        Args:
            query: Search query
            collection: Which collection to search ("courses" or "assignments")
            k: Number of results
        """
        if collection == "courses":
            return self.search_courses(query, k)
        elif collection == "assignments":
            return self.search_assignments(query, k)
        else:
            raise ValueError(f"Unknown collection: {collection}")
    
    def clear_collection(self, collection_name: str) -> None:
        """Clear a vector collection (for re-indexing)."""
        try:
            self.chroma_client.delete_collection(collection_name)
            if collection_name in self._vector_stores:
                del self._vector_stores[collection_name]
        except Exception:
            pass
    
    def clear_all(self) -> None:
        """Clear all vector collections."""
        for name in ["courses", "assignments"]:
            self.clear_collection(name)


# Singleton instance
_vector_store_manager: Optional[VectorStoreManager] = None


def get_vector_store_manager() -> VectorStoreManager:
    """Get singleton VectorStoreManager instance."""
    global _vector_store_manager
    if _vector_store_manager is None:
        _vector_store_manager = VectorStoreManager()
    return _vector_store_manager
