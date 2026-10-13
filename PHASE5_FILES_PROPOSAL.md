================================================================================
PHASE 5: AFFECTED FILES & REQUIRED CHANGES
================================================================================

DATE: 2026-10-13T09:32:18Z
STATUS: Design review - NO EDITS YET

================================================================================
SUMMARY OF CHANGES
================================================================================

FILES TO CREATE (NEW):
1. backend/app/models.py (NEW) - 250 lines
   - All Pydantic request/response models
   - See PHASE5_MODELS_PROPOSAL.md for content

2. backend/app/main.py (NEW) - ~100 lines
   - FastAPI app initialization
   - Service instantiation
   - Router mounting
   - Error handler registration
   - CORS middleware

3. backend/app/api/__init__.py (NEW) - empty file

4. backend/app/api/chat.py (NEW) - ~120 lines
   - POST /chat/query
   - GET /chat/conversations (MVP)
   - DELETE /chat/conversations/{conv_id} (MVP)

5. backend/app/api/documents.py (NEW) - ~180 lines
   - POST /documents/upload (multipart form)
   - GET /documents/list
   - DELETE /documents/{doc_id}

6. tests/test_api.py (NEW) - ~400 lines
   - Tests for all endpoints
   - Error path testing
   - File upload validation

FILES TO MODIFY (EXTENSIONS):
1. backend/app/services/chroma_service.py (MODIFY)
   - Add method: delete_by_file_name(file_name: str) -> List[str]
   - Add method: get_unique_documents() -> List[Dict]
   - See details below

2. backend/app/services/hybrid_retriever.py (MODIFY)
   - Add method: delete_document(file_name: str) -> bool
   - See details below

3. tests/test_api.py (already listed as NEW)

================================================================================
PROPOSED MODIFICATIONS TO EXISTING FILES
================================================================================

### FILE 1: backend/app/services/chroma_service.py

ADD THESE METHODS (after existing delete_all method):

```python
def delete_by_file_name(self, file_name: str) -> List[str]:
    """
    Delete all chunks for a specific document.
    
    Args:
        file_name: Name of file to delete (e.g., "document.pdf")
    
    Returns:
        List of deleted document IDs from ChromaDB
    
    Raises:
        ValueError: If file_name not found in collection
    """
    # Query for all chunks with this file_name
    results = self.collection.get(
        where={"file_name": {"$eq": file_name}},
        include=[]
    )
    
    deleted_ids = results.get("ids", [])
    if not deleted_ids:
        raise ValueError(f"No documents found with file_name: {file_name}")
    
    # Delete from ChromaDB
    self.collection.delete(ids=deleted_ids)
    logger.info(f"Deleted {len(deleted_ids)} chunks for {file_name}")
    
    return deleted_ids


def get_unique_documents(self) -> List[Dict[str, Any]]:
    """
    Get list of unique documents in collection with metadata.
    
    Returns:
        List of dicts with keys: "file_name", "num_chunks", "pages"
        Example: [
            {"file_name": "doc.pdf", "num_chunks": 42, "pages": [1, 2, 3, ...]},
            ...
        ]
    """
    all_docs = self.collection.get(include=["metadatas"])
    
    # Group by file_name
    doc_map = {}
    for metadata in all_docs.get("metadatas", []):
        file_name = metadata.get("file_name", "unknown")
        if file_name not in doc_map:
            doc_map[file_name] = {
                "file_name": file_name,
                "num_chunks": 0,
                "pages": set()
            }
        doc_map[file_name]["num_chunks"] += 1
        doc_map[file_name]["pages"].add(metadata.get("page", 0))
    
    # Convert sets to sorted lists
    result = []
    for doc in doc_map.values():
        doc["pages"] = sorted(doc["pages"])
        result.append(doc)
    
    return result
```

IMPORTS NEEDED:
- Add: `import logging`
- Add: `logger = logging.getLogger(__name__)`

---

### FILE 2: backend/app/services/hybrid_retriever.py

ADD THIS METHOD (after existing rebuild_index method):

```python
def delete_document(self, file_name: str) -> int:
    """
    Delete all chunks for a specific document and rebuild BM25 index.
    
    Args:
        file_name: Name of file to delete (e.g., "document.pdf")
    
    Returns:
        Number of chunks deleted
    
    Raises:
        ValueError: If file_name not found
    """
    # Delete from ChromaDB (raises ValueError if not found)
    deleted_ids = self.chroma.delete_by_file_name(file_name)
    num_deleted = len(deleted_ids)
    
    # Rebuild BM25 index from updated ChromaDB
    self._build_bm25_index()
    
    logger.info(f"Deleted {num_deleted} chunks for {file_name}, rebuilt BM25 index")
    return num_deleted
```

IMPORTS NEEDED:
- Add: `import logging`
- Add: `logger = logging.getLogger(__name__)`

---

### FILE 3: backend/app/main.py (NEW FILE - ENTIRE CONTENT)

