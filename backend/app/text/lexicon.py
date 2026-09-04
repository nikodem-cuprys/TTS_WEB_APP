"""Per-book pronunciation lexicon: literal or regex pattern -> replacement, applied to
each block's text BEFORE language normalization and segmentation ([M4-6]).

Substitution happening this early is what makes "editing an entry invalidates only the
chunks that contain it" true for free: a chunk's cache key (pipeline/cache.py) is a
hash of its exact final text, and a chunk whose text never contained the edited
pattern comes out byte-identical after this step, so its cache key — and therefore its
cached audio — is untouched. No separate cache-versioning scheme is needed.
"""
import re

from ..models import LexiconEntry


def apply_lexicon(text: str, entries: list[LexiconEntry]) -> str:
    for entry in entries:
        if not entry.enabled:
            continue
        if entry.is_regex:
            text = re.sub(entry.pattern, entry.replacement, text)
        else:
            text = text.replace(entry.pattern, entry.replacement)
    return text
