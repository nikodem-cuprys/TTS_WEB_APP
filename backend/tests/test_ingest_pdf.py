from app.ingest.pdf import PdfParser


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
