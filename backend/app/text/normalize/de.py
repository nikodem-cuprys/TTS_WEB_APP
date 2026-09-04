"""German text normalizer. See PLAN.md 'text/normalize/' and KANBAN [M4-3].

⚠️ Known limitation, by design (same tradeoff as the Polish normalizer): German
ordinal adjectives decline by case and gender — "3. Kapitel" wants "drittes" (strong
neuter nominative, no preceding article) while "am 3. Mai" wants "dritten" (weak
masculine dative, after "an dem"). num2words' German backend has no gender/case
parameter (verified: `to_ordinal()` takes only the number), so this always emits its
one citation form ("dritte"). Correct in some sentences, the "wrong" ending in
others, always intelligible — full agreement would need a small German declension
engine, out of scope for a text normalizer.
"""
import re

from num2words import num2words

from .base import register, roman_to_int

NORMALIZER_VERSION = "de-1"

# --- symbol / whitespace cleanup -------------------------------------------------

_SMART_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', "„": '"'}
_WHITESPACE_RE = re.compile(r"[ \t]+")
_ELLIPSIS_RE = re.compile(r"…")
_AMPERSAND_RE = re.compile(r"(?<=\w)\s*&\s*(?=\w)")

_DE_UPPER = "A-ZÄÖÜ"
_ALLCAPS_WORD_RE = re.compile(rf"\b[{_DE_UPPER}]{{4,}}\b")
_ACRONYM_ALLOWLIST = {"USA", "NATO", "EU", "UNO"}


def _clean_symbols(text: str) -> str:
    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)
    text = _ELLIPSIS_RE.sub("...", text)
    text = text.replace("\xa0", " ")
    text = _AMPERSAND_RE.sub(" und ", text)
    text = _ALLCAPS_WORD_RE.sub(
        lambda m: m.group(0) if m.group(0) in _ACRONYM_ALLOWLIST else m.group(0).title(), text
    )
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# --- abbreviations -----------------------------------------------------------------

_ABBREVIATIONS = [
    ("z.B.", "zum Beispiel"), ("bzw.", "beziehungsweise"), ("Nr.", "Nummer"),
    ("usw.", "und so weiter"), ("d.h.", "das heißt"), ("u.a.", "unter anderem"),
    ("ca.", "circa"), ("Dr.", "Doktor"), ("Prof.", "Professor"),
]


