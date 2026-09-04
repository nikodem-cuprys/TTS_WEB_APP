"""Plain-text parser: blank-line paragraphs, heuristic chapter split, encoding sniffing.

Chapter markers only exist as a text convention in TXT files. If none of the known
patterns (localized "Chapter"/"Rozdział"/"Kapitel"/"第...章" markers, or a short
Title-Case/ALL-CAPS line standing alone between blank lines) are found, the whole file
becomes a single chapter — better than guessing wrong and shredding the prose.
"""
import re
from pathlib import Path

from charset_normalizer import from_path

from ..models import BlockKind
from .base import ParseError
from .document import DocBlock, DocChapter, Document
from .heading import looks_like_heading


def _decode(path: Path) -> str:
    results = from_path(str(path))
    best = results.best()
    if best is None:
        raise ParseError(f"could not detect a text encoding for {path}")
    return str(best)


def _split_paragraphs(text: str) -> list[str]:
    # Normalize line endings, then split on one-or-more blank lines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_paragraphs = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in raw_paragraphs if p.strip()]


class TxtParser:
    extensions = ("txt",)

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def parse(self, path: Path) -> Document:
        text = _decode(path)
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            raise ParseError(f"{path} contains no text")

        chapters: list[DocChapter] = []
        current_blocks: list[DocBlock] = []
        chapter_index = 0
        current_title = "Chapter 1"

        def flush() -> None:
            nonlocal chapter_index, current_blocks, current_title
            if current_blocks:
                chapters.append(
                    DocChapter(index=chapter_index, title=current_title, blocks=current_blocks)
                )
                chapter_index += 1
            current_blocks = []

        for para in paragraphs:
            # A paragraph containing a single line that looks like a heading starts a
            # new chapter; multi-line paragraphs are always prose.
            if "\n" not in para and looks_like_heading(para):
                flush()
                current_title = para if len(para) <= 80 else para[:77] + "..."
                continue
            joined = " ".join(line.strip() for line in para.splitlines() if line.strip())
            current_blocks.append(DocBlock(kind=BlockKind.para, text=joined))
        flush()

        if not chapters:
            # No headings anywhere and no blocks were ever flushed (e.g. a single
            # paragraph file) — treat the whole thing as chapter 1.
            blocks = [
                DocBlock(kind=BlockKind.para, text=" ".join(p.splitlines()))
                for p in paragraphs
            ]
            chapters = [DocChapter(index=0, title="Chapter 1", blocks=blocks)]

        return Document(title=path.stem, language="und", chapters=chapters)
