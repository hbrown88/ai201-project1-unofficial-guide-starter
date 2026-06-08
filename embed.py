"""
Milestone 4 — Embedding + retrieval for "The Unofficial Guide".

Implements the middle stages of the planning.md pipeline:

    ... -> [ EMBEDDING ] -> [ VECTOR STORE ] -> [ RETRIEVAL ] -> (M5: generation)
              all-MiniLM-L6-v2     ChromaDB        top-k = 5
              (sentence-transformers / HuggingFace)

What this does (Retrieval Approach section of planning.md):
    - loads the chunks produced by ingest.py (chunks.json)
    - embeds each chunk locally with all-MiniLM-L6-v2 — runs on CPU, no API
      key, no rate limits
    - stores the vectors in a persistent ChromaDB collection together with each
      chunk's source URL (for attribution) and token count
    - retrieve(query, k=5) embeds the query with the same model and returns the
      k nearest chunks with their source and a cosine similarity score

Cosine distance is used (hnsw:space=cosine) with L2-normalized embeddings, which
is the right geometry for sentence-transformers vectors.

Build the index:   python embed.py
Try one query:     python embed.py --query "group fitness classes at the CRC"
Run the eval set:  python embed.py --demo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CHUNKS_PATH = "chunks.json"
PERSIST_DIR = "chroma_db"          # gitignored — local vector store
COLLECTION_NAME = "unofficial_guide"
MODEL_NAME = "all-MiniLM-L6-v2"    # planning.md Retrieval Approach
DEFAULT_K = 5                      # planning.md top-k
BATCH_SIZE = 256

# The 5 test questions from planning.md > Evaluation Plan (used by --demo).
EVAL_QUESTIONS = [
    "What upcoming events on campus or in the city can help enhance my resume?",
    "I finished class at 1pm with nothing else planned. What is going on on "
    "campus today that I could attend?",
    "I'm new to campus and want to meet people who are into photography. Are "
    "there student organizations at Georgia Tech I could join?",
    "What group fitness or intramural options does the Campus Rec Center have?",
    "It's the weekend and I want to get off campus. What's a free or cheap "
    "thing to do in Midtown Atlanta?",
]

# Lazily-initialized singletons so importing this module is cheap and the model
# / DB are loaded at most once per process.
_model = None
_collection = None


def get_model():
    """Load all-MiniLM-L6-v2 once (downloads ~80 MB on first run, then cached)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(f"Loading embedding model: {MODEL_NAME} ...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]):
    """Embed a list of texts into L2-normalized vectors (as plain lists)."""
    model = get_model()
    vecs = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 64,
    )
    return vecs.tolist()


