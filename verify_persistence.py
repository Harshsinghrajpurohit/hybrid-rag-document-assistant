"""
Verify persistence: Reopen database and confirm data is still there
"""
from backend.app.services.chroma_service import ChromaService
from backend.app.services.embeddings import EmbeddingsService

print("=" * 70)
print("PERSISTENCE VERIFICATION: Reopening ChromaDB")
print("=" * 70)

# Create NEW instance (simulating app restart)
embeddings = EmbeddingsService()
chroma = ChromaService()

# Check stats
stats = chroma.get_collection_stats()
print(f"\n[1] After 'restart', collection contains:")
print(f"    Document count: {stats['document_count']}")
print(f"    Path: {stats['db_path']}")

if stats['document_count'] == 3:
    print("    Status: SUCCESS - Data persisted!")
else:
    print(f"    Status: FAILED - Expected 3 docs, got {stats['document_count']}")

# Query the persisted data
print(f"\n[2] Querying persisted data:")
results = chroma.query("embeddings semantic", n_results=1)

if results['ids'][0]:
    print(f"    Found: {len(results['ids'][0])} result(s)")
    doc = results['documents'][0][0]
    meta = results['metadatas'][0][0]
    print(f"    Document: {doc[:70]}...")
    print(f"    From: {meta['file_name']}, page {meta['page']}")
    print("    Status: SUCCESS - Can query persisted data!")
else:
    print("    Status: FAILED - No results found")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
