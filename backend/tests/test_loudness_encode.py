import json
import subprocess

import numpy as np
import pytest

from app.audio.encode import (
    ChapterMarker,
    encode_flac,
    encode_m4b,
    encode_mp3,
    encode_opus,
    encode_wav,
    extract_wav_range,
    write_wav,
)
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


def _probe(path, *args):
    probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", *args, str(path)],
        capture_output=True, text=True,
    )
    return json.loads(probe.stdout)


def test_encode_m4b_embeds_navigable_chapters(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(3.0), SR)
    chapters = [
        ChapterMarker(start_s=0.0, end_s=1.5, title="Chapter One"),
        ChapterMarker(start_s=1.5, end_s=3.0, title="Chapter Two"),
    ]
    m4b = encode_m4b(wav, tmp_path / "out.m4b", title="My Book", artist="My Author", chapters=chapters)
    assert m4b.is_file()

    info = _probe(m4b, "-show_format", "-show_chapters")
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert tags["title"] == "My Book"
    assert tags["artist"] == "My Author"
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.1)

    probed_chapters = info["chapters"]
    assert len(probed_chapters) == 2
    assert probed_chapters[0]["tags"]["title"] == "Chapter One"
    assert probed_chapters[1]["tags"]["title"] == "Chapter Two"
    assert float(probed_chapters[0]["start_time"]) == pytest.approx(0.0, abs=0.01)
    assert float(probed_chapters[0]["end_time"]) == pytest.approx(1.5, abs=0.01)
    assert float(probed_chapters[1]["end_time"]) == pytest.approx(3.0, abs=0.01)

    # the temp FFMETADATA file must not leak into the output directory
    assert not (tmp_path / "out.chapters.txt").exists()


def test_encode_m4b_chapter_title_with_special_chars_survives_escaping(tmp_path):
    """FFMETADATA1 uses '=', ';', '#', and '\\' as syntax — a chapter title containing
    any of them must be escaped, not silently corrupt the metadata file."""
    wav = write_wav(tmp_path / "in.wav", _sine(1.0), SR)
    chapters = [ChapterMarker(start_s=0.0, end_s=1.0, title="A=B; C#D\\E")]
    m4b = encode_m4b(wav, tmp_path / "out.m4b", chapters=chapters)
    info = _probe(m4b, "-show_chapters")
    assert info["chapters"][0]["tags"]["title"] == "A=B; C#D\\E"


def test_encode_opus_produces_playable_file_with_tags(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(2.0), SR)
    opus = encode_opus(wav, tmp_path / "out.opus", title="T", artist="A", album="B")
    assert opus.is_file()
    info = _probe(opus, "-show_format", "-show_streams")
    # Ogg/Opus reports metadata tags on the stream, not the format, unlike mp3/flac/
    # wav/m4b (confirmed directly against a real ffmpeg encode, not assumed).
    tags = {k.lower(): v for k, v in info["streams"][0]["tags"].items()}
    assert tags["title"] == "T"
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.15)


def test_encode_flac_produces_lossless_file_with_tags(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(2.0), SR)
    flac = encode_flac(wav, tmp_path / "out.flac", title="T", artist="A", album="B")
    assert flac.is_file()
    info = _probe(flac, "-show_format")
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert tags["title"] == "T"
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.1)


def test_extract_wav_range_slices_the_requested_span(tmp_path):
    import soundfile as sf

    samples = _sine(4.0)
    wav = write_wav(tmp_path / "in.wav", samples, SR)
    out = extract_wav_range(wav, tmp_path / "part.wav", 1.0, 3.0)
    assert out.is_file()

    sliced, sr = sf.read(str(out))
    assert sr == SR
    assert len(sliced) == pytest.approx(2.0 * SR, abs=2)
    # sample-accurate, not just approximately right: the slice really is the original's
    # own [1s, 3s) samples, not a re-synthesized or silence-padded stand-in.
    expected = samples[int(1.0 * SR):int(1.0 * SR) + len(sliced)]
    assert np.allclose(sliced, expected, atol=1e-4)


def test_extract_wav_range_clamps_an_end_past_the_file_length(tmp_path):
    samples = _sine(2.0)
    wav = write_wav(tmp_path / "in.wav", samples, SR)
    out = extract_wav_range(wav, tmp_path / "part.wav", 1.0, 10.0)

    import soundfile as sf

    sliced, _ = sf.read(str(out))
    assert len(sliced) == pytest.approx(1.0 * SR, abs=2)


def test_encode_wav_remuxes_with_tags(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(2.0), SR)
    out = encode_wav(wav, tmp_path / "out.wav", title="T", artist="A", album="B")
    assert out.is_file()
    info = _probe(out, "-show_format")
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.1)
