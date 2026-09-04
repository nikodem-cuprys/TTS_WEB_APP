"""Shim for formats Calibre's `ebook-convert` handles but nothing in this project reads
natively: MOBI/AZW/AZW3/LIT/PDB/RTF. Converts to EPUB in a temp dir, then reuses
EpubParser. Calibre is optional — when `ebook-convert` isn't on PATH, parsing raises
ParserUnavailableError with an install hint instead of a generic failure, so the API
layer can mark these formats unavailable rather than erroring on upload.
See PLAN.md 'ingest/calibre.py'.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import ParseError, ParserUnavailableError
from .document import Document
from .epub import EpubParser

_INSTALL_HINT = (
    "Calibre's ebook-convert was not found on PATH. Install Calibre "
    "(https://calibre-ebook.com/download) to enable MOBI/AZW/AZW3/LIT/PDB/RTF uploads."
)
_CONVERT_TIMEOUT_S = 180


def ebook_convert_path() -> str | None:
    return shutil.which("ebook-convert")


class CalibreParser:
    extensions = ("mobi", "azw", "azw3", "lit", "pdb", "rtf")

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in self.extensions

    def is_available(self) -> bool:
        return ebook_convert_path() is not None

    def parse(self, path: Path) -> Document:
        exe = ebook_convert_path()
        if exe is None:
            raise ParserUnavailableError(_INSTALL_HINT)

        with tempfile.TemporaryDirectory(prefix="audiobook-studio-calibre-") as tmp:
            out_path = Path(tmp) / (path.stem + ".epub")
            try:
                result = subprocess.run(
                    [exe, str(path), str(out_path)],
                    capture_output=True,
                    text=True,
                    timeout=_CONVERT_TIMEOUT_S,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ParseError(f"ebook-convert timed out converting {path}") from exc

            if result.returncode != 0 or not out_path.is_file():
                stderr_tail = (result.stderr or "").strip().splitlines()[-5:]
                raise ParseError(
                    f"ebook-convert failed on {path} (exit {result.returncode}): "
                    + " | ".join(stderr_tail)
                )

            return EpubParser().parse(out_path)
