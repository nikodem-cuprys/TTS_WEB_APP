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
import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_PIPER_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


@dataclass(frozen=True)
class ModelFile:
    dest: str  # path relative to MODELS_DIR
    url: str
    size: int  # expected bytes, always checked
    sha256: str | None = None  # checked when known


MANIFEST: list[ModelFile] = [
    # Kokoro-82M: shared engine for English + Chinese voices (see PLAN.md routing table).
    ModelFile(
        dest="kokoro/kokoro-v1.0.onnx",
        url=f"{_KOKORO_RELEASE}/kokoro-v1.0.onnx",
        size=325_532_387,
    ),
    ModelFile(
        dest="kokoro/voices-v1.0.bin",
        url=f"{_KOKORO_RELEASE}/voices-v1.0.bin",
        size=28_214_398,
    ),
    # Piper: Polish voices.
    ModelFile(
        dest="piper/pl_PL-gosia-medium.onnx",
        url=f"{_PIPER_VOICES}/pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx",
        size=63_201_294,
        sha256="38f66464240ed74f186e6b7dc13c6e3b22e023426299f25c2b3cc9dfa9373fbc",
    ),
    ModelFile(
        dest="piper/pl_PL-gosia-medium.onnx.json",
        url=f"{_PIPER_VOICES}/pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx.json",
        size=4_814,
    ),
    ModelFile(
        dest="piper/pl_PL-darkman-medium.onnx",
        url=f"{_PIPER_VOICES}/pl/pl_PL/darkman/medium/pl_PL-darkman-medium.onnx",
        size=63_201_294,
        sha256="db505438a5364e8e2e0242c4324130a873ed660dfbe8d9689cef428ffb1b645f",
    ),
    ModelFile(
        dest="piper/pl_PL-darkman-medium.onnx.json",
        url=f"{_PIPER_VOICES}/pl/pl_PL/darkman/medium/pl_PL-darkman-medium.onnx.json",
        size=4_816,
    ),
    # Piper: German voice.
    ModelFile(
        dest="piper/de_DE-thorsten-high.onnx",
        url=f"{_PIPER_VOICES}/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx",
        size=113_895_201,
        sha256="9df1c43c61149ef9b39e618e2b861fbe41e1fcea9390b2dac62e8761573ea4f1",
    ),
    ModelFile(
        dest="piper/de_DE-thorsten-high.onnx.json",
        url=f"{_PIPER_VOICES}/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json",
        size=4_875,
    ),
]


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_valid(path: Path, model: ModelFile) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != model.size:
        return False
    if model.sha256 and _sha256_of(path) != model.sha256:
        return False
    return True


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

        if not force and _is_valid(dest_path, model):
            print(f"  {model.dest}  already present, skipping")
            continue

        for attempt in range(1, 4):
            try:
                _download(model, dest_path)
                if _is_valid(dest_path, model):
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
