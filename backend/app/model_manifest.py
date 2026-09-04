"""The model file manifest, shared by scripts/fetch_models.py (which downloads them)
and the Settings page's model status view (api/settings.py, which only reports
presence — downloading multi-hundred-MB files from an HTTP request handler is out of
scope for M3; the Settings page tells the user to run the script instead).
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_PIPER_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


@dataclass(frozen=True)
class ModelFile:
    dest: str  # path relative to models_dir
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


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid(path: Path, model: ModelFile) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != model.size:
        return False
    if model.sha256 and sha256_of(path) != model.sha256:
        return False
    return True
