# Audiobook Studio

Local web app that turns a book (EPUB/PDF/TXT/DOCX/...) into a high-quality, chaptered audiobook
and publish-ready video/audio files (MP3, M4B, MP4, SRT), fully offline, on CPU.

- **Languages:** English, Polish, German, Chinese
- **Engines:** Kokoro-82M (EN/ZH) + Piper (PL/DE), both via ONNX Runtime on CPU — no GPU/CUDA required
- **Target throughput:** ≥1:1 (1s of generation per 1s of audio); see `PLAN.md` for the measured RTF

See **`PLAN.md`** for the full architecture and rationale, and **`KANBAN.md`** for the live task board.

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
