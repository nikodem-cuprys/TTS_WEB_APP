# Audiobook Studio — Kanban

Board for the local book → audiobook → video pipeline.
Move cards between sections as work progresses. **WIP limit: 3 cards in `In Progress`.**

**Sizes:** `S` ≈ half a day · `M` ≈ 1–2 days · `L` ≈ 3–5 days · `XL` ≈ 1–2 weeks
**Card format:** `[ID] Title — size · deps` followed by acceptance criteria.

**Milestones:** M0 Scaffold → M1 Ingest → M2 TTS core (EN) → M3 GUI → M4 Multi-language →
M5 Publishing → M6 Quality & perf → L Later

---

## 🎯 Milestone gates

| Gate | Meaning | Card |
|---|---|---|
| **G1** | An EPUB becomes an English MP3 audiobook from the CLI | `M2-10` |
| **G2** | The whole flow works in the browser, no CLI needed | `M3-5` |
| **G3** | All four languages render at acceptable quality | `M4-4` |
| **G4** | Output is upload-ready: M4B + MP4 + SRT + timestamps | `M5-9` |
| **G5** | Measured end-to-end RTF < 1.0, listening pass clean | `M6-2` |

---

## 📋 Backlog

### M3 — GUI

- **[M3-1] Design system components** — M · M0-4
  Button / Card / Select / Slider / Progress / Toast / Modal / Tree on the theme tokens.
  Flat surfaces, 1px borders instead of shadows, 6px radii, green **only** for primary action,
  active state, and progress. Monospace for all timestamps and durations.

- **[M3-2] Library page + upload dropzone** — M · M1-8
  Book grid with cover, language badge, duration estimate, status. Drag-and-drop upload with
  per-file progress.

- **[M3-3] Book page: chapter tree + editing** — L · M3-2
  Include/exclude toggles, rename, reorder, inline text editing, per-chapter word count and estimated
  duration.

- **[M3-4] Render config page** — M · M2-9
  Language + voice picker with preview, speed, pause tuning, output format checkboxes, video style.

- **[M3-5] 🎯 G2 — Job monitor + SSE** — M · M2-9
  `GET /api/jobs/{id}/events`. Per-chapter progress bars, ETA, **live RTF readout**, cancel.
  ✅ The full flow is usable in the browser with no CLI.

- **[M3-6] Voice browser + preview** — S · M2-2
  Every installed voice, grouped by language, with a one-click sample sentence.

- **[M3-7] Settings page** — S
  Worker count, loudness target, output directory, model download manager, disk usage.

### M4 — Multi-language

- **[M4-1] Piper ONNX engine** — M · M2-1
  Wrap `piper1-gpl` / onnxruntime over `.onnx` + `.onnx.json` voice pairs, behind the same protocol.

- **[M4-2] Polish normalizer + voices** — L · M4-1, M2-3
  ⚠️ `num2words(lang="pl")` **declension** is the hard part — Polish numerals inflect by case and
  gender. Abbreviations `np. / itd. / tzn. / m.in. / ul.`. Voices `pl_PL-gosia-medium`,
  `pl_PL-darkman-medium`.
  ✅ Listening pass on 3 minutes of Polish prose.

- **[M4-3] German normalizer + voices** — M · M4-1
  `z.B. / bzw. / Nr. / usw.`, ordinal periods (`3. Kapitel`), compound handling.
  Voice `de_DE-thorsten-high`.
  ✅ Listening pass on 3 minutes of German prose.

- **[M4-4] 🎯 G3 — Chinese support** — L · M2-2
  Kokoro `zf_/zm_` voices via `misaki[zh]` G2P. **No space tokenisation**; terminators are
  `。！？；`; chunk packing counts characters, not words. Numbers read as Chinese numerals.
  ✅ Listening pass on 3 minutes of Chinese prose.

- **[M4-5] Language → engine routing + override UI** — S · M4-1
  Auto-route EN/ZH → Kokoro, PL/DE → Piper, with an explicit manual override.

- **[M4-6] Pronunciation lexicon + UI** — M · M2-5
  Per-book `pattern → replacement` table (literal or regex) for names and invented words.
  ✅ Editing an entry invalidates **only** the chunks that contain it.

### M5 — Publishing

- **[M5-1] M4B chaptered export** — M · M2-8
  ffmpeg metadata chapter file, cover, tags.
  ✅ Chapter markers are navigable in a real audiobook player.

- **[M5-2] Opus / FLAC / WAV exports** — S · M2-8

- **[M5-3] MP4 static-cover render** — M · M2-8
  Cover + audio, `-tune stillimage`, low input fps.
  ✅ A 10-hour book encodes in minutes, not hours, and stays reasonably small.

- **[M5-4] MP4 waveform + Ken Burns styles** — M · M5-3
  Green-tinted `showwaves` over the cover; slow `zoompan` alternative.

- **[M5-5] Generated cover art** — S · M5-3
  Pillow fallback cover in the dark/green theme with title + author.

