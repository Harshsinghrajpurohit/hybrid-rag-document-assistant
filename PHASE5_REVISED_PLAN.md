================================================================================
PHASE 5: REVISED IMPLEMENTATION PLAN - GAPS RESOLVED
================================================================================

DATE: 2026-10-13T09:41:36Z
STATUS: Design revision - NO CODE CHANGES YET

================================================================================
GAP ANALYSIS & CLOSURE STRATEGY
================================================================================

### GAP 1: Document Metadata (UUID ↔ filename mapping + metadata)

PROBLEM:
- Upload generates UUID but doesn't store it anywhere
- DELETE /documents/{doc_id} can't map UUID → filename
- No tracking of upload_time, file_size, chunk_count
- GET /documents/list has incomplete metadata

ROOT CAUSE:
- No persistent storage for document metadata
- Current design stores only chunks in ChromaDB

SOLUTION (no new database):
Use ChromaDB metadata itself as the storage mechanism.

APPROACH:
1. When uploading, store metadata in ChromaDB as a special marker document:
   - Create a metadata chunk with ID: "META:{doc_id}"
   - Store in metadatas: {"doc_id": uuid, "file_name": "...", "upload_time": "...", "size_bytes": 123, "num_chunks": 42, "is_metadata": true}
   - Content: empty or "metadata marker"

2. Rationale:
   - ChromaDB already persists
   - No new database needed
   - Metadata travels with the data
   - Survives app restart
   - Query-able by doc_id

3. Implementation:
   - Add ChromaService.store_document_metadata(doc_id, file_name, size_bytes, num_chunks, upload_time) -> None
   - Add ChromaService.get_document_metadata(doc_id) -> Dict
   - Add ChromaService.list_document_metadata() -> List[Dict]
   - Add ChromaService.delete_document_metadata(doc_id) -> None
   - These methods use special ID prefix "META:{doc_id}"

VERIFICATION:
- Metadata persists across app restart
- DELETE finds document by UUID
- GET /list shows correct metadata

---

### GAP 2: File Size

PROBLEM:
- File size known during upload
- Not persisted
- GET /documents/list returns 0
- Never a valid placeholder for real data

SOLUTION:
Store in ChromaDB metadata (same as GAP 1).

IMPLEMENTATION:
- DocumentUpload endpoint receives file content (already have byte length)
- Pass size_bytes to ChromaService.store_document_metadata()
- Retrieve via ChromaService.get_document_metadata()
- Return in GET /documents/list

FILES AFFECTED:
- backend/app/services/chroma_service.py (add metadata storage methods)
- backend/app/api/documents.py (use metadata methods)

VERIFICATION:
- GET /documents/list shows accurate file sizes
- No zero placeholders

---

### GAP 3: Deletion (UUID → chunks, no inconsistency)

PROBLEM:
- DELETE /documents/{doc_id} doesn't map UUID → filename
- If deletion fails halfway, ChromaDB and BM25 left inconsistent
- No atomicity

SOLUTION:
Implement atomic deletion with rollback semantics.

APPROACH:
1. Map UUID to filename via metadata storage (GAP 1)
2. Delete in order:
   a) Delete metadata from ChromaDB (marks document as "deleted")
   b) Delete all chunks for file_name from ChromaDB
   c) Rebuild BM25 index
   d) If any step fails, raise exception (client sees error, knows deletion failed)

3. Atomicity strategy:
   - Delete metadata first (single operation, unlikely to fail)
   - If this succeeds, chunks deletion follows
   - If chunks deletion fails, metadata is already deleted (partial state)
   - Solution: Re-add metadata on error, then raise

IMPLEMENTATION:
- Add HybridRetriever.delete_document(doc_id: str) -> Dict
  - Calls ChromaService.get_document_metadata(doc_id)
  - Calls ChromaService.delete_by_file_name(file_name)
  - Rebuilds BM25 index
  - Handles errors by restoring metadata if needed
  - Returns: {doc_id, file_name, chunks_deleted}

FILES AFFECTED:
- backend/app/services/chroma_service.py (metadata methods + delete_by_file_name)
- backend/app/services/hybrid_retriever.py (add delete_document)
- backend/app/api/documents.py (call delete_document)

VERIFICATION:
- DELETE /documents/{uuid} finds correct file
- All chunks removed from ChromaDB
- BM25 index updated
- No orphaned metadata or chunks left behind
- Error case: metadata restored, exception raised to client

