"""Content-addressed chunk cache. Every synthesized chunk's WAV is stored keyed by a
hash of everything that affects its audio, so re-rendering after fixing one typo or
tweaking one lexicon entry only re-synthesizes the affected chunks — essential once a
book is 10+ hours. See PLAN.md 'pipeline/cache.py'.
"""
import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import get_settings

_FIELD_SEP = "\x1f"  # avoids ambiguity from naive string concatenation of the fields


def compute_key(
    *,
    text: str,
    voice: str,
    engine_id: str,
    engine_version: str,
    speed: float,
    normalizer_version: str,
) -> str:
    payload = _FIELD_SEP.join(
        [text, voice, engine_id, engine_version, f"{speed:.3f}", normalizer_version]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(key: str) -> Path:
    return get_settings().cache_dir() / f"{key}.wav"


def get(key: str) -> Path | None:
    path = cache_path(key)
    return path if path.is_file() else None


def put(key: str, samples: np.ndarray, sample_rate: int) -> Path:
    path = cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate)
    return path
