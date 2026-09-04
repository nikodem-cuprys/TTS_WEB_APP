"""Sentence-aware chunk packing. A chunk is the unit of caching, parallelism, and
subtitle timing (PLAN.md 'text/segment.py') — it must never straddle a sentence
boundary, since that would produce audible mid-sentence gaps at the concatenation
seam and misaligned subtitle timestamps.

Operates on one block's text at a time (never merges text across blocks) so the
pipeline runner can still tell where paragraph/heading boundaries fall for pause
insertion (M2-7) — that's why this module takes plain strings rather than a
Document/Chapter, and leaves block iteration to its caller.
"""
import pysbd

_MAX_CHARS_DEFAULT = 350

#: languages that don't separate words/sentences with spaces — joining two packed
#: sentences with an ASCII " " would insert a space foreign to the script. Chinese is
#: the only one in scope; extend this if a future language needs it (e.g. Japanese).
_NO_SPACE_LANGUAGES = {"zh"}

_sentence_segmenters: dict[str, pysbd.Segmenter] = {}


def _get_sentence_segmenter(language: str) -> pysbd.Segmenter:
    segmenter = _sentence_segmenters.get(language)
    if segmenter is None:
        segmenter = pysbd.Segmenter(language=language, clean=False)
        _sentence_segmenters[language] = segmenter
    return segmenter


def split_sentences(text: str, language: str = "en") -> list[str]:
    text = text.strip()
    if not text:
        return []
    segmenter = _get_sentence_segmenter(language)
    return [s.strip() for s in segmenter.segment(text) if s.strip()]


def pack_chunks(sentences: list[str], max_chars: int = _MAX_CHARS_DEFAULT, joiner: str = " ") -> list[str]:
    """Greedily packs whole sentences into chunks up to `max_chars` (measured in
    characters — meaningful for any script, unlike a word count, which is exactly
    why this needs no special-casing for Chinese's lack of word-separating spaces).
    A single sentence longer than `max_chars` becomes its own oversized chunk rather
    than being split — "never mid-sentence" is a hard constraint, `max_chars` is a
    soft target. `joiner` goes between packed sentences; pass "" for a script that
    doesn't use spaces between sentences (see segment_text's _NO_SPACE_LANGUAGES)."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    joiner_len = len(joiner)

    for sentence in sentences:
        this_joiner_len = joiner_len if current else 0
        if current and current_len + this_joiner_len + len(sentence) > max_chars:
            chunks.append(joiner.join(current))
            current, current_len = [sentence], len(sentence)
        else:
            current.append(sentence)
            current_len += this_joiner_len + len(sentence)

    if current:
        chunks.append(joiner.join(current))
    return chunks


def segment_text(text: str, language: str = "en", max_chars: int = _MAX_CHARS_DEFAULT) -> list[str]:
    joiner = "" if language in _NO_SPACE_LANGUAGES else " "
    return pack_chunks(split_sentences(text, language), max_chars, joiner=joiner)
