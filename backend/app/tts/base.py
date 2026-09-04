"""TTSEngine protocol every synthesis backend implements, plus the VoiceInfo metadata
the registry and voice-browser UI (M3-6) surface. See PLAN.md 'tts/base.py'.

Kokoro and Piper (M4-1) are both non-autoregressive and carry no state across calls,
which is what makes it safe to run many `synth()` calls in parallel worker processes
(M2-6). A future autoregressive engine (XTTS/Chatterbox, [L-1]) would NOT get that
guarantee and must say so explicitly via `stateful_per_chapter`.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    engine: str
    language: str  # ISO 639-1
    gender: str | None = None
    sample_rate: int = 24000
    quality: str | None = None


@runtime_checkable
class TTSEngine(Protocol):
    #: short id used in cache keys and API responses (e.g. "kokoro", "piper").
    id: str
    #: identifies the pinned model/weights — part of the chunk cache key
    #: (pipeline/cache.py), so bumping it (e.g. after a model upgrade) invalidates
    #: stale cached audio the same way a normalizer version bump does.
    version: str
    #: True for engines whose output quality/prosody depends on synthesizing a whole
    #: chapter's chunks in order on one worker, rather than in parallel. False (the
    #: default expectation) for Kokoro and Piper.
    stateful_per_chapter: bool

    def voices(self) -> list[VoiceInfo]:
        """Static catalog; must not perform I/O beyond first-call caching."""
        ...

    def synth(
        self, text: str, voice: str, *, speed: float = 1.0, **opts
    ) -> tuple[np.ndarray, int]:
        """Returns (float32 mono samples, sample_rate) for one text chunk."""
        ...
