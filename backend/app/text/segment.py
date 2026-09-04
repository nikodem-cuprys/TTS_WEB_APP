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


def pack_chunks(sentences: list[str], max_chars: int = _MAX_CHARS_DEFAULT) -> list[str]:
    """Greedily packs whole sentences into chunks up to `max_chars`. A single sentence
    longer than `max_chars` becomes its own oversized chunk rather than being split —
    "never mid-sentence" is a hard constraint, `max_chars` is a soft target."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        joiner_len = 1 if current else 0  # the space that will join it to the chunk so far
        if current and current_len + joiner_len + len(sentence) > max_chars:
            chunks.append(" ".join(current))
            current, current_len = [sentence], len(sentence)
        else:
            current.append(sentence)
            current_len += joiner_len + len(sentence)

    if current:
        chunks.append(" ".join(current))
    return chunks


def segment_text(text: str, language: str = "en", max_chars: int = _MAX_CHARS_DEFAULT) -> list[str]:
    return pack_chunks(split_sentences(text, language), max_chars)