def _capitalize_first(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _abbreviation_variants(abbr: str, expansion: str) -> list[tuple[str, str]]:
    """Some of these (z.B., bzw., usw.) can appear lowercase mid-sentence or
    capitalized sentence-initially; others (Nr., Dr., Prof.) are conventionally
    always capitalized. Generating both case variants (only when they differ) avoids
    a sentence-initial "Z.B." collapsing to a lowercase "zum Beispiel" and breaking
    capitalization — same fix as the Polish normalizer needed for "np."/"Np."."""
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
# "Kapitel XIV" -> cardinal ("Kapitel vierzehn"), reading naturally as a continuation
# of the heading word — unlike Polish, where the analogous cardinal reads like a room
# label instead of a chapter title. The digit-period convention below is different
# text and gets the ordinal instead, matching how each pattern is actually used.

_HEADING_ROMAN_RE = re.compile(r"\b(Kapitel|Teil|Band|Akt)\s+([IVXLCDM]+)\b")


def _replace_heading_roman(m: re.Match) -> str:
    value = roman_to_int(m.group(2))
    if value is None:
        return m.group(0)
    return f"{m.group(1)} {num2words(value, lang='de')}"


# --- ordinal periods ("3. Kapitel", "3. Mai") ---------------------------------------
# German's "number + period" ordinal marker is only unambiguous when immediately
# followed by a word it plausibly modifies — a bare "digit + period + capitalized
# word" would also match an ordinary sentence-ending number followed by a new
# sentence, so this is deliberately scoped to a known set of heading words and month
# names rather than firing on any capitalized word.

_ORDINAL_CONTEXT_WORDS = "Kapitel|Teil|Band|Akt|Jahrhundert"
_MONTH_NAMES = (
    "Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
)
_ORDINAL_PERIOD_RE = re.compile(rf"\b(\d{{1,4}})\.\s+(?={_ORDINAL_CONTEXT_WORDS}|{_MONTH_NAMES})")


def _replace_ordinal_period(m: re.Match) -> str:
    return num2words(int(m.group(1)), lang="de", ordinal=True) + " "


# --- years and year ranges ----------------------------------------------------------
# num2words has a dedicated to="year" mode for German that already produces the
# conventional reading ("neunzehnhundertneununddreißig" for 1939) rather than the
# literal cardinal ("eintausendneunhundertneununddreißig") — no hand-rolled splitting
# needed here, unlike the English normalizer.

_YEAR_RANGE_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\s?[-–—]\s?(1[0-9]{3}|2[0-9]{3})\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\b")


def _replace_year_range(m: re.Match) -> str:
    a = num2words(int(m.group(1)), lang="de", to="year")
    b = num2words(int(m.group(2)), lang="de", to="year")
    return f"{a} bis {b}"


def _replace_year(m: re.Match) -> str:
    return num2words(int(m.group(1)), lang="de", to="year")


# --- currency -------------------------------------------------------------------
# Euro is conventionally written as a SUFFIX ("5 €"), unlike dollar/pound prefixes.

#: $/£ amounts conventionally keep English-style formatting (comma-thousands,
#: period-decimal) even embedded in German text — nobody writes "$1.234,56". Matches
#: the same pattern used for these two symbols in the English/Polish normalizers.
_CURRENCY_PREFIX_RE = re.compile(r"([$£])\s?(\d[\d,]*(?:\.\d+)?)")
_CURRENCY_CODES = {"$": "USD", "£": "GBP"}
# "€" is a symbol, not a \w character, so a trailing \b after it never matches (\b
# only fires at a \w/\W transition, and symbol-then-punctuation is \W-to-\W) — that
# silently failed to match "12,50 €" entirely in testing. Only "EUR" (a word) needs
# the boundary, to avoid matching inside a longer word like "EURO".
_EUR_RE = re.compile(r"(\d[\d.\s]*(?:,\d+)?)\s?(?:€|EUR\b)")
_ZERO_MINOR_UNIT_RE = re.compile(r" und null \w+$")


def _to_float(number_str: str) -> float:
    # German uses "." as the thousands separator and "," as the decimal mark.
    return float(number_str.replace(".", "").replace(" ", "").replace(",", "."))


def _replace_currency_prefix(m: re.Match) -> str:
    symbol, number_str = m.group(1), m.group(2).replace(",", "")
    value = float(number_str)
    words = num2words(value, lang="de", to="currency", currency=_CURRENCY_CODES[symbol])
    return _ZERO_MINOR_UNIT_RE.sub("", words)


def _replace_eur(m: re.Match) -> str:
    value = _to_float(m.group(1))
    words = num2words(value, lang="de", to="currency", currency="EUR")
    return _ZERO_MINOR_UNIT_RE.sub("", words)


# --- percentages ------------------------------------------------------------------

_PERCENT_RE = re.compile(r"(\d+(?:,\d+)?)\s?%")


def _replace_percent(m: re.Match) -> str:
    token = m.group(1).replace(",", ".")
    value = float(token) if "." in token else int(token)
    return f"{num2words(value, lang='de')} Prozent"


# --- decimals and plain integers -----------------------------------------------------

_DECIMAL_RE = re.compile(r"\b\d+,\d+\b")  # German decimal comma
_INTEGER_RE = re.compile(r"\b\d{1,3}(?:[ .]\d{3})+\b|\b\d+\b")


def _replace_decimal(m: re.Match) -> str:
    return num2words(float(m.group(0).replace(",", ".")), lang="de")


def _replace_integer(m: re.Match) -> str:
    number_str = m.group(0).replace(" ", "").replace(".", "")
    return num2words(int(number_str), lang="de")


def normalize_de(text: str) -> str:
    text = _clean_symbols(text)
    text = _expand_abbreviations(text)
    text = _HEADING_ROMAN_RE.sub(_replace_heading_roman, text)
    text = _ORDINAL_PERIOD_RE.sub(_replace_ordinal_period, text)
    # Order matters from here: each pattern must consume its match (turn it into
    # words) before a more generic one gets a chance to misread the leftover digits.
    text = _CURRENCY_PREFIX_RE.sub(_replace_currency_prefix, text)
    text = _EUR_RE.sub(_replace_eur, text)
    text = _PERCENT_RE.sub(_replace_percent, text)
    text = _YEAR_RANGE_RE.sub(_replace_year_range, text)
    text = _YEAR_RE.sub(_replace_year, text)
    text = _DECIMAL_RE.sub(_replace_decimal, text)
    text = _INTEGER_RE.sub(_replace_integer, text)
    return text


register("de", normalize_de, NORMALIZER_VERSION)
