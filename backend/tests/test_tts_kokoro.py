"""Runs real Kokoro synthesis — slower than the rest of the suite (loads the ONNX
model), but this is what actually exercises the engine, especially the [M4-4] fix
that makes Chinese synthesis work at all (see kokoro.py's synth() docstring)."""
import pytest

from app.tts.kokoro import KokoroEngine


@pytest.fixture(scope="module")
def engine():
    from app.config import get_settings

    settings = get_settings()
    return KokoroEngine(
        settings.models_dir / "kokoro" / "kokoro-v1.0.onnx",
        settings.models_dir / "kokoro" / "voices-v1.0.bin",
    )


def test_voices_include_all_54_with_correct_language_tags(engine):
    voices = engine.voices()
    assert len(voices) == 54
    by_lang = {}
    for v in voices:
        by_lang.setdefault(v.language, 0)
        by_lang[v.language] += 1
    assert by_lang["en"] == 28
    assert by_lang["zh"] == 8


@pytest.mark.slow
def test_synth_english_unaffected_by_chinese_routing_change(engine):
    samples, sr = engine.synth("Hello, this is a short test.", "af_heart")
    assert sr == 24000
    assert len(samples) / sr > 0.5


@pytest.mark.slow
def test_synth_chinese_produces_real_nonsilent_audio(engine):
    samples, sr = engine.synth("你好，世界！这是一个测试句子。", "zf_xiaobei")
    assert sr == 24000
    duration = len(samples) / sr
    assert duration > 1.0
    # not silence or near-silence — a real signal was actually generated
    assert float(abs(samples).max()) > 0.05


@pytest.mark.slow
def test_chinese_male_voice_also_works(engine):
    samples, sr = engine.synth("今天天气很好。", "zm_yunxi")
    assert len(samples) / sr > 0.3


def test_misaki_phonemes_fully_covered_by_kokoro_vocabulary():
    # This is the actual fix: this package's built-in phonemizer produces "(en)...
    # (cmn)" English-fallback garbage for Chinese (verified in M2), but misaki's
    # output phonemes are — because misaki is the G2P frontend Kokoro was actually
    # trained with — fully present in Kokoro's phoneme vocabulary.
    from kokoro_onnx.tokenizer import Tokenizer
    from misaki.zh import ZHG2P

    g2p = ZHG2P()
    phonemes, _ = g2p("你好，世界！这是一个比较长的测试句子，用来验证音素覆盖率。")
    tokenizer = Tokenizer()
    known = tokenizer.known(phonemes)
    assert known == phonemes, f"{len(phonemes) - len(known)} phoneme char(s) not in Kokoro's vocabulary"
