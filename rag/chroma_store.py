from __future__ import annotations

from pathlib import Path
from typing import Iterable

import chromadb
from chromadb.config import Settings as ChromaSettings


COLLECTION_NAME = "confluence_kb"


def get_client(persist_dir: str | Path) -> chromadb.ClientAPI:
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_or_create_collection(client: chromadb.ClientAPI):
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def index_documents(
    client: chromadb.ClientAPI,
    docs: Iterable[dict],
    reset: bool = True,
) -> int:
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    coll = get_or_create_collection(client)

    ids, texts, metadatas = [], [], []
    for doc in docs:
        ids.append(doc["id"])
        texts.append(doc["text"])
        metadatas.append(
            {
                "article_id": doc["id"],
                "title": doc["title"],
                "source": doc.get("source", "confluence"),
                "url": doc.get("url", ""),
            }
        )

    if not ids:
        return 0

    coll.add(ids=ids, documents=texts, metadatas=metadatas)
    return len(ids)


def search(
    client: chromadb.ClientAPI,
    query: str,
    top_k: int = 3,
) -> list[dict]:
    coll = get_or_create_collection(client)
    res = coll.query(query_texts=[query], n_results=top_k)

    hits: list[dict] = []
    if not res.get("ids"):
        return hits

    ids = res["ids"][0]
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    distances = res.get("distances", [[None] * len(ids)])[0]

    for i, doc_id in enumerate(ids):
        distance = distances[i]
        score = round(1.0 - distance, 4) if distance is not None else None
        hits.append(
            {
                "article_id": metas[i].get("article_id", doc_id),
                "title": metas[i].get("title", ""),
                "url": metas[i].get("url", ""),
                "score": score,
                "snippet": (docs[i] or "")[:600],
                "full_text": docs[i] or "",
            }
        )
    return hits
