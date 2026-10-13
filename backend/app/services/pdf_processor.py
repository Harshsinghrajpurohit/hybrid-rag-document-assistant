"""
PDF extraction and chunking service.

Handles:
- Extracting text from PDFs with page number preservation
- Splitting text into overlapping chunks
- Attaching metadata (document name, page, chunk index)
"""

import fitz  # PyMuPDF
import pymupdf  # For exception types
from pathlib import Path
from typing import List, Dict, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)


def extract_pdf_text(file_path: str) -> Tuple[List[Dict], str]:
    """
    Extract text from PDF, preserving page numbers and document metadata.

    Args:
        file_path: Path to PDF file

    Returns:
        Tuple of (list of page dicts, document name)
        Each dict: {"text": str, "page": int, "file_name": str}

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If PDF is corrupted or unreadable
    """
    pdf_path = Path(file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    file_name = pdf_path.name
    pages_with_metadata = []

    try:
        doc = fitz.open(file_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            # Only include non-empty pages
            if text.strip():
                pages_with_metadata.append({
                    "text": text,
                    "page": page_num + 1,  # 1-indexed for user display
                    "file_name": file_name
                })

        doc.close()

        if not pages_with_metadata:
            logger.warning(f"PDF {file_name} extracted but contains no readable text")

        logger.info(f"Extracted {len(pages_with_metadata)} pages from {file_name}")
        return pages_with_metadata, file_name

    except pymupdf.FileDataError as e:
        raise ValueError(f"Failed to read PDF {file_name}: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error extracting PDF {file_name}: {str(e)}")


def split_into_chunks(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[str]:
    """
    Split text into overlapping chunks using recursive character splitting.

    This approach:
    1. Splits on double newlines first (paragraphs)
    2. Then on single newlines (sentences)
    3. Then on spaces (words)
    4. Finally on characters if needed

    This preserves context and avoids breaking mid-sentence when possible.

    Args:
        text: Text to split
        chunk_size: Target size of each chunk (characters)
        chunk_overlap: Number of overlapping characters between chunks

    Returns:
        List of text chunks
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # Try to split on these separators in order (prefer larger chunks)
        separators=["\n\n", "\n", " ", ""]
    )

    chunks = splitter.split_text(text)
    logger.debug(f"Split text into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})")
    return chunks


def process_pdf(
    file_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[Dict]:
    """
    Complete PDF processing pipeline: extract → chunk → attach metadata.

    Args:
        file_path: Path to PDF file
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters

    Returns:
        List of processed chunks with full metadata:
        {
            "text": str,
            "page": int,
            "file_name": str,
            "chunk_index": int
        }
    """
    # Extract pages
    pages, file_name = extract_pdf_text(file_path)

    processed_chunks = []
    chunk_index = 0

    # Process each page
    for page_data in pages:
        page_text = page_data["text"]
        page_num = page_data["page"]

        # Split page into chunks
        text_chunks = split_into_chunks(page_text, chunk_size, chunk_overlap)

        # Attach full metadata to each chunk
        for chunk_text in text_chunks:
            processed_chunks.append({
                "text": chunk_text,
                "page": page_num,
                "file_name": file_name,
                "chunk_index": chunk_index
            })
            chunk_index += 1

    logger.info(f"Processed {file_name}: {len(pages)} pages → {len(processed_chunks)} chunks")
    return processed_chunks
