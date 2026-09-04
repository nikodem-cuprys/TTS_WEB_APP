#!/usr/bin/env python3
"""Downloads the ONNX voice models used by the TTS engines into models/.

Fetches Kokoro-82M (English + Chinese, via kokoro-onnx) and three Piper voices
(Polish x2, German x1) that cover the M0 default voice set. Resumable via HTTP
Range requests; verifies file size always, and SHA-256 where known (Hugging
Face LFS files publish it; the Kokoro GitHub release assets currently do not).

Usage:
    python scripts/fetch_models.py            # fetch everything missing/incomplete
    python scripts/fetch_models.py --list      # show manifest without downloading
    python scripts/fetch_models.py --force     # re-download even if already valid
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.model_manifest import MANIFEST, ModelFile, is_valid  # noqa: E402

MODELS_DIR = _REPO_ROOT / "models"


def _format_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _download(model: ModelFile, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    resume_from = tmp_path.stat().st_size if tmp_path.is_file() else 0
    if resume_from >= model.size:
        # Stale/oversized partial file — start over.
        resume_from = 0

    headers = {"User-Agent": "audiobook-studio-fetch-models"}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"

    req = urllib.request.Request(model.url, headers=headers)
    mode = "ab" if resume_from else "wb"

    print(f"  {model.dest}  ({_format_bytes(model.size)}) "
          f"{'resuming from ' + _format_bytes(resume_from) if resume_from else 'starting'}")

    with urllib.request.urlopen(req, timeout=30) as resp, tmp_path.open(mode) as out:
        downloaded = resume_from
        chunk_size = 1 << 20
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            pct = downloaded / model.size * 100 if model.size else 0
            print(f"\r    {_format_bytes(downloaded)} / {_format_bytes(model.size)} ({pct:5.1f}%)",
                  end="", flush=True)
    print()

    tmp_path.replace(dest_path)


def fetch_all(force: bool = False) -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for model in MANIFEST:
        dest_path = MODELS_DIR / model.dest

        if not force and is_valid(dest_path, model):
            print(f"  {model.dest}  already present, skipping")
            continue

        for attempt in range(1, 4):
            try:
                _download(model, dest_path)
                if is_valid(dest_path, model):
                    break
                print(f"    verification failed for {model.dest} (attempt {attempt}/3)")
                dest_path.unlink(missing_ok=True)
            except (HTTPError, URLError, OSError) as exc:
                print(f"    download error for {model.dest} (attempt {attempt}/3): {exc}")
        else:
            print(f"  FAILED: {model.dest} could not be downloaded/verified after 3 attempts")
            failures += 1
            continue

        print(f"  OK: {model.dest}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the manifest and exit")
    parser.add_argument("--force", action="store_true", help="re-download even if already valid")
    args = parser.parse_args()

    if args.list:
        for model in MANIFEST:
            print(f"{model.dest}\t{_format_bytes(model.size)}\t{model.url}")
        return 0

    print(f"Fetching models into {MODELS_DIR}")
    failures = fetch_all(force=args.force)
    if failures:
        print(f"\n{failures} file(s) failed. Re-run the script to retry (downloads resume).")
        return 1
    print("\nAll models present and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
