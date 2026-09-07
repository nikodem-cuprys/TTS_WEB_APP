"""PDF parser: the hard one. PDFs carry no semantic structure, only positioned text, so
this reconstructs paragraphs, drops running headers/footers/page numbers, orders
multi-column layouts, de-hyphenates line-end word breaks, merges drop-cap first
letters back into their paragraph, marks footnote-zone text so it's excluded from
narration by default, and finds chapter boundaries from the outline when present or
from font-size/heading-pattern heuristics otherwise. [M6-3] hardened this against
scanned (image-only) PDFs, drop caps, and footnotes; this covers the common case,
plus those. See PLAN.md 'ingest/pdf.py'.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..models import BlockKind
from .base import ParseError
from .document import DocBlock, DocChapter, Document
from .heading import CHAPTER_WORD_RE

_HEADER_ZONE = 0.10  # top fraction of the page treated as header territory
_FOOTER_ZONE = 0.90  # blocks below this fraction of the page are footer territory
_FULL_WIDTH_FRAC = 0.65  # a block this wide (relative to the page) breaks columns
_COLUMN_GAP_PT = 40  # x0 gap that separates two columns
_PAGE_NUM_RE = re.compile(r"^\s*(page\s+)?[ivxlcdm\d]+\s*(of\s+[ivxlcdm\d]+)?\s*$", re.IGNORECASE)

#: [M6-3] a drop cap's oversized single letter must not be mistaken for a chapter
#: heading (the existing heading heuristic alone would happily do that at 1.3x body
#: size) and must not become its own stray one-character block — it's merged back into
#: the paragraph that follows it. A real drop cap towers over a heading, not just the
#: body text, hence the much higher ratio than _is_heading_block's.
_DROP_CAP_MAX_CHARS = 2
_DROP_CAP_SIZE_RATIO = 1.8

#: [M6-3] footnotes sit low on the page like a footer, but — unlike a running
#: footer/page-number — they differ page to page, so the recurrence-based
#: _strip_headers_footers() below never catches them. What does distinguish a footnote
#: from ordinary bottom-of-page body text is that it's set noticeably smaller than the
#: body font; this only fires below the header/footer's own footer zone, so it can't
#: also swallow a legitimate short bottom-of-page paragraph in body-sized type.
_FOOTNOTE_ZONE = 0.78
_FOOTNOTE_SIZE_RATIO = 0.85


@dataclass
class _PdfBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    max_size: float
    page: int


def _merge_drop_cap_lines(lines: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """[M6-3] pymupdf extracts a drop cap and the rest of its opening word as two
    separate "lines" *within the same block* (it splits a line wherever the font size
    changes), even though visually they're one line of one paragraph. The normal
    line-join a few steps later (a space — correct for real wrapped lines) would
    otherwise turn that into "T he ancient..." instead of "The ancient...". Detected
    purely from the two lines' own text/size — a short, alphabetic line immediately
    followed by a markedly smaller one — so it needs no document-wide body-font-size
    estimate and works before one is even available."""
    merged: list[tuple[str, float]] = []
    i = 0
    while i < len(lines):
        text, size = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        stripped = text.strip()
        is_drop_cap = (
            nxt is not None
            and stripped.isalpha()
            and len(stripped) <= _DROP_CAP_MAX_CHARS
            and not CHAPTER_WORD_RE.match(stripped)
            and nxt[1] > 0
            and size >= nxt[1] * _DROP_CAP_SIZE_RATIO
        )
        if is_drop_cap:
            merged.append((stripped + nxt[0], nxt[1]))
            i += 2
            continue
        merged.append((text, size))
        i += 1
    return merged


def _page_blocks(page: "pymupdf.Page", page_index: int) -> list[_PdfBlock]:
    blocks: list[_PdfBlock] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:  # skip images etc.
            continue
        raw_lines: list[tuple[str, float]] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(s["text"] for s in spans)
            if not line_text.strip():
                continue
            line_size = max((s.get("size", 0.0) for s in spans), default=0.0)
            raw_lines.append((line_text, line_size))
        if not raw_lines:
            continue
        merged_lines = _merge_drop_cap_lines(raw_lines)
        text = "\n".join(t for t, _ in merged_lines).strip()
        if not text:
            continue
        max_size = max(size for _, size in merged_lines)
        x0, y0, x1, y1 = block["bbox"]
        blocks.append(_PdfBlock(x0, y0, x1, y1, text, max_size, page_index))
    return blocks


def _normalize_signature(text: str) -> str:
    sig = re.sub(r"\d+", "#", text.strip().lower())
    return re.sub(r"\s+", " ", sig)


def _strip_headers_footers(pages: list[list[_PdfBlock]], page_height: float) -> list[list[_PdfBlock]]:
    total_pages = len(pages)
    if total_pages < 3:
        # Not enough pages to tell a repeating header from a one-off, so leave as-is;
        # a lone header/footer misread here is corrected by the chapter-editing UI (M3-3).
        return pages

    header_top = page_height * _HEADER_ZONE
    footer_bottom = page_height * _FOOTER_ZONE

    def zone_of(b: _PdfBlock) -> str | None:
        if b.y1 <= header_top:
            return "header"
        if b.y0 >= footer_bottom:
            return "footer"
        return None

    signature_counts: dict[tuple[str, str, int], int] = {}
    for page_blocks in pages:
        for b in page_blocks:
            zone = zone_of(b)
            if zone is None:
                continue
            key = (zone, _normalize_signature(b.text), round(b.x0 / 20))
            signature_counts[key] = signature_counts.get(key, 0) + 1

    min_recurrence = max(3, (total_pages + 1) // 2)
    recurring_signatures = {k for k, count in signature_counts.items() if count >= min_recurrence}

    cleaned: list[list[_PdfBlock]] = []
    for page_blocks in pages:
        kept = []
        for b in page_blocks:
            zone = zone_of(b)
            if zone is None:
                kept.append(b)
                continue
            key = (zone, _normalize_signature(b.text), round(b.x0 / 20))
            if key in recurring_signatures:
                continue
            if _PAGE_NUM_RE.match(b.text.replace("\n", " ")):
                continue
            kept.append(b)
        cleaned.append(kept)
    return cleaned


def _order_columns(blocks: list[_PdfBlock]) -> list[_PdfBlock]:
    if len(blocks) <= 1:
        return list(blocks)
    xs = sorted(b.x0 for b in blocks)
    clusters: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > _COLUMN_GAP_PT:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    if len(clusters) != 2:
        return sorted(blocks, key=lambda b: (b.y0, b.x0))
    left_max = max(clusters[0])
    right_min = min(clusters[1])
    left = sorted((b for b in blocks if b.x0 <= left_max), key=lambda b: b.y0)
    right = sorted((b for b in blocks if b.x0 >= right_min), key=lambda b: b.y0)
    return left + right


def _reading_order(page_blocks: list[_PdfBlock], page_width: float) -> list[_PdfBlock]:
    threshold = page_width * _FULL_WIDTH_FRAC
    ordered: list[_PdfBlock] = []
    segment: list[_PdfBlock] = []
    for b in sorted(page_blocks, key=lambda b: b.y0):
        if (b.x1 - b.x0) >= threshold:
            ordered.extend(_order_columns(segment))
            segment = []
            ordered.append(b)
        else:
            segment.append(b)
    ordered.extend(_order_columns(segment))
    return ordered


def _clean_text(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line-end word breaks
    text = re.sub(r"\s*\n\s*", " ", text)  # join wrapped lines within a paragraph block
    return re.sub(r"\s+", " ", text).strip()


def _is_heading_block(b: _PdfBlock, body_font_size: float) -> bool:
    text = b.text.strip()
    if len(text) > 120 or "\n" in text:
        return False
    if CHAPTER_WORD_RE.match(text):
        return True
    if len(text) <= _DROP_CAP_MAX_CHARS:
        # An un-merged drop cap (e.g. the very last block in the document, with no
        # following paragraph to merge into) is an oversized lone letter, not a
        # heading — without this it would trip the font-size check below and split
        # off a bogus one-letter "chapter."
        return False
    return body_font_size > 0 and b.max_size >= body_font_size * 1.3


def _looks_like_drop_cap(b: _PdfBlock, body_font_size: float) -> bool:
    text = b.text.strip()
    if not text or len(text) > _DROP_CAP_MAX_CHARS or not text.isalpha():
        return False
    if CHAPTER_WORD_RE.match(text):
        return False
    return body_font_size > 0 and b.max_size >= body_font_size * _DROP_CAP_SIZE_RATIO


def _merge_drop_caps(blocks: list[_PdfBlock], body_font_size: float) -> list[_PdfBlock]:
    """A drop cap is its own oversized single-letter text block, immediately before the
    paragraph it actually belongs to — merged back in here (no separator: "T" +
    "he city stirred..." -> "The city stirred...") rather than left to become either a
    bogus one-letter chapter heading or a stray one-letter paragraph of its own."""
    merged: list[_PdfBlock] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if _looks_like_drop_cap(b, body_font_size) and nxt is not None and nxt.page == b.page:
            merged.append(
                _PdfBlock(
                    x0=b.x0, y0=b.y0, x1=nxt.x1, y1=nxt.y1,
                    text=b.text.strip() + nxt.text, max_size=nxt.max_size, page=nxt.page,
                )
            )
            i += 2
            continue
        merged.append(b)
        i += 1
    return merged


def _is_footnote_block(b: _PdfBlock, page_height: float, body_font_size: float) -> bool:
    if body_font_size <= 0 or page_height <= 0:
        return False
    return b.y0 >= page_height * _FOOTNOTE_ZONE and b.max_size <= body_font_size * _FOOTNOTE_SIZE_RATIO


def _classify_kind(b: _PdfBlock, page_height: float, body_font_size: float) -> BlockKind:
    if _is_footnote_block(b, page_height, body_font_size):
        return BlockKind.skip
    if _is_heading_block(b, body_font_size):
        return BlockKind.heading
    return BlockKind.para


def _body_font_size(all_blocks: list[_PdfBlock]) -> float:
    sizes: dict[float, int] = {}
    for b in all_blocks:
        rounded = round(b.max_size)
        sizes[rounded] = sizes.get(rounded, 0) + len(b.text)
    if not sizes:
        return 0.0
    return float(max(sizes, key=lambda s: sizes[s]))


def _chapters_from_outline(
    doc: "pymupdf.Document", ordered_blocks: list[_PdfBlock], page_height: float, body_font_size: float
) -> list[DocChapter] | None:
    toc = doc.get_toc(simple=True)
    if not toc:
        return None
    top_level = min(entry[0] for entry in toc)
    entries = [(title, page - 1) for level, title, page in toc if level == top_level]
    entries.sort(key=lambda e: e[1])

    chapters: list[DocChapter] = []
    chapter_index = 0

    def blocks_in_range(start_page: int, end_page: int) -> list[DocBlock]:
        return [
            DocBlock(kind=_classify_kind(b, page_height, body_font_size), text=_clean_text(b.text))
            for b in ordered_blocks
            if start_page <= b.page < end_page
        ]

    if entries[0][1] > 0:
        front = blocks_in_range(0, entries[0][1])
        if front:
            chapters.append(DocChapter(index=chapter_index, title="Front Matter", blocks=front))
            chapter_index += 1

    for i, (title, start_page) in enumerate(entries):
        end_page = entries[i + 1][1] if i + 1 < len(entries) else 10**9
        blocks = blocks_in_range(start_page, end_page)
        if not blocks:
            continue
        chapters.append(DocChapter(index=chapter_index, title=title, blocks=blocks))
        chapter_index += 1

    return chapters or None


def _chapters_from_headings(
    ordered_blocks: list[_PdfBlock], page_height: float, body_font_size: float
) -> list[DocChapter]:
    chapters: list[DocChapter] = []
    current_blocks: list[DocBlock] = []
    current_title = "Chapter 1"
    chapter_index = 0
    seen_heading = False

    def flush() -> None:
        nonlocal chapter_index, current_blocks, current_title
        if current_blocks:
            chapters.append(DocChapter(index=chapter_index, title=current_title, blocks=current_blocks))
            chapter_index += 1
        current_blocks = []

    for b in ordered_blocks:
        kind = _classify_kind(b, page_height, body_font_size)
        if kind == BlockKind.heading:
            flush()
            current_title = b.text.strip()
            seen_heading = True
            continue
        current_blocks.append(DocBlock(kind=kind, text=_clean_text(b.text)))
    flush()

    if not seen_heading:
        blocks = [
            DocBlock(kind=_classify_kind(b, page_height, body_font_size), text=_clean_text(b.text))
            for b in ordered_blocks
        ]
        return [DocChapter(index=0, title="Chapter 1", blocks=blocks)] if blocks else []

    return chapters


class PdfParser:
    extensions = ("pdf",)

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def parse(self, path: Path) -> Document:
        try:
            doc = pymupdf.open(str(path))
        except Exception as exc:
            raise ParseError(f"could not open PDF {path}: {exc}") from exc

        if doc.page_count == 0:
            raise ParseError(f"{path} has no pages")

        page_height = doc[0].rect.height
        page_width = doc[0].rect.width

        per_page_blocks = [_page_blocks(doc[i], i) for i in range(doc.page_count)]
        per_page_blocks = _strip_headers_footers(per_page_blocks, page_height)

        ordered_blocks: list[_PdfBlock] = []
        for page_blocks in per_page_blocks:
            ordered_blocks.extend(_reading_order(page_blocks, page_width))

        if not ordered_blocks:
            raise ParseError(f"{path} contains no extractable text (it may be a scanned image PDF)")

        body_font_size = _body_font_size(ordered_blocks)
        ordered_blocks = _merge_drop_caps(ordered_blocks, body_font_size)
        chapters = _chapters_from_outline(doc, ordered_blocks, page_height, body_font_size)
        if chapters is None:
            chapters = _chapters_from_headings(ordered_blocks, page_height, body_font_size)

        if not chapters:
            raise ParseError(f"{path} produced no chapters")

        metadata = doc.metadata or {}
        title = metadata.get("title") or path.stem
        author = metadata.get("author") or None

        return Document(title=title, author=author, language="und", chapters=chapters)
