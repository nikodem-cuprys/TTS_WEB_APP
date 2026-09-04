"""Format sniffing by magic bytes (never trust the extension alone) and language
detection on parsed prose, used to preselect the voice before the user confirms it.
See PLAN.md 'ingest/detect.py'.
"""
import zipfile
from pathlib import Path

from lingua import LanguageDetectorBuilder

from .base import Parser, ParseError
from .calibre import CalibreParser
from .docx import DocxParser
from .epub import EpubParser
from .fb2 import Fb2Parser
from .html import HtmlParser
from .pdf import PdfParser
from .txt import TxtParser

# Order matters only in that more specific formats are checked before generic fallbacks.
PARSERS: list[Parser] = [
    EpubParser(),
    DocxParser(),
    PdfParser(),
    Fb2Parser(),
    HtmlParser(),
    CalibreParser(),
    TxtParser(),  # last: the catch-all for anything that decodes as text
]

_detector = None


def _get_language_detector():
    global _detector
    if _detector is None:
        _detector = LanguageDetectorBuilder.from_all_languages().build()
    return _detector


def sniff_format(path: Path) -> str:
    """Best-effort format identification from file content, independent of extension.
    Returns one of the Parser.extensions values, or "" if nothing recognized it."""
    try:
        head = path.open("rb").read(2048)
    except OSError:
        return ""

    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")  # skip BOM/whitespace

    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if stripped.startswith(b"<?xml"):
        if b"FictionBook" in head:
            return "fb2"
        if b"<html" in head.lower() or b"<!doctype html" in head.lower():
            return "html"
    if stripped[:5].lower() in (b"<html", b"<!doc"):
        return "html"
    if head[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                if "mimetype" in names:
                    mimetype = zf.read("mimetype").strip()
                    if mimetype == b"application/epub+zip":
                        return "epub"
                if "word/document.xml" in names:
                    return "docx"
        except (zipfile.BadZipFile, OSError):
            pass
    if len(head) > 68 and head[60:68] in (b"BOOKMOBI", b"TEXtREAd"):
        return "mobi"

    return ""


def resolve_parser(path: Path) -> Parser:
    """Picks a parser for `path` by content sniffing first, falling back to the
    extension when sniffing is inconclusive (e.g. a plain-text file has no magic bytes)."""
    sniffed = sniff_format(path)
    if sniffed:
        for parser in PARSERS:
            if sniffed in parser.extensions:
                return parser

    for parser in PARSERS:
        if parser.can_parse(path):
            return parser

    raise ParseError(f"no parser recognizes {path.name} (sniffed format: {sniffed or 'unknown'})")


def detect_language(sample_text: str) -> str | None:
    """Returns a best-guess ISO 639-1 code for `sample_text`, or None if undetectable.
    Any language may come back, not just en/pl/de/zh — routing an unsupported result to
    a fallback voice is the TTS registry's job (M4), not ingest's."""
    sample_text = sample_text.strip()
    if len(sample_text) < 20:
        return None
    detector = _get_language_detector()
    language = detector.detect_language_of(sample_text)
    if language is None:
        return None
    return language.iso_code_639_1.name.lower()
