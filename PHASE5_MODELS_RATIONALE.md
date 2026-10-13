================================================================================
PHASE 5: MODELS.PY - DESIGN RATIONALE & KEY DECISIONS
================================================================================

DATE: 2026-10-13T09:42:38Z
STATUS: Design review - awaiting approval before file creation

================================================================================
MODEL STRUCTURE OVERVIEW
================================================================================

The proposed models.py contains:

1. INTERNAL MODELS (not exposed to API users):
   - DocumentMetadata: Tracks UUID→filename mapping, timestamps, sizes, chunk IDs
   - APIError: Internal error details for exception handling

2. REQUEST MODELS:
   - QueryRequest: User question submission with optional conversation_id

3. RESPONSE MODELS (success):
   - Source: Single cited passage (page, file, excerpt, relevance score)
   - QueryResponse: Answer with sources and token count
   - Document: Document metadata for listing
   - DocumentListResponse: List of all documents with totals
   - DocumentResponse: Confirmation after upload
   - DeleteResponse: Confirmation after deletion

4. ERROR MODEL:
   - ErrorResponse: Structured error response with request_id

5. HELPERS:
   - generate_request_id(): Create UUID for request tracking
   - get_current_timestamp(): Current UTC timestamp ISO 8601
   - ERROR_STATUS_CODES: Map error types to HTTP status codes

================================================================================
KEY DESIGN DECISIONS & RATIONALE
================================================================================

### DECISION 1: UUID for Document Identification

CHOICE: Use UUID (not filename) as document identifier

RATIONALE:
✓ Stable: Doesn't change if file renamed
✓ Unique: No collision even with 1 billion documents
✓ Anonymous: Doesn't leak filesystem structure
✓ Queryable: Can map doc_id → metadata in ChromaDB
✓ Deletion-safe: Deleting doc A doesn't affect doc B (filename independence)
✓ Allows: Same filename uploaded multiple times (different UUIDs)

ALTERNATIVE (rejected):
✗ Filename: Could collide, breaks if user renames file, tied to filesystem

WHERE USED:
- DocumentMetadata.doc_id: Stored in ChromaDB as "META:{doc_id}"
- Document.doc_id: Returned in list, used for deletion
- DeleteResponse.doc_id: Confirms which UUID was deleted
- All client deletion requests use doc_id

---

### DECISION 2: DocumentMetadata Internal Model

CHOICE: Create DocumentMetadata model for ChromaDB storage

RATIONALE:
✓ Maps UUID → filename (required for deletion)
✓ Stores upload_time (when uploaded)
✓ Stores size_bytes (actual file size, never 0)
✓ Stores num_chunks (for diagnostics)
✓ Stores chromadb_chunk_ids (for efficient deletion)
✓ Persists in ChromaDB with "META:{doc_id}" ID prefix
✓ Survives app restart
✓ No new database needed

STORAGE FORMAT:
- ChromaDB special entry:
  {
    "ids": ["META:550e8400-e29b-41d4-a716-446655440000"],
    "documents": [""],  # empty or metadata marker
    "metadatas": [{
      "doc_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_name": "ai_guide.pdf",
      "upload_time": "2026-10-13T09:42:00Z",
      "size_bytes": 2097152,
      "num_chunks": 42,
      "is_metadata": true
    }]
  }

