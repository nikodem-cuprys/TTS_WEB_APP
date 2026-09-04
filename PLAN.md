# Audiobook Studio — Implementation Plan

## Context

Local web app that turns a book file (many formats) into a finished, publishable audiobook: a
high-quality narrated audio track plus MP3/M4B/MP4 renditions ready to upload to video platforms.

Requirements driving the design:

- **Throughput ≥ 1:1** — one second of generation per second of audio produced.
- **Languages** — English (must), Polish, German, Chinese (all four, if achievable).
- **Quality** — must sound good over hours of narration, not just a demo sentence.
- **Roadmap** — voice cloning and more languages come later, so the TTS layer must be pluggable.
- **GUI** — minimalistic, dark grey tones with green accents.

Decisions confirmed with the user: **local-only generation on this PC**, **single-user local web
app** (no auth/accounts), **file export only** (no YouTube API upload), **Python FastAPI backend +
React/Vite frontend**.

### Hardware reality (measured on this machine)

| | |
|---|---|
| CPU | AMD Ryzen 5 5600X — 6 cores / 12 threads |
| RAM | 16 GB |
| GPU | GTX 1050 Ti, 4 GB VRAM, Pascal / **sm_61** |
| Disk | D: — 54 GB free |
| Installed | Python 3.11.9, Node 24.19, ffmpeg 8.1.1. **No Docker.** |

Two findings shape the whole architecture:

1. **The GPU is a dead end for PyTorch.** PyTorch dropped Pascal (sm_61) at 2.8 / CUDA 12.8; the
   1050 Ti requires pinning to torch ≤2.7. With 4 GB VRAM it also cannot run Chatterbox (3.5 GB)
   or XTTS-v2 at 1:1 anyway. **We do not build on PyTorch+CUDA.**
2. **The CPU is more than enough.** The pipeline is **ONNX Runtime on CPU**, which needs no CUDA,
   no torch, and no VRAM. Kokoro-82M runs ~5–10× realtime on a modern CPU core and Piper faster
   still; with a 4-worker process pool on the 5600X, expected end-to-end throughput is **~6–15×
   realtime**, clearing the 1:1 target with large headroom. The real constraint on this project is
   **voice quality**, not speed — so the plan spends its complexity budget on text normalization
   and audio mastering, not on inference optimisation.

### Engine + language strategy

No single local model covers all four languages well at 1:1. Kokoro has the best quality but no
Polish or German; Piper covers everything fast but is flatter. So the app **routes language →
engine** behind one interface:

| Language | Engine | Voices | Why |
|---|---|---|---|
| English (must) | **Kokoro-82M** (ONNX) | `af_*`, `am_*`, `bf_*`, `bm_*` | Best local quality/speed ratio, 20+ EN voices |
| Chinese | **Kokoro-82M** (ONNX) | `zf_*`, `zm_*` | Same model, Mandarin voices via `misaki[zh]` G2P |
| Polish | **Piper** `pl_PL` | `gosia-medium`, `darkman-medium` | Only credible local option at 1:1 |
| German | **Piper** `de_DE` | `thorsten-high`, `ramona-low`, `kerstin-low` | `thorsten-high` is a genuinely strong voice |

Phase 2 (voice cloning) plugs in behind the same `TTSEngine` protocol. XTTS-v2 and Chatterbox
Multilingual both cover all four target languages with zero-shot cloning; both will run
**slower than 1:1 on this hardware** and are therefore designed in as an opt-in "Studio (slow)"
quality tier, not the default. No engine-layer rework will be needed to add them.

> Note: the user is responsible for having the rights to any book they narrate and publish.

---

## Architecture

Two processes: FastAPI backend (owns everything heavy) + Vite dev server / static build for the UI.
State in SQLite. No Redis, no Celery — a single-user local app does not need a broker.

```
Upload → Ingest → Document model → Review/Edit → Normalize → Segment
       → Synthesize (worker pool, cached) → Assemble → Master → Export
```

The **canonical intermediate is a `Document`**: `Book{title, author, language, cover, chapters[]}`,
`Chapter{index, title, enabled, blocks[]}`, `Block{kind: heading|para|quote|verse|skip, text}`.
Every parser produces this; every downstream stage consumes only this. That is what keeps format
support open-ended.

### Repository layout

```
TTS_WEB_APP/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            FastAPI app, CORS, SPA static mount
│  │  ├─ config.py          pydantic-settings: paths, worker count, defaults
│  │  ├─ db.py  models.py  schemas.py      SQLModel + SQLite
│  │  ├─ api/               books, chapters, voices, jobs (SSE), exports, settings
│  │  ├─ ingest/            base, epub, pdf, txt, docx, html, fb2, calibre, detect
│  │  ├─ text/              normalize/{base,en,pl,de,zh}.py, segment.py, lexicon.py
│  │  ├─ tts/               base.py, kokoro.py, piper.py, registry.py, pool.py
│  │  ├─ audio/             assemble.py, loudness.py, encode.py
│  │  ├─ video/             render.py, cover.py
│  │  ├─ publish/           chapters_txt.py, subtitles.py, split.py
│  │  └─ pipeline/          runner.py, cache.py
│  ├─ tests/
│  └─ pyproject.toml
├─ frontend/                React + Vite + TS + Tailwind
│  └─ src/{pages,components,lib}, theme.css, tailwind.config.ts
├─ models/                  (gitignored) downloaded .onnx voices
├─ data/                    (gitignored) books/, cache/, output/, app.db
├─ scripts/                 fetch_models.py, bench.py
├─ KANBAN.md                task board — see that file for the current work queue
└─ README.md
```

