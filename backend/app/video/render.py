"""MP4 rendering for video platforms (YouTube etc.), built with ffmpeg. Three styles,
all sharing the same cover-or-placeholder input handling:
  - static   — cover held for the whole track, `-tune stillimage` at 2 fps: a 10-hour
               book still encodes in minutes and stays close to the audio's own size.
  - waveform — a green-tinted `showwaves` line overlaid across the bottom of the cover.
  - kenburns — a slow, continuous `zoompan` drift over the cover, timed to reach its
               target zoom exactly at the audio's own end (not a fixed frame count),
               so it never "finishes zooming" early and freezes for the rest of a book.
See PLAN.md 'video/render.py'.
"""
import subprocess
from pathlib import Path

import soundfile as sf

#: PLAN.md: "~1 fps input upscaled to a 2 fps output" — a still image needs almost no
#: source frames at all.
_STATIC_INPUT_FRAMERATE = 1
_STATIC_OUTPUT_FRAMERATE = 2
#: waveform/kenburns redraw every frame, so they need a real motion frame rate.
_MOTION_FRAMERATE = 24
#: Flat placeholder background when the book has no cover — theme.css's dark surface
#: tone. [M5-5] adds a proper generated title/author cover; this is just enough to make
#: MP4 export always work, not a replacement for that card.
_FALLBACK_COLOR = "0x14171a"
_CANVAS_W, _CANVAS_H = 1280, 720
_CANVAS_SIZE = f"{_CANVAS_W}x{_CANVAS_H}"
#: theme.css's --accent green, in ffmpeg's 0xRRGGBB color syntax.
_WAVEFORM_COLOR = "0x3ecf8e"
_WAVEFORM_HEIGHT = 220
#: how far kenburns zooms in by the end of the track — subtle and "slow" per PLAN.md,
#: not a dramatic push-in.
_KENBURNS_MAX_ZOOM = 1.15

VIDEO_STYLES = ("static", "waveform", "kenburns")

#: guards against odd-width/height cover images, which yuv420p (4:2:0 chroma
#: subsampling) can't encode — ffmpeg errors on odd dimensions otherwise.
_EVEN_DIMS = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
#: waveform/kenburns need a known canvas to overlay/zoom against, unlike static (which
#: just keeps the cover's native size) — scale-to-fit + pad rather than a hard crop, so
#: a portrait book cover doesn't lose content.
_CANVAS = (
    f"scale={_CANVAS_W}:{_CANVAS_H}:force_original_aspect_ratio=decrease,"
    f"pad={_CANVAS_W}:{_CANVAS_H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
)


class VideoEncodeError(Exception):
    pass


def _cover_input_args(cover_path: Path | None, framerate: int) -> list[str]:
    if cover_path is not None and cover_path.is_file():
        return ["-loop", "1", "-framerate", str(framerate), "-i", str(cover_path)]
    return ["-f", "lavfi", "-i", f"color=c={_FALLBACK_COLOR}:s={_CANVAS_SIZE}:r={framerate}"]


