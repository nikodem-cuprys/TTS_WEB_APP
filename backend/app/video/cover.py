"""Generates a placeholder cover — dark/green theme, title + author — with Pillow,
used whenever a book's source file carries no cover image of its own. Generated fresh
per render rather than cached on the book row, so an edited title/author is always
reflected rather than baked in once at ingest and going stale. See PLAN.md
'video/cover.py'.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: square — a safe aspect for both audiobook cover art and MP4/YouTube thumbnails.
_SIZE = 1600
#: theme.css tokens (dark/grey/green — see theme.css's :root block).
_BG = (14, 16, 17)          # --bg
_ACCENT = (62, 207, 142)    # --accent
_TEXT = (230, 234, 234)     # --text
_TEXT_2 = (154, 164, 166)   # --text-2

_MARGIN = 160
_FRAME_INSET = 56
_FRAME_WIDTH = 3
_TITLE_MAX_SIZE = 108
_TITLE_MIN_SIZE = 40
_TITLE_STEP = 8
_MAX_TITLE_LINES = 5
_AUTHOR_SIZE = 52
_TITLE_LINE_SPACING = 1.35
_TITLE_AUTHOR_GAP = 44


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_title(
    draw: ImageDraw.ImageDraw, title: str, max_width: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Shrinks the title font until it wraps to at most `_MAX_TITLE_LINES` lines within
    `max_width`, so an unusually long title never overflows the cover."""
    size = _TITLE_MAX_SIZE
    while size >= _TITLE_MIN_SIZE:
        font = ImageFont.load_default(size=size)
        lines = _wrap_text(draw, title, font, max_width)
        if len(lines) <= _MAX_TITLE_LINES:
            return font, lines
        size -= _TITLE_STEP
    font = ImageFont.load_default(size=_TITLE_MIN_SIZE)
    return font, _wrap_text(draw, title, font, max_width)


def generate_cover(output_path: Path, *, title: str, author: str | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (_SIZE, _SIZE), _BG)
    draw = ImageDraw.Draw(img)

    # a thin accent frame, matching theme.css's flat-surface/1px-border aesthetic
    # (no gradients or shadows).
    draw.rectangle(
        [_FRAME_INSET, _FRAME_INSET, _SIZE - _FRAME_INSET, _SIZE - _FRAME_INSET],
        outline=_ACCENT, width=_FRAME_WIDTH,
    )

    max_text_width = _SIZE - 2 * _MARGIN
    title_font, title_lines = _fit_title(draw, title.strip() or "Untitled", max_text_width)
    bbox = title_font.getbbox("Ag")
    title_line_height = (bbox[3] - bbox[1]) * _TITLE_LINE_SPACING
    title_block_height = title_line_height * len(title_lines)

    author_text = author.strip() if author else ""
    author_font = ImageFont.load_default(size=_AUTHOR_SIZE) if author_text else None
    author_height = _AUTHOR_SIZE * _TITLE_LINE_SPACING if author_text else 0
    gap = _TITLE_AUTHOR_GAP if author_text else 0

    total_height = title_block_height + gap + author_height
    y = (_SIZE - total_height) / 2

    for line in title_lines:
        width = draw.textlength(line, font=title_font)
        draw.text(((_SIZE - width) / 2, y), line, font=title_font, fill=_TEXT)
        y += title_line_height

    if author_text and author_font is not None:
        y += gap
        width = draw.textlength(author_text, font=author_font)
        draw.text(((_SIZE - width) / 2, y), author_text, font=author_font, fill=_TEXT_2)

    img.save(output_path)
    return output_path
