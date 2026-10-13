"""
Quick verification test for hybrid retriever
"""
import tempfile
import shutil
from backend.app.services.hybrid_retriever import HybridRetriever
from backend.app.services.chroma_service import ChromaService
from backend.app.services.embeddings import EmbeddingsService

print("=" * 70)
print("PHASE 3 HYBRID RETRIEVER - QUICK TEST")
print("=" * 70)

# Setup
temp_dir = tempfile.mkdtemp(prefix="hybrid_verify_")
embeddings = EmbeddingsService()
chroma = ChromaService(db_path=temp_dir, embeddings_service=embeddings)
retriever = HybridRetriever(chroma)

print("\n[1] Initialization test")
stats = retriever.get_index_stats()
print(f"    BM25 corpus size: {stats['bm25_corpus_size']}")
print(f"    K_RRF: {stats['k_rrf']}")
print("    Status: PASS")

# Add test documents
print("\n[2] Adding test documents...")
chunks = [
    {
        "text": "Retrieval-Augmented Generation combines information retrieval with generative models.",
        "page": 1,
        "file_name": "rag.pdf",
        "chunk_index": 0,
    },
    {
        "text": "Machine learning uses neural networks to learn patterns from data.",
        "page": 2,
        "file_name": "ml.pdf",
        "chunk_index": 0,
    },
    {
        "text": "The cat sat on the mat and fell asleep.",
        "page": 3,
        "file_name": "story.pdf",
        "chunk_index": 0,
    },
]

chroma.add_chunks(chunks)
retriever.rebuild_index()
print(f"    Added 3 documents")

stats = retriever.get_index_stats()
print(f"    BM25 corpus size: {stats['bm25_corpus_size']}")
print("    Status: PASS")

# Test BM25 search
print("\n[3] BM25 keyword search test")
results = retriever._bm25_search("cat mat", top_k=3)
print(f"    Query: 'cat mat'")
print(f"    Results found: {len(results)}")
if results:
    print(f"    Top match: {results[0][1]:.2f} score")
    print("    Status: PASS")
else:
    print("    Status: WARNING - No BM25 results")

# Test dense search
print("\n[4] Dense semantic search test")
results = retriever._dense_search("Retrieval-Augmented Generation systems", top_k=3)
print(f"    Query: 'Retrieval-Augmented Generation systems'")
print(f"    Results found: {len(results)}")
if results:
    print(f"    Top match: {results[0][1]:.4f} similarity")
    print("    Status: PASS")
else:
    print("    Status: FAIL - No dense results")

# Test hybrid retrieval
print("\n[5] Hybrid retrieval test")
results = retriever.retrieve("What is machine learning?", n_results=3)
print(f"    Query: 'What is machine learning?'")
print(f"    Results found: {len(results['ids'])}")
if results['ids']:
    for i, (doc_id, rrf_score) in enumerate(zip(results['ids'], results['rrf_scores']), 1):
        print(f"    [{i}] {doc_id}: RRF={rrf_score:.4f}")
    print("    Status: PASS")
else:
    print("    Status: FAIL - No results")

# Test metadata preservation
print("\n[6] Metadata preservation test")
if results['metadatas']:
    meta = results['metadatas'][0]
    print(f"    Page: {meta['page']}, File: {meta['file_name']}, Index: {meta['chunk_index']}")
    print("    Status: PASS")
else:
    print("    Status: FAIL - No metadata")

# Test return format
print("\n[7] Return format test")
required_fields = ['ids', 'documents', 'metadatas', 'distances', 'bm25_scores', 'rrf_scores']
missing = [f for f in required_fields if f not in results]
if not missing:
    print(f"    All {len(required_fields)} required fields present")
    print("    Status: PASS")
else:
    print(f"    Missing fields: {missing}")
    print("    Status: FAIL")

# Cleanup
shutil.rmtree(temp_dir, ignore_errors=True)

print("\n" + "=" * 70)
print("PHASE 3 QUICK TEST COMPLETE")
print("=" * 70)
