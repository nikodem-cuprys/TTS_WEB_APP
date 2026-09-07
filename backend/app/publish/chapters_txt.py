"""Builds a YouTube-ready video description: a title/author header plus the
`00:00 Chapter Title` timestamp block YouTube auto-detects as video chapters when it
appears in an eligible video's description. Built from the same `ChapterMarker` list
[M5-1]'s M4B chapters use — genuinely free, no separate alignment step. See PLAN.md
'publish/'.
"""
from ..audio.encode import ChapterMarker


def _format_timestamp(seconds: float) -> str:
    """YouTube's own accepted formats are `H:MM:SS` or `M:SS` — hours only appear once
    the video passes the one-hour mark."""
    total_seconds = max(0, round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_chapter_timestamps(markers: list[ChapterMarker]) -> str:
    """Just the `00:00 Chapter Title` block. YouTube requires the *first* line to start
    at 0:00 to recognize the block as chapters at all — guaranteed here because
    `_build_chapter_markers()` (pipeline/runner.py) always starts from the first
    enabled chapter's first segment, which always begins at t=0."""
    return "\n".join(f"{_format_timestamp(m.start_s)} {m.title}" for m in markers) + "\n"


def build_youtube_description(
    markers: list[ChapterMarker], *, title: str, author: str | None = None,
) -> str:
    """A description block ready to paste straight into YouTube's upload form: the
    book's title/author as a header, then the chapters timestamp block."""
    header = [title]
    if author:
        header.append(author)
    return "\n".join(header) + "\n\n" + build_chapter_timestamps(markers)
