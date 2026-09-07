"""Static-cover MP4 rendering for video platforms (YouTube etc.), built with ffmpeg.
See PLAN.md 'video/render.py'.
"""
import subprocess
from pathlib import Path

#: PLAN.md: "~1 fps input upscaled to a 2 fps output" — a still image needs almost no
#: frames at all, and a very low frame rate is what keeps a 10-hour render fast (minutes,
#: not hours) and the file small.
_INPUT_FRAMERATE = 1
_OUTPUT_FRAMERATE = 2
#: Flat placeholder background when the book has no cover — theme.css's dark surface
#: tone. [M5-5] adds a proper generated title/author cover; this is just enough to make
#: MP4 export always work, not a replacement for that card.
_FALLBACK_COLOR = "0x14171a"
_FALLBACK_SIZE = "1280x720"


class VideoEncodeError(Exception):
    pass


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
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-nostats", "-y"]

    has_cover = cover_path is not None and cover_path.is_file()
    if has_cover:
        args += ["-loop", "1", "-framerate", str(_INPUT_FRAMERATE), "-i", str(cover_path)]
    else:
        args += ["-f", "lavfi", "-i", f"color=c={_FALLBACK_COLOR}:s={_FALLBACK_SIZE}:r={_INPUT_FRAMERATE}"]
    args += ["-i", str(input_audio)]

    args += [
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", str(_OUTPUT_FRAMERATE),
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart",
    ]
    for key, value in (("title", title), ("artist", artist)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    args.append(str(output_mp4))

    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoEncodeError(f"ffmpeg MP4 encode failed: {result.stderr[-2000:]}")
    return output_mp4
