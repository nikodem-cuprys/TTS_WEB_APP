"""Runs real Piper synthesis — slower than the rest of the suite (loads ONNX voices),
but this is what actually exercises the engine against the real downloaded models."""
import pytest

from app.tts.piper import PiperEngine, default_voice_paths


@pytest.fixture(scope="module")
def engine():
    from app.config import get_settings

    return PiperEngine(default_voice_paths(get_settings().models_dir))


def test_voices_metadata_without_loading_models(engine):
    voices = engine.voices()
    assert len(voices) == 3
    by_id = {v.id: v for v in voices}
    assert by_id["pl_PL-gosia-medium"].language == "pl"
    assert by_id["pl_PL-gosia-medium"].gender == "female"
    assert by_id["pl_PL-darkman-medium"].gender == "male"
    assert by_id["de_DE-thorsten-high"].language == "de"
    assert all(v.sample_rate == 22050 for v in voices)
    # voices() must not have loaded any ONNX session as a side effect
    assert engine._loaded == {}


@pytest.mark.slow
def test_synth_polish_produces_real_audio(engine):
    samples, sr = engine.synth("Dzień dobry, jak się masz?", "pl_PL-gosia-medium")
    assert sr == 22050
    assert len(samples) / sr > 0.5
    assert samples.dtype.name == "float32"


@pytest.mark.slow
def test_synth_german_produces_real_audio(engine):
    samples, sr = engine.synth("Guten Tag, wie geht es Ihnen?", "de_DE-thorsten-high")
    assert sr == 22050
    assert len(samples) / sr > 0.5


@pytest.mark.slow
def test_speed_multiplier_changes_duration(engine):
    text = "Dzień dobry, jak się masz? To jest dłuższe zdanie testowe."
    normal, sr = engine.synth(text, "pl_PL-gosia-medium", speed=1.0)
    fast, _ = engine.synth(text, "pl_PL-gosia-medium", speed=1.25)
    assert len(fast) < len(normal)


@pytest.mark.slow
def test_engine_caches_loaded_voice_across_calls(engine):
    engine.synth("Test.", "de_DE-thorsten-high")
    assert "de_DE-thorsten-high" in engine._loaded
    loaded_instance = engine._loaded["de_DE-thorsten-high"]
    engine.synth("Another test.", "de_DE-thorsten-high")
    assert engine._loaded["de_DE-thorsten-high"] is loaded_instance
