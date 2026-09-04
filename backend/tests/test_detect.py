from app.ingest.calibre import CalibreParser
from app.ingest.detect import detect_language, resolve_parser, sniff_format
from app.ingest.docx import DocxParser
from app.ingest.epub import EpubParser
from app.ingest.pdf import PdfParser
from app.ingest.txt import TxtParser


def test_sniff_format_by_magic_bytes(epub_path, docx_path, pdf_2col_path, txt_path):
    assert sniff_format(epub_path) == "epub"
    assert sniff_format(docx_path) == "docx"
    assert sniff_format(pdf_2col_path) == "pdf"
    assert sniff_format(txt_path) == ""  # plain text has no magic bytes to sniff


def test_resolve_parser_prefers_content_over_extension(epub_path, docx_path, pdf_2col_path, txt_path):
    assert isinstance(resolve_parser(epub_path), EpubParser)
    assert isinstance(resolve_parser(docx_path), DocxParser)
    assert isinstance(resolve_parser(pdf_2col_path), PdfParser)
    assert isinstance(resolve_parser(txt_path), TxtParser)


def test_resolve_parser_falls_back_to_extension_for_calibre_formats(tmp_path):
    path = tmp_path / "sample.mobi"
    path.write_bytes(b"not a real mobi container, just extension-based fallback")
    assert isinstance(resolve_parser(path), CalibreParser)


def test_detect_language_four_target_languages():
    assert detect_language("This is a fairly long sentence written in English for testing.") == "en"
    assert detect_language("To jest dosc dlugie zdanie napisane w jezyku polskim do testow.") == "pl"
    assert detect_language("Dies ist ein ziemlich langer Satz auf Deutsch zum Testen der Erkennung.") == "de"
    assert detect_language("这是一句用中文写的比较长的示例句子,用来测试语言检测功能。") == "zh"


def test_detect_language_returns_none_for_short_text():
    assert detect_language("hi") is None
