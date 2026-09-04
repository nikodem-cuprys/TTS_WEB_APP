"""Kokoro-82M engine (ONNX Runtime, CPU). Covers English and Chinese voices — see the
language routing table in PLAN.md. Session construction (~2s, loading a 310MB model) is
the expensive part, so callers must build one KokoroEngine per worker process and reuse
it across every synth() call — never per chunk. See PLAN.md 'tts/kokoro.py'.

Chinese voices ("zf_"/"zm_") route through misaki's ZHG2P instead of this package's
built-in phonemizer — see the [M4-4] note on synth() for why that's necessary, not
optional.
"""
from pathlib import Path

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

from .base import VoiceInfo

# Kokoro voice ids are "<lang><gender>_<name>", e.g. "af_heart" = American English female.
_LANG_PREFIXES = {
    "a": "en",  # American English
    "b": "en",  # British English
    "e": "es",
    "f": "fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt",
    "z": "zh",
}
_GENDER_CODES = {"f": "female", "m": "male"}

#: intra-op threads per worker process; tuned empirically on the target 6C/12T CPU —
#: 4 worker processes x 2 threads beat both a single 6-thread session and 6x2/8x1
#: configurations (RTF 0.30 vs 0.35-0.57). See KANBAN [M2-2] verification notes.
DEFAULT_INTRA_OP_THREADS = 2


def _voice_metadata(voice_id: str, engine_id: str, sample_rate: int) -> VoiceInfo:
    prefix = voice_id[0] if voice_id else ""
    gender_code = voice_id[1] if len(voice_id) > 1 else ""
    return VoiceInfo(
        id=voice_id,
        engine=engine_id,
        language=_LANG_PREFIXES.get(prefix, "und"),
        gender=_GENDER_CODES.get(gender_code),
        sample_rate=sample_rate,
    )


class KokoroEngine:
    id = "kokoro"
    version = "kokoro-v1.0"  # matches the pinned model file; bump on a model upgrade
    stateful_per_chapter = False

    def __init__(
        self,
        model_path: str | Path,
        voices_path: str | Path,
        intra_op_threads: int = DEFAULT_INTRA_OP_THREADS,
    ):
        so = ort.SessionOptions()
        so.intra_op_num_threads = intra_op_threads
        so.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(model_path), sess_options=so, providers=["CPUExecutionProvider"]
        )
        self._kokoro = Kokoro.from_session(session, str(voices_path))
        self._sample_rate = 24000
        self._voices: list[VoiceInfo] | None = None
        self._zh_g2p = None  # lazy: ZHG2P() takes ~1s to build its jieba dictionary

    def voices(self) -> list[VoiceInfo]:
        if self._voices is None:
            self._voices = [
                _voice_metadata(v, self.id, self._sample_rate) for v in self._kokoro.get_voices()
            ]
        return self._voices

    def _get_zh_g2p(self):
        if self._zh_g2p is None:
            from misaki.zh import ZHG2P

            self._zh_g2p = ZHG2P()
        return self._zh_g2p

    def synth(self, text: str, voice: str, *, speed: float = 1.0, **opts) -> tuple[np.ndarray, int]:
        if voice.startswith("z"):
            # This package phonemizes via a bare phonemizer+espeak-ng pass-through
            # (see tokenizer.py), not the misaki G2P frontend the Kokoro model was
            # actually trained with — passing lang="cmn" was verified to silently
            # mis-phonemize Chinese (falls back to English phonemes). The fix is to
            # phonemize with misaki ourselves and feed Kokoro the phonemes directly
            # (is_phonemes=True), bypassing its broken built-in path entirely —
            # verified 100% of misaki's output phonemes exist in Kokoro's vocabulary
            # (tokenizer.known()), vs. the old approach producing "(en)...(cmn)"
            # English-fallback garbage. See KANBAN [M4-4].
            phonemes, _ = self._get_zh_g2p()(text)
            samples, sr = self._kokoro.create(phonemes, voice=voice, is_phonemes=True, speed=speed)
        else:
            lang = opts.get("lang", "en-us")
            samples, sr = self._kokoro.create(text, voice=voice, speed=speed, lang=lang)
        return samples, sr