### Key module contracts

**`ingest/base.py`**
```python
class Parser(Protocol):
    extensions: tuple[str, ...]
    def can_parse(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> Document: ...
```
- `epub.py` — `ebooklib` + `BeautifulSoup`; chapters from the **spine**, titles from the EPUB3 nav
  doc / EPUB2 NCX; extract cover from `<meta name="cover">`.
- `pdf.py` — `PyMuPDF` (`fitz`). This is the hard one: strip repeated headers/footers by detecting
  text blocks recurring at the same y-position across pages, de-hyphenate line-end `-\n`, join
  wrapped lines, detect chapters via font-size outliers + `^(Chapter|Rozdział|Kapitel|第.章)`
  patterns, and prefer the PDF outline/TOC when present.
- `calibre.py` — shim that shells out to Calibre's `ebook-convert` for MOBI/AZW3/LIT/PDB/RTF →
  EPUB, then reuses the EPUB parser. **Optional dependency**: if `ebook-convert` is not on PATH the
  UI shows those formats as unavailable with an install hint rather than erroring.
- `detect.py` — format sniffing by magic bytes (not extension) + language detection via
  `lingua-py` (more reliable than `langdetect` on short/mixed text), used to preselect the voice.

**`text/normalize/`** — the single largest quality lever for audiobooks; a per-language pipeline of
ordered rules applied before phonemization:
- numbers, ordinals, currency, percentages, dates, times → spelled out **in the target language**
  (`num2words` covers en/pl/de/zh and handles Polish declension cases);
- roman numerals in chapter headings (`Chapter XIV` → "Chapter fourteen");
- abbreviations (`Mr.`/`etc.`/`np.`/`itd.`/`z.B.`/`bzw.`), so a period after them does not become a
  full stop;
- symbol/unicode cleanup: smart quotes, em-dash → pause, ellipsis, `&`, footnote markers, stray
  page numbers, ALL-CAPS words → capitalised (avoid letter-by-letter spelling);
- language quirks: Chinese needs no space-based tokenisation and uses `。！？；` as terminators;
  Polish needs correct case endings from `num2words(lang="pl")`.
- **User lexicon** (`lexicon.py`): per-book table of `pattern → replacement` (literal or regex) so
  names and invented words can be fixed once and reused. Surfaced in the UI.

**`text/segment.py`** — sentence split (`pysbd` for en/de/pl, punctuation rules for zh), then pack
sentences into chunks of ≤ ~350 characters without ever splitting mid-sentence. Chunk = the unit of
caching, parallelism, and subtitle timing.

**`tts/base.py`**
```python
class TTSEngine(Protocol):
    id: str
    def voices(self) -> list[VoiceInfo]: ...           # id, lang, gender, sample_rate, quality
    def synth(self, text: str, voice: str, *,
              speed: float = 1.0, **opts) -> tuple[np.ndarray, int]: ...   # float32 mono, sr
```
- `kokoro.py` wraps `kokoro-onnx` (model + `voices.bin`); `piper.py` wraps `piper1-gpl` /
  `onnxruntime` on the `.onnx`+`.onnx.json` voice pairs.
- `registry.py` holds the voice catalog and the `language → engine` routing table above, and
  resolves an explicit user override.
- `pool.py` — `ProcessPoolExecutor(max_workers=N)` where each worker builds its ONNX session **once**
  (expensive) and reuses it, with `intra_op_num_threads` set so `workers × threads ≈ 10`. Default
  `N=4`, configurable. Safe to parallelise because Kokoro and Piper are non-autoregressive and carry
  no state across chunks (this is *not* true of XTTS/Chatterbox — the future Studio tier must run
  sequentially per chapter to avoid prosody drift).

**`pipeline/cache.py`** — every chunk's WAV is stored under
`data/cache/{sha256(text + voice + engine_version + speed + normalizer_version)}.wav`. This makes
renders **resumable and incremental**: fixing a typo in chapter 7 or changing a lexicon entry
re-synthesises only the affected chunks. Essential when a book is 10+ hours.