---

### GAP 4: Error Handling (structured responses, no stack traces)

PROBLEM:
- Current endpoints raise HTTPException with raw error messages
- No request_id for debugging
- Stack traces may leak to users
- Inconsistent error response format

SOLUTION:
Implement custom exception handlers at app level.

APPROACH:
1. Define custom exception class: APIException
   - Attributes: error_type (str), detail (str), status_code (int), request_id (str)
   - Auto-generates request_id if not provided

2. Raise APIException from endpoints (business logic errors)
   - Examples: "DOCUMENT_NOT_FOUND", "FILE_TOO_LARGE", "PDF_CORRUPTED", "OLLAMA_UNAVAILABLE"

3. Global exception handler in main.py
   - Catches APIException → return ErrorResponse (safe messages, no stack trace)
   - Catches Exception → log with request_id, return generic 500 error

4. Error types (expected):
   - FILE_TOO_LARGE (413)
   - INVALID_MIME_TYPE (400)
   - PDF_CORRUPTED (422)
   - DOCUMENT_NOT_FOUND (404)
   - OLLAMA_UNAVAILABLE (503)
   - INTERNAL_SERVER_ERROR (500)

IMPLEMENTATION:
- Add backend/app/exceptions.py (new file)
  - Define APIException class
  - Map error_type → HTTP status code
- Modify backend/app/main.py
  - Add exception handlers for APIException and generic Exception
  - Log with request_id
- Modify backend/app/api/chat.py and documents.py
  - Raise APIException instead of HTTPException
  - Catch business logic errors, re-raise as APIException

FILES AFFECTED:
- backend/app/exceptions.py (NEW)
- backend/app/main.py (exception handlers)
- backend/app/api/chat.py (use APIException)
- backend/app/api/documents.py (use APIException)

VERIFICATION:
- All error responses include request_id
- No stack traces in responses
- HTTP status codes match error types
- Errors logged with request_id for correlation

================================================================================
REVISED FILE STRUCTURE
================================================================================

FILES TO CREATE (NEW):
1. backend/app/models.py (NEW) - Pydantic schemas - 280 lines
2. backend/app/exceptions.py (NEW) - Custom exceptions - 60 lines
3. backend/app/main.py (NEW) - FastAPI app - 150 lines
4. backend/app/api/__init__.py (NEW) - empty
5. backend/app/api/chat.py (NEW) - Chat endpoints - 110 lines
6. backend/app/api/documents.py (NEW) - Document endpoints - 220 lines
7. tests/test_api.py (NEW) - Integration tests - 500 lines

FILES TO MODIFY (EXTENSIONS):
1. backend/app/services/chroma_service.py - Add 5 metadata management methods - ~80 lines
2. backend/app/services/hybrid_retriever.py - Add delete_document() method - ~30 lines

TOTAL NEW/MODIFIED: ~1,410 lines of code

================================================================================
IMPLEMENTATION SEQUENCE (REVISED - INCREMENTAL)
================================================================================

**STEP 1: Models** (this phase)
- Show complete models.py
- Include new models: DocumentMetadata, APIError, etc.
- Await approval

**STEP 2: Exceptions**
- Show exceptions.py
- Define APIException, error_type enum, status code mapping
- Await approval

**STEP 3: Service Extensions**
- Show ChromaService additions (metadata methods)
- Show HybridRetriever.delete_document()
- Await approval

**STEP 4: Main Application**
- Show main.py with exception handlers
- Show service initialization
- Await approval

**STEP 5: Chat Endpoints**
- Show api/chat.py with error handling
- Await approval

**STEP 6: Document Endpoints**
- Show api/documents.py with complete deletion logic
- Await approval

**STEP 7: Tests**
- Show comprehensive test suite
- Await approval

**STEP 8: Execution**
- Create all files in sequence
- Run tests
- Manual verification

================================================================================
STORAGE STRATEGY JUSTIFICATION
================================================================================

Why ChromaDB metadata for document storage?

