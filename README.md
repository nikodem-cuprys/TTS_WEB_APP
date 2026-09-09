# Audiobook Studio

Local web app that turns a book (EPUB/PDF/TXT/DOCX/...) into a high-quality, chaptered audiobook
and publish-ready video/audio files (MP3, M4B, MP4, SRT), fully offline, on CPU. It's a
single-user tool for your own machine — no account, no cloud API keys, no upload of your books
or audio anywhere. Everything (parsing, text normalization, speech synthesis, mastering, and
export) runs locally; books, cache, and rendered output all live under a local `data/` folder.

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
- (optional) Calibre's `ebook-convert` on PATH, for MOBI/AZW3/LIT/PDB/RTF input

Everything runs on CPU — no GPU/CUDA, no cloud API keys, no account. Books, cache, and rendered
output all stay under a local `data/` folder next to this README; nothing leaves the machine.

## Windows install

```powershell
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg               # or download a static build and add its bin\ to PATH yourself
winget install calibre.calibre           # optional — only needed for MOBI/AZW3/LIT/PDB/RTF input
```

`winget` installs don't update the *current* terminal's `PATH` — open a **new** terminal before
continuing, then confirm both landed on PATH:

```powershell
ffmpeg -version
ebook-convert --version   # only if you installed Calibre
```

If `ffmpeg -version` still fails after a new terminal, the installer put it somewhere PATH doesn't
see — find `ffmpeg.exe` (typically under `C:\ProgramData\...\ffmpeg\bin`) and add that folder to your
user `PATH` environment variable manually, then open yet another new terminal.

macOS/Linux: `brew install ffmpeg` / your distro's `ffmpeg` package (and `calibre` the same way);
Python/Node via your usual installers. Everything past this point is identical on every platform.

## Setup

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows — use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
python ../scripts/fetch_models.py     # downloads ~570 MB of ONNX voice models into models/
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173**. `fetch_models.py` is resumable and safe to re-run if a
download gets interrupted — it skips anything already present and verified.

For day-to-day use after that, build the frontend once with `npm --prefix frontend run build`
and use the one-click launcher below instead of running two dev servers by hand.

## Quick start (one click, Windows)

Once the [Setup](#setup) steps above have been done at least once (venv created, dependencies
installed, models downloaded), double-click **`start.bat`** in the project root — or run it from
a terminal:

```powershell
.\start.bat
```

It builds the frontend the first time it's needed, starts the backend (which also serves the
built UI on the same port), and opens **http://127.0.0.1:8000** in your default browser
automatically. A console window titled "Audiobook Studio" stays open while the app runs — close
it to stop the server. Re-run `npm --prefix frontend run build` (or delete `frontend/dist`) after
pulling frontend changes so `start.bat` picks them up.

## First run

1. **Upload a book.** On the Library page, drag a book file (EPUB/PDF/TXT/DOCX/FB2, or MOBI/AZW3/
   LIT/PDB/RTF if Calibre is installed) onto the drop zone. It's parsed immediately and its language
   auto-detected.
2. **Review chapters.** Open the book to see its chapter tree — toggle a chapter off to exclude it
   from the render, rename a chapter or edit a block's text inline (both save immediately), and
   add pronunciation overrides for names or invented words under the lexicon editor if needed.
3. **Configure and start a render.** Click *Render Audiobook*: pick a voice (pre-filtered to the
   book's language), adjust speed, and check off every output format you want — MP3, M4B
   (chaptered), Opus, FLAC, WAV, SRT/VTT subtitles, MP4 (pick a video style — static cover, waveform,
   or Ken Burns — once checked), and/or a YouTube chapters-and-description text file. Then *Start
   Render*.
4. **Watch it render.** The job page shows live progress through all five pipeline stages over a
   real-time connection; a long book can be safely closed and revisited later, or cancelled.
5. **Download.** Once done, every requested format gets its own download button on the job page (and
   on the book page, under *Renders*, for every past attempt) — a split MP4 gets one button per part.
   If a render fails, its error message names the exact text that caused it, and *Retry* starts a new
   attempt reusing the same settings — already-synthesized audio is reused automatically, so only
   what actually failed gets re-synthesized.
6. **Settings**, in the sidebar, covers worker-process count, loudness target, the MP4 part-length
   limit (default just under YouTube's 12h cap), disk usage with a one-click cache prune, and which
   voice models are present.
