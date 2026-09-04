#!/usr/bin/env python3
"""Renders a book file straight to a chaptered English MP3 audiobook — the M2
milestone gate (G1 in KANBAN.md): a real EPUB in, a listenable MP3 out, no GUI needed.

Usage:
    python scripts/render_book.py path/to/book.epub --voice af_heart
    python scripts/render_book.py path/to/book.epub --voice af_heart --output out.mp3 --workers 4

Run `python scripts/fetch_models.py` first if models/ is empty.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.db import get_session, init_db  # noqa: E402
from app.ingest.base import ParseError, ParserUnavailableError  # noqa: E402
from app.ingest.detect import resolve_parser  # noqa: E402
from app.ingest.persist import persist_document  # noqa: E402
from app.pipeline.runner import PipelineError, create_job, run_job  # noqa: E402
from app.tts.pool import DEFAULT_WORKERS  # noqa: E402
from app.tts.registry import UnsupportedLanguageError, get_engine  # noqa: E402


def _probe_duration(path: Path) -> float | None:
    import json
    import subprocess

    result = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book_path", type=Path, help="EPUB/PDF/TXT/DOCX/... file to render")
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice id (default: af_heart)")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier (default: 1.0)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"pool size (default: {DEFAULT_WORKERS})")
    parser.add_argument("--output", type=Path, default=None, help="output .mp3 path (default: data/output/<title>.mp3)")
    args = parser.parse_args()

    if not args.book_path.is_file():
        print(f"error: {args.book_path} does not exist", file=sys.stderr)
        return 1

    init_db()
    session_gen = get_session()
    session = next(session_gen)

    try:
        print(f"Parsing {args.book_path.name}...")
        try:
            file_parser = resolve_parser(args.book_path)
            document = file_parser.parse(args.book_path)
        except ParserUnavailableError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ParseError as exc:
            print(f"error: could not parse the book: {exc}", file=sys.stderr)
            return 1

        book = persist_document(session, document, args.book_path, args.book_path.suffix.lstrip("."))
        print(f"  title={book.title!r} author={book.author!r} language={book.language!r} "
              f"chapters={len(book.chapters)}")

        try:
            engine = get_engine("kokoro")
        except UnsupportedLanguageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        voice_ids = {v.id for v in engine.voices()}
        if args.voice not in voice_ids:
            print(f"error: unknown voice {args.voice!r}. Available: {sorted(voice_ids)}", file=sys.stderr)
            return 1

        job = create_job(session, book, voice=args.voice, speed=args.speed)
        print(f"Rendering (job {job.id}, {args.workers} workers)...")

        t0 = time.time()
        try:
            output_path = run_job(session, job, workers=args.workers, output_path=args.output)
        except PipelineError as exc:
            print(f"error: render failed: {exc}", file=sys.stderr)
            return 1
        elapsed = time.time() - t0

        duration = _probe_duration(output_path)
        print(f"Done in {elapsed:.1f}s -> {output_path}")
        if duration:
            print(f"  audio duration: {duration:.1f}s, RTF: {elapsed / duration:.3f}")
        return 0
    finally:
        session_gen.close()


if __name__ == "__main__":
    sys.exit(main())
