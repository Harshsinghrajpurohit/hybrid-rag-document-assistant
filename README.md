# RAG-Q&A Document Assistant

Hybrid Retrieval-Augmented Generation Q&A system. Upload PDF documents, ask
questions in natural language, and get answers grounded in your documents with
page-level source citations.

**Components**
- **Backend**: FastAPI REST API (`backend/app`)
- **Retrieval**: hybrid search — BM25 keyword + ChromaDB dense vectors, fused with Reciprocal Rank Fusion (`hybrid_retriever.py`)
- **Generation**: Qwen LLM served by Ollama, with measured token usage
- **Frontend**: Streamlit UI (`frontend/app.py`). Run with `python -m streamlit run frontend/app.py` from the repository root (backend must be running on `http://localhost:8000`).

See [Architecture.md](Architecture.md) for the system diagram, [Design.md](Design.md)
for design decisions, and [PRD.md](PRD.md) / [Phases.md](Phases.md) for requirements
and roadmap.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11–3.13 | **Validated on 3.13.0** (the version used for the current test environment) |
| [Ollama](https://ollama.com) | Installed and running locally (default: `http://localhost:11434`) |
| Two Ollama models | Both are required by the application's default settings: `ollama pull qwen3:4b-instruct` (answers) and `ollama pull nomic-embed-text:latest` (embeddings) |

## Setup

Run all commands from the repository root (required — the `backend` package is
resolved from the current working directory):

```powershell
# 1. Create and activate a virtual environment (PowerShell)
python -m venv env
env\Scripts\Activate.ps1

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. (Optional) Create a local config file — every key is optional;
#    the defaults in backend/app/config.py work out of the box
copy .env.example .env
```

bash/git-bash equivalents: `source env/Scripts/activate` and `cp .env.example .env`.

## Running the backend

```powershell
# From the repository root
python -m backend.app.main
```

or equivalently:

```powershell
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Host and port come from `API_HOST` / `API_PORT` (defaults `0.0.0.0:8000`; set
`API_HOST=127.0.0.1` in `.env` to restrict access to your machine). Real
environment variables always override values in `.env`.

## API

All errors use a consistent JSON shape: `{"error": ..., "detail": ..., "request_id": ..., "timestamp": ...}`.
If Ollama is unreachable, times out, or returns a server error, `/chat/query`
responds with **503** (`LLM_SERVICE_UNAVAILABLE`).

| Method & path | Description |
|---|---|
| `GET /health` | Health check |
| `POST /documents/upload` | Upload a document (`multipart/form-data`, field `file`). Formats: PDF, DOCX, TXT, MD, CSV, XLSX (validated by extension + magic bytes); **50 MB max** (hardcoded limit) |
| `GET /documents/list` | List uploaded documents with metadata |
| `DELETE /documents/{doc_id}` | Delete a document and its chunks |
| `POST /chat/query` | Ask a question: body `{"query": "...", "max_sources": 5}` → answer, sources with page numbers, measured `tokens_used` |
| `GET /chat/conversations` | **Stub** — always returns an empty list; no conversation history is stored |
| `DELETE /chat/conversations/{conv_id}` | **Stub** — returns a canned acknowledgement; nothing is persisted |

The API is stateless: the client manages any conversation context itself.

Example:

```powershell
curl -X POST http://localhost:8000/chat/query `
  -H "Content-Type: application/json" `
  -d "{\"query\": \"What is this document about?\", \"max_sources\": 5}"
```

## Configuration

`backend/app/config.py` loads `.env` at startup (real environment variables
take precedence). All keys are optional — the defaults below are what the code
uses if nothing is set.

| Key | Default | Purpose |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Bind port |
| `ENVIRONMENT` | `development` | Runtime environment label |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `LLM_MODEL` | `qwen3:4b-instruct` | Answer generation model |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `LLM_MAX_TOKENS` | `500` | Answer length cap |
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | Embedding model |
| `EMBEDDING_DIMENSION` | `768` | Embedding vector size |
| `CHROMA_DB_PATH` | `backend/chroma_db` | Vector store (git-ignored; relative paths resolve from the working directory) |

## Frontend (Streamlit)

A thin UI over the same API — upload/manage documents and ask questions with
page-level source citations. `streamlit` is an active dependency in
`requirements.txt`.

```powershell
# Terminal 2 — from the repository root (backend must already be running)
python -m streamlit run frontend/app.py
```

Open http://localhost:8501. The sidebar shows the backend URL (default
`http://localhost:8000`, override with the `API_BASE_URL` env var or the
sidebar input) and a connection check button. The UI is a pure API client —
no RAG logic and no conversation history (the API is stateless).

