"""Synthesis worker pool: N persistent processes, each building its ONNX engine ONCE
and reusing it across every chunk — session construction (~2s) would dominate cost
otherwise. Workers write straight to the chunk cache (pipeline/cache.py) and return
only lightweight metadata, not raw audio arrays, since pickling megabytes of samples
through IPC for every one of a book's thousands of chunks would be real overhead.
See PLAN.md 'tts/pool.py'.

Default tuning (4 workers x 2 intra-op threads) was picked empirically on the target
6-core/12-thread CPU: it beat both a single 6-thread session (RTF 0.57) and denser
configurations like 6x2=12 threads (RTF 0.32) or 8x1 (RTF 0.45), landing at RTF ~0.30
on a realistic multi-chunk batch — see KANBAN [M2-6] verification notes.

Safe to parallelize only because Kokoro/Piper are non-autoregressive and carry no
state across chunks (TTSEngine.stateful_per_chapter is False for both) — a future
autoregressive engine must NOT be scheduled through this pool; see tts/base.py.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from ..config import get_settings
from ..pipeline import cache
from . import kokoro
from .base import TTSEngine
from .kokoro import KokoroEngine

DEFAULT_WORKERS = 4
DEFAULT_INTRA_OP_THREADS = kokoro.DEFAULT_INTRA_OP_THREADS


@dataclass(frozen=True)
class SynthRequest:
    key: str  # precomputed chunk-cache key (pipeline/cache.compute_key)
    text: str
    voice: str
    engine_id: str
    speed: float = 1.0


@dataclass(frozen=True)
class SynthResult:
    key: str
    duration_s: float
    cached: bool  # True if the chunk was already cached — no synthesis happened
    error: str | None = None


# --- per-worker-process state -----------------------------------------------------
# Deliberately separate from tts/registry.py: the pool needs engines built with the
# throughput-tuned thread count above, while the registry (used by the API process
# for voice listing/single-shot previews) has no such constraint. The small
# duplication of "how to build engine X" is worth keeping the two call sites'
# differing threading needs independent and easy to reason about.

_worker_engines: dict[str, TTSEngine] = {}
_worker_intra_op_threads: int = DEFAULT_INTRA_OP_THREADS


def _build_engine(engine_id: str, intra_op_threads: int) -> TTSEngine:
    if engine_id == "kokoro":
        settings = get_settings()
        return KokoroEngine(
            settings.models_dir / "kokoro" / "kokoro-v1.0.onnx",
            settings.models_dir / "kokoro" / "voices-v1.0.bin",
            intra_op_threads=intra_op_threads,
        )
    raise ValueError(f"unknown engine id: {engine_id!r}")


def _worker_init(intra_op_threads: int) -> None:
    global _worker_intra_op_threads
    _worker_intra_op_threads = intra_op_threads
    _worker_engines.clear()


def _get_worker_engine(engine_id: str) -> TTSEngine:
    engine = _worker_engines.get(engine_id)
    if engine is None:
        engine = _build_engine(engine_id, _worker_intra_op_threads)
        _worker_engines[engine_id] = engine
    return engine


def _synth_one(req: SynthRequest) -> SynthResult:
    existing = cache.get(req.key)
    if existing is not None:
        import soundfile as sf

        return SynthResult(key=req.key, duration_s=sf.info(str(existing)).duration, cached=True)

    try:
        engine = _get_worker_engine(req.engine_id)
        samples, sr = engine.synth(req.text, req.voice, speed=req.speed)
        cache.put(req.key, samples, sr)
        return SynthResult(key=req.key, duration_s=len(samples) / sr, cached=False)
    except Exception as exc:  # noqa: BLE001 — reported to the caller, not raised in-worker
        return SynthResult(key=req.key, duration_s=0.0, cached=False, error=str(exc))


class SynthPool:
    def __init__(self, workers: int = DEFAULT_WORKERS, intra_op_threads: int = DEFAULT_INTRA_OP_THREADS):
        self._executor = ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init, initargs=(intra_op_threads,)
        )

    def synth_many(self, requests: list[SynthRequest]) -> list[SynthResult]:
        if not requests:
            return []
        return list(self._executor.map(_synth_one, requests))

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> "SynthPool":
        return self

    def __exit__(self, *exc_info) -> None:
        self.shutdown()
