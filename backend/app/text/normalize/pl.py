"""Polish text normalizer. See PLAN.md 'text/normalize/' and KANBAN [M4-2].

⚠️ Known limitation, by design: Polish numerals decline by grammatical case and by the
gender/animacy of the noun they modify ("dwóch mężczyzn" vs "dwie kobiety" vs "dwa
domy" — all "two"). Getting that right requires knowing what noun a number modifies
and parsing the sentence's grammatical case, which is a morphological-analysis problem
far beyond a text normalizer. This always emits the nominative ("citation") form via
num2words, which is what the vast majority of rule-based Polish TTS normalizers do —
correct in many sentences, occasionally the "wrong" case in others, but always
intelligible. Full agreement is out of scope.
"""
import re

from num2words import num2words

from .base import register, roman_to_int

NORMALIZER_VERSION = "pl-1"

# --- symbol / whitespace cleanup -------------------------------------------------

_SMART_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', "„": '"'}
_WHITESPACE_RE = re.compile(r"[ \t]+")
_ELLIPSIS_RE = re.compile(r"…")
_AMPERSAND_RE = re.compile(r"(?<=\w)\s*&\s*(?=\w)")

_PL_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_ALLCAPS_WORD_RE = re.compile(rf"\b[{_PL_UPPER}]{{4,}}\b")
_ACRONYM_ALLOWLIST = {"USA", "NATO", "ONZ", "UE"}


def _clean_symbols(text: str) -> str:
    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)
    text = _ELLIPSIS_RE.sub("...", text)
    text = text.replace("\xa0", " ")
    text = _AMPERSAND_RE.sub(" i ", text)
    text = _ALLCAPS_WORD_RE.sub(
        lambda m: m.group(0) if m.group(0) in _ACRONYM_ALLOWLIST else m.group(0).title(), text
    )
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# --- abbreviations -----------------------------------------------------------------

_ABBREVIATIONS = [
    ("np.", "na przykład"), ("itd.", "i tak dalej"), ("itp.", "i tym podobne"),
    ("tzn.", "to znaczy"), ("tj.", "to jest"), ("m.in.", "między innymi"),
    ("ul.", "ulica"), ("dr.", "doktor"), ("prof.", "profesor"), ("godz.", "godzina"),
]


def _capitalize_first(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _abbreviation_variants(abbr: str, expansion: str) -> list[tuple[str, str]]:
    """Unlike English's title abbreviations (always capitalized), these can appear
    lowercase mid-sentence or capitalized sentence-initially ("np." / "Np.") — a
    single case-insensitive match with one lowercase replacement would flatten
    "Np." to a lowercase "na przykład" and break the sentence's capitalization."""
    variants = [(abbr, expansion)]
    cap_abbr = _capitalize_first(abbr)
    if cap_abbr != abbr:
        variants.append((cap_abbr, _capitalize_first(expansion)))
    return variants


_ABBREVIATION_RES = [
    (re.compile(r"(?<!\w)" + re.escape(variant_abbr)), variant_expansion)
    for abbr, expansion in _ABBREVIATIONS
    for variant_abbr, variant_expansion in _abbreviation_variants(abbr, expansion)
]


def _expand_abbreviations(text: str) -> str:
    for pattern, expansion in _ABBREVIATION_RES:
        text = pattern.sub(expansion, text)
    return text


# --- roman numerals in headings -----------------------------------------------------
# Polish idiom strongly prefers the ordinal for chapter numbers ("Rozdział czternasty",
# not "Rozdział czternaście" — the cardinal reads like a room/section label instead of
# a chapter title), unlike the English normalizer's cardinal convention.

_HEADING_ROMAN_RE = re.compile(r"\b(Rozdział|Część|Tom|Akt)\s+([IVXLCDM]+)\b", re.IGNORECASE)


def _replace_heading_roman(m: re.Match) -> str:
    value = roman_to_int(m.group(2))
    if value is None:
        return m.group(0)
    return f"{m.group(1)} {num2words(value, lang='pl', ordinal=True)}"


# --- years and year ranges ----------------------------------------------------------
# Polish reads a year as a single ordinal number ("tysiąc dziewięćset trzydziesty
# dziewiąty"), not split into two 2-digit groups the way English does.

_YEAR_RANGE_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\s?[-–—]\s?(1[0-9]{3}|2[0-9]{3})\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\b")


def _replace_year_range(m: re.Match) -> str:
    a = num2words(int(m.group(1)), lang="pl", ordinal=True)
    b = num2words(int(m.group(2)), lang="pl", ordinal=True)
    return f"{a} do {b}"


def _replace_year(m: re.Match) -> str:
    return num2words(int(m.group(1)), lang="pl", ordinal=True)


# --- currency -------------------------------------------------------------------
# Two shapes: prefix symbols ($/£/€, as in English text) and the Polish złoty, written
# as a number FOLLOWED by "zł" — with either "," or "." accepted as the decimal mark,
# since both appear depending on the source text's origin.

_CURRENCY_PREFIX_RE = re.compile(r"([$£€])\s?(\d[\d,]*(?:\.\d+)?)")
_CURRENCY_CODES = {"$": "USD", "£": "GBP", "€": "EUR"}
_PLN_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s?(?:zł|PLN)\b")
_ZERO_MINOR_UNIT_RE = re.compile(r",\s*zero \w+$")


def _replace_currency_prefix(m: re.Match) -> str:
    symbol, number_str = m.group(1), m.group(2).replace(",", "")
    value = float(number_str)
    words = num2words(value, lang="pl", to="currency", currency=_CURRENCY_CODES[symbol])
    return _ZERO_MINOR_UNIT_RE.sub("", words)


def _replace_pln(m: re.Match) -> str:
    number_str = m.group(1).replace(" ", "").replace(",", ".")
    value = float(number_str)
    words = num2words(value, lang="pl", to="currency", currency="PLN")
    return _ZERO_MINOR_UNIT_RE.sub("", words)


# --- percentages ------------------------------------------------------------------

_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")


def _replace_percent(m: re.Match) -> str:
    token = m.group(1).replace(",", ".")
    value = float(token) if "." in token else int(token)
    return f"{num2words(value, lang='pl')} procent"


# --- decimals and plain integers -----------------------------------------------------

_DECIMAL_RE = re.compile(r"\b\d+,\d+\b")  # Polish decimal comma
_INTEGER_RE = re.compile(r"\b\d{1,3}(?:[ .]\d{3})+\b|\b\d+\b")


def _replace_decimal(m: re.Match) -> str:
    return num2words(float(m.group(0).replace(",", ".")), lang="pl")


def _replace_integer(m: re.Match) -> str:
    number_str = m.group(0).replace(" ", "").replace(".", "")
    return num2words(int(number_str), lang="pl")


def normalize_pl(text: str) -> str:
    text = _clean_symbols(text)
    text = _expand_abbreviations(text)
    text = _HEADING_ROMAN_RE.sub(_replace_heading_roman, text)
    # Order matters from here: each pattern must consume its match (turn it into
    # words) before a more generic one gets a chance to misread the leftover digits.
    text = _CURRENCY_PREFIX_RE.sub(_replace_currency_prefix, text)
    text = _PLN_RE.sub(_replace_pln, text)
    text = _PERCENT_RE.sub(_replace_percent, text)
    text = _YEAR_RANGE_RE.sub(_replace_year_range, text)
    text = _YEAR_RE.sub(_replace_year, text)
    text = _DECIMAL_RE.sub(_replace_decimal, text)
    text = _INTEGER_RE.sub(_replace_integer, text)
    return text


register("pl", normalize_pl, NORMALIZER_VERSION)
