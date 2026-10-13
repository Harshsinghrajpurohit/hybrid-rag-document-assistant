"""
Pydantic request/response models for Phase 5 API.

Design principles:
1. UUID for document identification (stable, unique, not collision-prone)
2. Stateless API - client manages conversation history
3. Structured error responses with request_id for all failures
4. No fabricated values - only measured/actual data in responses
5. All timestamps in ISO 8601 UTC format with 'Z' suffix
6. Complete metadata tracking: upload_time, file_size, chunk_count
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


# ============================================================================
# INTERNAL MODELS (used for data transfer, not exposed via API)
# ============================================================================

class DocumentMetadata(BaseModel):
    """
    Internal metadata for document tracking.
    Stored in ChromaDB as special "META:{doc_id}" entries.

    Purpose: Map UUID → filename and track upload details for deletion,
    listing, and consistency verification.
    """
    doc_id: str = Field(
        ...,
        description="UUID uniquely identifying this document upload"
    )
    file_name: str = Field(
        ...,
        description="Original filename (e.g., 'research_paper.pdf')"
    )
    upload_time: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when document was uploaded"
    )
    size_bytes: int = Field(
        ...,
        ge=1,
        description="Actual size of uploaded PDF file in bytes"
    )
    num_chunks: int = Field(
        ...,
        ge=1,
        description="Number of text chunks created from this document"
    )
    chromadb_chunk_ids: List[str] = Field(
        default_factory=list,
        description="List of ChromaDB IDs for chunks (for efficient deletion)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_name": "ai_fundamentals.pdf",
                "upload_time": "2026-10-13T09:30:00Z",
                "size_bytes": 2097152,
                "num_chunks": 42,
                "chromadb_chunk_ids": [
                    "ai_fundamentals.pdf_1_0",
                    "ai_fundamentals.pdf_1_1",
                    "ai_fundamentals.pdf_2_0"
                ]
            }
        }


class APIError(BaseModel):
    """
    Internal error details (for exception handling).
    Not directly exposed to users; mapped to ErrorResponse.
    """
    error_type: str  # e.g., "FILE_TOO_LARGE", "DOCUMENT_NOT_FOUND"
    detail: str  # Human-readable message (safe to show to user)
    status_code: int  # HTTP status code (400, 404, 413, etc.)
    request_id: Optional[str] = None  # Generated if not provided


# ============================================================================
# REQUEST MODELS
# ============================================================================

class QueryRequest(BaseModel):
    """
    User question submission for RAG answer generation.

    Fields:
    - query: The actual question/search text
    - conversation_id: Optional client-side conversation tracking (stateless API)
    - max_sources: How many chunks to use as context for LLM

    Design note: conversation_id is purely for client state tracking.
    Server doesn't store conversation history; client manages it.
    """
    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User question or search query (1-5000 characters)"
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Optional conversation ID for client-side history tracking. "
                    "Server echoes back; stateless API - no server-side history storage."
    )
    max_sources: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum number of source passages to use as LLM context (1-20). "
                    "More sources = more context but more tokens used."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the key principles of machine learning?",
                "conversation_id": "conv_550e8400-e29b-41d4",
                "max_sources": 5
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class Source(BaseModel):
    """
    Single source passage cited in answer.

    Includes:
    - Location (page, file)
    - Content (first 150 chars)
    - Relevance score (RRF fusion score from retriever)
    """
    page: int = Field(
        ...,
        ge=1,
        description="Page number in original document (1-indexed)"
    )
    file: str = Field(
        ...,
        description="Original filename (e.g., 'document.pdf')"
    )
    excerpt: str = Field(
        ...,
        max_length=200,
        description="First 150 characters of passage (or full text if shorter). "
                    "Truncated with '...' if needed."
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="RRF fusion score from retriever (0.0 = not relevant, 1.0 = perfect). "
                    "Based on both keyword (BM25) and semantic (dense) matching."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "page": 1,
                "file": "ai_guide.pdf",
                "excerpt": "Machine learning is a subset of artificial intelligence "
                          "that enables computers to learn from data...",
                "score": 0.0324
            }
        }


class QueryResponse(BaseModel):
    """
    Response to user query: answer with source citations.

    Contains:
    - Generated answer grounded in retrieved passages
    - Source citations (page, file, excerpt, relevance score)
    - Token count (actual LLM usage)
    - Conversation ID echo-back (for client state tracking)
    - Timestamp (when answer was generated)

    Design note: No confidence field (per user requirement: measured data only).
    tokens_used is the actual value from Ollama API, not estimated.
    """
    answer: str = Field(
        ...,
        description="Generated answer grounded in retrieved passages. "
                    "LLM instructed to answer only from provided sources."
    )
    sources: List[Source] = Field(
        default_factory=list,
        description="Passages used as context for answer generation. "
                    "Empty list if no relevant passages found."
    )
    tokens_used: int = Field(
        ...,
        ge=0,
        description="Actual token count used in LLM call. "
                    "Sum of prompt_eval_count + eval_count from Ollama API. "
                    "Measured value, not estimated."
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Echo of input conversation_id (or None if not provided). "
                    "Client uses this to track conversation history."
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when answer was generated. "
                    "Format: '2026-10-13T09:42:07Z'"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Machine learning is a subset of artificial intelligence that "
                         "enables systems to learn from data without being explicitly programmed. "
                         "It focuses on developing algorithms that can identify patterns and make predictions.",
                "sources": [
                    {
                        "page": 1,
                        "file": "ai_guide.pdf",
                        "excerpt": "Machine learning is a subset of AI that enables computers...",
                        "score": 0.0324
                    },
                    {
                        "page": 3,
                        "file": "ai_guide.pdf",
                        "excerpt": "Algorithms learn patterns from training data to make predictions...",
                        "score": 0.0265
                    }
                ],
                "tokens_used": 145,
                "conversation_id": "conv_550e8400-e29b-41d4",
                "timestamp": "2026-10-13T09:42:07Z"
            }
        }


class Document(BaseModel):
    """
    Document metadata for listing/display.

    Contains:
    - doc_id: UUID (stable identifier for deletion)
    - file_name: Original filename
    - num_chunks: Number of text chunks
    - upload_time: When uploaded
    - size_bytes: Actual file size (never 0)
    """
    doc_id: str = Field(
        ...,
        description="UUID uniquely identifying this document. "
                    "Use this for deletion: DELETE /documents/{doc_id}"
    )
    file_name: str = Field(
        ...,
        description="Original filename (e.g., 'research_paper.pdf')"
    )
    num_chunks: int = Field(
        ...,
        ge=1,
        description="Number of text chunks created from this document"
    )
    upload_time: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when document was uploaded"
    )
    size_bytes: int = Field(
        ...,
        ge=1,
        description="Actual size of uploaded PDF file in bytes. "
                    "Never 0 - always the real file size."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_name": "ai_fundamentals.pdf",
                "num_chunks": 42,
                "upload_time": "2026-10-13T09:30:00Z",
                "size_bytes": 2097152
            }
        }


class DocumentListResponse(BaseModel):
    """
    Response listing all uploaded documents.

    Includes:
    - documents: List of document metadata
    - total_documents: Count of documents
    - total_chunks: Sum of chunks across all documents

    All metadata is accurate (no placeholders).
    """
    documents: List[Document] = Field(
        default_factory=list,
        description="List of uploaded documents with complete metadata"
    )
    total_documents: int = Field(
        ...,
        ge=0,
        description="Total number of documents in system"
    )
    total_chunks: int = Field(
        ...,
        ge=0,
        description="Total number of chunks across all documents. "
                    "Sum of num_chunks for each document."
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
                        "size_bytes": 2097152
                    },
                    {
                        "doc_id": "660e8400-e29b-41d4-a716-446655440001",
                        "file_name": "ml_basics.pdf",
                        "num_chunks": 28,
                        "upload_time": "2026-10-13T09:15:00Z",
                        "size_bytes": 1048576
                    }
                ],
                "total_documents": 2,
                "total_chunks": 70
            }
        }


class DocumentResponse(BaseModel):
    """
    Response when uploading a document successfully.

    Contains:
    - doc_id: UUID assigned by server (for future deletion)
    - file_name: Echo of input filename
    - num_chunks: Chunks created
    - upload_time: Server timestamp of upload
    - size_bytes: Actual file size processed
    """
    doc_id: str = Field(
        ...,
        description="UUID assigned to this document by server. "
                    "Use for future operations (e.g., deletion)."
    )
    file_name: str = Field(
        ...,
        description="Original filename (echo of upload)"
    )
    num_chunks: int = Field(
        ...,
        ge=1,
        description="Number of text chunks created from this document"
    )
    upload_time: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when upload completed"
    )
    size_bytes: int = Field(
        ...,
        ge=1,
        description="Actual size of uploaded PDF in bytes"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_name": "research_paper.pdf",
                "num_chunks": 42,
                "upload_time": "2026-10-13T09:42:07Z",
                "size_bytes": 2097152
            }
        }


class DeleteResponse(BaseModel):
    """
    Response when deleting a document successfully.

    Contains:
    - doc_id: UUID of deleted document (confirmation)
    - file_name: Filename that was deleted
    - chunks_deleted: Number of chunks removed from indexes
    - timestamp: When deletion completed
    """
    doc_id: str = Field(
        ...,
        description="UUID of document that was deleted"
    )
    file_name: str = Field(
        ...,
        description="Filename of deleted document"
    )
    chunks_deleted: int = Field(
        ...,
        ge=0,
        description="Number of chunks removed from ChromaDB and BM25 indexes"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when deletion completed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_name": "old_document.pdf",
                "chunks_deleted": 42,
                "timestamp": "2026-10-13T09:42:07Z"
            }
        }


# ============================================================================
# ERROR RESPONSE MODEL
# ============================================================================

class ErrorResponse(BaseModel):
    """
    Structured error response for all API failures.

    Contains:
    - error: Brief error type/code (e.g., 'FILE_TOO_LARGE')
    - detail: Human-readable message (safe for users, no stack traces)
    - request_id: UUID for correlating with server logs
    - timestamp: When error occurred

    Design principles:
    1. Never expose stack traces or internal implementation details
    2. Always include request_id for debugging
    3. Use safe, user-friendly messages
    4. Consistent format for all errors

    Error types and HTTP status codes:
    - FILE_TOO_LARGE (413): Uploaded file exceeds 50 MB
    - INVALID_MIME_TYPE (400): File is not a PDF
    - PDF_CORRUPTED (422): PDF parsing failed
    - DOCUMENT_NOT_FOUND (404): UUID doesn't exist
    - OLLAMA_UNAVAILABLE (503): LLM service down
    - INTERNAL_SERVER_ERROR (500): Unexpected error
    - INVALID_REQUEST (400): Missing/invalid fields
    """
    error: str = Field(
        ...,
        description="Error type/code for programmatic handling. "
                    "Examples: FILE_TOO_LARGE, DOCUMENT_NOT_FOUND, OLLAMA_UNAVAILABLE"
    )
    detail: str = Field(
        ...,
        description="Human-readable error message safe for end users. "
                    "No stack traces or internal details. "
                    "Example: 'File exceeds 50 MB limit (provided: 75 MB)'"
    )
    request_id: str = Field(
        ...,
        description="UUID generated for this request. "
                    "Include in bug reports to help developers correlate with server logs."
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when error occurred. "
                    "Format: '2026-10-13T09:42:07Z'"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "FILE_TOO_LARGE",
                "detail": "Uploaded file exceeds 50 MB limit (provided: 75 MB)",
                "request_id": "550e8400-e29b-41d4-a716-446655440001",
                "timestamp": "2026-10-13T09:42:07Z"
            }
        }


# ============================================================================
# HELPER FUNCTIONS (not Pydantic models, used internally)
# ============================================================================

def generate_request_id() -> str:
    """Generate a UUID for request tracking."""
    return str(uuid.uuid4())


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


# ============================================================================
# ERROR TYPE TO STATUS CODE MAPPING
# ============================================================================

ERROR_STATUS_CODES = {
    "FILE_TOO_LARGE": 413,
    "INVALID_MIME_TYPE": 400,
    "PDF_CORRUPTED": 422,
    "DOCUMENT_NOT_FOUND": 404,
    "OLLAMA_UNAVAILABLE": 503,
    "INTERNAL_SERVER_ERROR": 500,
    "INVALID_REQUEST": 400,
}