- **[M5-6] SRT / VTT subtitles** — S · M2-7
  ⭐ Free and perfectly aligned — derived from known per-chunk durations, no forced alignment.

- **[M5-7] YouTube chapter timestamps + description** — S · M2-7
  `00:00 Chapter 1` block, ready to paste.

- **[M5-8] Part splitting under 12 h** — M · M5-3
  Chapter-aligned splits at a configurable limit (default 11 h 45 m), consistent part naming.

- **[M5-9] 🎯 G4 — Exports API + download UI** — S · M5-1…M5-8
  ✅ Every artifact for a finished book is downloadable from one panel.

### M6 — Quality & performance

- **[M6-1] bench.py + RTF gate** — M · M4-*
  Fixed ~5-minute passage per language; reports per-engine and end-to-end RTF including ffmpeg.
  ✅ **End-to-end RTF < 1.0** with the default 4-worker pool. Record the real number in the README.

- **[M6-2] 🎯 G5 — Listening QA pass × 4 languages** — L · M4-*
  3 consecutive minutes per language. Check number/abbreviation reading, pause pacing, chunk-join
  artifacts. No automated metric substitutes for this.

- **[M6-3] PDF parser hardening** — L · M1-4
  Real-world samples: scanned, 2-column, heavy footnotes, drop caps.

- **[M6-4] Disk + cache management** — M · M2-5
  Size reporting, prune, intermediate cleanup. ⚠️ Only 54 GB free on `D:`; WAV intermediates for a
  10-hour book run ~1.7 GB.

- **[M6-5] Error handling + recovery UX** — M · M3-5
  Legible failures; retry **only** the failed chunks.

- **[M6-6] README + setup docs** — S
  Windows install, ffmpeg + optional Calibre notes, first-run walkthrough, measured RTF.

### L — Later (post-v1)

- **[L-1] Voice cloning — "Studio (slow)" tier** — XL
  XTTS-v2 or Chatterbox Multilingual behind the existing `TTSEngine` protocol; both cover all four
  languages with zero-shot cloning. ⚠️ Must run **sequentially per chapter** — unlike Kokoro/Piper
  they are autoregressive and drift in prosody across parallel chunks. Will be **slower than 1:1** on
  this hardware; surface an explicit warning. Includes a reference-clip manager.
- **[L-2] Additional languages** — L — extend routing + normalizers.
- **[L-3] Multi-voice dialogue casting** — XL — speaker attribution per quoted line.
- **[L-4] GPU acceleration tier** — M — ONNX Runtime **DirectML** EP, which works on Pascal (unlike
  torch + CUDA, which dropped sm_61 at 2.8).
- **[L-5] Desktop packaging** — L — PyInstaller / Tauri, single-click launch.

---

## ✅ Ready

### M2 — TTS core (English)

- **[M2-1] TTSEngine protocol + registry** — S
  `voices() -> list[VoiceInfo]`, `synth(text, voice, speed) -> (float32 mono, sample_rate)`.
  Registry holds the voice catalog and the language → engine routing table.

- **[M2-2] Kokoro ONNX engine** — M · M2-1, M0-5
  Wrap `kokoro-onnx` (model + `voices.bin`). Build the ONNX session **once per process** — session
  construction dominates cost otherwise. Expose the `af_/am_/bf_/bm_` English voices.

- **[M2-3] English normalizer** — L · M1-1
  ⭐ *Single largest quality lever.* Ordered rules: numbers / ordinals / currency / percent / dates /
  times via `num2words`; roman numerals in headings; abbreviations (`Mr.`, `Dr.`, `etc.`, `vs.`) so a
  trailing period isn't read as a full stop; smart quotes, em-dash → pause, ellipsis, `&`, footnote
  markers; ALL-CAPS → capitalised so it isn't spelled letter by letter.
  ✅ Golden-file tests: `$1,234.56`, `Chapter XIV`, `1939–1945`, `3rd`, `Dr. Smith vs. Mr. Jones`.

- **[M2-4] Segmenter** — M · M2-3
  `pysbd` sentence split, then pack into ≤350-char chunks. **Never splits mid-sentence.** The chunk
  is the unit of caching, parallelism, and subtitle timing.

- **[M2-5] Chunk cache** — M · M2-4
  `data/cache/{sha256(text + voice + engine_version + speed + normalizer_version)}.wav`.
  ✅ Renders are resumable; fixing one typo re-synthesises only the affected chunks.

- **[M2-6] Worker pool** — M · M2-2, M2-5
  `ProcessPoolExecutor(4)`, one warm ONNX session per worker, `intra_op_num_threads` set so
  `workers × threads ≈ 10` on the 6C/12T CPU. Safe because Kokoro/Piper are non-autoregressive and
  hold no cross-chunk state.

