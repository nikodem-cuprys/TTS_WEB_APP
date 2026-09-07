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
| **G4** ✅ | Output is upload-ready: M4B + MP4 + SRT + timestamps | `M5-9` |
| **G5** | Measured end-to-end RTF < 1.0, listening pass clean | `M6-2` |

---

## 📋 Backlog

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

*(M5 complete — see M6 in Backlog above)*

---

## 🔨 In Progress

- **[M6-2] 🎯 G5 — Listening QA pass × 4 languages** — L · M4-* — **blocked on the user's own ears**,
  by this card's own explicit "no automated metric substitutes" acceptance criterion; an AI agent
  cannot judge audio naturalness or pause pacing by listening. What's done: a new
  `scripts/render_qa_clips.py` renders a real ~3-minute-per-language clip (2:58 en / 3:05 pl / 2:50 de
  / 2:42 zh) — an original 3-chapter story per language (not from any real book), deliberately loaded
  with exactly the content this card asks to check: cardinal/decimal/percentage numbers, currency,
  dates, negative temperatures, fractions, abbreviated titles (Mr./Dr./Prof. and their pl/de
  equivalents), an ALL-CAPS word, and a roman-numeral chapter heading, with three chapter breaks (1.2s
  pause) and several paragraph breaks (0.6s pause) per clip to exercise pacing, and enough sentence
  variety to expose chunk-join artifacts. The four MP3s were sent directly to the user, and a
  published review checklist (one card per language: an item-by-item checklist plus a pass/issues
  toggle and a notes field, state saved to the browser via `localStorage`) accompanies them —
  <https://claude.ai/code/artifact/2a2e57d7-c81e-476d-bae8-4457d10825cc>. Awaiting the user's actual
  listening pass; record the real per-language verdict here once they report back, then close the G5
  gate.

---

## 👀 Review

*(empty)*

---

## ✔️ Done

### M6 — Quality & performance (5 of 6 cards so far: M6-1, M6-3, M6-4, M6-5, M6-6)

