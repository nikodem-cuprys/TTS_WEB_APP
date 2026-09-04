import json
import subprocess

import numpy as np
import pytest

from app.audio.encode import encode_mp3, write_wav
from app.audio.loudness import DEFAULT_TARGET_I, LoudnormError, normalize_loudness

SR = 24000


def _sine(seconds: float, amplitude: float = 0.3, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), dtype=np.float32)
    return (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)


def _measure_lufs(path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    import re
    match = re.search(r"\{[^{}]*\}", result.stderr, re.DOTALL)
    return float(json.loads(match.group(0))["input_i"])


def test_write_wav_roundtrip(tmp_path):
    import soundfile as sf

    samples = _sine(1.0)
    path = write_wav(tmp_path / "test.wav", samples, SR)
    assert path.is_file()
    read_back, sr = sf.read(str(path))
    assert sr == SR
    assert len(read_back) == len(samples)


def test_normalize_loudness_reaches_target(tmp_path):
    raw = write_wav(tmp_path / "raw.wav", _sine(3.0, amplitude=0.3), SR)
    mastered = tmp_path / "mastered.wav"

    stats = normalize_loudness(raw, mastered)
    assert mastered.is_file()
    assert float(stats["input_i"]) < -1.0  # sanity: pre-mastering level was measured

    achieved = _measure_lufs(mastered)
    assert achieved == pytest.approx(DEFAULT_TARGET_I, abs=0.5)


def test_normalize_loudness_missing_input_raises(tmp_path):
    with pytest.raises(LoudnormError):
        normalize_loudness(tmp_path / "does_not_exist.wav", tmp_path / "out.wav")


def test_encode_mp3_produces_playable_file_with_tags(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(2.0), SR)
    mp3 = encode_mp3(
        wav, tmp_path / "out.mp3",
        title="My Chapter", artist="My Author", album="My Book", track=3,
    )
    assert mp3.is_file()
    assert mp3.stat().st_size > 0

    probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json",
         "-show_format", str(mp3)],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert tags["title"] == "My Chapter"
    assert tags["artist"] == "My Author"
    assert tags["album"] == "My Book"
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.1)
