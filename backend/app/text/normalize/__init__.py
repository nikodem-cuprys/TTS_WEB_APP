"""Importing this package registers every available language's normalizer (each
submodule calls `register()` as a side effect of being imported)."""
from . import en  # noqa: F401
from .base import UnsupportedNormalizerLanguageError, get_version, normalize

__all__ = ["normalize", "get_version", "UnsupportedNormalizerLanguageError"]