- **[M6-1] bench.py + RTF gate** — M · M4-* — `scripts/bench.py` renders a fixed ~5-minute passage
  per language through the **real production pipeline** (`pipeline.runner.run_job()` — pooled
  synthesis, assembly, loudness mastering, MP3 encode, exactly what a real render does), reporting
  both that end-to-end RTF and a separate "engine RTF" (the same passage's chunks synthesized
  sequentially through the raw engine, no pool/assembly/mastering/encode overhead) so the pool's own
  contribution is visible. Doubles as a CI-style gate: exits non-zero if any language's end-to-end RTF
  doesn't beat `--target-rtf` (default 1.0). The four passages are original prose (a short
  "lighthouse keeper" narrative, not excerpted from any real book) written in parallel across all four
  languages and deliberately loaded with the kind of content the normalizers actually handle — years,
  percentages, currency, abbreviated titles — not just plain filler words; each repetition needed to
  reach the target length is prefixed with a distinct "Part N" marker so that repeating the passage
  never produces two chunks sharing a cache key (a naive repeated-verbatim passage would have let the
  second occurrence hit the content-addressed chunk cache and silently report a falsely fast time).
  Runs in a `tempfile.mkdtemp()`-created throwaway data directory, deleted on exit, so a benchmark run
  never touches the app's real cache/output/database.
  Two real, reproducible bugs hit and fixed while building this, both instructive beyond this one
  script:
  1. **A classic Windows `ProcessPoolExecutor` pitfall, not a heredoc this time.** The env-var/tempdir
     setup was originally unindented top-level code — but on Windows, the `spawn` start method
     re-imports the entry script in every worker process, and an unguarded `tempfile.mkdtemp()` /
     `os.environ[...]` assignment there let each of the 4 workers overwrite its own *correctly
     inherited* copy of `AUDIOBOOK_DATA_DIR` with a fresh, different random tempdir before actually
     doing any synthesis work — splitting chunk-cache reads/writes across processes and crashing the
     parent with `soundfile` "Error opening ... System error" once it tried to read a chunk a worker
     had written to a directory the parent didn't know about. Root cause confirmed directly (found 3
     result directories after one 2-worker run, 2 of them containing only stray files a worker wrote,
     matching the worker count exactly), not assumed. Fixed by guarding that specific setup with
     `if __name__ == "__main__":` — the spawn bootstrap gives re-imported children `__name__ ==
     "__mp_main__"`, so the guard is exactly what makes a worker inherit the parent's real value
     instead of manufacturing its own. This is a sharper, more general version of the existing
     "multiprocessing + stdin heredocs don't mix on Windows" standing decision below — same
     re-import-of-`__main__` root mechanism, different unguarded-top-level-code symptom.
  2. **Chinese has no whitespace between words.** The initial "~N minutes" passage-length estimate
     used `str.split()` word counts for every language, including Chinese — where an entire unspaced
     sentence counts as "one word," undercounting the real length by roughly two orders of magnitude.
     A `--minutes 0.2` smoke test that should have produced a ~30-second Chinese passage instead
     produced 288 seconds of audio, caught by comparing actual vs. requested duration rather than
     assuming the loop terminated correctly. Fixed with a characters-per-minute heuristic for Chinese
     specifically instead of a word count, since a CJK character is the right unit there.
  A real, incidental finding while smoke-testing against the live dev server for [M5-9]'s
  verification earlier in this session had also left stray output files under the repo's real `data/`
  directory (a wrong cleanup path was used at the time) — discovered and cleaned up in the course of
  this card's own real-data-dir-pollution check, which is exactly the kind of check this card's
  isolated-tempdir design exists to make unnecessary going forward.
  ✅ **End-to-end RTF < 1.0 for all four languages** with the real default 4-worker pool, verified with
  the actual ~5-minute passages (not just the quick smoke-test lengths used while debugging): English
  0.131, Polish 0.083, German 0.126, Chinese 0.150 — all comfortably inside the ≥1:1 realtime target,
  consistent with M2's earlier from-a-real-book English RTF ~0.30 measurement (this run's lower number
  reflects a fixed, non-book-formatting-heavy benchmark passage rather than a regression). Recorded in
  a new "Measured performance" section in `README.md`, per this card's own acceptance line, including
  the reproduction command. No pytest coverage was added — `scripts/bench.py`, like the pre-existing
  `scripts/render_book.py` and `scripts/fetch_models.py`, is verified by direct execution against the
  real backend rather than unit-tested, the same convention KANBAN's M2-10/M0-5 entries already
  established for this project's standalone scripts.