- **[M2-7] Assembly + pauses + fades** — M · M2-6
  Concatenate with configurable silence (sentence 0.35 s / paragraph 0.6 s / chapter 1.2 s) and 10 ms
  fades at joins.
  ✅ No audible click at any chunk boundary. Duration ≈ Σ chunks + Σ pauses (±50 ms).

- **[M2-8] Loudness master + MP3 export** — M · M2-7
  ffmpeg **two-pass** `loudnorm` to `I=-19 LUFS, TP=-3 dBTP, LRA=7` (inside ACX limits), 60 Hz
  high-pass, then MP3 with ID3 tags + embedded cover.
  ✅ `ffprobe` confirms the target loudness.

- **[M2-9] Pipeline runner + job records** — M · M2-8
  Stage orchestration, progress rows in SQLite, cancel, resume-from-cache.

- **[M2-10] 🎯 G1 — EPUB → English MP3 via CLI** — S · M2-9
  ✅ One command turns a real public-domain EPUB into a listenable chaptered MP3.

---

## 🔨 In Progress

*(empty — WIP limit 3)*

---

## 👀 Review

*(empty)*

---

## ✔️ Done

### M1 — Ingest (all 8 cards)

Verified end-to-end: uploaded every fixture through the real HTTP API (not just unit-tested), and
27 pytest cases cover parsers, format/language detection, and the API. Notably: the PDF font-size
heading heuristic, header/footer stripping, and 2-column reading-order logic were each confirmed
against synthetic multi-page PDF fixtures generated with PyMuPDF (not just eyeballed); the Calibre
shim was verified against a real "not installed" environment (Calibre isn't on this machine) so the
graceful-degradation path is real, not theoretical, and `/api/formats` lets the future upload UI
grey those formats out up front. `@app.on_event` was migrated to a `lifespan` handler along the way
(deprecated in the FastAPI version this project pinned).

- **[M1-1] Document model + Parser protocol** — S — `ingest/document.py` + `ingest/base.py`.
- **[M1-2] TXT parser** — S · M1-1 — encoding sniffing verified against real CP1250 Polish text.
- **[M1-3] EPUB parser** — M · M1-1 — spine order, nav-derived titles, nav document dropped.
- **[M1-4] PDF parser** — L · M1-1 — outline path, font-size-heuristic path, and header/footer/
  column logic all independently verified against synthetic fixtures.
- **[M1-5] DOCX + HTML + FB2 parsers** — M · M1-1 — Heading-1-starts-chapter convention; FB2
  footnote `<body name="notes">` correctly excluded from chapters.
- **[M1-6] Calibre shim** — M · M1-3 — confirmed graceful `ParserUnavailableError` with install
  hint on this Calibre-less machine.
- **[M1-7] Format + language detection** — S — magic-byte sniffing (ZIP-internals-aware for
  EPUB vs. DOCX) + `lingua` detector confirmed on real en/pl/de/zh text.
- **[M1-8] Upload API + parser fixtures** — M · M1-2…M1-7 — `POST/GET /api/books`,
  `GET /api/books/{id}/chapters/{id}`, `GET /api/formats`; 27 tests passing.

### M0 — Scaffold (all 5 cards)

- **[M0-1] Repo scaffold + git init** — S
- **[M0-2] Backend skeleton** — M — `/api/health` verified live.
- **[M0-3] SQLite + SQLModel schema** — M · M0-2 — all 8 tables confirmed created on startup.
- **[M0-4] Frontend skeleton** — M — dev server verified reaching the backend via proxy.
- **[M0-5] Model fetcher** — S — all 8 model files downloaded, checksummed, and skip-on-rerun
  confirmed.

- **[P-0] Architecture plan + this board** — done
  Hardware audited, engine strategy settled: **ONNX Runtime on CPU**, no PyTorch/CUDA (the 1050 Ti is
  Pascal/sm_61, dropped by PyTorch 2.8); Kokoro for EN + ZH, Piper for PL + DE. Full plan in
  `PLAN.md`.

---

## 📌 Standing decisions

| Decision | Rationale |
|---|---|
| ONNX Runtime on CPU, **no PyTorch/CUDA** | 1050 Ti is Pascal/sm_61 — dropped by PyTorch ≥2.8; 4 GB VRAM can't run the big models at 1:1 anyway. The 5600X can. |
| Kokoro (EN, ZH) + Piper (PL, DE) | No single local model covers all four well at 1:1. Kokoro has no Polish or German; Piper covers everything but is flatter. |
| Speed is solved; **quality is the constraint** | Expected 6–15× realtime. Complexity budget goes to text normalization and mastering, not inference tuning. |
| `Document` is the only intermediate | Keeps format support open-ended — new parsers need no downstream changes. |
| Content-hashed chunk cache | Makes 10-hour renders resumable and edits incremental. |
| SQLite + in-process pool, no Redis/Celery | Single-user local app; a broker is pure overhead. |
| Local-only, no accounts, file export only | Confirmed with the user. YouTube upload stays manual. |
