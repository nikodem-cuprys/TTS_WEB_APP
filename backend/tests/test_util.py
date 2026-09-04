"""Regression test for a real bug found during M3 browser testing: SQLite round-trips
our (always-UTC) datetime columns as naive, and a bare .isoformat() on a naive value
produces a string with no UTC offset — which JavaScript's Date parser then reads as
*local* time, making every "elapsed time" display wrong by the viewer's UTC offset.
"""
from datetime import datetime, timezone

from app.util import utc_iso


def test_utc_iso_none_passthrough():
    assert utc_iso(None) is None


def test_utc_iso_adds_offset_to_naive_datetime():
    naive = datetime(2026, 1, 15, 12, 30, 0)
    result = utc_iso(naive)
    assert result == "2026-01-15T12:30:00+00:00"
    # critically: JS's `new Date(result)` must parse this as UTC, not local time —
    # the "+00:00" suffix is exactly what guarantees that.
    assert result.endswith("+00:00")


def test_utc_iso_preserves_existing_aware_datetime():
    aware = datetime(2026, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
    assert utc_iso(aware) == "2026-01-15T12:30:00+00:00"
