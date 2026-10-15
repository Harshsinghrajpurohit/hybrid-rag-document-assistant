"""
ChromaDB service for persistent vector storage and retrieval.
Manages document embeddings and semantic search.
"""

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

from backend.app.config import Config
from backend.app.services.embeddings import EmbeddingsService


class ChromaService:
    """Manages ChromaDB for vector storage and retrieval."""

    def __init__(
        self,
        db_path: str = None,
        embeddings_service: EmbeddingsService = None,
    ):
        """
        Initialize ChromaDB service with persistent storage.

        Args:
            db_path: Path to ChromaDB storage (default: from config)
            embeddings_service: EmbeddingsService instance (default: creates new)
        """
        self.db_path = db_path or Config.CHROMA_DB_PATH
        self.embeddings_service = embeddings_service or EmbeddingsService()

        # Ensure directory exists
        Config.ensure_chroma_db_dir()

        # Initialize ChromaDB client with persistent storage
        settings = Settings(
            is_persistent=True,
            persist_directory=self.db_path,
            anonymized_telemetry=False,
        )
        self.client = chromadb.Client(settings)

        # Get or create default collection for documents
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Add embedded chunks to ChromaDB.

        Args:
            chunks: List of dicts with keys:
                - "text" (str): chunk text (never stored as metadata)
                - "page" (int): page number
                - "file_name" (str): source document name
                - "chunk_index" (int): chunk sequence number
                - "doc_id" (str, optional): upload UUID; enables collision-free
                  chunk IDs ({doc_id}_p{page}_c{chunk_index}) and doc-level
                  metadata. Without it, the legacy ID format
                  ({file_name}_{page}_{chunk_index}) is used.
                - any additional keys (e.g., "upload_time", "size_bytes") are
                  stored as chunk metadata alongside the standard fields

        Returns:
            List of document IDs added to ChromaDB

        Example:
            chunks = [
                {"text": "...", "page": 1, "file_name": "doc.pdf", "chunk_index": 0},
                {"text": "...", "page": 2, "file_name": "doc.pdf", "chunk_index": 1},
            ]
            ids = service.add_chunks(chunks)
        """
        if not chunks:
            return []

        # Extract texts and generate embeddings
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embeddings_service.embed(texts)

        # Prepare IDs and metadata
        # New format (doc_id supplied): {doc_id}_p{page}_c{chunk_index}. The UUID
        # contains no underscores, so positions stay unambiguous for any filename.
        # Legacy format (no doc_id): {file_name}_{page}_{chunk_index}, kept for
        # backward compatibility with existing callers and stored records.
        ids = []
        metadatas = []
        for chunk in chunks:
            if "doc_id" in chunk:
                ids.append(
                    f"{chunk['doc_id']}_p{chunk['page']}_c{chunk['chunk_index']}"
                )
            else:
                ids.append(
                    f"{chunk['file_name']}_{chunk['page']}_{chunk['chunk_index']}"
                )
            metadatas.append(
                {key: value for key, value in chunk.items() if key != "text"}
            )

        # Add to ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

        return ids

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query for semantically similar chunks.

        Args:
            query_text: Question or search text
            n_results: Number of results to return
            where: Optional ChromaDB filter (e.g., {"file_name": {"$eq": "doc.pdf"}})

        Returns:
            Dict with keys:
                - "ids": list of document IDs
                - "distances": list of distances (lower = more similar)
                - "documents": list of chunk texts
                - "metadatas": list of metadata dicts
                - "query_embedding": the query embedding used

        Example:
            results = service.query("What is RAG?", n_results=3)
            for doc, meta in zip(results["documents"], results["metadatas"]):
                print(f"Page {meta['page']}: {doc}")
        """
        # Generate embedding for query
        query_embedding = self.embeddings_service.embed(query_text)

        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances", "embeddings"],
        )

        # Add query embedding to results for debugging/analysis
        results["query_embedding"] = query_embedding.tolist()

        return results

    def get_collection_stats(self) -> Dict[str, Any]:
        """Return statistics about the collection."""
        count = self.collection.count()
        return {
            "collection_name": self.collection.name,
            "document_count": count,
            "db_path": self.db_path,
        }

    def delete_all(self):
        """Delete all documents in the collection (for testing)."""
        # Get all IDs
        all_docs = self.collection.get()
        if all_docs["ids"]:
            self.collection.delete(ids=all_docs["ids"])

    def persist(self):
        """Data is auto-persisted in ChromaDB 1.5.9+ persistent mode."""
        pass  # No-op: data persists automatically
