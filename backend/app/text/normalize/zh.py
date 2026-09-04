"""Chinese (Mandarin) text normalizer. See PLAN.md 'text/normalize/' and KANBAN
[M4-4]. num2words has no Chinese backend at all (`NotImplementedError`); this uses
`cn2an` instead — already a transitive dependency of `misaki[zh]`, so no new package.

Deliberately does not touch native Chinese punctuation (「」『』，。！？；：) the way
the other normalizers clean up smart quotes for their Latin-script phonemizers —
misaki's G2P is built for Chinese punctuation and handles it correctly on its own;
rewriting it here would risk fighting that rather than helping it.
"""
import re

import cn2an

from .base import register

NORMALIZER_VERSION = "zh-1"

_WHITESPACE_RE = re.compile(r"[ \t]+")


def _clean_symbols(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# --- chapter headings ("第14章" -> "第十四章") ---------------------------------------
# Chinese book headings already spell out the "第...章" structure explicitly (unlike
# English/Polish/German, which need a heading *word* matched before converting a
# trailing roman numeral) — the only normalization needed is Arabic digits, which
# some sources use instead of Chinese numerals, to the spoken numeral form.

_HEADING_DIGIT_RE = re.compile(r"第\s*(\d+)\s*([章节部卷回幕篇])")


def _replace_heading_digit(m: re.Match) -> str:
    return f"第{cn2an.an2cn(m.group(1), 'low')}{m.group(2)}"


# --- years and year ranges ----------------------------------------------------------
# Chinese reads years digit-by-digit ("2024" -> "二零二四"), not as a cardinal
# quantity ("二千零二十四") — cn2an's "direct" mode is exactly this reading.
#
# The other normalizers bound their year regex with \b, but \b is the wrong tool
# here: Python's re treats CJK characters as \w, so \b between a digit run and a
# following Chinese character (e.g. "1939年") is never a boundary at all — that
# pattern would fail to match a real year entirely. An explicit digit lookaround
# does the right thing in both directions: it still finds "1939" in "1939年", and
# unlike no boundary check at all, it correctly refuses to match "1234" as a prefix
# of "12345" (verified as a real bug during development — see test suite).

_YEAR_RANGE_RE = re.compile(
    r"(?<!\d)(1[0-9]{3}|2[0-9]{3})\s?[-–—]\s?(1[0-9]{3}|2[0-9]{3})(?!\d)"
)
_YEAR_RE = re.compile(r"(?<!\d)(1[0-9]{3}|2[0-9]{3})(?!\d)")


def _replace_year_range(m: re.Match) -> str:
    a = cn2an.an2cn(m.group(1), "direct")
    b = cn2an.an2cn(m.group(2), "direct")
    return f"{a}到{b}"


def _replace_year(m: re.Match) -> str:
    return cn2an.an2cn(m.group(1), "direct")


# --- currency -------------------------------------------------------------------

_CURRENCY_PREFIX_RE = re.compile(r"([$£¥])\s?(\d[\d,]*(?:\.\d+)?)")
_CURRENCY_WORDS = {"$": "美元", "£": "英镑", "¥": "元"}
_CNY_SUFFIX_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?(?:元|CNY|RMB)\b")


def _replace_currency_prefix(m: re.Match) -> str:
    symbol, number_str = m.group(1), m.group(2).replace(",", "")
    return f"{cn2an.an2cn(number_str, 'low')}{_CURRENCY_WORDS[symbol]}"


def _replace_cny_suffix(m: re.Match) -> str:
    number_str = m.group(1).replace(",", "")
    return f"{cn2an.an2cn(number_str, 'low')}元"


# --- percentages ------------------------------------------------------------------
# Chinese percentage phrasing is reversed from English: "百分之四十五" is literally
# "out of a hundred parts, forty-five" — the number comes after the fixed prefix, not
# before a trailing word.

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def _replace_percent(m: re.Match) -> str:
    return f"百分之{cn2an.an2cn(m.group(1), 'low')}"


# --- plain numbers ------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _replace_number(m: re.Match) -> str:
    return cn2an.an2cn(m.group(0), "low")


def normalize_zh(text: str) -> str:
    text = _clean_symbols(text)
    text = _HEADING_DIGIT_RE.sub(_replace_heading_digit, text)
    # Order matters from here: each pattern must consume its match (turn it into
    # words) before a more generic one gets a chance to misread the leftover digits.
    text = _CURRENCY_PREFIX_RE.sub(_replace_currency_prefix, text)
    text = _CNY_SUFFIX_RE.sub(_replace_cny_suffix, text)
    text = _PERCENT_RE.sub(_replace_percent, text)
    text = _YEAR_RANGE_RE.sub(_replace_year_range, text)
    text = _YEAR_RE.sub(_replace_year, text)
    text = _NUMBER_RE.sub(_replace_number, text)
    return text


register("zh", normalize_zh, NORMALIZER_VERSION)
