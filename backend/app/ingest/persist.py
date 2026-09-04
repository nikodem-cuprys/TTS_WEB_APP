"""Turns a parsed Document into Book/Chapter/Block rows. Shared by the upload API
(app/api/books.py) and the render CLI (scripts/render_book.py) so both paths persist
books identically. See PLAN.md 'Architecture'.
"""
from pathlib import Path

from sqlmodel import Session

from ..models import Block, Book, Chapter
from .detect import detect_language
from .document import Document


def _language_sample(document: Document, max_chars: int = 800) -> str:
    parts: list[str] = []
    total = 0
    for chapter in document.chapters:
        for block in chapter.blocks:
            parts.append(block.text)
            total += len(block.text)
            if total >= max_chars:
                return " ".join(parts)[:max_chars]
    return " ".join(parts)


def persist_document(session: Session, document: Document, source_path: Path, source_format: str) -> Book:
    language = document.language
    if language in ("", "und", None):
        language = detect_language(_language_sample(document)) or "en"

    cover_path: str | None = None
    if document.cover_bytes:
        ext = (document.cover_mime or "image/jpeg").split("/")[-1].split("+")[0]
        cover_file = source_path.parent / f"cover.{ext}"
        cover_file.write_bytes(document.cover_bytes)
        cover_path = str(cover_file)

    book = Book(
        title=document.title,
        author=document.author,
        language=language,
        cover_path=cover_path,
        source_path=str(source_path),
        source_format=source_format,
    )
    session.add(book)
    session.flush()  # assigns book.id without committing yet

    for doc_chapter in document.chapters:
        chapter = Chapter(
            book_id=book.id,
            index=doc_chapter.index,
            title=doc_chapter.title,
            enabled=doc_chapter.enabled,
        )
        session.add(chapter)
        session.flush()

        for i, doc_block in enumerate(doc_chapter.blocks):
            session.add(
                Block(chapter_id=chapter.id, index=i, kind=doc_block.kind, text=doc_block.text)
            )

    session.commit()
    session.refresh(book)
    return book
