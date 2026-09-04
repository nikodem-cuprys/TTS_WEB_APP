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
