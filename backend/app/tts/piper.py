"""Piper engine (ONNX Runtime, CPU). Covers Polish and German — see the language
routing table in PLAN.md. Each voice's ONNX session is loaded lazily and cached
per-process (~1-4s per voice depending on model size), mirroring KokoroEngine.
See PLAN.md 'tts/piper.py'.
"""
import json
from pathlib import Path

import numpy as np
from piper import PiperVoice, SynthesisConfig

from .base import VoiceInfo

# Piper voice ids don't encode gender anywhere in the model or its config, so it's a
# small lookup table instead of a rule. Extend this when new voices are added.
_VOICE_GENDER = {
    "pl_PL-gosia-medium": "female",
    "pl_PL-darkman-medium": "male",
    "de_DE-thorsten-high": "male",
}


#: the voice set fetch_models.py downloads by default (see app/model_manifest.py).
DEFAULT_VOICE_IDS = ("pl_PL-gosia-medium", "pl_PL-darkman-medium", "de_DE-thorsten-high")


def default_voice_paths(models_dir: Path) -> dict[str, Path]:
    return {voice_id: models_dir / "piper" / f"{voice_id}.onnx" for voice_id in DEFAULT_VOICE_IDS}


def _read_voice_metadata(config_path: Path) -> tuple[str, int, str | None]:
    """Reads (language, sample_rate, quality) straight from the .onnx.json sidecar —
    cheap, unlike PiperVoice.load(), which builds a full ONNX session."""
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)
    language = data.get("language", {}).get("family", "und")
    sample_rate = data.get("audio", {}).get("sample_rate", 22050)
    quality = data.get("audio", {}).get("quality")
    return language, sample_rate, quality


class PiperEngine:
    id = "piper"
    version = "piper-1.8.0"  # pinned piper-tts package version
    stateful_per_chapter = False

    def __init__(self, voice_paths: dict[str, Path]):
        """voice_paths maps voice id (e.g. "pl_PL-gosia-medium") to its .onnx path;
        the matching "<path>.json" config must sit alongside it."""
        self._voice_paths = dict(voice_paths)
        self._loaded: dict[str, PiperVoice] = {}
        self._voices_cache: list[VoiceInfo] | None = None

    def _get_voice(self, voice_id: str) -> PiperVoice:
        pv = self._loaded.get(voice_id)
        if pv is None:
            path = self._voice_paths[voice_id]
            pv = PiperVoice.load(str(path))
            self._loaded[voice_id] = pv
        return pv

    def voices(self) -> list[VoiceInfo]:
        if self._voices_cache is None:
            infos = []
            for voice_id, onnx_path in self._voice_paths.items():
                config_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
                language, sample_rate, quality = _read_voice_metadata(config_path)
                infos.append(
                    VoiceInfo(
                        id=voice_id, engine=self.id, language=language,
                        gender=_VOICE_GENDER.get(voice_id),
                        sample_rate=sample_rate, quality=quality,
                    )
                )
            self._voices_cache = infos
        return self._voices_cache

    def synth(self, text: str, voice: str, *, speed: float = 1.0, **opts) -> tuple[np.ndarray, int]:
        pv = self._get_voice(voice)
        # Piper's length_scale is duration, not rate: >1 slower, <1 faster — the
        # inverse of our speed multiplier.
        syn_config = SynthesisConfig(length_scale=1.0 / speed) if speed != 1.0 else None
        chunks = list(pv.synthesize(text, syn_config=syn_config))
        if not chunks:
            return np.zeros(0, dtype=np.float32), pv.config.sample_rate
        audio = np.concatenate([c.audio_float_array for c in chunks])
        return audio, chunks[0].sample_rate
