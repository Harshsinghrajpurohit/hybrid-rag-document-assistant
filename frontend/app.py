"""
Streamlit frontend for the RAG-Q&A Document Assistant.

A thin client over the FastAPI backend — no RAG logic lives here.
Run from the repository root (backend must be running):

    python -m streamlit run frontend/app.py
"""

import os

import requests
import streamlit as st

DEFAULT_API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # mirrors the backend's hardcoded limit
CONNECT_TIMEOUT = 10  # seconds; read timeouts are set per call

st.set_page_config(page_title="RAG-Q&A Document Assistant", page_icon="📄", layout="wide")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_base() -> str:
    """Current backend base URL (sidebar-editable via the text_input key)."""
    return st.session_state.get("api_url_field", DEFAULT_API_URL).rstrip("/")


def show_api_error(resp_or_exc, action: str) -> None:
    """Render any API/network failure in a friendly, uniform way."""
    if isinstance(resp_or_exc, requests.exceptions.ConnectionError):
        st.error(
            f"Cannot reach the backend at `{api_base()}`. Is it running? "
            "Start it from the repository root with `python -m backend.app.main`."
        )
        return
    if isinstance(resp_or_exc, requests.exceptions.Timeout):
        st.error(
            f"{action} timed out — the backend or Ollama may still be busy. "
            "Retry in a moment."
        )
        return

    resp = resp_or_exc
    try:
        body = resp.json()
    except ValueError:
        st.error(f"{action} failed (HTTP {resp.status_code}) with an unreadable response.")
        return

    error = body.get("error", "UNKNOWN")
    detail = body.get("detail", "No details provided.")
    if resp.status_code == 503 or error == "OLLAMA_UNAVAILABLE":
        st.error(
            f"⚠️ The LLM service (Ollama) is temporarily unavailable. {detail} "
            "Start it with `ollama serve` and retry."
        )
    else:
        guidance = {
            "UNSUPPORTED_FORMAT": "Supported: PDF, DOCX, TXT, MD, CSV, XLSX.",
            "EMPTY_FILE": "The selected file is empty.",
            "EXTRACTION_FAILED": (
                "The file could not be parsed — it may be corrupted or "
                "contain no readable text."
            ),
        }
        extra = f" {guidance[error]}" if error in guidance else ""
        st.error(f"{action} failed — **{error}**: {detail}{extra}")
    with st.expander("Error details"):
        st.write(f"**Error code:** {error}")
        st.write(f"**HTTP status:** {resp.status_code}")
        st.write(f"**Request ID:** `{body.get('request_id', '')}`")
        st.write(f"**Time:** {body.get('timestamp', '')}")


def api_get(path: str, timeout_read: int = 30):
    return requests.get(f"{api_base()}{path}", timeout=(CONNECT_TIMEOUT, timeout_read))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Connection")
    st.text_input("Backend API URL", value=DEFAULT_API_URL, key="api_url_field")
    if st.button("Check connection"):
        try:
            r = api_get("/health")
            if r.status_code == 200 and r.json().get("status") == "healthy":
                st.success(f"Backend healthy at {api_base()}")
            else:
                st.warning(f"Unexpected /health response (HTTP {r.status_code}).")
        except requests.exceptions.RequestException as e:
            show_api_error(e, "Health check")
    st.divider()
    st.caption(
        "The API is stateless — no conversation history is stored. "
        "Each question is answered independently."
    )
    st.caption("Documents tab → upload & manage PDFs · Ask tab → question answering.")


tab_docs, tab_ask = st.tabs(["📄 Documents", "💬 Ask Questions"])

# ---------------------------------------------------------------------------
# Documents tab — upload / list / delete via the existing API
# ---------------------------------------------------------------------------

