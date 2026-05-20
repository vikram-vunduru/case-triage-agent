"""Auto-seed the Confluence space with the 5 KB markdown articles in seed/confluence_docs/.

Idempotent: pages with the same title are updated in place (no duplicates).
Requires CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEY
to be set in .env.

Usage:
    python seed/seed_confluence.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atlassian import Confluence

from config import settings


def md_to_storage_html(md: str) -> str:
    """Minimal markdown → Confluence storage format converter.

    Confluence accepts a constrained HTML dialect. We do enough conversion
    here for headings, paragraphs, lists, bold, italic, and code so the seed
    KB articles render cleanly without pulling in a full markdown library.
    """
    import re

    lines = md.splitlines()
    out: list[str] = []
    in_list = False
    in_ol = False

    def close_list():
        nonlocal in_list, in_ol
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_list()
            out.append("")
            continue

        # headings
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_list()
            level = len(m.group(1))
            text = _inline(m.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            continue

        # ordered list
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if not in_ol:
                close_list()
                out.append("<ol>")
                in_ol = True
            out.append(f"  <li>{_inline(m.group(1))}</li>")
            continue

        # unordered list
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if not in_list:
                close_list()
                out.append("<ul>")
                in_list = True
            out.append(f"  <li>{_inline(m.group(1))}</li>")
            continue

        close_list()
        out.append(f"<p>{_inline(line)}</p>")

    close_list()
    return "\n".join(out)


def _inline(text: str) -> str:
    import re
    # escape HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # inline code `x`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # bold **x**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # italic *x*  (avoid eating bold)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def main() -> None:
    missing = []
    for key in ("confluence_url", "confluence_username", "confluence_api_token", "confluence_space_key"):
        if not getattr(settings, key):
            missing.append(key.upper())
    if missing:
        print("Missing required env vars: " + ", ".join(missing))
        sys.exit(1)

    client = Confluence(
        url=settings.confluence_url,
        username=settings.confluence_username,
        password=settings.confluence_api_token,
        cloud=True,
    )

    docs_dir = ROOT / "seed" / "confluence_docs"
    paths = sorted(docs_dir.glob("*.md"))
    if not paths:
        print(f"No markdown files found in {docs_dir}")
        sys.exit(1)

    print(f"Seeding {len(paths)} pages into space '{settings.confluence_space_key}' on {settings.confluence_url}…\n")

    for path in paths:
        body = path.read_text(encoding="utf-8")
        # First H1 line is the page title (e.g. 'KB-247: "Invalid Credentials" After a Password Reset')
        first_line = next((ln for ln in body.splitlines() if ln.strip().startswith("# ")), None)
        title = first_line.lstrip("# ").strip() if first_line else path.stem
        # Strip the title line from the body since Confluence renders the title separately.
        body_without_title = "\n".join(ln for ln in body.splitlines() if ln != first_line).lstrip()
        storage = md_to_storage_html(body_without_title)

        existing = client.get_page_by_title(space=settings.confluence_space_key, title=title)
        if existing:
            page_id = existing["id"]
            client.update_page(
                page_id=page_id,
                title=title,
                body=storage,
                representation="storage",
            )
            print(f"  ↻ updated  {title}")
        else:
            client.create_page(
                space=settings.confluence_space_key,
                title=title,
                body=storage,
                representation="storage",
            )
            print(f"  ✓ created  {title}")

    print(f"\nDone. View at {settings.confluence_url}/spaces/{settings.confluence_space_key}/overview")


if __name__ == "__main__":
    main()
