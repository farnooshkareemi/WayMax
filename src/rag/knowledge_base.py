"""Builds and persists the local Chroma vector store for WayMax's RAG layer.

Uses a local sentence-transformers embedding model (no API calls, no quota) so
the knowledge base can be built and queried entirely offline. The store is
persisted to disk (config.rag.persist_directory) so it only needs to be built
once; subsequent runs reuse the persisted collection.
"""

import chromadb
from chromadb.utils import embedding_functions

from src.config import load_config
from src.rag.documents.baggage_fees import BAGGAGE_DOCUMENTS


def get_chroma_client() -> chromadb.ClientAPI:
    config = load_config().rag
    return chromadb.PersistentClient(path=config.persist_directory)


def get_embedding_function() -> embedding_functions.EmbeddingFunction:
    config = load_config().rag
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=config.embedding_model)


def build_baggage_collection(client: chromadb.ClientAPI = None) -> chromadb.Collection:
    """Create (or fetch, if already built) the baggage-fees collection and
    ensure every document in BAGGAGE_DOCUMENTS is present in it."""
    config = load_config().rag
    client = client or get_chroma_client()

    collection = client.get_or_create_collection(
        name=config.collection_name,
        embedding_function=get_embedding_function(),
    )

    existing_ids = set(collection.get()["ids"])
    to_add = [doc for doc in BAGGAGE_DOCUMENTS if doc["airline"] not in existing_ids]

    if to_add:
        collection.add(
            ids=[doc["airline"] for doc in to_add],
            documents=[doc["text"] for doc in to_add],
            metadatas=[{"airline": doc["airline"], "source_url": doc["source_url"]} for doc in to_add],
        )

    return collection


if __name__ == "__main__":
    collection = build_baggage_collection()
    print(f"Baggage-fees collection ready with {collection.count()} document(s).")