with tab_docs:
    st.header("Document library")

    uploaded = st.file_uploader(
        "Upload a document (max 50 MB)",
        type=["pdf", "docx", "txt", "md", "csv", "xlsx"],
    )
    if uploaded is not None:
        raw = uploaded.getvalue()
        size_mb = len(raw) / (1024 * 1024)
        fmt = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "?"
        st.caption(f"Selected: **{uploaded.name}** ({size_mb:.2f} MB, format: **{fmt}**)")
        if len(raw) > MAX_UPLOAD_BYTES:
            st.warning(
                f"This file exceeds the backend's 50 MB limit ({size_mb:.1f} MB). "
                "Split or shrink it and retry."
            )
        elif st.button("Upload & index", type="primary"):
            try:
                with st.spinner("Uploading, chunking and embedding… large PDFs can take a while."):
                    r = requests.post(
                        f"{api_base()}/documents/upload",
                        files={"file": (uploaded.name, raw, "application/pdf")},
                        timeout=(CONNECT_TIMEOUT, 600),
                    )
                if r.status_code == 200:
                    d = r.json()
                    st.success(
                        f"**{d['file_name']}** indexed — {d['num_chunks']} chunks, "
                        f"{d['size_bytes'] / 1024:.1f} KB.\n\nDocument ID: `{d['doc_id']}`"
                    )
                else:
                    show_api_error(r, "Upload")
            except requests.exceptions.RequestException as e:
                show_api_error(e, "Upload")

    st.divider()
    st.subheader("Uploaded documents")
    try:
        with st.spinner("Loading document list…"):
            r = api_get("/documents/list")
        if r.status_code == 200:
            data = r.json()
            docs = data.get("documents", [])
            st.caption(
                f"{data.get('total_documents', len(docs))} document(s) · "
                f"{data.get('total_chunks', 0)} chunk(s) total"
            )
            if not docs:
                st.info("No documents yet — upload a PDF above.")
            else:
                st.dataframe(
                    [
                        {
                            "File": doc["file_name"],
                            "Format": doc.get("file_type") or "—",
                            "Chunks": doc["num_chunks"],
                            "Size (KB)": round(doc["size_bytes"] / 1024, 1),
                            "Uploaded": doc["upload_time"],
                            "Doc ID": doc["doc_id"],
                        }
                        for doc in docs
                    ],
                    width="stretch",
                )
                labels = {f"{doc['file_name']}  ({doc['doc_id'][:8]}…)": doc for doc in docs}
                choice = st.selectbox("Document to delete", options=list(labels.keys()))
                if st.button("🗑 Delete selected document"):
                    doc = labels[choice]
                    try:
                        with st.spinner(f"Deleting {doc['file_name']}…"):
                            dr = requests.delete(
                                f"{api_base()}/documents/{doc['doc_id']}",
                                timeout=(CONNECT_TIMEOUT, 60),
                            )
                        if dr.status_code == 200:
                            dd = dr.json()
                            st.success(
                                f"Deleted **{dd['file_name']}** "
                                f"({dd['chunks_deleted']} chunks removed)."
                            )
                            st.rerun()
                        else:
                            show_api_error(dr, "Delete")
                    except requests.exceptions.RequestException as e:
                        show_api_error(e, "Delete")
        else:
            show_api_error(r, "List documents")
    except requests.exceptions.RequestException as e:
        show_api_error(e, "List documents")

# ---------------------------------------------------------------------------
# Ask tab — question answering via the existing API
# ---------------------------------------------------------------------------

with tab_ask:
    st.header("Ask your documents")
    question = st.text_area("Question", placeholder="What is hybrid search?", height=120)
    max_sources = st.slider("Max sources", min_value=1, max_value=10, value=5)

    if st.button("Ask", type="primary", disabled=not question.strip()):
        try:
            with st.spinner("Searching documents and generating an answer…"):
                r = requests.post(
                    f"{api_base()}/chat/query",
                    json={"query": question.strip(), "max_sources": max_sources},
                    timeout=(CONNECT_TIMEOUT, 180),
                )
            if r.status_code == 200:
                d = r.json()
                st.subheader("Answer")
                st.markdown(d.get("answer") or "_No answer generated._")
                st.caption(
                    f"⏱ {d.get('tokens_used', 0)} tokens (measured) · {d.get('timestamp', '')}"
                )
                sources = d.get("sources") or []
                if sources:
                    st.subheader(f"Sources ({len(sources)})")
                    for i, s in enumerate(sources, 1):
                        score = s.get("score") or 0.0
                        page = s.get("page")
                        where = f"page {page}" if page else (s.get("location") or "location not recorded")
                        label = (
                            f"{i}. {s.get('file', '?')} — {where} "
                            f"(score {score:.4f})"
                        )
                        with st.expander(label):
                            st.write(s.get("excerpt", ""))
                else:
                    st.info(
                        "No sources were retrieved — upload a document on the "
                        "Documents tab, or rephrase the question."
                    )
            else:
                show_api_error(r, "Query")
        except requests.exceptions.RequestException as e:
            show_api_error(e, "Query")