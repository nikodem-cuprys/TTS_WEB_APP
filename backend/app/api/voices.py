"""Voice catalog + one-click preview. Previews are content-addressed through the same
chunk cache as real renders (pipeline/cache.py), so the first click per voice pays for
synthesis (~1-5s) and every one after that is instant. See PLAN.md 'tts/registry.py'.
"""
from fastapi import APIRouter, HTTPException, Response

from ..pipeline import cache
from ..tts.registry import VoiceNotFoundError, all_voices, get_engine, resolve_voice

router = APIRouter()

_PREVIEW_TEXT = "Hello! This is a preview of my voice, reading a short sample sentence aloud."
_PREVIEW_NORMALIZER_VERSION = "preview"  # fixed text needs no real normalizer; distinct cache namespace


@router.get("/voices")
def list_voices() -> list[dict]:
    return [
        {
            "id": v.id, "engine": v.engine, "language": v.language,
            "gender": v.gender, "sample_rate": v.sample_rate, "quality": v.quality,
        }
        for v in all_voices()
    ]


@router.post("/voices/{voice_id}/preview")
def preview_voice(voice_id: str) -> Response:
    try:
        voice = resolve_voice(voice_id)
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    engine = get_engine(voice.engine)
    key = cache.compute_key(
        text=_PREVIEW_TEXT, voice=voice.id, engine_id=engine.id, engine_version=engine.version,
        speed=1.0, normalizer_version=_PREVIEW_NORMALIZER_VERSION,
    )
    path = cache.get(key)
    if path is None:
        samples, sr = engine.synth(_PREVIEW_TEXT, voice.id, speed=1.0)
        path = cache.put(key, samples, sr)

    return Response(content=path.read_bytes(), media_type="audio/wav")
