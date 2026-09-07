import pytest

from app.audio.encode import ChapterMarker
from app.publish.split import Part, part_filename, part_title, split_into_parts


def _markers(*spans: tuple[float, float, str]) -> list[ChapterMarker]:
    return [ChapterMarker(start_s=s, end_s=e, title=t) for s, e, t in spans]


def test_split_into_parts_returns_a_single_part_when_under_the_limit():
    markers = _markers((0.0, 100.0, "One"), (100.0, 200.0, "Two"))
    parts = split_into_parts(markers, limit_s=1000.0)
    assert len(parts) == 1
    assert parts[0].index == 1
    assert parts[0].start_s == 0.0
    assert parts[0].end_s == 200.0
    assert [c.title for c in parts[0].chapters] == ["One", "Two"]


def test_split_into_parts_never_cuts_a_chapter_and_starts_a_new_part_at_the_limit():
    # each chapter is 40s; a 100s limit fits 2 chapters (80s) but not a 3rd (120s).
    markers = _markers(
        (0.0, 40.0, "One"), (40.0, 80.0, "Two"), (80.0, 120.0, "Three"), (120.0, 160.0, "Four"),
    )
    parts = split_into_parts(markers, limit_s=100.0)
    assert len(parts) == 2
    assert [c.title for c in parts[0].chapters] == ["One", "Two"]
    assert [c.title for c in parts[1].chapters] == ["Three", "Four"]
    assert parts[0].start_s == 0.0
    assert parts[0].end_s == 80.0
    assert parts[1].start_s == 80.0
    assert parts[1].end_s == 160.0


def test_split_into_parts_rebases_chapter_markers_to_zero_within_each_part():
    markers = _markers((0.0, 50.0, "One"), (50.0, 100.0, "Two"), (100.0, 150.0, "Three"))
    parts = split_into_parts(markers, limit_s=100.0)
    assert len(parts) == 2
    assert parts[1].chapters[0].start_s == 0.0  # "Three" re-based within part 2
    assert parts[1].chapters[0].end_s == 50.0


def test_split_into_parts_keeps_an_over_limit_single_chapter_as_its_own_part():
    markers = _markers((0.0, 500.0, "Huge Chapter"))
    parts = split_into_parts(markers, limit_s=100.0)
    assert len(parts) == 1
    assert parts[0].end_s == 500.0


def test_split_into_parts_empty_list():
    assert split_into_parts([]) == []


def test_part_filename_stays_plain_when_only_one_part():
    assert part_filename("My Book", "mp4", 1, 1) == "My Book.mp4"


def test_part_filename_includes_part_number_when_split():
    assert part_filename("My Book", "mp4", 2, 3) == "My Book - Part 2 of 3.mp4"


def test_part_title_stays_plain_when_only_one_part():
    assert part_title("My Book", 1, 1) == "My Book"


def test_part_title_includes_part_number_when_split():
    assert part_title("My Book", 2, 3) == "My Book — Part 2 of 3"


@pytest.mark.parametrize("bad_limit", [0.0, -1.0])
def test_split_into_parts_still_terminates_with_a_degenerate_limit(bad_limit):
    """A limit of 0 (or negative) must not infinite-loop or crash — every chapter just
    ends up alone in its own part."""
    markers = _markers((0.0, 10.0, "One"), (10.0, 20.0, "Two"))
    parts = split_into_parts(markers, limit_s=bad_limit)
    assert len(parts) == 2
