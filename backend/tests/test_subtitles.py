from app.publish.subtitles import SubtitleCue, to_srt, to_vtt


def test_to_srt_formats_timestamps_and_numbers_sequentially():
    cues = [
        SubtitleCue(start_s=0.0, end_s=1.234, text="Hello there."),
        SubtitleCue(start_s=1.5, end_s=3661.789, text="Second line."),
    ]
    srt = to_srt(cues)
    assert srt == (
        "1\n"
        "00:00:00,000 --> 00:00:01,234\n"
        "Hello there.\n"
        "\n"
        "2\n"
        "00:00:01,500 --> 01:01:01,789\n"
        "Second line.\n"
    )


def test_to_vtt_formats_timestamps_with_dot_separator_and_header():
    cues = [SubtitleCue(start_s=0.0, end_s=1.234, text="Hello there.")]
    vtt = to_vtt(cues)
    assert vtt == "WEBVTT\n\n00:00:00.000 --> 00:00:01.234\nHello there.\n"


def test_empty_cue_list_still_produces_valid_headers():
    assert to_srt([]) == "\n"
    assert to_vtt([]) == "WEBVTT\n\n\n"


def test_srt_and_vtt_never_emit_a_negative_timestamp():
    # a segment's start_s is always >= 0 in practice, but the formatter should not
    # produce a malformed negative timestamp if it ever were.
    cues = [SubtitleCue(start_s=-0.5, end_s=1.0, text="x")]
    assert "00:00:00,000" in to_srt(cues)
