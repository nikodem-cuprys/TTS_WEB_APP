"""EPUB parser: chapters follow the spine, titles come from the nav/NCX-derived TOC
(ebooklib normalizes both EPUB3 nav and EPUB2 NCX into book.toc), and the nav document
itself is dropped rather than narrated. See PLAN.md 'ingest/base.py'.
"""
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from ..models import BlockKind
from .base import ParseError
from .document import DocBlock, DocChapter, Document

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_QUOTE_TAGS = {"blockquote"}
_SKIP_TAGS = {"script", "style", "nav", "svg", "img", "figure"}
_TEXT_TAGS = _HEADING_TAGS | _QUOTE_TAGS | {"p", "li", "dd", "figcaption"}


def _flatten_toc(toc, out: dict[str, str]) -> None:
    """book.toc is a nested tuple of Link/Section; flatten to {href_without_fragment: title}."""
    for entry in toc:
        if isinstance(entry, epub.Link):
            href = entry.href.split("#", 1)[0]
            out.setdefault(href, entry.title)
        elif isinstance(entry, tuple):
            # (Section|Link, [children]) or plain nested tuple
            for part in entry:
                if isinstance(part, (list, tuple)):
                    _flatten_toc(part, out)
                elif isinstance(part, epub.Link):
                    href = part.href.split("#", 1)[0]
                    out.setdefault(href, part.title)


def _blocks_from_html(html: bytes) -> tuple[list[DocBlock], str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_SKIP_TAGS):
        tag.decompose()

    blocks: list[DocBlock] = []
    first_heading: str | None = None

    for tag in soup.find_all(_TEXT_TAGS):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if tag.name in _HEADING_TAGS:
            if first_heading is None:
                first_heading = text
            blocks.append(DocBlock(kind=BlockKind.heading, text=text))
        elif tag.name in _QUOTE_TAGS:
            blocks.append(DocBlock(kind=BlockKind.quote, text=text))
        else:
            blocks.append(DocBlock(kind=BlockKind.para, text=text))

    return blocks, first_heading


def _find_cover(book: epub.EpubBook) -> tuple[bytes | None, str | None]:
    cover_meta = book.get_metadata("OPF", "cover")
    if cover_meta:
        content_id = cover_meta[0][1].get("content")
        item = book.get_item_with_id(content_id) if content_id else None
        if item is not None:
            return item.get_content(), item.media_type

    for item in book.get_items():
        props = getattr(item, "properties", None) or []
        if "cover-image" in props:
            return item.get_content(), item.media_type

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE and "cover" in item.get_id().lower():
            return item.get_content(), item.media_type

    return None, None


class EpubParser:
    extensions = ("epub",)

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def parse(self, path: Path) -> Document:
        try:
            book = epub.read_epub(str(path), options={"ignore_ncx": False})
        except Exception as exc:  # ebooklib raises assorted exceptions on malformed input
            raise ParseError(f"could not read EPUB {path}: {exc}") from exc

        titles = book.get_metadata("DC", "title")
        title = titles[0][0] if titles else path.stem

        creators = book.get_metadata("DC", "creator")
        author = creators[0][0] if creators else None

        languages = book.get_metadata("DC", "language")
        language = languages[0][0].split("-")[0].lower() if languages else "und"

        href_titles: dict[str, str] = {}
        _flatten_toc(book.toc, href_titles)

        cover_bytes, cover_mime = _find_cover(book)

        chapters: list[DocChapter] = []
        chapter_index = 0
        for idref, linear in book.spine:
            if linear == "no":
                continue
            item = book.get_item_with_id(idref)
            if item is None or isinstance(item, epub.EpubNav):
                continue
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            blocks, first_heading = _blocks_from_html(item.get_content())
            if not blocks:
                continue  # e.g. a blank separator page

            chapter_title = href_titles.get(item.get_name()) or first_heading or f"Chapter {chapter_index + 1}"
            chapters.append(DocChapter(index=chapter_index, title=chapter_title, blocks=blocks))
            chapter_index += 1

        if not chapters:
            raise ParseError(f"{path} has no readable spine content")

        return Document(
            title=title,
            author=author,
            language=language,
            cover_bytes=cover_bytes,
            cover_mime=cover_mime,
            chapters=chapters,
        )
