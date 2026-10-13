"""
End-to-end integration test for the complete RAG pipeline.
Tests the full flow: PDF extraction → embeddings → retrieval → answer generation.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import json

from backend.app.services.embeddings import EmbeddingsService
from backend.app.services.chroma_service import ChromaService
from backend.app.services.hybrid_retriever import HybridRetriever
from backend.app.services.answer_generator import AnswerGenerator


@pytest.fixture
def temp_db_dir():
    """Create temporary directory for ChromaDB."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup - ChromaDB may hold locks, so use ignore_errors
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_embeddings_service():
    """Mock embeddings service that returns deterministic embeddings."""
    service = Mock(spec=EmbeddingsService)

    # Return deterministic 768-dim embeddings based on text hash
    def mock_embed(text):
        import numpy as np

        # Handle both single strings and lists
        if isinstance(text, str):
            # Single text
            text_hash = hash(text) % 1000
            np.random.seed(text_hash)
            embedding = np.random.randn(768).astype(np.float32)
            return embedding / np.linalg.norm(embedding)  # Normalize
        elif isinstance(text, list):
            # List of texts
            embeddings = []
            for t in text:
                text_hash = hash(t) % 1000
                np.random.seed(text_hash)
                embedding = np.random.randn(768).astype(np.float32)
                embedding = embedding / np.linalg.norm(embedding)
                embeddings.append(embedding)
            return np.array(embeddings)
        else:
            raise TypeError(f"Expected str or list, got {type(text)}")

    service.embed = Mock(side_effect=mock_embed)
    return service


@pytest.fixture
def sample_pdf_path():
    """Create a temporary sample PDF for testing."""
    # For this test, we'll create a mock PDF processor that returns chunks
    # In a real scenario, this would be an actual PDF file
    pass


