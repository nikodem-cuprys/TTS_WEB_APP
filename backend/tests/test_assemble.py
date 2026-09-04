import numpy as np
import pytest

from app.audio.assemble import (
    AssembleItem,
    MixedSampleRateError,
    PAUSE_PARAGRAPH_S,
    PAUSE_SENTENCE_S,
    assemble_chapter,
)

SR = 24000


def _tone(seconds: float, amplitude: float = 0.8) -> np.ndarray:
    n = int(seconds * SR)
    return np.full(n, amplitude, dtype=np.float32)


def test_empty_input():
    samples, sr, timings = assemble_chapter([])
    assert len(samples) == 0
    assert timings == []


def test_single_chunk_no_pause():
    item = AssembleItem(samples=_tone(1.0), sample_rate=SR, pause_after_s=0.0)
    samples, sr, timings = assemble_chapter([item])
    assert sr == SR
    assert len(timings) == 1
    assert timings[0].start_s == pytest.approx(0.0)
    assert timings[0].duration_s == pytest.approx(1.0, abs=1e-3)
    assert len(samples) == pytest.approx(SR, abs=2)


def test_duration_equals_sum_of_chunks_and_pauses():
    items = [
        AssembleItem(samples=_tone(1.0), sample_rate=SR, pause_after_s=PAUSE_SENTENCE_S),
        AssembleItem(samples=_tone(0.5), sample_rate=SR, pause_after_s=PAUSE_PARAGRAPH_S),
        AssembleItem(samples=_tone(2.0), sample_rate=SR, pause_after_s=0.0),
    ]
    samples, sr, timings = assemble_chapter(items)
    expected_total = 1.0 + PAUSE_SENTENCE_S + 0.5 + PAUSE_PARAGRAPH_S + 2.0
    assert len(samples) / sr == pytest.approx(expected_total, abs=0.05)


def test_segment_timings_account_for_pauses():
    items = [
        AssembleItem(samples=_tone(1.0), sample_rate=SR, pause_after_s=0.5),
        AssembleItem(samples=_tone(2.0), sample_rate=SR, pause_after_s=0.0),
    ]
    _, _, timings = assemble_chapter(items)
    assert timings[0].start_s == pytest.approx(0.0)
    assert timings[0].duration_s == pytest.approx(1.0, abs=1e-3)
    # second chunk starts after chunk 1's audio AND its trailing pause
    assert timings[1].start_s == pytest.approx(1.5, abs=1e-3)
    assert timings[1].duration_s == pytest.approx(2.0, abs=1e-3)


def test_fade_ramps_to_near_zero_at_chunk_edges():
    item = AssembleItem(samples=_tone(1.0, amplitude=0.9), sample_rate=SR, pause_after_s=0.0)
    samples, _, _ = assemble_chapter([item])
    assert abs(samples[0]) < 0.01  # fades in from ~0
    assert abs(samples[-1]) < 0.01  # fades out to ~0
    assert abs(samples[len(samples) // 2] - 0.9) < 1e-3  # untouched in the middle


def test_mixed_sample_rates_rejected():
    items = [
        AssembleItem(samples=_tone(1.0), sample_rate=SR, pause_after_s=0.0),
        AssembleItem(samples=_tone(1.0), sample_rate=22050, pause_after_s=0.0),
    ]
    with pytest.raises(MixedSampleRateError):
        assemble_chapter(items)
