"""
Tests for EmbeddingsService using Ollama's nomic-embed-text model.
"""

import pytest
import numpy as np
from backend.app.services.embeddings import EmbeddingsService
from backend.app.config import Config


class TestEmbeddingsService:
    """Test suite for embeddings service."""

    @pytest.fixture
    def service(self):
        """Create an embeddings service instance."""
        return EmbeddingsService()

    def test_initialization(self, service):
        """Test service initializes with correct config."""
        assert service.model == Config.EMBEDDING_MODEL
        assert service.base_url == Config.OLLAMA_BASE_URL
        assert service.get_embedding_dimension() == 768

    def test_embed_single_text(self, service):
        """Test embedding a single text string."""
        text = "This is a test sentence."
        embedding = service.embed(text)

        # Should return 1D array of dimension 768
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (768,)
        assert embedding.dtype == np.float32

    def test_embed_multiple_texts(self, service):
        """Test embedding multiple texts at once."""
        texts = [
            "This is the first sentence.",
            "This is the second sentence.",
            "This is the third sentence.",
        ]
        embeddings = service.embed(texts)

        # Should return 2D array: (3, 768)
        assert isinstance(embeddings, np.ndarray)
        assert embeddings.shape == (3, 768)
        assert embeddings.dtype == np.float32

    def test_embeddings_are_normalized(self, service):
        """Test that embeddings are reasonable vectors (not NaN/Inf)."""
        text = "The quick brown fox jumps over the lazy dog."
        embedding = service.embed(text)

        # Check for NaN or Inf
        assert not np.isnan(embedding).any(), "Embedding contains NaN"
        assert not np.isinf(embedding).any(), "Embedding contains Inf"

        # Check reasonable magnitude (embeddings should be normalized)
        norm = np.linalg.norm(embedding)
        assert 0.5 < norm < 2.0, f"Embedding norm {norm} seems unusual"

    def test_same_text_produces_same_embedding(self, service):
        """Test determinism: same input = same output."""
        text = "Determinism test sentence"
        embedding1 = service.embed(text)
        embedding2 = service.embed(text)

        np.testing.assert_array_equal(embedding1, embedding2)

    def test_different_texts_produce_different_embeddings(self, service):
        """Test that different texts produce different embeddings."""
        text1 = "The cat sat on the mat."
        text2 = "The dog ran in the park."

        embedding1 = service.embed(text1)
        embedding2 = service.embed(text2)

        # Embeddings should be different (extremely unlikely to be identical)
        assert not np.allclose(embedding1, embedding2)

    def test_similar_texts_have_similar_embeddings(self, service):
        """Test that semantically similar texts have similar embeddings."""
        text1 = "The cat is sleeping on the bed."
        text2 = "A cat is napping on the bed."
        text3 = "The rocket launched into space."

        emb1 = service.embed(text1)
        emb2 = service.embed(text2)
        emb3 = service.embed(text3)

        # Compute cosine similarities
        def cosine_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_similar = cosine_sim(emb1, emb2)
        sim_different = cosine_sim(emb1, emb3)

        # Similar texts should have higher similarity than different texts
        assert sim_similar > sim_different, (
            f"Similar texts ({sim_similar}) should be more similar "
            f"than different texts ({sim_different})"
        )

    def test_caching_works(self, service):
        """Test that embeddings are cached."""
        text = "Cache test sentence"

        # First call: should call Ollama API
        emb1 = service.embed(text)
        cache_size_1 = len(service._cache)

        # Second call: should use cache
        emb2 = service.embed(text)
        cache_size_2 = len(service._cache)

        # Cache size shouldn't grow (same text)
        assert cache_size_1 == cache_size_2
        np.testing.assert_array_equal(emb1, emb2)

    def test_cache_clear(self, service):
        """Test cache clearing."""
        text = "Clear cache test"
        service.embed(text)

        assert len(service._cache) > 0
        service.clear_cache()
        assert len(service._cache) == 0

    def test_embedding_dimension_correct(self, service):
        """Verify embedding dimension is exactly 768."""
        texts = [
            "Short.",
            "A much longer text with more words and information content.",
            "Medium length text here.",
        ]

        for text in texts:
            emb = service.embed(text)
            assert emb.shape == (768,), f"Expected (768,), got {emb.shape}"

    def test_batch_vs_individual_consistency(self, service):
        """Test that batch embedding matches individual embeddings."""
        texts = ["First text.", "Second text.", "Third text."]

        # Batch embedding
        batch_embeddings = service.embed(texts)

        # Individual embeddings
        individual_embeddings = np.array([service.embed(t) for t in texts])

        # They should be identical (or very close due to floating point)
        np.testing.assert_array_almost_equal(batch_embeddings, individual_embeddings)

    def test_empty_text_handling(self, service):
        """Test handling of empty or whitespace-only text."""
        # Empty string should still return embedding
        embedding = service.embed("")
        assert embedding.shape == (768,)
        assert not np.isnan(embedding).any()

        # Whitespace should work too
        embedding = service.embed("   ")
        assert embedding.shape == (768,)
        assert not np.isnan(embedding).any()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
