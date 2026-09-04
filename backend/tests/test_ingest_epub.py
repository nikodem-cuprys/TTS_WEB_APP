from app.ingest.epub import EpubParser
from app.models import BlockKind


def test_epub_chapter_count_and_titles(epub_path):
    doc = EpubParser().parse(epub_path)
    assert [c.title for c in doc.chapters] == ["Chapter One", "Chapter Two"]


def test_epub_metadata(epub_path):
    doc = EpubParser().parse(epub_path)
    assert doc.title == "Sample Book"
    assert doc.author == "Jane Author"
    assert doc.language == "en"


def test_epub_block_kinds_and_text(epub_path):
    doc = EpubParser().parse(epub_path)
    ch1, ch2 = doc.chapters
    assert [b.kind for b in ch1.blocks] == [BlockKind.heading, BlockKind.para, BlockKind.para]
    assert [b.text for b in ch1.blocks] == ["Chapter One", "First paragraph.", "Second paragraph."]
    assert ch2.blocks[0].kind == BlockKind.heading
    assert ch2.blocks[1].kind == BlockKind.quote
    assert ch2.blocks[1].text == "A quoted line."


def test_epub_nav_document_not_narrated(epub_path):
    doc = EpubParser().parse(epub_path)
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "Chapter One" in all_text  # sanity: real content survived
    assert "nav" not in all_text.lower()
