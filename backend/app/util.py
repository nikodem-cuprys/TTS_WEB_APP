"""Small helpers with no natural home in a more specific module."""
from datetime import datetime, timezone


def utc_iso(dt: datetime | None) -> str | None:
    """ISO 8601 with an explicit UTC offset, even for a naive datetime.

    SQLite has no native datetime type — SQLAlchemy stores our (always UTC)
    timestamps as text and hands back a naive datetime on read, silently dropping
    the tzinfo that was there when the row was written. A bare `.isoformat()` on
    that naive value produces a string with no offset ("2026-01-01T12:00:00"), which
    JavaScript's `Date` parser then treats as *local* time, not UTC — every reader
    ends up off by their own UTC offset. Everything in this app is UTC, so a naive
    value is always safe to label as UTC explicitly here.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
