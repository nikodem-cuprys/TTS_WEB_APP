"""Concatenates a chapter's synthesized chunks into one track, with a short fade at
every chunk boundary (avoids audible clicks from the raw waveform discontinuity) and a
caller-supplied silence gap after each chunk (sentence/paragraph/chapter pacing — see
PLAN.md 'audio/'). Also returns each chunk's (start_s, duration_s) in the assembled
track, which SRT/VTT generation (M5-6) gets for free from this, with no forced
alignment needed.
"""
from dataclasses import dataclass

import numpy as np

FADE_MS = 10.0
PAUSE_SENTENCE_S = 0.35  # between chunks split from the same block (mid-paragraph)
PAUSE_PARAGRAPH_S = 0.6  # between blocks (end of a paragraph/heading)
PAUSE_CHAPTER_S = 1.2  # after the last block of a chapter


@dataclass(frozen=True)
class AssembleItem:
    samples: np.ndarray
    sample_rate: int
    pause_after_s: float = 0.0  # silence to insert after this chunk; 0 for the very last one


@dataclass(frozen=True)
class SegmentTiming:
    start_s: float
    duration_s: float  # excludes the trailing pause


class MixedSampleRateError(Exception):
    pass


def _apply_fade(samples: np.ndarray, sample_rate: int, fade_ms: float = FADE_MS) -> np.ndarray:
    fade_len = min(int(sample_rate * fade_ms / 1000), len(samples) // 2)
    if fade_len <= 0:
        return samples
    samples = samples.copy()
    ramp = np.linspace(0.0, 1.0, fade_len, dtype=samples.dtype)
    samples[:fade_len] *= ramp
    samples[-fade_len:] *= ramp[::-1]
    return samples


def assemble_chapter(items: list[AssembleItem]) -> tuple[np.ndarray, int, list[SegmentTiming]]:
    """Returns (samples, sample_rate, per-item timing). Raises MixedSampleRateError if
    items don't share one sample rate — resampling is out of scope until an engine mix
    within one chapter is actually needed."""
    if not items:
        return np.zeros(0, dtype=np.float32), 0, []

    sample_rate = items[0].sample_rate
    if any(item.sample_rate != sample_rate for item in items):
        raise MixedSampleRateError("all chunks in a chapter must share one sample rate")

    pieces: list[np.ndarray] = []
    timings: list[SegmentTiming] = []
    cursor_samples = 0

    for item in items:
        faded = _apply_fade(item.samples, sample_rate)
        pieces.append(faded)
        duration_samples = len(faded)
        timings.append(
            SegmentTiming(
                start_s=cursor_samples / sample_rate,
                duration_s=duration_samples / sample_rate,
            )
        )
        cursor_samples += duration_samples

        if item.pause_after_s > 0:
            pause_samples = int(round(item.pause_after_s * sample_rate))
            pieces.append(np.zeros(pause_samples, dtype=item.samples.dtype))
            cursor_samples += pause_samples

    assembled = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
    return assembled, sample_rate, timings
