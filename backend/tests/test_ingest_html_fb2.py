from app.ingest.fb2 import Fb2Parser
from app.ingest.html import HtmlParser


def test_html_boilerplate_stripped_and_chapters_split(tmp_path):
    html = """<!DOCTYPE html><html lang="en-US">
    <head><title>My Web Book</title><script>alert(1)</script></head>
    <body>
    <nav>Site nav</nav><header>Site header</header>
    <h1>Chapter One</h1><p>First paragraph.</p>
    <h1>Chapter Two</h1><p>Second paragraph.</p>
    <footer>Site footer</footer>
    </body></html>"""
    path = tmp_path / "sample.html"
    path.write_text(html, encoding="utf-8")

    doc = HtmlParser().parse(path)
    assert doc.title == "My Web Book"
    assert doc.language == "en"
    assert [c.title for c in doc.chapters] == ["Chapter One", "Chapter Two"]
    all_text = " ".join(b.text for c in doc.chapters for b in c.blocks)
    assert "nav" not in all_text.lower()
    assert "footer" not in all_text.lower()


def test_fb2_sections_and_footnote_body_excluded(tmp_path):
    fb2 = """<?xml version="1.0" encoding="utf-8"?>
    <FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
    <description><title-info><book-title>My FB2 Book</book-title>
    <author><first-name>Jan</first-name><last-name>Kowalski</last-name></author>
    <lang>pl</lang></title-info></description>
    <body>
      <section><title><p>Rozdzial pierwszy</p></title><p>Pierwszy akapit.</p></section>
      <section><title><p>Rozdzial drugi</p></title><p>Drugi akapit.</p></section>
    </body>
    <body name="notes">
      <section><title><p>Notes</p></title><p>Should not become a chapter.</p></section>
    </body>
    </FictionBook>"""
    path = tmp_path / "sample.fb2"
    path.write_text(fb2, encoding="utf-8")

    doc = Fb2Parser().parse(path)
    assert doc.title == "My FB2 Book"
    assert doc.author == "Jan Kowalski"
    assert [c.title for c in doc.chapters] == ["Rozdzial pierwszy", "Rozdzial drugi"]
