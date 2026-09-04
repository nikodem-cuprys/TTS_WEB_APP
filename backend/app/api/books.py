"""Upload endpoint: accepts a book file, sniffs its format, parses it into a Document
(app.ingest), and persists Book/Chapter/Block rows. See PLAN.md 'Architecture'.
"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import Settings, get_settings
from ..db import get_session
from ..ingest.base import ParseError, ParserUnavailableError
from ..ingest.calibre import CalibreParser
from ..ingest.detect import PARSERS, resolve_parser
from ..ingest.persist import persist_document
from ..models import Block, Book, Chapter
from ..schemas import (
    BlockOut,
    BlockUpdate,
    BookDetailOut,
    BookSummaryOut,
    ChapterDetailOut,
    ChapterSummaryOut,
    ChapterUpdate,
)

router = APIRouter()

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    name = Path(name).name  # strip any path components the client might send
    name = _SAFE_NAME_RE.sub("_", name)
    return name or "upload"


@router.get("/formats")
def list_formats() -> list[dict]:
    """Supported extensions and whether each is currently usable, so the upload UI can
    grey out Calibre-dependent formats up front instead of failing after upload."""
    formats: list[dict] = []
    for parser in PARSERS:
        available = parser.is_available() if isinstance(parser, CalibreParser) else True
        note = None if available else "requires Calibre (ebook-convert) on PATH"
        for ext in parser.extensions:
            formats.append({"extension": ext, "available": available, "note": note})
    return formats


@router.post("/books", response_model=BookSummaryOut, status_code=201)
async def upload_book(
    file: UploadFile,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Book:
    max_bytes = settings.max_upload_mb * 1024 * 1024

    book_dir = settings.books_dir() / uuid.uuid4().hex
    book_dir.mkdir(parents=True, exist_ok=True)
    dest_path = book_dir / _safe_filename(file.filename or "upload")

    size = 0
    with dest_path.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds the {settings.max_upload_mb}MB upload limit",
                )
            out.write(chunk)

    try:
        parser = resolve_parser(dest_path)
        document = parser.parse(dest_path)
    except ParserUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    source_format = dest_path.suffix.lower().lstrip(".")
    book = persist_document(session, document, dest_path, source_format)

    return BookSummaryOut(
        id=book.id,
        title=book.title,
        author=book.author,
        language=book.language,
        source_format=book.source_format,
        has_cover=book.cover_path is not None,
        chapter_count=len(book.chapters),
        created_at=book.created_at,
    )


@router.get("/books", response_model=list[BookSummaryOut])
def list_books(session: Session = Depends(get_session)) -> list[BookSummaryOut]:
    books = session.exec(select(Book).order_by(Book.created_at.desc())).all()
    return [
        BookSummaryOut(
            id=b.id,
            title=b.title,
            author=b.author,
            language=b.language,
            source_format=b.source_format,
            has_cover=b.cover_path is not None,
            chapter_count=len(b.chapters),
            created_at=b.created_at,
        )
        for b in books
    ]


@router.get("/books/{book_id}", response_model=BookDetailOut)
def get_book(book_id: int, session: Session = Depends(get_session)) -> BookDetailOut:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    chapters = sorted(book.chapters, key=lambda c: c.index)
    return BookDetailOut(
        id=book.id,
        title=book.title,
        author=book.author,
        language=book.language,
        source_format=book.source_format,
        has_cover=book.cover_path is not None,
        chapter_count=len(chapters),
        created_at=book.created_at,
        chapters=[
            ChapterSummaryOut(
                id=c.id, index=c.index, title=c.title, enabled=c.enabled, block_count=len(c.blocks)
            )
            for c in chapters
        ],
    )


@router.get("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterDetailOut)
def get_chapter(book_id: int, chapter_id: int, session: Session = Depends(get_session)) -> ChapterDetailOut:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="chapter not found")
    blocks = sorted(chapter.blocks, key=lambda b: b.index)
    return ChapterDetailOut(
        id=chapter.id,
        index=chapter.index,
        title=chapter.title,
        enabled=chapter.enabled,
        blocks=[BlockOut(id=b.id, index=b.index, kind=b.kind, text=b.text) for b in blocks],
    )


@router.patch("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterDetailOut)
def update_chapter(
    book_id: int, chapter_id: int, body: ChapterUpdate, session: Session = Depends(get_session)
) -> ChapterDetailOut:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="chapter not found")

    if body.title is not None:
        chapter.title = body.title
    if body.enabled is not None:
        chapter.enabled = body.enabled
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    blocks = sorted(chapter.blocks, key=lambda b: b.index)
    return ChapterDetailOut(
        id=chapter.id, index=chapter.index, title=chapter.title, enabled=chapter.enabled,
        blocks=[BlockOut(id=b.id, index=b.index, kind=b.kind, text=b.text) for b in blocks],
    )


@router.patch("/books/{book_id}/chapters/{chapter_id}/blocks/{block_id}", response_model=BlockOut)
def update_block(
    book_id: int, chapter_id: int, block_id: int, body: BlockUpdate, session: Session = Depends(get_session)
) -> BlockOut:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="chapter not found")
    block = session.get(Block, block_id)
    if block is None or block.chapter_id != chapter_id:
        raise HTTPException(status_code=404, detail="block not found")

    block.text = body.text
    session.add(block)
    session.commit()
    session.refresh(block)
    return BlockOut(id=block.id, index=block.index, kind=block.kind, text=block.text)
