from app.ingest.txt import TxtParser


def test_txt_chapter_split_on_headings(txt_path):
    doc = TxtParser().parse(txt_path)
    assert [c.title for c in doc.chapters] == ["Chapter 1: The Beginning", "Chapter 2"]


def test_txt_paragraphs_join_wrapped_lines(txt_path):
    doc = TxtParser().parse(txt_path)
    ch1 = doc.chapters[0]
    assert ch1.blocks[0].text == (
        "It was a dark and stormy night. The wind howled through the trees, "
        "carrying with it the scent of rain."
    )


def test_txt_cp1250_polish_encoding_detected(tmp_path):
    text = "Rozdział pierwszy\n\nDzień dobry, jak się masz? Polskie znaki: ąćęłńóśźż."
    path = tmp_path / "polish.txt"
    path.write_text(text, encoding="cp1250")

    doc = TxtParser().parse(path)
    assert doc.chapters[0].title == "Rozdział pierwszy"
    assert "ąćęłńóśźż" in doc.chapters[0].blocks[0].text


def test_txt_no_headings_becomes_single_chapter(tmp_path):
    path = tmp_path / "flat.txt"
    path.write_text("Just one paragraph of plain prose with no chapter markers at all.")
    doc = TxtParser().parse(path)
    assert len(doc.chapters) == 1
