================================================================================
PHASE 5: EXISTING PIPELINE INTERFACES & IMPLEMENTATION PLAN
================================================================================

DATE: 2026-10-13
STATUS: Analysis phase - NO CODE CHANGES YET

================================================================================
PART 1: EXISTING PIPELINE INTERFACES
================================================================================

### Phase 1: PDF Processing (backend/app/services/pdf_processor.py)

Functions (module-level, not a class):

1. extract_pdf_text(file_path: str) -> Tuple[List[Dict], str]
   - Input: Path to PDF file
   - Output: (list of page dicts, file_name)
   - Returns: [{"text": str, "page": int, "file_name": str}, ...]
   - Raises: FileNotFoundError, ValueError (corrupted PDF)
   - Side effects: Logs warnings/info, reads from disk

2. split_into_chunks(text: str, chunk_size: int=512, chunk_overlap: int=50) -> List[str]
   - Input: Text string
   - Output: List of overlapping chunks
   - Uses: LangChain RecursiveCharacterTextSplitter

3. process_pdf(file_path: str, chunk_size: int=512, chunk_overlap: int=50) -> List[Dict]
   - Combined pipeline: extract → chunk → attach metadata
   - Output format: [{"text": str, "page": int, "file_name": str, "chunk_index": int}, ...]
   - This is the main entry point for Phase 1

---

### Phase 2: Embeddings & Storage (ChromaService)

Class: ChromaService
Location: backend/app/services/chroma_service.py

Constructor:
- __init__(db_path: str = None, embeddings_service: EmbeddingsService = None)
- Default db_path: backend/chroma_db (from Config)
- Creates persistent ChromaDB client
- Auto-creates "documents" collection

Key Methods:

1. add_chunks(chunks: List[Dict[str, Any]]) -> List[str]
   - Input: List of dicts with keys: "text", "page", "file_name", "chunk_index"
   - Process: Embeds texts, generates IDs (format: "{file_name}_{page}_{chunk_index}")
   - Output: List of document IDs added to ChromaDB
   - Side effects: Writes to ChromaDB (auto-persisted)
   - Returns: IDs for tracking

2. query(query_text: str, n_results: int=5, where: Optional[Dict]=None) -> Dict
   - Input: Query string
   - Output: {"ids": [...], "distances": [...], "documents": [...], "metadatas": [...], "query_embedding": [...]}
   - Can filter by metadata using "where" parameter

3. get_collection_stats() -> Dict[str, Any]
   - Returns: {"collection_name": "documents", "document_count": int, "db_path": str}

4. delete_all()
   - ⚠️ CRITICAL: Deletes all documents from collection
   - Used for testing only
   - NOTE: No selective deletion method exists!

5. persist()
   - No-op: data auto-persists in ChromaDB 1.5.9+

---

### Phase 3: Hybrid Retrieval (HybridRetriever)

Class: HybridRetriever
Location: backend/app/services/hybrid_retriever.py

Constructor:
- __init__(chroma_service: ChromaService, embeddings_service: Optional[EmbeddingsService]=None, k_rrf: int=60)
- Builds BM25 index from ChromaDB on init
- Uses dependency injection for services

Key Methods:

1. retrieve(query_text: str, n_results: int=5, where: Optional[Dict]=None) -> Dict
   - Input: Query string, number of results
   - Process:
     a) BM25 search (sparse retrieval)
     b) Dense search (semantic via ChromaDB)
     c) RRF fusion (combine rankings)
   - Output: {
       "ids": [...],
       "documents": [...],
       "metadatas": [...],
       "distances": [...],
       "bm25_scores": [...],
       "rrf_scores": [...]
     }
   - Returns results in fused order (highest RRF scores first)

2. rebuild_index()
   - Rebuilds BM25 index from current ChromaDB documents
   - Call this after adding/deleting documents

3. get_index_stats() -> Dict[str, Any]
   - Returns stats about BM25 index

4. _build_bm25_index() (private)
   - Called on __init__
   - Fetches all documents from ChromaDB and builds BM25 index

---

### Phase 4: Answer Generation (AnswerGenerator)

Class: AnswerGenerator
Location: backend/app/services/answer_generator.py

