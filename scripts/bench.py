#!/usr/bin/env python3
"""Benchmarks synthesis throughput per language against a fixed ~N-minute passage,
reporting both the raw per-engine RTF (a single-process, unpooled loop of
`engine.synth()` calls — how fast the model itself is) and the end-to-end RTF (the
real `pipeline.runner.run_job()` path: pooled synthesis, assembly, loudness
mastering, MP3 encode — everything an actual render does). Doubles as an RTF gate:
exits non-zero if any language's end-to-end RTF does not beat --target-rtf (default
1.0, i.e. at least 1:1 realtime per PLAN.md).

Usage:
    python scripts/bench.py
    python scripts/bench.py --languages en,zh --minutes 3 --workers 4

Runs entirely in a throwaway data directory (deleted on exit) so it never touches the
app's real cache/output/database, and always re-synthesizes cold — the passage is
"Part N" + a base paragraph set repeated with an incrementing part number, so no two
repetitions produce identical chunk-cache keys and a warm cache can't silently make the
benchmark look faster than real usage.

Run `python scripts/fetch_models.py` first if models/ is empty.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

# Must happen before any `app.*` import (app.config.get_settings() is @lru_cache'd and
# app.db builds its engine from it at import time — the data dir has to be pinned via
# env var first, the same pattern the test suite's isolated_data_dir fixture uses) AND
# must be guarded by `__name__ == "__main__"`: on Windows, ProcessPoolExecutor's spawn
# start method re-imports this script in every worker process with `__name__ ==
# "__mp_main__"`, not `"__main__"` — an unguarded mkdtemp()/os.environ assignment here
# would let each worker overwrite its own *inherited* (and correct) copy of the env var
# with a fresh, different tempdir, splitting cache reads/writes across processes and
# breaking the render with file-not-found errors. Guarding it is what makes each
# worker simply inherit the real parent's already-correct value instead.
if __name__ == "__main__":
    _BENCH_DATA_DIR = Path(tempfile.mkdtemp(prefix="audiobook_bench_"))
    os.environ["AUDIOBOOK_DATA_DIR"] = str(_BENCH_DATA_DIR)

from app import db as _db_module  # noqa: E402
from app.db import get_session, init_db  # noqa: E402
from app.ingest.document import DocBlock, DocChapter, Document  # noqa: E402
from app.ingest.persist import persist_document  # noqa: E402
from app.models import BlockKind  # noqa: E402
from app.pipeline.runner import create_job, run_job  # noqa: E402
from app.text.normalize import get_version as normalizer_version  # noqa: E402
from app.text.normalize import normalize  # noqa: E402
from app.text.segment import segment_text  # noqa: E402
from app.tts.pool import DEFAULT_WORKERS  # noqa: E402
from app.tts.registry import engine_for_language  # noqa: E402

#: same heuristic the frontend's own duration estimate (Book.tsx) uses, so "~5 minutes"
#: here and "~5 minutes" there mean the same thing.
WORDS_PER_MINUTE = 150

#: Original benchmark prose (not excerpted from any real book) — the same short
#: "lighthouse keeper" narrative in each language, chosen to exercise the kind of
#: numbers/dates/currency/percentages the normalizers actually handle, not just plain
#: words. language -> (voice id, base paragraphs).
_PASSAGES: dict[str, tuple[str, list[str]]] = {
    "en": (
        "af_heart",
        [
            "The old lighthouse keeper had worked this stretch of coast since 1987, and in "
            "that time he had logged more than four thousand ships passing beyond the point.",
            "On clear evenings he could see nearly twelve miles out to sea, where the last "
            "ferry of the day, the Northern Star, finished its final crossing at half past six.",
            "Dr. Alvarez, who visited every August to study the local seabird colonies, once "
            "told him the cliffs held at least 230 nesting pairs, nearly 15% more than a "
            "decade before.",
            "His records showed that on 3 March 1998, a storm drove winds of 90 miles per "
            "hour against the tower, cracking a pane of glass that cost $1,250 to replace.",
            "Still, he preferred the quiet months, when the only sound was the sea itself, "
            "and a cup of tea cost him nothing more than a few minutes of his own company.",
        ],
    ),
    "pl": (
        "pl_PL-gosia-medium",
        [
            "Stary latarnik pracował na tym wybrzeżu od 1987 roku i przez ten czas zanotował "
            "w dzienniku ponad cztery tysiące statków płynących za cyplem.",
            "W pogodne wieczory widział morze na odległość niemal dwunastu mil, gdzie ostatni "
            "prom dnia, Gwiazda Północy, kończył swój kurs o wpół do siódmej.",
            "Doktor Nowak, który odwiedzał latarnię co roku w sierpniu, aby badać kolonie "
            "ptaków morskich, powiedział mu kiedyś, że na klifach gnieździ się co najmniej "
            "230 par, czyli o 15% więcej niż dekadę wcześniej.",
            "Z zapisków wynikało, że 3 marca 1998 roku sztorm uderzył w wieżę wiatrem o "
            "prędkości 90 mil na godzinę, pękła wtedy szyba, której naprawa kosztowała "
            "1250 złotych.",
            "Mimo to latarnik wolał ciche miesiące, gdy jedynym dźwiękiem było samo morze, a "
            "filiżanka herbaty kosztowała go tylko kilka minut własnego towarzystwa.",
        ],
    ),
    "de": (
        "de_DE-thorsten-high",
        [
            "Der alte Leuchtturmwärter arbeitete seit 1987 an dieser Küste und hatte in dieser "
            "Zeit mehr als viertausend Schiffe in seinem Logbuch festgehalten, die an der "
            "Landspitze vorbeifuhren.",
            "An klaren Abenden konnte er fast zwölf Meilen weit aufs Meer hinaussehen, wo die "
            "letzte Fähre des Tages, die Nordstern, um halb sieben ihre letzte Fahrt beendete.",
            "Dr. Weber, der jeden August kam, um die Seevogelkolonien zu untersuchen, erzählte "
            "ihm einmal, dass an den Klippen mindestens 230 Brutpaare nisteten, ein Anstieg "
            "von etwa 15% gegenüber dem Jahrzehnt zuvor.",
            "Seinen Aufzeichnungen zufolge traf am 3. März 1998 ein Sturm mit "
            "Windgeschwindigkeiten von 90 Meilen pro Stunde den Turm und zerbrach eine "
            "Fensterscheibe, deren Reparatur 1250 Euro kostete.",
            "Dennoch mochte er die ruhigen Monate lieber, wenn nur das Meer selbst zu hören "
            "war und eine Tasse Tee ihn nicht mehr kostete als ein paar Minuten seiner "
            "eigenen Gesellschaft.",
        ],
    ),
    "zh": (
        "zf_xiaobei",
        [
            "这位老灯塔看守人从1987年起就在这段海岸工作,这些年来他在日志里记录了四千多艘经过海角的船只。",
            "在晴朗的夜晚,他能望见十二英里外的海面,那天最后一班渡轮「北极星号」在六点半完成了它的最后一次航行。",
            "每年八月都会来研究海鸟栖息地的王博士曾告诉他,悬崖上至少筑有230对鸟巢,比十年前增加了将近15%。",
            "记录显示,1998年3月3日,一场风暴以每小时90英里的风速袭击了灯塔,打碎了一块玻璃,维修花费了1250元。",
            "尽管如此,他还是更喜欢安静的月份,那时唯一的声音就是大海本身,一杯茶只需要他几分钟的独处时光。",
        ],
    ),
}


#: Chinese has no whitespace between words, so a `str.split()` word count silently
#: undercounts it by orders of magnitude (a whole unspaced sentence counts as "one
#: word") — a characters-per-minute heuristic approximates Mandarin narration pace
#: instead. Both are deliberately rough; this only has to get "~N minutes" in the
#: right ballpark, not exact — bench.py reports the real measured duration regardless.
_CHARS_PER_MINUTE_ZH = 240


def _passage_length(language: str, paragraphs: list[str]) -> int:
    if language == "zh":
        return sum(len(p) for p in paragraphs)
    return sum(len(p.split()) for p in paragraphs)


def _target_length(language: str, target_minutes: float) -> int:
    per_minute = _CHARS_PER_MINUTE_ZH if language == "zh" else WORDS_PER_MINUTE
    return max(1, int(target_minutes * per_minute))


def _build_passage(language: str, target_minutes: float) -> list[str]:
    """Repeats the base passage, each repetition prefixed with a distinct "Part N"
    marker, until it reaches roughly `target_minutes`. The marker is what keeps every
    repetition's chunks out of the content-addressed cache from each other within a
    single run — see the module docstring."""
    _, base_paragraphs = _PASSAGES[language]
    target_length = _target_length(language, target_minutes)
    paragraphs: list[str] = []
    part = 1
    while _passage_length(language, paragraphs) < target_length:
        marker = f"第{part}部分。" if language == "zh" else f"Part {part}."
        paragraphs.append(marker)
        paragraphs.extend(base_paragraphs)
        part += 1
    return paragraphs


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _engine_rtf(language: str, paragraphs: list[str], voice: str) -> tuple[float, float]:
    """Raw, single-process synth speed: normalize+segment the passage exactly like the
    real pipeline does (per-block, never crossing a block boundary — see
    text/segment.py), then synth every resulting chunk sequentially through the engine
    directly, with no worker pool and no assembly/mastering/encode overhead."""
    engine = engine_for_language(language)
    chunks: list[str] = []
    for paragraph in paragraphs:
        normalized = normalize(paragraph, language)
        chunks.extend(segment_text(normalized, language))

    total_audio_s = 0.0
    t0 = time.time()
    for chunk in chunks:
        samples, sr = engine.synth(chunk, voice)
        total_audio_s += len(samples) / sr
    elapsed = time.time() - t0
    return elapsed, total_audio_s


def _end_to_end_rtf(language: str, paragraphs: list[str], voice: str, workers: int) -> tuple[float, float]:
    """The real production path a user's render actually takes."""
    session_gen = get_session()
    session = next(session_gen)
    try:
        document = Document(
            title=f"Bench {language}",
            language=language,
            chapters=[
                DocChapter(
                    index=0, title="Bench Chapter",
                    blocks=[DocBlock(kind=BlockKind.para, text=p) for p in paragraphs],
                )
            ],
        )
        book = persist_document(session, document, Path(f"bench_{language}.txt"), "txt")
        job = create_job(
            session, book, voice=voice, speed=1.0, engine_id=engine_for_language(language).id,
            formats=["mp3"],
        )
        t0 = time.time()
        output_path = run_job(session, job, workers=workers)
        elapsed = time.time() - t0
        duration = _probe_duration(output_path)
        return elapsed, duration
    finally:
        session_gen.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--languages", default="en,pl,de,zh", help="comma-separated language codes to bench")
    parser.add_argument("--minutes", type=float, default=5.0, help="target passage length in minutes (default: 5)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"pool size (default: {DEFAULT_WORKERS})")
    parser.add_argument("--target-rtf", type=float, default=1.0, help="end-to-end RTF gate threshold (default: 1.0)")
    args = parser.parse_args()

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    unknown = sorted(set(languages) - set(_PASSAGES))
    if unknown:
        print(f"error: unknown language(s) {unknown}; supported: {sorted(_PASSAGES)}", file=sys.stderr)
        return 1

    init_db()

    print(f"Workers: {args.workers}  Target passage: ~{args.minutes:.1f} min  RTF gate: < {args.target_rtf}\n")
    header = f"{'Lang':<6}{'Voice':<22}{'Audio':>9}{'Engine RTF':>13}{'End-to-end RTF':>17}   Gate"
    print(header)
    print("-" * len(header))

    failed: list[str] = []
    try:
        for language in languages:
            voice, _ = _PASSAGES[language]
            paragraphs = _build_passage(language, args.minutes)
            normalizer_version(language)  # sanity: raises early if language is unregistered

            engine_elapsed, engine_audio_s = _engine_rtf(language, paragraphs, voice)
            engine_rtf = engine_elapsed / engine_audio_s if engine_audio_s else float("nan")

            e2e_elapsed, e2e_audio_s = _end_to_end_rtf(language, paragraphs, voice, args.workers)
            e2e_rtf = e2e_elapsed / e2e_audio_s if e2e_audio_s else float("nan")

            gate_ok = e2e_rtf < args.target_rtf
            if not gate_ok:
                failed.append(language)

            print(
                f"{language:<6}{voice:<22}{e2e_audio_s:>8.1f}s{engine_rtf:>13.3f}{e2e_rtf:>17.3f}   "
                f"{'OK' if gate_ok else 'FAIL'}"
            )
    finally:
        # SQLite keeps its file locked on Windows until the engine's connections are
        # explicitly disposed — without this, rmtree() (still running before process
        # exit) silently fails to remove app.db and leaves an empty directory behind.
        _db_module._engine.dispose()
        shutil.rmtree(_BENCH_DATA_DIR, ignore_errors=True)

    print()
    if failed:
        print(f"RTF gate FAILED for: {', '.join(failed)} (target < {args.target_rtf})", file=sys.stderr)
        return 1
    print(f"RTF gate passed for all {len(languages)} language(s) (target < {args.target_rtf}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