OPTION A: ChromaDB metadata (CHOSEN)
✓ Already persistent
✓ No new infrastructure
✓ Survives app restart
✓ Query-able by doc_id
✓ Data travels with chunks (can't orphan metadata)
✗ Slightly non-standard use (mixing data + metadata in same collection)

OPTION B: JSON file in backend/data/
✓ Simple, human-readable
✓ No new dependencies
✗ Manual sync with ChromaDB (can get out of sync)
✗ Doesn't survive if file deleted but ChromaDB not

OPTION C: SQLite database
✓ Proper relational storage
✗ New dependency (sqlite3 is builtin, but adds complexity)
✗ User approved "no new database without explanation"
✗ Overkill for MVP

OPTION D: In-memory dict
✓ Fastest
✗ Lost on app restart
✗ Not suitable for persistent system

CONCLUSION: ChromaDB metadata (OPTION A) is the best fit for this project.
- Leverages existing infrastructure
- Zero new dependencies
- Guaranteed consistency (metadata stored with data)
- Simple implementation
- Suitable for MVP and beyond

================================================================================
HOW EACH GAP IS CLOSED
================================================================================

GAP 1: Document Metadata Storage
├─ File: backend/app/services/chroma_service.py
├─ Add: store_document_metadata(doc_id, file_name, size_bytes, num_chunks, upload_time)
├─ Add: get_document_metadata(doc_id)
├─ Add: list_document_metadata()
├─ Add: delete_document_metadata(doc_id)
└─ Storage: Special ChromaDB entries with ID prefix "META:{doc_id}"

GAP 2: File Size Recording
├─ File: backend/app/api/documents.py
├─ Action: Pass actual file size to store_document_metadata()
├─ Retrieval: Get from list_document_metadata()
├─ Return: Accurate size_bytes in GET /documents/list
└─ Verification: Never return 0 for known value

GAP 3: Deletion without Inconsistency
├─ File: backend/app/services/hybrid_retriever.py
├─ Add: delete_document(doc_id)
├─ Logic:
│  1. Get metadata (fail if not found → 404)
│  2. Extract file_name
│  3. Delete from ChromaDB by file_name
│  4. Delete metadata from ChromaDB
│  5. Rebuild BM25 index
│  6. Return success or fail atomically
└─ Handles: Partial failure with rollback

GAP 4: Error Handling with Request IDs
├─ File: backend/app/exceptions.py (NEW)
├─ Add: APIException class
├─ File: backend/app/main.py
├─ Add: Exception handlers
├─ File: backend/app/api/chat.py and documents.py
├─ Action: Raise APIException instead of HTTPException
└─ Result: All errors have request_id, no stack traces

================================================================================
VERIFICATION STRATEGY
================================================================================

For each gap, how will we verify it's closed?

GAP 1 VERIFICATION: Document Metadata
Test: test_document_metadata_storage
1. Upload document with UUID
2. Query metadata by UUID
3. Verify all fields present (file_name, upload_time, size_bytes, num_chunks)
4. Restart app
5. Query metadata again → should still be there

GAP 2 VERIFICATION: File Size
Test: test_document_list_includes_sizes
1. Upload 3 documents (1MB, 5MB, 10MB)
2. GET /documents/list
3. Verify each size matches uploaded size
4. Assert no zeros in size_bytes field

GAP 3 VERIFICATION: Deletion Atomicity
Test: test_delete_document_removes_all_chunks
1. Upload document (10 chunks)
2. DELETE /documents/{doc_id}
3. Query ChromaDB → verify 0 chunks remain
4. Query BM25 → verify no results for doc content
5. GET /documents/list → verify doc not in list

Test: test_delete_nonexistent_document
1. DELETE /documents/{fake_uuid}
2. Expect 404 error with request_id

Test: test_delete_partial_failure_recovery
1. Mock ChromaDB failure
2. DELETE /documents/{doc_id}
3. Expect error with request_id
4. Verify metadata not deleted (recovery)

GAP 4 VERIFICATION: Error Handling
Test: test_error_response_structure
1. Send invalid request (missing field)
2. Expect 400 with ErrorResponse structure
3. Verify has: error, detail, request_id, timestamp
4. Verify no stack trace in detail

Test: test_request_id_logging
1. Make request that causes error
2. Check server logs for request_id
3. Verify same request_id in error response

================================================================================
NEXT STEP: PROPOSE COMPLETE MODELS.PY
================================================================================

Ready to show complete models.py code with:
1. All Pydantic models
2. DocumentMetadata model for storage
3. APIError model (internal)
4. All request/response schemas
5. Detailed docstrings for each model
6. Design rationale for each decision

Awaiting approval to proceed with models.py code proposal.

================================================================================
