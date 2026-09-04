"""Engine registry and language -> engine routing table. See PLAN.md 'tts/registry.py'.

Engines are expensive to construct (Kokoro loads a 310MB ONNX model, ~2s), so this
module lazily builds and caches one instance per engine id for the current process.
That's the right lifetime for the API process (voice listing, single-shot previews),
but NOT what the synthesis worker pool uses — each pool worker builds and keeps its
own engine instance for the life of the process (see tts/pool.py); this registry's
cache is never shared across processes.
"""
from functools import lru_cache

from ..config import get_settings
from .base import TTSEngine, VoiceInfo
from .kokoro import KokoroEngine
from .piper import PiperEngine, default_voice_paths

LANGUAGE_ROUTING: dict[str, str] = {
    "en": "kokoro",
    "zh": "kokoro",  # real Mandarin G2P via misaki, see kokoro.py's synth() ([M4-4])
    "pl": "piper",
    "de": "piper",
}


class UnsupportedLanguageError(Exception):
    pass


class VoiceNotFoundError(Exception):
    pass


@lru_cache
def get_engine(engine_id: str) -> TTSEngine:
    settings = get_settings()
    if engine_id == "kokoro":
        return KokoroEngine(
            settings.models_dir / "kokoro" / "kokoro-v1.0.onnx",
            settings.models_dir / "kokoro" / "voices-v1.0.bin",
        )
    if engine_id == "piper":
        return PiperEngine(default_voice_paths(settings.models_dir))
    raise ValueError(f"unknown engine id: {engine_id!r}")


def engine_for_language(language: str) -> TTSEngine:
    engine_id = LANGUAGE_ROUTING.get(language)
    if engine_id is None:
        raise UnsupportedLanguageError(
            f"no TTS engine is routed for language {language!r} yet "
            f"(supported: {sorted(LANGUAGE_ROUTING)})"
        )
    return get_engine(engine_id)


def all_voices() -> list[VoiceInfo]:
    engine_ids = sorted(set(LANGUAGE_ROUTING.values()))
    voices: list[VoiceInfo] = []
    for engine_id in engine_ids:
        voices.extend(get_engine(engine_id).voices())
    return voices


def resolve_voice(voice_id: str) -> VoiceInfo:
    for voice in all_voices():
        if voice.id == voice_id:
            return voice
    raise VoiceNotFoundError(f"no voice named {voice_id!r}")
