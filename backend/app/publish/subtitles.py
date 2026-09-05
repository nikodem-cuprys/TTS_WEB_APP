"""Emits SRT/VTT subtitles for free from each segment's already-known (start_s,
duration_s) in the assembled track — sentence-level chunk timing computed during
`audio/assemble.py`'s pass, so no forced alignment is needed. See PLAN.md 'publish/'.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleCue:
    start_s: float
    end_s: float
    text: str


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = round(max(0.0, seconds) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_vtt_timestamp(seconds: float) -> str:
    return _format_srt_timestamp(seconds).replace(",", ".")


def to_srt(cues: list[SubtitleCue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{_format_srt_timestamp(cue.start_s)} --> {_format_srt_timestamp(cue.end_s)}\n{cue.text}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[SubtitleCue]) -> str:
    blocks = [
        f"{_format_vtt_timestamp(cue.start_s)} --> {_format_vtt_timestamp(cue.end_s)}\n{cue.text}"
        for cue in cues
    ]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"
