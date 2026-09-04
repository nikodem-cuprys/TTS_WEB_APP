"""Shared chapter-heading text patterns, used by parsers that don't have a reliable
structural source of chapter titles (TXT always; PDF as a fallback when there's no
outline/TOC and no font-size signal). See PLAN.md 'ingest/pdf.py'.
"""
import re

CHAPTER_WORD_RE = re.compile(
    r"^(chapter|rozdzia[łl]|kapitel|第\s*[0-9一二三四五六七八九十百千]+\s*[章节])"
    r"[\s.:]*([ivxlcdm]+|\d+|[一二三四五六七八九十百千]+)?\s*[-:.]?\s*(.*)$",
    re.IGNORECASE,
)
_STANDALONE_TITLE_RE = re.compile(r"^[A-ZĄĆĘŁŃÓŚŹŻÄÖÜß0-9][^.!?]{0,59}$")


def looks_like_heading(line: str) -> bool:
    """True for a short line that reads as a chapter/section title on its own."""
    stripped = line.strip()
    if not stripped:
        return False
    if CHAPTER_WORD_RE.match(stripped):
        return True
    return bool(_STANDALONE_TITLE_RE.match(stripped)) and len(stripped) <= 60