```python
"""
FastAPI application for RAG Q&A system.
Initializes services and exposes REST API endpoints.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime, timezone

from backend.app.models import ErrorResponse
from backend.app.services.embeddings import EmbeddingsService
from backend.app.services.chroma_service import ChromaService
from backend.app.services.hybrid_retriever import HybridRetriever
from backend.app.services.answer_generator import AnswerGenerator
from backend.app.api import chat, documents

logger = logging.getLogger(__name__)

# Global service instances (initialized on startup)
embeddings_service: EmbeddingsService = None
chroma_service: ChromaService = None
retriever: HybridRetriever = None
answer_generator: AnswerGenerator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown context manager for FastAPI.
    Initializes services on startup.
    """
    # Startup
    global embeddings_service, chroma_service, retriever, answer_generator
    
    logger.info("Initializing RAG services...")
    embeddings_service = EmbeddingsService()
    chroma_service = ChromaService(embeddings_service=embeddings_service)
    retriever = HybridRetriever(
        chroma_service=chroma_service,
        embeddings_service=embeddings_service
    )
    answer_generator = AnswerGenerator()
    logger.info("RAG services initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG services")
    # Services will clean up automatically


# Create FastAPI app
app = FastAPI(
    title="RAG Q&A API",
    description="Retrieval-Augmented Generation system for question answering",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware (allow all origins for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all exceptions and return structured error response."""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            detail="An unexpected error occurred. Please try again later.",
            request_id=request_id,
            timestamp=timestamp
        ).model_dump()
    )


# Mount routers
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    """Redirect to OpenAPI docs."""
    pass  # FastAPI handles this automatically at /docs


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
```

---

### FILE 4: backend/app/api/chat.py (NEW FILE)

```python
"""Chat endpoints for question answering."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime, timezone
import logging

from backend.app import main
from backend.app.models import QueryRequest, QueryResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def submit_query(request: QueryRequest):
    """
    Submit a question and get an answer with source citations.
    
    - **query**: User question (1-5000 chars)
    - **conversation_id**: Optional ID for client-side history tracking
    - **max_sources**: Max passages to include (1-20, default 5)
    
    Returns:
    - **answer**: Generated answer grounded in documents
    - **sources**: Passages used as context
    - **tokens_used**: LLM token count
    - **conversation_id**: Echo of input conversation_id
    - **timestamp**: When answer was generated
    """
    try:
        # Retrieve passages using hybrid retrieval
        retrieval_results = main.retriever.retrieve(
            query_text=request.query,
            n_results=request.max_sources
        )
        
        # Generate answer from passages
        answer_result = main.answer_generator.generate(
            query=request.query,
            retriever_results=retrieval_results,
            max_sources=request.max_sources
        )
        
        # Map to response model
        sources = [
            {
                "page": s["page"],
                "file": s["file"],
                "excerpt": s["excerpt"],
                "score": s["score"]
            }
            for s in answer_result.get("sources", [])
        ]
        
        return QueryResponse(
            answer=answer_result["answer"],
            sources=sources,
            tokens_used=answer_result.get("tokens_used", 0),
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
    
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/conversations")
async def list_conversations():
    """
    List active conversations (MVP: returns empty list).
    
    Client manages conversation history locally.
    Stateless API - no server-side session tracking.
    """
    return {"conversations": []}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """
    Delete a conversation (MVP: no-op).
    
    Client manages conversation history locally.
    """
    return {"status": "ok", "conversation_id": conv_id}
```

---

### FILE 5: backend/app/api/documents.py (NEW FILE)

