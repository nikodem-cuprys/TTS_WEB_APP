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
| **G1** ✅ | An EPUB becomes an English MP3 audiobook from the CLI | `M2-10` |
| **G2** ✅ | The whole flow works in the browser, no CLI needed | `M3-5` |
| **G3** ✅ | All four languages render at acceptable quality | `M4-4` |
| **G4** | Output is upload-ready: M4B + MP4 + SRT + timestamps | `M5-9` |
| **G5** | Measured end-to-end RTF < 1.0, listening pass clean | `M6-2` |

---

## 📋 Backlog

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

### M5 — Publishing

- **[M5-8] Part splitting under 12 h** — M · M5-3
  Chapter-aligned splits at a configurable limit (default 11 h 45 m), consistent part naming.

- **[M5-9] 🎯 G4 — Exports API + download UI** — S · M5-1…M5-8
  ✅ Every artifact for a finished book is downloadable from one panel.

---

## 🔨 In Progress

*(empty — WIP limit 3)*

---

## 👀 Review

*(empty)*

---

## ✔️ Done

### M5 — Publishing (7 of 9 cards so far: M5-1, M5-2, M5-3, M5-4, M5-5, M5-6, M5-7)

A single job can now request any combination of `mp3,m4b,opus,flac,wav,srt,vtt,mp4` — each format is
produced from the one already-mastered WAV (no format-specific re-synthesis) and recorded as a new
`JobArtifact(job_id, format, path)` row, so a job's `output_path`/`/download`/`/stream` stay MP3-only
for backward compatibility while a new `GET /api/jobs/{id}/artifacts/{format}/download` endpoint
serves every other produced format. M5-1/M5-2/M5-6 (audio-only formats + subtitles) were verified
against the **real running dev server**, not just pytest (the Chrome extension needed for an actual
browser session wasn't connected in that environment, so browser-driven GUI verification — the
project's usual pattern for GUI changes — was substituted with a direct HTTP smoke test against
`uvicorn`/real Kokoro synthesis): uploaded a real 2-chapter EPUB, requested all 7 then-supported
formats in one job, and confirmed all 7 downloaded successfully with correct `Content-Type`s,
non-empty bodies, and — independently re-measured via `ffprobe`, not just "didn't error" — 2
correctly-titled, contiguous M4B chapter markers and SRT/VTT cues whose timestamps exactly match the
real per-segment synthesis timing. The frontend (`Render` page's format checkboxes, `Job` page's
per-format download buttons) was verified via a real `tsc -b && vite build` and `oxlint` pass (clean;
the one pre-existing lint warning on `Render.tsx` predates this change, confirmed via `git stash`)
rather than an actual browser session, given the extension limitation above — noted explicitly per
the project's "say so if you can't test the UI" rule rather than claimed as done.