def load_chunks(path: str | Path = CHUNKS_PATH) -> list[dict]:
    """Load the chunk records written by ingest.py."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python ingest.py --docs-dir documents/raw` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _open_collection(persist_dir: str, name: str, create: bool):
    """Open (and optionally create) the ChromaDB collection, cosine space."""
    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    if create:
        return client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
    return client.get_collection(name=name)


def build_index(
    chunks_path: str | Path = CHUNKS_PATH,
    persist_dir: str = PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> int:
    """Embed every chunk and (re)build the ChromaDB collection from scratch."""
    chunks = load_chunks(chunks_path)
    if not chunks:
        print("No chunks to embed — chunks.json is empty.")
        return 0

    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    # Rebuild cleanly so re-running never leaves stale or duplicated vectors.
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )

    # Chroma requires unique ids; disambiguate any rare slug collisions.
    seen: dict[str, int] = {}
    pos_counter: dict[str, int] = {}  # fallback if chunks lack an explicit position
    ids, documents, metadatas = [], [], []
    for c in chunks:
        cid = c["id"]
        if cid in seen:
            seen[cid] += 1
            cid = f"{cid}-{seen[cid]}"
        else:
            seen[cid] = 0

        src = c.get("source", "")
        position = c.get("position")
        if position is None:  # derive position-in-document from arrival order
            position = pos_counter.get(src, 0)
        pos_counter[src] = position + 1

        ids.append(cid)
        documents.append(c["text"])
        metadatas.append(
            {
                "source": src,                 # source document (URL) — for attribution
                "position": position,          # chunk's index within that document
                "token_count": c.get("token_count", 0),
            }
        )

    print(f"Embedding {len(documents)} chunk(s) with {MODEL_NAME} ...")
    for start in range(0, len(documents), BATCH_SIZE):
        sl = slice(start, start + BATCH_SIZE)
        collection.add(
            ids=ids[sl],
            embeddings=embed_texts(documents[sl]),
            documents=documents[sl],
            metadatas=metadatas[sl],
        )
        print(f"  indexed {min(start + BATCH_SIZE, len(documents))}/{len(documents)}")

    print(f"\nBuilt collection '{collection_name}' with {collection.count()} vectors "
          f"in {persist_dir}/")
    return collection.count()


def retrieve(
    query: str,
    k: int = DEFAULT_K,
    persist_dir: str = PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
    candidate_multiplier: int = 4,
    mmr_lambda: float = 0.8,
    min_score: float = 0.0,
) -> list[dict]:
    """Return up to k relevant chunks for `query`, diversified with MMR.

    Each result: {id, source, position, text, score, token_count}, where score
    is a cosine similarity in [0, 1] (higher = more relevant).

    Rather than taking the raw top-k (which over-represents a few "magnetic"
    overview chunks that are vaguely similar to everything), we over-fetch
    `k * candidate_multiplier` candidates and select k by Maximal Marginal
    Relevance: each pick maximizes mmr_lambda * sim_to_query minus
    (1 - mmr_lambda) * sim_to_already_selected. mmr_lambda=0.8 favors relevance
    while still suppressing near-duplicates. `min_score` drops candidates whose
    similarity to the query falls below the floor (lets generation say "I don't
    have that" instead of being fed loosely related noise).
    """
    import numpy as np

    global _collection
    if _collection is None:
        _collection = _open_collection(persist_dir, collection_name, create=False)

    fetch_n = min(_collection.count(), max(k * candidate_multiplier, k))
    qvec = embed_texts([query])
    res = _collection.query(
        query_embeddings=qvec,
        n_results=fetch_n,
        include=["documents", "metadatas", "distances", "embeddings"],
    )
    docs, metas = res["documents"][0], res["metadatas"][0]
    embs = res["embeddings"][0]
    if not docs:
        return []

    # Embeddings were stored L2-normalized, so cosine similarity == dot product.
    cand = np.asarray(embs, dtype=float)
    cand /= np.clip(np.linalg.norm(cand, axis=1, keepdims=True), 1e-9, None)
    q = np.asarray(qvec[0], dtype=float)
    q /= max(np.linalg.norm(q), 1e-9)
    sim_q = cand @ q                      # similarity of each candidate to query

    selected: list[int] = []
    remaining = list(range(len(docs)))
    while remaining and len(selected) < k:
        if not selected:
            i = max(remaining, key=lambda c: sim_q[c])
        else:
            sel = cand[selected]
            i = max(
                remaining,
                key=lambda c: mmr_lambda * sim_q[c]
                - (1 - mmr_lambda) * float(np.max(sel @ cand[c])),
            )
        if sim_q[i] < min_score:
            break
        selected.append(i)
        remaining.remove(i)

    return [
        {
            "id": res["ids"][0][idx],
            "source": metas[idx].get("source", ""),
            "position": metas[idx].get("position", -1),
            "text": docs[idx],
            "score": round(float(sim_q[idx]), 4),
            "token_count": metas[idx].get("token_count", 0),
        }
        for idx in selected
    ]


def _print_results(query: str, results: list[dict]) -> None:
    print(f"\nQ: {query}")
    for i, r in enumerate(results, 1):
        snippet = " ".join(r["text"].split())[:150]
        print(f"  {i}. [{r['score']:.3f}] {r['source']}  (chunk #{r['position']})")
        print(f"     {snippet}...")


def main() -> None:
    ap = argparse.ArgumentParser(description="Embed chunks + retrieve (Milestone 4).")
    ap.add_argument("--chunks", default=CHUNKS_PATH, help="chunks.json from ingest.py")
    ap.add_argument("--persist-dir", default=PERSIST_DIR)
    ap.add_argument("--collection", default=COLLECTION_NAME)
    ap.add_argument("--query", help="run a single retrieval instead of building")
    ap.add_argument("--demo", action="store_true", help="retrieve for the 5 eval questions")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    args = ap.parse_args()

    if args.query:
        _print_results(args.query, retrieve(args.query, args.k,
                                            args.persist_dir, args.collection))
        return
    if args.demo:
        for q in EVAL_QUESTIONS:
            _print_results(q, retrieve(q, args.k, args.persist_dir, args.collection))
        return

    build_index(args.chunks, args.persist_dir, args.collection)


if __name__ == "__main__":
    main()