def _metadata_args(title: str | None, artist: str | None) -> list[str]:
    args = []
    for key, value in (("title", title), ("artist", artist)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    return args


def _run_ffmpeg(args: list[str], output_mp4: Path) -> Path:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoEncodeError(f"ffmpeg MP4 encode failed: {result.stderr[-2000:]}")
    return output_mp4


def _audio_duration_s(path: Path) -> float:
    info = sf.info(str(path))
    return info.frames / info.samplerate


def render_static_mp4(
    input_audio: Path,
    output_mp4: Path,
    *,
    cover_path: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    audio_bitrate: str = "192k",
) -> Path:
    """Cover image (or a flat placeholder, if the book has none) + audio, encoded with
    `-tune stillimage` at a very low frame rate."""
    args = ["-hide_banner", "-nostats", "-y"]
    args += _cover_input_args(cover_path, _STATIC_INPUT_FRAMERATE)
    args += ["-i", str(input_audio)]
    args += [
        "-vf", _EVEN_DIMS,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", str(_STATIC_OUTPUT_FRAMERATE),
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart",
    ]
    args += _metadata_args(title, artist)
    args.append(str(output_mp4))
    return _run_ffmpeg(args, output_mp4)


def render_waveform_mp4(
    input_audio: Path,
    output_mp4: Path,
    *,
    cover_path: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    audio_bitrate: str = "192k",
) -> Path:
    """Cover (or placeholder) background with a green-tinted `showwaves` line overlaid
    across the bottom, matching theme.css's dark/green accent."""
    args = ["-hide_banner", "-nostats", "-y"]
    args += _cover_input_args(cover_path, _MOTION_FRAMERATE)
    args += ["-i", str(input_audio)]

    filter_complex = (
        f"[0:v]{_CANVAS}[bg];"
        f"[1:a]showwaves=s={_CANVAS_W}x{_WAVEFORM_HEIGHT}:mode=cline:colors={_WAVEFORM_COLOR},"
        "format=yuva420p,colorchannelmixer=aa=0.85[wave];"
        "[bg][wave]overlay=x=0:y=H-h-40:shortest=1,format=yuv420p[v]"
    )
    args += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(_MOTION_FRAMERATE),
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart",
    ]
    args += _metadata_args(title, artist)
    args.append(str(output_mp4))
    return _run_ffmpeg(args, output_mp4)


def render_kenburns_mp4(
    input_audio: Path,
    output_mp4: Path,
    *,
    cover_path: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    audio_bitrate: str = "192k",
    max_zoom: float = _KENBURNS_MAX_ZOOM,
) -> Path:
    """Slow, continuous zoom over the cover (or placeholder). The per-frame zoom
    increment is derived from the audio's own duration so the drift reaches `max_zoom`
    exactly at the end of the track, rather than a fixed frame count that would finish
    early and freeze for the remainder of a long book."""
    duration_s = _audio_duration_s(input_audio)
    total_frames = max(1, round(duration_s * _MOTION_FRAMERATE))
    zoom_increment = (max_zoom - 1.0) / total_frames

    args = ["-hide_banner", "-nostats", "-y"]
    args += _cover_input_args(cover_path, _MOTION_FRAMERATE)
    args += ["-i", str(input_audio)]

    # ffmpeg's expression evaluator doesn't reliably parse Python's scientific-notation
    # repr() for very small floats (a 10-hour book's per-frame increment is ~1e-7) — a
    # fixed-decimal format keeps it a plain literal the parser always accepts.
    zoom_increment_str = f"{zoom_increment:.12f}"
    filter_complex = (
        f"[0:v]{_CANVAS},scale={_CANVAS_W * 2}:{_CANVAS_H * 2},"
        f"zoompan=z='min(zoom+{zoom_increment_str},{max_zoom})':d=1:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={_CANVAS_SIZE}:fps={_MOTION_FRAMERATE},format=yuv420p[v]"
    )
    args += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(_MOTION_FRAMERATE),
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart",
    ]
    args += _metadata_args(title, artist)
    args.append(str(output_mp4))
    return _run_ffmpeg(args, output_mp4)


_RENDERERS = {
    "static": render_static_mp4,
    "waveform": render_waveform_mp4,
    "kenburns": render_kenburns_mp4,
}


def render_mp4(
    input_audio: Path,
    output_mp4: Path,
    *,
    style: str = "static",
    cover_path: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    audio_bitrate: str = "192k",
) -> Path:
    """Dispatches to the render_*_mp4() function for `style` — the single entry point
    the pipeline runner calls, so it doesn't need to know each style's function name."""
    try:
        renderer = _RENDERERS[style]
    except KeyError:
        raise VideoEncodeError(f"unknown video style {style!r}; supported: {VIDEO_STYLES}") from None
    return renderer(
        input_audio, output_mp4, cover_path=cover_path, title=title, artist=artist, audio_bitrate=audio_bitrate,
    )
