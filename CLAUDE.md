# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Audiobook Studio: a local, offline, single-user web app that turns a book (EPUB/PDF/TXT/DOCX/FB2)
into a chaptered audiobook (MP3/M4B) and publish-ready video (MP4/SRT), entirely on CPU — no
GPU/CUDA required. FastAPI backend + React/Vite frontend, SQLite storage, no auth/accounts.

Languages: English + Chinese via Kokoro-82M (ONNX), Polish + German via Piper (ONNX). Target
throughput is ≥1:1 realtime (1s generated audio per 1s of wall time).

`PLAN.md` has the full architecture and rationale (hardware constraints, engine choice, module
contracts). `KANBAN.md` is the live task board — check it for current milestone status before
starting new work, and update it (Done/In Progress columns, verification narrative) when
completing a card, following the format of existing entries.

## Commands

### Backend (`backend/`, Python 3.11+, venv at `backend/.venv`)

```bash
# setup
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -e ".[dev]"
python ../scripts/fetch_models.py                  # downloads ONNX voice models into models/

# run
uvicorn app.main:app --reload                       # http://127.0.0.1:8000

# test
python -m pytest -q                                  # full suite
python -m pytest -q -m "not slow"                    # skip real-model-inference tests (fast)
python -m pytest tests/test_normalize_pl.py -q        # single file
python -m pytest tests/test_normalize_pl.py::test_name -q   # single test
```