Constructor:
- __init__(base_url: str=None, model: str=None, max_tokens: int=500, temperature: float=0.3)
- Default model: "qwen3:4b-instruct"
- Default base_url: from Config (http://localhost:11434)

Key Method:

1. generate(query: str, retriever_results: Dict[str, Any], max_sources: int=5) -> Dict
   - Input: Query string, retriever results dict
   - Process:
     a) Validates retriever_results (empty → graceful fallback)
     b) Extracts top-5 chunks by default
     c) Formats as prompt with source attribution
     d) Calls Ollama qwen3:4b-instruct
     e) Extracts sources from metadata + scores
     f) Calculates confidence from RRF scores
   - Output: {
       "answer": str,
       "sources": [{"page": int, "file": str, "excerpt": str, "score": float}, ...],
       "confidence": float (0.0-1.0),
       "tokens_used": int,
       "model": str,
       "timestamp": str (ISO 8601)
     }
   - Raises: RuntimeError if Ollama API fails

---

### Embeddings Service (EmbeddingsService)

Class: EmbeddingsService
Location: backend/app/services/embeddings.py

Key Method:

1. embed(text: Union[str, List[str]]) -> np.ndarray
   - Input: Single string or list of strings
   - Output: 768-dim embeddings (float32)
   - Returns: Single array (1D) for string, or array of arrays (2D) for list
   - Calls: Ollama API (/api/embed)
   - Model: "nomic-embed-text:latest"
   - Caches results

================================================================================
PART 2: CRITICAL FINDINGS - PERSISTENCE & DELETION
================================================================================

ISSUE #1: Document Deletion Not Fully Implemented
---
Current State:
- ChromaService.add_chunks() writes to ChromaDB ✓
- ChromaService.delete_all() exists but deletes ALL documents (not selective)
- HybridRetriever has NO delete method
- BM25 index is rebuilt in memory only, never persisted

Problem:
- If we delete from ChromaDB, BM25 index is stale until rebuild_index() called
- No API to delete a single document by ID
- If delete fails halfway, ChromaDB and BM25 can be inconsistent

Solution Approach for Phase 5:
1. Add ChromaService.delete_by_file_name(file_name: str) method
   - Deletes all chunks for a specific file from ChromaDB
   - Returns list of deleted IDs
2. Add HybridRetriever.delete_document(file_name: str) method
   - Calls ChromaService.delete_by_file_name()
   - Rebuilds BM25 index
   - Ensures atomic operation
3. Ensure upload failure doesn't leave partial data
   - Wrap in transaction-like logic

ISSUE #2: Document Listing Not Implemented
---
Current State:
- ChromaService.get_collection_stats() gives total count only
- No way to list individual documents with file names

Solution for Phase 5:
1. Add ChromaService.get_unique_documents() method
   - Query ChromaDB for all unique (file_name, num_chunks, first_page, last_page)
   - Returns list of document metadata

---

ISSUE #3: BM25 Index Persistence
---
Current State:
- BM25 index is in-memory only
- On app restart, index rebuilt from ChromaDB
- If ChromaDB has more docs than BM25 knows about → stale

Solution:
- HybridRetriever._build_bm25_index() is called on __init__
- Should always catch up on startup
- No problem for Phase 5 (stateless API)

================================================================================
PART 3: PROPOSED PHASE 5 FILE STRUCTURE
================================================================================

Files to CREATE:

1. backend/app/main.py (NEW)
   - FastAPI app initialization
   - Import services (ChromaService, HybridRetriever, AnswerGenerator)
   - Initialize dependency instances
   - Mount routers
   - Add error handlers
   - ~80 lines

2. backend/app/models.py (NEW)
   - Pydantic request/response models
   - QueryRequest, QueryResponse, Source
   - DocumentResponse, DocumentListResponse
   - ErrorResponse
   - ~100 lines

3. backend/app/api/__init__.py (NEW - empty)

4. backend/app/api/chat.py (NEW)
   - POST /chat/query
   - GET /chat/conversations (simplified: just return empty for MVP)
   - DELETE /chat/conversations/{conv_id} (no-op for MVP)
   - ~80 lines

5. backend/app/api/documents.py (NEW)
   - POST /documents/upload
   - GET /documents/list
   - DELETE /documents/{doc_id}
   - ~120 lines

6. backend/app/services/chroma_service.py (MODIFY)
   - Add: delete_by_file_name(file_name: str) -> List[str]
   - Add: get_unique_documents() -> List[Dict]
   - ~30 new lines

7. backend/app/services/hybrid_retriever.py (MODIFY)
   - Add: delete_document(file_name: str) -> bool
   - ~15 new lines

Files NOT changed:
- config.py (already complete)
- pdf_processor.py (already complete)
- embeddings.py (already complete)
- chroma_service.py base functionality (keep existing)
- hybrid_retriever.py base functionality (keep existing)
- answer_generator.py (already complete)

