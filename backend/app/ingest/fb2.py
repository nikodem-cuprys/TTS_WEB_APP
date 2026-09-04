"""FictionBook2 (FB2) parser: an XML format where top-level <section> elements under the
main <body> are chapters, with nested subsections flattened into headings inside their
parent chapter. Footnote/annotation bodies (<body name="notes">) are skipped. See
PLAN.md 'ingest/base.py'.
"""
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from ..models import BlockKind
from .base import ParseError
from .document import DocBlock, DocChapter, Document

_QUOTE_TAGS = {"cite", "epigraph"}


def _section_title(section: Tag) -> str | None:
    title_tag = section.find("title", recursive=False)
    if not title_tag:
        return None
    text = title_tag.get_text(" ", strip=True)
    return text or None


def _collect_blocks(section: Tag, blocks: list[DocBlock]) -> None:
    """Walks a <section>, emitting paragraphs/subtitles/quotes and recursing into
    nested <section>s (their own <title> becomes a heading block, not a new chapter)."""
    for child in section.find_all(recursive=False):
        if child.name == "title":
            continue  # already used as the chapter title
        if child.name == "section":
            nested_title = _section_title(child)
            if nested_title:
                blocks.append(DocBlock(kind=BlockKind.heading, text=nested_title))
            _collect_blocks(child, blocks)
        elif child.name == "subtitle":
            text = child.get_text(" ", strip=True)
            if text:
                blocks.append(DocBlock(kind=BlockKind.heading, text=text))
        elif child.name in _QUOTE_TAGS:
            text = child.get_text(" ", strip=True)
            if text:
                blocks.append(DocBlock(kind=BlockKind.quote, text=text))
        elif child.name == "p":
            text = child.get_text(" ", strip=True)
            if text:
                blocks.append(DocBlock(kind=BlockKind.para, text=text))
        elif child.name in ("empty-line", "image"):
            continue


class Fb2Parser:
    extensions = ("fb2",)

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def parse(self, path: Path) -> Document:
        try:
            raw = path.read_bytes()
            soup = BeautifulSoup(raw, "xml")
        except Exception as exc:
            raise ParseError(f"could not parse FB2 {path}: {exc}") from exc

        title_info = soup.find("title-info")
        book_title = None
        author = None
        language = "und"
        if title_info:
            title_tag = title_info.find("book-title")
            if title_tag:
                book_title = title_tag.get_text(strip=True)
            author_tag = title_info.find("author")
            if author_tag:
                names = [
                    author_tag.find(n).get_text(strip=True)
                    for n in ("first-name", "last-name")
                    if author_tag.find(n)
                ]
                author = " ".join(names) if names else None
            lang_tag = title_info.find("lang")
            if lang_tag:
                language = lang_tag.get_text(strip=True).split("-")[0].lower() or "und"

        main_body = None
        for body in soup.find_all("body"):
            if body.get("name") is None:
                main_body = body
                break
        if main_body is None:
            raise ParseError(f"{path} has no main <body>")

        chapters: list[DocChapter] = []
        for i, section in enumerate(main_body.find_all("section", recursive=False)):
            title = _section_title(section) or f"Chapter {i + 1}"
            blocks: list[DocBlock] = []
            _collect_blocks(section, blocks)
            if blocks:
                chapters.append(DocChapter(index=len(chapters), title=title, blocks=blocks))

        if not chapters:
            raise ParseError(f"{path} has no readable sections")

        return Document(
            title=book_title or path.stem,
            author=author,
            language=language,
            chapters=chapters,
        )
