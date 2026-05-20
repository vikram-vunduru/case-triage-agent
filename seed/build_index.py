"""One-time setup: index seed Confluence markdown docs into Chroma."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag.chroma_store import get_client, index_documents


def load_docs(docs_dir: Path) -> list[dict]:
    docs: list[dict] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first_line = next((ln for ln in text.splitlines() if ln.strip()), path.stem)
        title = first_line.lstrip("# ").strip() or path.stem
        article_id = path.stem.split("_")[0]
        docs.append(
            {
                "id": article_id,
                "title": title,
                "text": text,
                "source": "confluence",
                "url": f"https://confluence.local/wiki/{article_id}",
            }
        )
    return docs


def main() -> None:
    persist_dir = ROOT / "chroma_db"
    docs_dir = ROOT / "seed" / "confluence_docs"
    docs = load_docs(docs_dir)
    client = get_client(persist_dir)
    count = index_documents(client, docs, reset=True)
    print(f"Indexed {count} articles into {persist_dir}")
    for d in docs:
        print(f"  - {d['id']}: {d['title']}")


if __name__ == "__main__":
    main()