## Supported document formats

| Format | Extraction | Source attribution |
|---|---|---|
| `.pdf` | PyMuPDF text per page (existing behavior preserved) | page number |
| `.docx` | python-docx paragraphs grouped by headings | section heading path |
| `.txt` | utf-8 / latin-1 fallback decoding | filename only |
| `.md` | heading-path segmentation (`#` levels) | section heading path |
| `.csv` | header-aware row serialization (`Column: value \| ...`) | row range |
| `.xlsx` | openpyxl, per worksheet | sheet name + row range |

Files are validated by extension plus light magic-byte checks; empty or
unparseable files return clear errors (`UNSUPPORTED_FORMAT`, `EMPTY_FILE`,
`EXTRACTION_FAILED`). Spreadsheet ingestion is limited to **5,000 data rows
per sheet/file** — larger files are rejected with an explicit error rather
than silently truncated.

**Tabular limitations**: vector/BM25 retrieval finds relevant *rows* with
their column context, but this system does not perform numerical analysis —
no aggregations, calculations, sorting, or spreadsheet formulas. Answers
about numbers quote retrieved rows only; the LLM never executes generated code.

## Testing

```powershell
# From the repository root
python -m pytest tests/ -q
```

Use `python -m pytest` (not bare `pytest`) from the repository root — this is
what puts `backend` on `sys.path`. The suite never touches the real ChromaDB
directory; most tests use mocks, but a few service/retrieval tests
(`test_retriever.py`, `test_chroma_service.py`, `test_document_operations.py`)
call the local Ollama embedding API, so Ollama should be running for the full
suite. The newer test files (`test_document_processor.py`,
`test_multi_format_api.py`) are fully mocked and need no Ollama.

Expected result: **119 passed, 4 skipped, 0 failed** (recorded validation result on Python 3.13.0 / Windows; not a guarantee for all environments). The 4 skips are PDF-fixture tests in `tests/test_pdf_processor.py` that need `reportlab`; without it they skip.

## Data & storage

- Documents are chunked (512 characters, 50 overlap — currently hardcoded in
  `services/pdf_processor.py`) and embedded via Ollama, then stored in
  ChromaDB at `backend/chroma_db/` (git-ignored, created on first use).
- A BM25 index is built in memory from the stored chunks at query time.

## Project layout

```
backend/app/
  main.py               FastAPI app, /health, global error handlers
  config.py             Env-based settings (10 keys, loads .env)
  exceptions.py         APIException hierarchy -> structured 4xx/5xx JSON
  models.py             Pydantic request/response models
  api/
    chat.py             /chat/query + conversation stubs
    documents.py        upload / list / delete
  services/
    answer_generator.py   Ollama /api/generate (qwen3:4b-instruct)
    embeddings.py         Ollama /api/embed (nomic-embed-text)
    chroma_service.py     ChromaDB persistence
    hybrid_retriever.py   BM25 + dense + RRF fusion
    pdf_processor.py      PyMuPDF extraction + chunking
    document_processor.py Multi-format dispatcher (docx/txt/md/csv/xlsx)
    llm_service.py        legacy module, not referenced by the app
tests/                  pytest test suite
.env.example            Template for the 10 configuration keys
frontend/app.py         Streamlit UI (documents + Q&A over the API)
```