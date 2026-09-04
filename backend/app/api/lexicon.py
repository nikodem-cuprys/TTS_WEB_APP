"""Per-book pronunciation lexicon CRUD ([M4-6]). Applied in pipeline/runner.py via
text/lexicon.py — see that module's docstring for why editing an entry here only
invalidates the chunks that actually contain the pattern, not the whole book's cache.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Book, LexiconEntry
from ..schemas import LexiconEntryCreate, LexiconEntryOut, LexiconEntryUpdate

router = APIRouter()


def _out(entry: LexiconEntry) -> LexiconEntryOut:
    return LexiconEntryOut(
        id=entry.id, pattern=entry.pattern, replacement=entry.replacement,
        is_regex=entry.is_regex, enabled=entry.enabled,
    )


def _validate_regex(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"invalid regex pattern: {exc}") from exc


@router.get("/books/{book_id}/lexicon", response_model=list[LexiconEntryOut])
def list_lexicon(book_id: int, session: Session = Depends(get_session)) -> list[LexiconEntryOut]:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return [_out(e) for e in book.lexicon_entries]


@router.post("/books/{book_id}/lexicon", response_model=LexiconEntryOut, status_code=201)
def create_lexicon_entry(
    book_id: int, body: LexiconEntryCreate, session: Session = Depends(get_session)
) -> LexiconEntryOut:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    if body.is_regex:
        _validate_regex(body.pattern)

    entry = LexiconEntry(
        book_id=book_id, pattern=body.pattern, replacement=body.replacement,
        is_regex=body.is_regex, enabled=body.enabled,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _out(entry)


@router.patch("/books/{book_id}/lexicon/{entry_id}", response_model=LexiconEntryOut)
def update_lexicon_entry(
    book_id: int, entry_id: int, body: LexiconEntryUpdate, session: Session = Depends(get_session)
) -> LexiconEntryOut:
    entry = session.get(LexiconEntry, entry_id)
    if entry is None or entry.book_id != book_id:
        raise HTTPException(status_code=404, detail="lexicon entry not found")

    if body.pattern is not None:
        entry.pattern = body.pattern
    if body.replacement is not None:
        entry.replacement = body.replacement
    if body.is_regex is not None:
        entry.is_regex = body.is_regex
    if body.enabled is not None:
        entry.enabled = body.enabled

    if entry.is_regex:
        _validate_regex(entry.pattern)

    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _out(entry)


@router.delete("/books/{book_id}/lexicon/{entry_id}", status_code=204)
def delete_lexicon_entry(book_id: int, entry_id: int, session: Session = Depends(get_session)) -> None:
    entry = session.get(LexiconEntry, entry_id)
    if entry is None or entry.book_id != book_id:
        raise HTTPException(status_code=404, detail="lexicon entry not found")
    session.delete(entry)
    session.commit()
