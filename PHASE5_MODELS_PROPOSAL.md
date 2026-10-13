"""
Pydantic request/response models for Phase 5 API.
All models use UUID for document identification and structured error responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


# ============================================================================
# REQUEST MODELS
# ============================================================================

class QueryRequest(BaseModel):
    """User question submission."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User question or search query"
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Optional conversation ID for client-side history tracking (stateless API)"
    )
    max_sources: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum number of source passages to include in context (1-20)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is machine learning?",
                "conversation_id": "conv_abc123",
                "max_sources": 5
            }
        }


class DocumentUploadRequest(BaseModel):
    """Metadata for uploaded document (file itself sent as multipart)."""
    # Note: file_path/file content handled by FastAPI FileUpload
    # This model is for request body validation if needed
    pass


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class Source(BaseModel):
    """Single source passage cited in answer."""
    page: int = Field(..., description="Page number in original document")
    file: str = Field(..., description="Original filename (e.g., 'document.pdf')")
    excerpt: str = Field(
        ...,
        max_length=200,
        description="First 150 chars of passage with '...' if truncated"
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="RRF fusion score (0.0 = not relevant, 1.0 = perfect match)"
    )


class QueryResponse(BaseModel):
    """Answer to user question with source citations."""
    answer: str = Field(
        ...,
        description="Generated answer grounded in retrieved passages"
    )
    sources: List[Source] = Field(
        default_factory=list,
        description="Passages used as context for answer generation"
    )
    tokens_used: int = Field(
        ...,
        ge=0,
        description="Actual token count used in LLM call (prompt + completion)"
    )
    conversation_id: str = Field(
        ...,
        description="Echo back of input conversation_id (or None if not provided)"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp when answer was generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Machine learning is a subset of artificial intelligence...",
                "sources": [
                    {
                        "page": 1,
                        "file": "ai_guide.pdf",
                        "excerpt": "Machine learning is a subset of AI...",
                        "score": 0.0324
                    }
                ],
                "tokens_used": 145,
                "conversation_id": "conv_abc123",
                "timestamp": "2026-10-13T09:32:03Z"
            }
        }


class Document(BaseModel):
    """Metadata for an uploaded document."""
    doc_id: str = Field(
        ...,
        description="UUID uniquely identifying this uploaded document"
    )
    file_name: str = Field(
        ...,
        description="Original filename (e.g., 'document.pdf')"
    )
    num_chunks: int = Field(
        ...,
        ge=1,
        description="Number of text chunks created from this document"
    )
    upload_time: str = Field(
        ...,
        description="ISO 8601 timestamp when document was uploaded"
    )
    size_bytes: int = Field(
        ...,
        ge=1,
        description="Size of uploaded PDF file in bytes"
    )


class DocumentListResponse(BaseModel):
    """List of all uploaded documents."""
    documents: List[Document] = Field(
        default_factory=list,
        description="List of document metadata"
    )
    total_documents: int = Field(
        ...,
        ge=0,
        description="Total number of documents in system"
    )
    total_chunks: int = Field(
        ...,
        ge=0,
        description="Total number of chunks across all documents"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "documents": [
                    {
                        "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_name": "ai_guide.pdf",
                        "num_chunks": 42,
                        "upload_time": "2026-10-13T09:00:00Z",
                        "size_bytes": 1048576
                    }
                ],
                "total_documents": 1,
                "total_chunks": 42
            }
        }


class DocumentResponse(BaseModel):
    """Response when uploading a document."""
    doc_id: str = Field(
        ...,
        description="UUID assigned to this document"
    )
    file_name: str = Field(...)
    num_chunks: int = Field(...)
    upload_time: str = Field(...)
    size_bytes: int = Field(...)


class DeleteResponse(BaseModel):
    """Response when deleting a document."""
    doc_id: str = Field(
        ...,
        description="UUID of deleted document"
    )
    file_name: str = Field(...)
    chunks_deleted: int = Field(
        ...,
        description="Number of chunks removed from indexes"
    )
    timestamp: str = Field(...)


# ============================================================================
# ERROR RESPONSE MODEL
# ============================================================================

class ErrorResponse(BaseModel):
    """Structured error response."""
    error: str = Field(
        ...,
        description="Brief error type (e.g., 'FILE_TOO_LARGE', 'PDF_CORRUPTED', 'OLLAMA_UNAVAILABLE')"
    )
    detail: str = Field(
        ...,
        description="Detailed human-readable error message (safe for users)"
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique ID for correlating server logs with this error"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO 8601 timestamp when error occurred"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "FILE_TOO_LARGE",
                "detail": "Uploaded file exceeds 50 MB limit (provided: 75 MB)",
                "request_id": "550e8400-e29b-41d4-a716-446655440001",
                "timestamp": "2026-10-13T09:32:03Z"
            }
        }


# ============================================================================
# INTERNAL MODELS (not exposed via API, used for data transfer)
# ============================================================================

class DocumentMetadata(BaseModel):
    """Internal metadata tracking for uploaded documents."""
    doc_id: str  # UUID
    file_name: str
    upload_time: str  # ISO 8601
    size_bytes: int
    num_chunks: int
    chromadb_ids: List[str]  # IDs of chunks in ChromaDB (for deletion)