**`audio/`** — concatenate chunks with configurable silence (sentence 0.35 s / paragraph 0.6 s /
chapter 1.2 s), 10 ms fades at joins to avoid clicks, then master with **ffmpeg two-pass
`loudnorm`** to an audiobook-appropriate target (default `I=-19 LUFS, TP=-3 dBTP, LRA=7`, which
sits inside ACX's RMS/peak/noise-floor requirements), plus a light high-pass at 60 Hz.

**`video/render.py`** — MP4 for video platforms, built with ffmpeg:
- *Static* — cover image + audio, `-tune stillimage`, ~1 fps input upscaled to a 2 fps output:
  encodes a 10-hour file in minutes and keeps the file small.
- *Waveform* — `showwaves`/`showspectrum` filter over the cover, green-tinted to match the theme.
- *Ken Burns* — slow `zoompan` over the cover.
- `cover.py` generates a clean dark/green cover with Pillow when the book has none.

**`publish/`** — `subtitles.py` emits SRT/VTT **for free** from the known per-chunk durations
(sentence-level, perfectly aligned, no forced alignment needed); `chapters_txt.py` emits
`00:00 Chapter 1` timestamp blocks for the video description; `split.py` splits output at chapter
boundaries into parts under a configurable limit (default 11 h 45 m, under YouTube's 12 h cap).

**`pipeline/runner.py`** — orchestrates stages, writes progress rows to SQLite, and streams updates
to the UI over **SSE** (`GET /api/jobs/{id}/events`). Cancellable; resumable from the cache.

### Frontend

React 19 + Vite + TypeScript + Tailwind + Zustand. Pages: **Library** (grid of books), **Book**
(chapter tree, include/exclude, rename, inline text edit, lexicon), **Render** (voice/language,
speed, pauses, output formats, video style), **Job** (live progress per chapter, waveform preview,
per-chunk re-roll), **Voices** (browse + preview all installed voices), **Settings** (paths, worker
count, loudness target, model downloads).

**Design tokens** (`theme.css`) — minimalistic, dark grey, green accent:

```css
:root{
  --bg:#0E1011; --surface:#16191B; --elevated:#1D2124; --border:#282D31;
  --text:#E6EAEA; --text-2:#9AA4A6; --text-3:#6B7679;
  --accent:#3ECF8E; --accent-hover:#4ADE80; --accent-dim:#1F6F4E;
  --ring:rgba(62,207,142,.28); --danger:#E05252; --warn:#D9A03C;
  --radius:6px; --font:Inter,system-ui,sans-serif; --mono:"JetBrains Mono",monospace;
}
```
Rules: flat surfaces, 1px `--border` separators instead of shadows, 6px radii, green reserved for
primary action / active state / progress only, monospace for timestamps and durations, generous
whitespace, no gradients.

---

## Implementation order

1. **M0 Scaffold** — backend + frontend skeletons, config, SQLite, health check, `fetch_models.py`
   downloading Kokoro + the four Piper voices into `models/`.
2. **M1 Ingest** — `Document` model, TXT → EPUB → PDF parsers, Calibre shim, format/language detect.
3. **M2 TTS core (English)** — engine protocol, Kokoro engine, normalizer (en), segmenter, chunk
   cache, worker pool, assembly, loudness, MP3 export. **First end-to-end audiobook here.**
4. **M3 GUI** — theme, Library/Book/Render/Job pages, SSE progress, chapter editing, voice preview.
5. **M4 Multi-language** — Piper engine + `pl`/`de` voices, Kokoro `zh`, per-language normalizers,
   language→engine routing, lexicon UI.
6. **M5 Publishing** — M4B with chapters, MP4 (3 styles), SRT/VTT, YouTube timestamps, part splitting.
7. **M6 Quality & perf** — `bench.py` RTF gate, listening pass per language, PDF parser hardening,
   cache/disk management.
8. **Backlog** — voice cloning (XTTS-v2 / Chatterbox "Studio" tier), more languages, multi-voice
   dialogue casting, packaging as a desktop app.

The full task breakdown with sizes, dependencies, and acceptance criteria lives in **`KANBAN.md`** —
that file is the live work queue; this file explains the *why* behind it.

---

## Verification

**Speed (the 1:1 requirement)** — `python scripts/bench.py` synthesises a fixed ~5-minute passage in
each of the four languages and reports per-engine and end-to-end RTF including ffmpeg mastering.
**Acceptance: end-to-end RTF < 1.0 with the default 4-worker pool**; record the actual number in the
README. Expected ~0.07–0.2 (5–15× realtime).

**Correctness** — `pytest backend/tests`:
- parser fixtures: a small EPUB, a 2-column PDF, TXT, DOCX → assert chapter count, titles, and that
  headers/footers/page numbers are gone;
- normalizer golden files per language (`$1,234.56`, `Rozdział XIV`, `z.B.`, `第3章`, `1939-1945`);
- segmenter never splits mid-sentence and respects the size cap;
- cache: identical input → cache hit; changed lexicon → targeted invalidation only;
- assembly: output duration ≈ Σ chunk durations + Σ pauses (±50 ms).

**End-to-end** — `uvicorn app.main:app --reload` + `npm run dev`, then for each language upload a
public-domain book, render, and confirm: audio plays, chapter boundaries land correctly, M4B chapter
markers appear in a player, MP4 opens, SRT timings match the audio, and `ffprobe` reports the target
loudness. Verify the >11 h split path with a long book.

**Listening pass** — no automated metric catches audiobook quality. For each language, listen to 3
consecutive minutes and check number/abbreviation reading, pause pacing, and absence of clicks at
chunk joins. This gate is what M6 exists for.
