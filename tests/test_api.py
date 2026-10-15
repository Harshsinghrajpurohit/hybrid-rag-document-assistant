"""
Integration tests for API endpoints.

Tests the complete API flow from document upload to query answering.
Uses FastAPI's TestClient for HTTP testing.
"""

import unittest
import io
import json
import shutil
import tempfile

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.documents import router as documents_router
from backend.app.api.chat import router as chat_router
from backend.app.config import Config
from backend.app.models import DocumentResponse, QueryResponse, Source


def make_valid_pdf(
    text: str = "Hybrid RAG test document. This PDF contains extractable text for chunking.",
) -> bytes:
    """Build a one-page PDF containing extractable text."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestAPIFlow(unittest.TestCase):
    def setUp(self):
        """Set up test client with an isolated temporary ChromaDB directory."""
        # ChromaService reads Config.CHROMA_DB_PATH at construction time, and
        # every API endpoint constructs it per request, so overriding the class
        # attribute here isolates all database access for each test.
        self._original_db_path = Config.CHROMA_DB_PATH
        self._temp_db_path = tempfile.mkdtemp(prefix="api_test_")
        Config.CHROMA_DB_PATH = self._temp_db_path
        self.client = TestClient(app)

    def tearDown(self):
        """Restore configuration and remove temporary resources (even on failure)."""
        Config.CHROMA_DB_PATH = self._original_db_path
        shutil.rmtree(self._temp_db_path, ignore_errors=True)

    def test_health_check(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy", "service": "RAG-Q&A API"})

    def test_documents_list_empty(self):
        """Test documents list when no documents exist."""
        response = self.client.get("/documents/list")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_documents"], 0)
        self.assertEqual(data["total_chunks"], 0)
        self.assertEqual(len(data["documents"]), 0)

    def test_upload_document_success(self):
        """Test successful document upload."""
        pdf_content = make_valid_pdf()

        # Test file upload
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        response = self.client.post("/documents/upload", files=files)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure
        self.assertIn("doc_id", data)
        self.assertIn("file_name", data)
        self.assertIn("num_chunks", data)
        self.assertIn("upload_time", data)
        self.assertIn("size_bytes", data)
        self.assertGreaterEqual(data["size_bytes"], 1)
        self.assertGreaterEqual(data["num_chunks"], 1)
        # Reported size must equal the actual uploaded byte length
        self.assertEqual(data["size_bytes"], len(pdf_content))

    def test_upload_invalid_mime_type(self):
        """Test upload with invalid file type."""
        files = {"file": ("test.txt", io.BytesIO(b"text content"), "text/plain")}
        response = self.client.post("/documents/upload", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "INVALID_MIME_TYPE")

    def test_upload_file_too_large(self):
        """Test upload with file exceeding size limit."""
        # Create large file content (51 MB)
        large_content = b"x" * (51 * 1024 * 1024)
        files = {"file": ("large.pdf", io.BytesIO(large_content), "application/pdf")}
        response = self.client.post("/documents/upload", files=files)
        # Approved API contract: oversized uploads fail with HTTP 413
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "FILE_TOO_LARGE")

    def test_delete_document_success(self):
        """Test successful document deletion."""
        # First upload a valid document
        pdf_content = make_valid_pdf()
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        upload_response = self.client.post("/documents/upload", files=files)

        self.assertEqual(upload_response.status_code, 200)
        doc_data = upload_response.json()
        doc_id = doc_data["doc_id"]

        # Now test deletion
        response = self.client.delete(f"/documents/{doc_id}")
        self.assertEqual(response.status_code, 200)
        doc_response = response.json()

        self.assertEqual(doc_response["doc_id"], doc_id)
        self.assertIn("file_name", doc_response)
        self.assertIn("chunks_deleted", doc_response)
        self.assertGreaterEqual(doc_response["chunks_deleted"], 1)

    def test_chat_query_success(self):
        """Test successful chat query."""
        # First upload a valid document so retrieval returns a real source
        pdf_content = make_valid_pdf()
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        upload_response = self.client.post("/documents/upload", files=files)
        self.assertEqual(upload_response.status_code, 200)
        doc_data = upload_response.json()
        doc_id = doc_data["doc_id"]

        # Test chat query
        query_data = {
            "query": "What is this document about?",
            "max_sources": 5
        }
        response = self.client.post("/chat/query", json=query_data)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()

        self.assertIn("answer", response_data)
        self.assertIn("sources", response_data)
        self.assertIn("tokens_used", response_data)
        self.assertIn("conversation_id", response_data)
        self.assertIn("timestamp", response_data)
        self.assertGreaterEqual(response_data["tokens_used"], 0)
        # The valid uploaded document must be retrieved and cited as a source
        self.assertGreaterEqual(len(response_data["sources"]), 1)


    def test_upload_and_list_single_document(self):
        """Upload one document and verify it is listed exactly once with correct metadata."""
        pdf_content = make_valid_pdf()
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        upload_response = self.client.post("/documents/upload", files=files)
        self.assertEqual(upload_response.status_code, 200)
        upload_data = upload_response.json()

        list_response = self.client.get("/documents/list")
        self.assertEqual(list_response.status_code, 200)
        list_data = list_response.json()

        self.assertEqual(list_data["total_documents"], 1)
        self.assertEqual(len(list_data["documents"]), 1)
        self.assertEqual(list_data["total_chunks"], upload_data["num_chunks"])

        document = list_data["documents"][0]
        self.assertEqual(document["doc_id"], upload_data["doc_id"])
        self.assertEqual(document["file_name"], "test.pdf")
        self.assertEqual(document["num_chunks"], upload_data["num_chunks"])
        self.assertEqual(document["upload_time"], upload_data["upload_time"])
        self.assertEqual(document["size_bytes"], len(pdf_content))

    def test_delete_one_of_two_documents(self):
        """Deleting one document must leave the other intact."""
        pdf_a = make_valid_pdf("Document A content about retrieval augmented generation.")
        files_a = {"file": ("doc_a.pdf", io.BytesIO(pdf_a), "application/pdf")}
        upload_a = self.client.post("/documents/upload", files=files_a)
        self.assertEqual(upload_a.status_code, 200)
        doc_a = upload_a.json()

        pdf_b = make_valid_pdf("Document B content about hybrid search with BM25.")
        files_b = {"file": ("doc_b.pdf", io.BytesIO(pdf_b), "application/pdf")}
        upload_b = self.client.post("/documents/upload", files=files_b)
        self.assertEqual(upload_b.status_code, 200)
        doc_b = upload_b.json()

        self.assertNotEqual(doc_a["doc_id"], doc_b["doc_id"])

        delete_response = self.client.delete(f"/documents/{doc_a['doc_id']}")
        self.assertEqual(delete_response.status_code, 200)
        delete_data = delete_response.json()
        self.assertEqual(delete_data["doc_id"], doc_a["doc_id"])
        self.assertEqual(delete_data["file_name"], "doc_a.pdf")
        self.assertEqual(delete_data["chunks_deleted"], doc_a["num_chunks"])

        list_response = self.client.get("/documents/list")
        self.assertEqual(list_response.status_code, 200)
        list_data = list_response.json()
        self.assertEqual(list_data["total_documents"], 1)
        self.assertEqual(len(list_data["documents"]), 1)
        self.assertEqual(list_data["documents"][0]["doc_id"], doc_b["doc_id"])
        self.assertEqual(list_data["documents"][0]["file_name"], "doc_b.pdf")
        self.assertEqual(list_data["total_chunks"], doc_b["num_chunks"])

    def test_delete_same_document_twice(self):
        """Deleting a document twice must return 404 on the second request."""
        pdf_content = make_valid_pdf()
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        upload_response = self.client.post("/documents/upload", files=files)
        self.assertEqual(upload_response.status_code, 200)
        doc_id = upload_response.json()["doc_id"]

        first_delete = self.client.delete(f"/documents/{doc_id}")
        self.assertEqual(first_delete.status_code, 200)

        second_delete = self.client.delete(f"/documents/{doc_id}")
        self.assertEqual(second_delete.status_code, 404)
        self.assertEqual(second_delete.json()["error"], "DOCUMENT_NOT_FOUND")

    def test_delete_unknown_document(self):
        """Deleting a document that was never uploaded must return 404."""
        response = self.client.delete("/documents/00000000-0000-4000-8000-000000000000")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "DOCUMENT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()