"""
Tests for ChromaService with focus on persistence and retrieval.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from backend.app.services.chroma_service import ChromaService
from backend.app.services.embeddings import EmbeddingsService


class TestChromaService:
    """Test suite for ChromaDB service."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary directory for ChromaDB."""
        temp_dir = tempfile.mkdtemp(prefix="chroma_test_")
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def embeddings_service(self):
        """Create embeddings service."""
        return EmbeddingsService()

    @pytest.fixture
    def service(self, temp_db_path, embeddings_service):
        """Create a ChromaService with temporary database."""
        return ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)

    def test_initialization(self, service, temp_db_path):
        """Test service initializes correctly."""
        assert service.db_path == temp_db_path
        assert service.collection.name == "documents"
        assert Path(temp_db_path).exists()

    def test_add_single_chunk(self, service):
        """Test adding a single chunk."""
        chunks = [
            {
                "text": "This is the first chunk of text.",
                "page": 1,
                "file_name": "test.pdf",
                "chunk_index": 0,
            }
        ]

        ids = service.add_chunks(chunks)

        assert len(ids) == 1
        assert ids[0] == "test.pdf_1_0"

        # Verify in collection
        stats = service.get_collection_stats()
        assert stats["document_count"] == 1

    def test_add_multiple_chunks(self, service):
        """Test adding multiple chunks at once."""
        chunks = [
            {
                "text": f"Chunk {i} content.",
                "page": i // 2 + 1,
                "file_name": "doc.pdf",
                "chunk_index": i,
            }
            for i in range(5)
        ]

        ids = service.add_chunks(chunks)

        assert len(ids) == 5
        stats = service.get_collection_stats()
        assert stats["document_count"] == 5

    def test_query_basic(self, service):
        """Test basic semantic search query."""
        # Add some chunks
        chunks = [
            {
                "text": "The quick brown fox jumps over the lazy dog.",
                "page": 1,
                "file_name": "animals.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Python is a popular programming language.",
                "page": 2,
                "file_name": "programming.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Machine learning uses neural networks.",
                "page": 3,
                "file_name": "ml.pdf",
                "chunk_index": 0,
            },
        ]

        service.add_chunks(chunks)

        # Query for something about animals
        results = service.query("fox and animals", n_results=2)

        assert "ids" in results
        assert "documents" in results
        assert "metadatas" in results
        assert "distances" in results

        # First result should be most similar
        assert len(results["ids"]) <= 2
        assert len(results["documents"]) <= 2

    def test_query_with_metadata_filter(self, service):
        """Test query with metadata filtering."""
        chunks = [
            {
                "text": "Chapter 1: Introduction",
                "page": 1,
                "file_name": "book_a.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Chapter 1: Getting Started",
                "page": 1,
                "file_name": "book_b.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Chapter 2: Advanced Topics",
                "page": 2,
                "file_name": "book_a.pdf",
                "chunk_index": 1,
            },
        ]

        service.add_chunks(chunks)

        # Query only book_a.pdf
        results = service.query(
            "Introduction",
            n_results=5,
            where={"file_name": {"$eq": "book_a.pdf"}},
        )

        # All results should be from book_a.pdf
        # metadatas is a list of lists in ChromaDB 1.5.9
        metadatas_list = results["metadatas"][0] if results["metadatas"] else []
        for meta in metadatas_list:
            assert meta["file_name"] == "book_a.pdf"

    def test_collection_stats(self, service):
        """Test collection statistics."""
        chunks = [
            {
                "text": f"Text {i}",
                "page": 1,
                "file_name": "doc.pdf",
                "chunk_index": i,
            }
            for i in range(3)
        ]

        service.add_chunks(chunks)
        stats = service.get_collection_stats()

        assert stats["collection_name"] == "documents"
        assert stats["document_count"] == 3
        assert stats["db_path"] == service.db_path

    def test_metadata_preserved(self, service):
        """Test that metadata is correctly stored and retrieved."""
        chunks = [
            {
                "text": "Sample text for metadata test.",
                "page": 42,
                "file_name": "important_doc.pdf",
                "chunk_index": 7,
            }
        ]

        service.add_chunks(chunks)
        results = service.query("metadata test", n_results=1)

        # metadatas is a list of lists in ChromaDB 1.5.9
        meta = results["metadatas"][0][0]
        assert meta["page"] == 42
        assert meta["file_name"] == "important_doc.pdf"
        assert meta["chunk_index"] == 7

    def test_delete_all(self, service):
        """Test deleting all documents."""
        chunks = [
            {
                "text": f"Chunk {i}",
                "page": 1,
                "file_name": "doc.pdf",
                "chunk_index": i,
            }
            for i in range(5)
        ]

        service.add_chunks(chunks)
        assert service.get_collection_stats()["document_count"] == 5

        service.delete_all()
        assert service.get_collection_stats()["document_count"] == 0

    def test_persistence_across_instances(self, temp_db_path, embeddings_service):
        """
        CRITICAL TEST: Verify data persists when reopening database.
        This tests the core requirement for RAG systems.
        """
        # Create first instance and add data
        service1 = ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)

        chunks = [
            {
                "text": "This is persistent data that should survive restart.",
                "page": 1,
                "file_name": "persistent.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Second chunk that should also persist.",
                "page": 2,
                "file_name": "persistent.pdf",
                "chunk_index": 1,
            },
        ]

        ids_before = service1.add_chunks(chunks)
        count_before = service1.get_collection_stats()["document_count"]

        # Persist and close first instance (auto-persists in ChromaDB 1.5.9+)
        service1.persist()
        del service1

        # Create NEW instance with same database path
        service2 = ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)

        # Verify data is still there
        count_after = service2.get_collection_stats()["document_count"]
        assert count_after == count_before, (
            f"Data was lost! Before: {count_before}, After: {count_after}"
        )

        # Verify we can query the persisted data
        results = service2.query("persistent data", n_results=5)
        assert len(results["ids"][0]) > 0, "Cannot query persisted data"

        # Verify metadata is intact
        meta = results["metadatas"][0][0]
        assert meta["file_name"] == "persistent.pdf"

    def test_persistence_with_multiple_files(self, temp_db_path, embeddings_service):
        """Test persistence with documents from multiple files."""
        service1 = ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)

        # Add chunks from different files
        chunks = [
            {
                "text": "Content from file A",
                "page": 1,
                "file_name": "file_a.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Content from file B",
                "page": 1,
                "file_name": "file_b.pdf",
                "chunk_index": 0,
            },
            {
                "text": "More content from file A",
                "page": 2,
                "file_name": "file_a.pdf",
                "chunk_index": 1,
            },
        ]

        service1.add_chunks(chunks)
        service1.persist()
        del service1

        # Reopen and verify
        service2 = ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)
        stats = service2.get_collection_stats()

        assert stats["document_count"] == 3

        # Verify filtering by file still works
        results = service2.query(
            "content",
            n_results=10,
            where={"file_name": {"$eq": "file_a.pdf"}},
        )

        # All results should be from file_a.pdf
        # metadatas is a list of lists in ChromaDB 1.5.9
        file_names = [meta["file_name"] for meta in results["metadatas"][0]]
        assert all(name == "file_a.pdf" for name in file_names)

    def test_empty_add_chunks(self, service):
        """Test adding empty chunk list."""
        ids = service.add_chunks([])
        assert ids == []
        assert service.get_collection_stats()["document_count"] == 0

    def test_query_returns_correct_fields(self, service):
        """Test that query returns all expected fields."""
        chunks = [
            {
                "text": "Sample query test content.",
                "page": 1,
                "file_name": "test.pdf",
                "chunk_index": 0,
            }
        ]

        service.add_chunks(chunks)
        results = service.query("query test", n_results=1)

        # Verify required fields
        assert "ids" in results
        assert "documents" in results
        assert "metadatas" in results
        assert "distances" in results
        assert "query_embedding" in results

        # Verify query_embedding is correct dimension
        assert len(results["query_embedding"]) == 768


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
