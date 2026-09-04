"""English text normalizer: the single largest audiobook-quality lever, applied before
segmentation/synthesis. Rules run in a specific order — see the comment above
`normalize_en` — because each pattern must consume its match (turning digits into
words) before a more generic pattern gets a chance to misread it. See PLAN.md
'text/normalize/'.
"""
import re

from num2words import num2words

from .base import register, roman_to_int

#: bump whenever a rule changes meaningfully — see base.register()'s docstring.
NORMALIZER_VERSION = "en-1"

# --- symbol / whitespace cleanup -------------------------------------------------

_SMART_QUOTES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
}
_WHITESPACE_RE = re.compile(r"[ \t]+")
_ELLIPSIS_RE = re.compile(r"…")
_AMPERSAND_RE = re.compile(r"(?<=\w)\s*&\s*(?=\w)")

# Words fully capitalized and >=4 letters read as spelled-out prose emphasis
# ("NEVER") rather than acronyms get Title-Cased so they aren't spelled letter by
# letter. Short acronyms and this common-word allowlist are left alone. This is a
# heuristic, not a dictionary lookup — genuine unlisted acronyms of 4+ letters will
# be mis-Title-Cased; there is no reliable way to tell without one.
_ACRONYM_ALLOWLIST = {
    "NASA", "FBI", "CIA", "USA", "NATO", "UNESCO", "OK",
}
_ALLCAPS_WORD_RE = re.compile(r"\b[A-Z]{4,}\b")


def _clean_symbols(text: str) -> str:
    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)
    text = _ELLIPSIS_RE.sub("...", text)
    text = text.replace("\xa0", " ")
    text = _AMPERSAND_RE.sub(" and ", text)
    text = _ALLCAPS_WORD_RE.sub(
        lambda m: m.group(0) if m.group(0) in _ACRONYM_ALLOWLIST else m.group(0).title(), text
    )
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# --- abbreviations -----------------------------------------------------------------

# Deliberately excludes ambiguous ones like "No." (could be the word "no", not
# "Number") — a wrong expansion there is more jarring than leaving the period as-is.
_ABBREVIATIONS = [
    ("Mr.", "Mister"), ("Mrs.", "Missus"), ("Ms.", "Miss"), ("Dr.", "Doctor"),
    ("Prof.", "Professor"), ("Sr.", "Senior"), ("Jr.", "Junior"),
    ("St.", "Saint"),  # common-case choice for prose; "Street" loses this tradeoff
    ("vs.", "versus"), ("etc.", "et cetera"), ("e.g.", "for example"),
    ("i.e.", "that is"), ("approx.", "approximately"),
]
_ABBREVIATION_RES = [
    (re.compile(r"(?<!\w)" + re.escape(abbr)), expansion) for abbr, expansion in _ABBREVIATIONS
]


def _expand_abbreviations(text: str) -> str:
    for pattern, expansion in _ABBREVIATION_RES:
        text = pattern.sub(expansion, text)
    return text


# --- roman numerals in headings -----------------------------------------------------

_HEADING_ROMAN_RE = re.compile(r"\b(Chapter|Part|Book|Volume|Act)\s+([IVXLCDM]+)\b")


def _replace_heading_roman(m: re.Match) -> str:
    value = roman_to_int(m.group(2))
    if value is None:
        return m.group(0)
    return f"{m.group(1)} {num2words(value)}"


# --- years and year ranges ----------------------------------------------------------
# Any bare 4-digit number in 1000-2999 is read as a year (e.g. 1939 -> "nineteen
# thirty-nine"). This misfires on genuine large quantities in that range, but years
# are overwhelmingly more common in prose than raw 4-digit counts, so it's the right
# default for an audiobook.

_YEAR_RANGE_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\s?[-–—]\s?(1[0-9]{3}|2[0-9]{3})\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\b")


def _read_year(year: int) -> str:
    century, rest = divmod(year, 100)
    if century == 20:  # "two thousand" era reads as a whole, not split like 19XX
        return "two thousand" if rest == 0 else f"two thousand {num2words(rest)}"
    if rest == 0:
        return f"{num2words(century)} hundred"
    if rest < 10:
        return f"{num2words(century)} oh {num2words(rest)}"
    return f"{num2words(century)} {num2words(rest)}"


def _replace_year_range(m: re.Match) -> str:
    return f"{_read_year(int(m.group(1)))} to {_read_year(int(m.group(2)))}"


def _replace_year(m: re.Match) -> str:
    return _read_year(int(m.group(1)))


# --- currency -------------------------------------------------------------------

_CURRENCY_RE = re.compile(r"([$£€])\s?(\d[\d,]*(?:\.\d+)?)")
_CURRENCY_CODES = {"$": "USD", "£": "GBP", "€": "EUR"}
_ZERO_MINOR_UNIT_RE = re.compile(r",\s*zero \w+$")  # "cents"/"pence"/etc — whichever num2words used


def _replace_currency(m: re.Match) -> str:
    symbol, number_str = m.group(1), m.group(2).replace(",", "")
    value = float(number_str)  # num2words currency mode misreads bare ints as cents
    words = num2words(value, to="currency", currency=_CURRENCY_CODES[symbol])
    return _ZERO_MINOR_UNIT_RE.sub("", words)


# --- percentages ------------------------------------------------------------------

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def _replace_percent(m: re.Match) -> str:
    token = m.group(1)
    value = float(token) if "." in token else int(token)
    return f"{num2words(value)} percent"


# --- ordinals -----------------------------------------------------------------------

_ORDINAL_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*)(st|nd|rd|th)\b", re.IGNORECASE)


def _replace_ordinal(m: re.Match) -> str:
    return num2words(int(m.group(1).replace(",", "")), ordinal=True)


# --- decimals and plain integers -----------------------------------------------------

_DECIMAL_RE = re.compile(r"\b\d+\.\d+\b")
_INTEGER_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b")


def _replace_decimal(m: re.Match) -> str:
    return num2words(float(m.group(0)))


def _replace_integer(m: re.Match) -> str:
    return num2words(int(m.group(0).replace(",", "")))


def normalize_en(text: str) -> str:
    text = _clean_symbols(text)
    text = _expand_abbreviations(text)
    text = _HEADING_ROMAN_RE.sub(_replace_heading_roman, text)
    # Order matters from here: each pattern must consume its match (turn it into
    # words) before a more generic one gets a chance to misread the leftover digits.
    text = _CURRENCY_RE.sub(_replace_currency, text)
    text = _PERCENT_RE.sub(_replace_percent, text)
    text = _YEAR_RANGE_RE.sub(_replace_year_range, text)
    text = _YEAR_RE.sub(_replace_year, text)
    text = _ORDINAL_RE.sub(_replace_ordinal, text)
    text = _DECIMAL_RE.sub(_replace_decimal, text)
    text = _INTEGER_RE.sub(_replace_integer, text)
    return text


register("en", normalize_en, NORMALIZER_VERSION)
