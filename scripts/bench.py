#!/usr/bin/env python3
"""Measures end-to-end real-time factor (RTF) per language and gates the 1:1 throughput
requirement from PLAN.md. Stubbed until the TTS engines land in M2/M4 — see KANBAN.md [M6-1].
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "bench.py is a placeholder until milestone M6 (card [M6-1]).\n"
        "It will synthesize a fixed ~5-minute passage per language (en/pl/de/zh) through\n"
        "the full pipeline (normalize -> segment -> synth -> assemble -> master) and report\n"
        "per-engine and end-to-end RTF. Acceptance: end-to-end RTF < 1.0 with the default\n"
        "4-worker pool. See PLAN.md 'Verification' for the target numbers.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
