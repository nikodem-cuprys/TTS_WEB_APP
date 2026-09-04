"""Standalone HTML parser: strips boilerplate (script/style/nav/header/footer chrome)
and splits into chapters at top-level headings. Unlike EPUB there is no spine or TOC to
lean on, so chapter boundaries are purely heading-driven; a file with no headings at all
becomes a single chapter. See PLAN.md 'ingest/base.py'.
"""
from pathlib import Path

from bs4 import BeautifulSoup

from ..models import BlockKind
from .base import ParseError
from .document import DocBlock, DocChapter, Document

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_QUOTE_TAGS = {"blockquote"}
_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "svg", "img", "figure", "aside"}
_TEXT_TAGS = _HEADING_TAGS | _QUOTE_TAGS | {"p", "li", "dd", "figcaption"}
_CHAPTER_HEADING_TAGS = {"h1", "h2"}  # only these start a new chapter; h3+ stay inline


class HtmlParser:
    extensions = ("html", "htm")

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def parse(self, path: Path) -> Document:
        try:
            raw = path.read_bytes()
            soup = BeautifulSoup(raw, "lxml")
        except Exception as exc:
            raise ParseError(f"could not parse HTML {path}: {exc}") from exc

        for tag in soup.find_all(_SKIP_TAGS):
            tag.decompose()

        title_tag = soup.find("title")
        doc_title = title_tag.get_text(strip=True) if title_tag else path.stem

        html_tag = soup.find("html")
        language = (html_tag.get("lang") or "und").split("-")[0].lower() if html_tag else "und"

        body = soup.body or soup

        chapters: list[DocChapter] = []
        current_blocks: list[DocBlock] = []
        current_title = doc_title
        chapter_index = 0
        seen_chapter_heading = False

        def flush() -> None:
            nonlocal chapter_index, current_blocks, current_title
            if current_blocks:
                chapters.append(DocChapter(index=chapter_index, title=current_title, blocks=current_blocks))
                chapter_index += 1
            current_blocks = []

        for tag in body.find_all(_TEXT_TAGS):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            if tag.name in _CHAPTER_HEADING_TAGS:
                flush()
                current_title = text if len(text) <= 80 else text[:77] + "..."
                seen_chapter_heading = True
                continue
            kind = BlockKind.heading if tag.name in _HEADING_TAGS else (
                BlockKind.quote if tag.name in _QUOTE_TAGS else BlockKind.para
            )
            current_blocks.append(DocBlock(kind=kind, text=text))
        flush()

        if not chapters:
            raise ParseError(f"{path} contains no readable text")
        if not seen_chapter_heading and len(chapters) == 1:
            chapters[0].title = doc_title

        return Document(title=doc_title, language=language, chapters=chapters)
