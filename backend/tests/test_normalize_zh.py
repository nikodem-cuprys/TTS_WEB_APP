import pytest

from app.text.normalize import normalize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("第14章", "第十四章"),
        ("第3节", "第三节"),
        ("1939-1945", "一九三九到一九四五"),
        ("这发生在1939年。", "这发生在一九三九年。"),
        ("现在是2024年。", "现在是二零二四年。"),
        ("这花了100元。", "这花了一百元。"),
        ("这花了$5。", "这花了五美元。"),
        ("他有45%的机会。", "他有百分之四十五的机会。"),
        ("价格是12.5元。", "价格是十二点五元。"),
    ],
)
def test_normalize_zh_golden(text, expected):
    assert normalize(text, "zh") == expected


def test_large_number_reads_as_full_cardinal_not_truncated():
    # Regression: the year regex originally had no digit-adjacency boundary, so it
    # matched "1234" as a substring prefix of "12345" and left "5" to be converted
    # separately — producing the nonsense "一二三四五" (digit-by-digit) instead of
    # the correct cardinal reading of twelve thousand three hundred forty-five.
    assert normalize("有12345人。", "zh") == "有一万二千三百四十五人。"
    assert normalize("有123456789人。", "zh") == "有一亿二千三百四十五万六千七百八十九人。"


def test_year_still_matches_immediately_before_a_chinese_character():
    # The other normalizers bound their year regex with \b, but Python's re treats
    # CJK characters as \w, so \b never fires between a digit run and a following
    # Chinese character — a \b-based version of this regex would silently fail to
    # match any real year at all ("1939年" has no \b between "9" and "年").
    assert normalize("1939年", "zh") == "一九三九年"


def test_no_word_boundary_semantics_needed_for_native_punctuation():
    # Chinese punctuation is left untouched by design — only the digits change.
    assert normalize("他说：「1939年。」", "zh") == "他说：「一九三九年。」"
