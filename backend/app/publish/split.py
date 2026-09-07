"""Splits a book's chapter markers into chapter-aligned "parts" that each stay under a
configurable duration limit — for platforms with an upload duration cap, most notably
YouTube's 12h. A part never cuts a chapter in half: chapters are packed into a part
until the *next* chapter would push it over the limit, then a new part starts. See
PLAN.md 'publish/'.
"""
from dataclasses import dataclass

from ..audio.encode import ChapterMarker

#: YouTube's own cap is 12h; this default leaves 15 minutes of headroom.
DEFAULT_PART_LIMIT_S = 11 * 3600 + 45 * 60


@dataclass(frozen=True)
class Part:
    index: int  # 1-based
    start_s: float  # offset into the original, unsplit track
    end_s: float
    #: chapter markers re-based so this part's own start is t=0 — ready to hand
    #: straight to an M4B-style chapter embedder for this part alone, if ever needed.
    chapters: list[ChapterMarker]


def split_into_parts(markers: list[ChapterMarker], *, limit_s: float = DEFAULT_PART_LIMIT_S) -> list[Part]:
    """Greedily packs consecutive chapters into parts. A single chapter longer than
    `limit_s` on its own still becomes its own (over-limit) part rather than being cut
    mid-chapter, which would break its own marker and the audio it describes."""
    if not markers:
        return []

    parts: list[Part] = []
    current: list[ChapterMarker] = []
    part_start = markers[0].start_s

    for marker in markers:
        if current and (marker.end_s - part_start) > limit_s:
            parts.append(_build_part(len(parts) + 1, part_start, current))
            current = []
            part_start = marker.start_s
        current.append(marker)

    if current:
        parts.append(_build_part(len(parts) + 1, part_start, current))
    return parts


def _build_part(index: int, part_start: float, chapters: list[ChapterMarker]) -> Part:
    rebased = [
        ChapterMarker(start_s=c.start_s - part_start, end_s=c.end_s - part_start, title=c.title)
        for c in chapters
    ]
    return Part(index=index, start_s=part_start, end_s=chapters[-1].end_s, chapters=rebased)


def part_filename(base_name: str, extension: str, index: int, total: int) -> str:
    """`total == 1` (no split needed) keeps the plain, pre-existing filename — splitting
    must never rename a book's output when it doesn't actually apply."""
    if total <= 1:
        return f"{base_name}.{extension}"
    return f"{base_name} - Part {index} of {total}.{extension}"


def part_title(book_title: str, index: int, total: int) -> str:
    if total <= 1:
        return book_title
    return f"{book_title} — Part {index} of {total}"