DELETION SAFETY:
- Metadata not visible in queries (filtered by "is_metadata" flag)
- Metadata travels with chunks (can't orphan)
- Deleting by file_name removes both chunks and metadata atomically

---

### DECISION 3: No Confidence Field in QueryResponse

CHOICE: Omit confidence score (user requirement: measured data only)

RATIONALE:
✗ Confidence from RRF scores is semi-fabricated (scaling 0.01-0.05 → 0-1)
✓ tokens_used is measured directly from Ollama API (real value)
✓ User requirement: "Include measured token usage only; omit uncalibrated confidence"

WHERE VERIFICATION HAPPENS:
- Source.score: RRF score is measured (preserved as-is, 0.0-0.1 range)
- QueryResponse.tokens_used: Sum of eval_count + prompt_eval_count (actual)
- No fabricated confidence field

---

### DECISION 4: Stateless API with conversation_id Pass-Through

CHOICE: No server-side conversation history; client manages it

RATIONALE:
✓ Simpler implementation (no session storage)
✓ Scales better (stateless servers)
✓ Client has full history control
✓ Compatible with multi-tab browsing
✓ conversation_id is optional (conversation_id: Optional[str])

CLIENT FLOW:
1. User asks question in conversation A
2. Client creates conversation_id = uuid.uuid4()
3. Client POST /chat/query with conversation_id
4. Server returns answer with same conversation_id
5. Client stores: {conversation_id, query, answer}
6. User asks follow-up
7. Client POST /chat/query with same conversation_id
8. Server doesn't care about conversation_id (stateless)
9. Client stores second Q&A under same conversation_id

SERVER BEHAVIOR:
- Echo back conversation_id (no state management)
- Each query is independent
- No session cleanup needed
- No database of conversations

---

### DECISION 5: Structured Error Responses with request_id

CHOICE: All errors follow ErrorResponse structure with UUID tracking

ERROR TYPES:
- FILE_TOO_LARGE (413): > 50 MB
- INVALID_MIME_TYPE (400): Not application/pdf
- PDF_CORRUPTED (422): PDF extraction failed
- DOCUMENT_NOT_FOUND (404): UUID doesn't exist
- OLLAMA_UNAVAILABLE (503): LLM service down
- INTERNAL_SERVER_ERROR (500): Unexpected exception
- INVALID_REQUEST (400): Missing/invalid fields

RATIONALE:
✓ request_id correlates error with server logs
✓ detail is user-friendly (no stack traces)
✓ error is machine-readable (programmatic handling)
✓ timestamp helps debugging
✓ Consistent format for all errors

EXAMPLE ERROR:
```json
{
  "error": "FILE_TOO_LARGE",
  "detail": "Uploaded file exceeds 50 MB limit (provided: 75 MB)",
  "request_id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-10-13T09:42:07Z"
}
```

HOW LOGGED:
Server logs:
```
ERROR [request_id=550e8400-e29b-41d4-a716-446655440001] 
  FILE_TOO_LARGE: File upload exceeds limit
  path=/documents/upload method=POST size_bytes=75000000
```

User sees only detail (safe message), can report request_id for support.

---

### DECISION 6: Timestamp Format

CHOICE: ISO 8601 UTC with 'Z' suffix (e.g., "2026-10-13T09:42:07Z")

RATIONALE:
✓ ISO 8601 is standard (machine-parseable)
✓ UTC removes timezone ambiguity
✓ 'Z' suffix is explicit (means UTC, not +00:00)
✓ Consistent across all responses
✓ Matches Ollama/LangChain conventions

WHERE USED:
- DocumentMetadata.upload_time
- QueryResponse.timestamp
- Document.upload_time
- DocumentResponse.upload_time
- DeleteResponse.timestamp
- ErrorResponse.timestamp

HELPER: get_current_timestamp() generates correct format

---

### DECISION 7: Field Constraints (min/max lengths, ranges)

CHOICE: Validate at Pydantic level before processing

EXAMPLES:
- QueryRequest.query: min_length=1, max_length=5000
  (too short = confusing, too long = token waste)
- QueryRequest.max_sources: ge=1, le=20
  (0 = no context, >20 = excessive context, tokens bloat)
- Document.num_chunks: ge=1
  (0 or negative = data corruption)
- DocumentListResponse.total_chunks: ge=0
  (0 is valid, negative = data error)

BENEFIT:
✓ Reject invalid input early (before processing)
✓ Clear error messages (validation error details Pydantic generates)
✓ Prevents downstream bugs

---

### DECISION 8: Complete Metadata Never Returns 0

CHOICE: size_bytes is always actual file size (never 0 placeholder)

RATIONALE:
✓ User requirement: "Never use 0 as placeholder for value that should be available"
✓ File size is known during upload (HTTP Content-Length)
✓ Must be persisted in DocumentMetadata
✓ Must be returned in all responses
✓ 0 is only valid if file is truly 0 bytes (invalid PDF anyway)

WHERE ENFORCED:
- Document.size_bytes: ge=1 (field constraint)
- DocumentResponse.size_bytes: ge=1
- DocumentMetadata.size_bytes: ge=1
- All responses never return 0

---

### DECISION 9: Source Excerpts Limited to 150 Characters

CHOICE: Excerpt field max_length=200 (150 chars + "..." if truncated)

RATIONALE:
✓ Keeps response size reasonable
✓ Shows context without overwhelming user
✓ Consistent with industry practice
✓ Fits well in UI/mobile displays
✓ Tokenizable by LLM if needed

WHERE ENFORCED:
- Source.excerpt: max_length=200
- Generated by AnswerGenerator._extract_sources()

---

### DECISION 10: Response Structure is Minimal but Complete

CHOICE: Include all necessary fields, exclude fabricated ones

INCLUDED (measured/actual):
✓ answer: Generated by LLM (actual)
✓ sources: Retrieved by retriever (actual)
✓ tokens_used: From Ollama API (measured)
✓ timestamp: Server time (measured)
✓ conversation_id: Echo (client-provided or generated)

EXCLUDED (not measured):
✗ confidence: Score scaling is semi-fabricated
✗ retrieval_metadata: Retriever internal details
✗ cache_hits: Caching not implemented yet
✗ inference_time: Not measured by Ollama API

================================================================================
VALIDATION FLOW (Error Prevention)
================================================================================

QueryRequest validation:
1. query: 1-5000 chars (too short = error, too long = token waste)
2. conversation_id: Optional[str] (null allowed)
3. max_sources: 1-20 (0 = no context, >20 = excessive)

DocumentListResponse validation:
1. documents: List[Document] (empty allowed)
2. total_documents: ≥ 0 (never negative)
3. total_chunks: ≥ 0 (consistent with document count)

ErrorResponse validation:
1. error: Must be valid error type (checked in exception handler)
2. detail: Safe message (no stack traces)
3. request_id: UUID format (auto-generated if not provided)
4. timestamp: ISO 8601 (auto-generated)

================================================================================
STORAGE MAPPING (How Models Persist)
================================================================================

User uploads document:
1. FastAPI receives UploadFile
2. Extract: file_name, size_bytes, content
3. Process PDF → chunks
4. Create DocumentMetadata:
   - doc_id = uuid.uuid4()
   - file_name = "ai_guide.pdf"
   - upload_time = now()
   - size_bytes = actual bytes
   - num_chunks = len(chunks)
   - chromadb_chunk_ids = IDs returned by add_chunks()
5. Store DocumentMetadata in ChromaDB as "META:{doc_id}"
6. Return DocumentResponse

User lists documents:
1. Query ChromaDB for all "META:*" entries
2. Extract metadata from each
3. Build Document objects
4. Sort by upload_time (descending)
5. Return DocumentListResponse

User deletes document:
1. Query DocumentMetadata by doc_id
2. Extract file_name from metadata
3. Delete all chunks matching file_name from ChromaDB
4. Delete DocumentMetadata from ChromaDB
5. Rebuild BM25 index
6. Return DeleteResponse

================================================================================
API EXAMPLES (Request/Response Pairs)
================================================================================

### EXAMPLE 1: Query with Conversation Tracking

REQUEST:
POST /chat/query
{
  "query": "What is machine learning?",
  "conversation_id": "conv_550e8400",
  "max_sources": 5
}

RESPONSE:
{
  "answer": "Machine learning is a subset of AI...",
  "sources": [
    {
      "page": 1,
      "file": "ai_guide.pdf",
      "excerpt": "Machine learning is a subset of AI...",
      "score": 0.0324
    }
  ],
  "tokens_used": 145,
  "conversation_id": "conv_550e8400",
  "timestamp": "2026-10-13T09:42:07Z"
}

---

### EXAMPLE 2: Upload Document

REQUEST:
POST /documents/upload
Content-Type: multipart/form-data
[binary PDF file]

RESPONSE:
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "research_paper.pdf",
  "num_chunks": 42,
  "upload_time": "2026-10-13T09:42:07Z",
  "size_bytes": 2097152
}

---

### EXAMPLE 3: Error Response

REQUEST:
POST /documents/upload
Content-Type: multipart/form-data
[200 MB PDF file]

RESPONSE (413 Payload Too Large):
{
  "error": "FILE_TOO_LARGE",
  "detail": "Uploaded file exceeds 50 MB limit (provided: 200 MB)",
  "request_id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-10-13T09:42:07Z"
}

================================================================================
NEXT STEPS
================================================================================

PENDING APPROVAL:

1. Review models.py structure and design rationale
2. Confirm all 10 design decisions are acceptable
3. Approve complete models.py code

UPON APPROVAL, WILL PROCEED WITH:

**STEP 2**: Create exceptions.py (custom exception class, error type mapping)
**STEP 3**: Modify ChromaService (add metadata storage methods)
**STEP 4**: Modify HybridRetriever (add delete_document)
**STEP 5**: Create main.py (FastAPI app initialization)
**STEP 6**: Create api/chat.py (chat endpoints)
**STEP 7**: Create api/documents.py (document endpoints)
**STEP 8**: Create tests/test_api.py (integration tests)

NO FILES WILL BE CREATED OR MODIFIED UNTIL EXPLICIT APPROVAL.

================================================================================
