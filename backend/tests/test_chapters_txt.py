from app.audio.encode import ChapterMarker
from app.publish.chapters_txt import build_chapter_timestamps, build_youtube_description


def test_build_chapter_timestamps_formats_minutes_seconds():
    markers = [
        ChapterMarker(start_s=0.0, end_s=65.0, title="Chapter One"),
        ChapterMarker(start_s=65.0, end_s=125.4, title="Chapter Two"),
    ]
    assert build_chapter_timestamps(markers) == "0:00 Chapter One\n1:05 Chapter Two\n"


def test_build_chapter_timestamps_adds_hours_past_the_one_hour_mark():
    markers = [
        ChapterMarker(start_s=0.0, end_s=3661.0, title="Intro"),
        ChapterMarker(start_s=3661.0, end_s=3700.0, title="Past One Hour"),
    ]
    text = build_chapter_timestamps(markers)
    assert text == "0:00 Intro\n1:01:01 Past One Hour\n"


def test_build_chapter_timestamps_never_emits_a_negative_timestamp():
    markers = [ChapterMarker(start_s=-0.5, end_s=10.0, title="X")]
    assert build_chapter_timestamps(markers) == "0:00 X\n"


def test_build_chapter_timestamps_empty_list():
    assert build_chapter_timestamps([]) == "\n"


def test_build_youtube_description_includes_title_author_and_chapters():
    markers = [
        ChapterMarker(start_s=0.0, end_s=100.0, title="Chapter One"),
        ChapterMarker(start_s=100.0, end_s=200.0, title="Chapter Two"),
    ]
    description = build_youtube_description(markers, title="My Book", author="My Author")
    assert description == (
        "My Book\n"
        "My Author\n"
        "\n"
        "0:00 Chapter One\n"
        "1:40 Chapter Two\n"
    )


def test_build_youtube_description_without_author():
    markers = [ChapterMarker(start_s=0.0, end_s=10.0, title="Chapter One")]
    description = build_youtube_description(markers, title="My Book")
    assert description == "My Book\n\n0:00 Chapter One\n"