- **[M6-3] PDF parser hardening** — L · M1-4 — closed all three real-world gaps this card names, each
  found and fixed via direct output inspection against a purpose-built synthetic fixture, not assumed
  to work.
  1. **Drop caps.** The actual bug turned out subtler than "a drop cap forms its own stray block":
     pymupdf extracts a drop-cap glyph and the rest of its opening word as two separate *lines within
     one block* (it splits a line wherever the font size changes), so the existing line-join (a
     space — correct for real wrapped lines) produced "T he ancient city..." instead of "The ancient
     city...". Worse, that block's `max_size` picked up the drop cap's own huge font size, so the
     *whole paragraph* tripped `_is_heading_block`'s 1.3× ratio check and got misread as a chapter
     title. Fixed at the source in `_page_blocks()`: a new `_merge_drop_cap_lines()` merges a short,
     alphabetic, markedly-oversized line straight into the line after it (no separator), purely from
     the two lines' own text/size — no document-wide body-font estimate needed, and it runs before one
     is even available. The block's `max_size` is then computed from the *merged* lines, so it no
     longer carries the drop cap's inflated size once merged. A second, independent defense (kept for
     a differently-structured real-world PDF where a drop cap genuinely is its own block, not just its
     own line) merges an un-merged oversized 1-2 character block into whatever follows it on the same
     page, and `_is_heading_block` now also refuses to call anything that short a heading even if font
     size alone would have suggested it.
  2. **Footnotes.** Unlike a running header/footer, footnote text differs page to page, so the
     existing recurrence-based `_strip_headers_footers()` can never catch it — it needed an entirely
     separate signal. Footnote-zone blocks (positioned in the lower ~22% of the page, just above the
     header/footer's own footer zone, in a font noticeably smaller than body text) are now classified
     as `BlockKind.skip` rather than `BlockKind.para` — kept as real, visible, editable blocks (a user
     can still promote one back to narrated in the UI) rather than silently discarded, consistent with
     how the rest of the app already treats "exclude, don't delete." **Along the way, found that
     `BlockKind.skip` had existed in the schema since FB2 support ([M1-5]) but was never actually
     wired up anywhere** — FB2's own "footnotes excluded" claim worked by never creating blocks for
     its notes body at all, not via this enum value, so nothing in `pipeline/runner.py`'s
     `_build_chunk_plan()` ever filtered `skip`-kind blocks from narration. A skip block would have
     been narrated anyway. Fixed as part of this card (small, surgical, and necessary for the new PDF
     footnote-marking to actually do anything): `_build_chunk_plan()` now filters `BlockKind.skip`
     blocks out before computing anything, including which block is a chapter's *last* one for
     pause-placement purposes — verified with a dedicated test where the skip block trails the real
     last paragraph, confirming the end-of-book pause lands on the real content, not stolen by (or
     miscounted around) the footnote after it.
  3. **Scanned (image-only) PDFs.** The graceful-degradation path (`ParseError` — "may be a scanned
     image PDF" — when zero text blocks are extracted) already existed but had no regression test;
     added one against a real image-only synthetic PDF (a plain white pixmap on every page, no text
     objects at all) to lock it in. A *partially*-scanned PDF (some real-text pages, one image-only
     page mixed in) needed no code change — a page contributing zero blocks was already silently
     tolerated, confirmed rather than assumed by including it implicitly in how `_page_blocks()`
     already worked page-by-page.
  ✅ Verified against purpose-built synthetic fixtures (this project's established PDF-testing
  convention since [M1-4], generated with `pymupdf` itself rather than committing binary files): a new
  `pdf_drop_cap_and_footnote_path` fixture (a drop-cap opening line plus a distinct, non-recurring,
  small-font footnote on every one of 3 pages) and a new `pdf_scanned_path` fixture (image-only, 2
  pages). 5 new PDF-level tests confirm the drop cap merges into real prose (not "T he ancient..."),
  is never mistaken for a chapter title, and that every footnote block — one per page, still
  individually present and correctly `BlockKind.skip` — leaves the real body paragraphs on the same
  pages untouched and still `BlockKind.para`; 1 more confirms the scanned-PDF error path. A 6th, at the
  pipeline level, confirms `_build_chunk_plan()`'s new skip-filtering directly. Full backend suite:
  235 passed (up from 229).

- **[M6-4] Disk + cache management** — M · M2-5 — size reporting already existed ([M3-7]'s
  `GET /api/settings/disk-usage`); this card closed the two real gaps the card names.
  1. **Intermediate cleanup.** Confirmed by direct inspection, not assumed: `pipeline/runner.py`
     never deleted a job's `raw.wav`/`mastered.wav` (the pre-/post-mastering full assembled track —
     the exact ~1.7 GB-per-10-hour-book intermediate this card's own warning names), its auto-generated
     fallback cover ([M5-5]), or its per-part MP4 source WAVs ([M5-8]) — every one of them a pure,
     job-scoped scratch file, never reused once `run_job()` returns, unlike the real content-addressed
     chunk cache, which must persist for resumability. Every render was leaking roughly 2× the book's
     raw WAV size permanently. Fixed with a `_cleanup_job_intermediates()` call in a `finally` block
     wrapping the whole of `run_job()`, so it fires whether the job finished, failed, or was cancelled
     — verified with two dedicated tests (real renders, not mocked): one confirms the intermediates
     are gone after a successful render while the real chunk cache is untouched, the other forces a
     failure partway through export and confirms cleanup still ran.
  2. **Prune.** A new `DELETE /api/settings/cache` endpoint (and a matching Settings-page button, with
     a two-click "Prune cache" → "Confirm: delete cached audio" pattern rather than a native browser
     `confirm()` dialog, to match the app's own chrome) empties the chunk cache on demand — the
     content-addressed cache has no automatic expiry by design ([M2-5]'s own standing decision, since
     that's exactly what makes incremental re-renders free), so on a disk-constrained machine a manual
     release valve is the right tool, not automatic eviction the card didn't ask for. Deliberately
     simple and safe rather than clever: `pool.py`'s workers already treat a missing cache entry as an
     ordinary cache miss and just re-synthesize it, so pruning — even mid-render, though the UI warns
     against it as wasteful — costs redundant work at worst, never a crash, so no locking or
     in-progress-job detection was needed.
  ✅ Verified against the **real running dev server**, not just pytest: hit the real endpoint against
  1,229 real accumulated chunk files from this session's own testing, confirmed exactly 1,229
  `files_removed` and `bytes_freed` (1.53 GB) matching what `disk-usage` had reported a moment before,
  and confirmed `cache_bytes` read back as 0 immediately after. (Along the way, discovered the dev
  server's `--reload` had silently stopped picking up file changes partway through this session's
  earlier edits — a real environment quirk, not a code bug — worked around by restarting it rather than
  trusting reload for the rest of verification.) 2 new pipeline-level tests plus 2 new API-level tests
  (a real multi-file prune, and a no-op-on-empty-cache case). Full backend suite: 239 passed (up from
  235). Frontend verified via a clean `tsc -b && vite build` and `oxlint` pass (same pre-existing,
  unrelated `Render.tsx` warning) rather than an actual browser session, given the Chrome extension
  still wasn't connected in this environment.

- **[M6-5] Error handling + recovery UX** — M · M3-5 — closed both halves the card names.
  1. **Legible failures.** The synthesize stage's failure message previously named only *how many*
     chunks failed and the raw exception text of the first one — `"2 chunk(s) failed to synthesize:
     Voice xyz not found in available voices"` — with no way to tell *which* sentence in the book
     actually triggered it. Now: `"Speech synthesis failed on 2 of 2 chunk(s). First failure —
     "Chapter One": Voice xyz not found in available voices"` — the exact chunk text (each `Segment`
     already stored it; nothing new had to be tracked) is what actually lets a user find and fix (or
     lexicon-substitute) whatever the engine choked on, verified against a real, unmocked failure (a
     nonexistent voice id, not a monkeypatched exception).
  2. **Retry.** A new `POST /api/jobs/{id}/retry` (409 if the job isn't actually failed/cancelled)
     starts a *new* job reusing the original's voice/speed/formats/video_style — sparing a trip back
     through the Render page to re-enter settings already chosen once — with a matching "Retry" button
     on the Job page. "Retry only the failed chunks" needed no new mechanism at all: it falls straight
     out of the existing content-addressed chunk cache ([M2-5]) — every chunk that synthesized
     successfully on the first attempt is an instant cache hit on retry, and only the chunk(s) that
     actually failed pay for real re-synthesis. `create_render_job`'s thread-starting code was factored
     into a shared `_start_job_thread()` helper so retry didn't have to duplicate it.
  ✅ Verified end to end against the real API (real Kokoro synthesis, not mocked): created a job,
  cancelled it, retried it, and confirmed the new job is a genuinely different job id carrying over
  every one of voice/speed/video_style, and that it actually renders to `done` with every requested
  format present. Separate tests cover retrying a still-running job (409) and a nonexistent one (404).
  3 new API-level tests, 1 new pipeline-level test (the failure-message content). Full backend suite:
  243 passed (up from 239). Frontend verified via a clean `tsc -b && vite build` and `oxlint` pass (same
  pre-existing, unrelated `Render.tsx` warning), plus a live HTTP check against the real running dev
  server (restarted, since `--reload` had again stopped picking up file changes partway through this
  session — the same quirk noted in [M6-4]) — real user data was present on that server by this point
  (the user has started using the app this session), so verification stayed to non-destructive
  requests (a 404 retry, a disk-usage read) rather than creating jobs against their real books.

- **[M6-6] README + setup docs** — S — closed every gap the card names, README-only. Added a
  **Windows install** section with real, individually-verified `winget` package IDs (`Python.Python.
  3.11`, `OpenJS.NodeJS.LTS`, `Gyan.FFmpeg`, `calibre.calibre`) — checked against real `winget search`
  output on this machine rather than assumed, since a wrong package ID in setup docs is worse than no
  docs at all; also flags the "installers don't update your current terminal's `PATH`" gotcha, since
  that's the step that actually trips people up. A **First run** walkthrough (upload → chapter review
  → render config → live progress → download/retry → Settings) documents the real UI as it exists
  today, cross-checked against the actual frontend source rather than described from memory — caught
  and corrected one real inaccuracy in a first draft (called Settings part of a "top nav"; the app
  actually has a left sidebar, per `AppShell.tsx`) and one wrong number (guessed "~1.1 GB" for the
  model download; the real manifest total, cross-checked against this session's own live
  `/api/settings/disk-usage` reading, is ~570 MB). **Measured performance** ([M6-1]'s RTF table) was
  already in place from that card. No test suite applies to a documentation-only change; verified by
  re-reading the finished section against the real running app and source rather than by any
  automated check.

### M5 — Publishing (all 9 cards) — 🎯 G4 achieved

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

- **[M5-8] Part splitting under 12 h** — M · M5-3 — a new `publish/split.py` greedily packs a
  book's `ChapterMarker` list (the same one [M5-1]/[M5-7] already compute) into chapter-aligned
  "parts": it keeps adding the next chapter to the current part until doing so would push the part
  past `mp4_part_limit_s` (default 11h45m, 15 minutes under YouTube's 12h cap), then starts a new
  part — a part never cuts a chapter in half, and a single chapter longer than the limit on its own
  still becomes its own (over-limit) part rather than being split mid-chapter, which would break its
  own marker. Scoped to **MP4 only**, not every format (matching the card's own `M5-3` dependency,
  and PLAN.md's framing of this feature as specifically for YouTube's cap) — M4B/MP3/etc. single
  files aren't platform-capped the way a YouTube upload is, and splitting them too would have meant
  reworking `output_path`/`/download`/`/stream`'s long-standing single-file assumptions for no real
  benefit. Chapter-range extraction from the mastered WAV uses `audio/encode.py`'s new
  `extract_wav_range()` — direct `soundfile` sample-index slicing rather than ffmpeg `-ss`/`-to`,
  which sidesteps seek-accuracy caveats entirely (WAV is uncompressed PCM, so sample-index slicing is
  always exact). `JobArtifact` gained nullable `part_index`/`part_total` columns so a split format can
  have several rows sharing one `format` string; every other format leaves both `None`, and an
  unsplit MP4 (the common case) is byte-for-byte the same single, plainly-named file as before this
  card — splitting must never rename a book's output when it doesn't actually apply. The limit is a
  real Settings-page-backed value (`mp4_part_limit_s`, alongside the pre-existing worker-count/
  loudness settings), not a hardcoded constant, so "configurable" per the card's own description is
  literal, not just "a function parameter nobody can reach." The jobs API's artifact-download endpoint
  gained `?part=N` (1-based, defaulting to part 1 when omitted) to reach each part; `JobOut.artifacts`
  stays a deduplicated format list (a 3-part MP4 job still reports one `"mp4"` entry, not three) so
  the pre-existing per-format download-button loop keeps working without changes — a fully
  multi-part-aware download panel is explicitly [M5-9]'s job, not this card's.
  ✅ Verified concretely, real synthesis end to end, not just the grouping logic in isolation: 11 new
  `test_split.py` cases cover the packing/rebasing/naming logic against synthetic markers (including
  a never-cuts-a-chapter check and a degenerate zero/negative-limit input), 2 new
  `test_loudness_encode.py` cases confirm `extract_wav_range()` is sample-accurate (compared directly
  against the source array, not just "the right approximate length") and correctly clamps an
  out-of-range end time, and a `@pytest.mark.slow` pipeline test forces the real 2-chapter fixture
  book to actually split (via a tiny `mp4_part_limit_s=1.0`) and confirms each part is a real,
  independently-valid MP4 whose *durations sum back to* the same book rendered unsplit (proving the
  split lost or duplicated no audio at the chapter boundary), with consistent `"Book - Part N of
  M.mp4"` naming. A second `@pytest.mark.slow` API-level test drives the real HTTP surface — sets the
  tiny limit through the real `PUT /api/settings` endpoint (the same one the Settings page calls, not
  a backdoor), confirms the deduplicated `artifacts` list, and confirms `?part=1`/`?part=2` each
  return a genuinely different real file while an out-of-range part 404s. Full backend suite: 229
  passed (up from 212). Frontend (`Settings.tsx` gained an "MP4 part limit (hours)" field, seconds
  ↔ hours converted at the input boundary) verified via a clean `tsc -b && vite build` and `oxlint`
  pass (same pre-existing, unrelated `Render.tsx` warning; no actual browser session, same
  Chrome-extension-unavailable caveat as the rest of this M5 session).

- **[M5-9] 🎯 G4 — Exports API + download UI** — S · M5-1…M5-8 — the Exports API side was
  essentially complete by the end of [M5-8] (all 9 formats, `?part=N`, deduplication-free artifact
  rows); this card's real work was closing two UI gaps that had accumulated across the whole M5
  sequence: `JobOut.artifacts` changed from a plain deduplicated `list[str]` (which could only ever
  say "an mp4 exists somewhere," not how many parts or which ones) to `list[JobArtifactOut]`
  (`{format, part_index, part_total}`, one entry per real row) so the UI can actually enumerate every
  part; and the Job page's inline download logic was extracted into a shared
  `components/JobDownloads.tsx` (also gaining a one-click "Copy chapters text" button next to the
  download link, matching [M5-7]'s "ready to paste" framing) so the same real, complete download
  panel could be reused rather than re-built. The **second, larger gap**: nothing before this card
  let a user get back to a finished book's downloads without already having the specific Job page URL
  in hand — `GET /api/books/{id}/jobs` had existed unused since [M3-5], and the Book page never called
  it. Fixed with a new `RenderHistory` section on the Book page listing every past render (status
  badge + timestamp + voice, newest first) with that render's full `<JobDownloads>` panel inline —
  this is what makes "every artifact for a finished book downloadable from one panel" literally true
  at the *book* level, not just the job level.
  ✅ Verified end to end against the **real running dev server** (`uvicorn` + real Kokoro synthesis;
  the Chrome extension still wasn't connected in this environment, so the frontend's actual rendering
  couldn't be screenshotted — noted explicitly rather than claimed — but every JSON shape the new
  components consume was independently confirmed real, not assumed): uploaded a real 2-chapter EPUB,
  rendered one normal job (`mp3`+`chapters`) and, after setting `mp4_part_limit_s` to 1 second through
  the real `PUT /api/settings` endpoint, one job that actually split into 2 real MP4 parts — confirmed
  `GET /api/books/{id}/jobs` (what `RenderHistory` calls) returns both jobs with the exact
  `part_index`/`part_total` shape `JobDownloads` groups by, confirmed `?part=1` and `?part=2` each
  download a genuinely different real file (`cmp` verified byte-level difference, not just two
  200s), and confirmed the `chapters` artifact's real text content (what the "Copy" button fetches)
  reads correctly. 229 backend tests passed both before and after this card's `JobOut` schema change
  (the schema change itself is covered by two updated `test_api_jobs.py` assertions: the normal-job
  shape and the split-job shape). Frontend verified via a clean `tsc -b && vite build` and `oxlint`
  pass — the extracted `JobDownloads.tsx` needed its one shared constant made module-private to avoid
  a new "only export components from this file" lint warning, otherwise clean; same pre-existing,
  unrelated `Render.tsx` warning as every other M5 card.

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
| Any script-level (not just test-fixture) code that sets `AUDIOBOOK_DATA_DIR`/similar env state before using `ProcessPoolExecutor` must guard that setup with `if __name__ == "__main__":` | On Windows, `spawn` re-imports the entry script in every worker process with `__name__ == "__mp_main__"`, not `"__main__"`. Unguarded top-level side effects (e.g. `tempfile.mkdtemp()` + an `os.environ` assignment) re-run in each worker too, overwriting its own correctly-*inherited* copy of the env var with a fresh, different value — silently splitting cache reads/writes across processes. Found in [M6-1]'s `bench.py`; the same root mechanism as the pre-existing "stdin heredocs don't mix with multiprocessing on Windows" finding above, just a different symptom. |
