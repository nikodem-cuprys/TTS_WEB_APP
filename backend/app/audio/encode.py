"""Writes raw samples to WAV and encodes the final MP3 (with ID3 tags + cover art).
Additional export formats (M4B, Opus, FLAC) land in M5. See PLAN.md 'audio/'.
"""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


class EncodeError(Exception):
    pass


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate)
    return path


def encode_mp3(
    input_wav: Path,
    output_mp3: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    track: int | None = None,
    cover_path: Path | None = None,
    bitrate: str = "128k",
) -> Path:
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-nostats", "-y", "-i", str(input_wav)]

    has_cover = cover_path is not None and cover_path.is_file()
    if has_cover:
        args += ["-i", str(cover_path), "-map", "0:a", "-map", "1:v"]
        args += ["-c:v", "mjpeg", "-disposition:v", "attached_pic"]

    args += ["-c:a", "libmp3lame", "-b:a", bitrate, "-id3v2_version", "3"]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    if track is not None:
        args += ["-metadata", f"track={track}"]

    args.append(str(output_mp3))
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise EncodeError(f"ffmpeg MP3 encode failed: {result.stderr[-2000:]}")
    return output_mp3
