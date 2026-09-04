"""Two-pass EBU R128 loudness normalization via ffmpeg, plus a light 60Hz high-pass.
Two passes because `loudnorm`'s single-pass mode is only a real-time approximation —
measuring first and feeding the exact stats back in on the second pass gives a much
more accurate target, which matters over a book-length track. Defaults sit inside
ACX's audiobook loudness/peak requirements. See PLAN.md 'audio/'.
"""
import json
import re
import subprocess
from pathlib import Path

DEFAULT_TARGET_I = -19.0  # integrated loudness, LUFS
DEFAULT_TARGET_TP = -3.0  # true peak ceiling, dBTP
DEFAULT_TARGET_LRA = 7.0  # loudness range, LU
HIGHPASS_HZ = 60


class LoudnormError(Exception):
    pass


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", *args], capture_output=True, text=True)


def _filter_chain(loudnorm_args: str) -> str:
    return f"highpass=f={HIGHPASS_HZ},{loudnorm_args}"


def _measure(input_path: Path, target_i: float, target_tp: float, target_lra: float) -> dict:
    loudnorm = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
    result = _run_ffmpeg(
        [
            "-hide_banner", "-nostats", "-i", str(input_path),
            "-af", _filter_chain(loudnorm), "-f", "null", "-",
        ]
    )
    if result.returncode != 0:
        raise LoudnormError(f"ffmpeg loudnorm measurement pass failed: {result.stderr[-2000:]}")
    match = re.search(r"\{[^{}]*\}", result.stderr, re.DOTALL)
    if not match:
        raise LoudnormError(f"could not find loudnorm JSON stats in ffmpeg output: {result.stderr[-1000:]}")
    return json.loads(match.group(0))


def normalize_loudness(
    input_path: Path,
    output_path: Path,
    target_i: float = DEFAULT_TARGET_I,
    target_tp: float = DEFAULT_TARGET_TP,
    target_lra: float = DEFAULT_TARGET_LRA,
) -> dict:
    """Writes the mastered WAV to `output_path`. Returns the measured (pre-mastering)
    loudness stats, useful for logging/QA."""
    stats = _measure(input_path, target_i, target_tp, target_lra)
    loudnorm = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
        f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:linear=true:print_format=summary"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_ffmpeg(
        [
            "-hide_banner", "-nostats", "-y", "-i", str(input_path),
            "-af", _filter_chain(loudnorm), "-ar", "44100", str(output_path),
        ]
    )
    if result.returncode != 0:
        raise LoudnormError(f"ffmpeg loudnorm apply pass failed: {result.stderr[-2000:]}")
    return stats
