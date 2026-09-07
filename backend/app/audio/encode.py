"""Writes raw samples to WAV and encodes every export format (MP3/M4B/Opus/FLAC/WAV),
each with ID3/Vorbis/FFMETADATA tags and cover art where the container supports it.
See PLAN.md 'audio/'.
"""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


class EncodeError(Exception):
    pass


@dataclass(frozen=True)
class ChapterMarker:
    """One chapter's span in the final assembled track, for M4B chapter embedding."""

    start_s: float
    end_s: float
    title: str


#: FFMETADATA1 escapes '=', ';', '#', '\', and newline with a backslash — see
#: https://ffmpeg.org/ffmpeg-formats.html#Metadata-1
_FFMETADATA_ESCAPE_RE = re.compile(r"([=;#\\\n])")


def _escape_ffmetadata(value: str) -> str:
    return _FFMETADATA_ESCAPE_RE.sub(r"\\\1", value)


def _write_chapters_metadata(
    path: Path,
    chapters: list[ChapterMarker],
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> None:
    lines = [";FFMETADATA1"]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            lines.append(f"{key}={_escape_ffmetadata(value)}")
    for chapter in chapters:
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={round(chapter.start_s * 1000)}")
        lines.append(f"END={round(chapter.end_s * 1000)}")
        lines.append(f"title={_escape_ffmetadata(chapter.title)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate)
    return path


def extract_wav_range(input_wav: Path, output_wav: Path, start_s: float, end_s: float) -> Path:
    """Losslessly extracts `[start_s, end_s)` from a WAV via direct sample-index slicing
    (soundfile) rather than ffmpeg `-ss`/`-to` — exact, with no seek-accuracy caveats.
    Used by [M5-8]'s part splitting to cut a chapter-aligned range from the mastered
    track before per-part encoding."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with sf.SoundFile(str(input_wav)) as f:
        sample_rate = f.samplerate
        start_frame = max(0, round(start_s * sample_rate))
        end_frame = min(f.frames, round(end_s * sample_rate))
        f.seek(start_frame)
        samples = f.read(frames=max(0, end_frame - start_frame), dtype="float32")
    sf.write(str(output_wav), samples, sample_rate)
    return output_wav


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


def encode_m4b(
    input_wav: Path,
    output_m4b: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    chapters: list[ChapterMarker] | None = None,
    cover_path: Path | None = None,
    bitrate: str = "64k",
) -> Path:
    """AAC-in-MP4 with FFMETADATA1 chapter markers, navigable in real audiobook
    players (the format ffmpeg's 'ipod' muxer picks up from the .m4b extension)."""
    output_m4b.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_m4b.with_suffix(".chapters.txt")
    _write_chapters_metadata(metadata_path, chapters or [], title=title, artist=artist, album=title)

    args = ["-hide_banner", "-nostats", "-y", "-i", str(input_wav), "-i", str(metadata_path)]
    has_cover = cover_path is not None and cover_path.is_file()
    if has_cover:
        args += ["-i", str(cover_path)]
    args += ["-map_metadata", "1", "-map", "0:a"]
    if has_cover:
        args += ["-map", "2:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
    args += ["-c:a", "aac", "-b:a", bitrate, str(output_m4b)]

    try:
        result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    finally:
        metadata_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise EncodeError(f"ffmpeg M4B encode failed: {result.stderr[-2000:]}")
    return output_m4b


def encode_opus(
    input_wav: Path,
    output_opus: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    bitrate: str = "64k",
) -> Path:
    output_opus.parent.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-nostats", "-y", "-i", str(input_wav), "-c:a", "libopus", "-b:a", bitrate]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    args.append(str(output_opus))
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise EncodeError(f"ffmpeg Opus encode failed: {result.stderr[-2000:]}")
    return output_opus


def encode_flac(
    input_wav: Path,
    output_flac: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> Path:
    output_flac.parent.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-nostats", "-y", "-i", str(input_wav), "-c:a", "flac"]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    args.append(str(output_flac))
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise EncodeError(f"ffmpeg FLAC encode failed: {result.stderr[-2000:]}")
    return output_flac


def encode_wav(
    input_wav: Path,
    output_wav: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> Path:
    """Remuxes the already-mastered WAV under the final output name, tagging it via
    RIFF INFO chunks (`-c:a copy` — lossless, no re-encode needed)."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-nostats", "-y", "-i", str(input_wav), "-c:a", "copy"]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    args.append(str(output_wav))
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise EncodeError(f"ffmpeg WAV export failed: {result.stderr[-2000:]}")
    return output_wav
