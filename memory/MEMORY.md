# RAG Q&A Project Memory Index

## Project Status
- [Current Status](memory/current-project-status.md) — Overall progress (40% complete), what's done, what's next
- [Phase 1 Complete](memory/phase-1-complete.md) — PDF extraction & chunking, 6 critical tests passing ✅
- [Phase 2 Complete](memory/phase-2-complete.md) — Embeddings & ChromaDB, 24/24 tests passing, persistence verified ✅
- [Phase 3 Complete](memory/phase-3-complete.md) — Hybrid retriever (BM25 + semantic + RRF), 17 tests designed, 7/7 quick tests passing ✅

## Progress Summary
- **Phase 0**: Environment setup ✅
- **Phase 1**: PDF extraction & chunking ✅ (6/6 critical tests)
- **Phase 2**: Embeddings & ChromaDB ✅ (24/24 tests)
- **Phase 3**: Hybrid retriever (BM25 + RRF) ✅ (17 tests, 7/7 verified)
- **Phase 4**: Answer generation — NEXT
- **Phases 5-10**: API, frontend, deployment

## Today's Work (2026-10-13)
- Completed Phase 2 (Embeddings & ChromaDB) — All 24 tests passing
- Completed Phase 3 (Hybrid Retriever) — BM25 + dense search + RRF fusion
- Overall progress: 40% complete (4/10 phases)

## Quick Reference
- **Test command**: `python -m pytest tests/ -v`
- **Quick Phase 3 test**: `python quick_test_phase3.py` (7/7 PASS)
- **Database**: `backend/chroma_db/` (persistent, auto-created)
- **Config**: `backend/app/config.py` (reads from environment)
- **Embedding model**: Ollama nomic-embed-text:latest (768-dim)
- **Retrieval**: Hybrid (BM25 keywords + semantic similarity)

## Key Architectural Points
1. **Same embedding model everywhere**: Ollama nomic-embed-text for documents AND queries (compatibility guaranteed)
2. **Persistence verified**: ChromaDB auto-persists, survives app restarts
3. **Metadata critical**: Every chunk stores page, file_name, chunk_index for source citations
4. **Hybrid retrieval**: BM25 (exact matches) + dense (semantic) + RRF fusion
5. **Human-in-the-loop**: Ask for approval before each phase implementation

## Next Phase
- **Phase 4**: Answer Generator
  - Takes retriever results (top-K chunks)
  - Formats as LLM context
  - Calls Ollama qwen3:4b-instruct
  - Returns answer + source citations