class TestE2ERAGPipeline:
    """End-to-end tests for complete RAG pipeline."""

    def test_e2e_pdf_to_answer(self, temp_db_dir, mock_embeddings_service):
        """
        Test complete pipeline: chunks → embeddings → retrieval → answer.

        This test simulates the full RAG flow without requiring actual PDFs
        or Ollama, using mocks for file I/O and LLM calls.
        """

        # =====================================================================
        # Phase 1: PDF Extraction and Chunking
        # =====================================================================
        # In this test, we simulate PDF processor output
        pdf_chunks = [
            {
                "text": "Machine learning is a subset of artificial intelligence that focuses on enabling computers to learn from data.",
                "page": 1,
                "file_name": "ai_basics.pdf",
                "chunk_index": 0
            },
            {
                "text": "Deep learning involves neural networks with multiple layers that can learn hierarchical representations.",
                "page": 2,
                "file_name": "ai_basics.pdf",
                "chunk_index": 1
            },
            {
                "text": "Supervised learning requires labeled training data where each input has a corresponding output.",
                "page": 3,
                "file_name": "ai_basics.pdf",
                "chunk_index": 2
            },
            {
                "text": "Unsupervised learning finds patterns in data without labels, including clustering and dimensionality reduction.",
                "page": 4,
                "file_name": "ai_basics.pdf",
                "chunk_index": 3
            },
            {
                "text": "Neural networks are composed of interconnected layers of nodes that process information hierarchically.",
                "page": 5,
                "file_name": "neural_networks.pdf",
                "chunk_index": 0
            },
        ]

        # =====================================================================
        # Phase 2: Embeddings and ChromaDB Storage
        # =====================================================================
        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )

        # Add chunks to ChromaDB
        added_ids = chroma_service.add_chunks(pdf_chunks)
        assert len(added_ids) == 5, "Should add all 5 chunks"

        # Verify chunks are stored
        stored_docs = chroma_service.collection.get(include=["documents", "metadatas"])
        assert len(stored_docs["documents"]) == 5

        # =====================================================================
        # Phase 3: Hybrid Retrieval (BM25 + Dense + RRF)
        # =====================================================================
        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        # Test retrieval
        query = "What is machine learning?"
        results = retriever.retrieve(query, n_results=3)

        assert len(results["documents"]) > 0, "Should retrieve results"
        assert len(results["documents"]) <= 3, "Should respect k=3"
        assert "machine learning" in results["documents"][0].lower() or \
               "learning" in results["documents"][0].lower(), \
               "First result should be relevant to query"

        # =====================================================================
        # Phase 4: Answer Generation from Retrieved Passages
        # =====================================================================
        answer_generator = AnswerGenerator(
            base_url="http://localhost:11434",
            model="qwen3:4b-instruct",
        )

        # Mock Ollama response
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "response": (
                    "Machine learning is a subset of artificial intelligence that focuses on "
                    "enabling computers to learn from data without being explicitly programmed."
                ),
                "eval_count": 30,
                "prompt_eval_count": 120,
            }
            mock_post.return_value = mock_response

            # Generate answer
            answer = answer_generator.generate(
                query=query,
                retriever_results=results,
                max_sources=3,
            )

        # =====================================================================
        # Verify Complete Response
        # =====================================================================
        assert answer["answer"], "Should have generated answer"
        assert len(answer["sources"]) > 0, "Should have sources"
        assert answer["confidence"] > 0, "Should have confidence score"
        assert answer["tokens_used"] > 0, "Should count tokens"

        # Verify sources are from our documents
        for source in answer["sources"]:
            assert source["file"] in {"ai_basics.pdf", "neural_networks.pdf"}
            assert source["page"] >= 1
            assert len(source["excerpt"]) > 0

    def test_e2e_multiple_documents(self, temp_db_dir, mock_embeddings_service):
        """Test retrieval and answer generation with multiple documents."""

        # Create chunks from multiple documents
        chunks = []
        documents = [
            ("biology_101.pdf", [
                "DNA is the molecule that carries genetic information.",
                "Photosynthesis is the process by which plants convert light into chemical energy.",
                "Cells are the basic building blocks of all living organisms.",
            ]),
            ("chemistry_101.pdf", [
                "Chemical bonds hold atoms together in molecules.",
                "The periodic table organizes elements by atomic number.",
                "Reactions involve the rearrangement of atoms and electrons.",
            ]),
        ]

        chunk_index = 0
        for doc_name, texts in documents:
            for page, text in enumerate(texts, start=1):
                chunks.append({
                    "text": text,
                    "page": page,
                    "file_name": doc_name,
                    "chunk_index": chunk_index
                })
                chunk_index += 1

        # Store in ChromaDB
        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )
        chroma_service.add_chunks(chunks)

        # Retrieve relevant passages
        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        results = retriever.retrieve("What is photosynthesis?", n_results=2)
        assert len(results["documents"]) > 0

        # Generate answer
        answer_gen = AnswerGenerator()
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "response": "Photosynthesis is the process by which plants convert light energy into chemical energy.",
                "eval_count": 25,
                "prompt_eval_count": 110,
            }
            mock_post.return_value = mock_response

            answer = answer_gen.generate(
                query="What is photosynthesis?",
                retriever_results=results,
            )

        assert "photosynthesis" in answer["answer"].lower()
        assert any(s["file"] == "biology_101.pdf" for s in answer["sources"])

    def test_e2e_empty_retrieval_graceful_fallback(self, temp_db_dir, mock_embeddings_service):
        """Test that pipeline handles empty retrievals gracefully."""

        # Create empty database
        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )

        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        # Try to retrieve from empty database
        results = retriever.retrieve("What is this?", n_results=5)

        # Results should be empty but structured
        assert results["documents"] == []
        assert results["ids"] == []

        # Answer generator should handle gracefully
        answer_gen = AnswerGenerator()
        answer = answer_gen.generate(
            query="What is this?",
            retriever_results=results,
        )

        # Should return "insufficient context" response
        assert "don't have enough context" in answer["answer"].lower()
        assert answer["sources"] == []
        assert answer["confidence"] == 0.0

    def test_e2e_metadata_preservation(self, temp_db_dir, mock_embeddings_service):
        """Test that metadata is preserved through entire pipeline."""

        chunks = [
            {
                "text": "Important information on page 42.",
                "page": 42,
                "file_name": "important_doc.pdf",
                "chunk_index": 7
            }
        ]

        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )
        chroma_service.add_chunks(chunks)

        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        results = retriever.retrieve("Important information", n_results=1)

        # Check metadata is preserved
        assert results["metadatas"][0]["page"] == 42
        assert results["metadatas"][0]["file_name"] == "important_doc.pdf"
        assert results["metadatas"][0]["chunk_index"] == 7

        # Verify metadata reaches answer generator
        answer_gen = AnswerGenerator()
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "response": "Answer",
                "eval_count": 10,
                "prompt_eval_count": 90,
            }
            mock_post.return_value = mock_response

            answer = answer_gen.generate(
                query="Important information",
                retriever_results=results,
            )

        # Source should include correct page and file
        assert answer["sources"][0]["page"] == 42
        assert answer["sources"][0]["file"] == "important_doc.pdf"

    def test_e2e_response_completeness(self, temp_db_dir, mock_embeddings_service):
        """Test that each stage produces complete, valid responses."""

        chunks = [
            {
                "text": "Test information for verification.",
                "page": 1,
                "file_name": "test.pdf",
                "chunk_index": 0
            }
        ]

        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )
        chroma_service.add_chunks(chunks)

        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        results = retriever.retrieve("Test information", n_results=5)

        # Phase 3 response should have all required fields
        assert "ids" in results
        assert "documents" in results
        assert "metadatas" in results
        # The retriever returns flat structure: rrf_scores, bm25_scores, distances
        assert "rrf_scores" in results or "scores" in results
        assert len(results["documents"]) > 0, "Should retrieve results"

        # Phase 4 response
        answer_gen = AnswerGenerator()
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "response": "Test answer",
                "eval_count": 5,
                "prompt_eval_count": 85,
            }
            mock_post.return_value = mock_response

            answer = answer_gen.generate(
                query="Test?",
                retriever_results=results,
            )

        # Phase 4 response should have all required fields
        required_fields = {"answer", "sources", "confidence", "tokens_used", "model", "timestamp"}
        assert set(answer.keys()) == required_fields

        # All sources should have required fields
        for source in answer["sources"]:
            assert "page" in source
            assert "file" in source
            assert "excerpt" in source
            assert "score" in source


