# Session Memory Index

This file tracks important facts, decisions, and progress for the RAG-Q&A Project. It helps maintain context across chat sessions and prevents redundant work.

**Last Updated**: 2026-10-12

## Completed Tasks
- ✅ Created project documentation (PRD.md, Architecture.md, Rules.md, Phases.md, Design.md)
- ✅ Project structure defined
- ✅ Technology stack finalized
- ✅ Development phases planned

## Current Phase
- ⏳ **Phase 0**: Environment verification (awaiting approval and execution)

## Key Decisions

### Technology Stack
- **Frontend**: Streamlit (native components)
- **Backend**: FastAPI + Uvicorn
- **RAG**: LangChain (no LangGraph initially)
- **Vector DB**: ChromaDB (persistent local)
- **Embeddings**: Sentence Transformers
- **Keyword Search**: BM25
- **Fusion**: Reciprocal Rank Fusion (RRF)
- **LLM**: Qwen via Ollama (local, no API keys)
- **PDF**: PyMuPDF

### Rationale
- Minimal dependencies, no unnecessary frameworks
- Everything runs locally (no external APIs)
- Simple, understandable pipeline
- Deterministic (reproducible results)

### No LangGraph
- Project is deterministic RAG, not agentic
- LangChain handles document processing, splitting, embeddings, prompts
- No dynamic routing or conditional logic needed
- Added complexity without benefit for MVP

## Important Notes

### Data Consistency
- ChromaDB is persistent (survives restarts)
- BM25 index rebuilt from ChromaDB metadata on startup
- Every chunk stores: document ID, document name, page number
- Deletions must remove from both indexes

### API Design
- Streamlit talks to FastAPI via HTTP
- All RAG logic in backend (not duplicated in frontend)
- Responses include source metadata (document, page, passage)

### Error Handling Strategy
- Retrieve empty → LLM responds "insufficient information"
- Never hallucinate when evidence is missing
- Log errors server-side for debugging
- Clear, actionable messages to user

## Environment Status

### Python
- Workspace location: `D:\Work Folder\RAG-Q&A-Project`
- Virtual environment: `env/` directory exists
- Python version: [to be verified in Phase 0]
- Dependencies: requirements.txt ready

### Ollama
- Installation: [to be verified in Phase 0]
- Model: qwen3:4b-instruct [to verify actual model name]
- Status: [to be checked]

### Project Structure
- [to be created in Phase 0]

## Blocking Issues
- None currently

## Next Steps
1. Phase 0: Verify Python environment, Ollama, and model name
2. Create project directory structure
3. Create .env.example and .gitignore
4. Proceed to Phase 1: PDF extraction and chunking

---

- [Phase 1 Complete](memory/phase-1-complete.md) — PDF extraction & chunking, all tests passing ✅
- [Current Status](memory/current-project-status.md) — What's done, what's next, reminders
