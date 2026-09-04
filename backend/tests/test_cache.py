import numpy as np
import pytest

from app.pipeline import cache
from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models")
    settings.ensure_dirs()
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    return settings


def _key(**overrides):
    defaults = dict(
        text="Hello world.", voice="af_heart", engine_id="kokoro",
        engine_version="kokoro-v1.0", speed=1.0, normalizer_version="en-1",
    )
    defaults.update(overrides)
    return cache.compute_key(**defaults)


def test_same_inputs_produce_same_key():
    assert _key() == _key()


@pytest.mark.parametrize(
    "override",
    [
        {"text": "Different text."},
        {"voice": "af_bella"},
        {"engine_id": "piper"},
        {"engine_version": "kokoro-v2.0"},
        {"speed": 1.1},
        {"normalizer_version": "en-2"},
    ],
)
def test_each_field_changes_the_key(override):
    assert _key() != _key(**override)


def test_get_miss_then_put_then_hit():
    key = _key()
    assert cache.get(key) is None

    samples = np.zeros(24000, dtype=np.float32)
    path = cache.put(key, samples, 24000)
    assert path.is_file()

    hit = cache.get(key)
    assert hit == path
    assert hit.is_file()


def test_put_writes_readable_wav(isolated_cache_dir):
    import soundfile as sf

    key = _key()
    samples = (np.sin(np.linspace(0, 6.28, 2400)) * 0.5).astype(np.float32)
    cache.put(key, samples, 24000)

    read_back, sr = sf.read(str(cache.cache_path(key)))
    assert sr == 24000
    assert len(read_back) == len(samples)
