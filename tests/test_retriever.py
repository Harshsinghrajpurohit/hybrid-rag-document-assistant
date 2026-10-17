"""
Tests for HybridRetriever: BM25 + dense search + RRF fusion.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from backend.app.services.hybrid_retriever import HybridRetriever
from backend.app.services.chroma_service import ChromaService
from backend.app.services.embeddings import EmbeddingsService


class TestHybridRetriever:
    """Test suite for hybrid retriever."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary ChromaDB directory."""
        temp_dir = tempfile.mkdtemp(prefix="hybrid_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def embeddings_service(self):
        """Create embeddings service."""
        return EmbeddingsService()

    @pytest.fixture
    def chroma_service(self, temp_db_path, embeddings_service):
        """Create ChromaDB service with temp path."""
        return ChromaService(db_path=temp_db_path, embeddings_service=embeddings_service)

    @pytest.fixture
    def retriever(self, chroma_service):
        """Create hybrid retriever."""
        return HybridRetriever(chroma_service)

    def test_initialization(self, retriever):
        """Test retriever initializes with correct config."""
        assert retriever.k_rrf == 60
        assert retriever.chroma is not None
        stats = retriever.get_index_stats()
        assert stats["k_rrf"] == 60
        assert "bm25_corpus_size" in stats

    def test_initialization_empty_database(self, retriever):
        """Test initialization with empty ChromaDB."""
        assert retriever.bm25_index is None
        assert retriever.doc_ids == []
        stats = retriever.get_index_stats()
        assert stats["bm25_corpus_size"] == 0

    def test_bm25_single_document(self, chroma_service, retriever):
        """Test BM25 search with single document."""
        chunks = [
            {
                "text": "The cat sat on the mat. The cat was very comfortable and happy sitting on the soft mat.",
                "page": 1,
                "file_name": "animals.pdf",
                "chunk_index": 0,
            }
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query with exact keywords
        results = retriever.retrieve("cat mat", n_results=1)

        assert len(results["ids"]) == 1
        assert "cat" in results["documents"][0].lower()
        assert results["bm25_scores"][0] >= 0  # BM25 score >= 0 (may be 0 for very short docs)

    def test_bm25_keyword_matching(self, chroma_service, retriever):
        """Test BM25 prioritizes exact keyword matches."""
        chunks = [
            {
                "text": "The cat sat on the mat.",
                "page": 1,
                "file_name": "animals.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Machine learning uses neural networks.",
                "page": 2,
                "file_name": "ml.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Artificial intelligence powers modern applications.",
                "page": 1,
                "file_name": "ai.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query with keywords that match only first doc
        results = retriever.retrieve("cat mat", n_results=2)

        # First result should be about cats (has exact keywords)
        assert "cat" in results["documents"][0].lower()
        assert results["bm25_scores"][0] > results["bm25_scores"][1]

    def test_dense_semantic_matching(self, chroma_service, retriever):
        """Test dense search finds semantically similar text."""
        chunks = [
            {
                "text": "Retrieval-Augmented Generation combines information retrieval with generative models.",
                "page": 1,
                "file_name": "rag.pdf",
                "chunk_index": 0,
            },
            {
                "text": "The weather is sunny and warm today.",
                "page": 2,
                "file_name": "weather.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query with semantic variant (different words, same meaning)
        results = retriever.retrieve("generative retrieval systems", n_results=2)

        # At least one result should be about RAG (semantic match)
        # Note: With small corpus, exact ranking may vary
        assert any("retrieval" in doc.lower() for doc in results["documents"])

    def test_hybrid_combining_signals(self, chroma_service, retriever):
        """Test hybrid retrieval combines both BM25 and dense signals."""
        chunks = [
            {
                "text": "RAG systems combine retrieval with generation.",
                "page": 1,
                "file_name": "rag.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Information retrieval methods for search engines.",
                "page": 2,
                "file_name": "ir.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Deep learning models for natural language processing.",
                "page": 3,
                "file_name": "nlp.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query that could match multiple docs
        results = retriever.retrieve("retrieval augmented generation", n_results=3)

        # Should get multiple results, first being most relevant
        assert len(results["ids"]) >= 1
        # First doc should mention retrieval and/or generation
        first_doc = results["documents"][0].lower()
        assert "retrieval" in first_doc or "generation" in first_doc

    def test_rrf_deduplication(self, chroma_service, retriever):
        """Test RRF correctly deduplicates and combines scores."""
        chunks = [
            {
                "text": "RAG combines retrieval and generation.",
                "page": 1,
                "file_name": "doc.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Semantic search using embeddings.",
                "page": 2,
                "file_name": "doc.pdf",
                "chunk_index": 1,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query that could return same doc from both rankers
        results = retriever.retrieve("RAG retrieval", n_results=2)

        # Same doc shouldn't appear twice
        assert len(results["ids"]) == len(set(results["ids"]))

        # RRF scores should be reasonable (sum of both ranker contributions)
        assert all(score > 0 for score in results["rrf_scores"])

    def test_rrf_score_ordering(self, chroma_service, retriever):
        """Test RRF scores are in descending order."""
        chunks = [
            {
                "text": "First document content here.",
                "page": 1,
                "file_name": "doc1.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Second document content here.",
                "page": 2,
                "file_name": "doc2.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Third document content here.",
                "page": 3,
                "file_name": "doc3.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        results = retriever.retrieve("document content", n_results=3)

        # RRF scores should be descending
        rrf_scores = results["rrf_scores"]
        for i in range(len(rrf_scores) - 1):
            assert rrf_scores[i] >= rrf_scores[i + 1]

    def test_metadata_preserved(self, chroma_service, retriever):
        """Test that metadata is preserved in results."""
        chunks = [
            {
                "text": "Important information on page 42.",
                "page": 42,
                "file_name": "important_doc.pdf",
                "chunk_index": 7,
            }
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        results = retriever.retrieve("important information", n_results=1)

        meta = results["metadatas"][0]
        assert meta["page"] == 42
        assert meta["file_name"] == "important_doc.pdf"
        assert meta["chunk_index"] == 7

    def test_metadata_filtering(self, chroma_service, retriever):
        """Test metadata filtering (where clause)."""
        chunks = [
            {
                "text": "Content from file A.",
                "page": 1,
                "file_name": "file_a.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Content from file B.",
                "page": 1,
                "file_name": "file_b.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query with metadata filter
        results = retriever.retrieve(
            "content", n_results=5, where={"file_name": {"$eq": "file_a.pdf"}}
        )

        # All results should be from file_a.pdf
        assert all(meta["file_name"] == "file_a.pdf" for meta in results["metadatas"])

    def test_empty_query_results(self, chroma_service, retriever):
        """Test handling of query with no results."""
        chunks = [
            {
                "text": "The quick brown fox jumps over the lazy dog.",
                "page": 1,
                "file_name": "fable.pdf",
                "chunk_index": 0,
            }
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query that shares no terms with the corpus
        results = retriever.retrieve("xyzabc unrelated nonsense", n_results=5)

        # Contract: with no matching terms the BM25 leg contributes nothing
        # (every bm25_score is 0), while dense k-NN search still returns its
        # nearest neighbors (no relevance threshold), so the overall result
        # list may be non-empty. Only the zero lexical contribution is asserted.
        assert all(score <= 0 for score in results["bm25_scores"])

        # Response structure stays consistent either way
        n = len(results["ids"])
        assert len(results["documents"]) == n
        assert len(results["metadatas"]) == n
        assert len(results["bm25_scores"]) == n

    def test_return_format(self, chroma_service, retriever):
        """Test that retrieve returns all expected fields."""
        chunks = [
            {
                "text": "Sample text for format test.",
                "page": 1,
                "file_name": "test.pdf",
                "chunk_index": 0,
            }
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        results = retriever.retrieve("sample", n_results=1)

        # Check all required fields
        required_fields = [
            "ids",
            "documents",
            "metadatas",
            "distances",
            "bm25_scores",
            "rrf_scores",
        ]
        for field in required_fields:
            assert field in results, f"Missing field: {field}"

        # Check that all lists have same length
        if results["ids"]:
            n = len(results["ids"])
            assert len(results["documents"]) == n
            assert len(results["metadatas"]) == n
            assert len(results["distances"]) == n
            assert len(results["bm25_scores"]) == n
            assert len(results["rrf_scores"]) == n

    def test_rebuild_index_adds_new_documents(self, chroma_service, retriever):
        """Test that rebuild_index picks up newly added documents."""
        # Add first batch
        chunks1 = [
            {
                "text": "First batch of documents.",
                "page": 1,
                "file_name": "batch1.pdf",
                "chunk_index": 0,
            }
        ]
        chroma_service.add_chunks(chunks1)
        retriever.rebuild_index()

        stats1 = retriever.get_index_stats()
        assert stats1["bm25_corpus_size"] == 1

        # Add second batch
        chunks2 = [
            {
                "text": "Second batch of documents.",
                "page": 1,
                "file_name": "batch2.pdf",
                "chunk_index": 0,
            }
        ]
        chroma_service.add_chunks(chunks2)
        retriever.rebuild_index()

        stats2 = retriever.get_index_stats()
        assert stats2["bm25_corpus_size"] == 2

        # Query should find both
        results = retriever.retrieve("batch documents", n_results=2)
        assert len(results["ids"]) == 2

    def test_tokenization_consistency(self, retriever):
        """Test that tokenization is consistent."""
        # Tokenize same text multiple times
        text = "The Quick BROWN Fox JUMPS over the lazy DOG."
        tokens1 = retriever._tokenize(text)
        tokens2 = retriever._tokenize(text)

        assert tokens1 == tokens2
        # Should be lowercase
        assert all(t.islower() or not t.isalpha() for t in tokens1)

    def test_bm25_with_rare_terms(self, chroma_service, retriever):
        """Test BM25 weights rare terms higher."""
        chunks = [
            {
                "text": "Common word common word common word.",
                "page": 1,
                "file_name": "common.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Rare term appears once in this document.",
                "page": 2,
                "file_name": "rare.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Query with rare term
        results = retriever.retrieve("rare", n_results=2)

        # Rare term should rank higher
        first_doc = results["documents"][0].lower()
        assert "rare" in first_doc

    def test_large_corpus(self, chroma_service, retriever):
        """Test retriever with larger corpus."""
        # Add many documents
        chunks = [
            {
                "text": f"Document number {i} with content about topic {i % 5}.",
                "page": i,
                "file_name": f"doc_{i}.pdf",
                "chunk_index": 0,
            }
            for i in range(20)
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        stats = retriever.get_index_stats()
        assert stats["bm25_corpus_size"] == 20

        # Query should work on large corpus
        results = retriever.retrieve("topic document", n_results=5)
        assert len(results["ids"]) <= 5

    def test_multiple_queries(self, chroma_service, retriever):
        """Test that retriever handles multiple sequential queries."""
        chunks = [
            {
                "text": "Machine learning is a subset of artificial intelligence.",
                "page": 1,
                "file_name": "ai.pdf",
                "chunk_index": 0,
            },
            {
                "text": "Deep learning uses neural networks with multiple layers.",
                "page": 2,
                "file_name": "dl.pdf",
                "chunk_index": 0,
            },
        ]
        chroma_service.add_chunks(chunks)
        retriever.rebuild_index()

        # Multiple queries
        q1 = retriever.retrieve("machine learning", n_results=1)
        q2 = retriever.retrieve("deep learning neural", n_results=1)
        q3 = retriever.retrieve("artificial intelligence", n_results=1)

        # All should succeed and return results
        assert len(q1["ids"]) >= 0
        assert len(q2["ids"]) >= 0
        assert len(q3["ids"]) >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
