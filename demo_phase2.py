"""
Demonstration: Real persistence with actual backend/chroma_db/ directory
"""
from backend.app.services.chroma_service import ChromaService
from backend.app.services.embeddings import EmbeddingsService
import os

print("=" * 70)
print("PHASE 2 PERSISTENCE DEMONSTRATION")
print("=" * 70)

# Initialize services
embeddings = EmbeddingsService()
chroma = ChromaService()

# Add sample chunks (simulating Phase 1 output)
sample_chunks = [
    {
        "text": "Retrieval-Augmented Generation is a technique that combines information retrieval with generative models.",
        "page": 1,
        "file_name": "rag_paper.pdf",
        "chunk_index": 0,
    },
    {
        "text": "The RAG system retrieves relevant documents from a knowledge base and uses them to augment the generation process.",
        "page": 2,
        "file_name": "rag_paper.pdf",
        "chunk_index": 1,
    },
    {
        "text": "Embeddings are numerical representations of text that capture semantic meaning. Similar texts have similar embeddings.",
        "page": 3,
        "file_name": "embeddings_guide.pdf",
        "chunk_index": 0,
    },
]

print("\n[1] Adding sample chunks to ChromaDB...")
ids = chroma.add_chunks(sample_chunks)
print(f"    Added {len(ids)} chunks")
print(f"    IDs: {ids}")

# Show stats
stats = chroma.get_collection_stats()
print(f"\n[2] Collection stats:")
print(f"    Collection: {stats['collection_name']}")
print(f"    Document count: {stats['document_count']}")
print(f"    Database path: {stats['db_path']}")

# Persist
chroma.persist()
print(f"\n[3] Data persisted to disk")

# Test query
print(f"\n[4] Testing semantic search:")
results = chroma.query("What is RAG?", n_results=2)
print(f"    Query: 'What is RAG?'")
print(f"    Results found: {len(results['ids'][0])}")
for i, doc in enumerate(results['documents'][0], 1):
    print(f"    [{i}] {doc[:80]}...")

# Verify directory
chroma_path = "backend/chroma_db"
if os.path.exists(chroma_path):
    files = os.listdir(chroma_path)
    print(f"\n[5] ChromaDB directory contents:")
    print(f"    Path: {chroma_path}")
    print(f"    Total items: {len(files)}")
    if files:
        print(f"    Sample: {files[:3]}")

print("\n" + "=" * 70)
print("PHASE 2 COMPLETE: Embeddings & ChromaDB ready")
print("=" * 70)