`slow`-marked tests load real Kokoro/Piper models and run real synthesis — expect the full suite
to take ~1.5–2 minutes. Delete `data/app.db` before a clean full run if a prior run left stale
state (most tests use isolated `tmp_path` DBs and don't need this).

### Frontend (`frontend/`, Node 20+)

```bash
npm install
npm run dev       # Vite dev server on :5173, proxies /api to 127.0.0.1:8000
npm run build     # tsc -b && vite build -> frontend/dist (served by the backend as a SPA if present)
npm run lint       # oxlint
```

There is no frontend test runner configured — verify UI changes by running the dev server and
exercising the feature in a browser (this project's established pattern for GUI milestones).

### Other

`scripts/fetch_models.py` downloads and checksums the Kokoro + Piper voice files into `models/`
(gitignored); it's resumable and safe to re-run. `scripts/bench.py` (M6) measures RTF.

## Architecture

### Pipeline

```
Upload → Parser (per format) → Document{Book, Chapter[], Block[]} → persist to SQLite
       → [lexicon substitution] → normalize (per-language) → segment (sentence-packed chunks)
       → synthesize (process pool, content-addressed cache) → assemble (pauses/fades)
       → master (loudnorm) → export (mp3/m4b/mp4/srt)
```

`Document` (`app/ingest/document.py`) is the only intermediate every parser produces and every
downstream stage consumes — new input formats need no changes below the parser layer. Each parser
implements the `Parser` protocol (`app/ingest/base.py`).

`app/pipeline/runner.py` orchestrates the whole thing, writing `Job`/`JobStage`/`Segment` rows to
SQLite as progress markers and streaming them over SSE (`GET /api/jobs/{id}/events`). Cancellation
is checked between synthesis **batches** (`SYNTHESIZE_BATCH_SIZE = 50` in runner.py), not just
between stages, since synthesis dominates render time for long books.

### Text normalization (`app/text/normalize/`)

One module per language (`en.py`, `pl.py`, `de.py`, `zh.py`), each registered via
`base.py`'s `register(language, fn, version)`. Handles numbers/currency/percentages/years/
ordinals/abbreviations/roman-numeral headings via ordered regex substitution before the text is
handed to TTS. `version` is part of the chunk cache key — bump it whenever a ruleset changes
meaningfully, or stale cached audio won't be invalidated.

Known limitation, by design: Polish and German numeral/ordinal **declension** (grammatical
case/gender agreement) is out of scope for a regex-based normalizer — both always emit one
citation form. Documented in each module's docstring.

Pitfalls hit before, worth remembering: Python's `re` treats CJK characters as `\w`, so `\b` never
matches at a digit/CJK boundary — use `(?<!\d)...(?!\d)` instead. `\b` also can't match right after
a symbol like `€` when followed by punctuation (symbol-then-punctuation is `\W`-to-`\W`).

A per-book pronunciation lexicon (`app/text/lexicon.py`, `apply_lexicon()`) is applied **before**
normalization/segmentation in `pipeline/runner.py`'s `_build_chunk_plan()` — this is what makes
"editing one lexicon entry only invalidates the chunks it affects" true for free, since an
unaffected chunk's final text (and thus cache key) never changes.

### TTS engines (`app/tts/`)

`TTSEngine` protocol (`base.py`): `voices()` + `synth(text, voice, speed=...) -> (samples, sr)`.
`registry.py` holds `LANGUAGE_ROUTING = {"en": "kokoro", "zh": "kokoro", "pl": "piper", "de":
"piper"}` and lazily builds/caches one engine instance per process for the API. Chinese synthesis
routes through `misaki.zh.ZHG2P` for phonemization (Kokoro's own built-in phonemizer is bare
espeak-ng and produces near-garbage for Chinese) and feeds Kokoro the phonemes directly via
`is_phonemes=True`.

`app/tts/pool.py` runs synthesis in a `ProcessPoolExecutor` — each worker builds its own ONNX
session once and reuses it across chunks; default is 4 workers × 2 intra-op threads (empirically
tuned, RTF ~0.30). Workers write finished audio straight to the chunk cache and return only
metadata, to avoid IPC overhead from shipping raw audio arrays back to the parent process. Kokoro
and Piper are non-autoregressive with no state across chunks, so parallelizing across a whole book
is safe — this will **not** be true of future autoregressive cloning engines (XTTS/Chatterbox),
which must run sequentially per chapter.

### Chunk cache (`app/pipeline/cache.py`)

Content-addressed: key = sha256 of `text + voice + engine_id + engine_version + speed +
normalizer_version`. Makes multi-hour renders resumable (interrupted jobs just re-use whatever
chunks already exist) and incremental (fixing one paragraph or lexicon entry re-synthesizes only
the chunks whose exact final text changed).

### Data model (`app/models.py`, SQLModel/SQLite)

`Book → Chapter → Block` (the persisted form of `Document`), `Job → JobStage`/`Segment` (one
render run and its per-chunk timing/status), `LexiconEntry` (per-book pronunciation overrides),
`Setting` (key/value app settings). `Book.language` drives `LANGUAGE_ROUTING` and can be
overridden via `PATCH /api/books/{id}`.

### Backend gotchas worth knowing before touching this code

- **`get_settings()` is `@lru_cache`'d process-wide** (`app/config.py`). Tests that need an
  isolated `data_dir` must call `get_settings.cache_clear()` in both fixture setup and teardown, in
  addition to `monkeypatch.setenv(...)` — background threads (same process) are affected by this;
  `ProcessPoolExecutor` workers (separate processes) are not, and need real env vars instead.
- **Naive datetime + SQLite**: SQLite drops tzinfo on read, so a bare `.isoformat()` on a value
  read back from the DB has no UTC offset and gets misread as local time by JS's `Date` parser.
  Always serialize datetimes through `app/util.py`'s `utc_iso()`.
- **`FileResponse(..., filename=...)`** sets `Content-Disposition: attachment`, which breaks
  inline `<audio>`/`<video>` playback in the browser. Use a separate endpoint without `filename=`
  for streaming (see the job `/stream` vs `/download` split in `app/api/jobs.py`).
- **Multiprocessing + stdin heredocs don't mix on Windows**: running Python via a `<<'EOF'`
  heredoc breaks `ProcessPoolExecutor` on Windows spawn (the child can't re-import `<stdin>`).
  Any multiprocessing script/test needs a real `.py` file.

### Frontend (`frontend/src/`)

Pages under `pages/` (Library, Book, Render, Job, Voices, Settings) map roughly 1:1 to the
pipeline's stages; `components/ui/` holds the shared design-system primitives (Button/Card/Select/
Slider/ProgressBar/Badge/Spinner) built on the theme tokens in `theme.css` (dark/grey/green,
minimalistic — flat surfaces, 1px borders instead of shadows, green reserved for primary
action/active state/progress). `lib/api.ts` is the single typed fetch wrapper for the whole
backend API — add new endpoints there rather than calling `fetch` directly from a page/component.
SSE progress is consumed via `subscribeJobEvents()` in the same file.
