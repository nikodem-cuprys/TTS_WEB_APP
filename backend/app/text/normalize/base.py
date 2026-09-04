"""Per-language normalizer dispatcher, plus the roman-numeral utility shared by every
language's heading handling. See PLAN.md 'text/normalize/'.
"""
from typing import Callable

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(token: str) -> int | None:
    """Returns the value of a roman numeral, or None if `token` isn't a valid one
    (including the empty string — never returns 0 for invalid input)."""
    token = token.upper()
    if not token or any(c not in _ROMAN_VALUES for c in token):
        return None
    total = 0
    prev = 0
    for c in reversed(token):
        value = _ROMAN_VALUES[c]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total if total > 0 else None


class UnsupportedNormalizerLanguageError(Exception):
    pass


_NORMALIZERS: dict[str, Callable[[str], str]] = {}
_VERSIONS: dict[str, str] = {}


def register(language: str, fn: Callable[[str], str], version: str) -> None:
    """`version` must change whenever the ruleset changes meaningfully — it's part of
    the chunk cache key (pipeline/cache.py), so a version bump is what invalidates
    stale cached audio after a normalizer fix."""
    _NORMALIZERS[language] = fn
    _VERSIONS[language] = version


def normalize(text: str, language: str) -> str:
    fn = _NORMALIZERS.get(language)
    if fn is None:
        raise UnsupportedNormalizerLanguageError(
            f"no normalizer registered for language {language!r} "
            f"(available: {sorted(_NORMALIZERS)})"
        )
    return fn(text)


def get_version(language: str) -> str:
    version = _VERSIONS.get(language)
    if version is None:
        raise UnsupportedNormalizerLanguageError(
            f"no normalizer registered for language {language!r} "
            f"(available: {sorted(_VERSIONS)})"
        )
    return version
