from app.ingest.docx import DocxParser
from app.models import BlockKind


def test_docx_chapter_count_and_titles(docx_path):
    doc = DocxParser().parse(docx_path)
    assert [c.title for c in doc.chapters] == ["Chapter One", "Chapter Two"]


def test_docx_metadata(docx_path):
    doc = DocxParser().parse(docx_path)
    assert doc.title == "My DOCX Book"
    assert doc.author == "Some Author"


def test_docx_heading_2_stays_inside_chapter_one(docx_path):
    doc = DocxParser().parse(docx_path)
    ch1 = doc.chapters[0]
    kinds_and_text = [(b.kind, b.text) for b in ch1.blocks]
    assert (BlockKind.para, "First paragraph of chapter one.") in kinds_and_text
    assert (BlockKind.quote, "A quoted line.") in kinds_and_text
    assert (BlockKind.heading, "A subsection") in kinds_and_text
    assert (BlockKind.para, "More text here.") in kinds_and_text
