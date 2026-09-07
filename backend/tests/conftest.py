"""Generates small, deterministic book fixtures at test time (rather than committing
binary files) for each format the ingest layer supports."""
import pymupdf
import pytest
from docx import Document as DocxDocument
from ebooklib import epub


@pytest.fixture
def epub_path(tmp_path):
    book = epub.EpubBook()
    book.set_identifier("test-book-1")
    book.set_title("Sample Book")
    book.set_language("en")
    book.add_author("Jane Author")

    c1 = epub.EpubHtml(title="Chapter One", file_name="chap1.xhtml", lang="en")
    c1.content = (
        "<html><body><h1>Chapter One</h1>"
        "<p>First paragraph.</p><p>Second paragraph.</p></body></html>"
    )
    c2 = epub.EpubHtml(title="Chapter Two", file_name="chap2.xhtml", lang="en")
    c2.content = (
        "<html><body><h1>Chapter Two</h1>"
        "<blockquote>A quoted line.</blockquote><p>More text.</p></body></html>"
    )
    book.add_item(c1)
    book.add_item(c2)
    book.toc = (epub.Link("chap1.xhtml", "Chapter One", "c1"), epub.Link("chap2.xhtml", "Chapter Two", "c2"))
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = ["nav", c1, c2]

    path = tmp_path / "sample.epub"
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def docx_path(tmp_path):
    doc = DocxDocument()
    doc.core_properties.title = "My DOCX Book"
    doc.core_properties.author = "Some Author"
    doc.add_heading("Chapter One", level=1)
    doc.add_paragraph("First paragraph of chapter one.")
    doc.add_paragraph("A quoted line.", style="Intense Quote")
    doc.add_heading("A subsection", level=2)
    doc.add_paragraph("More text here.")
    doc.add_heading("Chapter Two", level=1)
    doc.add_paragraph("Second chapter text.")

    path = tmp_path / "sample.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def txt_path(tmp_path):
    text = (
        "Chapter 1: The Beginning\n\n"
        "It was a dark and stormy night. The wind howled through the trees,\n"
        "carrying with it the scent of rain.\n\n"
        "She walked slowly toward the old house, unsure of what awaited her\n"
        "inside.\n\n"
        "Chapter 2\n\n"
        "The door creaked open on its own.\n\n"
        '"Hello?" she called out, her voice trembling.\n'
    )
    path = tmp_path / "sample.txt"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def pdf_2col_path(tmp_path):
    """A 2-page, 2-column PDF with a running header and page-number footer on every
    page, and a larger-font chapter heading on the first page only."""
    doc = pymupdf.open()
    W, H = 500, 700
    paras = [
        "It was a dark and stormy night when Elena first set foot on the ancient bridge "
        "that connected the two halves of the city.",
        "The wind howled through the trees, carrying with it the scent of rain and "
        "something extraordinary that she could not quite place at first.",
    ]

    for page_num in (1, 2):
        page = doc.new_page(width=W, height=H)
        page.insert_text((40, 30), "SAMPLE NOVEL", fontsize=8)
        page.insert_text((W / 2 - 5, H - 20), str(page_num), fontsize=9)
        if page_num == 1:
            page.insert_text((40, 70), "Chapter One: The Journey Begins", fontsize=16)
            top = 100
        else:
            top = 60
        body = " ".join(paras) + f" Unique marker {page_num}."
        col_w = (W - 80 - 20) / 2
        left_rect = pymupdf.Rect(40, top, 40 + col_w, H - 50)
        right_rect = pymupdf.Rect(40 + col_w + 20, top, W - 40, H - 50)
        split_at = body.find(" ", len(body) // 2)
        page.insert_textbox(left_rect, body[:split_at], fontsize=10)
        page.insert_textbox(right_rect, body[split_at + 1 :], fontsize=10)

    # A 3rd page keeps header/footer stripping's recurrence threshold satisfied
    # (it requires >= 3 pages to trust a repeating signature over a one-off).
    page = doc.new_page(width=W, height=H)
    page.insert_text((40, 30), "SAMPLE NOVEL", fontsize=8)
    page.insert_text((W / 2 - 5, H - 20), "3", fontsize=9)
    page.insert_textbox(pymupdf.Rect(40, 60, W - 40, H - 50), "Final page body text.", fontsize=10)

    path = tmp_path / "sample_2col.pdf"
    doc.save(str(path))
    return path


@pytest.fixture
def pdf_drop_cap_and_footnote_path(tmp_path):
    """A 3-page, single-column PDF whose first page opens with a drop-cap first letter
    (a large-font "T" immediately followed by the rest of the word/sentence at body
    size) and whose every page carries a small-font footnote near the bottom — distinct
    text per page, so it can't be mistaken for a recurring header/footer."""
    doc = pymupdf.open()
    W, H = 500, 700
    body_size = 11
    drop_cap_size = 11 * 3  # towers over body text, like a real illuminated capital
    footnote_size = 7  # noticeably smaller than body text

    for page_num in (1, 2, 3):
        page = doc.new_page(width=W, height=H)
        if page_num == 1:
            # The drop cap and the rest of the word are two separate text insertions
            # (as real drop-cap layouts produce) but sit on the same visual line.
            page.insert_text((40, 110), "T", fontsize=drop_cap_size)
            page.insert_textbox(
                pymupdf.Rect(75, 90, W - 40, 140),
                "he ancient city stirred with life as dawn broke over the quiet harbor.",
                fontsize=body_size,
            )
            body_top = 160
        else:
            page.insert_textbox(
                pymupdf.Rect(40, 60, W - 40, 140),
                f"Page {page_num} continues the story with an entirely ordinary paragraph "
                "of body text, long enough to fill a couple of lines.",
                fontsize=body_size,
            )
            body_top = 160
        page.insert_textbox(
            pymupdf.Rect(40, body_top, W - 40, H - 120),
            f"Unique body marker {page_num}.",
            fontsize=body_size,
        )
        # Footnote zone (~80% down the page): distinct text per page, well below body
        # text and well above the very bottom, in a noticeably smaller font.
        page.insert_textbox(
            pymupdf.Rect(40, H - 130, W - 40, H - 100),
            f"{page_num}. Footnote text unique to page {page_num}, citing a source.",
            fontsize=footnote_size,
        )

    path = tmp_path / "sample_hardening.pdf"
    doc.save(str(path))
    return path


@pytest.fixture
def pdf_scanned_path(tmp_path):
    """A PDF with no extractable text at all — every page is a plain image, the way a
    scanned book typically comes through."""
    doc = pymupdf.open()
    W, H = 500, 700
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pix.set_rect(pix.irect, (255, 255, 255))
    image_bytes = pix.tobytes("png")

    for _ in range(2):
        page = doc.new_page(width=W, height=H)
        page.insert_image(pymupdf.Rect(50, 50, 450, 650), stream=image_bytes)

    path = tmp_path / "sample_scanned.pdf"
    doc.save(str(path))
    return path
