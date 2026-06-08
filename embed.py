"""
Milestone 4 — Embedding + Retrieval for the Deadlock RAG knowledge base.

Reads chunks.json (produced in Milestone 3), embeds each chunk locally with
all-MiniLM-L6-v2, stores the vectors in a persistent ChromaDB collection, and
exposes a retrieve() function used downstream in Milestone 5 (generation).

Run standalone:  python embed.py
No API key is required — all-MiniLM-L6-v2 runs fully offline.
"""

import json
import os

from sentence_transformers import SentenceTransformer
import chromadb

# --- Config ---------------------------------------------------------------
CHUNKS_PATH = "chunks.json"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "deadlock_chunks"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 100

# A module-level model handle so both embedding and retrieval reuse the same
# loaded weights instead of reloading the model on every call.
_model = None


def get_model() -> SentenceTransformer:
    """Load (once) and return the local SentenceTransformer model."""
    global _model
    if _model is None:
        print(f"Loading embedding model '{MODEL_NAME}' (runs locally, no API key)...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_collection():
    """Return the persistent ChromaDB collection, creating it if needed."""
    # PersistentClient writes the vector index to disk at CHROMA_PATH so the
    # embeddings survive between runs (no re-embedding on the next launch).
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # metadata={"hnsw:space": "cosine"} tells Chroma to use cosine distance for
    # similarity instead of its default squared-L2. Cosine distance lands in a
    # 0..2 range (0 = identical), which is what the 0.6 "weak match" threshold
    # below assumes. This space is fixed at creation time for the collection.
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def embed_and_store():
    """STEP 1–4: load chunks, embed them, and populate ChromaDB."""

    # STEP 1 — Load chunks
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_PATH}")

    # STEP 2 / STEP 3 — model + collection
    model = get_model()
    collection = get_collection()

    # STEP 3 (cont.) — skip re-embedding if already populated.
    # .count() returns how many documents are stored in the collection.
    existing = collection.count()
    if existing > 0:
        print(f"Collection '{COLLECTION_NAME}' already populated with "
              f"{existing} documents — skipping embedding.")
        return collection

    # STEP 4 — embed and store in batches of BATCH_SIZE
    total = len(chunks)
    for start in range(0, total, BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]

        ids = [c["id"] for c in batch]
        texts = [c["text"] for c in batch]
        metadatas = [
            # Preserve these exactly — Milestone 5 uses them for source attribution.
            {"hero": c["hero"], "section": c["section"], "source": c["source"]}
            for c in batch
        ]

        # encode() returns a numpy array; .tolist() converts it to the plain
        # Python lists that Chroma's add() expects for the embeddings argument.
        embeddings = model.encode(texts).tolist()

        # add() inserts new records. We pass our own embeddings so Chroma stores
        # them as-is rather than trying to compute its own.
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        done = min(start + BATCH_SIZE, total)
        print(f"  embedded + stored {done}/{total} chunks")

    print(f"Done. Collection now holds {collection.count()} documents.")
    return collection


# STEP 5 — Retrieval function
def retrieve(query: str, k: int = 5):
    """
    Embed `query` and return the top-k most similar chunks from ChromaDB.

    Returns a list of dicts: {text, hero, section, source, distance}.
    """
    model = get_model()
    collection = get_collection()

    query_embedding = model.encode([query]).tolist()

    # include=[...] tells Chroma which fields to return alongside the matches.
    # "distances" is what we threshold on; ids are always returned regardless.
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    # query() returns each field as a list-of-lists (one inner list per query).
    # We sent a single query, so we read index [0] of each.
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({
            "text": doc,
            "hero": meta.get("hero"),
            "section": meta.get("section"),
            "source": meta.get("source"),
            "distance": dist,
        })
    return hits


# STEP 6 — Test queries
def run_test_queries():
    queries = [
        "Does Haze throw a knife when using her ultimate ability?",
        "What tier is Ivy placed at?",
        "Does Haze have a passive ability?",
    ]

    for q in queries:
        print("\n" + "=" * 80)
        print(f"QUERY: {q}")
        print("=" * 80)

        hits = retrieve(q, k=5)
        for rank, hit in enumerate(hits, start=1):
            preview = hit["text"][:200].replace("\n", " ")
            print(f"\n[{rank}] distance={hit['distance']:.4f} | "
                  f"hero={hit['hero']} | section={hit['section']}")
            print(f"    source: {hit['source']}")
            print(f"    text:   {preview}")

        # Debug judgment on the top result's distance.
        top_distance = hits[0]["distance"] if hits else 1.0
        if top_distance > 0.6:
            print(f"\n>>> WARNING: weak match (top distance {top_distance:.4f} > 0.6)")
        else:
            print(f"\n>>> OK (top distance {top_distance:.4f})")


if __name__ == "__main__":
    embed_and_store()
    run_test_queries()