================================================================================
PART 4: REVISED IMPLEMENTATION SEQUENCE
================================================================================

STEP 1: Pydantic Models (models.py)
  - Define all request/response schemas
  - No file I/O, no API calls
  - Pure type definitions
  - Approval: Review model structure

STEP 2: Service Extensions (chroma_service.py + hybrid_retriever.py)
  - Add delete_by_file_name() to ChromaService
  - Add get_unique_documents() to ChromaService
  - Add delete_document() to HybridRetriever
  - Approval: Review new methods

STEP 3: FastAPI App (main.py)
  - Initialize FastAPI instance
  - Create service instances (ChroService, HybridRetriever, AnswerGenerator)
  - Mount routers
  - Add error handlers
  - Approval: Review app structure

STEP 4: Chat Endpoints (api/chat.py)
  - POST /chat/query: retrieve + generate answer
  - GET /chat/conversations: MVP (empty list)
  - DELETE /chat/conversations/{conv_id}: MVP (no-op)
  - Approval: Review endpoint logic

STEP 5: Document Endpoints (api/documents.py)
  - POST /documents/upload: process PDF, store chunks
  - GET /documents/list: list uploaded files
  - DELETE /documents/{doc_id}: remove from indexes
  - Approval: Review endpoint logic

STEP 6: Tests (tests/test_api.py)
  - Unit tests for endpoints
  - Integration tests with real services
  - Error path tests
  - Approval: Review test plan

================================================================================
PART 5: KEY DESIGN DECISIONS FOR APPROVAL
================================================================================

DECISION 1: Document ID Format
Question: How do we identify documents for deletion/listing?
Proposed: Use file_name as primary identifier
Rationale:
  - Simpler than inventing new IDs
  - Metadata already stored in ChromaDB
  - Matches Phase 1 output ("file_name" field)
  - Limitation: Can only upload one version of "foo.pdf" at a time
  - Approve? Y/N

DECISION 2: Stateless API
Question: Store conversation history?
Proposed: Stateless for MVP - client tracks conversation_id, we pass it through
Rationale:
  - Simpler implementation
  - No database schema needed
  - Client can POST same query multiple times if needed
  - Future phases can add session storage
  - Approve? Y/N

DECISION 3: File Upload Validation
Question: What validations on uploaded PDF?
Proposed:
  - File size limit: 50 MB (check Content-Length)
  - MIME type: application/pdf (check header)
  - PDF validity: Try extract_pdf_text() - if it raises ValueError, reject
  - Approve? Y/N

DECISION 4: Confidence & Tokens
Question: Include these fields in response?
Current:
  - AnswerGenerator already calculates both
  - confidence: average of top RRF scores scaled 0-1
  - tokens_used: sum of eval_count + prompt_eval_count from Ollama
  - Both are meaningful values, not fabricated
  - Approve including both? Y/N

DECISION 5: Error Handling
Question: How detailed should error responses be?
Proposed: Return structured errors:
  {
    "error": str (brief message),
    "detail": str (detailed explanation),
    "request_id": str (for debugging),
    "timestamp": str (ISO 8601)
  }
  HTTP status codes:
  - 400: Bad request (invalid query, missing fields)
  - 404: Not found (document doesn't exist)
  - 413: Payload too large (PDF > 50MB)
  - 422: Unprocessable entity (corrupted PDF)
  - 500: Server error (Ollama down, ChromaDB error)
  - 503: Service unavailable
  Approve? Y/N

================================================================================
SUMMARY
================================================================================

EXISTING IMPLEMENTATIONS (REUSE):
✓ Phase 1: process_pdf() - use as-is
✓ Phase 2: ChromaService.add_chunks() - use as-is
✓ Phase 3: HybridRetriever.retrieve() - use as-is
✓ Phase 4: AnswerGenerator.generate() - use as-is

REQUIRED EXTENSIONS:
◐ ChromaService: Add delete_by_file_name(), get_unique_documents()
◐ HybridRetriever: Add delete_document()

NEW FILES TO CREATE:
☐ backend/app/main.py (FastAPI app)
☐ backend/app/models.py (Pydantic schemas)
☐ backend/app/api/chat.py (Chat endpoints)
☐ backend/app/api/documents.py (Document endpoints)
☐ tests/test_api.py (Integration tests)

NEXT STEP:
1. Review this analysis
2. Approve/reject the 5 design decisions
3. I will create models.py as Step 1
4. Then wait for your approval before Step 2

================================================================================
