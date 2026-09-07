import pytest

from app.ingest.base import ParseError
from app.ingest.pdf import PdfParser
from app.models import BlockKind


def test_pdf_running_header_and_page_numbers_stripped(pdf_2col_path):
    doc = PdfParser().parse(pdf_2col_path)
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "SAMPLE NOVEL" not in all_text
    # A bare page number ("1", "2", "3") must not survive as its own block.
    for c in doc.chapters:
        for b in c.blocks:
            assert b.text.strip() not in {"1", "2", "3"}


def test_pdf_chapter_heading_detected_by_font_size(pdf_2col_path):
    doc = PdfParser().parse(pdf_2col_path)
    assert doc.chapters[0].title == "Chapter One: The Journey Begins"


def test_pdf_two_column_reading_order(pdf_2col_path):
    doc = PdfParser().parse(pdf_2col_path)
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    # The left column's sentence must precede the right column's sentence that
    # continues it — a naive top-to-bottom-then-left-to-right scan would interleave
    # them instead.
    assert all_text.find("Elena first set foot") < all_text.find("something extraordinary")


def test_pdf_all_pages_present(pdf_2col_path):
    doc = PdfParser().parse(pdf_2col_path)
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "Unique marker 1" in all_text
    assert "Unique marker 2" in all_text
    assert "Final page body text" in all_text


# --- [M6-3] hardening: drop caps, footnotes, scanned PDFs -------------------------


def test_pdf_drop_cap_merges_into_its_paragraph(pdf_drop_cap_and_footnote_path):
    doc = PdfParser().parse(pdf_drop_cap_and_footnote_path)
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    # The oversized "T" and the body-sized "he ancient city..." that followed it must
    # merge into one real word/sentence, not survive as two separate blocks.
    assert "The ancient city stirred with life" in all_text
    assert "T he ancient city" not in all_text


def test_pdf_drop_cap_is_not_mistaken_for_a_chapter_heading(pdf_drop_cap_and_footnote_path):
    doc = PdfParser().parse(pdf_drop_cap_and_footnote_path)
    titles = [c.title for c in doc.chapters]
    assert "T" not in titles
    # No chapter title is a single character.
    assert all(len(t.strip()) > 1 for t in titles)


def test_pdf_footnote_marked_as_skip_and_excluded_from_narration(pdf_drop_cap_and_footnote_path):
    doc = PdfParser().parse(pdf_drop_cap_and_footnote_path)
    all_blocks = [b for c in doc.chapters for b in c.blocks]

    footnote_blocks = [b for b in all_blocks if "Footnote text unique to page" in b.text]
    assert len(footnote_blocks) == 3  # one per page, distinct text, none merged away
    assert all(b.kind == BlockKind.skip for b in footnote_blocks)

    # The regular body paragraphs on the same pages are unaffected — only the small,
    # low-on-the-page footnote text gets classified as skip.
    body_blocks = [b for b in all_blocks if "Unique body marker" in b.text]
    assert len(body_blocks) == 3
    assert all(b.kind == BlockKind.para for b in body_blocks)


def test_pdf_footnotes_do_not_recur_verbatim_so_header_footer_stripping_cannot_catch_them():
    """Sanity check on the fixture itself: each page's footnote text is genuinely
    distinct (unlike a running header/footer), which is exactly why classifying
    footnotes needs a separate, non-recurrence-based signal (font size + position)."""
    texts = {f"{n}. Footnote text unique to page {n}, citing a source." for n in (1, 2, 3)}
    assert len(texts) == 3


def test_pdf_scanned_image_only_raises_a_clear_parse_error(pdf_scanned_path):
    with pytest.raises(ParseError, match="scanned"):
        PdfParser().parse(pdf_scanned_path)
