# Audiobook Studio

Local web app that turns a book (EPUB/PDF/TXT/DOCX/...) into a high-quality, chaptered audiobook
and publish-ready video/audio files (MP3, M4B, MP4, SRT), fully offline, on CPU.

- **Languages:** English, Polish, German, Chinese
- **Engines:** Kokoro-82M (EN/ZH) + Piper (PL/DE), both via ONNX Runtime on CPU — no GPU/CUDA required
- **Target throughput:** ≥1:1 (1s of generation per 1s of audio) — comfortably met, see below

See **`PLAN.md`** for the full architecture and rationale, and **`KANBAN.md`** for the live task board.

## Measured performance

`scripts/bench.py` ([M6-1](KANBAN.md)) renders a fixed ~5-minute passage per language through the
real production pipeline (pooled synthesis, assembly, loudness mastering, MP3 encode) and reports
**end-to-end RTF** — wall-clock render time ÷ output audio duration; below 1.0 means faster than
realtime. Measured on a 6-core/12-thread CPU with the default 4-worker pool:

| Language | Voice                | Audio duration | Engine RTF | End-to-end RTF |
|----------|-----------------------|---------------:|-----------:|----------------:|
| English  | `af_heart`             | 4m 39s | 0.484 | **0.131** |
| Polish   | `pl_PL-gosia-medium`   | 6m 02s | 0.070 | **0.083** |
| German   | `de_DE-thorsten-high`  | 5m 37s | 0.294 | **0.126** |
| Chinese  | `zf_xiaobei`           | 4m 48s | 0.536 | **0.150** |

"Engine RTF" is the raw, single-process, unpooled engine — synthesizing chunks one at a time with no
worker pool, assembly, mastering, or encoding. The gap between it and the (lower) end-to-end RTF is
the 4-worker pool's parallelism paying for itself despite the extra pipeline stages. Reproduce with:

```bash
python scripts/bench.py                       # all four languages, ~5 min passages, exits non-zero
                                                # if any language's end-to-end RTF isn't below 1.0
python scripts/bench.py --languages en --minutes 1 --workers 8   # faster, narrower runs
```

## Requirements

- Python 3.11+
- Node.js 20+
- ffmpeg on PATH
- (optional) Calibre's `ebook-convert` on PATH, for MOBI/AZW3/LIT input

## Setup

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -e ".[dev]"
python ../scripts/fetch_models.py
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173.