class TestIntegrationPhases:
    """Integration tests between specific phases."""

    def test_phase_2_to_phase_3_integration(self, temp_db_dir, mock_embeddings_service):
        """Test integration: Phase 2 (storage) → Phase 3 (retrieval)."""

        chunks = [
            {
                "text": "Data science combines statistics and programming.",
                "page": 1,
                "file_name": "ds.pdf",
                "chunk_index": 0
            },
            {
                "text": "Statistics helps analyze patterns in data.",
                "page": 2,
                "file_name": "ds.pdf",
                "chunk_index": 1
            },
        ]

        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )
        chroma_service.add_chunks(chunks)

        # Phase 3 should work with Phase 2 storage
        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        results = retriever.retrieve("Statistics", n_results=2)
        assert len(results["documents"]) > 0
        assert "statistics" in " ".join(results["documents"]).lower()

    def test_phase_3_to_phase_4_integration(self, temp_db_dir, mock_embeddings_service):
        """Test integration: Phase 3 (retrieval) → Phase 4 (answer generation)."""

        chunks = [
            {
                "text": "Quantum computing uses quantum bits (qubits) instead of classical bits.",
                "page": 1,
                "file_name": "quantum.pdf",
                "chunk_index": 0
            }
        ]

        chroma_service = ChromaService(
            db_path=temp_db_dir,
            embeddings_service=mock_embeddings_service,
        )
        chroma_service.add_chunks(chunks)

        retriever = HybridRetriever(
            chroma_service=chroma_service,
            embeddings_service=mock_embeddings_service,
        )

        results = retriever.retrieve("Quantum computing", n_results=1)

        # Phase 4 should process Phase 3 output
        answer_gen = AnswerGenerator()
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "response": "Quantum computing uses qubits for computation.",
                "eval_count": 15,
                "prompt_eval_count": 95,
            }
            mock_post.return_value = mock_response

            answer = answer_gen.generate(
                query="What is quantum computing?",
                retriever_results=results,
            )

        assert "quantum" in answer["answer"].lower()
