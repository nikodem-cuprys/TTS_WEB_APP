"""Runs real Kokoro synthesis through the process pool — slower than the rest of the
suite (loads the model in each worker), but this is the only thing that actually
exercises multi-process scheduling and the cache-skip path together."""
import pytest

from app.pipeline import cache as cache_mod
from app.text.normalize import get_version as norm_version
from app.tts.kokoro import KokoroEngine
from app.tts.pool import SynthPool, SynthRequest


def _request(text: str) -> SynthRequest:
    return SynthRequest(
        key=cache_mod.compute_key(
            text=text, voice="af_heart", engine_id="kokoro",
            engine_version=KokoroEngine.version, speed=1.0,
            normalizer_version=norm_version("en"),
        ),
        text=text, voice="af_heart", engine_id="kokoro", speed=1.0,
    )


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    # Pool workers are separate spawned processes, so monkeypatching get_settings()
    # in this (parent) process wouldn't reach them — only an env var survives spawn.
    # models_dir is deliberately left at its default (the real downloaded models);
    # only the cache dir needs isolating for a clean test. get_settings() is also
    # @lru_cache'd process-wide, so clear it in case an earlier test in this session
    # already resolved it against the real paths — see test_pipeline_runner.py's
    # fixture for the full story on why that matters even though this test's own
    # assertions only touch worker-process state.
    from app.config import get_settings

    monkeypatch.setenv("AUDIOBOOK_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data" / "cache").mkdir(parents=True, exist_ok=True)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.slow
def test_pool_synthesizes_and_reuses_cache():
    requests = [_request("Hello there."), _request("A second short sentence.")]

    with SynthPool(workers=2) as pool:
        results = pool.synth_many(requests)
        assert len(results) == 2
        assert all(r.error is None for r in results)
        assert all(not r.cached for r in results)
        assert all(r.duration_s > 0 for r in results)

        results2 = pool.synth_many(requests)
        assert all(r.cached for r in results2)
        assert [r.duration_s for r in results2] == [r.duration_s for r in results]


@pytest.mark.slow
def test_pool_empty_requests_returns_empty():
    with SynthPool(workers=1) as pool:
        assert pool.synth_many([]) == []
