from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings
from rag.chroma_store import get_client, search

ROOT = Path(__file__).resolve().parent.parent


class ConfluenceTool:
    """Confluence knowledge retrieval via local Chroma index.

    Mock mode: indexes bundled seed markdown files into Chroma (default).
    Real mode: indexes the live Confluence space via Atlassian API on init.
    """

    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or settings.confluence_mode).lower()
        self._chroma = get_client(ROOT / "chroma_db")

        if self.mode == "real":
            self._sync_from_confluence()

    def _sync_from_confluence(self) -> None:
        """Pull pages from Confluence and re-index. Idempotent."""
        import re
        from atlassian import Confluence
        from rag.chroma_store import index_documents

        client = Confluence(
            url=settings.confluence_url,
            username=settings.confluence_username,
            password=settings.confluence_api_token,
            cloud=True,
        )
        pages = client.get_all_pages_from_space(
            space=settings.confluence_space_key,
            start=0,
            limit=200,
            expand="body.storage",
        )

        def _article_id(title: str, page_id: str) -> str:
            """Use the 'KB-###' prefix from the page title as the citable id
            (so the agent cites 'KB-247', not the opaque Confluence numeric id).
            Falls back to 'CF-<page_id>' for pages that don't follow the convention."""
            m = re.match(r"^\s*(KB-\d+)\b", title or "")
            return m.group(1) if m else f"CF-{page_id}"

        docs = [
            {
                "id": _article_id(page.get("title", ""), str(page["id"])),
                "title": page.get("title", ""),
                "text": _strip_html(page.get("body", {}).get("storage", {}).get("value", "")),
                "source": "confluence",
                "url": f"{settings.confluence_url}/spaces/{settings.confluence_space_key}/pages/{page['id']}",
            }
            for page in pages
        ]
        index_documents(self._chroma, docs, reset=True)

    def search_kb(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        hits = search(self._chroma, query=query, top_k=top_k)
        return [
            {
                "article_id": h["article_id"],
                "title": h["title"],
                "score": h["score"],
                "url": h["url"],
                "snippet": h["snippet"],
            }
            for h in hits
        ]

    def fetch_article(self, article_id: str) -> dict[str, Any]:
        coll = self._chroma.get_collection("confluence_kb")
        res = coll.get(ids=[article_id])
        if not res["ids"]:
            raise KeyError(f"Article {article_id} not found")
        meta = res["metadatas"][0]
        return {
            "article_id": meta.get("article_id", article_id),
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
            "text": res["documents"][0],
        }


def _strip_html(html: str) -> str:
    """Very small HTML stripper. Avoids pulling a full parser dependency."""
    import re

    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