- **[M5-1] M4B chaptered export** — M · M2-8 — chapter spans are derived from each chapter's
  already-known segment `start_s`/`duration_s` (no new alignment step): a chapter's marker runs
  from its first segment's start to the *next* chapter's start (so the inter-chapter pause reads as
  trailing silence of the chapter before it), and the last chapter's marker ends at the real end of
  the track. A chapter that produced zero segments (e.g. every block normalized to empty text) is
  skipped rather than emitting a bogus zero-length marker — covered by a dedicated unit test.
  Chapter titles are escaped per the FFMETADATA1 spec (`=`, `;`, `#`, `\` all have syntactic meaning
  there) — also covered by a regression test with a title containing all four characters.
  ✅ Chapter markers are navigable in a real audiobook player — verified via `ffprobe -show_chapters`
  against both a synthetic ffmpeg-generated file and the real end-to-end render above.

- **[M5-2] Opus / FLAC / WAV exports** — S · M2-8 — Opus and FLAC re-encode from the mastered WAV;
  WAV is a lossless `-c:a copy` remux under the final filename (no re-encode needed, since the
  mastered file is already a WAV). One real finding while writing the Opus test: `ffprobe` reports
  metadata tags on the **stream**, not the **format**, for an Ogg/Opus container — unlike MP3/FLAC/
  WAV/M4B, which all put tags on `format.tags`. Confirmed directly against a real ffmpeg encode
  before fixing the test, rather than assumed.

- **[M5-3] MP4 static-cover render** — M · M2-8 — `video/render.py`'s `render_static_mp4()` feeds
  ffmpeg the cover image (or, if the book has none, a flat placeholder background generated via an
  `-f lavfi color=...` source — a proper generated title/author cover is [M5-5]'s job, not this
  card's) as a looped input alongside the mastered WAV, encoded with `-tune stillimage` at a very low
  2 fps output. Wired into `pipeline/runner.py`'s export loop as an eighth `SUPPORTED_EXPORT_FORMATS`
  entry (`"mp4"`) and into the jobs API's artifact media-type map (`video/mp4`); the frontend's
  generic per-format checkbox/download-button lists (`EXPORT_FORMATS`, `Render.tsx`'s
  `FORMAT_LABELS`, `Job.tsx`'s `ARTIFACT_LABELS`) needed only a new entry each, no new UI code, since
  M5-9's download panel design was already format-agnostic.
  ✅ A 10-hour book encodes in minutes, not hours, and stays reasonably small — verified directly:
  the real end-to-end pipeline test (`test_run_job_produces_every_requested_export_format`) now also
  requests `mp4` alongside the other 7 formats and, via `ffprobe`, confirms the output actually
  contains both a video and an audio stream and that its duration matches the mastered audio to
  within 0.5s — not just "ffmpeg exited 0." A dedicated `test_video_render.py` separately confirms
  the no-cover placeholder-background path, a real-cover path (`h264` video codec), and the 2 fps
  output frame rate that keeps long renders fast, against synthetic ffmpeg-generated fixtures. Full
  backend suite: 191 passed (up from 172). Frontend verified via a clean `tsc -b && vite build` and
  `oxlint` pass (the one pre-existing `Render.tsx` warning is unrelated, per the prior M5 session's
  `git stash` confirmation) rather than an actual browser session — the Chrome extension was not
  connected in this environment either, so this is stated explicitly rather than claimed as done.

- **[M5-4] MP4 waveform + Ken Burns styles** — M · M5-3 — `video/render.py` grew
  `render_waveform_mp4()` and `render_kenburns_mp4()` alongside the existing static renderer, plus a
  `render_mp4(style=...)` dispatcher the pipeline runner calls so it never needs to know each style's
  function name. Waveform overlays a green-tinted (`0x3ecf8e`, theme.css's `--accent`) `showwaves`
  line across the bottom of the cover via `filter_complex`; both motion styles first scale/pad the
  cover onto a fixed 1280×720 canvas (`force_original_aspect_ratio=decrease` + `pad`, so a portrait
  book cover doesn't get cropped) since — unlike the static style, which just keeps the cover's native
  size — an overlay or zoom needs a known canvas to work against. A real, reproducible bug fixed along
  the way, in the *static* renderer this card touched incidentally while adding the shared even-dims
  guard: yuv420p (4:2:0 chroma subsampling) requires even width/height, so a real book cover of an
  arbitrary (odd) size would have made `render_static_mp4()` fail outright — never hit by [M5-3]'s own
  tests, which happened to only use even-sized synthetic covers. Fixed with a `scale=trunc(iw/2)*2:
  trunc(ih/2)*2` filter and covered by a dedicated regression test using a deliberately-odd 641×481
  cover. Ken Burns' trickiest real problem: `zoompan`'s zoom increment has to be *per-frame*, but a
  book's duration isn't known until the mastered WAV exists — a fixed increment tuned for a short clip
  would reach max zoom and freeze for the remaining hours of a long book. Fixed by probing the
  mastered WAV's real duration first (`soundfile.info()`, cheap — header-only, no full decode) and
  computing `zoom_increment = (max_zoom - 1) / (duration_s * fps)` so the drift reaches its target
  zoom exactly at the audio's own end regardless of book length. A second, subtler bug caught only by
  actually running the encode (not just reading the filter graph): Python's `repr()` of that
  increment renders in scientific notation for long books (~1e-7 for a 10-hour book at 24fps), which
  ffmpeg's expression evaluator doesn't reliably parse as a filter literal — fixed by formatting it as
  a fixed-decimal string (`f"{zoom_increment:.12f}"`) instead.

  Style selection is job-level, not per-format: `Job.video_style` (`"static"`/`"waveform"`/
  `"kenburns"`, default `"static"`) flows from a new `CreateJobRequest.video_style` field (validated
  against `VIDEO_STYLES` at the API boundary, same 422-on-unknown-value pattern the format list
  already used) through `create_job()` to the runner's `mp4` export branch. The `Render` page shows a
  video-style `<select>` only when the `mp4` checkbox is checked, using the same
  generic-list-drives-UI pattern `EXPORT_FORMATS` already established, so no new component was needed.
  ✅ Verified directly, not just "the filter graph looks right": a dedicated
  `test_video_render.py` suite (10 cases) exercises all three styles' cover and no-cover paths against
  synthetic ffmpeg fixtures — including asserting the waveform/Ken Burns outputs are actually a
  1280×720 canvas and that `render_mp4()`'s dispatcher produces output matching the requested style's
  own frame rate (2fps for static vs. 24fps for waveform) — real, distinguishing signals, not just
  "didn't crash." A `@pytest.mark.slow` pipeline test
  (`test_run_job_honors_a_non_default_video_style`) renders a real book end to end with
  `video_style="waveform"` and confirms via `ffprobe` that the *runner*, not just the standalone
  render function, actually threads the style through — the multi-format test alone would have missed
  a bug where `job.video_style` was accepted by the API but silently ignored by the export loop. Full
  backend suite: 201 passed (up from 191). Frontend verified via a clean `tsc -b && vite build` and
  `oxlint` pass (same pre-existing, unrelated `Render.tsx` warning; no actual browser session, per the
  same Chrome-extension-unavailable caveat as [M5-3]).

- **[M5-5] Generated cover art** — S · M5-3 — a new `video/cover.py` (`generate_cover()`) draws a
  1600×1600 dark/green-theme placeholder with Pillow — a thin `--accent` frame, the title
  word-wrapped and centered (auto-shrinking its font, down to a floor, until it fits within 5 lines
  so an unusually long title never overflows the canvas), and the author beneath in `--text-2` if
  given. Uses `ImageFont.load_default(size=...)`, Pillow's own bundled scalable font — no external
  font file to ship or a Windows-only system-font assumption to make. Added `Pillow` as a new backend
  dependency (nothing in the project pulled it in transitively). Wired into `pipeline/runner.py`'s
  export stage: when a book has no real extracted cover *and* the job actually requested a
  format that uses one (`mp3`/`m4b`/`mp4` — checked explicitly, so an SRT/VTT/Opus/FLAC/WAV-only job
  never pays for a Pillow render it wouldn't use), a fallback is generated fresh into the job's own
  cache-dir path and used exactly like a real cover from there on. Deliberately generated **per
  render, not cached on `Book.cover_path`**: a title/author is already editable via `PATCH
  /api/books/{id}` (`BookUpdate`, pre-existing from before this card), and caching the very first
  generated cover would have baked in the pre-edit title, going stale on every later render — regenerating
  it fresh each time costs a few tens of milliseconds and is worth it for correctness.
  ✅ Verified concretely: 5 new `test_cover.py` cases confirm the correct 1600×1600 output size, the
  real `--bg` background color sampled from an actual output pixel (not just "didn't throw"), the
  no-author layout, and that both an empty and a pathologically long title still produce a valid,
  non-overflowing image. The existing multi-format pipeline test (this fixture book has no cover of
  its own) now additionally confirms via `ffprobe` that the generated cover is actually what
  ends up embedded — the MP4's video track is 1600×1600 (`generate_cover()`'s own size, distinguishing
  it from `video/render.py`'s separate 1280×720 flat-color placeholder, which now only fires when
  *no* cover_path is passed in at all) and the MP3 carries a real `attached_pic` cover stream, which
  it did not before this card (no cover meant `encode_mp3()` skipped the cover entirely). Full backend
  suite: 206 passed (up from 201). No frontend change was needed or made — nothing in the UI serves
  cover images yet (`has_cover` is declared in `api.ts` but unused), so this card's own scope stayed
  backend-only.

- **[M5-6] SRT / VTT subtitles** — S · M2-7 — `publish/subtitles.py`, built from the exact same
  per-segment `(start_s, duration_s)` M5-1's chapter markers use — genuinely free, no forced
  alignment. Blank-after-normalization segments and segments that never got a `start_s`/`duration_s`
  (failed/未-synthesized) are skipped so they don't produce a bogus zero-duration or `None`-timed
  cue. Timestamp formatting (`HH:MM:SS,mmm` for SRT, `HH:MM:SS.mmm` for VTT) is covered by dedicated
  unit tests including an hour-boundary case and a defensively-clamped negative-input case.

- **[M5-7] YouTube chapter timestamps + description** — S · M2-7 — a new
  `publish/chapters_txt.py` (`build_youtube_description()`) reuses the exact same `ChapterMarker`
  list [M5-1]'s M4B chapters and [M5-6]'s `_build_chapter_markers()` already compute — no separate
  alignment step, same "genuinely free" pattern the rest of `publish/` follows. Output is a
  ready-to-paste video description: book title, author, a blank line, then one `H:MM:SS Chapter
  Title` (or `M:SS` under an hour) line per chapter — the exact format YouTube auto-detects as video
  chapters, which requires the *first* line to read `0:00`; guaranteed here since
  `_build_chapter_markers()` always starts from the first enabled chapter's first segment, which
  always begins at t=0. Wired in as a ninth export format (`"chapters"`, `.chapters.txt`,
  `text/plain`) through the same `SUPPORTED_EXPORT_FORMATS` / artifact-media-type / frontend-label
  pattern every format since [M5-2] has followed — computed purely from segment timing, so (unlike
  MP4) it doesn't depend on which audio format was actually requested and needed no cover-art
  involvement at all.
  ✅ Verified concretely: 6 new `test_chapters_txt.py` cases cover minute/second formatting, the
  hour-boundary switch to `H:MM:SS`, a defensively-clamped negative-timestamp input, and the
  full title/author/chapters description assembly with and without an author. The existing
  multi-format pipeline test now also requests `chapters` alongside the other 8 formats and confirms
  the real output starts with the book's actual title, contains its actual author, starts its first
  chapter line at `0:00`, and — cross-checked against the *M4B's own* `ffprobe`-read chapter titles,
  not just re-deriving the same value the code under test would produce — that both real chapter
  titles actually appear in the generated text. Full backend suite: 212 passed (up from 206).
  Frontend verified via a clean `tsc -b && vite build` and `oxlint` pass (same pre-existing,
  unrelated `Render.tsx` warning; no actual browser session, same Chrome-extension-unavailable
  caveat as the rest of this M5 session).

### M4 — Multi-language (all 6 cards) — 🎯 G3 achieved

Verified end-to-end for all three new languages, not just their normalizer unit tests: a
parametrized integration test renders a real small EPUB through the *entire* pipeline (real
normalizer → real engine → real ffmpeg mastering) for Polish, German, and Chinese, matching how
G1 proved English in M2. All three pass. Also drove a real Polish render through the actual
browser GUI end to end (upload → language badge already correctly "pl" → voice picker
auto-filtered to the 2 Polish voices → live SSE progress → a real downloadable MP3, verified via
`ffprobe`), and separately verified the two other new GUI pieces (the language-override selector
and the lexicon editor) in the same session.

**Chinese needed a real fix, not a workaround.** M2 had already found that this `kokoro-onnx`
package's built-in phonemizer produces garbage for Chinese (English-fallback phonemes wrapped in
`(en)...(cmn)` markers). The fix: phonemize with `misaki.zh.ZHG2P` (the actual G2P frontend Kokoro
was trained with, already a transitive dependency once `misaki[zh]` was added) and feed Kokoro the
phonemes directly via `is_phonemes=True`, bypassing its broken built-in path. Verified concretely,
not just "it sounds okay": `tokenizer.known(phonemes) == phonemes` — **100%** of misaki's output
phonemes exist in Kokoro's vocabulary, vs. the old path's near-total loss.

**`num2words` has no Chinese backend at all** (`NotImplementedError`) — found `cn2an` already
installed transitively via `misaki[zh]` and used its `an2cn()` instead. Its `"direct"` mode gives
the correct **digit-by-digit** year reading Chinese actually uses ("2024" → "二零二四"), which
`"low"` (cardinal) mode does not.

**Two real, reproducible bugs found and fixed via direct output inspection, each now covered by a
regression test** (beyond the declension limitations below, which are accepted-by-design, not
bugs):
1. **Chinese year regex matched a 4-digit substring of a longer number.** "12345" became
   "一二三四" + "五" (digit-by-digit garbage) instead of the correct cardinal reading, because the
   year pattern had no digit-adjacency check. The fix generalizes beyond this bug: the other
   normalizers bound their year regex with `\b`, but Python's `re` treats CJK characters as `\w`,
   so `\b` between a digit run and a following Chinese character (e.g. "1939年") **never matches at
   all** — a `\b`-based version of the Chinese year regex would have silently matched no real year
   ever. `(?<!\d)...(?!\d)` is the correct tool here, not `\b`.
2. **German `€` amounts were silently dropped**, and `$`-prefixed amounts in German text produced
   garbled output like `"Cent.sechsundfünfzig."`. Root causes: a trailing `\b` right after the `€`
   symbol can never match (`\b` needs a `\w`/`\W` transition, and symbol-then-punctuation is
   `\W`-to-`\W`), and the `$`/`£` handler assumed German-native comma-decimal formatting instead of
   the English-style formatting `$` amounts conventionally keep even inside German text.

**Declension is out of scope for Polish and German, by design, not oversight** — documented
explicitly in both modules' docstrings. Polish numerals and German ordinal adjectives both decline
by grammatical case and gender/animacy ("dwóch mężczyzn" vs. "dwie kobiety"; "drittes Kapitel" vs.
"dritten Mai"), which needs knowing what noun a number modifies and parsing sentence-level
grammatical case — a morphological-analysis problem, not a text-normalizer one. Both always emit
one citation form (verified `num2words`' German backend has no gender/case parameter at all).
Intelligible in every sentence, grammatically the "wrong" ending in some — the same tradeoff
essentially every rule-based normalizer for these languages makes.

**The lexicon's core promise — editing one entry only invalidates the chunks it affects — holds
because of *when* substitution happens, not a special cache-versioning mechanism.**
`apply_lexicon()` runs on each block's text *before* normalization and segmentation, so a chunk
whose text never contained the edited pattern comes out byte-identical both times, and its cache
key (a hash of its exact final text) is therefore untouched. Verified concretely: rendered a
2-paragraph chapter, added a lexicon entry affecting only one paragraph, re-rendered, and confirmed
the affected paragraph's cache key changed while the unaffected paragraph's — and an unrelated
chapter heading's — cache key and underlying cached file path were byte-identical across both
runs (a real cache hit, not just "didn't error").

Also closed a real validation gap while wiring routing: nothing previously stopped a request from
pairing a book with one engine's voice from a different engine (e.g. a Piper voice on an
English/Kokoro-routed book), which would have failed deep inside a worker instead of at the API
boundary. `POST /api/books/{id}/jobs` now checks `voice.engine == engine_for_language(book.language).id`
before creating the job.

172 pytest cases total (up from 100 at the start of M4), including the three-language
parametrized pipeline test and the lexicon cache-scoping test.

- **[M4-1] Piper ONNX engine** — M · M2-1 — voice metadata read straight from each voice's
  `.onnx.json` sidecar (sample_rate, quality, language) without loading the ONNX session, so
  `/api/voices` stays fast; verified real synthesis for both Polish voices and the German voice.
- **[M4-2] Polish normalizer + voices** — L · M4-1, M2-3 — 16 tests; fixed a real capitalization
  bug along the way ("Np." was collapsing to lowercase "na przykład" mid-sentence).
- **[M4-3] German normalizer + voices** — M · M4-1 — 17 tests; fixed the `€`-boundary and
  `$`-formatting bugs above; ordinal-period conversion ("3. Kapitel") deliberately scoped to a
  known word list (Kapitel/Teil/Band/Akt/Jahrhundert/month names) to avoid misreading an ordinary
  sentence-ending number followed by a new capitalized sentence.
- **[M4-4] 🎯 G3 — Chinese support** — L · M2-2 — 12 normalizer tests + dedicated Kokoro/misaki
  integration tests (including the 100%-vocabulary-coverage assertion above); `segment.py` gained a
  language-aware chunk joiner (`""` for zh instead of `" "`) so packed chunks don't get an ASCII
  space foreign to the script.
- **[M4-5] Language → engine routing + override UI** — S · M4-1 — `LANGUAGE_ROUTING` now covers
  all four languages; "override" implemented as `PATCH /api/books/{id}` for the language field
  (simpler and more durable than a per-render override — fixing a wrong auto-detected language
  once fixes every future render) plus the voice/engine mismatch validation above.
- **[M4-6] Pronunciation lexicon + UI** — M · M2-5 — cache-scoping behavior verified end-to-end
  (see above); UI is a simple pattern → replacement list with an enabled toggle and regex option
  on the Book page.

### M3 — GUI (all 7 cards) — 🎯 G2 achieved

Driven end to end in a real Chrome browser via `claude-in-chrome` (chromium-cli wasn't available on
this machine), not just typechecked: uploaded a real EPUB via drag-and-drop, expanded a chapter,
edited a block's text and a chapter's title inline and confirmed both survived a full page reload,
toggled a chapter off/on, started a render, watched **live SSE progress** through all 5 stages
against the real backend, previewed voices with real synthesized audio, and round-tripped a
settings change (worker count) through the real `Setting` DB table.

**Two real bugs surfaced by browser testing that no unit test had caught, both now fixed with
regression tests:**
1. **Timestamps showed "7232s elapsed" instead of "35s."** SQLite round-trips our (always-UTC)
   datetime columns as naive, and a bare `.isoformat()` on a naive value has no UTC offset —
   which JavaScript's `Date` parser then reads as *local* time, not UTC. Every timestamp in every
   API response was silently wrong by the viewer's own UTC offset. Fixed with a shared `utc_iso()`
   helper (`app/util.py`) applied at every datetime serialization boundary (Job timestamps via
   manual formatting, Book's via a Pydantic `field_serializer`). **Standing lesson: any new
   datetime field needs the same treatment — see the standing decision below.**
2. **The `<audio>` player showed 0:00/0:00 and never loaded**, even though the exact same file
   downloaded and played fine outside the browser. Root cause: `FileResponse(..., filename=...)`
   sets `Content-Disposition: attachment`, which tells the browser this is a file to save, not
   inline media to play — confirmed by testing a trivial vanilla ffmpeg-generated MP3, which hit
   the identical stuck state. Fixed by adding a separate `GET /api/jobs/{id}/stream` endpoint
   (no `filename=`, so no attachment header) for the `<audio>` element's `src`, keeping `/download`
   (with the attachment header) for the explicit download button.

Also diagnosed and ruled out a **false positive**: this specific `claude-in-chrome` automated
Chrome instance cannot decode *any* MP3 (confirmed by testing a minimal vanilla ffmpeg sine-wave
file, served with no proxy involved at all, which hung identically) — an environment limitation,
not an app bug. The pipeline's actual audio correctness was independently confirmed via `ffprobe`
(valid duration, tags, bitrate) rather than by ear in this session.

Backend also grew a fair amount beyond the original card list to make the GUI possible: job
creation runs the render in a background thread (`app/api/jobs.py`, its own DB session via
`db.new_session()` since the request-scoped session closes when the endpoint returns), a chapter/
block PATCH API for inline editing, voice preview with content-addressed caching (first click
synthesizes, every one after is instant), a `Setting`-table-backed settings store, and a
`model_manifest.py` shared between `scripts/fetch_models.py` and the Settings page's model-status
view (no more duplicated manifest). Cancellation is checked between **batches within the
synthesize stage** (`SYNTHESIZE_BATCH_SIZE = 50`), not just between stages — the naive "check once
per stage" design would leave cancel waiting for an entire book's synthesis to finish, since that
stage dominates total render time by far.

100 pytest cases total (up from 76 after M2), including real end-to-end job creation → SSE → poll
→ download flows against the live API (background thread + isolated test DB, with the same
`get_settings()` cache-clearing pattern M2 established, applied to a new wrinkle: the background
thread's `db.new_session()` isn't reachable via FastAPI's `dependency_overrides` at all, since it's
a plain module-level call, not a `Depends()` — fixed by monkeypatching the name directly in the
`app.api.jobs` module).

- **[M3-1] Design system components** — M · M0-4 — `Button/Card/Select/Slider/ProgressBar/Badge/
  Spinner` on the theme tokens; verified visually consistent dark/grey/green across every page.
- **[M3-2] Library page + upload dropzone** — M · M1-8 — drag-and-drop verified with a real file.
- **[M3-3] Book page: chapter tree + editing** — L · M3-2 — toggle, rename, and inline block-text
  edit all verified to persist across a reload. Word count + duration estimate computed client-side
  (150 wpm heuristic) from real block text. Drag-to-reorder was scoped out — no ✅ line required it.
- **[M3-4] Render config page** — M · M2-9 — voice picker scoped to the book's language, with an
  explicit "not supported yet" state for pl/de/zh rather than a silent failure.
- **[M3-5] 🎯 G2 — Job monitor + SSE** — M · M2-9 — real live progress verified through all 5
  stages; cancel checked between synthesize batches, not just between stages (see above).
- **[M3-6] Voice browser + preview** — S · M2-2 — all 54 voices grouped by language; non-English
  groups carry an explicit "preview only, not usable yet" badge matching the M2 finding.
- **[M3-7] Settings page** — S — worker count / loudness target save round-trip verified against
  the real `Setting` table; disk usage and model presence both verified against real numbers.

### M2 — TTS core, English (all 10 cards) — 🎯 G1 achieved

Ran a real EPUB through the CLI end to end: `python scripts/render_book.py book.epub --voice
af_heart` produces a tagged, chaptered MP3, and every normalizer rule fired correctly on real
prose in that run — inspected the persisted `Segment` rows directly and confirmed `$1,234.56` →
"one thousand, two hundred and thirty-four dollars, fifty-six cents", `1889` → "eighteen
eighty-nine", `Dr. Whitfield` → "Doctor Whitfield" (twice, consistently), `1914-1918` → "nineteen
fourteen to nineteen eighteen", and pause durations landing exactly on the paragraph (0.6s) vs.
chapter (1.2s) boundaries by design. Independently re-measured the mastered output with a fresh
`ffmpeg loudnorm` pass and got -18.95 to -19.03 LUFS against a -19 target.

**Worker pool tuning was empirically benchmarked, not guessed**: swept 1×6, 4×2, 6×2, 4×3, and
8×1 (workers × intra-op threads) on the real 6C/12T CPU with the real model. **4 workers × 2
threads won** (RTF 0.30 on a 48-chunk batch) — both denser (6×2, RTF 0.32) and sparser (8×1, RTF
0.45; 1×6, RTF 0.57) configurations were worse, so the KANBAN estimate of "workers × threads ≈ 10"
below is superseded by this measurement; the code uses 4×2 (8 threads) as the default.

Also discovered mid-build that this `kokoro-onnx` package phonemizes through a bare
`phonemizer`+espeak-ng pass-through, not the `misaki` G2P frontend the Kokoro model card assumes
— tested passing `lang="cmn"` for the Chinese voices and confirmed it silently mis-phonemizes
(falls back to English phonemes wrapped in `(en)...(cmn)` markers). `KokoroEngine.synth()` now
only claims `en-us`/`en-gb`; real Mandarin support is deferred to **[M4-4]** with its own G2P
solution, not a lang-tag change.

76 pytest cases total (up from 27 after M1), including two `@pytest.mark.slow` tests that run
real Kokoro synthesis through the process pool and the full pipeline runner. Hit and fixed a real
test-isolation bug along the way: `get_settings()` is `@lru_cache`'d process-wide, so a test whose
fixture only sets an env var can silently read another test's already-cached (real-path) Settings
if an earlier test in the same pytest session triggered the cache first — fixed by explicit
`get_settings.cache_clear()` in the fixtures that need process-local isolation (pool workers, as
separate spawned processes, were never affected — only the parent process's own calls were).

- **[M2-1] TTSEngine protocol + registry** — S — `tts/base.py`, `tts/registry.py`.
- **[M2-2] Kokoro ONNX engine** — M · M2-1, M0-5 — 54 voices catalogued (28 en, 8 zh, others
  es/fr/hi/it/ja/pt); metadata correct for all, synthesis verified for en only (see above).
- **[M2-3] English normalizer** — L · M1-1 — 21 tests incl. all 5 acceptance-criteria strings
  plus GBP/EUR currency, decimals, and the ALL-CAPS/acronym-allowlist heuristic.
- **[M2-4] Segmenter** — M · M2-3 — pysbd + greedy packing; verified never splits a sentence even
  when a single sentence exceeds `max_chars`.
- **[M2-5] Chunk cache** — M · M2-4 — sha256 of every field that affects output audio; verified
  each field independently changes the key, and a real hit/miss/write round-trip.
- **[M2-6] Worker pool** — M · M2-2, M2-5 — see tuning note above; workers write straight to the
  chunk cache and return only metadata, avoiding IPC overhead from shipping raw audio arrays.
- **[M2-7] Assembly + pauses + fades** — M · M2-6 — verified fade ramps to ~0 at every chunk edge
  and total duration matches Σ chunks + Σ pauses to within 50ms.
- **[M2-8] Loudness master + MP3 export** — M · M2-7 — two-pass `loudnorm` + 60Hz high-pass;
  independently re-measured output at -19.0 LUFS (target -19); ID3 tags + cover verified via
  `ffprobe`.
- **[M2-9] Pipeline runner + job records** — M · M2-8 — `Job`/`JobStage`/`Segment` rows persisted
  and verified populated correctly after a real render (statuses, `start_s`/`duration_s`).
- **[M2-10] 🎯 G1 — EPUB → English MP3 via CLI** — S · M2-9 — `scripts/render_book.py`; the
  verification run above **is** this gate.

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
| Speed is solved; **quality is the constraint** | Measured RTF ~0.30 (4 workers × 2 intra-op threads, empirically swept — beat 1×6, 6×2, and 8×1). Complexity budget goes to text normalization and mastering, not inference tuning. |
| `Document` is the only intermediate | Keeps format support open-ended — new parsers need no downstream changes. |
| Content-hashed chunk cache | Makes 10-hour renders resumable and edits incremental. |
| SQLite + in-process pool, no Redis/Celery | Single-user local app; a broker is pure overhead. |
| Local-only, no accounts, file export only | Confirmed with the user. YouTube upload stays manual. |
| Every datetime field must round-trip through `util.utc_iso()` | SQLite drops tzinfo on read; a bare `.isoformat()` on the resulting naive value has no UTC offset, which JS's `Date` parser misreads as local time. Discovered in M3; applies to any future datetime field (M5's export timestamps, etc). |
| Inline-playable media needs its own endpoint, separate from download | `FileResponse(..., filename=...)` sets `Content-Disposition: attachment`, which stops an `<audio>`/`<video>` element from loading it inline. M5's MP4 preview will need the same `/stream`-vs-`/download` split M3 built for the job's MP3. |
| Chinese synthesis: phonemize with `misaki.zh.ZHG2P`, feed Kokoro `is_phonemes=True` | Resolved in [M4-4]. Kokoro's own built-in phonemizer is bare espeak-ng, not the `misaki` frontend the model was trained with; verified 100% of misaki's phonemes exist in Kokoro's vocabulary vs. near-total loss the old way. |
| Chinese numbers: use `cn2an`, not `num2words` | `num2words(lang="zh")` raises `NotImplementedError` — no Chinese backend exists at all. `cn2an` (already transitive via `misaki[zh]`) covers it; its `"direct"` mode is what gives the correct digit-by-digit year reading. |
| `\b` doesn't work at a digit/CJK or digit/symbol boundary | Python's `re` treats CJK characters as `\w`, so `\b` never fires between a digit run and a following Chinese character — use `(?<!\d)...(?!\d)` for CJK number boundaries instead. Separately, `\b` right after a symbol like `€` can also never match (symbol-then-punctuation is `\W`-to-`\W`) — found via two independent bugs in [M4-4]/[M4-3]. |
| Polish/German numeral declension is out of scope, by design | Both decline by grammatical case and gender/animacy — correct agreement needs knowing what noun a number modifies and parsing sentence-level case, a morphological-analysis problem beyond a text normalizer. Both emit one citation form; documented explicitly in each module's docstring, not silently accepted. |
| Lexicon substitution runs before normalization/segmentation | Makes "editing an entry invalidates only the chunks it affects" true for free — a chunk's cache key is a hash of its exact final text, so an unaffected chunk's key (and cached audio) never changes. No separate cache-versioning scheme needed. Verified end-to-end in [M4-6]. |
