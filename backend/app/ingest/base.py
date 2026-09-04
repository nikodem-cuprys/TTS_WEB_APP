"""Parser protocol every format-specific ingester implements. See PLAN.md 'ingest/base.py'."""
from pathlib import Path
from typing import Protocol, runtime_checkable

from .document import Document


class ParseError(Exception):
    """Raised when a file matches a parser's format but cannot be parsed."""


class ParserUnavailableError(Exception):
    """Raised when a parser needs an external tool (e.g. Calibre) that isn't installed.

    The API layer catches this to mark the format unavailable with an install hint,
    rather than surfacing it as a generic upload failure.
    """


@runtime_checkable
class Parser(Protocol):
    #: lowercase file extensions this parser handles, without the leading dot.
    extensions: tuple[str, ...]

    def can_parse(self, path: Path) -> bool:
        """Cheap check (extension and/or magic bytes) — must not raise."""
        ...

    def parse(self, path: Path) -> Document:
        """Parse the file at `path` into a Document. Raises ParseError on failure."""
        ...
