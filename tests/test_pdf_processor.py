"""
Unit tests for PDF extraction and chunking.
"""

import pytest
import tempfile
from pathlib import Path
from backend.app.services.pdf_processor import (
    extract_pdf_text,
    split_into_chunks,
    process_pdf
)


class TestSplitIntoChunks:
    """Test text chunking logic."""

    def test_basic_split(self):
        """Test that text is split into chunks."""
        text = "Hello world. " * 100  # ~1300 characters
        chunks = split_into_chunks(text, chunk_size=200, chunk_overlap=50)

        assert len(chunks) > 1, "Should split into multiple chunks"
        assert all(isinstance(chunk, str) for chunk in chunks)
        assert all(len(chunk) <= 300 for chunk in chunks), "Chunks should respect size limit"

    def test_overlap_preserved(self):
        """Test that overlap creates redundancy between chunks."""
        text = "The quick brown fox jumps over the lazy dog. " * 20
        chunks = split_into_chunks(text, chunk_size=100, chunk_overlap=30)

        # Check that consecutive chunks have overlap (some repeated words)
        if len(chunks) >= 2:
            chunk1_words = set(chunks[0].split())
            chunk2_words = set(chunks[1].split())
            overlap = chunk1_words & chunk2_words
            assert len(overlap) > 0, "Consecutive chunks should share words (overlap)"

    def test_empty_text(self):
        """Test handling of empty text."""
        chunks = split_into_chunks("", chunk_size=512)
        # LangChain's splitter returns empty list for empty text (correct behavior)
        assert chunks == [], "Empty text should return empty list"

    def test_small_text(self):
        """Test text smaller than chunk size."""
        text = "Hello world"
        chunks = split_into_chunks(text, chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0] == text


class TestPDFExtraction:
    """Test PDF extraction (requires sample PDF)."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Create a simple test PDF using reportlab if available."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter

            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as tmp:
                c = canvas.Canvas(tmp.name, pagesize=letter)

                # Page 1
                c.drawString(100, 750, "Page 1: Introduction")
                c.drawString(100, 730, "This is the first page of the test PDF.")
                c.drawString(100, 710, "It contains some sample text.")

                # Page 2
                c.showPage()
                c.drawString(100, 750, "Page 2: Details")
                c.drawString(100, 730, "This is the second page.")
                c.drawString(100, 710, "More sample text here.")

                c.save()
                yield tmp.name

                # Cleanup
                Path(tmp.name).unlink()
        except ImportError:
            pytest.skip("reportlab not installed; skipping PDF extraction test")

    def test_extract_pdf_text(self, sample_pdf_path):
        """Test extracting text from PDF."""
        pages, file_name = extract_pdf_text(sample_pdf_path)

        assert len(pages) > 0, "Should extract at least one page"
        assert all("text" in p for p in pages), "Each page should have text"
        assert all("page" in p for p in pages), "Each page should have page number"
        assert all("file_name" in p for p in pages), "Each page should have file_name"
        assert file_name.endswith(".pdf"), "File name should end with .pdf"

    def test_page_numbers_correct(self, sample_pdf_path):
        """Test that page numbers are correctly preserved."""
        pages, _ = extract_pdf_text(sample_pdf_path)
        page_numbers = [p["page"] for p in pages]

        # Page numbers should be 1-indexed and sequential
        assert 1 in page_numbers, "Should have page 1"
        assert page_numbers == sorted(page_numbers), "Page numbers should be in order"

    def test_extract_nonexistent_file(self):
        """Test error handling for missing files."""
        with pytest.raises(FileNotFoundError):
            extract_pdf_text("/nonexistent/path/to/file.pdf")

    def test_extract_invalid_pdf(self):
        """Test error handling for invalid PDF."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as tmp:
            tmp.write("This is not a valid PDF file")
            tmp_path = tmp.name
            # File is closed when exiting the with block

        try:
            with pytest.raises(ValueError):
                extract_pdf_text(tmp_path)
        finally:
            # Clean up; file may still be locked, so catch PermissionError
            try:
                Path(tmp_path).unlink()
            except PermissionError:
                pass  # File still locked by PyMuPDF; OS will clean up


class TestProcessPDF:
    """Test complete PDF processing pipeline."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Create a test PDF."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter

            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as tmp:
                c = canvas.Canvas(tmp.name, pagesize=letter)
                c.drawString(100, 750, "Page 1: " + "Lorem ipsum dolor sit amet. " * 50)
                c.showPage()
                c.drawString(100, 750, "Page 2: " + "Consectetur adipiscing elit. " * 50)
                c.save()
                yield tmp.name
                Path(tmp.name).unlink()
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_process_pdf_returns_chunks(self, sample_pdf_path):
        """Test that process_pdf returns properly structured chunks."""
        chunks = process_pdf(sample_pdf_path, chunk_size=200, chunk_overlap=50)

        assert len(chunks) > 0, "Should return at least one chunk"

        # Verify chunk structure
        for chunk in chunks:
            assert "text" in chunk, "Chunk should have text"
            assert "page" in chunk, "Chunk should have page number"
            assert "file_name" in chunk, "Chunk should have file_name"
            assert "chunk_index" in chunk, "Chunk should have chunk_index"
            assert isinstance(chunk["text"], str), "Text should be string"
            assert isinstance(chunk["page"], int), "Page should be int"
            assert chunk["page"] >= 1, "Page numbers should be 1-indexed"

    def test_chunk_index_sequential(self, sample_pdf_path):
        """Test that chunk indices are sequential."""
        chunks = process_pdf(sample_pdf_path)
        chunk_indices = [c["chunk_index"] for c in chunks]

        assert chunk_indices == list(range(len(chunks))), "Chunk indices should be sequential"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