```python
"""Document upload and management endpoints."""

from fastapi import APIRouter, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime, timezone
import logging
import tempfile
import os

from backend.app import main
from backend.app.models import DocumentResponse, DocumentListResponse, DeleteResponse, ErrorResponse, Document
from backend.app.services.pdf_processor import process_pdf

logger = logging.getLogger(__name__)
router = APIRouter()

# Constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_MIME_TYPES = {"application/pdf"}


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF document for processing.
    
    - Validates file size (max 50 MB)
    - Validates MIME type (application/pdf)
    - Extracts text, chunks, generates embeddings
    - Stores in ChromaDB with BM25 index
    
    Returns:
    - **doc_id**: UUID assigned to document
    - **file_name**: Original filename
    - **num_chunks**: Chunks created
    - **upload_time**: ISO 8601 timestamp
    - **size_bytes**: File size
    """
    
    # Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Expected application/pdf"
        )
    
    try:
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Validate file size
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds 50 MB limit (provided: {file_size / 1024 / 1024:.1f} MB)"
            )
        
        # Write to temp file for PDF processing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Process PDF (extract, chunk, validate)
            chunks = process_pdf(tmp_path)
            
            if not chunks:
                raise ValueError("PDF contains no readable text")
            
            # Store in ChromaDB
            chromadb_ids = main.chroma_service.add_chunks(chunks)
            
            # Rebuild BM25 index
            main.retriever.rebuild_index()
            
            # Generate response
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            doc_id = str(uuid.uuid4())
            
            logger.info(f"Uploaded document: {file.filename} (doc_id={doc_id}, chunks={len(chunks)})")
            
            return DocumentResponse(
                doc_id=doc_id,
                file_name=file.filename,
                num_chunks=len(chunks),
                upload_time=timestamp,
                size_bytes=file_size
            )
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except ValueError as e:
        logger.error(f"PDF validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid PDF: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )


@router.get("/list", response_model=DocumentListResponse)
async def list_documents():
    """
    List all uploaded documents with metadata.
    
    Returns:
    - **documents**: List of document metadata
    - **total_documents**: Count of documents
    - **total_chunks**: Total chunks across all documents
    """
    try:
        docs = main.chroma_service.get_unique_documents()
        
        # Convert to Document models
        document_list = []
        for doc in docs:
            # Note: doc_id would need to come from document metadata storage
            # For MVP, using doc index as placeholder
            document_list.append(Document(
                doc_id=str(uuid.uuid4()),  # TODO: store UUIDs in metadata
                file_name=doc["file_name"],
                num_chunks=doc["num_chunks"],
                upload_time=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                size_bytes=0  # TODO: track file sizes
            ))
        
        # Calculate totals
        total_chunks = sum(d.num_chunks for d in document_list)
        
        return DocumentListResponse(
            documents=document_list,
            total_documents=len(document_list),
            total_chunks=total_chunks
        )
    
    except Exception as e:
        logger.error(f"List documents error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str):
    """
    Delete a document from all indexes (ChromaDB + BM25).
    
    - **doc_id**: UUID of document to delete
    
    Returns:
    - **doc_id**: Document that was deleted
    - **file_name**: Filename of deleted document
    - **chunks_deleted**: Number of chunks removed
    - **timestamp**: When deletion occurred
    """
    
    try:
        # TODO: Lookup file_name from doc_id (need metadata storage)
        # For now, this is a placeholder
        
        logger.info(f"Document deleted: doc_id={doc_id}")
        
        return DeleteResponse(
            doc_id=doc_id,
            file_name="unknown.pdf",  # TODO: lookup from metadata
            chunks_deleted=0,  # TODO: track actual count
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
    
    except Exception as e:
        logger.error(f"Delete document error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )
```

================================================================================
CRITICAL IMPLEMENTATION NOTES
================================================================================

NOTE 1: Document ID Mapping
Current state: We generate UUID per upload, but don't store it anywhere.
Problem: DELETE /documents/{doc_id} needs to map doc_id → file_name
Solution needed: Add document metadata storage (simple JSON file or ChromaDB special collection)
Recommended: Add to ChromaService.add_chunks() return value + store in temp dict

NOTE 2: File Size Tracking
Current state: We know size_bytes during upload, but don't persist it.
Problem: GET /documents/list shows size_bytes = 0
Solution: Store in metadata or separate tracking dict

NOTE 3: Dependency Injection
Current design: Global service instances in main.py module
Alternative: Use FastAPI Depends() for cleaner injection
Current approach: Simpler for Phase 5 MVP

NOTE 4: Error Response Structure
Not yet used in endpoints because HTTPException uses FastAPI defaults.
Should wrap in custom exception handler for consistency.
Placeholder in documents.py with TODOs.

================================================================================
FILES REQUIRING APPROVAL
================================================================================

READY FOR REVIEW:
✓ PHASE5_MODELS_PROPOSAL.md - All Pydantic models (shown above in separate file)
✓ This document - File structure, modifications, new endpoints

PROPOSED STRUCTURE:
1. backend/app/models.py (NEW) - 250 lines
2. backend/app/main.py (NEW) - 100 lines
3. backend/app/api/__init__.py (NEW) - empty
4. backend/app/api/chat.py (NEW) - 90 lines
5. backend/app/api/documents.py (NEW) - 180 lines
6. backend/app/services/chroma_service.py (MODIFY) - +40 lines
7. backend/app/services/hybrid_retriever.py (MODIFY) - +15 lines
8. tests/test_api.py (NEW) - 400 lines (proposed in next phase)

KNOWN GAPS (for future phases):
- Document UUID ↔ file_name mapping storage
- File size persistence
- Actual DELETE /documents/{doc_id} implementation
- Structured error responses in all endpoints
- Comprehensive test coverage

================================================================================
NEXT STEP
================================================================================

Please review:
1. models.py Pydantic schemas (in PHASE5_MODELS_PROPOSAL.md)
2. This file structure and modifications

Confirm/modify, then I will:
1. Create backend/app/models.py
2. Modify ChromaService and HybridRetriever (add the 2 new methods)
3. Create main.py, api/chat.py, api/documents.py
4. Create tests/test_api.py

DO NOT execute any commands until your explicit approval.

================================================================================
