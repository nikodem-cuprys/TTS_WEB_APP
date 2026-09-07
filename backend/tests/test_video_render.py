import json
import subprocess

import numpy as np
import pytest

from app.audio.encode import write_wav
from app.video.render import render_static_mp4

SR = 24000


def _sine(seconds: float, amplitude: float = 0.3, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), dtype=np.float32)
    return (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)


def _probe(path, *args):
    probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", *args, str(path)],
        capture_output=True, text=True,
    )
    return json.loads(probe.stdout)


def _make_cover(path, size="640x480"):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", "-f", "lavfi",
         "-i", f"color=c=0x224422:s={size}", "-frames:v", "1", str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return path


def test_render_static_mp4_without_cover_uses_placeholder_background(tmp_path):
    wav = write_wav(tmp_path / "in.wav", _sine(2.0), SR)
    mp4 = render_static_mp4(wav, tmp_path / "out.mp4", title="My Book", artist="My Author")
    assert mp4.is_file()
    assert mp4.stat().st_size > 0

    info = _probe(mp4, "-show_format", "-show_streams")
    kinds = {s["codec_type"] for s in info["streams"]}
    assert kinds == {"video", "audio"}
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.15)


def test_render_static_mp4_with_real_cover_image(tmp_path):
    cover = _make_cover(tmp_path / "cover.png")
    wav = write_wav(tmp_path / "in.wav", _sine(1.5), SR)
    mp4 = render_static_mp4(wav, tmp_path / "out.mp4", cover_path=cover)
    assert mp4.is_file()

    info = _probe(mp4, "-show_format", "-show_streams")
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert video_stream["codec_name"] == "h264"
    assert float(info["format"]["duration"]) == pytest.approx(1.5, abs=0.15)


def test_render_static_mp4_encodes_at_low_frame_rate(tmp_path):
    """[M5-3] acceptance: a 10-hour book must encode in minutes, not hours — the very
    low output frame rate (2 fps) for a still-image video is what makes that true."""
    wav = write_wav(tmp_path / "in.wav", _sine(1.0), SR)
    mp4 = render_static_mp4(wav, tmp_path / "out.mp4")
    info = _probe(mp4, "-show_streams")
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = video_stream["r_frame_rate"].split("/")
    assert float(num) / float(den) == pytest.approx(2.0, abs=0.15)
